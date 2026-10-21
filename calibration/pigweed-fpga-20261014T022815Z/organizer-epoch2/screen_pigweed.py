#!/usr/bin/env python3
"""Host-only PigWeedSAT readiness screen for the 210-instance corpus.

For every original CNF (byte-identical to the manifest cache, taken from the
CPU calibration package) this compares the candidate's actual host parser
(satlat.host.parse_dimacs) against the strict original, then calls the
candidate's actual build_images with pigweed(Config(lit_page=P)) for P=4,8,16.
No RTL simulation, synthesis or board access.  Candidate code runs in a
separate `python -B` subprocess per instance so crashes stay distinct from
capacity rejections.  Nothing under PigWeedSAT/ is modified.

Outputs (in --out): rows.csv (210 x 3), summary.json, run.json.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CANDIDATE_ROOT = os.path.join(ROOT, "PigWeedSAT")
sys.path.insert(0, CANDIDATE_ROOT)

DEFAULT_MANIFEST = os.path.join(HERE, "manifest.csv")
DEFAULT_CPU_RUN = os.path.join(HERE, "calibration", "cpu-v0")
DEFAULT_OUT = os.path.join(HERE, "calibration", "pigweed-v0")

PAGES = (4, 8, 16)
BASELINE_PAGE = 16          # matches Table3 / satbench freeze
TIERS = ("S", "S-tight", "M-low", "M-high")
WORKER_TIMEOUT_SECONDS = 600


# ---------------------------------------------------------------------------
# Worker: runs the unchanged candidate code (separate `python -B` process)
# ---------------------------------------------------------------------------

def worker_main(cnf_path: str, result_path: str) -> int:
    out: dict = {"candidate_parse": None, "builds": {}, "caps": None}
    try:
        import satlat.host as host           # actual unchanged loader
        import design as D                   # capacity constants it enforces
        out["caps"] = {k: getattr(D, k) for k in
                       ("N_MAX", "C_MAX", "LE_MAX", "CE_MAX", "MAX_LEARN",
                        "NUM_W", "REM_W", "FREE_W", "VAR_W", "LVL_W")}
        nv, clauses = host.parse_dimacs(cnf_path)
        out["candidate_parse"] = {"num_vars": nv, "clauses": clauses}
    except Exception as e:                   # noqa: BLE001 - classify as crash
        out["candidate_parse"] = {"crash": f"{type(e).__name__}: {e}",
                                  "trace": traceback.format_exc()[-1500:]}
        with open(result_path, "w") as f:
            json.dump(out, f)
        return 0
    for page in PAGES:
        try:
            cfg = host.pigweed(host.Config(lit_page=page))
            img = host.build_images(nv, clauses, cfg)
            out["builds"][str(page)] = {
                "status": "loaded",
                "lit_words": img.lit_elems,
                "cls_words": img.cls_elems,
                "fixed_height": img.fixed_height,
                "clause_ids_used": img.num_clauses,
                "lit_store_len": len(img.lit_store),
                "cls_store_len": len(img.cls_store),
            }
        except host.Unsupported as e:
            out["builds"][str(page)] = {"status": "unsupported",
                                        "reason": str(e)}
        except Exception as e:               # noqa: BLE001
            out["builds"][str(page)] = {
                "status": "crash", "reason": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc()[-1500:]}
    with open(result_path, "w") as f:
        json.dump(out, f)
    return 0


# ---------------------------------------------------------------------------
# Parent-side pure helpers
# ---------------------------------------------------------------------------

def expected_candidate_clauses(strict_clauses, declared_clauses: int):
    """What the candidate parser is *observed* to do to a strict formula:
    drop repeated literals within a clause, sort by |lit|, drop empty
    clauses, truncate to the declared clause count."""
    out = []
    for c in strict_clauses:
        seen, kept = set(), []
        for x in c:
            if x not in seen:
                seen.add(x)
                kept.append(x)
        kept.sort(key=abs)
        out.append(kept)
    out = [c for c in out if c][:declared_clauses]
    return out


def compare_semantics(strict_nv: int, strict_clauses, cand_nv: int,
                      cand_clauses) -> dict:
    """Compare candidate-parsed input to the strict original.

    Allowed normalization (recorded, not an error): within-clause sorting and
    repeated-literal removal.  Everything else (variable count, clause
    count/order, polarity, dropped empty clauses) is input_semantics_error.
    """
    reordered = 0
    if len(strict_clauses) == len(cand_clauses):   # positions align only then
        for orig, cand in zip(strict_clauses, cand_clauses):
            if list(orig) != list(cand):
                reordered += 1
    empty_in_original = sum(1 for c in strict_clauses if len(c) == 0)
    problems = []
    if cand_nv != strict_nv:
        problems.append(f"variable count {cand_nv} != original {strict_nv}")
    if len(cand_clauses) != len(strict_clauses):
        problems.append(
            f"clause count {len(cand_clauses)} != original {len(strict_clauses)}"
            + (f" ({empty_in_original} empty clause(s) dropped)"
               if empty_in_original else ""))
    else:
        expected = expected_candidate_clauses(strict_clauses, len(strict_clauses))
        for i, (e, cand) in enumerate(zip(expected, cand_clauses)):
            if list(cand) != e:
                problems.append(f"clause {i + 1} differs beyond sort/dedup")
                break
    if empty_in_original and not any("empty" in p for p in problems):
        problems.append(f"{empty_in_original} empty clause(s) in original")
    return {
        "status": "input_semantics_error" if problems else "ok",
        "detail": "; ".join(problems),
        "normalized_clauses": reordered,
        "empty_clauses_in_original": empty_in_original,
    }


def classify_unsupported(reason: str) -> str:
    for key, label in (("variables >", "variables"), ("clauses >", "clauses"),
                       ("clause store", "clause_store"),
                       ("literal store", "literal_store")):
        if key in reason:
            return label
    return "other"


def field_flags(caps: dict, max_clause_len: int, fixed_height: int = 0) -> list[str]:
    """Applicable fixed-field/stack limits that packing does not enforce.

    The answer stack holds N_MAX entries (design.py 'stk'); build_images does
    not check the fixed-decision height against it (contradictory units or
    repeated unit clauses can push it past N_MAX).
    """
    flags = []
    if caps and max_clause_len >= (1 << caps["NUM_W"]):
        flags.append(f"clause_len>={1 << caps['NUM_W']}(NUM_W={caps['NUM_W']})")
    if caps and max_clause_len >= (1 << caps["REM_W"]):
        flags.append(f"clause_len>={1 << caps['REM_W']}(REM_W={caps['REM_W']})")
    if caps and fixed_height > caps["N_MAX"]:
        flags.append(f"fixed_stack={fixed_height}>N_MAX={caps['N_MAX']}")
    return flags


def occupancy(build: dict, caps: dict) -> dict:
    cw = build["cls_words"] / caps["CE_MAX"]
    lw = build["lit_words"] / caps["LE_MAX"]
    ci = build["clause_ids_used"] / caps["C_MAX"]
    return {"clause_word_frac": cw, "lit_word_frac": lw,
            "clause_id_frac": ci, "occupancy": max(cw, lw, ci)}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_cpu_results(cpu_run: str) -> dict[str, dict]:
    path = os.path.join(cpu_run, "results.csv")
    with open(path, newline="", encoding="utf-8") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def run_worker(cnf_path: str) -> dict:
    with tempfile.TemporaryDirectory() as td:
        result = os.path.join(td, "result.json")
        try:
            proc = subprocess.run(
                [sys.executable, "-B", os.path.abspath(__file__),
                 "--worker", cnf_path, "--result", result],
                capture_output=True, text=True, timeout=WORKER_TIMEOUT_SECONDS,
                cwd=ROOT)
        except subprocess.TimeoutExpired:
            return {"worker_crash": f"timeout after {WORKER_TIMEOUT_SECONDS}s"}
        if proc.returncode != 0 or not os.path.isfile(result):
            return {"worker_crash":
                    f"exit {proc.returncode}: {proc.stderr.strip()[-500:]}"}
        with open(result) as f:
            return json.load(f)


# ---------------------------------------------------------------------------
# Screen
# ---------------------------------------------------------------------------

ROW_FIELDS = [
    "id", "tier", "family", "category", "result_gbd", "variables", "clauses",
    "literals", "max_width", "cpu_certified", "cpu_certified_kind",
    "cpu_reason", "cpu_solve_wall_seconds", "semantics_status",
    "semantics_detail", "normalized_clauses", "lit_page", "build_status",
    "build_reason", "unsupported_bucket", "lit_words", "cls_words",
    "fixed_height", "clause_ids_used", "clause_ids_free", "clause_word_frac",
    "lit_word_frac", "clause_id_frac", "occupancy", "field_flags",
    "dispatchable",
]


def screen_instance(row: dict, cpu: dict, cpu_run: str) -> list[dict]:
    from benchmark_cnf import parse_dimacs as strict_parse   # strict original

    iid = row["id"]
    attempt = int(cpu["attempt"])
    cnf_path = os.path.join(cpu_run, "attempts", iid,
                            f"attempt-{attempt:03d}", "input.cnf")
    if sha256_file(cnf_path) != row["cnf_sha256"]:
        raise RuntimeError(f"{iid}: input.cnf hash != manifest cnf_sha256")
    with open(cnf_path, encoding="utf-8") as f:
        strict = strict_parse(f.read())
    max_len = max((len(c) for c in strict.clauses), default=0)

    base = {
        "id": iid, "tier": row["tier"], "family": row["family"],
        "category": row["category"], "result_gbd": row["result_gbd"],
        "variables": row["variables"], "clauses": row["clauses"],
        "literals": row["literals"], "max_width": row["max_width"],
        "cpu_certified": cpu["certified"],
        "cpu_certified_kind": cpu["certified_kind"],
        "cpu_reason": cpu["reason"],
        "cpu_solve_wall_seconds": cpu["solve_wall_seconds"],
    }
    res = run_worker(cnf_path)
    rows = []

    def emit(page, **kw):
        r = {f: "" for f in ROW_FIELDS}
        r.update(base)
        r["lit_page"] = page
        r.update(kw)
        rows.append(r)

    if "worker_crash" in res or "crash" in (res.get("candidate_parse") or {}):
        why = res.get("worker_crash") or res["candidate_parse"]["crash"]
        for page in PAGES:
            emit(page, semantics_status="candidate_crash",
                 semantics_detail=why, build_status="crash",
                 build_reason=why, dispatchable="false")
        return rows

    cp = res["candidate_parse"]
    sem = compare_semantics(strict.num_vars, strict.clauses, cp["num_vars"],
                            cp["clauses"])
    caps = res["caps"]
    for page in PAGES:
        b = res["builds"][str(page)]
        flags = field_flags(caps, max_len, b.get("fixed_height", 0))
        kw = {
            "semantics_status": sem["status"],
            "semantics_detail": sem["detail"],
            "normalized_clauses": sem["normalized_clauses"],
            "build_status": b["status"],
            "field_flags": ";".join(flags),
        }
        if b["status"] == "loaded":
            occ = occupancy(b, caps)
            kw.update({
                "lit_words": b["lit_words"], "cls_words": b["cls_words"],
                "fixed_height": b["fixed_height"],
                "clause_ids_used": b["clause_ids_used"],
                "clause_ids_free": caps["C_MAX"] - b["clause_ids_used"],
                "clause_word_frac": f"{occ['clause_word_frac']:.6f}",
                "lit_word_frac": f"{occ['lit_word_frac']:.6f}",
                "clause_id_frac": f"{occ['clause_id_frac']:.6f}",
                "occupancy": f"{occ['occupancy']:.6f}",
            })
        else:
            kw["build_reason"] = b["reason"]
            if b["status"] == "unsupported":
                kw["unsupported_bucket"] = classify_unsupported(b["reason"])
        kw["dispatchable"] = str(
            sem["status"] == "ok" and b["status"] == "loaded" and not flags
        ).lower()
        emit(page, **kw)
    return rows


def pilot_candidates(rows: list[dict]) -> dict:
    """Per tier at P=16 among CPU-certified, semantics-safe, loadable rows:
    fastest SAT, fastest UNSAT, max initial occupancy.  Ties by ID.  Empty
    cells stay explicit gaps (no cross-tier substitution)."""
    out = {}
    eligible = [r for r in rows if int(r["lit_page"]) == BASELINE_PAGE
                and r["cpu_certified"] == "true"
                and r["semantics_status"] == "ok"
                and r["build_status"] == "loaded"
                and r["dispatchable"] == "true"]
    for tier in TIERS:
        cell = {"fastest_sat": None, "fastest_unsat": None,
                "max_occupancy": None}
        tr = [r for r in eligible if r["tier"] == tier]
        for key, kind in (("fastest_sat", "sat_witness"),
                          ("fastest_unsat", "unsat_proof")):
            cand = [r for r in tr if r["cpu_certified_kind"] == kind]
            if cand:
                best = min(cand, key=lambda r: (float(r["cpu_solve_wall_seconds"]),
                                                r["id"]))
                cell[key] = {"id": best["id"],
                             "cpu_solve_wall_seconds": float(best["cpu_solve_wall_seconds"]),
                             "occupancy": float(best["occupancy"])}
        if tr:
            top = max(float(r["occupancy"]) for r in tr)
            best = min((r for r in tr if float(r["occupancy"]) == top),
                       key=lambda r: r["id"])
            cell["max_occupancy"] = {"id": best["id"],
                                     "occupancy": float(best["occupancy"]),
                                     "cpu_certified_kind": best["cpu_certified_kind"]}
        ids = sorted({v["id"] for v in cell.values() if v})
        out[tier] = {"cells": cell, "ids": ids,
                     "gaps": [k for k, v in cell.items() if v is None]}
    out["all_ids"] = sorted({i for t in TIERS for i in out[t]["ids"]})
    return out


def derive_summary(rows: list[dict]) -> dict:
    def count(pred):
        return sum(1 for r in rows if pred(r))

    summary = {"rows": len(rows),
               "distinct_ids": len({r["id"] for r in rows}),
               "per_page": {}, "semantics": {}, "pilots": pilot_candidates(rows),
               "notes": [
                   "Packing success proves neither dynamic headroom nor "
                   "physical/semantic correctness.",
                   "MAX_LEARN=1024 is a dynamic learned-clause limit, not an "
                   "original width cap; packing does not exercise it.",
                   "P=16 is the baseline (matches Table3/satbench); P=4/8 are "
                   "sensitivity, not per-instance tuning.",
               ]}
    for page in PAGES:
        pr = [r for r in rows if int(r["lit_page"]) == page]
        buckets: dict[str, int] = {}
        for r in pr:
            if r["build_status"] == "unsupported":
                buckets[r["unsupported_bucket"]] = buckets.get(
                    r["unsupported_bucket"], 0) + 1
        by_tier = {}
        for tier in TIERS:
            tr = [r for r in pr if r["tier"] == tier]
            by_tier[tier] = {
                "total": len(tr),
                "loaded": sum(1 for r in tr if r["build_status"] == "loaded"),
                "dispatchable": sum(1 for r in tr if r["dispatchable"] == "true"),
                "dispatchable_and_cpu_certified": sum(
                    1 for r in tr if r["dispatchable"] == "true"
                    and r["cpu_certified"] == "true"),
            }
        summary["per_page"][str(page)] = {
            "loaded": sum(1 for r in pr if r["build_status"] == "loaded"),
            "unsupported": sum(1 for r in pr if r["build_status"] == "unsupported"),
            "crash": sum(1 for r in pr if r["build_status"] == "crash"),
            "unsupported_buckets": buckets,
            "field_flagged": sum(1 for r in pr if r["field_flags"]),
            "dispatchable": sum(1 for r in pr if r["dispatchable"] == "true"),
            "dispatchable_and_cpu_certified": sum(
                1 for r in pr if r["dispatchable"] == "true"
                and r["cpu_certified"] == "true"),
            "loaded_but_cpu_uncertified": sum(
                1 for r in pr if r["build_status"] == "loaded"
                and r["cpu_certified"] != "true"),
            "by_tier": by_tier,
        }
    p16 = [r for r in rows if int(r["lit_page"]) == BASELINE_PAGE]
    summary["semantics"] = {
        "ok": sum(1 for r in p16 if r["semantics_status"] == "ok"),
        "input_semantics_error": sum(
            1 for r in p16 if r["semantics_status"] == "input_semantics_error"),
        "candidate_crash": sum(
            1 for r in p16 if r["semantics_status"] == "candidate_crash"),
        "instances_with_within_clause_normalization": sum(
            1 for r in p16 if int(r["normalized_clauses"] or 0) > 0),
    }
    loaded16 = [r for r in p16 if r["build_status"] == "loaded"]
    if loaded16:
        top_occ = max(float(r["occupancy"]) for r in loaded16)
        top = min((r for r in loaded16 if float(r["occupancy"]) == top_occ),
                  key=lambda r: r["id"])
        summary["max_occupancy_p16"] = {"id": top["id"],
                                        "occupancy": float(top["occupancy"]),
                                        "lit_words": int(top["lit_words"]),
                                        "cls_words": int(top["cls_words"]),
                                        "clause_ids_used": int(top["clause_ids_used"])}
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--cpu-run", default=DEFAULT_CPU_RUN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--result", help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.worker:
        return worker_main(args.worker, args.result)

    out_dir = os.path.abspath(args.out)
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        print(f"error: {out_dir} exists and is not empty", file=sys.stderr)
        return 1
    cpu_run = os.path.abspath(args.cpu_run)
    with open(args.manifest, newline="", encoding="utf-8") as f:
        manifest = list(csv.DictReader(f))
    cpu = load_cpu_results(cpu_run)
    missing = [r["id"] for r in manifest if r["id"] not in cpu]
    if missing or len(cpu) != len(manifest):
        print(f"error: CPU run lacks rows for {missing[:5]} "
              f"({len(cpu)} vs {len(manifest)})", file=sys.stderr)
        return 1

    rows: list[dict] = []
    for i, m in enumerate(manifest, 1):
        rows.extend(screen_instance(m, cpu[m["id"]], cpu_run))
        if i % 30 == 0:
            print(f"[screen] {i}/{len(manifest)}", flush=True)

    summary = derive_summary(rows)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "rows.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=ROW_FIELDS)
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)
    cand = {
        "host_py_sha256": sha256_file(os.path.join(CANDIDATE_ROOT, "satlat", "host.py")),
        "design_py_sha256": sha256_file(os.path.join(CANDIDATE_ROOT, "design.py")),
        "screen_py_sha256": sha256_file(os.path.abspath(__file__)),
        "manifest_sha256": sha256_file(os.path.abspath(args.manifest)),
        "cpu_summary_sha256": sha256_file(os.path.join(cpu_run, "summary.json")),
        "cpu_results_sha256": sha256_file(os.path.join(cpu_run, "results.csv")),
        "config": "pigweed(Config(lit_page=P)) for P in (4, 8, 16); baseline 16",
        "python": sys.version.split()[0],
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "board_use": False,
    }
    with open(os.path.join(out_dir, "run.json"), "w") as f:
        json.dump(cand, f, indent=1, sort_keys=True)
    print(f"screen complete: {len(rows)} rows, "
          f"{summary['distinct_ids']} distinct ids")
    return 0


if __name__ == "__main__":
    sys.exit(main())
