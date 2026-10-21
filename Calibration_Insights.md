# CPU calibration and PigWeedSAT readiness: insights

Companion to `FPGA_Readiness_Plan.md`. Covers how the verification jobs and
smoke tests went, what we learned, where the benchmark stands, next steps, and
answers to follow-up questions. Artifacts: `calibration/cpu-v0/` (CPU
campaign), `calibration/pigweed-v0/` (loader screen).

## 1. Verification jobs

All verification passed in its final form. Every early failure came from a
test-script edit or a restart I chose; none was a certification defect.

| Job(s) | What it did | Result |
|---|---|---|
| bg_47 | Gave drat-trim an invalid proof (`0`) for a satisfiable formula | First try hit a wrong file path. The retry printed `s NOT VERIFIED`, exit 1, and was correctly left uncertified |
| bg_48, bg_51, bg_53, bg_54 | Launched and watched three early campaign runs | Stopped before any instance finished, so harness fixes could land first. Kept as `cpu-v0-aborted-attempt{1,2,3}`. The first stop deleted one partial run that had no results |
| bg_50 | Re-ran the tests after an edit | 2 errors: my edit had dropped a test variable. Fixed, then all passed |
| bg_55–bg_86 | Monitored the final campaign every 5–45 min | Steady progress. Free disk went from about 1010 to about 968 GiB |
| bg_87 | Completion watcher | Faulty: it searched for the campaign by command text and matched itself, so it could never exit. Cancelled; see §6.3 |
| bg_88 | Replacement watcher, tracking process ID 96005 | Campaign finished: 210 records, 148 certified, exit 2 (finished with unresolved results), as designed. Elapsed time from file timestamps: 2026-10-09 23:15:53 to 2026-10-11 09:49:09 EDT, **34 h 33 min**. That is 23.0 h of summed solver wall time plus 5.5 h of checker time, with the rest spent on proof compression and I/O. (An earlier draft said 14.2 h; that was only how long this watcher ran.) |
| bg_89 | `--report-only` re-verification of every saved record | Exit 2. Every evidence hash and every gzip proof decompression matches; the manifest is unchanged |
| bg_90, bg_91, bg_93 | Smoke tests plus the hardened validator over all 210 real records | 0 violations, including re-deriving each of the 148 certificates from its saved evidence. The executed harness still reproduces exit 2 |

## 2. CPU smoke tests

`run_smoke.py` pushes four tiny formulas through the real pipeline: preflight,
solve, check, report and exit code, using the pinned Kissat and drat-trim.

| Fixture | What it tests | Result |
|---|---|---|
| `SMOKE-SAT` | Normal SAT path | Model x1 = x2 = true found, checked independently, and agrees with its label |
| `SMOKE-TRIV` (units `1`, `-1`) | Checker's trivial-UNSAT path | Ordinary verified UNSAT, exit 0. The trivial path fires only on an explicit empty clause |
| `SMOKE-UNSAT` | Normal binary-proof check | Verified |
| `SMOKE-MISLAB` (satisfiable formula labelled UNSAT) | Label-conflict handling | Certified SAT, flagged as a conflict; the run exits 2 |
| `--report-only`, then one byte changed in a saved input | Evidence integrity | Re-verify gives exit 2; the tampered run fails with exit 1 and a hash mismatch |

Other checks I ran directly against the real binaries:
- An invalid proof is never certified.
- A corrupted or truncated SAT model is rejected.
- An explicit empty clause takes the checker's exit-1 trivial path, and that is accepted.
- Resume reuses finished results; changing any setting makes it refuse to continue.
- A run past its deadline is killed and cleaned up.
- A child process whose output hits the file-size limit is killed.

Unit tests: 63 (`test_calibrate_cpu.py`) and 15 (`test_screen_pigweed.py`), all
passing. The final independent review returned APPROVE with no findings.

## 3. What we learned

- **drat-trim (pinned commit):**
  - When its own time limit hits it prints `s TIMEOUT` but exits 0, so the exit code alone means nothing.
  - Status lines start with a hidden carriage return.
  - In binary-proof mode it reads a `c` comment line inside the CNF body as an empty clause, and then prints trivial-UNSAT / `s VERIFIED` even for a satisfiable formula. None of the 210 files has a comment line, and no recorded certificate used that path. The harness now accepts the path only when the original formula has a real empty clause.
