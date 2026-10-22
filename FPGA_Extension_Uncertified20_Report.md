# Extension: 20 chip-fitting, CPU-uncertified instances (5,000 s CPU / 2,600 s FPGA)

**Status (2026-10-22 14:45Z): COMPLETE.** CPU phase: 5 of 20 newly
certified. FPGA phase on those 5: 1 solved (MRB0-009, SAT). This report covers
the extension only. The original campaign's results are unchanged: see
`Benchmark/FPGA_Readiness_Plan.md` §7 and
`Benchmark/calibration/pigweed-fpga-20261014T022815Z/` (`report.md`,
`summary.json`, `interim-report.md`).

## Why

In the original campaign, 20 of the 210 benchmark instances fit on the chip
at P=16 but were never run on the FPGA. The CPU reference (Kissat with proof
logging, 1,000 s solve limit) could not certify an answer for them, and an
FPGA "UNSAT" cannot be checked without a certificate. The extension gives
the CPU 5× more time. Instances that become certified are then run on the
FPGA with a longer deadline.

## The 20 instances

Benchmark labels (GBD, not certificates): 7 SAT, 13 UNSAT. CPU outcome at
1,000 s (`calibration/cpu-v0`):

| ID | Tier | Family | Label | CPU at 1,000 s |
|---|---|---|---|---|
| MRB0-001 | S | long-learned-clauses | unsat | solve timeout |
| MRB0-003 | S | sgen | unsat | solve timeout |
| MRB0-004 | S | sgen | sat | solve timeout |
| MRB0-006 | S | sgen | sat | solve timeout |
| MRB0-007 | S | sgen | unsat | solve timeout |
| MRB0-008 | S | sgen | sat | solve timeout |
| MRB0-009 | S | sgen | sat | solver unknown (own limit) |
| MRB0-010 | S | sgen | sat | solve timeout |
| MRB0-012 | S | sgen | sat | solver unknown (own limit) |
| MRB0-019 | S | tseitin-formulas | unsat | proof hit 8 GiB cap |
| MRB0-021 | S-tight | binary-tree-parity | sat | solve timeout |
| MRB0-037 | S-tight | linvrinv | unsat | proof check timed out |
| MRB0-042 | S-tight | pigeon-hole | unsat | solve timeout |
| MRB0-080 | S-tight | scheduling | unsat | solve timeout |
| MRB0-082 | S-tight | sudoku-php | unsat | solve timeout |
| MRB0-084 | S-tight | tseitin-formulas | unsat | solve timeout |
| MRB0-086 | S-tight | tseitin-formulas | unsat | proof hit 8 GiB cap |
| MRB0-088 | S-tight | tseitin-formulas | unsat | solve timeout |
| MRB0-089 | S-tight | tseitin-formulas | unsat | solve timeout |
| MRB0-090 | S-tight | tseitin-formulas | unsat | solve timeout |

Subset manifest: `Benchmark/manifest.fit-uncertified20.csv`. Its rows are
byte-identical to `manifest.csv`.

## Settings

**CPU phase** (`Benchmark/calibration/cpu-v1-5000s`):

- Same pinned Kissat and drat-trim as cpu-v0; seed 0; one instance at a time
  (sequential), as in cpu-v0.
- Solve limit 5,000 s. Proof check limit 20,000 s.
- Proof file cap raised from 8 GiB to 64 GiB, because two instances already
  hit 8 GiB at 1,000 s. The cap is recorded in the campaign identity.
- cpu-v0 is untouched.

**FPGA phase** (new run directory, created once the CPU phase finishes):

- Same frozen PigWeedSAT candidate and configuration (P=16, 50 MHz), and the
  same safety rules as the original run, including the board-6 skip.
- **Deadline 2,600 s, not 5,000 s.** A board session lasts exactly one hour,
  and the platform cannot extend it. A solve needs the deadline plus 800 s of
  remaining lease before it starts, and session setup and the on-board check
  use about 150 s. 2,650 s is therefore the hard maximum; 2,600 s keeps a
  small safety margin.
- **1 repetition.** The original campaign was bit-for-bit deterministic
  across 3 repetitions and 4 boards.
- Only instances that cpu-v1 certifies are dispatched. Every SAT answer is
  checked against the original formula. An UNSAT answer counts only if it
  matches the new CPU certificate.
- A full local prepare and qualify (RTL simulation plus full-SoC
  place-and-route) runs under the extension's own organizer identity.

