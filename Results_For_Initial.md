# Benchmark results for the teammate: Kissat (CPU) and PigWeedSAT (loader screen)

This file is self-contained: it explains how each tool was configured, what was
and wasn't run, the overall results, and one row per CNF. The same per-CNF
data, with extra columns (CPU time, proof-trace size, store usage, GBD download
link, SHA-256), is in `Benchmark/calibration/combined_results.csv`.

CSV column notes:
- `kissat_proof_trace_raw_MB`: Kissat was asked to write a proof trace on every run, including SAT runs and timeouts. Only rows whose `certificate` is "UNSAT DRAT proof verified" (71) hold a checked proof.
- `pigweed_solver_run=false` and `pigweed_result=not_run_loader_screen_only`: PigWeedSAT has no SAT/UNSAT answers or run times yet. The `pigweed_P*` and occupancy columns describe memory fit only.

**Read this first.** Two different things were done, on a MacBook (Apple M1 Max):

1. **Kissat, a CPU SAT solver, ran on all 210 CNFs** with a 1000 s limit
   each. It answered 149, and 148 of those answers were then checked
   independently, so we have trusted SAT/UNSAT ground truth plus a CPU
   difficulty reference.
2. **PigWeedSAT was not run as a solver.** No FPGA, no RTL simulation, no
   PigWeedSAT solve times. We ran only its host-side Python loader, the code
   that turns a CNF into the memory images the FPGA would receive, to see
   which CNFs fit the chip's fixed memory. PigWeedSAT results below are about
   fit, not speed.

## 1. Kissat configuration (CPU reference run)