- **Kissat:**
  - It prints its statistics when killed. The "385 s" figure seen early on was the moment I stopped it, not a solve time.
  - Proofs are huge: up to 2.2 GB for a certified UNSAT, and 2 runs hit the 8 GiB cap. Streaming the proof compression was necessary.
  - Its memory figure is inflated about 1024× on macOS. Do not cite it.
- **Process:**
  - The delegated build runners failed with backend errors, so I ran the builds directly with logs kept.
  - Three restarts came from review fixes that had to land before the harness was frozen.

## 4. State of the benchmark

| Tier | CPU certified | Unresolved | Loadable, P=16 | Loadable, P=8 | Loadable and certified (P=16) |
|---|---|---|---|---|---|
| S | 9/19 | 10 | 19 | 19 | 9 |
| S-tight | 60/71 | 11 | 69 | 71 | 59 |
| M-low | 47/68 | 21 | 0 | 3 | 0 |
| M-high | 32/52 | 20 | 0 | 0 | 0 |
| **Total** | **148** | **62** | **88** | **93** | **68** |

- **Unresolved reasons:** 54 solver timeouts, 5 `s UNKNOWN` (Kissat's own 1000 s limit fired just before ours, so effectively timeouts), 2 hit the proof cap, 1 checker timeout. No unresolved result inherits a GBD label, and the 148 certified results show 0 label conflicts.
- **Difficulty spread (certified solve times):** 14 under 0.1 s, 23 in 0.1–1 s, 16 in 1–10 s, 43 in 10–100 s, 52 in 100–1000 s. The median is 39 s.
- **S is small but hard:** 10 of its 19 instances are unresolved, 8 of them from the `sgen` family (deliberately small, hard formulas).
- **FPGA fit:** at the baseline P=16 no M-tier instance loads. P=8 loads 3 M-low instances: MRB0-096 (certified UNSAT), MRB0-102 (certified SAT) and MRB0-108 (uncertified). All three start at 0.92–0.99 occupancy, which leaves almost no room for learned clauses.
- **Scoreable set today:** 68 of 210 (32%) can get validated FPGA timing.
- **Pilots:** MRB0-005, 011, 017, 026, 077, 078. M-low and M-high are gaps.

## 5. Next steps

**Decisions for you:**
1. **M-tier direction.** Either fund work on PigWeedSAT's memory limits (clause count, variable count, stores), checked against the 183 available BRAM blocks, or change the corpus. Changing the corpus needs the missing tier-generation script. A third, smaller option is whether to run the whole campaign at P=8, which adds 3 M-low instances.
2. **The 62 unresolved.** These need a separate CPU budget: longer limits, more seeds, or a higher proof cap. The cheapest single step is MRB0-037: its 1.7 GB proof is saved, so it only needs a longer checker run.
3. **Disk.** Keep or delete `cpu-v0-aborted-attempt{1,2,3}`?

**Ready once approved, per `FPGA_Readiness_Plan.md`:**
4. Build the external-corpus adapter (1000 s deadline, 50,000,000,000 cycles; no acceptance of UNSAT without a label).
5. RTL pilot on the six pilot IDs.
6. Route gate at 50 MHz with ≤ 208 BRAM blocks and ≤ 83,640 LUTs.
7. Board gate.

**Caveat:** all times are single-seed and proof-enabled. They are not proof-free speed and not FPGA predictions.

## 6. Follow-up questions

### 6.1 How do we know M-tier is not viable for PigWeedSAT without running it?

Kissat ran all 210 formulas, SAT and UNSAT alike; the 77/71 split is the
certificate outcome, not a choice of inputs. Its timings say nothing about
PigWeedSAT. The PigWeedSAT screen never ran a solver either. It called
PigWeedSAT's own unchanged host loader (`satlat/host.py: build_images`),
which refuses any formula that does not fit the fixed memory sizes compiled
into `design.py`. This establishes capacity only, not whether PigWeedSAT can
solve what fits:

| Limit | Value |
|---|---|
| Variables (`N_MAX`) | 2048 |
| Clauses (`C_MAX`, original plus learned) | 4096 |
| Literal-store words (`LE_MAX`) | 16384 |
| Clause-store words (`CE_MAX`) | 16384 |

M-tier overshoot, measured from the manifest and the screen:
- 98 of 120 have more than 4096 clauses. The median M-tier formula has 5840 clauses, 1.43× the limit.
- 15 have more than 2048 variables.
- The 20 that fit both counts still overflow a store at P=16: minimum 1.01×, median 1.52× of the limit. There are two separate stores: the literal-occurrence store (`LE_MAX`, packed in P-word pages, so P changes its size) and the clause-body store (`CE_MAX`, fixed 4-word pages, so P cannot fix an overflow there).

A refused formula is never dispatched, so a board run of these instances would
stop on the host before the FPGA sees anything. Two caveats:
- **P=8 is a runtime register (`R_LITPAGE`), not a rebuild.** At P=8 three M-low instances load, at 0.92–0.99 initial occupancy.
- **This covers the frozen configuration only.** Larger constants need a rebuild and a check that it still fits in BRAM. Shrinking inputs by preprocessing would change the benchmark formulas, which is a corpus decision.

Fitting is necessary, not sufficient: loading proves neither room for learned
clauses nor a correct answer.

### 6.2 Should a teammate run the manifest on PigWeedSAT on the FPGA platform?

**Not the full manifest yet.** 122 of 210 instances cannot load, and the
existing pipeline is not fit for this corpus:
- `satbench/runner.py` hardcodes a 30 s scoring timeout, a 60 s watchdog and a 2,000,000-cycle simulation cap.
- The 30 s deadline is built into the wrapper as a constructor constant (`DEADLINE_CYCLES`). A 1000 s protocol needs a rebuilt wrapper.
- `validate_answer` accepts UNSAT without a label.
- `satbench prepare` cannot read this manifest.

Results from that path would not be comparable to the CPU calibration.

**Useful now, with approval for platform and build cost:**
- The **route gate**: build the wrapped design and report LUT/BRAM use and 50 MHz timing. This does not depend on the corpus.
- An **RTL simulation pilot** of the six pilot IDs, once the adapter exists.

What to send the teammate:

| File | Why |
|---|---|
| `Benchmark/FPGA_Readiness_Plan.md` | Protocol and gates: 1000 s device deadline, 1060 s watchdog, 50 MHz, 3 repetitions, resource ceilings, eligibility rule |
| `Benchmark/manifest.csv` | IDs, GBD download URLs and SHA-256 hashes; they can fetch each CNF and verify `cnf_sha256` |
| `Benchmark/calibration/pigweed-v0/rows.csv`, `summary.json` | Which IDs are dispatchable at P=16; the pilot list |
| `Benchmark/calibration/cpu-v0/results.csv` | Certified kind per ID. Eligibility is `dispatchable=true AND cpu_certified=true`, and FPGA UNSAT answers are validated against these certificates |
| `Benchmark/calibration/pigweed-v0/run.json` | `host.py` and `design.py` hashes, to confirm they build the same frozen candidate |
| Optional: `Benchmark/cnf/<hash>.cnf.xz` for the pilot IDs | Small files, if you are happy to share directly rather than via GBD links |
| Optional: `Benchmark/screen_pigweed.py` | To re-screen against their own checkout |

Do not send the proofs (gigabytes; FPGA UNSAT is checked against the CPU
certificate record, not the proof), the aborted run directories, or `.tools/`.
The teammate needs their own platform credentials; never put keys in shared
files. An FPGA SAT answer is checked against the original CNF, so Kissat's
witnesses are not needed either.

### 6.3 Does bg_87 need re-validation?

No. bg_87 was only a watcher: a shell loop that read the console log. It
neither wrote files nor validated anything. Its failure to exit was my bug,
because the search for the campaign's command text matched its own command
line. Cancelling it was intended and harmless:
- The campaign was launched independently (`nohup`, detached) and kept running.
- bg_88 watched the real process ID until exit and recorded completion: 210 records, `CAMPAIGN_EXIT=2`.
- bg_89 (`--report-only`) and bg_91/bg_93 (hardened validator) then re-checked every record independently: 0 violations.

### 6.4 Is the benchmark too difficult, given the M1 Max Kissat run?

**As a CPU benchmark, no.**
- Kissat is a state-of-the-art solver, and it certified 70% of instances in 1000 s, with times spread across every bin up to 1000 s.
- Nothing saturates in either direction: neither everything trivial nor everything unsolved.
- The unresolved 62 are an upper bound on "too hard". Competitions allow 5000 s, and proof logging adds I/O; that some timeouts would resolve proof-free is [INFERENCE], not measured.

**For PigWeedSAT, the binding constraint is capacity, not difficulty.** 122 of
210 instances do not load at all. Of the 68 eligible instances, Kissat solved:

| Kissat solve time | Count |
|---|---|
| Under 1 s | 27 |
| 1–100 s | 25 |
| 100 s or more | 16 |

A 50 MHz FPGA solver without Kissat's preprocessing will likely be slower on
the hard ones [INFERENCE, unmeasured]. The realistic scoring signal is
therefore the roughly 27–52 easier eligible instances: thin, but not empty.

**The shape is the issue.**
- S is small but front-loaded with hard crafted formulas (8 unresolved `sgen` instances).
- The tier labels do not track PigWeedSAT's capacity: S-tight loads almost entirely, M not at all.
- There is no gentle difficulty ramp within the sizes that fit.

Before changing the corpus, measure FPGA difficulty directly with the six-ID RTL
pilot. Any corpus change needs your approval and the tier-generation script.

### 6.5 Can the loader be improved to accept more?

Very little can be gained from the loader alone. It mostly enforces fixed
hardware memory sizes, and the hardware reads exactly the layout the loader
writes.

**Without a rebuild:**
- Setting P=8 globally takes acceptance from 88 to 93 (from 68 to 71 certified).
- Choosing P per instance adds nothing more: P=8 already accepts every CNF that P=4 or P=16 accepts.
- A tighter memory layout (for example no full page for a literal polarity that never occurs, or denser clause pages) would need matching RTL changes, because the hardware walks and extends these exact structures.
- Shrinking formulas by preprocessing changes the benchmark input; see §6.6 for what it gains (measured) and what it costs.
- Squeezing more in has limited value anyway: the clause limit also has to hold learned clauses, so CNFs that only just fit (e.g. MRB0-096 at 93% full) may fail at run time.

**With a rebuild (larger capacities in `design.py`).** This is a host-packing
counterfactual, not a feasible loader improvement. `Benchmark/fit_whatif.py
capacity` re-runs the real unchanged loader with only the capacity constants
patched in memory:
- Derived field widths and the RTL memories are not re-elaborated.
- Nothing is synthesized.
- No PigWeedSAT file is changed.
- Output: `calibration/whatif-v0/capacity.json`.

Only synthesis and place-and-route of a resized design can show that the extra
CNFs are actually implementable.

| Hypothetical capacities | Accepted, P=16 | Certified, P=16 | Accepted, P=8 | M-low / M-high accepted (P=8) | Solver RAM bits vs today |
|---|---|---|---|---|---|
| Today: 2048 vars, 4096 clauses, 16K-word literal-occurrence store + 16K-word clause-body store | 88 (41.9%) | 68 | 93 | 3 / 0 | ×1.00 |
| Literal-occurrence and clause-body stores ×2 | 107 (51.0%) | 82 | 110 | 20 / 0 | ×1.56 |
| Clauses ×2, both stores ×2 | 130 (61.9%) | 99 | 136 | 46 / 0 | ×1.69 |
| Everything ×2 | 130 (61.9%) | 99 | 137 | 47 / 0 | ×1.97 |
| Vars ×2, clauses ×3, both stores ×3 | 167 (79.5%) | 122 | 194 | 62 / 42 | ×2.66 |
| Everything ×4 | 191 (91.0%) | 137 | 207 | 66 / 51 | ×3.91 |

The limit is on-chip memory (block RAM):
- The most recent recorded full-SoC build (`PigWeedSAT/build/pnr.json`, scope `soc`, 50 MHz, timing met) uses 147 of 208 block RAMs and 17,551 of 83,640 LUTs, leaving about 61 block RAMs free. That build's design hash has not been matched to the current `design.py`, so treat these numbers as indicative only.
- The four store-sized RAMs are about 56% of the solver's RAM bits (computed by the script): the literal-occurrence store, the clause-body store, and the two location maps linking them. Doubling them needs roughly +56 to +64 block RAMs, because the address fields also gain a bit [INFERENCE from RAM shapes, not a build].
- So "stores ×2" (51% accepted) is about the most this chip might hold, and it is marginal. Anything that also doubles clauses or variables almost certainly does not fit.
- Logic is not the constraint (about 21% of LUTs used), so moving small memories into LUT-based RAM could free some block RAM, at the cost of logic.

Conclusion: real gains need a hardware rebuild, and the chip's memory caps them
at roughly half the benchmark. Only a real build can confirm fit and 50 MHz
timing. Accepting most of the M tier would need a larger FPGA or a different
memory architecture. In every case, acceptance says nothing about whether
PigWeedSAT can solve the CNF.

### 6.6 How can formulas be shrunk by preprocessing, and what is lost?

Preprocessing rewrites a CNF into a smaller formula that is satisfiable exactly
when the original is (equisatisfiable). It is not an equivalent formula.
Typical steps, all in Kissat:
- unit propagation and removal of satisfied clauses;
- subsumption (dropping clauses implied by shorter ones);
- bounded variable elimination (resolving a variable away when that does not grow the formula);
- equivalence and gate substitution;
- probing;
- variable addition, which introduces new variables to shorten many clauses.

**Measured gain** (`Benchmark/fit_whatif.py preprocess`; output
`calibration/whatif-v0/preprocess.json`). Each original CNF went through the
pinned Kissat with only its initial preprocessing
(`--conflicts=0 -o simplified.cnf`). Variables were then renumbered compactly,
and the unchanged loader was run at today's capacities:

| Tier | Median clauses kept | Median variables kept | Accepted at P=16 after preprocessing |
|---|---|---|---|
| S | 99% | 102% | 19/19 (unchanged) |
| S-tight | 99% | 100% | 70/71 (+1) |
| M-low | 80% | 120% | 6/68 (+6) |
| M-high | 93% | 97% | 0/51 (+0; 1 more was solved outright by preprocessing) |

- **Overall at P=16:** 95 accepted instead of 88. That is +7, of which 6 are CPU-certified, and none of the original 88 is lost.
- **Overall at P=8:** 122 accepted instead of 93. The gain is mostly M-low (30 accepted); M-high reaches 2.
- **MRB0-196** (M-high) is solved as UNSAT by preprocessing alone.
- **Variables can go up:** variable addition raises the median M-low variable count to 120%.

**What is lost:**
1. **It is no longer the benchmark formula.** The FPGA would solve a derived, equisatisfiable CNF. Results stop being comparable with other solvers or submissions run on the original CNFs.
2. **SAT answers can't be checked against the original.** A model of the simplified formula is generally not a model of the original. Rebuilding one needs the preprocessor's reconstruction stack, which Kissat's `-o` output does not include. Without it, an FPGA SAT answer cannot meet the rule that SAT models satisfy the original formula.
3. **The CPU does part of the work.** Preprocessing can do substantial solving (MRB0-196 is solved outright). FPGA timing would then measure a CPU+FPGA pipeline, and the preprocessing time would have to be counted and reported.
4. **More to trust.** An UNSAT answer is only valid for the original formula if the preprocessor is correct. Our validation still compares against the CPU certificate, but the chain now has one more component.
5. **Version dependence.** The simplified CNFs depend on the Kissat version and settings. They would have to be frozen, hashed and published as new inputs, which makes this a corpus change.
6. **No new headroom.** CNFs that only just fit still leave little room for learned clauses.

Conclusion: preprocessing helps little at the baseline P=16 (+7) and more at
P=8 (+29). It breaks direct SAT validation unless a preprocessor with model
reconstruction is used, and it changes what the benchmark measures. That is a
protocol and corpus decision for you, not a loader fix.

### 6.7 Glossary: variables, literals, and PigWeedSAT's two stores

- **Variable:** a yes/no unknown, e.g. x1. In DIMACS, variables are numbered 1..N.
- **Literal:** a variable or its negation, e.g. x1 or ¬x1. In DIMACS these are written `1` and `-1`. N variables give 2N literals.
- **Clause:** an OR of literals. `1 -2 3 0` means (x1 ∨ ¬x2 ∨ x3).
- **CNF:** an AND of clauses. A model makes every clause true.

PigWeedSAT stores the same formula twice, indexed two ways:
- **Clause-body store** (`CE_MAX` = 16,384 words) answers "which literals does clause c contain?". Each clause takes 4-word pages: 3 literals plus a next-page pointer. The clause above uses one page: `1, -2, 3, 0`.
- **Literal-occurrence store** (`LE_MAX` = 16,384 words) answers "which clauses contain literal ℓ?". When the solver sets x2 = true, it walks the list for ¬x2 to find the clauses that just lost a true option. Each literal has a chain of P-word pages, each holding P−2 clause IDs plus 2 pointers. The clause above adds its ID to the lists for x1, ¬x2 and x3. This is the only store that P affects.
- **Location maps** (`c2l`, `l2c`) link matching entries between the two stores so learned clauses can be deleted cleanly. They are the same size as the stores.
- **Clause slots** (`C_MAX` = 4096) are separate from store words. They count clauses, original plus learned; each needs a metadata entry.
- **Variable limit** (`N_MAX` = 2048) sizes the per-variable memories, including the 2048-entry answer stack.

There are not "two clause stores". Earlier wording in this session that said so
was wrong: the two big memories are the clause-body store and the
literal-occurrence store.
