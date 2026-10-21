# PigWeedSAT native FPGA benchmark run

Generated 2026-10-19T01:53:25Z.

## Contract

- Unmodified PigWeedSAT candidate (frozen snapshot in `candidate/`), cfg `H.pigweed(H.Config(lit_page=16))`, P=16.
- 50 MHz system clock and timing target; 1,000 s **host** solve deadline; three repetitions; host-observed timing only — no device-enforced solve deadline is claimed.
- All 210 manifest rows retained; eligibility from fresh encoder acceptance + semantics/field safety + validated CPU certification.

## Outcomes

- status counts over eligible-id repetitions: `{"resource_error": 78, "sat": 51, "timeout": 66, "transport_error": 3, "unsat": 6}`
- eligible ids: 68 of 210 (`{"eligible": 68, "non_fitting": 122, "uncertified": 62}`)
- median host total (validated completions): 8.9199 s
- median device cycles (validated completions): 50277839
- CPU-vs-FPGA speedups and competition scores are intentionally absent: different timing contracts.
