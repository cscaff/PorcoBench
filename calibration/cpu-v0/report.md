# Checked CPU calibration campaign (cpu-v0)

## Certification statement

**Not all 210 certified**: 148/210 certified, 0 label conflicts, 62 unresolved.

## Headline counts

- records: 210
- attempted: 210
- claimed_sat: 77
- claimed_unsat: 72
- claimed_unknown_or_timeout: 61
- witness_checked_sat: 77
- proof_checked_unsat: 71
- trivial_original_unsat: 0
- certified_total: 148
- label_conflicts: 0
- unresolved: 62

## Breakdowns (certified / unresolved / conflict)

### by tier

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| M-high | 52 | 32 | 20 | 0 | 107.4812 | 87.2541 | 0.0029 |
| M-low | 68 | 47 | 21 | 0 | 69.4294 | 136.1779 | 0.0019 |
| S | 19 | 9 | 10 | 0 | 191.8739 | 153.7605 | 0.0002 |
| S-tight | 71 | 60 | 11 | 0 | 2.1533 | 17.7881 | 0.0009 |

### by family

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| automata-synchronization | 1 | 1 | 0 | 0 | 1.1324 | 0.3037 |  |
| battleship | 3 | 3 | 0 | 0 | 9.7964 | 17.7881 | 0.0022 |
| binary-pigeon-hole | 1 | 0 | 1 | 0 |  |  |  |
| binary-tree-parity | 2 | 0 | 2 | 0 |  |  |  |
| cardinality-constraints | 5 | 5 | 0 | 0 | 27.8448 | 618.0031 | 0.0029 |
| clique-formulas | 1 | 1 | 0 | 0 | 5.512 | 9.1251 |  |
| clustered-random | 1 | 1 | 0 | 0 | 127.3184 | 106.9999 |  |
| coloring | 10 | 7 | 3 | 0 | 0.2688 | 7.9106 | 0.0023 |
| coloring-clique | 4 | 0 | 4 | 0 |  |  |  |
| count | 2 | 0 | 2 | 0 |  |  |  |
| cryptography | 3 | 3 | 0 | 0 | 437.6582 | 737.6574 | 0.002 |
| datapath-equivalence-checking | 4 | 0 | 4 | 0 |  |  |  |
| exam-scheduling | 1 | 0 | 1 | 0 |  |  |  |
| fpga-routing | 3 | 3 | 0 | 0 | 41.096 | 83.7927 |  |
| generic-csp | 2 | 2 | 0 | 0 | 17.5771 | 21.1828 | 0.0024 |
| grandtour-puzzle | 1 | 1 | 0 | 0 | 37.0451 | 72.6794 |  |
| graph-coloring | 1 | 1 | 0 | 0 | 16.9721 | 15.7857 |  |
| greentao | 1 | 1 | 0 | 0 | 120.0969 |  | 0.0017 |
| hamiltonian | 10 | 10 | 0 | 0 | 56.1948 | 75.5264 | 0.0018 |
| heule-nol | 7 | 7 | 0 | 0 | 152.6882 |  | 0.003 |
| hgen | 3 | 3 | 0 | 0 | 1.4139 |  | 0.0005 |
| hidoku | 3 | 3 | 0 | 0 | 43.6311 | 49.9951 |  |
| lights-out | 3 | 2 | 1 | 0 | 192.8131 | 87.2541 | 0.0029 |
| linvrinv | 1 | 0 | 1 | 0 |  |  |  |
| long-learned-clauses | 1 | 0 | 1 | 0 |  |  |  |
| mechanical-master-key | 1 | 0 | 1 | 0 |  |  |  |
| minimal-disagreement-parity | 1 | 0 | 1 | 0 |  |  |  |
| minimum-disagreement-parity | 10 | 4 | 6 | 0 | 659.0937 | 1278.467 | 0.0019 |
| miter | 3 | 3 | 0 | 0 | 74.9762 | 149.4914 |  |
| multiplier-circuit-miters | 3 | 0 | 3 | 0 |  |  |  |
| multiplier-equivalence-checking | 2 | 1 | 1 | 0 | 366.3864 | 614.8815 |  |
| mutilated-chessboard | 5 | 4 | 1 | 0 | 89.5061 | 144.9195 |  |
| or_randxor | 2 | 2 | 0 | 0 | 11.1017 | 13.9699 |  |
| philips | 1 | 1 | 0 | 0 | 83.5384 | 136.1779 |  |
| pigeon-hole | 4 | 3 | 1 | 0 | 153.536 | 268.7659 |  |
| planning | 2 | 2 | 0 | 0 | 0.0499 |  | 0.0023 |
| prime-factoring | 1 | 1 | 0 | 0 | 6.1451 |  | 0.0027 |
| product-configuration | 1 | 1 | 0 | 0 | 0.0067 | 0.0472 |  |
| random | 10 | 10 | 0 | 0 | 0.3424 |  | 0.001 |
| random-graph-xorsat | 9 | 9 | 0 | 0 | 111.3492 |  | 0.001 |
| random-planted-solution | 10 | 10 | 0 | 0 | 0.6519 |  | 0.001 |
| register-allocation | 10 | 10 | 0 | 0 | 4.3804 | 7.9174 |  |
| relativized-pigeon-hole | 4 | 2 | 2 | 0 | 527.9403 | 824.4072 |  |
| scheduling | 7 | 5 | 2 | 0 | 0.0222 | 0.4493 | 0.0005 |
| sgen | 10 | 2 | 8 | 0 | 906.2221 | 153.7605 | 0.0002 |
| sgen-balanced | 1 | 1 | 0 | 0 | 398.776 | 250.3711 |  |
| st-connectivity-principle | 1 | 1 | 0 | 0 | 217.799 | 123.8267 |  |
| stable-semantics | 1 | 0 | 1 | 0 |  |  |  |
| subset-cardinality | 4 | 4 | 0 | 0 | 504.6724 | 406.3928 |  |
| sudoku-php | 2 | 0 | 2 | 0 |  |  |  |
| theorem-proving | 1 | 1 | 0 | 0 | 0.0258 | 0.0828 |  |
| tseitin-formulas | 10 | 4 | 6 | 0 | 205.7741 | 1003.3944 |  |
| uniform-random | 7 | 5 | 2 | 0 | 130.2728 |  | 0.0022 |
| unknown-cases | 4 | 4 | 0 | 0 | 193.0766 |  | 0.002 |
| van-der-waerden | 5 | 4 | 1 | 0 | 531.5614 | 1096.7755 |  |
| xor-shifting | 4 | 0 | 4 | 0 |  |  |  |

