# A fixed ~3-second stall hits ~1 in 30 live requests, and it sits upstream of uvicorn

**Date:** 2026-09-28 (evening) to 2026-09-29 00:16Z
**Ticket:** #193 (epic #185, ADR 0188 §3 item 0)
**Prompt:** Found while timing the #186/#187 deploy of `1078389`. Joe said "go ahead with #193".
**Instruments:**
- A scratch probe from the laptop (httpx, keep-alive, one request a second, the session cookie minted from `.env` the way `scripts/time_live_routes.py` does). It is not committed, because it is `time_live_routes.py`'s cookie and client in a loop.
- `curl -w` phase timings, with a fresh connection each request.
- `inspect_live_db.py read-incidents -n 40` (cheap).
- `scripts/probe_loopback_latency.py`, in-box (§C, pending).

**Cost:** zero credits, zero tokens. Every request was a GET, and the probe rate was one a second.

## What this establishes

- **The stall is a fixed ~3.1 s, not a slow tail.** Every slow request landed between 3,091 and 3,206 ms. The rest had a p50 of 91–98 ms and a p95 of 109–134 ms.
- **It is not route-specific.** It hits `/api/health`, `/api/signal` (a cache hit, which runs no SQL), `/api/window`, and a 404 page that **Next answers without calling the backend**, at similar rates.
- **It sits after the TLS handshake.** On every slow `curl`, DNS was ≤ 6 ms, TCP connect ≤ 46 ms and TLS ≤ 70 ms, and time-to-first-byte was ~3.16–3.21 s. So it is on the server side of Fly's edge, not on the laptop's network.
- **uvicorn itself does not show it.** The recorder probes `127.0.0.1:8000/api/health` on every pass with a 2 s threshold and records failures as `health_probe` incidents. The table holds **zero** such rows, ever. That count is a floor, because the writer never raises.

## What this does not establish

- **Which of the two remaining hops it is**: Fly's proxy into the machine, or Next's server on :3000. §C takes that reading.
- **That it predates today.** The 2026-09-18 table's single-rep maxima of 3,893, 3,663, 2,771 and 2,578 ms are consistent with a fixed +3 s. So is the 2026-09-17 "5,231 then 3,101 ms" signal miss. Neither was timed per phase, so this is a fit, not a proof.
- **A rate to quote.** The three probe runs gave 7/286, 8/150 and 13/453. That is one evening from one client, and the runs are not independent.
- **That the stalls are independent across a page's parallel calls.** So "a page load meets one ~10–20% of the time" (#193) is arithmetic on an assumption.

## §A — The laptop probes

| run | UTC | method | requests | stalls (3.09–3.21 s) | p50 | p95 |
|---|---|---|---|---|---|---|
| 1 | 21:51–21:56 | keep-alive, `/api/signal` + `/api/window` alternating | 286 | 7 | 98 | 134 |
| 2 | ~22:00 | `curl`, a fresh connection each time, `/api/signal` | 150 | 8 | — | — |
| 3 | 00:08–00:16 | keep-alive, `/api/health` + `/api/signal` + `/no-such-page-probe` round-robin | 453 | 13 (health 3, signal 5, 404 page 5) | 93 | 116 |

Run 3's stall times: 00:11:31.576, 11:45.695, 12:02.815, 12:33.923, 12:48.054, 13:25.190, 13:54.333, 14:11.435, 14:27.564, 14:44.688, 15:32.808, 15:47.948, 16:22.102. The gaps are 14, 17, 31, 14, 37, 29, 17, 16, 17, 48, 15 and 34 s, which cluster near 15 s and its multiples. Fly's health check hits `:3000/api/health` every **15 s** (`fly.live.toml [checks.health]`). That is a lead, not a finding: the probe's own 1 s cadence quantises every gap, and nothing here yet ties a stall to a check.

A fourth, accidental run (00:02–00:08) sent `C:/Program Files/Git/api/health`. Git Bash rewrote the leading `/` (`tasks/lessons.md` 2026-09-28), so 173 requests went to a Next 404 page, and one took 3,098 ms. It is counted nowhere above. It is the first observation that a request Next answers alone stalls too.

## §B — Where each hop has been read

| hop | evidence | stalls? |
|---|---|---|
| laptop → Fly edge (DNS, TCP, TLS) | `curl -w`, 150 requests | no: ≤ 70 ms to TLS done on every slow request |
| Fly edge → machine → Next → uvicorn | every public probe | **yes** |
| Next alone (a 404 page; the middleware makes no backend call, `frontend/src/middleware.ts`) | run 3 | **yes**, at the same rate |
| uvicorn direct (`127.0.0.1:8000/api/health`) | `health_probe` incidents: 0 in the table's life | no |

**Remaining:** Fly's proxy → machine, or Next's server on :3000.

## §C — In-box probe (pending)

`scripts/probe_loopback_latency.py` times uvicorn, Next's proxy and Next alone over loopback from inside the box.
- If `next-*` stalls, the stall is in Next.
- If none do, it is in Fly's proxy hop.
- **Caveat:** the probe opens a fresh connection per request. A stall that lives only in Fly's pooled-connection reuse into :3000 would not show here, and a clean run would point there.
