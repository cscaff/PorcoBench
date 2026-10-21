"""Decision-logic tests for screen_pigweed.py: semantics gate, fixed-limit
flags, pilot selection.  The candidate loader is exercised through the real
worker subprocess for the empty-clause loss case."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import screen_pigweed as S  # noqa: E402

CAPS = {"N_MAX": 2048, "C_MAX": 4096, "LE_MAX": 16384, "CE_MAX": 16384,
        "NUM_W": 11, "REM_W": 12}


class CompareSemantics(unittest.TestCase):
    def test_sort_and_dedup_allowed(self):
        strict = [(3, -1), (2, 2, -3)]
        cand = [[-1, 3], [2, -3]]
        r = S.compare_semantics(3, strict, 3, cand)
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["normalized_clauses"], 2)

    def test_dropped_empty_clause_is_error(self):
        r = S.compare_semantics(2, [(1, -2), (), (2,)], 2, [[1, -2], [2]])
        self.assertEqual(r["status"], "input_semantics_error")
        self.assertIn("empty", r["detail"])

    def test_polarity_flip_is_error(self):
        r = S.compare_semantics(2, [(1, 2)], 2, [[1, -2]])
        self.assertEqual(r["status"], "input_semantics_error")

    def test_duplicate_clauses_and_order_preserved(self):
        strict = [(1, 2), (1, 2), (-1,)]
        self.assertEqual(
            S.compare_semantics(2, strict, 2, [[1, 2], [1, 2], [-1]])["status"],
            "ok")
        self.assertEqual(
            S.compare_semantics(2, strict, 2, [[1, 2], [-1]])["status"],
            "input_semantics_error")          # a duplicate clause was merged
        self.assertEqual(
            S.compare_semantics(2, strict, 2, [[-1], [1, 2], [1, 2]])["status"],
            "input_semantics_error")          # clause order changed

    def test_variable_count_change_is_error(self):
        r = S.compare_semantics(5, [(1,)], 4, [[1]])
        self.assertEqual(r["status"], "input_semantics_error")

    def test_real_worker_exposes_empty_clause_loss(self):
        from benchmark_cnf import parse_dimacs
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "empty.cnf")
            with open(path, "w") as f:
                f.write("p cnf 2 3\n1 -2 0\n0\n2 0\n")
            strict = parse_dimacs(open(path).read())
            res = S.run_worker(path)
            cp = res["candidate_parse"]
            r = S.compare_semantics(strict.num_vars, strict.clauses,
                                    cp["num_vars"], cp["clauses"])
            self.assertEqual(r["status"], "input_semantics_error")


class FieldFlags(unittest.TestCase):
    def test_clean_instance_has_no_flags(self):
        self.assertEqual(S.field_flags(CAPS, 25, 12), [])

    def test_clause_length_fields(self):
        self.assertEqual(len(S.field_flags(CAPS, 2048, 0)), 1)   # NUM_W only
        self.assertEqual(len(S.field_flags(CAPS, 4096, 0)), 2)   # NUM_W + REM_W

    def test_fixed_stack_over_capacity(self):
        # 2048 vars with contradictory units 1 / -1: 2047 free + 2 units = 2049
        flags = S.field_flags(CAPS, 1, 2049)
        self.assertTrue(any("fixed_stack" in f for f in flags))
        self.assertEqual(S.field_flags(CAPS, 1, 2048), [])


class Pilots(unittest.TestCase):
    @staticmethod
    def row(i, tier, kind, secs, occ, **kw):
        r = {"id": i, "tier": tier, "lit_page": "16", "cpu_certified": "true",
             "cpu_certified_kind": kind, "cpu_solve_wall_seconds": str(secs),
             "occupancy": str(occ), "semantics_status": "ok",
             "build_status": "loaded", "dispatchable": "true"}
        r.update(kw)
        return r

    def test_selection_ties_gaps_and_filters(self):
        rows = [
            self.row("A2", "S", "sat_witness", 1.0, 0.5),
            self.row("A1", "S", "sat_witness", 1.0, 0.5),       # tie -> A1
            self.row("B1", "S", "unsat_proof", 9.0, 0.9),
            # ineligible: uncertified, wrong page, semantics, not dispatchable
            self.row("X1", "S", "sat_witness", 0.1, 0.99, cpu_certified="false"),
            self.row("X2", "S", "sat_witness", 0.1, 0.99, lit_page="8"),
            self.row("X3", "S", "sat_witness", 0.1, 0.99,
                     semantics_status="input_semantics_error"),
            self.row("X4", "S", "sat_witness", 0.1, 0.99, dispatchable="false"),
        ]
        p = S.pilot_candidates(rows)
        s = p["S"]["cells"]
        self.assertEqual(s["fastest_sat"]["id"], "A1")
        self.assertEqual(s["fastest_unsat"]["id"], "B1")
        self.assertEqual(s["max_occupancy"]["id"], "B1")
        self.assertEqual(p["S"]["ids"], ["A1", "B1"])
        # empty tiers are explicit gaps, never filled from another tier
        self.assertEqual(p["M-low"]["ids"], [])
        self.assertEqual(sorted(p["M-low"]["gaps"]),
                         ["fastest_sat", "fastest_unsat", "max_occupancy"])
        self.assertEqual(p["all_ids"], ["A1", "B1"])


class ScreenInstanceProductionPath(unittest.TestCase):
    """screen_instance end to end with the real candidate worker."""

    def screen(self, text, variables):
        import hashlib
        with tempfile.TemporaryDirectory() as td:
            d = os.path.join(td, "attempts", "X", "attempt-001")
            os.makedirs(d)
            with open(os.path.join(d, "input.cnf"), "w") as f:
                f.write(text)
            row = {"id": "X", "tier": "S", "family": "f", "category": "c",
                   "result_gbd": "sat", "variables": str(variables),
                   "clauses": "2", "literals": "2", "max_width": "1",
                   "cnf_sha256": hashlib.sha256(text.encode()).hexdigest()}
            cpu = {"attempt": "1", "certified": "true",
                   "certified_kind": "sat_witness", "reason": "ok",
                   "solve_wall_seconds": "1.0"}
            rows = S.screen_instance(row, cpu, td)
        return {int(r["lit_page"]): r for r in rows}

    def test_fixed_stack_overflow_blocks_dispatch(self):
        # units +1/-1 plus 2047 unconstrained vars -> 2049 fixed entries
        # against the 2048-entry answer stack; stores themselves fit
        rows = self.screen("p cnf 2048 2\n1 0\n-1 0\n", 2048)
        for page, r in rows.items():
            self.assertEqual(r["build_status"], "loaded", page)
            self.assertEqual(r["fixed_height"], 2049, page)
            self.assertIn("fixed_stack=2049>N_MAX=2048", r["field_flags"], page)
            self.assertEqual(r["dispatchable"], "false", page)

    def test_fixed_stack_exact_capacity_is_dispatchable(self):
        # unit 1 + 2047 unconstrained variables = exactly the 2048-entry stack
        rows = self.screen("p cnf 2048 1\n1 0\n", 2048)
        r = rows[16]
        self.assertEqual(r["fixed_height"], 2048)
        self.assertEqual(r["field_flags"], "")
        self.assertEqual(r["dispatchable"], "true")


class SummaryNormalizationCount(unittest.TestCase):
    @staticmethod
    def row(i, page, normalized, status="loaded", sem="ok"):
        r = {f: "" for f in S.ROW_FIELDS}
        r.update({"id": i, "tier": "S", "lit_page": str(page),
                  "cpu_certified": "true", "build_status": status,
                  "semantics_status": sem, "normalized_clauses": normalized,
                  "field_flags": "", "dispatchable": "true",
                  "occupancy": "0.1", "lit_words": 1, "cls_words": 1,
                  "clause_ids_used": 1})
        return r

    def test_counts_distinct_normalized_instances_at_baseline_only(self):
        rows = []
        for page in (4, 8, 16):
            rows.append(self.row("NORM", page, 3))     # normalized
            rows.append(self.row("PLAIN", page, 0))    # nothing reordered
            rows.append(self.row("CRASH", page, "", status="crash",
                                 sem="candidate_crash"))
        s = S.derive_summary(rows)["semantics"]
        self.assertEqual(s["instances_with_within_clause_normalization"], 1)
        self.assertEqual(s["candidate_crash"], 1)
        self.assertEqual(s["ok"], 2)


class Classification(unittest.TestCase):
    def test_unsupported_buckets(self):
        self.assertEqual(S.classify_unsupported("5000 variables > N_MAX 2048"),
                         "variables")
        self.assertEqual(S.classify_unsupported("5000 clauses > C_MAX 4096"),
                         "clauses")
        self.assertEqual(
            S.classify_unsupported("clause store needs 20000 words > CE_MAX 16384"),
            "clause_store")
        self.assertEqual(
            S.classify_unsupported("literal store needs 20000 words > LE_MAX 16384"),
            "literal_store")

    def test_occupancy_is_max_of_three_fractions(self):
        b = {"cls_words": 8192, "lit_words": 4096, "clause_ids_used": 1024}
        o = S.occupancy(b, CAPS)
        self.assertAlmostEqual(o["occupancy"], 0.5)
        self.assertAlmostEqual(o["lit_word_frac"], 0.25)


if __name__ == "__main__":
    unittest.main()
