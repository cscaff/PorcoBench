# Incident report: FPGA board 6 host agent drops `/stream` during long solves

Prepared 2026-10-16 for Manhattan Reasoning support. Account: `mhidalg3`.
Client: the official SDK at commit `d77d68d1` (0.1.10), with the persistent
WebSocket `/fpga/{id}/stream` transport. The design is a frozen PigWeedSAT
build at 50 MHz, and every build passed the platform build.

## Summary

On board 6 the `/stream` connection is closed by the server about 15–20 s
into a long-running solve, with this server error:

```
server closed with 4502: Host agent /stream failed (503): host agent unreachable
ConnectionClosedError(Close(code=4502, reason='FPGA connection fai…
```

Short operations on board 6 work: formula load (~1.7 s over the bus) and the
sub-2-second check solves succeed. The drop happens while the client polls a
CTRL register once every 50 ms during a solve that is still running. The
same design and the same polling pattern have run solves of up to 1,000 s on
boards 1, 2 and 3 across 26 sessions. The only exceptions were two
connection drops on board 3 during the platform redeploy on 2026-10-15
(17:43Z and 20:09Z).

The client network was healthy at the time of the 21:29Z drop: ping to
1.1.1.1 averaged 12–17 ms, and the API and github.com answered in about
0.1 s.

## Occurrences on board 6

| UTC | Build job | Session | What happened | Reset job |
|---|---|---|---|---|
| 2026-10-16 04:04:19 | `7ba68d8e-4460-4684-987c-61f1d0cdfc9a` | `652cef12-b679-4982-8309-38f656654b32` | Check passed; solve started 04:04:30; **4502/503 "host agent unreachable" ~15 s after start** | `ec1dfae2-fa9e-43dc-aa08-0ab1c1505e9b` |
| 2026-10-16 19:35:42 | `48511b5b-e954-4450-a908-a1a38f3c476f` | `69f4c6b3-0799-462e-82e5-3462b043fee3` | Check solves were slow (3–10 s each); connection lost during the abort test. The error text was not captured. Our local link was degraded at this time, so this one is inconclusive | `9e7793dd-bfb8-403c-9195-4bc94d10a713` |
| 2026-10-16 21:28:47 | `0fe92751-578f-4fb0-8a1d-e89128b7440c` | `00a388c4-25d5-4c22-80f1-d55916757efe` | Check passed (solves 0.8–1.9 s, abort test OK); solve started 21:29:00; **4502/503 "host agent unreachable" ~18 s after start** | `92092c12-31cf-4dd9-ab22-20821c130088` |

Each session was released immediately through
`POST /fpga/6/session/release`, and every reset job completed.

## Request

Please check board 6's host agent: its logs around 04:04:30Z and 21:29:00Z
on 2026-10-16, and its health under sustained `/stream` traffic. Either
repair it or take it out of build assignment. Three of our last four
sessions that reached the board check (#26–#29, on boards 6, 1, 6 and 6)
were placed on board 6. Each failure costs a full build (~14
build-minutes) and loses a benchmark measurement. If there is any supported
way to steer an account's builds away from a board, or onto a specific
board, please tell us; `POST /submit` has no board field.