### by category

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| crafted | 29 | 22 | 7 | 0 | 93.2402 | 153.7605 | 0.0012 |
| main | 154 | 101 | 53 | 0 | 41.096 | 65.6885 | 0.0019 |
| random | 27 | 25 | 2 | 0 | 0.4114 |  | 0.001 |

### by expected result

| value | total | certified | unresolved | conflict | median solve s | median checker s | median witness s |
|---|---|---|---|---|---|---|---|
| sat | 99 | 77 | 22 | 0 | 21.5161 |  | 0.0016 |
| unsat | 111 | 71 | 40 | 0 | 55.3489 | 75.5264 |  |

## Certified timing

- solve wall quantiles (s): {'count': 148, 'min': 0.0067, 'p50': 39.3188, 'p90': 461.2765, 'p99': 889.2287, 'max': 906.2221}
- checker wall quantiles (s): {'count': 71, 'min': 0.0446, 'p50': 75.5264, 'p90': 824.4072, 'p99': 1192.3027, 'max': 1278.467}
- witness check quantiles (s): {'count': 77, 'min': 0.0002, 'p50': 0.0016, 'p90': 0.0029, 'p99': 0.0043, 'max': 0.0047}
- solve bins: {'<0.1': 14, '0.1-1': 23, '1-10': 16, '10-100': 43, '100-1000': 52} (unresolved: 62)

Timing semantics: proof-enabled Kissat wall time including input parsing and proof I/O; not proof-free CPU speed and not projected FPGA runtime. A single seed-0 run is a calibration survey, not a precise ranking. Sub-0.1-second entries are triviality candidates only.

## Proof sizes

- raw total: 247819225232 bytes; gz total: 86839800870 bytes
- UNSAT proof raw-bytes quantiles (certificates only): {'count': 71, 'min': 1112, 'p50': 164340775.0, 'p90': 918409477.0, 'p99': 2132596886.9, 'max': 2178862514}
- UNSAT proof gz-bytes quantiles: {'count': 71, 'min': 464, 'p50': 66040657.0, 'p90': 353244078.0, 'p99': 588315300.4, 'max': 671421406}

