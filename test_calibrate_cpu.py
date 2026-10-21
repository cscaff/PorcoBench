"""Behavioral boundary tests for calibrate_cpu.py (stdlib unittest).

Exercises the real acceptance logic: solver status classification, strict
witness parsing, checker classification (including the narrow pinned-commit
trivial-UNSAT exit-1 rule), deadline kills, attempt numbering on resume, and
identity fail-closed behavior.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import calibrate_cpu as cc  # noqa: E402
from benchmark_cnf import parse_dimacs, check_witness  # noqa: E402


def solver_stdout_sat(num_vars=3, lits="1 2 3"):
    return f"c banner\ns SATISFIABLE\nv {lits} 0\n"



class LoadManifest(unittest.TestCase):
    ROW = ("X1,h1,main,m,f,S,S,sat,1,1,1,1,1.000,a,cnf/a.xz,10,%s,%s,u,l,t\n"
           "X2,h2,main,m,f,S,S,unsat,2,2,2,2,1.000,b,cnf/b.xz,10,%s,%s,u,l,t\n")

    def write(self, td, **edit):
        import hashlib
        c1, d1 = "c" * 64, "d" * 64
        c2, d2 = edit.get("c2", "e" * 64), edit.get("d2", "f" * 64)
        path = Path(td) / "m.csv"
        path.write_text(
            "id,gbd_hash,category,source_tracks,family,tier,gbd_tier,"
            "result_gbd,variables,clauses,literals,max_width,mean_width,alias,"
            "file,compressed_bytes,compressed_sha256,cnf_sha256,url,"
            "license_status,all_tracks\n" +
            self.ROW % (c1, d1, c2, d2))
        return path

    def test_unique_rows_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            rows = cc.load_manifest(str(self.write(td)))
            self.assertEqual([r["id"] for r in rows], ["X1", "X2"])

    def test_duplicate_hashes_rejected(self):
        for col, kw in (("cnf_sha256", {"c2": "c" * 64}),
                        ("compressed_sha256", {"d2": "d" * 64}),
                        ("gbd_hash", None)):
            with tempfile.TemporaryDirectory() as td:
                path = self.write(td, **(kw or {}))
                if col == "gbd_hash":
                    text = path.read_text().replace("h2", "h1")
                    path.write_text(text)
                with self.assertRaises(ValueError, msg=col):
                    cc.load_manifest(str(path))


class ClassifySolverRun(unittest.TestCase):
    def test_sat_accepted(self):
        status, claimed, _ = cc.classify_solver_run(10, solver_stdout_sat(), False)
        self.assertEqual((status, claimed), ("sat", "sat"))

    def test_unsat_accepted(self):
        status, claimed, _ = cc.classify_solver_run(20, "s UNSATISFIABLE\n", False)
        self.assertEqual((status, claimed), ("unsat", "unsat"))

    def test_unknown_accepted_as_unresolved(self):
        status, claimed, _ = cc.classify_solver_run(0, "s UNKNOWN\n", False)
        self.assertEqual((status, claimed), ("unknown", None))

    def test_duplicate_status_lines_rejected(self):
        status, _, _ = cc.classify_solver_run(
            10, "s SATISFIABLE\ns SATISFIABLE\nv 1 0\n", False)
        self.assertEqual(status, "protocol_error")

    def test_mismatching_exit_and_status_rejected(self):
        status, _, _ = cc.classify_solver_run(20, "s SATISFIABLE\nv 1 0\n", False)
        self.assertEqual(status, "protocol_error")
        status, _, _ = cc.classify_solver_run(10, "s UNSATISFIABLE\n", False)
        self.assertEqual(status, "protocol_error")

    def test_missing_status_rejected(self):
        status, _, _ = cc.classify_solver_run(10, "c nothing\n", False)
        self.assertEqual(status, "protocol_error")

    def test_timeout_overrides_late_success(self):
        stdout = "s SATISFIABLE\nv 1 2 3 0\n"   # late success text
        status, claimed, _ = cc.classify_solver_run(-9, stdout, True)
        self.assertEqual((status, claimed), ("timeout", None))

    def test_signal_reported(self):
        status, _, _ = cc.classify_solver_run(-11, "", False)
        self.assertEqual(status, "signal")


class ParseWitness(unittest.TestCase):
    def test_correct_assignment(self):
        text = "s SATISFIABLE\nv 1 -2\nv 3 0\n"
        assignment, err = cc.parse_witness(text, 3)
        self.assertIsNone(err)
        self.assertEqual(assignment, {1: True, 2: False, 3: True})
        cnf = parse_dimacs("p cnf 3 2\n1 -2 0\n3 0\n")
        self.assertTrue(check_witness(cnf, assignment))

    def test_missing_zero_rejected(self):
        _, err = cc.parse_witness("v 1 2 3\n", 3)
        self.assertIn("terminating 0", err)

    def test_extra_zero_rejected(self):
        _, err = cc.parse_witness("v 1 0 2 3 0\n", 3)
        self.assertIn("extra 0", err)

    def test_literals_after_zero_rejected(self):
        # tokens after the first 0 land in body -> "extra 0" guard
        _, err = cc.parse_witness("v 1 2 3 0 1\n", 3)
        self.assertIsNotNone(err)

    def test_truncated_model_rejected(self):
        _, err = cc.parse_witness("v 1 2 0\n", 3)
        self.assertIn("unassigned", err)

    def test_duplicate_variable_rejected(self):
        _, err = cc.parse_witness("v 1 1 2 3 0\n", 3)
        self.assertIn("more than once", err)

    def test_conflicting_assignment_rejected(self):
        _, err = cc.parse_witness("v 1 -1 2 3 0\n", 3)
        self.assertIn("more than once", err)

    def test_out_of_range_rejected(self):
        _, err = cc.parse_witness("v 1 2 3 4 0\n", 3)
        self.assertIn("out of range", err)

    def test_wrong_model_fails_independent_check(self):
        # complete, well-formed model that does not satisfy the formula
        assignment, err = cc.parse_witness("v 1 2 3 0\n", 3)
        self.assertIsNone(err)
        cnf = parse_dimacs("p cnf 3 2\n1 -2 0\n-3 0\n")
        self.assertFalse(check_witness(cnf, assignment))


class ClassifyCheckerRun(unittest.TestCase):
    VERIFIED = "\rc parsing input formula with 2 variables and 4 clauses\ns VERIFIED\nc verification time: 0.001 seconds\n"

    def test_verified_exit0(self):
        cls, certified, _ = cc.classify_checker_run(0, self.VERIFIED, False)
        self.assertEqual(cls, "verified")
        self.assertTrue(certified)

    def test_trivial_unsat_exit1_narrowly_accepted(self):
        text = "\rc parsing input formula\n\rc trivial UNSAT\ns VERIFIED\n"
        cls, certified, _ = cc.classify_checker_run(1, text, False)
        self.assertEqual(cls, "trivial_original_formula")
        self.assertTrue(certified)

    def test_exit1_without_trivial_marker_rejected(self):
        # exit 1 + s VERIFIED but no 'c trivial UNSAT' -> not the pinned path
        cls, certified, _ = cc.classify_checker_run(1, "\rs VERIFIED\n", False)
        self.assertFalse(certified)

    def test_exit0_with_trivial_marker_rejected(self):
        cls, certified, _ = cc.classify_checker_run(
            0, "\rc trivial UNSAT\ns VERIFIED\n", False)
        self.assertFalse(certified)

    def test_error_prefixed_line_rejected(self):
        # real drat-trim prints 'c error opening "...".' with a suffix; a
        # fabricated exit-0 's VERIFIED' alongside it must not certify
        cls, certified, _ = cc.classify_checker_run(
            0, "\rc error opening \"proof.drat\".\ns VERIFIED\n", False)
        self.assertFalse(certified)
        self.assertEqual(cls, "contradictory_status")

    def test_safe_attempt_dir_shape_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            for bad in ("/etc", "attempts/../../x", "elsewhere/attempts/X"):
                rec = {"id": "X", "attempt_dir": bad,
                       "identity": {"cnf_sha256": "0" * 64},
                       "solve": {"stdout_sha256": "0" * 64,
                                 "stderr_sha256": "0" * 64}}
                errs = cc.validate_record_evidence(out, rec)
                self.assertTrue(any("unsafe attempt_dir" in e for e in errs),
                                bad)

    def test_not_verified_rejected(self):
        cls, certified, _ = cc.classify_checker_run(
            1, "\rs NOT VERIFIED\n", False)
        self.assertFalse(certified)

    def test_derivation_rejected(self):
        cls, certified, _ = cc.classify_checker_run(1, "\rs DERIVATION\n", False)
        self.assertFalse(certified)

    def test_internal_timeout_exit0_rejected(self):
        # upstream prints 's TIMEOUT' and exits 0 — must not certify
        cls, certified, _ = cc.classify_checker_run(0, "\rs TIMEOUT\n", False)
        self.assertFalse(certified)

    def test_external_deadline_rejected(self):
        cls, certified, _ = cc.classify_checker_run(0, self.VERIFIED, True)
        self.assertEqual(cls, "checker_timeout")
        self.assertFalse(certified)

    def test_memory_error_rejected(self):
        cls, certified, _ = cc.classify_checker_run(
            1, "\rs MEMORY ALLOCATION ERROR\n", False)
        self.assertFalse(certified)

    def test_crash_rejected(self):
        cls, certified, _ = cc.classify_checker_run(-11, "", False)
        self.assertEqual(cls, "checker_signal")
        self.assertFalse(certified)


class RunChildDeadline(unittest.TestCase):
    def test_sleeping_child_killed_and_reaped(self):
        with tempfile.TemporaryDirectory() as td:
            out, err = Path(td) / "o", Path(td) / "e"
            t0 = time.monotonic()
            res = cc.run_child(["/bin/sleep", "300"], 1, out, err)
            wall = time.monotonic() - t0
            self.assertTrue(res["deadline_killed"])
            self.assertLess(wall, 10)
            self.assertLess(res["exit_code"], 0)   # killed by signal, reaped

    def test_fast_child_completes(self):
        with tempfile.TemporaryDirectory() as td:
            out, err = Path(td) / "o", Path(td) / "e"
            res = cc.run_child(["/bin/echo", "hi"], 10, out, err)
            self.assertFalse(res["deadline_killed"])
            self.assertEqual(res["exit_code"], 0)
            self.assertEqual(out.read_text().strip(), "hi")


class NativeStats(unittest.TestCase):
    def test_long_process_time_format(self):
        # observed from a 385s kissat run in the aborted campaign evidence
        text = ("c maximum-resident-set-size:      69289902080 bytes"
                "      66080 MB\n"
                "c process-time:                         6m 25s"
                "             385.07 seconds\n")
        stats = cc.parse_kissat_native_stats(text)
        self.assertEqual(stats["kissat_process_time_seconds"], 385.07)
        self.assertEqual(stats["kissat_max_rss_bytes"], 69289902080)

    def test_short_process_time_format(self):
        stats = cc.parse_kissat_native_stats(
            "c process-time: 0.01 seconds\n")
        self.assertEqual(stats["kissat_process_time_seconds"], 0.01)



    def test_output_file_size_limit_enforced(self):
        # 8 GiB limit is too large to test directly; shrink via RLIMIT by
        # running a child that writes more than a tiny configured limit.
        with tempfile.TemporaryDirectory() as td:
            out, err = Path(td) / "o", Path(td) / "e"
            old = cc.OUTPUT_FILE_LIMIT
            cc.OUTPUT_FILE_LIMIT = 4096
            try:
                # /usr/bin/yes writes unboundedly until SIGXFSZ kills it
                res = cc.run_child(["/usr/bin/yes"], 10, out, err)
            finally:
                cc.OUTPUT_FILE_LIMIT = old
            self.assertLess(res["exit_code"], 0)
            self.assertLessEqual(out.stat().st_size, 8192)


class AttemptNumberingAndResume(unittest.TestCase):
    def make_campaign(self, td: str):
        out = Path(td)
        return out

    def test_nonterminal_attempt_dir_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            out = self.make_campaign(td)
            base = out / "attempts" / "MRB0-001"
            (base / "attempt-001").mkdir(parents=True)
            (base / "attempt-001" / "solve.stdout").write_text("partial")
            rec, n = cc.latest_terminal_attempt(out, "MRB0-001")
            self.assertIsNone(rec)
            self.assertEqual(n, 1)   # retry must use attempt-002, not overwrite

    def test_terminal_record_reused(self):
        with tempfile.TemporaryDirectory() as td:
            out = self.make_campaign(td)
            base = out / "attempts" / "MRB0-001" / "attempt-001"
            base.mkdir(parents=True)
            (base / "attempt.json").write_text(json.dumps(
                {"id": "MRB0-001", "terminal": True, "reason": "solve_timeout"}))
            rec, n = cc.latest_terminal_attempt(out, "MRB0-001")
            self.assertEqual(rec["reason"], "solve_timeout")
            self.assertEqual(n, 1)

    def test_timeout_terminal_record_survives_resume_selection(self):
        with tempfile.TemporaryDirectory() as td:
            out = self.make_campaign(td)
            base = out / "attempts" / "MRB0-001"
            (base / "attempt-001").mkdir(parents=True)
            (base / "attempt-001" / "attempt.json").write_text(json.dumps(
                {"id": "MRB0-001", "terminal": True,
                 "reason": "solve_timeout", "certified": False}))
            (base / "attempt-002").mkdir(parents=True)   # interrupted retry
            rec, n = cc.latest_terminal_attempt(out, "MRB0-001")
            self.assertEqual(rec["reason"], "solve_timeout")
            self.assertEqual(n, 2)   # next retry is attempt-003

    def test_identity_mismatch_fails_closed(self):
        recorded = {"manifest_sha256": "a", "kissat_sha256": "b",
                    "drat_trim_sha256": "c", "harness_sha256": "d",
                    "parser_sha256": "e", "solve_timeout_seconds": 1000,
                    "check_timeout_seconds": 3000}
        same = dict(recorded)
        self.assertEqual(cc.identity_mismatches(recorded, same), [])
        for key, new in (("manifest_sha256", "z"), ("kissat_sha256", "z"),
                         ("drat_trim_sha256", "z"), ("harness_sha256", "z"),
                         ("parser_sha256", "z"), ("solve_timeout_seconds", 2000),
                         ("check_timeout_seconds", 4000)):
            changed = dict(recorded)
            changed[key] = new
            mism = cc.identity_mismatches(recorded, changed)
            self.assertTrue(mism, f"{key} change must fail closed")
            self.assertTrue(any(key in m for m in mism),
                            f"mismatch message must name {key}: {mism}")

    def test_output_file_limit_change_fails_closed(self):
        # a campaign recorded with one proof cap must not resume under
        # another, and one recorded without the key fails closed too
        rec8 = {"solve_timeout_seconds": 5000,
                "output_file_limit_bytes": 8 * 2**30}
        cur64 = {"solve_timeout_seconds": 5000,
                 "output_file_limit_bytes": 64 * 2**30}
        mism = cc.identity_mismatches(rec8, cur64)
        self.assertTrue(any("output_file_limit_bytes" in m for m in mism))
        legacy = {"solve_timeout_seconds": 5000}
        self.assertTrue(any("output_file_limit_bytes" in m for m in
                            cc.identity_mismatches(legacy, cur64)))
        old = cc.OUTPUT_FILE_LIMIT
        try:
            cc.OUTPUT_FILE_LIMIT = 64 * 2**30
            ident = cc.campaign_identity(cc.DEFAULT_MANIFEST, sys.executable,
                                         sys.executable, 5000, 20000)
        finally:
            cc.OUTPUT_FILE_LIMIT = old
        self.assertEqual(ident["output_file_limit_bytes"], 64 * 2**30)

    def test_manifest_field_binding_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            out = self.make_campaign(td)
            adir = out / "attempts" / "X" / "attempt-001"
            adir.mkdir(parents=True)
            (adir / "input.cnf").write_text("p cnf 1 1\n1 0\n")
            (adir / "solve.stdout").write_text("")
            (adir / "solve.stderr").write_text("")
            payload = b"\x00proof"
            (adir / "proof.drat.gz").write_bytes(
                __import__("gzip").compress(payload, mtime=0))
            row = {"id": "X", "tier": "S", "family": "f", "category": "main",
                   "result_gbd": "unsat", "variables": "1", "clauses": "1",
                   "literals": "1", "max_width": "1", "mean_width": "1.000",
                   "alias": "X",
                   "cnf_sha256": cc.sha256_bytes(b"p cnf 1 1\n1 0\n")}
            rec = {
                "id": "X", "attempt": 1, "terminal": True, "certified": False,
                "certified_kind": None, "gbd_agreement": None,
                "attempt_dir": "attempts/X/attempt-001",
                "identity": {"cnf_sha256": row["cnf_sha256"],
                             "compressed_sha256": "comp"},
                "environment": {"solve_timeout_seconds": 1000,
                                "check_timeout_seconds": 3000},
                "solve": {"stdout_sha256": cc.sha256_bytes(b""),
                          "stderr_sha256": cc.sha256_bytes(b"")},
                "proof": {"gz_path": "proof.drat.gz",
                          "gz_sha256": cc.sha256_file(adir / "proof.drat.gz"),
                          "raw_sha256": cc.sha256_bytes(payload),
                          "raw_bytes": len(payload)},
                "manifest": dict(row),
            }
            row2 = dict(row, compressed_sha256="comp")
            self.assertEqual(
                cc.validate_record_evidence(out, rec, row2,
                                            env_expected=(1000, 3000)), [])
            errs = cc.validate_record_evidence(out, rec, row2,
                                               env_expected=(500, 3000))
            self.assertTrue(any("timeouts" in e for e in errs))
            wrong_dir = dict(rec, attempt_dir="attempts/Y/attempt-001")
            errs = cc.validate_record_evidence(out, wrong_dir, row2)
            self.assertTrue(any("attempt_dir" in e for e in errs))
            tampered = dict(rec)
            tampered["manifest"] = {**rec["manifest"], "tier": "M-high"}
            errs = cc.validate_record_evidence(out, tampered, row2)
            self.assertTrue(any("tier" in e for e in errs))
            wrong_gz = {**rec["proof"], "gz_path": "../evil.gz"}
            badgz = {**rec, "proof": wrong_gz}
            errs = cc.validate_record_evidence(out, badgz, row2)
            self.assertTrue(any("unexpected proof gz_path" in e for e in errs))
            wrong_raw = {**rec["proof"], "raw_sha256": "0" * 64}
            bad = {**rec, "proof": wrong_raw}
            errs = cc.validate_record_evidence(out, bad, row2)
            self.assertTrue(any("roundtrip" in e for e in errs))

    def test_tampered_evidence_detected(self):
        with tempfile.TemporaryDirectory() as td:
            out = self.make_campaign(td)
            adir = out / "attempts" / "X" / "attempt-001"
            adir.mkdir(parents=True)
            (adir / "input.cnf").write_text("p cnf 1 1\n1 0\n")
            rec = {
                "id": "X", "attempt_dir": "attempts/X/attempt-001",
                "identity": {"cnf_sha256": cc.sha256_bytes(b"tampered")},
                "solve": {"stdout_sha256": "0" * 64, "stderr_sha256": "0" * 64},
            }
            errs = cc.validate_record_evidence(out, rec)
            self.assertTrue(any("input.cnf" in e for e in errs))
            self.assertTrue(any("solve.stdout" in e for e in errs))


class GzipEvidence(unittest.TestCase):
    def test_roundtrip_and_raw_removed(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "proof.drat"
            dst = Path(td) / "proof.drat.gz"
            payload = b"\x00\x01binary drat payload"
            src.write_bytes(payload)
            info = cc.gzip_evidence(src, dst)
            self.assertTrue(info["roundtrip_verified"])
            self.assertEqual(info["raw_sha256"], cc.sha256_bytes(payload))
            self.assertFalse(src.exists())
            self.assertTrue(dst.exists())


class FinalizeAgreement(unittest.TestCase):
    def base_rec(self, kind):
        return {"certified": kind is not None, "certified_kind": kind,
                "manifest": {"result_gbd": "unsat"}, "gbd_agreement": None}

    def test_agree(self):
        rec = cc.finalize_gbd_agreement(self.base_rec("unsat_proof"))
        self.assertEqual(rec["gbd_agreement"], "agree")

    def test_conflict_blocks(self):
        rec = cc.finalize_gbd_agreement(self.base_rec("sat_witness"))
        self.assertEqual(rec["gbd_agreement"], "conflict")

    def test_uncertified_never_inherits_label(self):
        rec = cc.finalize_gbd_agreement(self.base_rec(None))
        self.assertIsNone(rec["gbd_agreement"])


class RecordInvariants(unittest.TestCase):
    def sat_rec(self, **over):
        rec = {"id": "X", "terminal": True, "certified": True,
               "certified_kind": "sat_witness", "claimed": "sat",
               "gbd_agreement": "agree", "manifest": {"result_gbd": "sat"},
               "solve": {"exit_code": 10, "timeout": False},
               "witness": {"parse_ok": True, "independent_check": True}}
        rec.update(over)
        return rec

    def test_genuine_sat_record_passes(self):
        self.assertEqual(cc.record_invariant_errors(self.sat_rec()), [])

    def test_forged_certificate_on_timeout_record_rejected(self):
        forged = self.sat_rec(solve={"exit_code": -15, "timeout": True},
                              witness=None)
        errs = cc.record_invariant_errors(forged)
        self.assertTrue(any("timeout" in e for e in errs))
        self.assertTrue(any("checked total witness" in e for e in errs))

    def test_flipped_conflict_to_agree_rejected(self):
        # certified SAT vs an 'unsat' label is a conflict; recorded 'agree'
        # must not survive reload
        rec = self.sat_rec(manifest={"result_gbd": "unsat"})
        errs = cc.record_invariant_errors(rec)
        self.assertTrue(any("gbd_agreement" in e for e in errs))
        rec["gbd_agreement"] = "conflict"
        self.assertEqual(cc.record_invariant_errors(rec), [])

    def test_uncertified_record_cannot_carry_certificate(self):
        errs = cc.record_invariant_errors(
            {"id": "X", "terminal": True, "certified": False,
             "certified_kind": "sat_witness", "gbd_agreement": None})
        self.assertTrue(errs)

    def test_corrupt_attempt_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            adir = Path(td) / "attempts" / "X" / "attempt-001"
            adir.mkdir(parents=True)
            (adir / "attempt.json").write_text('{"id": "X", "termin')  # truncated
            with self.assertRaises(ValueError):
                cc.latest_terminal_attempt(Path(td), "X")

    def test_identity_cnf_hash_bound_to_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            adir = out / "attempts" / "X" / "attempt-001"
            adir.mkdir(parents=True)
            (adir / "input.cnf").write_text("p cnf 1 1\n1 0\n")
            (adir / "solve.stdout").write_text("")
            (adir / "solve.stderr").write_text("")
            other = cc.sha256_bytes(b"p cnf 1 1\n1 0\n")      # file's real hash
            row = {"id": "X", "tier": "S", "family": "f", "category": "m",
                   "result_gbd": "sat", "variables": "1", "clauses": "1",
                   "literals": "1", "max_width": "1", "mean_width": "1.000",
                   "alias": "X", "cnf_sha256": "f" * 64,       # manifest says other
                   "compressed_sha256": "c"}
            rec = {"id": "X", "attempt": 1, "attempt_dir": "attempts/X/attempt-001",
                   "terminal": True, "certified": False, "certified_kind": None,
                   "gbd_agreement": None,
                   "identity": {"cnf_sha256": other, "compressed_sha256": "c"},
                   "solve": {"stdout_sha256": cc.sha256_bytes(b""),
                             "stderr_sha256": cc.sha256_bytes(b"")},
                   "manifest": dict(row)}
            errs = cc.validate_record_evidence(out, rec, row)
            self.assertTrue(any("identity cnf_sha256" in e for e in errs))


class RederiveFromEvidence(unittest.TestCase):
    """Metadata edited, evidence files untouched (hashes still verify)."""

    def build(self, td, *, solve_out, check_out=None, witness_ok=True,
              kind="sat_witness", cnf_text="p cnf 2 2\n1 0\n-1 2 0\n"):
        out = Path(td)
        adir = out / "attempts" / "X" / "attempt-001"
        adir.mkdir(parents=True)
        (adir / "input.cnf").write_text(cnf_text)
        (adir / "solve.stdout").write_text(solve_out)
        (adir / "solve.stderr").write_text("")
        rec = {"id": "X", "terminal": True, "certified": True,
               "certified_kind": kind, "attempt": 1,
               "attempt_dir": "attempts/X/attempt-001",
               "claimed": "sat" if kind == "sat_witness" else "unsat",
               "gbd_agreement": "agree",
               "manifest": {"result_gbd": "sat" if kind == "sat_witness" else "unsat"},
               "identity": {"cnf_sha256": cc.sha256_bytes(cnf_text.encode())},
               "solve": {"exit_code": 10 if kind == "sat_witness" else 20,
                         "timeout": False,
                         "stdout_sha256": cc.sha256_bytes(solve_out.encode()),
                         "stderr_sha256": cc.sha256_bytes(b"")}}
        if kind == "sat_witness":
            wtxt = "v " + ("1 2" if witness_ok else "-1 -2") + " 0\n"
            (adir / "witness.txt").write_text(wtxt)
            rec["witness"] = {"parse_ok": True, "independent_check": True,
                              "witness_sha256": cc.sha256_bytes(wtxt.encode())}
        else:
            (adir / "check.stdout").write_text(check_out)
            (adir / "check.stderr").write_text("")
            (adir / "proof.drat.gz").write_bytes(
                __import__("gzip").compress(b"a\x00", mtime=0))
            rec["proof"] = {"gz_path": "proof.drat.gz", "raw_bytes": 2,
                            "raw_sha256": cc.sha256_bytes(b"a\x00"),
                            "gz_sha256": cc.sha256_file(adir / "proof.drat.gz")}
            rec["check"] = {"exit_code": 0, "timeout": False,
                            "classification": "verified",
                            "stdout_sha256": cc.sha256_bytes(check_out.encode()),
                            "stderr_sha256": cc.sha256_bytes(b"")}
        return out, adir, rec

    def test_genuine_sat_record_rederives(self):
        with tempfile.TemporaryDirectory() as td:
            out, adir, rec = self.build(
                td, solve_out="s SATISFIABLE\nv 1 2 0\n")
            self.assertEqual(cc.rederive_certification_errors(adir, rec), [])

    def test_witness_not_satisfying_formula_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            # solver log carries a model that violates the CNF; metadata
            # (parse_ok / independent_check) was edited to say it passed
            out, adir, rec = self.build(
                td, solve_out="s SATISFIABLE\nv -1 -2 0\n")
            errs = cc.rederive_certification_errors(adir, rec)
            self.assertTrue(any("does not satisfy" in e for e in errs))
            # and the full validator surfaces it when hashes/metadata agree
            self.assertTrue(cc.validate_record_evidence(out, rec))

    def test_checker_timeout_log_with_forged_verified_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            # real drat-trim prints 's TIMEOUT' and exits 0 on its own limit
            out, adir, rec = self.build(
                td, solve_out="s UNSATISFIABLE\n", kind="unsat_proof",
                check_out="\rc parsing\ns TIMEOUT\n",
                cnf_text="p cnf 1 2\n1 0\n-1 0\n")
            errs = cc.rederive_certification_errors(adir, rec)
            self.assertTrue(any("checker log re-classifies" in e for e in errs))

    def test_genuine_unsat_record_rederives(self):
        with tempfile.TemporaryDirectory() as td:
            out, adir, rec = self.build(
                td, solve_out="s UNSATISFIABLE\n", kind="unsat_proof",
                check_out="\rc parsing\ns VERIFIED\n",
                cnf_text="p cnf 1 2\n1 0\n-1 0\n")
            self.assertEqual(cc.rederive_certification_errors(adir, rec), [])


REAL_DRAT = os.path.join(HERE, ".tools", "drat-trim", "drat-trim")


class TrivialPathCorroboration(unittest.TestCase):
    def test_requires_explicit_empty_clause(self):
        self.assertFalse(cc.trivial_path_corroborated(
            parse_dimacs("p cnf 1 1\n1 0\n")))
        self.assertTrue(cc.trivial_path_corroborated(
            parse_dimacs("p cnf 1 2\n1 0\n0\n")))

    def test_trivial_invariant_needs_empty_clause_in_input(self):
        with tempfile.TemporaryDirectory() as td:
            inp = Path(td) / "input.cnf"
            rec = {"id": "X", "terminal": True, "certified": True,
                   "certified_kind": "unsat_trivial_original",
                   "claimed": "unsat", "gbd_agreement": "agree",
                   "manifest": {"result_gbd": "unsat"},
                   "solve": {"exit_code": 20, "timeout": False},
                   "proof": {"gz_path": "proof.drat.gz"},
                   "check": {"classification": "trivial_original_formula",
                             "exit_code": 1, "timeout": False}}
            inp.write_text("p cnf 1 1\n1 0\n")
            self.assertTrue(any("corroborated" in e for e in
                                cc.record_invariant_errors(rec, inp)))
            inp.write_text("p cnf 1 2\n1 0\n0\n")
            self.assertEqual(cc.record_invariant_errors(rec, inp), [])

    @unittest.skipUnless(os.access(REAL_DRAT, os.X_OK), "pinned drat-trim absent")
    def test_real_checker_comment_misparse_is_not_certified(self):
        # pinned drat-trim, binary-proof mode: a comment line inside the CNF
        # body is read as an empty clause and yields the trivial-UNSAT path
        # for a SATISFIABLE formula.  The classifier alone accepts that
        # output; the corroboration gate must not.
        import subprocess
        with tempfile.TemporaryDirectory() as td:
            cnf_path = Path(td) / "sat.cnf"
            cnf_path.write_text("p cnf 1 1\nc comment\n1 0\n")
            proof = Path(td) / "empty.proof"
            proof.write_bytes(b"")
            res = subprocess.run([REAL_DRAT, str(cnf_path), str(proof),
                                  "-t", "30"], capture_output=True, text=True,
                                 timeout=60)
            cls, certified, _ = cc.classify_checker_run(
                res.returncode, res.stdout, False)
            self.assertEqual((cls, certified),
                             ("trivial_original_formula", True))
            self.assertFalse(cc.trivial_path_corroborated(
                parse_dimacs(cnf_path.read_text())))


class MalformedRecordsFailClosed(unittest.TestCase):
    def test_valid_json_but_wrong_shape_rejected(self):
        for body in ("{}", "[]", '{"id": "X"}', '{"id": "X", "terminal": false}',
                     '{"id": "OTHER", "terminal": true}'):
            with tempfile.TemporaryDirectory() as td:
                adir = Path(td) / "attempts" / "X" / "attempt-001"
                adir.mkdir(parents=True)
                (adir / "attempt.json").write_text(body)
                with self.assertRaises(ValueError, msg=body):
                    cc.latest_terminal_attempt(Path(td), "X")

    def test_invalid_utf8_input_reports_errors_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            adir = out / "attempts" / "X" / "attempt-001"
            adir.mkdir(parents=True)
            (adir / "input.cnf").write_bytes(b"p cnf 1 1\n1 0\n\xff\xfe")
            (adir / "solve.stdout").write_text("s UNSATISFIABLE\n")
            (adir / "solve.stderr").write_text("")
            rec = {"id": "X", "terminal": True, "certified": True,
                   "certified_kind": "unsat_trivial_original",
                   "claimed": "unsat", "gbd_agreement": "agree",
                   "attempt": 1, "attempt_dir": "attempts/X/attempt-001",
                   "manifest": {"result_gbd": "unsat"},
                   "identity": {"cnf_sha256": "0" * 64},
                   "solve": {"exit_code": 20, "timeout": False,
                             "stdout_sha256": cc.sha256_bytes(b"s UNSATISFIABLE\n"),
                             "stderr_sha256": cc.sha256_bytes(b"")},
                   "proof": {"gz_path": "proof.drat.gz", "gz_sha256": "0" * 64,
                             "raw_sha256": "0" * 64, "raw_bytes": 0},
                   "check": {"classification": "trivial_original_formula",
                             "exit_code": 1, "timeout": False,
                             "stdout_sha256": "0" * 64,
                             "stderr_sha256": "0" * 64}}
            errs = cc.validate_record_evidence(out, rec)     # must not raise
            # the same record minus a required key must also fail closed
            del rec["proof"]["gz_sha256"]
            errs2 = cc.validate_record_evidence(out, rec)
            self.assertTrue(any("malformed record" in e for e in errs2))
            self.assertTrue(any("input.cnf" in e or "corroborated" in e
                                for e in errs))


@unittest.skipUnless(os.access(REAL_DRAT, os.X_OK), "pinned drat-trim absent")
class RunAttemptTrivialGate(unittest.TestCase):
    """Production run_attempt: a faulty solver claims UNSAT; the real pinned
    drat-trim is the checker.  The fake solver only prints the claim and
    creates an empty proof, like a solver that is simply wrong."""

    def attempt(self, cnf_text):
        with tempfile.TemporaryDirectory() as td:
            fake = Path(td) / "fake_kissat.sh"
            fake.write_text('#!/bin/sh\necho "s UNSATISFIABLE"\n: > "$4"\nexit 20\n')
            fake.chmod(0o755)
            data = cnf_text.encode()
            row = {"id": "X", "tier": "S", "family": "f", "category": "c",
                   "result_gbd": "unsat", "variables": "1", "clauses": "1",
                   "literals": "1", "max_width": "1", "mean_width": "1.000",
                   "alias": "X", "cnf_sha256": cc.sha256_bytes(data),
                   "compressed_sha256": "c"}
            out = Path(td) / "out"
            rec = cc.run_attempt(row, data, out, 1, str(fake), REAL_DRAT, 30, 30)
            return rec, cc.record_invariant_errors(
                rec, out / rec["attempt_dir"] / "input.cnf")

    def test_satisfiable_formula_with_body_comment_not_certified(self):
        rec, _ = self.attempt("p cnf 1 1\nc comment\n1 0\n")
        self.assertEqual(rec["check"]["classification"],
                         "trivial_original_formula")     # checker's quirk
        self.assertFalse(rec["certified"])
        self.assertIsNone(rec["certified_kind"])
        self.assertEqual(rec["reason"], "trivial_unsat_uncorroborated")

    def test_explicit_empty_clause_is_certified_via_trivial_path(self):
        rec, inv = self.attempt("p cnf 1 2\n1 0\n0\n")
        self.assertTrue(rec["certified"])
        self.assertEqual(rec["certified_kind"], "unsat_trivial_original")
        self.assertEqual(rec["reason"], "ok")
        self.assertEqual(inv, [])


if __name__ == "__main__":
    unittest.main()
