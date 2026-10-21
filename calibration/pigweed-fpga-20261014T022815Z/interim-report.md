# PigWeedSAT native FPGA campaign — INTERIM report

> **Superseded 2026-10-19:** the campaign completed (`run.json` phase
> `run_done`). See §17 for the final state; the final results are in
> `report.md` / `summary.json` and `Benchmark/FPGA_Readiness_Plan.md` §7.
> The sections below are the dated chronology, kept unchanged.

Run: `Benchmark/calibration/pigweed-fpga-20261014T022815Z`
Status as of 2026-10-15 16:00Z: **paused, not complete** — 108 of 204 planned
attempts are terminal; 96 are `not_run`. The campaign stopped because the
Manhattan Reasoning platform stopped assigning boards to builds (§6), not
because of any correctness, budget or harness halt (`run.json`: phase
`running`, no `halt_reason`). This file is a hand-written interim summary;
the machine-generated `report.md` / `summary.json` / `results.csv` (last
`report` run 2026-10-15T11:23Z, `identity_ok: true`, 0 binding errors) are the
authoritative records and are unchanged since — no attempt has run after
2026-10-14T20:49:46Z.

## 1. Contract

- Candidate: unmodified PigWeedSAT, clone HEAD `27e4de5e…` (git clean), frozen
  snapshot in `candidate/`; cfg `H.pigweed(H.Config(lit_page=16))`.
- Platform: Manhattan Reasoning cloud FPGA, SDK pinned `d77d68d1…` (0.1.10),
  50 MHz system clock and timing target.
- 1,000 s **host-observed** solve deadline measured from the GO intent;
  three repetitions per eligible ID; pilots `MRB0-005/011/017/026/077/078`
  first. No device-enforced deadline is claimed.
- Correctness: every SAT answer is checked against the original CNF with the
  organizer's strict parser; UNSAT answers are accepted only when they agree
  with the retained CPU certificate (`calibration/cpu-v0`). A wrong answer
  would halt the campaign.
- Not a competition score and not a CPU-vs-FPGA speedup: the CPU baseline is
  proof-enabled Kissat wall time, a different contract.

## 2. Eligibility (all 210 manifest rows retained in `inventory.csv`)

| | Count |
|---|---|
| Eligible (fits P=16, semantics/field-safe, CPU-certified) | **68** |
| Non-fitting only | 80 |
| Uncertified only | 20 |
| Non-fitting and uncertified | 42 |

Every eligible ID is in tiers S (9) or S-tight (59); no M-low or M-high
instance fits the loader at P=16. The six pilots were all eligible.

Local gates before booking (all passed): RTL SAT→UNSAT→SAT sequence, RTL abort
pattern, six capped RTL pilots, official full-SoC PnR at 50 MHz — fits, timing
met, Fmax 73.9 MHz, logic 21,268/83,640, BRAM 150/208, DSP 6/156.

## 3. Progress by repetition

| Repetition | Terminal | Not run |
|---|---|---|
| 1 | **68 / 68** | 0 |
| 2 | 40 / 68 (MRB0-002 … MRB0-055) | 28 |
| 3 | 0 / 68 | 68 |
| **Total** | **108 / 204** | **96** |

| Outcome (all terminal attempts) | Count |
|---|---|
| SAT (witness-validated) | 25 |
| UNSAT (certificate-consistent) | 2 |
| Timeout at 1,000 s | 34 |
| Resource error | 47 (-5: 30, -4: 17) |
| Wrong answer / transport error / interrupted | 0 |

Result codes come from the learned-clause save stage in `candidate/design.py`:
**-5** (`:1777`) = the free literal-page pool is empty; **-4** (`:1694`) =
free clause pages or free clause IDs are exhausted. Both mean the on-chip
learned-clause store filled up. They are recorded as `resource_error`, never
as UNSAT. 47 of the 108 terminal attempts ended this way, so storage
capacity, more than the 1,000 s deadline, is the main limit observed.

