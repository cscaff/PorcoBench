# FPGA readiness plan for PigWeedSAT on the 210-instance corpus

This document turns the measured CPU calibration and the host-only loader
screen into a follow-on plan. It authorizes **no** FPGA build, simulation
campaign, board use or candidate change. All numbers below are measured by the
artifacts named in each section; timing is proof-enabled Kissat wall time on one
seed, a calibration survey and not an FPGA runtime projection.

## 1. Measured state

### 1.1 CPU certification (`Benchmark/calibration/cpu-v0/`)

Kissat 4.0.4 (`8af8e56f…`), drat-trim (`2e3b2dc0…`), seed 0, 1000 s solve,
3000 s check, sequential, Apple M1 Max. All 210 manifest IDs have a terminal
record; `--report-only` re-validated every evidence hash and gz roundtrip.

| Outcome | Count |
|---|---|
| Attempted | 210 |
| Claimed SAT / UNSAT | 77 / 72 |
| Witness-checked SAT | 77 |
| Proof-checked UNSAT | 71 |
| **Certified total** | **148** |
| Label conflicts (certificate vs GBD) | 0 |
| **Unresolved** | **62** |

Unresolved reasons: 54 solver wall timeout, 5 `s UNKNOWN` exits at ~1000 s
(Kissat's own `--time=1000` limit fired just before the harness deadline:
exit 0, not killed, wall ≈ 1000.01 s; effectively timeouts), 2 solver killed by `RLIMIT_FSIZE` at the 8 GiB proof cap
(MRB0-019, MRB0-086), 1 checker `s TIMEOUT` (MRB0-037, 2824 s).
Of the 62: 40 expected UNSAT, 22 expected SAT. Unresolved rows carry no
inherited GBD label. Certified by tier: S 9/19, S-tight 60/71, M-low 47/68,
M-high 32/52. Certified solve-time bins: <0.1 s 14, 0.1–1 s 23, 1–10 s 16,
10–100 s 43, 100–1000 s 52. 14 certified entries under 0.1 s are triviality
candidates, retained.

Independent recheck outside recorded timing: first certified SAT (MRB0-011,
200/200 variables) passes `check_witness`; first non-trivially certified UNSAT
(MRB0-002) re-verifies from the retained gz proof with drat-trim. The pinned
checker reaches its `c trivial UNSAT` exit-1 path only for an explicit empty
original clause; the `1 / -1` unit pair goes through ordinary verification and
exits 0 (both paths exercised against the real binary).

Measurement caveat: `kissat_max_rss_bytes` in `results.csv`/`summary.json` is
**not** valid physical memory on this Darwin run. The pinned
`kissat/src/resources.c` does `ru_maxrss << 10` unconditionally (Linux reports
KiB), but macOS already reports bytes, so recorded values are inflated ×1024
(100 of 208 exceed the machine's 64 GiB RAM; the maximum is 777,691,070,464 for
MRB0-147). The raw solver text is retained in each `solve.stdout`; treat the
column as solver-reported and mis-scaled (÷1024 gives a Darwin estimate) and do
not cite it as measured RSS.

### 1.2 Loader screen (`Benchmark/calibration/pigweed-v0/`)

630 rows (210 IDs × P=4,8,16), 0 crashes, no board use. Candidate parse vs the
strict original: **210/210 semantics-ok** under the only observed normalization
(within-clause sort by |lit| and repeated-literal removal; 158 instances
contain at least one reordered clause). The candidate
parser *does* silently drop empty clauses and truncate to the declared count; a
fixture confirmed this surfaces as `input_semantics_error`, but no corpus
instance triggers it. No instance exceeds the fixed `NUM_W=11`/`REM_W=12`
clause-length fields (max width among loadable instances: 25).

| P | loaded | unsupported | variables > 2048 | clauses > 4096 | clause store > 16384 | literal store > 16384 |
|---|---|---|---|---|---|---|
| 16 (baseline) | 88 | 122 | 15 | 85 | 12 | 10 |
| 8 (sensitivity) | 93 | 117 | 15 | 85 | 12 | 5 |
| 4 (sensitivity) | 88 | 122 | 15 | 85 | 12 | 10 |