## Organizer changes for the extension

These were reviewed (APPROVE after one fix) and tested (189 tests pass).

- `calibrate_cpu.py`: new `--output-file-limit-gib` option; report header no
  longer assumes 210 instances.
- `run_pigweed_fpga.py`: prepare-only options `--solve-timeout`,
  `--repetitions`, `--only-ids-manifest` and `--cpu-override`.
  - These are recorded in `run.json` and the run identity.
  - Lease limits and the solve watchdog follow the deadline, and the default
    reproduces the original 1,000 s contract exactly.
  - A deadline that cannot fit a one-hour session is refused.
  - Per-instance CPU evidence comes from the newest CPU run that has a record
    for it, validated against that run's own limits.
  - `report.md` and `summary.json` state the campaign's real contract.
- `pigweed_fpga_worker.py`: the "too many cycles" check scales with the
  deadline (deadline × 50 MHz), instead of being fixed at 1,000 s.
- The original campaign's exact organizer code is preserved in
  `calibration/pigweed-fpga-20261014T022815Z/organizer-epoch2/`, so its
  report remains reproducible.

## Cost and schedule

- CPU: up to 20 × 5,000 s of solving (about 28 h) plus proof checking, on
  this machine. Expect 1.5–3 days.
- FPGA: at a 2,600 s deadline, each attempt uses its own board session,
  about 14 build-minutes per instance plus any platform failures. The
  account has about 121 build-minutes left this month, so the FPGA phase
  may need next month's quota, depending on how many instances certify.

## Results

| Phase | Status |
|---|---|
| CPU (cpu-v1-5000s) | **complete** 2026-10-22T09:27Z: 20/20 terminal, **5 certified**, 0 label conflicts (harness exit 2 = complete with uncertified instances) |
| FPGA | **complete** 2026-10-22T14:30Z: `calibration/pigweed-fpga-ext20-20261022T094311Z`, 5/5 attempts terminal (1 SAT, 3 resource errors, 1 transport error); started automatically at 09:43Z, one user-cleared halt |

### CPU phase: 5 of 20 newly certified at 5,000 s

| ID | Tier | Family | Certificate | Solve | Proof check | Proof (gz) |
|---|---|---|---|---|---|---|
| MRB0-037 | S-tight | linvrinv | UNSAT, DRAT verified | 841 s | 2,069 s | 0.7 GB |
| MRB0-009 | S | sgen | SAT, witness checked | 1,130 s | — | 1.0 GB |
| MRB0-021 | S-tight | binary-tree-parity | SAT, witness checked | 1,658 s | — | 1.8 GB |
| MRB0-001 | S | long-learned-clauses | UNSAT, DRAT verified | 2,188 s | 5,320 s | 1.7 GB |
| MRB0-003 | S | sgen | UNSAT, DRAT verified | 4,618 s | 8,737 s | 2.1 GB |

- All 5 certificates agree with the benchmark labels.
- **MRB0-037 produced the same proof both times.** Kissat solved it within
  1,000 s in both runs, and the two proofs are byte-identical (sha256
  `3d78863f…`). In cpu-v0, drat-trim stopped with its own internal timeout
  after 2,824 s, under the 3,000 s limit. In cpu-v1 the same proof
  verified in 2,069 s. The records do not show why the first check stopped
  early, so the higher check limit is not established as the cause. For the
  other four, the extra solve time made the difference.
- **Still uncertified (15):** every remaining sgen instance (004, 006, 007,
  008, 010, 012), all six tseitin-formulas instances (019, 084, 086, 088,
  089, 090), pigeon-hole MRB0-042, scheduling MRB0-080 and sudoku-php
  MRB0-082. Each hit the 5,000 s limit; for 019, 006 and 088 Kissat's own
  time limit fired first ("unknown"). None hit the 64 GiB proof cap; the
  largest compressed proof was 6.7 GB.
- **Timing caveat:** between 2026-10-21 14:13Z and 14:28Z, two short
  single-process jobs (a fresh-clone test run and an FPGA prepare dry-run)
  ran on the same 10-core machine while MRB0-012 was solving. Kissat is
  single-threaded and MRB0-012 timed out at 5,000 s anyway, so the effect
  on these results is negligible, but it was not a dedicated machine for
  those ~15 minutes.

### FPGA phase: 1 new solve, 3 memory limits, 1 dropped connection