## 4. Repetition 1 — one complete pass over all 68 eligible IDs

| Outcome | Count | CPU label |
|---|---|---|
| SAT | 17 | all SAT |
| UNSAT | 2 | all UNSAT |
| Timeout | 23 | 20 UNSAT, 3 SAT |
| Resource error | 26 | 13 UNSAT, 13 SAT |

**Solved: 19 / 68 (28%)**, all in tier S-tight. Every answer agrees with the
CPU certificate.

By tier: S — 0/9 solved (6 resource, 3 timeout); S-tight — 19/59 solved
(20 timeout, 20 resource).

By family (eligible families only; rep 1):

| Family | Eligible | SAT | UNSAT | Timeout | Resource |
|---|---|---|---|---|---|
| random-planted-solution | 10 | 7 | | | 3 |
| random | 10 | 6 | | | 4 |
| register-allocation | 10 | | | 10 | |
| coloring | 5 | | | 2 | 3 |
| random-graph-xorsat | 4 | | | 2 | 2 |
| subset-cardinality | 4 | | | | 4 |
| tseitin-formulas | 4 | | | 4 | |
| hgen | 3 | | | | 3 |
| scheduling | 3 | 2 | 1 | | |
| fpga-routing | 2 | | | 2 | |
| hamiltonian | 2 | 2 | | | |
| mutilated-chessboard | 2 | | | | 2 |
| sgen | 2 | | | 1 | 1 |
| battleship, clique-formulas | 1 each | | | 1 each | |
| theorem-proving | 1 | | 1 | | |
| cardinality-constraints, miter, pigeon-hole, sgen-balanced | 1 each | | | | 1 each |

Pilots: MRB0-077 SAT, MRB0-078 UNSAT, MRB0-005 resource error (-5),
MRB0-011/017/026 timeout.

### Solved instances (rep 1), device cycles

Device seconds below are cycles ÷ 50 MHz; see §5 for the clock evidence.
"GO→obs" is host-observed time from the GO intent to seeing done.

| ID | Family | Answer | Cycles | ≈ device s | GO→obs s |
|---|---|---|---|---|---|
| MRB0-079 | scheduling | SAT | 52,445 | 0.001 | 0.03 |
| MRB0-077 | scheduling | SAT | 267,772 | 0.005 | 0.04 |
| MRB0-046 | random | SAT | 1,420,082 | 0.028 | 0.10 |
| MRB0-078 | scheduling | UNSAT | 2,504,229 | 0.050 | 0.10 |
| MRB0-083 | theorem-proving | UNSAT | 4,914,403 | 0.098 | 0.19 |
| MRB0-061 | random-planted-solution | SAT | 6,501,577 | 0.130 | 0.38 |
| MRB0-057 | random-planted-solution | SAT | 7,936,634 | 0.159 | 0.18 |
| MRB0-043 | random | SAT | 22,291,196 | 0.446 | 0.46 |
| MRB0-062 | random-planted-solution | SAT | 40,749,614 | 0.815 | 0.91 |
| MRB0-066 | random-planted-solution | SAT | 50,277,839 | 1.006 | 1.10 |
| MRB0-033 | hamiltonian | SAT | 218,052,263 | 4.361 | 4.40 |
| MRB0-044 | random | SAT | 263,842,914 | 5.277 | 5.29 |
| MRB0-032 | hamiltonian | SAT | 294,923,299 | 5.898 | 6.23 |
| MRB0-050 | random | SAT | 318,102,536 | 6.362 | 6.45 |
| MRB0-063 | random-planted-solution | SAT | 359,363,726 | 7.187 | 7.22 |
| MRB0-065 | random-planted-solution | SAT | 401,421,502 | 8.028 | 8.09 |
| MRB0-049 | random | SAT | 1,040,311,157 | 20.806 | 20.89 |
| MRB0-058 | random-planted-solution | SAT | 1,157,885,526 | 23.158 | 23.24 |
| MRB0-045 | random | SAT | 1,868,199,718 | 37.364 | 37.54 |