## Unresolved / conflicting instances

| id | claimed | certified | reason | gbd | agreement |
|---|---|---|---|---|---|
| MRB0-001 |  | false | solve_timeout | unsat |  |
| MRB0-003 |  | false | solve_timeout | unsat |  |
| MRB0-004 |  | false | solve_timeout | sat |  |
| MRB0-006 |  | false | solve_timeout | sat |  |
| MRB0-007 |  | false | solve_timeout | unsat |  |
| MRB0-008 |  | false | solve_timeout | sat |  |
| MRB0-009 |  | false | solver_unknown | sat |  |
| MRB0-010 |  | false | solve_timeout | sat |  |
| MRB0-012 |  | false | solver_unknown | sat |  |
| MRB0-019 |  | false | solver_signal_25 | unsat |  |
| MRB0-021 |  | false | solve_timeout | sat |  |
| MRB0-037 | unsat | false | checker_internal_timeout | unsat |  |
| MRB0-039 |  | false | solve_timeout | unsat |  |
| MRB0-042 |  | false | solve_timeout | unsat |  |
| MRB0-080 |  | false | solve_timeout | unsat |  |
| MRB0-082 |  | false | solve_timeout | unsat |  |
| MRB0-084 |  | false | solve_timeout | unsat |  |
| MRB0-086 |  | false | solver_signal_25 | unsat |  |
| MRB0-088 |  | false | solve_timeout | unsat |  |
| MRB0-089 |  | false | solve_timeout | unsat |  |
| MRB0-090 |  | false | solve_timeout | unsat |  |
| MRB0-094 |  | false | solve_timeout | sat |  |
| MRB0-099 |  | false | solve_timeout | unsat |  |
| MRB0-101 |  | false | solve_timeout | unsat |  |
| MRB0-103 |  | false | solve_timeout | unsat |  |
| MRB0-104 |  | false | solver_unknown | unsat |  |
| MRB0-105 |  | false | solve_timeout | unsat |  |
| MRB0-106 |  | false | solve_timeout | unsat |  |
| MRB0-107 |  | false | solver_unknown | unsat |  |
| MRB0-108 |  | false | solve_timeout | unsat |  |
| MRB0-120 |  | false | solve_timeout | unsat |  |
| MRB0-121 |  | false | solve_timeout | sat |  |
| MRB0-124 |  | false | solve_timeout | sat |  |
| MRB0-125 |  | false | solve_timeout | unsat |  |
| MRB0-129 |  | false | solve_timeout | unsat |  |
| MRB0-130 |  | false | solve_timeout | unsat |  |
| MRB0-144 |  | false | solve_timeout | unsat |  |
| MRB0-147 |  | false | solve_timeout | unsat |  |
| MRB0-149 |  | false | solve_timeout | sat |  |
| MRB0-150 |  | false | solve_timeout | unsat |  |
| MRB0-157 |  | false | solve_timeout | sat |  |
| MRB0-158 |  | false | solve_timeout | sat |  |
| MRB0-159 |  | false | solve_timeout | unsat |  |
| MRB0-161 |  | false | solve_timeout | unsat |  |
| MRB0-162 |  | false | solve_timeout | unsat |  |
| MRB0-163 |  | false | solve_timeout | unsat |  |
| MRB0-167 |  | false | solve_timeout | unsat |  |
| MRB0-168 |  | false | solve_timeout | unsat |  |
| MRB0-169 |  | false | solve_timeout | unsat |  |
| MRB0-182 |  | false | solver_unknown | unsat |  |
| MRB0-185 |  | false | solve_timeout | sat |  |
| MRB0-187 |  | false | solve_timeout | sat |  |
| MRB0-188 |  | false | solve_timeout | sat |  |
| MRB0-189 |  | false | solve_timeout | sat |  |
| MRB0-190 |  | false | solve_timeout | unsat |  |
| MRB0-191 |  | false | solve_timeout | unsat |  |
| MRB0-197 |  | false | solve_timeout | unsat |  |
| MRB0-203 |  | false | solve_timeout | sat |  |
| MRB0-204 |  | false | solve_timeout | sat |  |
| MRB0-206 |  | false | solve_timeout | sat |  |
| MRB0-209 |  | false | solve_timeout | sat |  |
| MRB0-210 |  | false | solve_timeout | sat |  |

