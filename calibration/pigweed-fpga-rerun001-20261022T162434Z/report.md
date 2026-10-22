# PigWeedSAT native FPGA benchmark run

Generated 2026-10-22T18:25:39Z.

## Contract

- Unmodified PigWeedSAT candidate (frozen snapshot in `candidate/`), cfg `H.pigweed(H.Config(lit_page=16))`, P=16.
- 50 MHz system clock and timing target; 2,600 s **host** solve deadline; 1 repetition; host-observed timing only — no device-enforced solve deadline is claimed.
- Scope: 1 requested ids, of which 1 are eligible and planned.
- All 210 manifest rows retained; eligibility from fresh encoder acceptance + semantics/field safety + validated CPU certification (CPU evidence: `calibration/cpu-v0` (solve 1000 s / check 3000 s), `calibration/cpu-v1-5000s` (solve 5000 s / check 20000 s); later runs override earlier ones per id).

## Outcomes

- status counts over planned repetitions: `{"timeout": 1}`
- eligible ids (whole inventory): 73 of 210 (`{"eligible": 73, "non_fitting": 122, "uncertified": 57}`)
- median host total (validated completions): None s
- median device cycles (validated completions): None
- CPU-vs-FPGA speedups and competition scores are intentionally absent: different timing contracts.