Median over the 19: 50.3 M cycles (≈1.0 s). The generated `report.md` median
(218 M cycles, 9.5 s host total) is over all 27 validated completions across
both repetitions and includes host load time.

### Resource errors (rep 1)

26 IDs, exhausted after 6.7 s to 815 s of device time (≈ cycles ÷ 50 MHz).
-5 (no literal page): 17 IDs, mostly random / random-planted-solution / hgen
/ mutilated-chessboard / random-graph-xorsat. -4 (no clause space): 9 IDs —
all four subset-cardinality, plus coloring ×2, sgen-balanced, miter,
pigeon-hole. 13 of the 26 are CPU-certified SAT, so the on-chip learned-clause
capacity is a binding limit for satisfiable instances too, not only for UNSAT.

### Timeouts (rep 1)

23 IDs reached the 1,000 s host deadline (observed at 1000.0002–1000.052 s;
none late), were aborted, and the board passed synthetic recovery each time.
20 are CPU-certified UNSAT (register-allocation 10/10, tseitin-formulas 4/4,
fpga-routing 2/2, coloring 2, battleship, clique-formulas); 3 are SAT
(MRB0-011 sgen, MRB0-053 and MRB0-055 random-graph-xorsat).

## 5. Determinism and timing evidence

- **Repeatability:** all 40 IDs with two repetitions gave the same outcome
  both times. The 8 solved in both had bit-identical cycle counts, and all 21
  resource errors in both stopped at identical cycle counts. Native
  PigWeedSAT on this board is deterministic, so repetitions 2–3 confirm
  determinism rather than add timing variance.
- **Clock:** cloud build metadata exposes no clock field, so per-attempt
  records keep `device_seconds` blank (`clock_confirmed=false`). Across 32
  clean attempts lasting ≥60 s, cycles ÷ (GO→observation interval) gives
  0.9975–0.9999 × 50 MHz and never exceeds it. The interval includes GO send
  latency and up to one 50 ms poll, so this is a lower bound; it is consistent
  with the requested 50 MHz.
- **Host overhead:** formula load median 2.0 s (max 4.3 s) over the
  WebSocket bus; not counted in device cycles.

## 6. Operations and incidents

- Board 2 for the whole run (2026-10-14 03:21Z → 20:49Z, ≈17.5 h). 20 sessions
  acquired and rotated on lease exhaustion; each session ran on-board
  qualification (caps, SAT→UNSAT→SAT, active abort) before scored work. 21
  releases (the 20 + one crash-orphaned session), every reset job journaled
  and complete.
- **Build spend:** 24 builds for this run, 346 build-minutes; the account
  total is 359/1000 (includes 13 min for the first, rejected attach in
  `calibration/stale/pigweed-fpga-20261014T005349Z-blocked-attach`).
- **Local network dropouts (×3):** a connect timeout (between 15:07Z and
  15:19Z), a DNS failure (between 20:50Z and 21:04Z), and ENETUNREACH
  (≈23:56Z) each crashed the runner while it polled a build. Each was
  recovered with `run --resume`, and reconcile settled the orphaned build:
  666b2ffe's session was released unused (reset job 8e26b912), and
  2d903cde's session had expired unused before the next resume.
