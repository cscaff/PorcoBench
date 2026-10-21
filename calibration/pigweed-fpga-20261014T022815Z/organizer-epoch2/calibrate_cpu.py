#!/usr/bin/env python3
"""Checked CPU calibration campaign for the 210-instance benchmark corpus.

Solves every manifest instance with pinned Kissat (proof-enabled, seed 0),
then independently certifies outcomes:
  * SAT   -> strict total-model parse + benchmark_cnf.check_witness
  * UNSAT -> pinned drat-trim backward check of the solver-written binary DRAT

Every attempt writes its own evidence directory (input, stdout/stderr,
witness/proof, checker logs, attempt.json).  Outcomes are kept separate from
GBD manifest labels; a valid certificate that contradicts the label is a
recorded conflict, never silently resolved.

Exit codes: 0 = all 210 certified and label-consistent; 2 = campaign complete
with unresolved or conflicting outcomes; 1 = invalid setup or incomplete run.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import lzma
import os
import platform
import re
import resource
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
from benchmark_cnf import CNFError, parse_dimacs, check_witness  # noqa: E402

SCHEMA = "calibrate-cpu-attempt/1"
RUN_SCHEMA = "calibrate-cpu-run/1"

DEFAULT_MANIFEST = os.path.join(HERE, "manifest.csv")
DEFAULT_KISSAT = os.path.join(HERE, ".tools", "kissat", "build", "kissat")
DEFAULT_DRAT = os.path.join(HERE, ".tools", "drat-trim", "drat-trim")
DEFAULT_OUT = os.path.join(HERE, "calibration", "cpu-v0")
DEFAULT_SOLVE_TIMEOUT = 1000
DEFAULT_CHECK_TIMEOUT = 3000

OUTPUT_FILE_LIMIT = 8 * 2**30          # per solver/checker output file (RLIMIT_FSIZE)
MIN_FREE_DISK = 20 * 2**30             # stop-safe threshold before each instance
KILL_GRACE_SECONDS = 5.0               # SIGTERM -> SIGKILL escalation window
WALL_OVERRUN_TOLERANCE = 0.5           # child self-exit vs. parent reap jitter

SAT_STATUS = "s SATISFIABLE"
UNSAT_STATUS = "s UNSATISFIABLE"
UNKNOWN_STATUS = "s UNKNOWN"

CONTRADICTORY_CHECKER_MARKERS = (
    "s NOT VERIFIED",
    "s DERIVATION",
    "s TIMEOUT",
    "s MEMORY ALLOCATION ERROR",
    "c ERROR",
    "c error",
)


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj) -> None:
    atomic_write_bytes(path, (json.dumps(obj, indent=1, sort_keys=True) + "\n").encode())


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode())


# ---------------------------------------------------------------------------
# Pure classification helpers (unit-tested in test_calibrate_cpu.py)
# ---------------------------------------------------------------------------

def normalize_lines(text: str) -> list[str]:
    """Split on any CR/LF ending; drat-trim prefixes 'c' lines with a bare CR."""
    return text.splitlines()


def classify_solver_run(exit_code, stdout_text, timeout_flag):
    """Classify a Kissat run.

    Returns (status, claimed, detail) where status is one of
    'sat', 'unsat', 'unknown', 'timeout', 'protocol_error', 'signal'
    and claimed is 'sat'/'unsat'/None.  A deadline kill overrides any
    late success text in the captured stdout.
    """
    lines = normalize_lines(stdout_text)
    sat_n = sum(1 for l in lines if l == SAT_STATUS)
    unsat_n = sum(1 for l in lines if l == UNSAT_STATUS)
    unknown_n = sum(1 for l in lines if l == UNKNOWN_STATUS)

    if timeout_flag:
        return "timeout", None, "external deadline enforced (late output ignored)"
    if exit_code is not None and exit_code < 0:
        return "signal", None, f"terminated by signal {-exit_code}"

    if exit_code == 10 and sat_n == 1 and unsat_n == 0 and unknown_n == 0:
        return "sat", "sat", None
    if exit_code == 20 and unsat_n == 1 and sat_n == 0 and unknown_n == 0:
        return "unsat", "unsat", None
    if exit_code == 0 and unknown_n == 1 and sat_n == 0 and unsat_n == 0:
        return "unknown", None, "solver reported UNKNOWN"
    detail = (f"exit={exit_code} s-lines: sat={sat_n} unsat={unsat_n} "
              f"unknown={unknown_n}")
    return "protocol_error", None, detail


def parse_witness(stdout_text: str, num_vars: int):
    """Parse kissat 'v' lines as one zero-terminated total assignment.

    Returns (assignment dict[int, bool] | None, error: str | None).
    Strict: every variable 1..num_vars exactly once, single trailing 0,
    nothing after the terminator, no out-of-range literals.
    """
    lines = normalize_lines(stdout_text)
    tokens: list[str] = []
    v_lines = [l for l in lines if l == "v" or l.startswith("v ")]
    for line in v_lines:
        tokens.extend(line[1:].split())
    if not tokens:
        return None, "no witness 'v' lines"
    if tokens[-1] != "0":
        return None, "missing terminating 0"
    body = tokens[:-1]
    if "0" in body:
        return None, "extra 0 inside assignment"
    assignment: dict[int, bool] = {}
    for tok in body:
        try:
            lit = int(tok)
        except ValueError:
            return None, f"non-integer literal {tok!r}"
        if lit == 0 or abs(lit) > num_vars:
            return None, f"literal {lit} out of range 1..{num_vars}"
        var = abs(lit)
        if var in assignment:
            return None, f"variable {var} assigned more than once"
        assignment[var] = lit > 0
    missing = [v for v in range(1, num_vars + 1) if v not in assignment]
    if missing:
        return None, f"{len(missing)} variables unassigned (e.g. {missing[:5]})"
    return assignment, None


def classify_checker_run(exit_code, stdout_text, timeout_flag):
    """Classify a drat-trim verification run.

    Returns (classification, certified, detail):
      'verified'                  exit 0 + exact 's VERIFIED', no contradictions
      'trivial_original_formula'  exit 1 + exact 'c trivial UNSAT' + 's VERIFIED'
                                  (checker certified the original formula itself;
                                  sts stayed ERROR, hence exit 1)
      anything else               uncertified with reason detail.
    Note upstream 's TIMEOUT' exits 0 — only the exact status line rule
    distinguishes it from verification.
    """
    lines = normalize_lines(stdout_text)
    has_verified = "s VERIFIED" in lines
    has_trivial = "c trivial UNSAT" in lines
    contradictions = [m for m in CONTRADICTORY_CHECKER_MARKERS if m in lines]
    # real drat-trim error lines carry suffixes: 'c error opening "..."'
    error_prefixes = [l for l in lines
                      if l.startswith("c error") or l.startswith("c ERROR")]
    if timeout_flag:
        return "checker_timeout", False, "external deadline enforced"
    if exit_code is not None and exit_code < 0:
        return "checker_signal", False, f"terminated by signal {-exit_code}"
    if contradictions or error_prefixes:
        detail = "; ".join(contradictions + error_prefixes[:2])
        return "contradictory_status", False, detail
    if exit_code == 0 and has_verified and not has_trivial:
        return "verified", True, None
    if exit_code == 1 and has_trivial and has_verified:
        return "trivial_original_formula", True, None
    detail = (f"exit={exit_code} verified_line={has_verified} "
              f"trivial_line={has_trivial}")
    return "checker_protocol_error", False, detail


def parse_kissat_native_stats(stdout_text: str) -> dict:
    """Extract kissat-reported resource statistics (units in key names).

    Long runs print a human-readable prefix: 'process-time:  6m 25s  385.07
    seconds' — anchor on the numeric token immediately before 'seconds'.
    """
    out = {"kissat_process_time_seconds": None, "kissat_max_rss_bytes": None}
    m = re.search(r"process-time:.*?([0-9.]+) seconds\s*$", stdout_text,
                  re.MULTILINE)
    if m:
        out["kissat_process_time_seconds"] = float(m.group(1))
    m = re.search(r"maximum-resident-set-size:\s*(\d+) bytes", stdout_text)
    if m:
        out["kissat_max_rss_bytes"] = int(m.group(1))
    return out


def parse_checker_time(stdout_text: str):
    m = re.search(r"c verification time: ([0-9.]+) seconds", stdout_text)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Child process management: external wall deadline + process-group kill
# ---------------------------------------------------------------------------

def _child_limits(fsize_limit: int):
    def apply():
        resource.setrlimit(resource.RLIMIT_FSIZE, (fsize_limit, fsize_limit))
    return apply


def _kill_group(proc: subprocess.Popen, sig) -> bool:
    try:
        os.killpg(os.getpgid(proc.pid), sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def run_child(argv, timeout_seconds, stdout_path, stderr_path):
    """Run argv in its own session with an external wall deadline.

    On deadline: SIGTERM the process group, escalate to SIGKILL after
    KILL_GRACE_SECONDS, then reap.  Returns a dict with exit_code
    (negative on signal), wall_seconds, deadline_killed flag.
    """
    start = time.monotonic()
    with open(stdout_path, "wb") as so, open(stderr_path, "wb") as se:
        proc = subprocess.Popen(
            argv, stdout=so, stderr=se, stdin=subprocess.DEVNULL,
            start_new_session=True, preexec_fn=_child_limits(OUTPUT_FILE_LIMIT),
        )
        deadline_killed = False
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            deadline_killed = _kill_group(proc, signal.SIGTERM)
            try:
                proc.wait(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                _kill_group(proc, signal.SIGKILL)
                try:
                    proc.wait(timeout=KILL_GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
        wall = time.monotonic() - start
    # A child that self-exited in the reap window just past the deadline is
    # still treated as timed out (late success text must not certify).
    late = wall > timeout_seconds + WALL_OVERRUN_TOLERANCE
    return {
        "exit_code": proc.returncode,
        "wall_seconds": wall,
        "deadline_killed": bool(deadline_killed or late),
    }


# ---------------------------------------------------------------------------
# Manifest preflight
# ---------------------------------------------------------------------------

MANIFEST_COLUMNS = [
    "id", "gbd_hash", "category", "source_tracks", "family", "tier",
    "gbd_tier", "result_gbd", "variables", "clauses", "literals",
    "max_width", "mean_width", "alias", "file", "compressed_bytes",
    "compressed_sha256", "cnf_sha256", "url", "license_status", "all_tracks",
]


def load_manifest(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in MANIFEST_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"manifest missing columns: {missing}")
        rows = list(reader)
    ids = [r["id"] for r in rows]
    dup_ids = {i for i in ids if ids.count(i) > 1}
    if dup_ids:
        raise ValueError(f"duplicate manifest ids: {sorted(dup_ids)}")
    for col in ("cnf_sha256", "compressed_sha256", "gbd_hash"):
        vals = [r[col] for r in rows]
        dups = {v for v in vals if vals.count(v) > 1}
        if dups:
            raise ValueError(f"duplicate {col} values: {sorted(dups)}")
    return rows


def preflight_instance(row: dict, manifest_parent: str) -> tuple[bytes, str | None]:
    """Verify one manifest row against its cached file; return decompressed bytes."""
    path = os.path.normpath(os.path.join(manifest_parent, row["file"]))
    if not os.path.isfile(path):
        return b"", f"missing file {path}"
    raw = open(path, "rb").read()
    if len(raw) != int(row["compressed_bytes"]):
        return b"", (f"compressed size mismatch: manifest={row['compressed_bytes']} "
                     f"actual={len(raw)}")
    if sha256_bytes(raw) != row["compressed_sha256"]:
        return b"", "compressed sha256 mismatch"
    try:
        data = lzma.decompress(raw)
    except lzma.LZMAError as e:
        return b"", f"lzma decompression failed: {e}"
    if sha256_bytes(data) != row["cnf_sha256"]:
        return b"", "decompressed cnf sha256 mismatch"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        return b"", f"non-utf8 DIMACS: {e}"
    try:
        cnf = parse_dimacs(text)
    except CNFError as e:
        return b"", f"DIMACS parse error: {e}"
    checks = [
        (cnf.num_vars, int(row["variables"]), "variables"),
        (len(cnf.clauses), int(row["clauses"]), "clauses"),
        (sum(len(c) for c in cnf.clauses), int(row["literals"]), "literals"),
        (max((len(c) for c in cnf.clauses), default=0), int(row["max_width"]),
         "max_width"),
    ]
    for actual, expected, name in checks:
        if actual != expected:
            return b"", f"{name} mismatch: manifest={expected} actual={actual}"
    mean = (sum(len(c) for c in cnf.clauses) / len(cnf.clauses)) if cnf.clauses else 0.0
    if abs(mean - float(row["mean_width"])) > 1e-3:
        return b"", f"mean_width mismatch: manifest={row['mean_width']} actual={mean:.6f}"
    return data, None


# ---------------------------------------------------------------------------
# Campaign identity / resume
# ---------------------------------------------------------------------------

def campaign_identity(manifest_path, kissat, drat, solve_timeout, check_timeout) -> dict:
    harness = os.path.abspath(__file__)
    parser = os.path.join(HERE, "benchmark_cnf.py")
    return {
        "manifest_sha256": sha256_file(manifest_path),
        "kissat_sha256": sha256_file(kissat),
        "drat_trim_sha256": sha256_file(drat),
        "harness_sha256": sha256_file(harness),
        "parser_sha256": sha256_file(parser),
        "solve_timeout_seconds": solve_timeout,
        "check_timeout_seconds": check_timeout,
    }


def identity_mismatches(recorded: dict, current: dict) -> list[str]:
    out = []
    for key in sorted(set(recorded) & set(current)):
        if key.endswith("_seconds") and recorded[key] == current[key]:
            continue
        if recorded[key] != current[key]:
            out.append(f"{key}: campaign={recorded[key]!r} current={current[key]!r}")
    for key in sorted(set(current) - set(recorded)):
        out.append(f"{key}: missing from campaign record")
    return out


def host_provenance() -> dict:
    mem = None
    cpu = None
    for cmd, key in ((["sysctl", "-n", "hw.memsize"], "memory_bytes"),
                     (["sysctl", "-n", "machdep.cpu.brand_string"], "cpu")):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                if key == "memory_bytes":
                    mem = int(res.stdout.strip())
                else:
                    cpu = res.stdout.strip()
        except (OSError, ValueError):
            pass
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": cpu,
        "memory_bytes": mem,
        "compiler": _first_line(["cc", "--version"]),
    }


def _first_line(cmd: list[str]):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.splitlines()[0] if r.stdout else None
    except (OSError, IndexError):
        return None


def tool_provenance(kissat: str, drat: str) -> dict:
    def run(args):
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=30)
            return r.stdout.strip() if r.returncode == 0 else None
        except OSError:
            return None

    version = run([kissat, "--version"])
    build = run([kissat, "--build"])
    help_text = run([kissat, "--help"]) or ""
    return {
        "kissat_version_line": version,
        "kissat_build_text": build,
        "kissat_help_excerpt": [l for l in (help_text or "").splitlines()
                                if any(t in l for t in
                                       ("seed", "time", "proof", "usage"))],
        "kissat_help_mentions_seed": "--seed" in help_text,
        "kissat_help_mentions_time": "--time" in help_text,
        "drat_trim_usage_first_line": (run([drat]) or "").splitlines()[0:1],
    }


# ---------------------------------------------------------------------------
# Attempt execution
# ---------------------------------------------------------------------------

def attempt_paths(out_dir: Path, instance_id: str, attempt: int) -> Path:
    return out_dir / "attempts" / instance_id / f"attempt-{attempt:03d}"


def latest_terminal_attempt(out_dir: Path, instance_id: str):
    base = out_dir / "attempts" / instance_id
    if not base.is_dir():
        return None, 0
    best, best_n = None, 0
    for d in sorted(base.iterdir()):
        if not d.is_dir() or not d.name.startswith("attempt-"):
            continue
        try:
            n = int(d.name.split("-")[1])
        except (IndexError, ValueError):
            continue
        best_n = max(best_n, n)   # counts interrupted attempts: never reuse a dir
        meta = d / "attempt.json"
        if meta.is_file():
            try:
                rec = json.loads(meta.read_text())
            except (OSError, json.JSONDecodeError) as e:
                # a final record that exists but cannot be read is corruption,
                # never "interrupted": fail closed instead of re-solving
                raise ValueError(f"{instance_id}: unreadable {meta}: {e}")
            # run_attempt only ever writes terminal records for this ID; any
            # other shape (e.g. '{}') is corruption, not an interrupted attempt
            if (not isinstance(rec, dict) or rec.get("terminal") is not True
                    or rec.get("id") != instance_id):
                raise ValueError(f"{instance_id}: malformed record {meta}")
            best = rec
    return best, best_n


def gzip_evidence(src: Path, dst: Path, chunk: int = 1 << 20) -> dict:
    """Stream-gzip src (raw proof), verify roundtrip hash, remove the raw file.

    Streams both directions: proofs may legally reach the multi-GiB
    RLIMIT_FSIZE cap before SIGXFSZ, so no whole-proof read ever happens.
    """
    h = hashlib.sha256()
    total = 0
    with open(src, "rb") as fin, open(dst, "wb") as fout:
        with gzip.GzipFile(fileobj=fout, mode="wb", mtime=0) as gz:
            while True:
                buf = fin.read(chunk)
                if not buf:
                    break
                h.update(buf)
                gz.write(buf)
                total += len(buf)
    raw_sha = h.hexdigest()
    rh = hashlib.sha256()
    with gzip.open(dst, "rb") as gz:
        while True:
            buf = gz.read(chunk)
            if not buf:
                break
            rh.update(buf)
    if rh.hexdigest() != raw_sha:
        raise RuntimeError(f"gzip roundtrip mismatch for {dst}")
    src.unlink()
    return {
        "raw_bytes": total,
        "raw_sha256": raw_sha,
        "gz_bytes": dst.stat().st_size,
        "gz_sha256": sha256_file(dst),
        "roundtrip_verified": True,
        "gz_path": dst.name,
    }


def free_disk_bytes(path: Path) -> int:
    return os.statvfs(path).f_bavail * os.statvfs(path).f_frsize


def run_attempt(row: dict, cnf_bytes: bytes, out_dir: Path, attempt: int,
                kissat: str, drat: str, solve_timeout: int,
                check_timeout: int) -> dict:
    instance_id = row["id"]
    adir = attempt_paths(out_dir, instance_id, attempt)
    adir.mkdir(parents=True, exist_ok=True)
    input_path = adir / "input.cnf"
    atomic_write_bytes(input_path, cnf_bytes)

    solve_argv = [kissat, "--seed=0", f"--time={solve_timeout}",
                  str(input_path), str(adir / "proof.drat")]
    solve = run_child(solve_argv, solve_timeout, adir / "solve.stdout",
                      adir / "solve.stderr")
    stdout_text = (adir / "solve.stdout").read_text("latin-1")
    status, claimed, detail = classify_solver_run(
        solve["exit_code"], stdout_text, solve["deadline_killed"])

    native = parse_kissat_native_stats(stdout_text)
    cnf = parse_dimacs(cnf_bytes.decode("utf-8"))

    rec = {
        "schema": SCHEMA,
        "id": instance_id,
        "attempt": attempt,
        "attempt_dir": os.path.relpath(adir, out_dir),
        "terminal": True,
        "reason": None,
        "claimed": claimed,
        "certified": False,
        "certified_kind": None,
        "gbd_agreement": None,
        "manifest": {k: row[k] for k in
                     ("id", "tier", "family", "category", "result_gbd",
                      "variables", "clauses", "literals", "max_width",
                      "mean_width", "alias", "cnf_sha256")},
        "identity": {"cnf_sha256": row["cnf_sha256"],
                     "compressed_sha256": row["compressed_sha256"],
                     "input_bytes": len(cnf_bytes)},
        "commands": {"solve": solve_argv, "check": None},
        "solve": {
            "exit_code": solve["exit_code"],
            "wall_seconds": solve["wall_seconds"],
            "timeout": solve["deadline_killed"],
            "stdout_sha256": sha256_file(adir / "solve.stdout"),
            "stdout_bytes": (adir / "solve.stdout").stat().st_size,
            "stderr_sha256": sha256_file(adir / "solve.stderr"),
            "stderr_bytes": (adir / "solve.stderr").stat().st_size,
            **native,
        },
        "witness": None,
        "proof": None,
        "check": None,
        "environment": {"solve_timeout_seconds": solve_timeout,
                        "check_timeout_seconds": check_timeout,
                        "output_file_limit_bytes": OUTPUT_FILE_LIMIT,
                        "min_free_disk_bytes": MIN_FREE_DISK},
    }

    reason_map = {
        "timeout": "solve_timeout",
        "unknown": "solver_unknown",
        "protocol_error": "solver_protocol_error",
        "signal": f"solver_signal_{-solve['exit_code'] if solve['exit_code'] is not None and solve['exit_code'] < 0 else 'unknown'}",
    }
    if status in reason_map:
        rec["reason"] = reason_map[status]
        if (adir / "proof.drat").exists():
            rec["proof"] = gzip_evidence(adir / "proof.drat", adir / "proof.drat.gz")
        finalize_gbd_agreement(rec)
        atomic_write_json(adir / "attempt.json", rec)
        return rec

    if status == "sat":
        assignment, werr = parse_witness(stdout_text, cnf.num_vars)
        witness_lines = [l for l in normalize_lines(stdout_text)
                         if l == "v" or l.startswith("v ")]
        wpath = adir / "witness.txt"
        atomic_write_text(wpath, "\n".join(witness_lines) + "\n")
        wrec = {
            "present": True,
            "parse_ok": assignment is not None,
            "error": werr,
            "assignment_size": len(assignment) if assignment else 0,
            "witness_sha256": sha256_file(wpath),
            "independent_check": False,
            "check_seconds": None,
        }
        if assignment is not None:
            t0 = time.monotonic()
            ok = check_witness(cnf, assignment)
            wrec["independent_check"] = bool(ok)
            wrec["check_seconds"] = time.monotonic() - t0
            if ok:
                rec["certified"] = True
                rec["certified_kind"] = "sat_witness"
                rec["reason"] = "ok"
            else:
                rec["reason"] = "witness_check_failed"
        else:
            rec["reason"] = "witness_invalid"
        rec["witness"] = wrec
        if (adir / "proof.drat").exists():
            rec["proof"] = gzip_evidence(adir / "proof.drat", adir / "proof.drat.gz")
        finalize_gbd_agreement(rec)
        atomic_write_json(adir / "attempt.json", rec)
        return rec

    # status == "unsat"
    proof_path = adir / "proof.drat"
    if not proof_path.exists():
        rec["reason"] = "missing_proof"
        finalize_gbd_agreement(rec)
        atomic_write_json(adir / "attempt.json", rec)
        return rec

    check_argv = [drat, str(input_path), str(proof_path), "-t", str(check_timeout)]
    check = run_child(check_argv, check_timeout, adir / "check.stdout",
                      adir / "check.stderr")
    check_text = (adir / "check.stdout").read_text("latin-1")
    classification, certified, cdetail = classify_checker_run(
        check["exit_code"], check_text, check["deadline_killed"])
    rec["commands"]["check"] = check_argv
    rec["check"] = {
        "exit_code": check["exit_code"],
        "wall_seconds": check["wall_seconds"],
        "timeout": check["deadline_killed"],
        "classification": classification,
        "detail": cdetail,
        "stdout_sha256": sha256_file(adir / "check.stdout"),
        "stdout_bytes": (adir / "check.stdout").stat().st_size,
        "stderr_sha256": sha256_file(adir / "check.stderr"),
        "stderr_bytes": (adir / "check.stderr").stat().st_size,
        "reported_verification_seconds": parse_checker_time(check_text),
    }
    rec["proof"] = gzip_evidence(proof_path, adir / "proof.drat.gz")

    if certified and classification == "verified":
        rec["certified"] = True
        rec["certified_kind"] = "unsat_proof"
        rec["reason"] = "ok"
    elif certified and classification == "trivial_original_formula":
        if trivial_path_corroborated(cnf):
            rec["certified"] = True
            rec["certified_kind"] = "unsat_trivial_original"
            rec["reason"] = "ok"
        else:
            rec["reason"] = "trivial_unsat_uncorroborated"
    elif classification == "checker_timeout":
        rec["reason"] = "checker_timeout"
    elif classification == "checker_signal":
        rec["reason"] = "checker_signal"
    elif classification in ("contradictory_status", "checker_protocol_error"):
        if "s NOT VERIFIED" in check_text:
            rec["reason"] = "proof_not_verified"
        elif "s TIMEOUT" in check_text:
            rec["reason"] = "checker_internal_timeout"
        else:
            rec["reason"] = "checker_protocol_error"
    else:
        rec["reason"] = "checker_protocol_error"
    finalize_gbd_agreement(rec)
    atomic_write_json(adir / "attempt.json", rec)
    return rec


def finalize_gbd_agreement(rec: dict) -> dict:
    if rec["certified"]:
        expected_sat = rec["manifest"]["result_gbd"] == "sat"
        actual_sat = rec["certified_kind"] == "sat_witness"
        rec["gbd_agreement"] = "agree" if expected_sat == actual_sat else "conflict"
    return rec


def trivial_path_corroborated(cnf) -> bool:
    """drat-trim's exit-1 'c trivial UNSAT' path means its parser saw an empty
    original clause.  In binary-proof mode it ALSO fabricates empty clauses
    from any 'c' comment line inside the CNF body (reproduced on a SAT
    formula), so accept it only if the strict original really has one."""
    return any(len(c) == 0 for c in cnf.clauses)


def record_invariant_errors(rec: dict, input_path=None) -> list[str]:
    """A certified record must follow from the evidence it carries; agreement
    is recomputed from the manifest label rather than trusted."""
    iid = rec.get("id")
    errs = []
    kind = rec.get("certified_kind")
    if not rec.get("terminal"):
        errs.append(f"{iid}: record is not terminal")
    if not rec.get("certified"):
        if kind is not None or rec.get("gbd_agreement") is not None:
            errs.append(f"{iid}: uncertified record carries a certificate "
                        "kind or label agreement")
        return errs
    solve = rec.get("solve") or {}
    if solve.get("timeout"):
        errs.append(f"{iid}: certified record has a solver timeout")
    if kind == "sat_witness":
        w = rec.get("witness") or {}
        if not (rec.get("claimed") == "sat" and solve.get("exit_code") == 10
                and w.get("parse_ok") and w.get("independent_check") is True):
            errs.append(f"{iid}: sat_witness lacks a checked total witness")
    elif kind in ("unsat_proof", "unsat_trivial_original"):
        c = rec.get("check") or {}
        want_cls, want_exit = (("verified", 0) if kind == "unsat_proof"
                               else ("trivial_original_formula", 1))
        if not (rec.get("claimed") == "unsat" and solve.get("exit_code") == 20
                and rec.get("proof") and c.get("classification") == want_cls
                and c.get("exit_code") == want_exit and not c.get("timeout")):
            errs.append(f"{iid}: {kind} lacks a matching solver claim/proof/"
                        "checker result")
        if kind == "unsat_trivial_original":
            ok = False
            if input_path is not None:
                try:
                    ok = trivial_path_corroborated(
                        parse_dimacs(Path(input_path).read_text()))
                except (OSError, ValueError):     # incl. UnicodeDecodeError, CNFError
                    ok = False
            if not ok:
                errs.append(f"{iid}: trivial-UNSAT certificate not "
                            "corroborated by an empty original clause")
    else:
        errs.append(f"{iid}: unknown certified_kind {kind!r}")
    expected_sat = (rec.get("manifest") or {}).get("result_gbd") == "sat"
    expected = "agree" if expected_sat == (kind == "sat_witness") else "conflict"
    if rec.get("gbd_agreement") != expected:
        errs.append(f"{iid}: gbd_agreement {rec.get('gbd_agreement')!r} != "
                    f"recomputed {expected!r}")
    return errs


def rederive_certification_errors(adir: Path, rec: dict) -> list[str]:
    """Re-derive a certified record's verdict from its retained evidence files
    (call only after their hashes verified): reclassify the solver/checker
    logs from the recorded exit codes and re-check the witness against the
    retained original CNF, instead of trusting recorded metadata."""
    iid = rec.get("id")
    if not rec.get("certified"):
        return []
    errs = []
    try:
        cnf = parse_dimacs((adir / "input.cnf").read_text())
        solve = rec["solve"]
        status, claimed, _ = classify_solver_run(
            solve["exit_code"], (adir / "solve.stdout").read_text("latin-1"),
            solve["timeout"])
        if claimed != rec.get("claimed") or status not in ("sat", "unsat"):
            errs.append(f"{iid}: solver log re-classifies as {status!r}, "
                        f"record claims {rec.get('claimed')!r}")
        kind = rec.get("certified_kind")
        if kind == "sat_witness":
            assignment, werr = parse_witness(
                (adir / "solve.stdout").read_text("latin-1"), cnf.num_vars)
            if assignment is None or not check_witness(cnf, assignment):
                errs.append(f"{iid}: retained witness does not satisfy the "
                            f"original formula ({werr or 'check failed'})")
        elif kind in ("unsat_proof", "unsat_trivial_original"):
            check = rec["check"]
            cls, certified, _ = classify_checker_run(
                check["exit_code"], (adir / "check.stdout").read_text("latin-1"),
                check["timeout"])
            want = ("verified" if kind == "unsat_proof"
                    else "trivial_original_formula")
            if not certified or cls != want:
                errs.append(f"{iid}: checker log re-classifies as {cls!r}, "
                            f"record certifies {want!r}")
    except (OSError, KeyError, TypeError, ValueError) as e:   # ValueError: decode/CNFError
        errs.append(f"{iid}: certification cannot be re-derived: {e!r}")
    return errs


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

BINS = [("<0.1", 0.0, 0.1), ("0.1-1", 0.1, 1.0), ("1-10", 1.0, 10.0),
        ("10-100", 10.0, 100.0), ("100-1000", 100.0, 1000.0)]


def quantiles(values):
    if not values:
        return {}
    vs = sorted(values)
    def q(p):
        idx = p * (len(vs) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(vs) - 1)
        frac = idx - lo
        return round(vs[lo] + (vs[hi] - vs[lo]) * frac, 4)
    return {"count": len(vs), "min": round(vs[0], 4), "p50": q(0.5),
            "p90": q(0.9), "p99": q(0.99), "max": round(vs[-1], 4)}


def derive_summary(records: list[dict], identity: dict, provenance: dict) -> dict:
    by_key = lambda key: group_records(records, key)
    certified = [r for r in records if r["certified"]]
    conflicts = [r for r in records if r["gbd_agreement"] == "conflict"]
    unresolved = [r for r in records if not r["certified"]]
    solve_times = [r["solve"]["wall_seconds"] for r in certified]
    check_times = [r["check"]["wall_seconds"] for r in certified
                   if r.get("check")]
    witness_times = [r["witness"]["check_seconds"] for r in certified
                     if r.get("witness")]
    bins = {label: 0 for label, _, _ in BINS}
    for t in solve_times:
        for label, lo, hi in BINS:
            if lo <= t < hi:
                bins[label] += 1
                break
    return {
        "identity": identity,
        "provenance": provenance,
        "counts": {
            "records": len(records),
            "attempted": len(records),
            "claimed_sat": sum(1 for r in records if r["claimed"] == "sat"),
            "claimed_unsat": sum(1 for r in records if r["claimed"] == "unsat"),
            "claimed_unknown_or_timeout": sum(
                1 for r in records if r["claimed"] is None),
            "witness_checked_sat": sum(
                1 for r in records if r["certified_kind"] == "sat_witness"),
            "proof_checked_unsat": sum(
                1 for r in records if r["certified_kind"] == "unsat_proof"),
            "trivial_original_unsat": sum(
                1 for r in records
                if r["certified_kind"] == "unsat_trivial_original"),
            "certified_total": len(certified),
            "label_conflicts": len(conflicts),
            "unresolved": len(unresolved),
        },
        "breakdowns": {
            "by_tier": by_key("tier"),
            "by_family": by_key("family"),
            "by_category": by_key("category"),
            "by_expected_result": by_key("result_gbd"),
        },
        "times": {
            "certified_solve_wall_seconds": quantiles(solve_times),
            "certified_checker_wall_seconds": quantiles(check_times),
            "certified_witness_check_seconds": quantiles(witness_times),
            "certified_solve_bins": bins,
            "timing_semantics": ("proof-enabled Kissat wall time including input "
                                 "parsing and proof I/O; not proof-free CPU speed "
                                 "and not projected FPGA runtime"),
        },
        "proofs": {
            "raw_total_bytes": sum(r["proof"]["raw_bytes"] for r in records
                                   if r.get("proof")),
            "gz_total_bytes": sum(r["proof"]["gz_bytes"] for r in records
                                  if r.get("proof")),
            "note": ("quantiles cover proof-checked UNSAT certificates only; "
                     "SAT-run proof traces are evidence, not certificates"),
            "unsat_proof_raw_bytes_quantiles": quantiles(
                [r["proof"]["raw_bytes"] for r in records
                 if r.get("proof") and r["certified_kind"] == "unsat_proof"]),
            "unsat_proof_gz_bytes_quantiles": quantiles(
                [r["proof"]["gz_bytes"] for r in records
                 if r.get("proof") and r["certified_kind"] == "unsat_proof"]),
        },
    }


def group_records(records: list[dict], key: str) -> dict:
    def med(values):
        return round(sorted(values)[len(values) // 2], 4) if values else None
    out: dict[str, dict] = {}
    for r in records:
        k = r["manifest"].get(key) or "?"
        slot = out.setdefault(k, {"total": 0, "certified": 0, "unresolved": 0,
                                  "conflict": 0,
                                  "median_certified_solve_seconds": None,
                                  "median_certified_checker_seconds": None,
                                  "median_certified_witness_seconds": None})
        slot["total"] += 1
        if r["certified"]:
            slot["certified"] += 1
        else:
            slot["unresolved"] += 1
        if r["gbd_agreement"] == "conflict":
            slot["conflict"] += 1
    for k, slot in out.items():
        group = [r for r in records
                 if r["manifest"].get(key) == k and r["certified"]]
        slot["median_certified_solve_seconds"] = med(
            [r["solve"]["wall_seconds"] for r in group])
        slot["median_certified_checker_seconds"] = med(
            [r["check"]["wall_seconds"] for r in group if r.get("check")])
        slot["median_certified_witness_seconds"] = med(
            [r["witness"]["check_seconds"] for r in group
             if r.get("witness") and r["witness"].get("check_seconds") is not None])
    return out


def write_results_csv(path: Path, records: list[dict]) -> None:
    fields = ["id", "tier", "family", "category", "result_gbd", "variables",
              "clauses", "literals", "claimed", "certified", "certified_kind",
              "reason", "gbd_agreement", "solve_wall_seconds",
              "kissat_process_time_seconds", "kissat_max_rss_bytes",
              "witness_check_seconds", "checker_wall_seconds",
              "reported_verification_seconds", "proof_raw_bytes",
              "proof_gz_bytes", "attempt"]
    lines = [",".join(fields)]
    for r in records:
        def g(sub, key):
            v = (r.get(sub) or {}).get(key) if sub else r.get(key)
            return "" if v is None else str(v)
        vals = [
            r["id"], r["manifest"]["tier"],
            r["manifest"]["family"], r["manifest"]["category"],
            r["manifest"]["result_gbd"], r["manifest"]["variables"],
            r["manifest"]["clauses"], r["manifest"]["literals"],
            r["claimed"] or "", str(r["certified"]).lower(),
            r["certified_kind"] or "", r["reason"] or "",
            r["gbd_agreement"] or "",
            g("solve", "wall_seconds"), g("solve", "kissat_process_time_seconds"),
            g("solve", "kissat_max_rss_bytes"), g("witness", "check_seconds"),
            g("check", "wall_seconds"), g("check", "reported_verification_seconds"),
            g("proof", "raw_bytes"), g("proof", "gz_bytes"), str(r["attempt"]),
        ]
        lines.append(",".join('"' + v.replace('"', '""') + '"' for v in vals))
    atomic_write_text(path, "\n".join(lines) + "\n")


def write_report_md(path: Path, summary: dict, records: list[dict]) -> None:
    c = summary["counts"]
    certified_all = (c["records"] == c["certified_total"] == 210
                     and c["label_conflicts"] == 0)
    lines = []
    lines.append("# Checked CPU calibration campaign (cpu-v0)")
    lines.append("")
    lines.append("## Certification statement")
    lines.append("")
    if c["records"] == 210 and certified_all:
        lines.append("**All 210 certified**: every attempted instance holds a "
                     "valid independent certificate agreeing with the manifest.")
    else:
        lines.append(f"**Not all 210 certified**: {c['certified_total']}/"
                     f"{c['records']} certified, {c['label_conflicts']} label "
                     f"conflicts, {c['unresolved']} unresolved.")
    lines.append("")
    lines.append("## Headline counts")
    lines.append("")
    for k, v in c.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Breakdowns (certified / unresolved / conflict)")
    lines.append("")
    for name, key in (("tier", "by_tier"), ("family", "by_family"),
                      ("category", "by_category"),
                      ("expected result", "by_expected_result")):
        lines.append(f"### by {name}")
        lines.append("")
        lines.append("| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for k, slot in sorted(summary["breakdowns"][key].items()):
            def cell(name):
                v = slot.get(name)
                return v if v is not None else ""
            lines.append(f"| {k} | {slot['total']} | {slot['certified']} | "
                         f"{slot['unresolved']} | {slot['conflict']} | "
                         f"{cell('median_certified_solve_seconds')} | "
                         f"{cell('median_certified_checker_seconds')} | "
                         f"{cell('median_certified_witness_seconds')} |")
        lines.append("")
    t = summary["times"]
    lines.append("## Certified timing")
    lines.append("")
    lines.append(f"- solve wall quantiles (s): {t['certified_solve_wall_seconds']}")
    lines.append(f"- checker wall quantiles (s): {t['certified_checker_wall_seconds']}")
    lines.append(f"- witness check quantiles (s): {t['certified_witness_check_seconds']}")
    lines.append(f"- solve bins: {t['certified_solve_bins']} (unresolved: "
                 f"{c['unresolved']})")
    lines.append("")
    lines.append(f"Timing semantics: {t['timing_semantics']}. A single seed-0 "
                 "run is a calibration survey, not a precise ranking. "
                 "Sub-0.1-second entries are triviality candidates only.")
    lines.append("")
    lines.append("## Proof sizes")
    lines.append("")
    p = summary["proofs"]
    lines.append(f"- raw total: {p['raw_total_bytes']} bytes; gz total: "
                 f"{p['gz_total_bytes']} bytes")
    lines.append(f"- UNSAT proof raw-bytes quantiles (certificates only): "
                 f"{p['unsat_proof_raw_bytes_quantiles']}")
    lines.append(f"- UNSAT proof gz-bytes quantiles: "
                 f"{p['unsat_proof_gz_bytes_quantiles']}")
    lines.append("")
    unresolved = [r for r in records if not r["certified"] or
                  r["gbd_agreement"] == "conflict"]
    if unresolved:
        lines.append("## Unresolved / conflicting instances")
        lines.append("")
        lines.append("| id | claimed | certified | reason | gbd | agreement |")
        lines.append("|---|---|---|---|---|---|")
        for r in unresolved:
            lines.append(f"| {r['id']} | {r['claimed'] or ''} | "
                         f"{str(r['certified']).lower()} | {r['reason']} | "
                         f"{r['manifest']['result_gbd']} | "
                         f"{r['gbd_agreement'] or ''} |")
        lines.append("")
    atomic_write_text(path, "\n".join(lines) + "\n")


def generate_reports(out_dir: Path, records: list[dict], identity: dict,
                     provenance: dict) -> None:
    summary = derive_summary(records, identity, provenance)
    atomic_write_json(out_dir / "summary.json", summary)
    write_results_csv(out_dir / "results.csv", records)
    write_report_md(out_dir / "report.md", summary, records)


# ---------------------------------------------------------------------------
# Evidence re-validation (--report-only and resume)
# ---------------------------------------------------------------------------

def _validate_record_evidence(out_dir: Path, rec: dict, row: dict | None = None,
                              env_expected: tuple | None = None) -> list[str]:
    """Re-verify one record's evidence files (and manifest-row binding)."""
    errs = []
    # shape-check the attempt path BEFORE any file under it is read:
    # pathlib replaces the base when joining an absolute path, and a tampered
    # relative path could redirect evidence reads outside the campaign
    attempt_dir = rec.get("attempt_dir") or ""
    if (not attempt_dir.startswith("attempts/")
            or ".." in attempt_dir.split("/")
            or os.path.isabs(attempt_dir)):
        return [f"{rec.get('id')}: unsafe attempt_dir {attempt_dir!r}"]
    adir = out_dir / attempt_dir
    checks = [
        (adir / "input.cnf", rec["identity"]["cnf_sha256"]),
        (adir / "solve.stdout", rec["solve"]["stdout_sha256"]),
        (adir / "solve.stderr", rec["solve"]["stderr_sha256"]),
    ]
    if rec.get("witness"):
        checks.append((adir / "witness.txt", rec["witness"]["witness_sha256"]))
    if rec.get("proof"):
        gz_path = adir / rec["proof"]["gz_path"]
        checks.append((gz_path, rec["proof"]["gz_sha256"]))
        if rec["proof"].get("gz_path") != "proof.drat.gz":
            errs.append(f"{rec['id']}: unexpected proof gz_path "
                        f"{rec['proof'].get('gz_path')!r}")
    if rec.get("check"):
        checks.append((adir / "check.stdout", rec["check"]["stdout_sha256"]))
        checks.append((adir / "check.stderr", rec["check"]["stderr_sha256"]))
    for path, expected in checks:
        if not path.is_file():
            errs.append(f"{rec['id']}: missing evidence {path.name}")
        elif sha256_file(path) != expected:
            errs.append(f"{rec['id']}: hash mismatch {path.name}")
    if rec.get("proof") and rec["proof"].get("gz_path") == "proof.drat.gz" \
            and not any("proof.drat.gz" in e for e in errs):
        # compressed hash already matched; now stream-decompress and require
        # both size and hash to reproduce the recorded raw proof
        try:
            rh = hashlib.sha256()
            total = 0
            with gzip.open(adir / rec["proof"]["gz_path"], "rb") as gz:
                while True:
                    buf = gz.read(1 << 20)
                    if not buf:
                        break
                    rh.update(buf)
                    total += len(buf)
            if rh.hexdigest() != rec["proof"]["raw_sha256"]:
                errs.append(f"{rec['id']}: proof gz roundtrip hash mismatch")
            if total != rec["proof"]["raw_bytes"]:
                errs.append(f"{rec['id']}: proof gz roundtrip size mismatch")
        except (OSError, gzip.BadGzipFile, EOFError) as e:
            errs.append(f"{rec['id']}: proof gz unreadable: {e}")
    if row is not None:
        # bind the reused record to its current manifest row
        if rec.get("id") != row["id"]:
            errs.append(f"record id {rec.get('id')!r} != manifest id {row['id']!r}")
        for key in ("tier", "family", "category", "result_gbd", "variables",
                    "clauses", "literals", "max_width", "mean_width", "alias",
                    "cnf_sha256"):
            if str(rec.get("manifest", {}).get(key)) != str(row[key]):
                errs.append(f"{row['id']}: manifest field {key} mismatch "
                            f"(record={rec.get('manifest', {}).get(key)!r} "
                            f"manifest={row[key]!r})")
        if rec.get("identity", {}).get("cnf_sha256") != row["cnf_sha256"]:
            errs.append(f"{row['id']}: identity cnf_sha256 != manifest cnf_sha256")
        if rec.get("identity", {}).get("compressed_sha256") != row["compressed_sha256"]:
            errs.append(f"{row['id']}: compressed_sha256 binding mismatch")
        env = rec.get("environment", {})
        if env_expected is not None and (
                env.get("solve_timeout_seconds") != env_expected[0]
                or env.get("check_timeout_seconds") != env_expected[1]):
            errs.append(f"{row['id']}: recorded timeouts "
                        f"({env.get('solve_timeout_seconds')}/"
                        f"{env.get('check_timeout_seconds')}) != campaign "
                        f"settings {env_expected}")
        expected_dir = f"attempts/{row['id']}/attempt-{rec.get('attempt', 0):03d}"
        if rec.get("attempt_dir") != expected_dir:
            errs.append(f"{row['id']}: attempt_dir {rec.get('attempt_dir')!r} "
                        f"!= expected {expected_dir!r}")
    errs.extend(record_invariant_errors(rec, adir / "input.cnf"))
    if not errs:      # evidence hashes and metadata consistent: re-derive
        errs.extend(rederive_certification_errors(adir, rec))
    return errs


