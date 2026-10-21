#!/usr/bin/env python3
"""Build the Manhattan Reasoning FPGA-SAT benchmark (v0) from existing SAT Competition CNFs.

Recipe (Proposal §4; SAT_Corpus_Feasibility_Assessment.md Part III):
  * sources  : SAT Competition main tracks 2022-2026, crafted tracks 2014-2016,
               random tracks 2016-2018 (category priority main > crafted > random)
  * eligible : memory tier S, S-tight or M in ../gbd_tiers.csv; GBD result sat/unsat;
               one instance per GBD variant group (union of shared isohash/isohash2
               keys over ALL GBD metadata, so ineligible instances also link groups)
  * tiers    : benchmark tiers S, S-tight, M-low, M-high — the tier file's M is split
               into M-low / M-high at the 2/3 quantile of the eligible, deduplicated M
               pool's literal counts (M-high = literal-heaviest third). The manifest's
               `tier` column carries these four labels; `gbd_tier` keeps the tier file's.
  * targets  : TARGETS below; SAT share per tier = reference share of labeled
               main-track 2022-2026 instances; shortfalls reassigned to later tiers
  * diversity: at most FAMILY_CAP instances per GBD family; deterministic round-robin
               over families inside each (tier, result) cell
  * verify   : every accepted instance is downloaded from GBD, decompressed, strictly
               parsed (benchmark_cnf.parse_dimacs) and must match the tier file's
               variables / clauses / literals; failures are rejected and replaced
  * pinning  : if Benchmark/manifest.csv exists, it pins the benchmark: only its instances
               are accepted, each file must match its recorded compressed and CNF SHA-256,
               the regenerated manifest must equal the pinned file byte-for-byte (so
               metadata drift fails instead of silently rewriting it), and a failing
               build leaves manifest.csv/summary.txt untouched (writes summary.failed.txt).
               Pinned runs never rewrite manifest.csv. With no manifest, the build is an
               unpinned online bootstrap (fresh downloads; --offline refused). --repin
               deliberately pins a new selection.

Usage (from the workspace root):
    PigWeedSAT/.venv/bin/python -B Benchmark/build_benchmark.py            # fetch + build
    PigWeedSAT/.venv/bin/python -B Benchmark/build_benchmark.py --offline  # cached bytes only
    PigWeedSAT/.venv/bin/python -B Benchmark/build_benchmark.py --dry-run  # selection only
    PigWeedSAT/.venv/bin/python -B Benchmark/build_benchmark.py --repin    # new pinned version

Outputs (deterministic, no timestamps): Benchmark/manifest.csv, Benchmark/summary.txt,
Benchmark/cnf/<gbd-hash>.cnf.xz. Downloads and the fetch log live in Benchmark/.cache/.
Distribution is link-only: manifest.csv + this script are the shareable benchmark definition;
cnf/ is a local organizer build cache (76 instances carry no explicit license; see the
manifest's license_status column) and must not be packaged or re-hosted as-is.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import lzma
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
from benchmark_cnf import CNFError, parse_dimacs  # noqa: E402

GBD = "https://benchmark-database.de"
ZENODO_MAP = ("https://zenodo.org/records/15125952/files/"
              "sc02to24-gbd-hashes-filenames.txt?download=1")
TIERS_CSV = os.path.join(ROOT, "gbd_tiers.csv")

SEED = "manhattan-sat-benchmark-v0"
SOURCES = [("main", range(2022, 2027)), ("crafted", range(2014, 2017)),
           ("random", range(2016, 2019))]
ELIGIBLE_TIERS = ("S", "S-tight", "M")
TIERS = ["S", "S-tight", "M-low", "M-high"]   # benchmark tiers
TARGETS = {"S": 22, "S-tight": 72, "M-low": 64, "M-high": 52}
REASSIGN_ORDER = ["S-tight", "M-low", "M-high"]
FAMILY_CAP = 10
M_HIGH_QUANTILE = 2 / 3      # M-low <= split < M-high
SIZE_RANGE = (200, 300)
SAT_SHARE_TOLERANCE = 0.02
TIER_TOLERANCE = 5           # |achieved - target| per tier, instances
BAD_ISO = {"", "None", "none", "unknown", None}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def order_key(s: str) -> str:
    return hashlib.sha256(f"{SEED}:{s}".encode()).hexdigest()


def track_years(tracks: str, kind: str) -> set[int]:
    out = set()
    for t in tracks.split():
        m = re.fullmatch(r"([a-z]+)_(\d{4})", t)
        if m and m.group(1) == kind:
            out.add(int(m.group(2)))
    return out


def category(row: dict) -> str | None:
    for kind, years in SOURCES:
        if track_years(row["tracks"], kind) & set(years):
            return kind
    return None


def source_tracks(row: dict) -> str:
    keep = []
    for kind, years in SOURCES:
        for y in sorted(track_years(row["tracks"], kind) & set(years)):
            keep.append(f"{kind}_{y}")
    return " ".join(keep)


class Fetcher:
    def __init__(self, cache: str, offline: bool):
        self.cache, self.offline = cache, offline
        os.makedirs(cache, exist_ok=True)
        self.log_path = os.path.join(cache, "fetch_log.jsonl")

    def log(self, rec: dict) -> None:
        rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with open(self.log_path, "a") as f:
            f.write(json.dumps(rec, sort_keys=True) + "\n")

    def get(self, url: str, dest: str, timeout: int = 120) -> str | None:
        """Return None on success, else an error string; never raises for HTTP errors."""
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return None
        if self.offline:
            return "missing in --offline mode"
        err = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "mr-benchmark/0"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = r.read()
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with open(dest + ".tmp", "wb") as f:
                    f.write(data)
                os.replace(dest + ".tmp", dest)
                self.log({"url": url, "dest": os.path.relpath(dest, ROOT), "bytes": len(data)})
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                err = f"{type(e).__name__}: {e}"
                if attempt == 1:
                    time.sleep(5)
        self.log({"url": url, "error": err})
        return err


def load_meta(path: str):
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    iso = {h: (a, b) for h, a, b in con.execute("SELECT hash, isohash, isohash2 FROM features")}
    alias = {}
    for h, v in con.execute("SELECT hash, value FROM filename ORDER BY hash, value"):
        alias.setdefault(h, v)
    con.close()
    return iso, alias


def dedupe(rows: list[dict], iso: dict) -> tuple[list[dict], dict]:
    """Variant groups = connected components of hashes linked by shared, non-empty
    isohash/isohash2 keys over ALL GBD metadata; keep the smallest eligible hash per group.
    Returns (deduplicated rows, component root per hash)."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for h, keys in sorted(iso.items()):
        find(h)
        for k in keys:
            if k not in BAD_ISO:
                a, b = find("key:" + k), find(h)
                if a != b:
                    parent[max(a, b)] = min(a, b)
    for r in rows:
        find(r["hash"])
    best = {}
    for r in rows:
        g = find(r["hash"])
        if g not in best or r["hash"] < best[g]["hash"]:
            best[g] = r
    return sorted(best.values(), key=lambda r: r["hash"]), {h: find(h) for h in parent}