Baseline P=16 by tier: **S 19/19, S-tight 69/71, M-low 0/68, M-high 0/52**.
Loadable ∩ CPU-certified: **68** (33 SAT, 35 UNSAT) = 32% of 210; 9 of those
are under 0.1 s. The literal store binds first for 81 of 88 loadable
instances. Initial occupancy ≥ 0.75 for 23 and ≥ 0.9 for 6 (4 certified); the
maximum is MRB0-021 at 0.998 (16352/16384 literal words, uncertified).
Packing success proves nothing about dynamic headroom: learned clauses need
store space beyond the initial image (`MAX_LEARN=1024` is a dynamic limit, not
a width cap). P=4/8 are sensitivity only, never per-instance tuning.

## 2. Blocking conditions

1. **Capacity (candidate memory).** 122/210 instances (all 120 M-tier plus two
   S-tight) cannot be loaded at the frozen P=16 configuration. Clause-count
   (85) and variable-count (15) limits dominate; neither is addressable by
   page size. Supporting them requires separately approved solver work or
   user-approved corpus changes. They remain in the inventory as
   "non-fitting, not dispatched".
2. **Certification.** 62 CPU-unresolved IDs cannot receive validated FPGA
   timing. Resolving them needs a separately budgeted CPU follow-up (longer
   limits, other seeds, bounded proof size); none is authorized here.
3. **Tier basis.** The tier-generation script is missing; M/X routed fit
   depends on an unverified full-chip slot budget. The screen shows the
   prior tier arithmetic does not predict loadability: no M-tier instance
   fits the candidate. No X addition or corpus replacement is authorized,
   and tier-based rebalancing waits for the script and measured user-slot
   resources.
4. **Adapter limits.** The inherited evaluator hardcodes a 30 s scoring
   timeout, 60 s host watchdog, 2,000,000-cycle simulation cap and
   `DEFAULT_DEADLINE_CYCLES = 30 * 50 MHz` (`satbench/runner.py` lines
   33–43, `satbench/shell.py` lines 64–66). The 1000 s protocol needs
   50,000,000,000 cycles; every inherited 60 s transport limit must be
   replaced in the new adapter.

## 3. Pilot set (`pigweed-v0/summary.json → pilots`)

Selection rule: CPU-certified, semantics-ok, P=16 loadable, no flagged fixed
fields; per tier the fastest SAT, fastest UNSAT and maximum initial occupancy;
ties by ID; deduplicated. Empty cells are explicit gaps, never filled from
another tier.

| Tier | Fastest SAT | Fastest UNSAT | Max initial occupancy |
|---|---|---|---|
| S | MRB0-011 (906.2 s CPU, occ 0.391) | MRB0-017 (0.353 s, occ 0.193) | MRB0-005 (UNSAT, occ 0.416) |
| S-tight | MRB0-077 (0.021 s, occ 0.561) | MRB0-078 (0.022 s, occ 0.500) | MRB0-026 (UNSAT, occ 0.984) |
| M-low | **gap** (0 loadable) | **gap** | **gap** |
| M-high | **gap** | **gap** | **gap** |

Pilot IDs: **MRB0-005, MRB0-011, MRB0-017, MRB0-026, MRB0-077, MRB0-078**.
Caveats: S has only one certified SAT, and MRB0-011 needed 906 s on CPU
(unlikely to be a short device case; informational, not a prediction). The two
S-tight fastest entries are triviality candidates (<0.1 s). The existing PoC
semantic/reset/abort cases remain a separate qualification set and never enter
the 210.

## 4. Follow-on gates

Each gate must pass before the next. No gate is authorized by this document.

1. **Certification gate.** Only CPU-certified inputs qualify for validated
   FPGA timing. FPGA SAT models must satisfy the original formula (strict
   parser + `check_witness`, all declared variables). FPGA UNSAT is validated
   against a retained CPU UNSAT certificate, not a device-generated proof:
   the inspected PigWeed interface emits no DRAT.
2. **External-corpus adapter.** New organizer code outside `PigWeedSAT/`.
   Reuse `satbench.pigweed.run_worker` (line 111), `run_transaction` (134),
   `satbench.shell.BenchmarkShell` (69) and the `satbench.cloud` build/submit
   primitives where their contracts permit. `satbench prepare`/`corpus.py`
   generate and enumerate a tiny corpus and cannot accept this manifest; do not
   reuse them. Bind input, certificate, candidate source, config and build
   identities; never edit a frozen bundle; never enumerate large instances;
   never inherit label-less UNSAT acceptance (`runner.validate_answer`).