def validate_record_evidence(out_dir: Path, rec: dict, row: dict | None = None,
                             env_expected: tuple | None = None) -> list[str]:
    """Fail closed: a record missing fields or of the wrong type is an
    evidence error, never an exception that aborts validation of the rest."""
    try:
        return _validate_record_evidence(out_dir, rec, row, env_expected)
    except (KeyError, TypeError, AttributeError, ValueError, OSError) as e:
        iid = rec.get("id") if isinstance(rec, dict) else None
        return [f"{iid}: malformed record: {type(e).__name__}: {e}"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST)
    ap.add_argument("--kissat", default=DEFAULT_KISSAT)
    ap.add_argument("--drat-trim", default=DEFAULT_DRAT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--solve-timeout", type=int, default=DEFAULT_SOLVE_TIMEOUT)
    ap.add_argument("--check-timeout", type=int, default=DEFAULT_CHECK_TIMEOUT)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    manifest_path = os.path.abspath(args.manifest)
    kissat = os.path.abspath(args.kissat)
    drat = os.path.abspath(args.drat_trim)

    for tool in (kissat, drat):
        if not (os.path.isfile(tool) and os.access(tool, os.X_OK)):
            print(f"error: tool missing or not executable: {tool}", file=sys.stderr)
            return 1
    if args.solve_timeout <= 0 or args.check_timeout <= 0:
        print("error: timeouts must be positive", file=sys.stderr)
        return 1

    current_identity = campaign_identity(manifest_path, kissat, drat,
                                         args.solve_timeout, args.check_timeout)
    run_json = out_dir / "run.json"
    resuming = run_json.is_file()

    if args.report_only and not resuming:
        print(f"error: --report-only requires an existing campaign at "
              f"{out_dir}", file=sys.stderr)
        return 1
    if not resuming and out_dir.exists() and any(out_dir.iterdir()):
        print(f"error: {out_dir} exists and is not empty; existing output "
              "requires an identical-campaign --resume (fail closed)",
              file=sys.stderr)
        return 1
    if resuming and not (args.resume or args.report_only):
        print("error: existing campaign at {}; pass --resume to continue "
              "or --report-only to re-verify".format(out_dir), file=sys.stderr)
        return 1
    if args.resume and not resuming:
        print("error: --resume specified but no campaign exists at "
              f"{out_dir}", file=sys.stderr)
        return 1
    if resuming:
        recorded = json.loads(run_json.read_text())["identity"]
        mism = identity_mismatches(recorded, current_identity)
        if mism:
            print("error: campaign identity mismatch (fail closed); use a new "
                  "output directory for changed settings:", file=sys.stderr)
            for m in mism:
                print(f"  {m}", file=sys.stderr)
            return 1

    try:
        rows = load_manifest(manifest_path)
    except (OSError, ValueError) as e:
        print(f"error: manifest load failed: {e}", file=sys.stderr)
        return 1

    # Preflight every input before any solving.
    cnf_cache: dict[str, bytes] = {}
    preflight_errors = []
    for row in rows:
        data, err = preflight_instance(row, os.path.dirname(manifest_path))
        if err:
            preflight_errors.append(f"{row['id']}: {err}")
        else:
            cnf_cache[row["id"]] = data
    if preflight_errors:
        print(f"error: preflight rejected {len(preflight_errors)} input(s):",
              file=sys.stderr)
        for e in preflight_errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    if not resuming:
        out_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(out_dir / "manifest.snapshot.csv",
                           Path(manifest_path).read_bytes())
        sv = os.statvfs(out_dir)
        atomic_write_json(out_dir / "run.json", {
            "schema": RUN_SCHEMA,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "identity": current_identity,
            "provenance": {
                "host": host_provenance(),
                "tools": tool_provenance(kissat, drat),
                "tool_commits": {
                    "kissat": "8af8e56f174b778aef3aa45af9f739b2a5f492c2",
                    "drat_trim": "2e3b2dc0ecf938addbd779d42877b6ed69d9a985",
                },
                "build_commands": {
                    "kissat": "./configure && make -j4",
                    "drat_trim": "make drat-trim (gcc drat-trim.c -std=c99 -O2 -o drat-trim)",
                },
                "disk": {
                    "free_bytes_at_start": sv.f_bavail * sv.f_frsize,
                    "total_bytes": sv.f_blocks * sv.f_frsize,
                    "path": str(out_dir),
                },
                "safety_limits": {
                    "output_file_limit_bytes": OUTPUT_FILE_LIMIT,
                    "min_free_disk_bytes": MIN_FREE_DISK,
                    "kill_grace_seconds": KILL_GRACE_SECONDS,
                },
            },
            "manifest_rows": len(rows),
        })
    recorded_run = json.loads(run_json.read_text())
    provenance = recorded_run["provenance"]
    snapshot = out_dir / "manifest.snapshot.csv"
    if not snapshot.is_file() or sha256_file(snapshot) != current_identity["manifest_sha256"]:
        print("error: manifest.snapshot.csv missing or not byte-identical to "
              "the current manifest (fail closed)", file=sys.stderr)
        return 1

    if not recorded_run["provenance"]["tools"].get("kissat_help_mentions_seed") \
            or not recorded_run["provenance"]["tools"].get("kissat_help_mentions_time"):
        print("error: pinned kissat --help lacks --seed/--time; toolchain "
              "blocker (no version substitution permitted)", file=sys.stderr)
        return 1

    records: list[dict] = []
    infra_block = None
    if args.report_only:
        for row in rows:
            try:
                rec, _ = latest_terminal_attempt(out_dir, row["id"])
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            if rec is None:
                print(f"error: no terminal record for {row['id']}", file=sys.stderr)
                return 1
            errs = validate_record_evidence(
                out_dir, rec, row,
                env_expected=(args.solve_timeout, args.check_timeout))
            if errs:
                for e in errs:
                    print(f"error: {e}", file=sys.stderr)
                return 1
            records.append(rec)
    else:
        state_path = out_dir / "state.json"
        state = {"id_status": {}, "infra_block": None}
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text())
            except (OSError, json.JSONDecodeError):
                pass
        for row in rows:
            iid = row["id"]
            if not re.fullmatch(r"[A-Za-z0-9._-]+", iid):
                print(f"error: unsafe instance id {iid!r}", file=sys.stderr)
                return 1
            try:
                rec, last_n = latest_terminal_attempt(out_dir, iid)
            except ValueError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            if rec is not None:
                errs = validate_record_evidence(
                    out_dir, rec, row,
                    env_expected=(args.solve_timeout, args.check_timeout))
                if errs:
                    print(f"error: retained evidence invalid; fail closed:",
                          file=sys.stderr)
                    for e in errs:
                        print(f"  {e}", file=sys.stderr)
                    return 1
                records.append(rec)
                print(f"[resume] {iid}: reusing terminal record "
                      f"(reason={rec['reason']})", flush=True)
                continue
            if free_disk_bytes(out_dir) < MIN_FREE_DISK:
                infra_block = {"reason": "disk_below_20gib",
                               "at_id": iid,
                               "free_bytes": free_disk_bytes(out_dir)}
                state["infra_block"] = infra_block
                atomic_write_json(state_path, state)
                print(f"error: infrastructure block before {iid}: "
                      f"{infra_block}", file=sys.stderr)
                break
            attempt = last_n + 1
            print(f"[run] {iid}: attempt {attempt} "
                  f"({len(records) + 1}/{len(rows)})", flush=True)
            rec = run_attempt(row, cnf_cache[iid], out_dir, attempt, kissat,
                              drat, args.solve_timeout, args.check_timeout)
            state["id_status"][iid] = {
                "status": "terminal" if rec["terminal"] else "nonterminal",
                "attempt": attempt,
                "attempt_dir": rec["attempt_dir"],
            }
            atomic_write_json(state_path, state)
            records.append(rec)
            cert = ("CERTIFIED " + rec["certified_kind"]) if rec["certified"] \
                else f"uncertified ({rec['reason']})"
            print(f"[done] {iid}: claimed={rec['claimed']} {cert} "
                  f"gbd={rec['gbd_agreement']}", flush=True)

    if len(records) != len(rows):
        print(f"error: campaign incomplete: {len(records)}/{len(rows)} terminal "
              f"records (infrastructure block: {infra_block or 'none'})",
              file=sys.stderr)
        generate_reports(out_dir, records, current_identity, provenance)
        return 1

    generate_reports(out_dir, records, current_identity, provenance)
    n_cert = sum(1 for r in records if r["certified"])
    n_conf = sum(1 for r in records if r["gbd_agreement"] == "conflict")
    print(f"campaign complete: {len(records)} records, {n_cert} certified, "
          f"{n_conf} conflicts", flush=True)
    if n_cert == len(records) and n_conf == 0:
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