Run `calibration/pigweed-fpga-ext20-20261022T094311Z`: 2,600 s host
deadline, 1 repetition, the 5 newly certified ids. `report` is clean
(`identity_ok: true`, 0 binding errors). All three sessions landed on
board 0, and every one was released with a completed reset job.

| ID | CPU certificate | FPGA result | Device cycles | Host GO→observation | ≈ at nominal 50 MHz |
|---|---|---|---|---|---|
| MRB0-009 | SAT | **SAT, witness checked** against the original formula | 117,105,253,124 | 2,342.09 s | 2,342.1 s |
| MRB0-003 | UNSAT | resource error -4 (no clause space) | 5,796,268,606 | 116.09 s | 115.9 s |
| MRB0-037 | UNSAT | resource error -5 (no literal page) | 4,387,262,084 | 87.80 s | 87.7 s |
| MRB0-021 | SAT | resource error -5 (no literal page) | 51,803,006 | 1.11 s | 1.0 s |
| MRB0-001 | UNSAT | `transport_error`: connection to board 0 lost 2,344 s after GO | — | — | — |

The attempt records keep `clock_confirmed: false` and leave `device_seconds`
blank: the platform does not report the board clock. The last column is
cycles ÷ 50 MHz, the nominal clock requested at build time, not a measured
duration.

- **There were no wrong answers.**
- **MRB0-009 is the first FPGA solve in the project that needed more than
  the original 1,000 s deadline.** It took 117.1 G device cycles and
  2,342.09 s host-observed from GO to the observed result; the CPU needed
  1,130 s.
- **On-chip memory remains the dominant limit.** 3 of the 4 instances that
  ran to an outcome exhausted learned-clause storage. That includes the SAT
  instance MRB0-021, which failed after 1 second.
- **MRB0-001's drop.** It occurred with no platform error code, while the
  local network was healthy. The halt was cleared by the user and recorded
  in `run.json` → `halt_clearances`. MRB0-001 stays recorded as
  `transport_error`, because the runner never re-runs an attempt.
  MRB0-009's connection on the same board outlived it (2,347.5 s vs
  2,346.0 s from attach to end, and an older session), so the records rule
  out a fixed platform connection-length cap at that point.
- **Clock.** For MRB0-009, cycles ÷ (host GO→observation × 50 MHz) =
  1.0000063. That is consistent with the nominal 50 MHz clock at the ppm
  level, as in the original campaign. It is not a measurement of the board's
  oscillator: host-clock drift of the same size would give the same ratio.
- **Cost:** 3 board sessions for this run (one rotation after MRB0-009).
  This month's account usage stood at 893/1000 build-minutes after
  session 1.

### Re-run of MRB0-001 (user-requested, 2026-10-22)

The ext20 record for MRB0-001 is left unchanged (`transport_error`). It was
re-run as a separate one-instance run,
`calibration/pigweed-fpga-rerun001-20261022T162434Z`, with identical
settings: 2,600 s deadline, 1 repetition, cpu-v1 evidence. That run had its
own prepare and its full local qualify passed (subset manifest
`manifest.rerun-MRB0-001.csv`).

- **Result: `timeout`.** It ran the full 2,600 s (host GO→observation
  2,600.005 s) on board 1 without a connection drop. It was aborted at the
  deadline, and the post-abort recovery check passed. The board was released
  (reset job `34aa1754`), and `report` is clean.
- PigWeedSAT on this platform has been deterministic: identical outcomes and
  bit-identical cycles across repetitions and boards in the first campaign.
  The dropped attempt at 2,344 s would therefore not have finished within
  2,600 s either.

## Conclusion

Giving the CPU reference 5× more time certified 5 of the 20 previously
uncertified chip-fitting instances. Of those 5, the FPGA solved 1
(MRB0-009, SAT; 117.1 G cycles, 2,342 s host-observed). Three ran out of
learned-clause memory, and MRB0-001 timed out at 2,600 s on re-run. The
extension therefore adds one solved instance to the benchmark's FPGA record,
beyond the original 19, and that solve needed a deadline longer than the
original 1,000 s. Its other outcomes match the first campaign's main
finding: on-chip learned-clause memory, not time, mostly limits what
PigWeedSAT solves. The 15 still-uncertified instances (mostly sgen and
tseitin) remain unscored. Proving them on CPU would need either far more
than 5,000 s or a different proof strategy.
