# Checked CPU calibration campaign (cpu-v1-5000s)

## Certification statement

**Not all 20 certified**: 5/20 certified, 0 label conflicts, 15 unresolved.

## Headline counts

- records: 20
- attempted: 20
- claimed_sat: 2
- claimed_unsat: 3
- claimed_unknown_or_timeout: 15
- witness_checked_sat: 2
- proof_checked_unsat: 3
- trivial_original_unsat: 0
- certified_total: 5
- label_conflicts: 0
- unresolved: 15

## Breakdowns (certified / unresolved / conflict)

### by tier

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| S | 10 | 3 | 7 | 0 | 2187.5333 | 8736.519 | 0.0002 |
| S-tight | 10 | 2 | 8 | 0 | 1658.2249 | 2069.4489 | 0.001 |

### by family

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| binary-tree-parity | 1 | 1 | 0 | 0 | 1658.2249 |  | 0.001 |
| linvrinv | 1 | 1 | 0 | 0 | 841.1355 | 2069.4489 |  |
| long-learned-clauses | 1 | 1 | 0 | 0 | 2187.5333 | 5319.9813 |  |
| pigeon-hole | 1 | 0 | 1 | 0 |  |  |  |
| scheduling | 1 | 0 | 1 | 0 |  |  |  |
| sgen | 8 | 2 | 6 | 0 | 4617.8396 | 8736.519 | 0.0002 |
| sudoku-php | 1 | 0 | 1 | 0 |  |  |  |
| tseitin-formulas | 6 | 0 | 6 | 0 |  |  |  |

### by category

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| crafted | 5 | 1 | 4 | 0 | 4617.8396 | 8736.519 |  |
| main | 15 | 4 | 11 | 0 | 1658.2249 | 5319.9813 | 0.001 |

### by expected result

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| sat | 7 | 2 | 5 | 0 | 1658.2249 |  | 0.001 |
| unsat | 13 | 3 | 10 | 0 | 2187.5333 | 5319.9813 |  |

## Certified timing

- solve wall quantiles (s): {'count': 5, 'min': 841.1355, 'p50': 1658.2249, 'p90': 3645.7171, 'p99': 4520.6273, 'max': 4617.8396}
- checker wall quantiles (s): {'count': 3, 'min': 2069.4489, 'p50': 5319.9813, 'p90': 8053.2115, 'p99': 8668.1883, 'max': 8736.519}
- witness check quantiles (s): {'count': 2, 'min': 0.0002, 'p50': 0.0006, 'p90': 0.0009, 'p99': 0.001, 'max': 0.001}
- solve bins: {'<0.1': 0, '0.1-1': 0, '1-10': 0, '10-100': 0, '100-1000': 1} (unresolved: 15)

Timing semantics: proof-enabled Kissat wall time including input parsing and proof I/O; not proof-free CPU speed and not projected FPGA runtime. A single seed-0 run is a calibration survey, not a precise ranking. Sub-0.1-second entries are triviality candidates only.

## Proof sizes

- raw total: 359441156949 bytes; gz total: 77201012593 bytes
- UNSAT proof raw-bytes quantiles (certificates only): {'count': 3, 'min': 1711035576, 'p50': 4247499041.0, 'p90': 5333062704.2, 'p99': 5577314528.42, 'max': 5604453620}
- UNSAT proof gz-bytes quantiles: {'count': 3, 'min': 730340941, 'p50': 1673476256.0, 'p90': 1985342793.6, 'p99': 2055512764.56, 'max': 2063309428}

## Unresolved / conflicting instances

| id | claimed | certified | reason | gbd | agreement |
|---|---|---|---|---|---|
| MRB0-004 |  | false | solve_timeout | sat |  |
| MRB0-006 |  | false | solver_unknown | sat |  |
| MRB0-007 |  | false | solve_timeout | unsat |  |
| MRB0-008 |  | false | solve_timeout | sat |  |
| MRB0-010 |  | false | solve_timeout | sat |  |
| MRB0-012 |  | false | solve_timeout | sat |  |
| MRB0-019 |  | false | solver_unknown | unsat |  |
| MRB0-042 |  | false | solve_timeout | unsat |  |
| MRB0-080 |  | false | solve_timeout | unsat |  |
| MRB0-082 |  | false | solve_timeout | unsat |  |
| MRB0-084 |  | false | solve_timeout | unsat |  |
| MRB0-086 |  | false | solve_timeout | unsat |  |
| MRB0-088 |  | false | solver_unknown | unsat |  |
| MRB0-089 |  | false | solve_timeout | unsat |  |
| MRB0-090 |  | false | solve_timeout | unsat |  |