def verify_instance(row: dict, path: str) -> tuple[dict | None, str]:
    raw = open(path, "rb").read()
    if raw[:6] != b"\xfd7zXZ\x00":
        return None, "not an xz stream"
    try:
        text = lzma.decompress(raw).decode("ascii")
    except (lzma.LZMAError, UnicodeDecodeError) as e:
        return None, f"decompress/decode: {e}"
    try:
        cnf = parse_dimacs(text)
    except CNFError as e:
        return None, f"strict parse: {e}"
    st = cnf.structural()
    got = (cnf.num_vars, len(cnf.clauses), st["literals"])
    want = (int(row["variables"]), int(row["clauses"]), int(row["literals"]))
    if got != want:
        return None, f"size mismatch file {got} vs tiers {want}"
    widths = st["widths"]
    return {
        "compressed_sha256": hashlib.sha256(raw).hexdigest(),
        "cnf_sha256": hashlib.sha256(text.encode("ascii")).hexdigest(),
        "compressed_bytes": len(raw),
        "max_width": max(widths) if widths else 0,
        "mean_width": round(st["literals"] / len(widths), 3) if widths else 0.0,
        "empty_clauses": st["empty_clauses"],
    }, "ok"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repin", action="store_true",
                    help="ignore an existing manifest.csv and pin a new selection (new version)")
    args = ap.parse_args()

    # An existing manifest pins the benchmark: the same instances, byte-identical files.
    # Pin mode follows from the file existing (not from it having rows), so a truncated or
    # empty manifest fails closed instead of silently starting a new pin.
    manifest_path = os.path.join(HERE, "manifest.csv")
    pin_mode = os.path.exists(manifest_path) and not args.repin
    pinned = {}
    if pin_mode:
        with open(manifest_path, newline="") as f:
            reader = csv.DictReader(f)
            need = {"gbd_hash", "compressed_sha256", "cnf_sha256"}
            if not need <= set(reader.fieldnames or []):
                raise SystemExit(f"manifest.csv lacks required columns {sorted(need)}; "
                                 "restore it or rebuild deliberately with --repin")
            for m in reader:
                if not all(m[k] for k in need):
                    raise SystemExit(f"manifest.csv row {m.get('id', '?')} has empty pin fields")
                pinned[m["gbd_hash"]] = (m["compressed_sha256"], m["cnf_sha256"])
        if not pinned:
            raise SystemExit("manifest.csv exists but pins no instances; restore it or use --repin")

    cache = os.path.join(HERE, ".cache")
    fetch = Fetcher(cache, args.offline)
    meta_path = os.path.join(cache, "gbd-meta")
    map_path = os.path.join(cache, "sc02to24-gbd-hashes-filenames.txt")
    for url, dest in ((f"{GBD}/getdatabase/meta", meta_path), (ZENODO_MAP, map_path)):
        err = fetch.get(url, dest, timeout=600)
        if err:
            raise SystemExit(f"cannot obtain {dest}: {err}")

    rows = list(csv.DictReader(open(TIERS_CSV)))
    iso, alias = load_meta(meta_path)
    zenodo = {line.split()[0] for line in open(map_path) if line.strip()}

    # reference SAT share: labeled main-track 2022-2026 instances (all tiers)
    ref = Counter(r["result"] for r in rows if track_years(r["tracks"], "main") & set(range(2022, 2027)))
    sat_share = ref["sat"] / (ref["sat"] + ref["unsat"])

    eligible = [r for r in rows if r["tier"] in ELIGIBLE_TIERS
                and r["result"] in ("sat", "unsat") and category(r)]
    pool, component = dedupe(eligible, iso)
    m_lits = sorted(int(r["literals"]) for r in pool if r["tier"] == "M")
    m_split = m_lits[int(round(M_HIGH_QUANTILE * (len(m_lits) - 1)))]

    def bench_tier(r):
        if r["tier"] != "M":
            return r["tier"]
        return "M-low" if int(r["literals"]) <= m_split else "M-high"

    cnf_dir = os.path.join(HERE, "cnf")
    if not pin_mode and not args.dry_run:
        # No trust root yet (first build or --repin): never trust cached CNF bytes.
        if args.offline:
            raise SystemExit("unpinned build (no manifest, or --repin) must fetch fresh from GBD; "
                             "--offline requires a pinned manifest.csv")
        if os.path.isdir(cnf_dir):
            for name in os.listdir(cnf_dir):
                if name.endswith((".cnf.xz", ".tmp")):
                    os.remove(os.path.join(cnf_dir, name))
    verified: dict[str, dict] = {}
    rejected: list[tuple[str, str]] = []
    pin_mismatch: list[str] = []

    def accept(r) -> bool:
        if args.dry_run:
            return True
        if pin_mode and r["hash"] not in pinned:
            # pinned mode never substitutes: any drift away from the manifest fails the build
            rejected.append((r["hash"], "not in pinned manifest"))
            return False
        dest = os.path.join(cnf_dir, f"{r['hash']}.cnf.xz")
        err = fetch.get(f"{GBD}/file/{r['hash']}?context=cnf", dest)
        if err:
            rejected.append((r["hash"], f"fetch: {err}"))
            return False
        info, why = verify_instance(r, dest)
        if info is None:
            rejected.append((r["hash"], why))
            os.remove(dest)
            return False
        if r["hash"] in pinned and (info["compressed_sha256"], info["cnf_sha256"]) != pinned[r["hash"]]:
            pin_mismatch.append(r["hash"])
            rejected.append((r["hash"], "hash mismatch vs pinned manifest"))
            return False
        verified[r["hash"]] = info
        return True

    taken_family: Counter = Counter()
    picked: dict[str, dict] = {}

    def fill(b: str, res: str, n: int) -> int:
        queues = defaultdict(list)
        cands = [r for r in pool if bench_tier(r) == b and r["result"] == res and r["hash"] not in picked]
        for r in sorted(cands, key=lambda r: order_key(r["hash"])):
            queues[r["family"]].append(r)
        families = sorted(queues, key=order_key)
        got = 0
        while got < n:
            progressed = False
            for f in families:
                if got >= n:
                    break
                while queues[f] and taken_family[f] < FAMILY_CAP:
                    r = queues[f].pop(0)
                    if accept(r):
                        picked[r["hash"]] = r
                        taken_family[f] += 1
                        got += 1
                        progressed = True
                        break
            if not progressed:
                break
        return got

    planned = {}
    deficit = Counter()
    for b in TIERS:
        n_sat = round(TARGETS[b] * sat_share)
        planned[b] = (n_sat, TARGETS[b] - n_sat)
        for res, n in (("sat", n_sat), ("unsat", TARGETS[b] - n_sat)):
            deficit[res] += n - fill(b, res, n)
    reassigned = Counter()
    for res in ("sat", "unsat"):
        for b in REASSIGN_ORDER:
            if deficit[res] > 0:
                g = fill(b, res, deficit[res])
                deficit[res] -= g
                reassigned[(b, res)] += g

    sel = sorted(picked.values(), key=lambda r: (TIERS.index(bench_tier(r)), r["family"], r["hash"]))
    cols = ["id", "gbd_hash", "category", "source_tracks", "family", "tier", "gbd_tier", "result_gbd",
            "variables", "clauses", "literals", "max_width", "mean_width", "alias", "file",
            "compressed_bytes", "compressed_sha256", "cnf_sha256", "url", "license_status",
            "all_tracks"]
    out_rows = []
    for i, r in enumerate(sel, 1):
        v = verified.get(r["hash"], {})
        out_rows.append({
            "id": f"MRB0-{i:03d}", "gbd_hash": r["hash"], "category": category(r),
            "source_tracks": source_tracks(r), "family": r["family"], "tier": bench_tier(r),
            "gbd_tier": r["tier"], "result_gbd": r["result"], "variables": r["variables"],
            "clauses": r["clauses"], "literals": r["literals"],
            "max_width": v.get("max_width", ""), "mean_width": v.get("mean_width", ""),
            "alias": alias.get(r["hash"], ""), "file": f"cnf/{r['hash']}.cnf.xz",
            "compressed_bytes": v.get("compressed_bytes", ""),
            "compressed_sha256": v.get("compressed_sha256", ""),
            "cnf_sha256": v.get("cnf_sha256", ""),
            "url": f"{GBD}/file/{r['hash']}?context=cnf",
            "license_status": ("CC-BY-4.0 via Zenodo 10.5281/zenodo.15125952 archive copy "
                               "(listed there by GBD hash; GBD-served bytes not compared to it)"
                               if r["hash"] in zenodo else "unverified (no license statement found)"),
            "all_tracks": r["tracks"],
        })

    # ---- self-checks
    checks = []

    def check(name, cond, detail=""):
        checks.append((name, bool(cond), detail))

    n = len(sel)
    sat_n = sum(1 for r in sel if r["result"] == "sat")
    fam = Counter(r["family"] for r in sel)
    dup = n - len({component[r["hash"]] for r in sel})
    check("size-in-range", SIZE_RANGE[0] <= n <= SIZE_RANGE[1], f"{n}")
    check("sat-share", abs(sat_n / n - sat_share) <= SAT_SHARE_TOLERANCE,
          f"{sat_n / n:.3f} vs reference {sat_share:.3f}")
    check("family-cap", max(fam.values()) <= FAMILY_CAP, f"max {max(fam.values())}")
    tier_n = Counter(bench_tier(r) for r in sel)
    check("tier-targets", all(abs(tier_n[b] - TARGETS[b]) <= TIER_TOLERANCE for b in TIERS),
          " ".join(f"{b}={tier_n[b]}/{TARGETS[b]}" for b in TIERS))
    check("no-variant-duplicates", dup == 0, f"{dup} (global variant groups)")
    check("eligible-only", all(r["tier"] in ELIGIBLE_TIERS and r["result"] in ("sat", "unsat")
                               and category(r) for r in sel))
    if not args.dry_run:
        check("all-verified", all(r["hash"] in verified for r in sel), f"{len(verified)} verified")
        check("files-present", all(os.path.exists(os.path.join(cnf_dir, f"{r['hash']}.cnf.xz"))
                                   for r in sel))
        stray = sorted(set(os.listdir(cnf_dir)) - {f"{r['hash']}.cnf.xz" for r in sel})
        check("no-stray-files", not stray, f"{len(stray)} stray")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=cols, lineterminator="\r\n")
    w.writeheader()
    w.writerows(out_rows)
    manifest_text = buf.getvalue()
    if pin_mode:
        if not args.dry_run:
            check("pinned-hashes", not pin_mismatch, f"{len(pin_mismatch)} mismatched")
            with open(manifest_path, newline="") as f:
                same = f.read() == manifest_text
            check("pinned-manifest-identical", same,
                  "" if same else "regenerated manifest differs from pinned file (metadata drift?)")
        check("pinned-selection", {r["hash"] for r in sel} == set(pinned),
              f"{len({r['hash'] for r in sel} ^ set(pinned))} differ from pinned manifest")

    bc = Counter(bench_tier(r) for r in sel)
    lines = [
        "Manhattan Reasoning FPGA-SAT benchmark v0 — build summary",
        f"inputs: gbd_tiers.csv sha256={sha256_file(TIERS_CSV)}",
        f"inputs: gbd-meta sha256={sha256_file(meta_path)}",
        f"inputs: zenodo sc02to24 mapping sha256={sha256_file(map_path)}",
        f"seed={SEED} family_cap={FAMILY_CAP} targets={TARGETS} reassign_order={REASSIGN_ORDER}",
        f"reference SAT share (labeled main 2022-2026): {ref['sat']}/{ref['sat'] + ref['unsat']} = {sat_share:.4f}",
        f"eligible (tier S/S-tight/M, labeled, in sources): {len(eligible)}; after isohash dedup: {len(pool)}",
        f"M split at the {M_HIGH_QUANTILE:.4f} quantile of M literal counts (M-low <= split < M-high): {m_split}",
        f"planned (sat, unsat) per tier: {planned}",
        f"reassigned after shortfalls: { {f'{b}/{r}': v for (b, r), v in sorted(reassigned.items())} }",
        f"unmet after reassignment: {dict(deficit)}",
        f"selected: {n}  sat={sat_n} unsat={n - sat_n}  sat share={sat_n / n:.4f}",
        "tier    | n   | share | sat | unsat",
    ]
    for b in TIERS:
        s = sum(1 for r in sel if bench_tier(r) == b and r["result"] == "sat")
        lines.append(f"{b:7s} | {bc[b]:3d} | {bc[b] / n:.3f} | {s:3d} | {bc[b] - s:3d}")
    cat = Counter(category(r) for r in sel)
    lines.append(f"categories: { {k: cat[k] for k, _ in SOURCES} }")
    lines.append(f"families: {len(fam)}  max per family: {max(fam.values())}")
    lines.append("family counts: " + ", ".join(f"{f}={c}" for f, c in sorted(fam.items(), key=lambda kv: (-kv[1], kv[0]))))
    lic = Counter(o["license_status"].split(" ")[0] for o in out_rows)
    lines.append(f"license status: {dict(sorted(lic.items()))}")
    lines.append(f"rejected candidates: {len(rejected)}")
    for h, why in sorted(rejected):
        lines.append(f"  rejected {h}: {why}")
    for name, ok, detail in checks:
        lines.append(f"{'PASS' if ok else 'FAIL'} {name} {detail}")
    lines.append(f"self-checks: {sum(ok for _, ok, _ in checks)}/{len(checks)} passed")

    ok_all = all(ok for _, ok, _ in checks)
    print("\n".join(lines))
    if args.dry_run:
        if not ok_all:
            raise SystemExit("self-check failure (dry run; no files read or written)")
        return
    if not ok_all:
        # fail closed: never overwrite the pinned manifest/summary with a failing build
        with open(os.path.join(HERE, "summary.failed.txt"), "w") as f:
            f.write("\n".join(lines) + "\n")
        raise SystemExit("self-check failure (manifest.csv/summary.txt left untouched; see summary.failed.txt)")
    stale = os.path.join(HERE, "summary.failed.txt")
    if os.path.exists(stale):
        os.remove(stale)
    def atomic_write(path: str, write) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            write(f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    if not pin_mode:   # pinned runs never rewrite the trust root
        atomic_write(manifest_path, lambda f: f.write(manifest_text))
    atomic_write(os.path.join(HERE, "summary.txt"), lambda f: f.write("\n".join(lines) + "\n"))


if __name__ == "__main__":
    main()