3. **RTL gate.** Pilot IDs through the organizer wrapper/transaction path at
   an initial 2,000,000-cycle cap (`SIM_CYCLE_CAP`, `runner.py` line 40),
   recording explicit cap outcomes. Check answers/witnesses independently;
   run SAT→UNSAT→SAT on one DUT and timeout/abort→next solve with stale RAM
   preserved. Golden-model agreement is diagnostic only. A simulation cap is
   neither a board timeout nor physical infeasibility.
4. **Route gate.** Frozen wrapped design at 50 MHz (`OPERATIONAL_CLOCK_HZ`,
   matching the evaluator rather than Table3's 65 MHz claim). Require
   full-SoC totals ≤ 208 EBR / 83,640 LUT (user slot 183 EBR / 78,292 LUT
   after base SoC), timing closure, retained source/export/bitstream/
   toolchain hashes. LUTRAM competes with solver logic. Verify the SDK CLI in
   that phase; `satbench build` builds only its PoC bundle.
5. **Board gate.** Needs authorized access, availability, a qualified source,
   a routed wrapper, and separate approval for board use. Pilot at a
   1,000 s device deadline with a 1,060 s host watchdog. Confirm the shell's
   internal elapsed/deadline counters hold 50,000,000,000 cycles (the
   register map exposes 64-bit elapsed at 132/133 and deadline at 138/139,
   but internal counter widths are unverified here) and replace all inherited
   60 s transport limits (`HOST_WATCHDOG_S`, worker `watchdog_s` defaults of
   60/120 s, `cloud` `op_timeout_s`). Keep load-to-stop, start-to-stop and
   host parse/load/readback separate. Abort/reset after timeout/resource
   failures and verify the next solve. Then cover all 210 inventory entries.
   Physical eligibility is `dispatchable=true AND cpu_certified=true` (68
   rows at P=16); the other 142 stay as non-dispatched inventory rows (122
   non-fitting, 20 loadable but CPU-uncertified). 3 physical repetitions for
   eligible cases only. Do not shrink the denominator to what
   PigWeedSAT solves; publish no ranking until certification, qualification
   and infrastructure are complete.
6. **Freeze gate.** Report actual coverage (§1.2) and required memory/
   semantic changes without modifying the candidate. Obtain the missing
   tier-generation script and rerun against measured user-slot resources
   before tier rebalancing. X stays outside the scored set.

## 5. Prerequisites and acceptance outputs

| Gate | Prerequisites | Acceptance output |
|---|---|---|
| Adapter | this CPU package, `pigweed-v0/rows.csv` | adapter that dispatches only rows with `dispatchable=true` and `cpu_certified=true`, 210-row inventory including non-dispatched IDs with reasons |
| RTL | adapter, frozen candidate hashes (`pigweed-v0/run.json`) | per-pilot record: status, witness check, `sim_cycles`, explicit cap outcomes; SAT→UNSAT→SAT and abort→next-solve results |
| Route | RTL gate, SDK access | routed bitstream, LUT/EBR totals vs 208/83,640, timing report at 50 MHz, artifact hashes |
| Board | route, access approval, 64-bit timer confirmation | 3 repetitions per physically eligible case (`dispatchable=true AND cpu_certified=true`), separated timing columns, reset-after-timeout results |
| Freeze | all above | coverage report, list of memory/semantic changes required, scored-set decision |

## 6. Artifacts

- `Benchmark/calibrate_cpu.py`, `test_calibrate_cpu.py` (63 tests),
  `screen_pigweed.py`, `test_screen_pigweed.py` (15 tests)
- `Benchmark/calibration/cpu-v0/` — `run.json`, `manifest.snapshot.csv`,
  `results.csv`, `summary.json`, `report.md`, per-attempt evidence
  (input, stdout/stderr, witness, gzip proofs, checker logs)
- `Benchmark/calibration/pigweed-v0/` — `rows.csv` (630), `summary.json`,
  `run.json`
- `Benchmark/calibration/cpu-v0-aborted-attempt{1,2,3}*` — three superseded
  runs preserved after harness fixes (each had zero terminal records); not
  part of the result set
- `Benchmark/calibration/cpu-v0-executed-harness/calibrate_cpu.py` — the
  byte-exact harness that produced `cpu-v0` (sha256 `d48bcd32…`, as recorded in
  `run.json`). The current `calibrate_cpu.py` was hardened after independent
  review (below), so it intentionally **fails** the identity check on `cpu-v0`.
  To re-verify `cpu-v0`: copy the preserved file next to the tests (e.g.
  `Benchmark/calibrate_cpu_v0_executed.py`) and run it with `--report-only`
  (done: exit 2, 210 records, 148 certified, 0 conflicts), then delete the copy.
- Post-campaign review hardening (does not change any recorded result): the
  pinned drat-trim, in binary-proof mode, reads a `c` comment line inside a CNF
  body as an empty clause and then prints `c trivial UNSAT` / `s VERIFIED` /
  exit 1 even for a satisfiable formula (reproduced). None of the 210 CNFs has
  any comment line and 0 certificates used that path, so no recorded
  certificate is affected; the current harness accepts the trivial path only
  when the strict original contains an explicit empty clause. It also now
  re-derives every certified record from retained evidence, binds the recorded
  CNF identity to the manifest, recomputes label agreement, and fails closed on
  an unreadable or wrongly shaped `attempt.json` or malformed record. The
  hardened validator reports 0 violations over all 210 real records.
- Tools pinned under `Benchmark/.tools/` (Kissat, drat-trim)
- CNFs, witnesses and proofs stay local; share only link-based identities and
  measurements without separate redistribution permission.

## 7. Native FPGA campaign — results (executed 2026-10-14 → 2026-10-19, COMPLETE)

This is a deliberate difference from the earlier hardware-wrapper and
device-deadline proposal in §6: this run measures **unmodified PigWeedSAT**
on real boards through a benchmark-owned organizer. Nothing in `PigWeedSAT/`
(clean git at `27e4de5e…`), the SDK (pinned `d77d68d1…`), the firmware or the
sandbox image was edited. No competition score and no CPU-vs-FPGA speedup are
claimed: the CPU baseline is proof-enabled Kissat wall time, a different
timing contract.

- **Command:** `Benchmark/.venv-fpga/bin/python -B Benchmark/run_pigweed_fpga.py
  prepare|qualify|run|report --out RUN` with
  `MRG_SANDBOX_IMAGE=ghcr.io/manhattanreasoning/mrg-sandbox@sha256:a5c74a81…`.
  Contract: P=16, 50 MHz, 1,000 s **host-observed** solve deadline, three
  repetitions.
- **Run artifact:** `Benchmark/calibration/pigweed-fpga-20261014T022815Z`
  (`report.md`, `summary.json` and `results.csv` are authoritative;
  `interim-report.md` has the dated chronology; `board6-incident.md` is the
  platform incident report). 68 of 210 manifest IDs are eligible (S 9,
  S-tight 59; no M-tier instance fits at P=16). The 142 ineligible rows are
  80 non-fitting only, 20 uncertified only, and 42 both; the reason counts
  overlap, so they don't sum to 210. All 210 rows are retained in the
  inventory.
- **Identity epochs:** reps 1–2 ran under epoch 1. Rep 3 ran under epoch 2,
  which added a user-authorized rule that releases and rebuilds any build
  landing on board 6, because its host agent dropped `/stream` with
  4502/503. Each epoch passed the full local qualification: RTL semantic,
  abort and pilots, plus full-SoC PnR at 50 MHz (Fmax 73.9 and 76.6 MHz).
  Each `attempt.json` carries its own identity snapshot.
- **Outcome per ID** (identical in every scored repetition):

  | Outcome | IDs |
  |---|---|
  | SAT (witness-checked against the original CNF) | 17 |
  | UNSAT (agrees with the CPU certificate) | 2 |
  | Timeout at 1,000 s | 23 |
  | Resource error (learned-clause store full: -5 no literal page, -4 no clause space) | 26 |

  Across all 204 attempts: 51 SAT, 6 UNSAT, 66 timeout, 78 resource error,
  and 3 `transport_error` (MRB0-072, 075 and 087, all rep 2: platform
  connection drops). There were 0 wrong answers and 0 binding errors.
- **Solved:** 19 of 68 IDs, all S-tight. Device time ranges from 52 k to
  1.87 G cycles; the median is 50.3 M cycles (about 1.0 s at 50 MHz). 13 of
  the 26 resource errors are CPU-certified SAT, so on-chip learned-clause
  capacity, not the deadline, is the dominant limit.
- **Determinism:** all 68 IDs gave the same outcome in every scored
  repetition, and all 45 non-timeout IDs had bit-identical cycle counts
  across repetitions.
- **Clock:** the cloud build metadata exposes no clock field, so attempt
  records withhold device seconds (`clock_confirmed=false`). Across 51 clean
  attempts of at least 60 s, cycles ÷ (GO→observation interval) is
  0.9960–0.9999 × 50 MHz. This is a lower bound, since host latency is
  included, and it is consistent with the submitted `sys_clk_freq=50000000`.
- **Operations:** 46 board sessions were assigned, and 41 ran scored work.
  Every assigned session has a verified journal release chain, all 51
  release jobs are `complete` on the live API, and nothing is left held.
  The account ran 63 build jobs (62 for this run: 51 completed, 7 failed
  board-0 flashes, 4 cancelled or left unfinished by crashes) using 879/1000
  build-minutes. The `/usage` builds list is capped at 50 entries.
- **Incidents** (details in `interim-report.md` §6–16):
  - The first attach was blocked because the platform leaves a board's
    `current_job_id` null. Sessions are now bound by account plus the
    `expires_at = updated_at + 3600 s` relation, with a competing-build
    block. Evidence is in
    `Benchmark/calibration/stale/pigweed-fpga-20261014T005349Z-blocked-attach`.
  - Local network dropouts crashed the runner several times; each was
    recovered by `run --resume`. A stability-gated supervisor was added.
  - Platform incidents: a board-assignment outage (2026-10-14/15), drops
    during the redeploy, board 6 host-agent failures (now skipped; 3
    skips), and board 0 flash failures (`never came up within 10.0s`; 7
    failed builds, relaunched automatically under a bounded rule).
  - One operator-caused halt (a misread "stop") was cleared and the
    interrupted attempt re-run.
- **Known organizer defects** (not patched mid-campaign; see
  `interim-report.md` §11 and §15): the release flag lands on
  `sessions/NNN.job.json` instead of `NNN.json` (the journal is
  authoritative); idempotent GET polls have no transient-error retry;
  qualification transport failures are opaque; reconcile journals spurious
  `session_expired_or_reassigned` evidence; and a Ctrl-C right after a
  board skip can submit one extra build.

## 8. Extension: 20 fitting-but-uncertified instances (2026-10-20 → 2026-10-22, COMPLETE)

§7's results stand unchanged. This extension adds measurements; it does not
replace any of them. Full details and results are in
`Benchmark/FPGA_Extension_Uncertified20_Report.md`.

- **Scope:** the 20 instances that fit the chip at P=16 but had no CPU
  certificate at 1,000 s (S 10, S-tight 10; benchmark labels 7 SAT,
  13 UNSAT).
- **CPU phase:** `calibration/cpu-v1-5000s`. Same pinned Kissat and
  drat-trim, 5,000 s solve limit, 20,000 s proof-check limit, 64 GiB proof
  cap, run sequentially. cpu-v0 is untouched.
- **FPGA phase:** only for the instances cpu-v1 certifies. Same frozen
  candidate, 1 repetition, and a **2,600 s** host deadline. 5,000 s is
  impossible because the platform's board session is fixed at one hour, and
  2,650 s is the most that fits. It runs in a new run directory with its
  own prepare and qualify.
- **CPU result:** 5 of 20 newly certified, all agreeing with their labels:
  UNSAT MRB0-001, 003 and 037; SAT MRB0-009 and 021. The other 15 still
  hit the 5,000 s limit.
- **FPGA result** (`calibration/pigweed-fpga-ext20-20261022T094311Z`, clean
  `report`):
  - **MRB0-009 SAT**, witness checked, after 117.1 G device cycles (2,342 s
    host-observed from GO; device seconds are withheld because the platform
    does not confirm the clock). It is the first FPGA solve in the project
    that needed more than 1,000 s.
  - Three resource errors: MRB0-003 (-4), MRB0-037 (-5) and MRB0-021 (-5,
    after 1 s).
  - One `transport_error`: MRB0-001, a board-0 connection drop at 2,344 s.
    The halt was cleared by the user. At the user's request MRB0-001 was
    re-run in a separate one-instance run
    (`calibration/pigweed-fpga-rerun001-20261022T162434Z`, same settings):
    **timeout** at the full 2,600 s on board 1, with no drop.
  - No wrong answers.
- **Takeaway:** the extension adds one solved instance (19 → 20 FPGA-solved
  ids overall). Learned-clause memory, not time, remains the dominant
  limit.