| Item | Value |
|---|---|
| Solver | Kissat 4.0.4, commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2`, default configuration |
| Build | `./configure && make -j4`; Apple clang 21.0.0, `-O3 -DNDEBUG`; binary SHA-256 `2c139b29…bf40` |
| Command per CNF | `kissat --seed=0 --time=1000 input.cnf proof.drat` (binary DRAT proof written for every instance) |
| Time limit | 1000 s wall clock per CNF, enforced externally (SIGTERM, then SIGKILL 5 s later); late answers count as timeouts |
| Output cap | 8 GiB per output file; a proof reaching it kills Kissat, recorded as unresolved |
| Scheduling | Strictly sequential: one solver or checker process at a time, single seed |
| SAT check | Kissat's full model parsed strictly (every variable exactly once) and checked against the original CNF with `satbench.cnf.check_witness` |
| UNSAT check | `drat-trim input.cnf proof.drat -t 3000` (commit `2e3b2dc0…`, backward checking, 3000 s limit); certified only on an exact `s VERIFIED` |
| Machine | Apple M1 Max, 64 GiB RAM, macOS 26.6.2 (Darwin 25.6.0), Python 3.12.13 |
| Run period | 2026-10-09 23:15 to 2026-10-11 09:49 EDT (34 h 33 min elapsed). Summed solver wall time 23.0 h, checker 5.5 h; the rest was proof compression and I/O |

Timing caveats:
- "Kissat wall s" includes reading the input and writing the proof, sometimes gigabytes.
- It is one run with one seed.
- It is not proof-free solver speed, and it does not predict FPGA time.
- Kissat's memory figure is inflated about 1024× on macOS, so it is left out.

## 2. PigWeedSAT configuration (loader screen only)

| Item | Value |
|---|---|
| Code | Unchanged PigWeedSAT checkout: `satlat/host.py` SHA-256 `2e6e1039…bdf7`, `design.py` SHA-256 `38c3364e…2685` |
| What ran | `satlat.host.parse_dimacs` (PigWeedSAT's own CNF parser) and `satlat.host.build_images` (memory packing) for every CNF |
| Settings | `pigweed(Config(lit_page=P))`: P = 16 baseline (as used in PigWeedSAT's published Table3 results), also P = 8 and 4 for comparison |
| Other load-time settings (unchanged defaults) | reset_multiplier 100, positive_phase false, decay 0.95, prune 0.1, low_cls_pages 256, low_lit_pages 32, glue_buckets 1, used_bit true, min_abstract true, rephase 0 |
| Fixed hardware capacities (need a rebuild to change) | 2048 variables, 4096 clauses (original + learned), 16,384-word literal-occurrence store, 16,384-word clause-body store, 2048-entry answer stack, longest learned clause 1024 |
| Checks | Does PigWeedSAT's parser preserve the formula (all 210 do)? Does it fit the memories? Is the initial stack within 2048 entries? |
| Not done | No solving, no RTL simulation, no hardware build, no board use |

What P is:
- P is the page size, in words, of the literal-occurrence store. For each literal (x and ¬x), the chip keeps a list of the clauses containing it.
- Each page holds P−2 clause IDs plus 2 pointers.
- Large P wastes space on short lists; small P spends more of each page on pointers. That is why P = 8 fits 5 more CNFs than P = 16.
- P is a load-time register (`R_LITPAGE`), so the FPGA bitstream does not need rebuilding. But the CNF memory image must be packed with the same P that is written to the register; mixing them is invalid.
- P does not affect the clause-body store, which uses fixed 4-word pages.

Clock speed: the evaluation platform runs the design at 50 MHz, i.e. 50 million
cycles per second. FPGA time is cycles ÷ 50,000,000, so a 1000 s deadline is
50,000,000,000 cycles.

RTL simulation runs the real circuit cycle by cycle on a laptop, far slower than
50 MHz in real time. The existing cap of 2,000,000 simulated cycles equals only
0.04 s of FPGA time, so simulation is for short functional checks. Long timing
runs need the actual board.

## 3. Overall results

### Headline: how many CNFs Kissat verified
| Answer | Count | Share of the 148 verified | Share of all 210 |
|---|---|---|---|
| SAT (model checked against the CNF) | 77 | 77/148 = 52.0% | 77/210 = 36.7% |
| UNSAT (DRAT proof verified) | 71 | 71/148 = 48.0% | 71/210 = 33.8% |
| **Verified total** | **148** | 100% | **148/210 = 70.5%** |
| Unverified | 62 | – | 62/210 = 29.5% |

Against the GBD labels:
- 77 of the 99 expected-SAT CNFs were verified (77.8%).
- 71 of the 111 expected-UNSAT CNFs were verified (64.0%).
- No verified answer contradicts its label.

### Headline: how many CNFs the PigWeedSAT loader accepted
"Accepted" means PigWeedSAT's own host loader packed the CNF into the chip's
memories without refusing it, and nothing exceeds a fixed hardware field or
the answer stack. It says nothing about whether PigWeedSAT can solve the CNF.

| Group | CNFs | Accepted P=16 | Accepted P=8 | Accepted P=4 | Accepted P=16 and CPU-certified (FPGA-eligible) |
|---|---|---|---|---|---|
| S | 19 | 19 (100.0%) | 19 (100.0%) | 19 (100.0%) | 9 (47.4%) |
| S-tight | 71 | 69 (97.2%) | 71 (100.0%) | 69 (97.2%) | 59 (83.1%) |
| M-low | 68 | 0 (0.0%) | 3 (4.4%) | 0 (0.0%) | 0 (0.0%) |
| M-high | 52 | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| **All** | 210 | 88 (41.9%) | 93 (44.3%) | 88 (41.9%) | 68 (32.4%) |

- **Baseline P=16:** the loader accepts 88 of 210 (41.9%).
- **Certified and accepted:** 68 of the 148 verified CNFs (45.9%) are accepted at P=16. At the baseline P=16, these 68 (32.4% of 210) are the only ones that can get a validated FPGA answer later. At P=8 the figure would be 71.
- **P=8** accepts 93 (44.3%): everything P=16 accepts plus 5 more.
- **P=4** also accepts 88, but a different set. It refuses MRB0-026 (certified; P=16 accepts it) and accepts MRB0-039 (uncertified; P=16 refuses it), so only 67 certified CNFs are accepted at P=4.

### By tier
| Group | CNFs | Certified SAT | Certified UNSAT | Certified total | Unresolved | Median Kissat wall s (certified) | Median checker s (UNSAT) | PigWeed loads P=16 | PigWeed loads P=8 | FPGA-eligible (P=16) |
|---|---|---|---|---|---|---|---|---|---|---|
| S | 19 | 1 | 8 | 9 | 10 | 191.9 | 124.0 | 19 | 19 | 9 |
| S-tight | 71 | 33 | 27 | 60 | 11 | 1.8 | 17.8 | 69 | 71 | 59 |
| M-low | 68 | 27 | 20 | 47 | 21 | 69.4 | 130.0 | 0 | 3 | 0 |
| M-high | 52 | 16 | 16 | 32 | 20 | 104.9 | 86.1 | 0 | 0 | 0 |
| **All** | 210 | 77 | 71 | 148 | 62 | 39.3 | 75.5 | 88 | 93 | 68 |

### By expected answer (GBD label)
| Group | CNFs | Certified SAT | Certified UNSAT | Certified total | Unresolved | Median Kissat wall s (certified) | Median checker s (UNSAT) | PigWeed loads P=16 | PigWeed loads P=8 | FPGA-eligible (P=16) |
|---|---|---|---|---|---|---|---|---|---|---|
| expected SAT | 99 | 77 | 0 | 77 | 22 | 21.5 | – | 40 | 42 | 33 |
| expected UNSAT | 111 | 0 | 71 | 71 | 40 | 55.3 | 75.5 | 48 | 51 | 35 |

"FPGA-eligible" means the CNF loads at P = 16 and has a CPU certificate. Only
these can get a validated FPGA answer and timing later.

### Kissat difficulty spread (certified CNFs)
| Kissat wall time | Certified CNFs | of which FPGA-eligible |
|---|---|---|
| < 0.1 s | 14 | 9 |
| 0.1–1 s | 23 | 18 |
| 1–10 s | 16 | 13 |
| 10–100 s | 43 | 12 |
| 100–1000 s | 52 | 16 |
| unresolved (no certificate) | 62 | – |

### Unresolved CNFs (62)
| Reason | Count |
|---|---|
| Kissat timed out at 1000 s | 54 |
| Kissat stopped itself at its own `--time=1000` limit a moment before our timer (exit 0, `s UNKNOWN`), so effectively a timeout | 5 |
| Killed: proof exceeded 8 GiB (MRB0-019, MRB0-086) | 2 |
| UNSAT claimed, but the proof check hit 3000 s (MRB0-037) | 1 |

No unresolved CNF inherits the GBD label. All 148 certified answers agree with
the GBD labels (0 conflicts).

### Unverified CNFs (62) by tier
| Tier | Unverified | Share of the 62 | Share of its tier | Expected SAT / UNSAT | Reasons | Loads at P=16 | Loads at P=8 |
|---|---|---|---|---|---|---|---|
| S | 10 | 16.1% | 52.6% of 19 | 6 / 4 | 7 timeout, 2 unknown, 1 proof too large | 10 | 10 |
| S-tight | 11 | 17.7% | 15.5% of 71 | 1 / 10 | 9 timeout, 1 proof check timed out, 1 proof too large | 10 | 11 |
| M-low | 21 | 33.9% | 30.9% of 68 | 6 / 15 | 19 timeout, 2 unknown | 0 | 1 |
| M-high | 20 | 32.3% | 38.5% of 52 | 9 / 11 | 19 timeout, 1 unknown | 0 | 0 |
| **Total** | **62** | 100% | 29.5% of 210 | **22 / 40** | 54 timeout, 5 unknown, 2 proof too large, 1 proof check timed out | 20 | 22 |

- **S is proportionally the hardest tier:** 52.6% of it is unverified, mostly the small but hard `sgen` family.
- **M-tier holds 41 of the 62 unverified.**
- **Only 20 unverified CNFs are accepted by the loader at P=16.** These are the S and S-tight ones that fit the chip but have no certified answer to validate an FPGA result against.
- **At P=8 that rises to 22:** S-tight MRB0-039 and M-low MRB0-108 also load. So M-tier is not entirely irrelevant to FPGA testing if a global P=8 setting were approved.

### PigWeedSAT fit at P = 16
- 88 of 210 load; 68 of those are CPU-certified (FPGA-eligible).
- 122 do not load: too many clauses (85), too many variables (15), clause-body store full (12), literal store full (10).
- No M-low or M-high CNF loads at P = 16. At P = 8, three M-low CNFs load (MRB0-096, -102, -108), all at 92–99% initial occupancy, leaving almost no room for learned clauses.

### Suggested pilot CNFs for a first FPGA/RTL test
Rule: within each tier, the fastest certified SAT, the fastest certified UNSAT,
and the fullest initial memory, among FPGA-eligible CNFs. M-low and M-high have
no eligible CNFs.

| ID | Tier | Kissat result | Kissat wall s | P = 16 initial occupancy |
|---|---|---|---|---|
| MRB0-005 | S | UNSAT, certified | 78.946 | 0.416 |
| MRB0-011 | S | SAT, certified | 906.222 | 0.391 |
| MRB0-017 | S | UNSAT, certified | 0.353 | 0.193 |
| MRB0-026 | S-tight | UNSAT, certified | 33.550 | 0.984 |
| MRB0-077 | S-tight | SAT, certified | 0.021 | 0.561 |
| MRB0-078 | S-tight | UNSAT, certified | 0.022 | 0.500 |

## 4. Per-CNF results (all 210)

"Checker s" is the drat-trim proof-check time for UNSAT answers (SAT models are
checked in milliseconds). "–" means no proof check was run.

| ID | Tier | Family | Vars | Clauses | Expected (GBD) | Kissat result | Kissat wall s | Checker s | PigWeed P=16 | PigWeed P=8 | FPGA-eligible |
|---|---|---|---|---|---|---|---|---|---|---|---|
| MRB0-001 | S | long-learned-clauses | 190 | 632 | UNSAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-002 | S | pigeon-hole | 90 | 415 | UNSAT | UNSAT, certified | 1.75 | 2.64 | loads | loads | yes |
| MRB0-003 | S | sgen | 101 | 212 | UNSAT | timeout (1000 s) | 1000.02 | – | loads | loads | no |
| MRB0-004 | S | sgen | 230 | 552 | SAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-005 (pilot) | S | sgen | 216 | 285 | UNSAT | UNSAT, certified | 78.95 | 153.76 | loads | loads | yes |
| MRB0-006 | S | sgen | 240 | 576 | SAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-007 | S | sgen | 121 | 252 | UNSAT | timeout (1000 s) | 1000.03 | – | loads | loads | no |
| MRB0-008 | S | sgen | 260 | 624 | SAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-009 | S | sgen | 180 | 432 | SAT | unknown at ~1000 s | 1000.01 | – | loads | loads | no |
| MRB0-010 | S | sgen | 270 | 648 | SAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-011 (pilot) | S | sgen | 200 | 480 | SAT | SAT, certified | 906.22 | – | loads | loads | yes |
| MRB0-012 | S | sgen | 250 | 600 | SAT | unknown at ~1000 s | 1000.01 | – | loads | loads | no |
| MRB0-013 | S | subset-cardinality | 133 | 542 | UNSAT | UNSAT, certified | 504.67 | 406.39 | loads | loads | yes |
| MRB0-014 | S | subset-cardinality | 169 | 685 | UNSAT | UNSAT, certified | 191.87 | 94.16 | loads | loads | yes |
| MRB0-015 | S | subset-cardinality | 129 | 526 | UNSAT | UNSAT, certified | 805.67 | 1054.27 | loads | loads | yes |
| MRB0-016 | S | subset-cardinality | 161 | 654 | UNSAT | UNSAT, certified | 342.34 | 186.82 | loads | loads | yes |
| MRB0-017 (pilot) | S | tseitin-formulas | 99 | 264 | UNSAT | UNSAT, certified | 0.35 | 0.75 | loads | loads | yes |
| MRB0-018 | S | tseitin-formulas | 45 | 376 | UNSAT | UNSAT, certified | 0.53 | 1.05 | loads | loads | yes |
| MRB0-019 | S | tseitin-formulas | 237 | 632 | UNSAT | killed: proof > 8 GiB | 976.00 | – | loads | loads | no |
| MRB0-020 | S-tight | battleship | 169 | 1183 | UNSAT | UNSAT, certified | 12.64 | 17.79 | loads | loads | yes |
| MRB0-021 | S-tight | binary-tree-parity | 511 | 2039 | SAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-022 | S-tight | cardinality-constraints | 400 | 1737 | UNSAT | UNSAT, certified | 27.84 | 33.44 | loads | loads | yes |
| MRB0-023 | S-tight | clique-formulas | 180 | 3160 | UNSAT | UNSAT, certified | 5.51 | 9.13 | loads | loads | yes |
| MRB0-024 | S-tight | coloring | 240 | 1026 | SAT | SAT, certified | 0.25 | – | loads | loads | yes |
| MRB0-025 | S-tight | coloring | 190 | 1375 | UNSAT | UNSAT, certified | 5.31 | 7.91 | loads | loads | yes |
| MRB0-026 (pilot) | S-tight | coloring | 276 | 2838 | UNSAT | UNSAT, certified | 33.55 | 48.50 | loads | loads | yes |
| MRB0-027 | S-tight | coloring | 184 | 2200 | UNSAT | UNSAT, certified | 0.20 | 0.13 | loads | loads | yes |
| MRB0-028 | S-tight | coloring | 132 | 1527 | UNSAT | UNSAT, certified | 0.66 | 0.67 | loads | loads | yes |
| MRB0-029 | S-tight | fpga-routing | 220 | 1122 | UNSAT | UNSAT, certified | 41.10 | 83.79 | loads | loads | yes |
| MRB0-030 | S-tight | fpga-routing | 308 | 2030 | UNSAT | UNSAT, certified | 298.95 | 559.53 | loads | loads | yes |
| MRB0-031 | S-tight | hamiltonian | 350 | 3147 | SAT | SAT, certified | 0.08 | – | literal store full | loads | no |
| MRB0-032 | S-tight | hamiltonian | 300 | 2696 | SAT | SAT, certified | 0.38 | – | loads | loads | yes |
| MRB0-033 | S-tight | hamiltonian | 300 | 2698 | SAT | SAT, certified | 0.09 | – | loads | loads | yes |
| MRB0-034 | S-tight | hgen | 320 | 1120 | SAT | SAT, certified | 1.29 | – | loads | loads | yes |
| MRB0-035 | S-tight | hgen | 322 | 1127 | SAT | SAT, certified | 1.41 | – | loads | loads | yes |
| MRB0-036 | S-tight | hgen | 320 | 1120 | SAT | SAT, certified | 542.77 | – | loads | loads | yes |
| MRB0-037 | S-tight | linvrinv | 450 | 1426 | UNSAT | UNSAT claimed; proof check timed out | 932.44 | 2824.05 | loads | loads | no |
| MRB0-038 | S-tight | miter | 162 | 774 | UNSAT | UNSAT, certified | 74.98 | 149.49 | loads | loads | yes |
| MRB0-039 | S-tight | mutilated-chessboard | 544 | 1815 | UNSAT | timeout (1000 s) | 1000.01 | – | literal store full | loads | no |
| MRB0-040 | S-tight | mutilated-chessboard | 480 | 1596 | UNSAT | UNSAT, certified | 239.80 | 444.94 | loads | loads | yes |
| MRB0-041 | S-tight | mutilated-chessboard | 420 | 1391 | UNSAT | UNSAT, certified | 41.14 | 65.69 | loads | loads | yes |
| MRB0-042 | S-tight | pigeon-hole | 240 | 3496 | UNSAT | timeout (1000 s) | 1000.02 | – | loads | loads | no |
| MRB0-043 | S-tight | random | 400 | 2199 | SAT | SAT, certified | 0.36 | – | loads | loads | yes |
| MRB0-044 | S-tight | random | 440 | 2289 | SAT | SAT, certified | 2.60 | – | loads | loads | yes |
| MRB0-045 | S-tight | random | 280 | 1203 | SAT | SAT, certified | 0.08 | – | loads | loads | yes |
| MRB0-046 | S-tight | random | 300 | 1649 | SAT | SAT, certified | 0.34 | – | loads | loads | yes |
| MRB0-047 | S-tight | random | 400 | 1720 | SAT | SAT, certified | 0.13 | – | loads | loads | yes |
| MRB0-048 | S-tight | random | 400 | 1720 | SAT | SAT, certified | 0.13 | – | loads | loads | yes |
| MRB0-049 | S-tight | random | 400 | 2081 | SAT | SAT, certified | 11.99 | – | loads | loads | yes |
| MRB0-050 | S-tight | random | 300 | 1290 | SAT | SAT, certified | 0.09 | – | loads | loads | yes |
| MRB0-051 | S-tight | random | 340 | 1462 | SAT | SAT, certified | 0.41 | – | loads | loads | yes |
| MRB0-052 | S-tight | random | 440 | 1891 | SAT | SAT, certified | 0.09 | – | loads | loads | yes |
| MRB0-053 | S-tight | random-graph-xorsat | 280 | 1120 | SAT | SAT, certified | 281.73 | – | loads | loads | yes |
| MRB0-054 | S-tight | random-graph-xorsat | 250 | 1000 | SAT | SAT, certified | 147.68 | – | loads | loads | yes |
| MRB0-055 | S-tight | random-graph-xorsat | 230 | 920 | SAT | SAT, certified | 93.24 | – | loads | loads | yes |
| MRB0-056 | S-tight | random-graph-xorsat | 270 | 1080 | SAT | SAT, certified | 475.53 | – | loads | loads | yes |
| MRB0-057 | S-tight | random-planted-solution | 240 | 1249 | SAT | SAT, certified | 0.08 | – | loads | loads | yes |
| MRB0-058 | S-tight | random-planted-solution | 260 | 1118 | SAT | SAT, certified | 0.35 | – | loads | loads | yes |
| MRB0-059 | S-tight | random-planted-solution | 350 | 1543 | SAT | SAT, certified | 62.12 | – | loads | loads | yes |
| MRB0-060 | S-tight | random-planted-solution | 480 | 2064 | SAT | SAT, certified | 1.30 | – | loads | loads | yes |
| MRB0-061 | S-tight | random-planted-solution | 360 | 1874 | SAT | SAT, certified | 0.65 | – | loads | loads | yes |
| MRB0-062 | S-tight | random-planted-solution | 260 | 1353 | SAT | SAT, certified | 0.13 | – | loads | loads | yes |
| MRB0-063 | S-tight | random-planted-solution | 340 | 1770 | SAT | SAT, certified | 5.54 | – | loads | loads | yes |
| MRB0-064 | S-tight | random-planted-solution | 450 | 1984 | SAT | SAT, certified | 606.53 | – | loads | loads | yes |
| MRB0-065 | S-tight | random-planted-solution | 300 | 1290 | SAT | SAT, certified | 0.29 | – | loads | loads | yes |
| MRB0-066 | S-tight | random-planted-solution | 240 | 1032 | SAT | SAT, certified | 0.14 | – | loads | loads | yes |
| MRB0-067 | S-tight | register-allocation | 176 | 1149 | UNSAT | UNSAT, certified | 1.33 | 1.88 | loads | loads | yes |
| MRB0-068 | S-tight | register-allocation | 228 | 2023 | UNSAT | UNSAT, certified | 12.14 | 18.68 | loads | loads | yes |
| MRB0-069 | S-tight | register-allocation | 247 | 2073 | UNSAT | UNSAT, certified | 165.89 | 298.51 | loads | loads | yes |
| MRB0-070 | S-tight | register-allocation | 187 | 1348 | UNSAT | UNSAT, certified | 0.35 | 0.36 | loads | loads | yes |
| MRB0-071 | S-tight | register-allocation | 288 | 3240 | UNSAT | UNSAT, certified | 2.15 | 1.58 | loads | loads | yes |
| MRB0-072 | S-tight | register-allocation | 228 | 1915 | UNSAT | UNSAT, certified | 0.86 | 0.99 | loads | loads | yes |
| MRB0-073 | S-tight | register-allocation | 231 | 1880 | UNSAT | UNSAT, certified | 4.38 | 7.92 | loads | loads | yes |
| MRB0-074 | S-tight | register-allocation | 252 | 2049 | UNSAT | UNSAT, certified | 59.92 | 157.68 | loads | loads | yes |
| MRB0-075 | S-tight | register-allocation | 192 | 1252 | UNSAT | UNSAT, certified | 4.35 | 5.55 | loads | loads | yes |
| MRB0-076 | S-tight | register-allocation | 299 | 3182 | UNSAT | UNSAT, certified | 6.61 | 9.17 | loads | loads | yes |
| MRB0-077 (pilot) | S-tight | scheduling | 252 | 1163 | SAT | SAT, certified | 0.02 | – | loads | loads | yes |
| MRB0-078 (pilot) | S-tight | scheduling | 221 | 1085 | UNSAT | UNSAT, certified | 0.02 | 0.04 | loads | loads | yes |
| MRB0-079 | S-tight | scheduling | 227 | 1106 | SAT | SAT, certified | 0.02 | – | loads | loads | yes |
| MRB0-080 | S-tight | scheduling | 210 | 1420 | UNSAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-081 | S-tight | sgen-balanced | 201 | 707 | UNSAT | UNSAT, certified | 398.78 | 250.37 | loads | loads | yes |
| MRB0-082 | S-tight | sudoku-php | 210 | 2850 | UNSAT | timeout (1000 s) | 1000.02 | – | loads | loads | no |
| MRB0-083 | S-tight | theorem-proving | 398 | 741 | UNSAT | UNSAT, certified | 0.03 | 0.08 | loads | loads | yes |
| MRB0-084 | S-tight | tseitin-formulas | 409 | 1520 | UNSAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-085 | S-tight | tseitin-formulas | 264 | 968 | UNSAT | UNSAT, certified | 385.46 | 1003.39 | loads | loads | yes |
| MRB0-086 | S-tight | tseitin-formulas | 294 | 784 | UNSAT | killed: proof > 8 GiB | 912.94 | – | loads | loads | no |
| MRB0-087 | S-tight | tseitin-formulas | 74 | 694 | UNSAT | UNSAT, certified | 205.77 | 1132.97 | loads | loads | yes |
| MRB0-088 | S-tight | tseitin-formulas | 243 | 648 | UNSAT | timeout (1000 s) | 1000.01 | – | loads | loads | no |
| MRB0-089 | S-tight | tseitin-formulas | 288 | 768 | UNSAT | timeout (1000 s) | 1000.02 | – | loads | loads | no |
| MRB0-090 | S-tight | tseitin-formulas | 114 | 888 | UNSAT | timeout (1000 s) | 1000.02 | – | loads | loads | no |
| MRB0-091 | M-low | automata-synchronization | 1287 | 2332 | UNSAT | UNSAT, certified | 1.13 | 0.30 | literal store full | literal store full | no |
| MRB0-092 | M-low | battleship | 364 | 2562 | SAT | SAT, certified | 9.80 | – | clause store full | clause store full | no |
| MRB0-093 | M-low | battleship | 496 | 3976 | SAT | SAT, certified | 0.31 | – | clause store full | clause store full | no |
| MRB0-094 | M-low | binary-tree-parity | 1023 | 4088 | SAT | timeout (1000 s) | 1000.02 | – | literal store full | literal store full | no |
| MRB0-095 | M-low | cardinality-constraints | 1672 | 5207 | SAT | SAT, certified | 235.16 | – | too many clauses | too many clauses | no |
| MRB0-096 | M-low | cardinality-constraints | 851 | 2731 | UNSAT | UNSAT, certified | 393.78 | 618.00 | literal store full | loads | no |
| MRB0-097 | M-low | cardinality-constraints | 1672 | 5262 | SAT | SAT, certified | 10.10 | – | too many clauses | too many clauses | no |
| MRB0-098 | M-low | cardinality-constraints | 647 | 3239 | SAT | SAT, certified | 14.78 | – | literal store full | literal store full | no |
| MRB0-099 | M-low | coloring | 351 | 6747 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-100 | M-low | coloring | 1381 | 5521 | SAT | SAT, certified | 0.27 | – | too many clauses | too many clauses | no |
| MRB0-101 | M-low | coloring | 1621 | 6482 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-102 | M-low | coloring | 360 | 3109 | SAT | SAT, certified | 0.09 | – | literal store full | loads | no |
| MRB0-103 | M-low | coloring-clique | 270 | 6663 | UNSAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-104 | M-low | coloring-clique | 328 | 7199 | UNSAT | unknown at ~1000 s | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-105 | M-low | count | 300 | 6925 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-106 | M-low | count | 210 | 4011 | UNSAT | timeout (1000 s) | 1000.02 | – | clause store full | clause store full | no |
| MRB0-107 | M-low | datapath-equivalence-checking | 979 | 3169 | UNSAT | unknown at ~1000 s | 1000.01 | – | literal store full | literal store full | no |
| MRB0-108 | M-low | datapath-equivalence-checking | 644 | 2619 | UNSAT | timeout (1000 s) | 1000.01 | – | literal store full | loads | no |
| MRB0-109 | M-low | fpga-routing | 440 | 4220 | UNSAT | UNSAT, certified | 39.50 | 58.30 | too many clauses | too many clauses | no |
| MRB0-110 | M-low | generic-csp | 556 | 6427 | SAT | SAT, certified | 0.19 | – | too many clauses | too many clauses | no |
| MRB0-111 | M-low | grandtour-puzzle | 1043 | 3649 | UNSAT | UNSAT, certified | 37.05 | 72.68 | clause store full | clause store full | no |
| MRB0-112 | M-low | greentao | 509 | 4478 | SAT | SAT, certified | 120.10 | – | too many clauses | too many clauses | no |
| MRB0-113 | M-low | hamiltonian | 500 | 4496 | SAT | SAT, certified | 18.03 | – | too many clauses | too many clauses | no |
| MRB0-114 | M-low | hamiltonian | 550 | 4941 | SAT | SAT, certified | 269.50 | – | too many clauses | too many clauses | no |
| MRB0-115 | M-low | hamiltonian | 500 | 4506 | SAT | SAT, certified | 39.14 | – | too many clauses | too many clauses | no |
| MRB0-116 | M-low | hamiltonian | 600 | 5395 | SAT | SAT, certified | 455.17 | – | too many clauses | too many clauses | no |
| MRB0-117 | M-low | hamiltonian | 600 | 5392 | SAT | SAT, certified | 84.63 | – | too many clauses | too many clauses | no |
| MRB0-118 | M-low | hamiltonian | 500 | 4502 | UNSAT | UNSAT, certified | 69.43 | 75.53 | too many clauses | too many clauses | no |
| MRB0-119 | M-low | hamiltonian | 500 | 4511 | UNSAT | UNSAT, certified | 56.20 | 61.59 | too many clauses | too many clauses | no |
| MRB0-120 | M-low | mechanical-master-key | 3432 | 6248 | UNSAT | timeout (1000 s) | 1000.01 | – | too many variables | too many variables | no |
| MRB0-121 | M-low | minimal-disagreement-parity | 1333 | 5326 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-122 | M-low | minimum-disagreement-parity | 792 | 4386 | SAT | SAT, certified | 659.09 | – | too many clauses | too many clauses | no |
| MRB0-123 | M-low | minimum-disagreement-parity | 757 | 4270 | UNSAT | UNSAT, certified | 740.88 | 1278.47 | too many clauses | too many clauses | no |
| MRB0-124 | M-low | minimum-disagreement-parity | 1033 | 5806 | SAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-125 | M-low | minimum-disagreement-parity | 985 | 5614 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-126 | M-low | minimum-disagreement-parity | 799 | 4438 | SAT | SAT, certified | 110.52 | – | too many clauses | too many clauses | no |
| MRB0-127 | M-low | miter | 2780 | 8297 | UNSAT | UNSAT, certified | 383.01 | 784.99 | too many variables | too many variables | no |
| MRB0-128 | M-low | miter | 2958 | 8709 | UNSAT | UNSAT, certified | 55.35 | 90.43 | too many variables | too many variables | no |
| MRB0-129 | M-low | multiplier-circuit-miters | 2365 | 7607 | UNSAT | timeout (1000 s) | 1000.01 | – | too many variables | too many variables | no |
| MRB0-130 | M-low | multiplier-circuit-miters | 1033 | 3309 | UNSAT | timeout (1000 s) | 1000.02 | – | literal store full | literal store full | no |
| MRB0-131 | M-low | mutilated-chessboard | 16278 | 988 | UNSAT | UNSAT, certified | 32.90 | 52.52 | too many variables | too many variables | no |
| MRB0-132 | M-low | mutilated-chessboard | 16278 | 965 | UNSAT | UNSAT, certified | 89.51 | 144.92 | too many variables | too many variables | no |
| MRB0-133 | M-low | philips | 3641 | 4456 | UNSAT | UNSAT, certified | 83.54 | 136.18 | too many variables | too many variables | no |
| MRB0-134 | M-low | pigeon-hole | 460 | 8655 | UNSAT | UNSAT, certified | 153.54 | 268.77 | too many clauses | too many clauses | no |
| MRB0-135 | M-low | pigeon-hole | 136 | 5457 | UNSAT | UNSAT, certified | 390.05 | 852.93 | too many clauses | too many clauses | no |
| MRB0-136 | M-low | planning | 439 | 5423 | SAT | SAT, certified | 0.05 | – | too many clauses | too many clauses | no |
| MRB0-137 | M-low | planning | 1178 | 6182 | SAT | SAT, certified | 0.05 | – | too many clauses | too many clauses | no |
| MRB0-138 | M-low | random-graph-xorsat | 339 | 2416 | SAT | SAT, certified | 61.46 | – | clause store full | clause store full | no |
| MRB0-139 | M-low | random-graph-xorsat | 354 | 2596 | SAT | SAT, certified | 36.10 | – | clause store full | clause store full | no |
| MRB0-140 | M-low | random-graph-xorsat | 349 | 2416 | SAT | SAT, certified | 19.36 | – | clause store full | clause store full | no |
| MRB0-141 | M-low | random-graph-xorsat | 352 | 2492 | SAT | SAT, certified | 111.35 | – | clause store full | clause store full | no |
| MRB0-142 | M-low | random-graph-xorsat | 338 | 2376 | SAT | SAT, certified | 184.35 | – | clause store full | clause store full | no |
| MRB0-143 | M-low | relativized-pigeon-hole | 400 | 3765 | UNSAT | UNSAT, certified | 527.94 | 824.41 | clause store full | clause store full | no |
| MRB0-144 | M-low | relativized-pigeon-hole | 450 | 4685 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-145 | M-low | scheduling | 1101 | 5037 | UNSAT | UNSAT, certified | 0.51 | 0.45 | too many clauses | too many clauses | no |
| MRB0-146 | M-low | scheduling | 1516 | 6802 | UNSAT | UNSAT, certified | 18.58 | 30.92 | too many clauses | too many clauses | no |
| MRB0-147 | M-low | scheduling | 733 | 9175 | UNSAT | timeout (1000 s) | 1000.03 | – | too many clauses | too many clauses | no |
| MRB0-148 | M-low | st-connectivity-principle | 936 | 6488 | UNSAT | UNSAT, certified | 217.80 | 123.83 | too many clauses | too many clauses | no |
| MRB0-149 | M-low | stable-semantics | 540 | 7044 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-150 | M-low | sudoku-php | 380 | 7050 | UNSAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-151 | M-low | unknown-cases | 600 | 5405 | SAT | SAT, certified | 426.56 | – | too many clauses | too many clauses | no |
| MRB0-152 | M-low | unknown-cases | 550 | 4949 | SAT | SAT, certified | 21.52 | – | too many clauses | too many clauses | no |
| MRB0-153 | M-low | unknown-cases | 600 | 5404 | SAT | SAT, certified | 193.08 | – | too many clauses | too many clauses | no |
| MRB0-154 | M-low | unknown-cases | 500 | 4502 | SAT | SAT, certified | 73.54 | – | too many clauses | too many clauses | no |
| MRB0-155 | M-low | van-der-waerden | 218 | 3080 | UNSAT | UNSAT, certified | 174.51 | 382.41 | clause store full | clause store full | no |
| MRB0-156 | M-low | van-der-waerden | 220 | 3136 | UNSAT | UNSAT, certified | 193.93 | 412.15 | clause store full | clause store full | no |
| MRB0-157 | M-low | xor-shifting | 1773 | 6618 | SAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-158 | M-low | xor-shifting | 1866 | 6990 | SAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-159 | M-high | binary-pigeon-hole | 115 | 5796 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-160 | M-high | clustered-random | 1100 | 7545 | UNSAT | UNSAT, certified | 127.32 | 107.00 | too many clauses | too many clauses | no |
| MRB0-161 | M-high | coloring | 299 | 7796 | UNSAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-162 | M-high | coloring-clique | 329 | 9018 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-163 | M-high | coloring-clique | 387 | 9088 | UNSAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-164 | M-high | cryptography | 528 | 5016 | SAT | SAT, certified | 864.17 | – | too many clauses | too many clauses | no |
| MRB0-165 | M-high | cryptography | 970 | 5432 | UNSAT | UNSAT, certified | 220.16 | 324.16 | too many clauses | too many clauses | no |
| MRB0-166 | M-high | cryptography | 974 | 5505 | UNSAT | UNSAT, certified | 437.66 | 737.66 | too many clauses | too many clauses | no |
| MRB0-167 | M-high | datapath-equivalence-checking | 1757 | 7469 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-168 | M-high | datapath-equivalence-checking | 1757 | 7468 | UNSAT | timeout (1000 s) | 1000.03 | – | too many clauses | too many clauses | no |
| MRB0-169 | M-high | exam-scheduling | 336 | 10430 | UNSAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-170 | M-high | generic-csp | 568 | 7150 | UNSAT | UNSAT, certified | 17.58 | 21.18 | too many clauses | too many clauses | no |
| MRB0-171 | M-high | graph-coloring | 2520 | 8297 | UNSAT | UNSAT, certified | 16.97 | 15.79 | too many variables | too many variables | no |
| MRB0-172 | M-high | heule-nol | 1419 | 7823 | SAT | SAT, certified | 107.48 | – | too many clauses | too many clauses | no |
| MRB0-173 | M-high | heule-nol | 1419 | 7821 | SAT | SAT, certified | 229.78 | – | too many clauses | too many clauses | no |
| MRB0-174 | M-high | heule-nol | 1419 | 7829 | SAT | SAT, certified | 344.25 | – | too many clauses | too many clauses | no |
| MRB0-175 | M-high | heule-nol | 1419 | 7835 | SAT | SAT, certified | 23.74 | – | too many clauses | too many clauses | no |
| MRB0-176 | M-high | heule-nol | 1419 | 7831 | SAT | SAT, certified | 152.69 | – | too many clauses | too many clauses | no |
| MRB0-177 | M-high | heule-nol | 1419 | 7825 | SAT | SAT, certified | 578.30 | – | too many clauses | too many clauses | no |
| MRB0-178 | M-high | heule-nol | 1419 | 7837 | SAT | SAT, certified | 25.68 | – | too many clauses | too many clauses | no |
| MRB0-179 | M-high | hidoku | 1908 | 6232 | UNSAT | UNSAT, certified | 43.63 | 50.00 | too many clauses | too many clauses | no |
| MRB0-180 | M-high | hidoku | 1908 | 6232 | UNSAT | UNSAT, certified | 37.29 | 47.31 | too many clauses | too many clauses | no |
| MRB0-181 | M-high | hidoku | 1908 | 6232 | UNSAT | UNSAT, certified | 65.91 | 85.03 | too many clauses | too many clauses | no |
| MRB0-182 | M-high | lights-out | 2475 | 8172 | UNSAT | unknown at ~1000 s | 1000.02 | – | too many variables | too many variables | no |
| MRB0-183 | M-high | lights-out | 484 | 7056 | SAT | SAT, certified | 83.51 | – | too many clauses | too many clauses | no |
| MRB0-184 | M-high | lights-out | 2279 | 7529 | UNSAT | UNSAT, certified | 192.81 | 87.25 | too many variables | too many variables | no |
| MRB0-185 | M-high | minimum-disagreement-parity | 1302 | 7382 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-186 | M-high | minimum-disagreement-parity | 1042 | 5874 | SAT | SAT, certified | 70.03 | – | too many clauses | too many clauses | no |
| MRB0-187 | M-high | minimum-disagreement-parity | 1304 | 7406 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-188 | M-high | minimum-disagreement-parity | 1294 | 7346 | SAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-189 | M-high | minimum-disagreement-parity | 1300 | 7390 | SAT | timeout (1000 s) | 1000.01 | – | too many clauses | too many clauses | no |
| MRB0-190 | M-high | multiplier-circuit-miters | 2565 | 8255 | UNSAT | timeout (1000 s) | 1000.01 | – | too many variables | too many variables | no |
| MRB0-191 | M-high | multiplier-equivalence-checking | 2540 | 8495 | UNSAT | timeout (1000 s) | 1000.01 | – | too many variables | too many variables | no |
| MRB0-192 | M-high | multiplier-equivalence-checking | 2575 | 8611 | UNSAT | UNSAT, certified | 366.39 | 614.88 | too many variables | too many variables | no |
| MRB0-193 | M-high | or_randxor | 1040 | 6991 | UNSAT | UNSAT, certified | 0.98 | 0.94 | too many clauses | too many clauses | no |
| MRB0-194 | M-high | or_randxor | 1080 | 7287 | UNSAT | UNSAT, certified | 11.10 | 13.97 | too many clauses | too many clauses | no |
| MRB0-195 | M-high | prime-factoring | 1201 | 6563 | SAT | SAT, certified | 6.14 | – | too many clauses | too many clauses | no |
| MRB0-196 | M-high | product-configuration | 1805 | 7334 | UNSAT | UNSAT, certified | 0.01 | 0.05 | too many clauses | too many clauses | no |
| MRB0-197 | M-high | relativized-pigeon-hole | 800 | 7850 | UNSAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-198 | M-high | relativized-pigeon-hole | 560 | 8019 | UNSAT | UNSAT, certified | 102.25 | 185.78 | too many clauses | too many clauses | no |
| MRB0-199 | M-high | uniform-random | 250 | 5279 | SAT | SAT, certified | 50.77 | – | too many clauses | too many clauses | no |
| MRB0-200 | M-high | uniform-random | 250 | 5279 | SAT | SAT, certified | 899.63 | – | too many clauses | too many clauses | no |
| MRB0-201 | M-high | uniform-random | 250 | 5279 | SAT | SAT, certified | 49.74 | – | too many clauses | too many clauses | no |
| MRB0-202 | M-high | uniform-random | 250 | 5279 | SAT | SAT, certified | 877.50 | – | too many clauses | too many clauses | no |
| MRB0-203 | M-high | uniform-random | 250 | 5279 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-204 | M-high | uniform-random | 250 | 5279 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-205 | M-high | uniform-random | 360 | 7602 | SAT | SAT, certified | 130.27 | – | too many clauses | too many clauses | no |
| MRB0-206 | M-high | van-der-waerden | 290 | 5152 | SAT | timeout (1000 s) | 1000.02 | – | too many clauses | too many clauses | no |
| MRB0-207 | M-high | van-der-waerden | 320 | 7628 | UNSAT | UNSAT, certified | 531.56 | 1155.38 | too many clauses | too many clauses | no |
| MRB0-208 | M-high | van-der-waerden | 322 | 7723 | UNSAT | UNSAT, certified | 555.50 | 1096.78 | too many clauses | too many clauses | no |
| MRB0-209 | M-high | xor-shifting | 2273 | 8366 | SAT | timeout (1000 s) | 1000.02 | – | too many variables | too many variables | no |
| MRB0-210 | M-high | xor-shifting | 2087 | 7622 | SAT | timeout (1000 s) | 1000.02 | – | too many variables | too many variables | no |

## 5. Source artifacts
- `Benchmark/manifest.csv`: the 210 CNFs, GBD download URLs, SHA-256 of each file. File SHA-256 `23305e51e46e326b1bd150b97190dcac99e4b3030e3a6a0cbc691932d97315f6`.
- `Benchmark/calibration/cpu-v0/results.csv` (SHA-256 `edddaa9bdf1ac349d138c2e875d11a2a554c99d71458dc6f544f139a287d26d6`), `summary.json`, `run.json`, `report.md`: Kissat campaign results and provenance.
- `Benchmark/calibration/pigweed-v0/rows.csv` (SHA-256 `7e2b96535debcad89cc1f7bc2de78da8370b3ed34e69b18dfb0b4f8b747dde2b`), `summary.json`, `run.json`: loader screen, 210 CNFs × P = 4, 8, 16.
- `Benchmark/calibration/combined_results.csv` (SHA-256 `ee9b244b44f1eb30aa8ccc353eec441e8ce7251d625d5075225f0824dd235215`): the per-CNF table above, joined from the three files listed here by CNF ID. If any of these hashes differ from your copy, this report is stale.
- `Benchmark/FPGA_Readiness_Plan.md`, `Benchmark/Calibration_Insights.md`: protocol, gates, next steps, Q&A.

Proofs, witnesses and per-run logs stay on the original machine (the proofs
total about 87 GB compressed). The CNFs can be downloaded from GBD by URL and
checked against `cnf_sha256`.
