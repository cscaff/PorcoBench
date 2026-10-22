#!/usr/bin/env python3
"""Strict DIMACS CNF parsing and witness checking for the benchmark organizer.

This replaces the ``satbench.cnf`` dependency that lived inside the PigWeedSAT
clone at CPU-calibration time and is no longer present there.  It is a fresh,
independently reviewed implementation: its hash is recorded as a *new*
organizer identity component and never presented as the historical parser.

Contract (frozen; consumers: build_benchmark.verify_instance,
calibrate_cpu preflight/certification, screen_pigweed, run_pigweed_fpga):

* ``parse_dimacs(text)`` accepts exactly one ``p cnf N M`` header before any
  data, nonnegative counts, signed integer literals within 1..N, ``0``
  terminating each clause (empty clauses included), multiple clauses per line
  and clauses spanning lines.  Blank lines and whole-line ``c`` comments are
  ignored.  Exactly M terminated clauses are required.  The historical DIMACS
  trailer -- a standalone ``%`` line followed by exactly a ``0`` line (blank/
  comment lines in between allowed) -- is accepted after the completed
  formula; incomplete or malformed trailers and any further data are errors.
  Order, duplicate literals, tautologies and empty clauses are preserved
  verbatim: no simplification of any kind.

* ``check_witness(cnf, assignment)`` requires exactly the keys 1..N, boolean
  values, and every original clause satisfied.  An empty clause is false; an
  empty formula is true with a total (empty) assignment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict

__all__ = ["CNFError", "CNF", "parse_dimacs", "check_witness"]

_INT_TOKEN = re.compile(r"^[+-]?[0-9]+$")


class CNFError(ValueError):
    """Malformed DIMACS input (strict parse)."""


@dataclass(frozen=True)
class CNF:
    num_vars: int
    clauses: tuple[tuple[int, ...], ...]

    def structural(self) -> Dict[str, object]:
        """Raw structural counts used by tier verification: total literal
        count, one width per clause, and how many clauses are empty."""
        widths = [len(c) for c in self.clauses]
        return {
            "literals": sum(widths),
            "widths": widths,
            "empty_clauses": sum(1 for w in widths if w == 0),
        }


def parse_dimacs(text: str) -> CNF:
    """Parse *text* as a strict DIMACS CNF; raise CNFError on any deviation."""
    header_seen = False
    formula_complete = False
    trailer_percent = False
    trailer_zero = False
    num_vars = num_clauses = -1
    clauses: list[tuple[int, ...]] = []
    cur: list[int] = []

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("c"):
            continue
        tokens = stripped.split()
        if formula_complete:
            if not trailer_percent:
                if tokens == ["%"]:
                    trailer_percent = True
                    continue
                raise CNFError(f"line {lineno}: data after completed formula")
            if not trailer_zero:
                if tokens == ["0"]:
                    trailer_zero = True
                    continue
                raise CNFError(f"line {lineno}: malformed DIMACS trailer "
                               f"(expected '0' after '%')")
            raise CNFError(f"line {lineno}: data after DIMACS trailer")
        if tokens[0] == "p":
            if header_seen:
                raise CNFError(f"line {lineno}: duplicate 'p cnf' header")
            if len(tokens) != 4 or tokens[1] != "cnf":
                raise CNFError(f"line {lineno}: malformed 'p cnf' header")
            if not _INT_TOKEN.match(tokens[2]) or not _INT_TOKEN.match(tokens[3]):
                raise CNFError(f"line {lineno}: non-integer header counts")
            num_vars, num_clauses = int(tokens[2]), int(tokens[3])
            if num_vars < 0 or num_clauses < 0:
                raise CNFError(f"line {lineno}: negative header counts "
                               f"(vars={num_vars}, clauses={num_clauses})")
            header_seen = True
            if num_clauses == 0:
                formula_complete = True
            continue
        if not header_seen:
            raise CNFError(f"line {lineno}: data before 'p cnf' header")
        for i, tok in enumerate(tokens):
            if not _INT_TOKEN.match(tok):
                raise CNFError(f"line {lineno}: non-integer token {tok!r}")
            v = int(tok)
            if v == 0:
                clauses.append(tuple(cur))
                cur = []
                if len(clauses) == num_clauses:
                    formula_complete = True
                    if i != len(tokens) - 1:
                        raise CNFError(
                            f"line {lineno}: data after completed formula")
                    break
            elif abs(v) > num_vars:
                raise CNFError(f"line {lineno}: literal {v} out of range "
                               f"1..{num_vars}")
            else:
                cur.append(v)

    if not header_seen:
        raise CNFError("missing 'p cnf' header")
    if trailer_percent and not trailer_zero:
        raise CNFError("incomplete DIMACS trailer ('%' without '0')")
    if not formula_complete:
        if cur:
            raise CNFError(f"clause missing terminating 0 "
                           f"({len(clauses) + 1} clauses started, "
                           f"{num_clauses} declared)")
        raise CNFError(f"{len(clauses)} clauses terminated, "
                       f"{num_clauses} declared")
    return CNF(num_vars=num_vars, clauses=tuple(clauses))


def check_witness(cnf: CNF, assignment: dict[int, bool]) -> bool:
    """True iff *assignment* is a total model of *cnf* (keys exactly 1..N,
    boolean values, every original clause satisfied)."""
    if not isinstance(assignment, dict):
        return False
    if set(assignment.keys()) != set(range(1, cnf.num_vars + 1)):
        return False
    if not all(isinstance(v, bool) for v in assignment.values()):
        return False
    for clause in cnf.clauses:
        if not clause:
            return False
        if not any(assignment[abs(x)] == (x > 0) for x in clause):
            return False
    return True