- **Platform board-assignment outage (ongoing):** the last assignment was
  build `2d903cde` → board 2 at 21:05:20Z. By 23:28Z board 2 showed `reserved`
  with no session. Builds `7a68fef5` and `ddfafa83` both finished gateware
  (≈23:43Z, ≈03:03Z) and were never given a board; both were cancelled (the
  second by the runner's 4 h ceiling). Since then boards 1/2/3/5/6 report
  `reserved` with no session and boards 0/4 report `error`; a watcher has seen
  zero idle boards on every 10-minute poll since 06:49Z.
- **Build-minutes lost to incidents:** 666b2ffe 16, 2d903cde 15, 7a68fef5 14,
  ddfafa83 14 — 59 minutes.
- Known cosmetic journal issue: after a crash, reconcile re-journals earlier
  cleanly released sessions as `session_expired_or_reassigned` evidence. These
  entries are informational only and caused no cloud mutation.

## 7. Remaining work

96 attempts remain: 28 for repetition 2 (MRB0-056 onward) and 68 for
repetition 3. Because outcomes are deterministic (§5), the earlier
session usage predicts the cost: repetition 1 took 13 sessions, and the
remaining part of repetition 2 matches sessions 8–13 of repetition 1, so
about 19 more sessions — roughly 270–290 build-minutes against 641
remaining and about 17 h of board time. Resume once a board is
assignable:

```
PYTHONDONTWRITEBYTECODE=1 caffeinate -i Benchmark/.venv-fpga/bin/python -B \
  Benchmark/run_pigweed_fpga.py run --resume --out \
  Benchmark/calibration/pigweed-fpga-20261014T022815Z
```

Then run `report --out …`, verify the release jobs and board states, and
replace this interim file with the final results.

## 8. Update 2026-10-16T03:05Z — platform redeploy, halt cleared, resumed

- 2026-10-15T17:27Z: boards became idle again and the watcher resumed the
  campaign. Session 21 (board 3) failed on-board qualification: the
  active-abort demo lost its connection. Its release then hit an API 502
  and the runner crashed; the next resume completed the pending release
  (reset job `b990436b`).
- Sessions 22–24 (boards 1, 2, 3) ran rep 2 MRB0-056 … MRB0-071.
- 20:09Z: the board-3 connection dropped 403 s into MRB0-072 rep 2, well
  before the deadline. That attempt is recorded as `transport_error`, the
  board was released, and the campaign halted as designed.
- The user confirmed the Manhattan Reasoning platform was redeployed at the
  time. The halt was cleared on that basis; the justification is recorded in
  `run.json` → `halt_clearances`. MRB0-072 rep 2 stays `transport_error`: the
  runner never replays a terminal attempt. Its rep-1 outcome was a timeout.
- Determinism still holds: 56/56 IDs with two scored repetitions agree on
  outcome, and 40/40 non-timeout pairs have identical cycle counts.
- State at resume: rep 1 68/68; rep 2 57/68 (56 scored + 1
  `transport_error`), 11 not run; rep 3 0/68. Quota 415/1000 build-minutes
  used. Resumed at 03:02Z (build `407e8e34`) under a detached supervisor
  whose output is in `supervisor-console.log`.

## 9. Update 2026-10-16T04:10Z — second transport halt (platform host agent)

- Session 25 (board 3) finished MRB0-073 and MRB0-074 rep 2 (both
  timeouts, matching rep 1), then rotated.
- Session 26 (board 6) qualified, but MRB0-075 rep 2 lost its connection
  15 s after GO. The platform's error states the cause: `server closed with
  4502: Host agent /stream failed (503): host agent unreachable`. This was a
  Manhattan Reasoning host-agent failure, on a different board from the
  earlier drops. The attempt is recorded as `transport_error`, board 6 was
  released (reset job `ec1dfae2`), and the campaign halted.
- User decision: stay halted until the platform is confirmed stable, then
  clear the halt with a recorded justification and resume.
- State: rep 1 68/68; rep 2 60/68 (58 scored, 2 `transport_error`:
  MRB0-072 and MRB0-075), 8 not run; rep 3 0/68. Quota 442/1000
  build-minutes used.
- 2026-10-16T17:26Z: the user reported the platform is up (fleet: boards
  1/2/3/5/6 idle). The halt was cleared with a recorded justification
  (`run.json` → `halt_clearances[1]`) and the run resumed. Build `479cd0ec`
  went to board 1; session 27 qualified and started MRB0-076 rep 2 at
  17:43Z.

## 10. Update 2026-10-16T19:45Z — local network degradation, paused

- Session 27 (board 1) finished rep 2 for MRB0-076, 077, 078, 079, 081,
  083 and 085 (17:42–18:20Z), each matching its rep-1 outcome.
- 18:20–19:12Z: the local internet connection flapped. TLS handshake
  timeouts, connection resets and read timeouts hit the platform API and
  github.com at the same moments, so this was local, not the platform.
  Every crash came after a paid build, and reconcile then released that
  build's session unused: `7884db4b` (15 min), `06c409b1` (14), `74a4bff8`
  (13). Build `68d54edc` was cancelled mid-build. The old resume script
  stopped on a network-caused Blocker at 19:09Z.
- Supervisor v3 (`/tmp/pigweed-supervise3.sh`) requires 10 consecutive
  connectivity probes, 30 s apart, before every run. Its first session
  (build `48511b5b`, board 6) failed on-board qualification: the three tiny
  check solves took 3–10 s instead of about 1 s, and the active-abort demo
  lost its connection. The board was released (reset job `9e7793dd`) and
  the runner stopped (rc 3).
- At 19:37Z the link was up but poor: ping to 1.1.1.1 averaged 211 ms (max
  528 ms), and github.com took 3–9 s per fetch.
- User decision: wait for a better connection, then relaunch the gated
  resume.
- State: rep 1 68/68; rep 2 67/68 (65 scored, 2 `transport_error`);
  MRB0-087 rep 2 and all 68 of rep 3 remain (69 attempts, about 14
  sessions). Quota 516/1000 build-minutes used. Nothing is running and no
  board is held.

## 11. Known organizer defects (found mid-campaign; not patched)

Patching `run_pigweed_fpga.py` or the worker now would change the frozen
organizer identity, and `--resume` would refuse this run. These defects are
recorded here and are for the next code version.

- **Release flag lands on the wrong file.** `mark_session_released`
  (`run_pigweed_fpga.py:1893`) scans `sessions/*.json` in sorted order and
  updates the first match. That is the worker spec `NNN.job.json`, not the
  canonical `NNN.json`. All 28 canonical records therefore read
  `released: false`. Nothing decides on this flag. The journal is
  authoritative: every one of the 28 assigned sessions has a verified chain
  from `release_accepted` to `release_terminal` (`job_status: complete`,
  `session_gone: true`).
- **No transient-error retry on idempotent GET polls.** A single
  ReadTimeout or ConnectionReset during build polling or reconcile kills
  the runner. The next resume then releases that build's session unused,
  which caused most of the wasted builds in sections 6 and 10. Supervisor v3's stability gate
  mitigates this but does not remove it. Fix: bounded retry with backoff on
  GETs only, failing closed after a few minutes; never retry POSTs.
- **Opaque qualification transport failures.** When the active-abort demo
  loses its connection, the qualification record only says
  `transport: true`; it does not keep the exception or the stage.
  Session 21's and session 28's failures cannot be attributed further.
- **Spurious reconcile evidence.** `release_terminal` does not carry
  `session_id`, so every resume re-journals all cleanly released sessions
  as `session_expired_or_reassigned`. This is informational only and
  caused no cloud mutation.

## 12. Update 2026-10-16T21:40Z — board 6 host agent, halted pending fix

- 21:09Z: the user reported stable Wi-Fi, confirmed by probes (ping 12 ms;
  API and github.com about 0.1 s). The gated resume passed its stability
  window, and session 29 landed on board 6 and passed its board check.
- 21:29Z: MRB0-087 rep 2 lost its connection 18 s after GO with the same
  platform error as MRB0-075 (`4502: Host agent /stream failed (503): host
  agent unreachable`), on the same board and with the same timing. The
  attempt is recorded as `transport_error`; board 6 was released (reset job
  `92092c12`), and the campaign halted.
- Conclusion: in both confirmed failures, board 6's host agent dropped
  `/stream` about 15–18 s into a solve. Boards 1, 2 and 3 have sustained
  long solves, apart from two board-3 drops during the 2026-10-15
  redeploy. The runner cannot choose or avoid a board.
- User decision: report board 6 to Manhattan Reasoning, then clear the halt
  and run rep 3 once it is fixed or removed from assignment. The evidence
  is in `board6-incident.md`.
- State: **rep 1 68/68 and rep 2 68/68 complete** (rep 2: 65 scored, 3
  `transport_error` — MRB0-072, 075, 087); rep 3 0/68. Quota 529/1000
  build-minutes used. Nothing is running and no board is held.

## 13. Update 2026-10-18T05:30Z — epoch 2: skip board 6, rep 3 started

- The user asked to run rep 3 without board 6. `POST /submit` has no board
  field, so the runner gained a bounded skip rule (`SKIP_FPGA_IDS=(6,)`,
  `MAX_BOARD_SKIPS=3`): a build that lands on board 6 has its session
  released before any board I/O and is rebuilt; a 4th consecutive landing
  stops the run. Both settings are part of the config identity.
- Verification: two new tests (both fail with the rule disabled); full
  suite 180 passed; independent review APPROVE with no blocking findings.
  The reviewed diff was taken against a baseline reconstructed
  byte-for-byte to the frozen organizer hash (`1a8480c3…`).
- **Identity epoch transition** (`run.json` → `identity_epochs[0]`,
  `halt_clearances[2]`, `phase_resets`): the epoch-1 identity and its
  qualification record (`qualification.epoch-1.json`) are preserved. The
  full local qualify was re-run under the new organizer hash and passed
  every gate (RTL semantic, abort, six pilots, PnR fits at 50 MHz, Fmax
  76.6 MHz). Every `attempt.json` carries its own identity snapshot: reps 1–2
  ran under epoch 1, and rep 3 runs under epoch 2.
- 04:52Z: the first epoch-2 build (`d21d1312`) built fine, but the platform
  failed to flash it onto board 0 (`Host agent /flash failed (502): FPGA at
  192.168.1.101:1234 never came up within 10.0s after flashing`). The runner
  stopped as designed (14 build-minutes). Board 0 had shown `error` for days
  before turning `idle`.
- 05:13Z: relaunched. Build `e703b85d` landed on board 5, session 30
  qualified, and rep 3 started with MRB0-002 at 05:28Z. Quota 543/1000
  build-minutes used before this build.

## 14. Update 2026-10-18T15:40Z — second board-0 flash failure; auto-relaunch rule

- 05:28–09:27Z: sessions 30–34 (boards 5, 1, 3) ran rep 3 for MRB0-002 …
  MRB0-030; all 19 outcomes match reps 1–2.
- 09:27Z: build `deabdccf` built fine, but the platform again failed to
  flash board 0 (`Host agent /flash failed (502) … never came up within
  10.0s`). No session was created and nothing was held. This is the second
  board-0 flash failure; each cost 14 build-minutes.
- User decision: auto-relaunch on this platform flash error only. Supervisor
  v4 (`/tmp/pigweed-supervise4.sh`; the runner and its identity are
  unchanged) relaunches after a stop only when the most recent build failed,
  never got a session, `run.json` has no halt, and the build log's final
  line is `Host agent /flash failed`. At most 3 relaunches in a row, and the
  counter resets when new attempts are recorded. The detector was checked on
  the real stop (accepted) and on three negative variants (session
  assigned, non-flash failure log, halt present: all refused). Every other
  stop still waits for a human.
- 15:19Z: relaunched under v4. Build `f4b6530b` landed on board 5, session
  35 qualified, and rep 3 resumed at MRB0-032. State before this session:
  rep 3 19/68, 49 left; quota 629/1000 build-minutes used.

## 15. Update 2026-10-18T17:20Z — operator-caused halt, resumed

- 16:55:52Z: the coordinator sent SIGTERM to the runner after misreading a
  user "stop run" that referred to a separate documentation-research job.
  The in-flight MRB0-055 rep 3 attempt-001 was killed and recorded as
  `interrupted` (non-terminal). Board 1 was released (reset job `60c0e6c0`)
  and the run halted as designed.
- The user clarified that the campaign should keep running one board at a
  time. The halt was cleared with this justification (`run.json` →
  `halt_clearances[3]`) after confirming no own boards or jobs were held.
- 17:02Z: relaunched under supervisor v4. Build `37790052` landed on board 5,
  session 37 qualified, and MRB0-055 rep 3 is re-running as attempt-002.
- Accepted residual (supervisor v4): its flash-failure detector inspects
  journal state only. After a board-0 flash failure, a later pre-submit stop
  (for example the quota floor) could also be read as a flash failure and
  relaunched, at most 3 times. Such relaunches submit no builds.

## 16. Update 2026-10-18T20:45Z — board-0 streak, relaunch, back on board 3

- 17:17–18:01Z: session 37 (board 5) finished MRB0-055 (attempt-002,
  timeout) through MRB0-067 rep 3; every outcome matches reps 1–2.
- 18:01–19:30Z: the platform sent 4 of 5 builds to board 0, and all 4
  flashes failed with the same `never came up within 10.0s` error (builds
  at 18:18, 18:37, 18:56 and 19:30Z). The other build landed on board 6 and
  was skipped before any board I/O. Supervisor v4 used its 3 automatic
  relaunches and stopped; nothing was held.
- The user chose to relaunch with a fresh set of 3 automatic retries. At
  20:18Z a local network error (`OSError 22`) crashed the runner while it
  polled build `3abfe873`. After the stability gate, reconcile released that
  build's session (it had landed on board 6; reset job `aee37104`).
- 20:41Z: build `f6a95ec2` landed on board 3, session 38 qualified, and rep 3
  resumed at MRB0-068.
- State: rep 3 52/68 before this session (16 left, about 6 sessions).
  Quota 767/1000 build-minutes used. The board-0 failures, the board-6
  skip and the crash-orphaned build cost about 98 build-minutes since 18:01Z.

## 17. Final — campaign complete 2026-10-19T01:53Z

- Rep 3 finished on boards 3, 1 and 5 (sessions 38–43). There was one more
  board-0 flash failure (`18cbef71`, 00:27Z), relaunched automatically, and
  two more board-6 skips (`4e7a9374`, `dfb12460`). The runner exited with
  `run: campaign complete` and phase `run_done`.
- **Final counts** (204 attempts): 51 SAT, 6 UNSAT, 66 timeout, 78
  resource error, 3 `transport_error` (all rep 2). Per ID: 17 SAT, 2 UNSAT,
  23 timeout and 26 resource error, identical in every scored repetition.
  All 45 non-timeout IDs have bit-identical cycles across repetitions.
- `report` (2026-10-19T01:53:25Z): exit 0, `identity_ok: true`, 0 binding
  errors.
- Release verification: all 46 assigned sessions have a journal chain from
  `release_accepted` to `release_terminal` (complete, session gone), and all
  51 release jobs read `complete` on the live API. No board or job of ours
  remained.
- Clock evidence over 51 clean attempts of at least 60 s: 0.9960–0.9999 ×
  50 MHz.
- Spend: 63 build jobs on the account (62 for this run), 879/1000
  build-minutes; the `/usage` builds list is capped at 50 entries. Totals
  across the campaign: 7 board-0 flash failures, 3 board-6 skips, 3
  platform transport drops, and several local-network crash recoveries.
