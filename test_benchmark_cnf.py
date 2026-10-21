"""Behavioral boundary tests for benchmark_cnf.py (stdlib unittest).

Strict parse: order/duplicates/tautologies/empty clauses preserved verbatim;
count, termination, range, header and trailer deviations rejected; the
historical '%'/'0' DIMACS trailer rule enforced exactly.  Witness validation
requires a total boolean model of the original formula.
"""

from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from benchmark_cnf import CNF, CNFError, check_witness, parse_dimacs  # noqa: E402


def parse(text: str) -> CNF:
    return parse_dimacs(text)


class Accepts(unittest.TestCase):
    def test_preserves_empty_clauses_duplicates_tautologies_order(self):
        cnf = parse("p cnf 3 6\n1 -2 0\n0\n2 2 0\n-3 -3 0\n3 1 0\n1 -2 0\n")
        self.assertEqual(cnf.num_vars, 3)
        self.assertEqual(cnf.clauses, (
            (1, -2), (), (2, 2), (-3, -3), (3, 1), (1, -2)))

    def test_multiple_clauses_per_line_and_across_lines(self):
        cnf = parse("p cnf 2 3\n1 2 0 -1 0\n2\n-2 0\n")
        self.assertEqual(cnf.clauses, ((1, 2), (-1,), (2, -2)))

    def test_comments_blanks_and_full_trailer(self):
        cnf = parse("c header comment\n\np cnf 1 1\nc mid\n1 0\n\nc tail\n%\n0\n")
        self.assertEqual(cnf.clauses, ((1,),))

    def test_no_trailer_is_fine(self):
        self.assertEqual(parse("p cnf 1 1\n1 0\n").clauses, ((1,),))

    def test_empty_formula_and_empty_clause_forms(self):
        self.assertEqual(parse("p cnf 0 0\n").clauses, ())
        self.assertEqual(parse("p cnf 1 2\n0 0\n").clauses, ((), ()))
        self.assertEqual(parse("p cnf 2 1\n0\n").clauses, ((),))

    def test_structural_counts(self):
        cnf = parse("p cnf 2 3\n1 -2 0\n0\n2 0\n")
        st = cnf.structural()
        self.assertEqual(st["literals"], 3)
        self.assertEqual(st["widths"], [2, 0, 1])
        self.assertEqual(st["empty_clauses"], 1)

    def test_cnf_is_frozen(self):
        cnf = parse("p cnf 1 1\n1 0\n")
        with self.assertRaises(Exception):
            cnf.num_vars = 5


class Rejects(unittest.TestCase):
    def check(self, text: str, why: str):
        with self.assertRaises(CNFError, msg=why):
            parse(text)

    def test_missing_header(self):
        self.check("1 2 0\n", "no header at all")
        self.check("c only comments\n", "comments only")

    def test_duplicate_or_malformed_header(self):
        self.check("p cnf 1 1\n1 0\np cnf 1 1\n1 0\n", "duplicate header")
        self.check("p cnf 1\n1 0\n", "short header")
        self.check("p cnf 1 1 1\n1 0\n", "long header")
        self.check("p sat 1 1\n1 0\n", "wrong format name")
        self.check("p cnf x 1\n1 0\n", "non-integer count")
        self.check("p cnf -1 1\n1 0\n", "negative var count")
        self.check("p cnf 1 -1\n0\n", "negative clause count")

    def test_data_before_header(self):
        self.check("1 0\np cnf 1 1\n", "literal before header")

    def test_clause_count_mismatch(self):
        self.check("p cnf 1 2\n1 0\n", "too few clauses")
        self.check("p cnf 1 1\n1 0\n1 0\n", "too many clauses (new line)")
        self.check("p cnf 1 1\n1 0 1 0\n", "too many clauses (same line)")
        self.check("p cnf 2 0\n1 0\n", "data after M=0 header")

    def test_missing_terminator(self):
        self.check("p cnf 2 2\n1 0\n2\n", "trailing unterminated clause")
        self.check("p cnf 2 1\n1 2\n", "single unterminated clause")

    def test_literal_range(self):
        self.check("p cnf 1 1\n2 0\n", "beyond N")
        self.check("p cnf 1 1\n-2 0\n", "below -N")
        self.check("p cnf 0 1\n1 0\n", "any literal with N=0")

    def test_non_integer_tokens(self):
        self.check("p cnf 2 1\n1 x 0\n", "letter token")
        self.check("p cnf 2 1\n1.5 0\n", "float token")
        self.check("p cnf 2 1\n1 --2 0\n", "double sign")
        self.check("p cnf 2 1\n+ 0\n", "bare sign")

    def test_trailer_rules(self):
        self.check("p cnf 1 1\n1 0\n%\n", "percent without zero")
        self.check("p cnf 1 1\n1 0\n0\n", "zero without percent")
        self.check("p cnf 1 1\n1 0\n%\n1 0\n", "data in trailer slot")
        self.check("p cnf 1 1\n1 0\n%\n0\n0\n", "trailer zero repeated")
        self.check("p cnf 1 1\n1 0\n%%\n0\n", "percent not standalone")
        self.check("p cnf 1 1\n1 0\n% 0\n", "trailer on one line")
        self.check("p cnf 1 1\n%\n1 0\n0\n", "percent before formula end")


class Witness(unittest.TestCase):
    # clause 1: (1 or 2); clause 2: (-1).  Only model: 1=False, 2=True.
    CNF2 = parse("p cnf 2 2\n1 2 0\n-1 0\n")
    EMPTY_CLAUSE = parse("p cnf 1 1\n0\n")
    EMPTY_FORMULA = parse("p cnf 0 0\n")

    def test_total_satisfying_model_accepted(self):
        self.assertTrue(check_witness(self.CNF2, {1: False, 2: True}))

    def test_wrong_model_rejected(self):
        self.assertFalse(check_witness(self.CNF2, {1: True, 2: False}))
        self.assertFalse(check_witness(self.CNF2, {1: False, 2: False}))

    def test_incomplete_or_overfull_model_rejected(self):
        self.assertFalse(check_witness(self.CNF2, {1: False}))
        self.assertFalse(check_witness(self.CNF2, {1: False, 2: True, 3: True}))

    def test_non_boolean_values_rejected(self):
        self.assertFalse(check_witness(self.CNF2, {1: 0, 2: 1}))
        self.assertFalse(check_witness(self.CNF2, {1: "false", 2: True}))

    def test_non_dict_rejected(self):
        self.assertFalse(check_witness(self.CNF2, [(1, True), (2, False)]))

    def test_empty_clause_is_false(self):
        self.assertFalse(check_witness(self.EMPTY_CLAUSE, {1: True}))

    def test_empty_formula_true_with_empty_total_model(self):
        self.assertTrue(check_witness(self.EMPTY_FORMULA, {}))

    def test_tautology_preserved_in_satisfaction(self):
        cnf = parse("p cnf 2 2\n1 -1 0\n-2 0\n")
        self.assertTrue(check_witness(cnf, {1: False, 2: False}))


if __name__ == "__main__":
    unittest.main()
