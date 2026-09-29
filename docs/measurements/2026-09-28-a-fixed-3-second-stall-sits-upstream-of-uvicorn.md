# A fixed ~3-second stall hits ~1 in 30 live requests, and nothing on the machine shows it

**Date:** 2026-09-28 21:51Z to 2026-09-29 04:43Z
**Ticket:** #193 (epic #185, ADR 0188 §3 item 0)
**Prompt:** Found while timing the #186/#187 deploy of `1078389`. Joe said "go ahead with #193".
**Instruments:**
- A scratch probe from the laptop (httpx, keep-alive, one request a second, the session cookie minted from `.env` the way `scripts/time_live_routes.py` does). It is not committed. **It prints every non-200 response as `SLOW`, so the stalls are only the lines of 1,000 ms or more.**
- `curl -w` phase timings, with a fresh connection each request.
- `inspect_live_db.py read-incidents -n 40` (cheap).
- `scripts/probe_loopback_latency.py`, run in-box (§C).
- `flyctl logs --no-tail` over the §C window.
- `scripts/probe_public_latency.py` (#194), the laptop probe committed, for §F.

**Cost:** zero credits, zero tokens. Every request was a GET, and the probe rate was one a second.
**Audited:** measurement-skeptic, 2026-09-29. The verdict on the first draft was OVERSTATED: its headline claimed "outside the machine", two counts were off by one, and it called the period "sharp". This version carries the corrections.

## What this establishes

- **The stall is a fixed ~3.1 s, not a slow tail.** Every stall but one landed between 3,091 and 3,206 ms. The exception was 2,406 ms, in §C. Non-stalled requests had a p50 of 91–98 ms and a p95 of 109–134 ms.
- **It is not route-specific.** It hits `/api/health`, `/api/signal` (a cache hit, which runs no SQL), `/api/window`, and a 404 page that **Next answers without calling the backend**. The middleware verifies the cookie and makes no backend call (`frontend/src/middleware.ts`). The rates across these routes are not distinguishable at these counts.
- **It sits after the TLS handshake.** On every slow `curl`, DNS was ≤ 6 ms, TCP connect ≤ 46 ms and TLS ≤ 70 ms, and time-to-first-byte was 3.156–3.206 s. So it is on the server side of Fly's edge, not on the laptop's network.
- **No process on the box stalls (§C).** Over one 10-minute window, 0 of 1,773 fresh loopback requests to uvicorn, Next's proxy and Next alone took over 72 ms. From outside, over the same minutes, 21 of 554 took 3,095–3,178 ms. A stall that froze Next or uvicorn for everyone would have shown up about 20 times per target. That rules out an event-loop block, GC pause or lock inside either process.
- **The guest kernel shows nothing either (§E).** In a 10-minute window with 13 stalls: 0 retransmitted segments, 0 SYN retransmits, 0 listen drops or overflows, 0 TCP timeouts. That matches a quiet baseline window with no probe running. Fly's proxy reuses pooled connections into the box: 573 extra requests added ~10 passive opens.
- **The stalls are regular, not random (§C).** No gap between stalls is under 14 s. The short gaps run 14.1–19.1 s, and the mean cycle is 15.6 s. At the observed rate, random arrivals would put about 7 of 20 gaps under 14 s, and 0 did (p ≈ 2e-4).

## What this does not establish

- **Where on the proxied path the 3 s is added.** The candidates are Fly's proxy, the machine's network interface or guest kernel, or Next's handling of the pooled connections Fly's proxy reuses into :3000. The in-box probe opens a fresh loopback connection per request, so it cannot separate these. **A dropped packet and its retransmit timer would give exactly a fixed ~3 s.** §D reads the counters that would show it.
- **What sets the ~15.6 s rhythm.** Two 15 s timers exist:
  - **The recorder's quote pass** (`RUNNER_FAST_INTERVAL_S=15`) is excluded. Its measured cycle in the §C log is ~18.5 s, and stalls fall in and out of it.
  - **Fly's health check on :3000** runs every 15 s (`fly.live.toml [checks.health]`). It is not tested. Whether Fly jitters its check interval is unknown. If it does not, the 15.6 s mean argues against it.
- **That it predates today.** The 2026-09-18 table's single-rep maxima of 3,893, 3,663, 2,771 and 2,578 ms are consistent with a fixed +3 s. So is the 2026-09-17 "5,231 then 3,101 ms" signal miss. Neither was timed per phase, so this is a fit, not a proof.
- **A rate to quote.** Four runs gave 7/286, 8/150, 13/453 and 21/554. That is one evening from one client, and the runs are not independent.
- **That the stalls are independent across a page's parallel calls.** So "a page load meets one ~10–20% of the time" (#193) is arithmetic on an assumption.

## §A — The laptop probes

| run | UTC | method | requests | stalls | p50 | p95 |
|---|---|---|---|---|---|---|
| 1 | 21:51–21:56 | keep-alive, `/api/signal` + `/api/window` alternating | 286 | 7 (3,091–3,161 ms) | 98 | 134 |
| 2 | ~21:58–22:01 | `curl`, a fresh connection each time, `/api/signal` | 150 | 8 (3,156–3,206 ms) | — | — |
| 3 | 00:08–00:16 | keep-alive, `/api/health` + `/api/signal` + `/no-such-page-probe` round-robin | 453 | 13 (health 3, signal 5, 404 page 5) | 93 | 116 |

Run 3's stall times: 00:11:31.576, 11:45.695, 12:02.815, 12:33.923, 12:48.054, 13:25.190, 13:54.333, 14:11.435, 14:27.564, 14:44.688, 15:32.808, 15:47.948 and 16:22.102. None of its gaps is under 14 s. Its 29, 34 and 37 s gaps fall between multiples of 15.

An accidental run (00:02–00:08) sent `C:/Program Files/Git/api/health`, because Git Bash rewrote the leading `/` (`tasks/lessons.md` 2026-09-28). All 173 of those requests hit a Next 404 page, and one took 3,098 ms. It is counted nowhere above. It was the first sign that a request Next answers alone stalls too.

## §B — Where each hop has been read

| hop | evidence | stalls? |
|---|---|---|
| laptop → Fly edge (DNS, TCP, TLS) | `curl -w`, 150 requests | no: TLS done in ≤ 70 ms on every slow request |
| the whole proxied path: Fly edge → machine interface → Next (:3000) → uvicorn | every public probe | **yes** |
| Next alone, on the proxied path (a 404 page) | runs 3 and §C | **yes** |
| every process on the box, over fresh loopback connections | §C in-box probe | no: 0 of 1,773 |
| uvicorn, over the recorder's pooled client | `health_probe` incidents, below | no |

**The recorder's probe.** It runs `probe_hub_running` after every pass (`scripts/run_loop.py:1294`): every 15 s while the window is open, every 900 s otherwise. It targets `127.0.0.1:8000/api/health` at a 2 s threshold, on a pooled client, and failures are written at `:736` and `:744`. Since that writer landed (schema v42, 2026-09-14) it has recorded **0 `health_probe` rows**. The same writer has recorded 8 `read_budget` rows, so it is not dead. It never raises, so 0 is a floor.

**What remains:** Fly's proxy, the machine's network interface or guest kernel, or Next's handling of reused connections.

## §C — In-box probe, with an external control over the same 10 minutes

`d16ddd2` was deployed at 03:14Z, after Monday Night Football was final, on Joe's word. Both probes started together:
- in-box, `probe_loopback_latency.py --seconds 600 --interval 1`, whose ssh session logged its start at 03:17:19. `inbox-probe.txt` carries no per-request timestamps.
- external, the laptop probe hitting `/api/health` and a 404 page, one a second, 03:17:25–03:27:25.

| where | target | n | stalls | p50 | p95 | max |
|---|---|---|---|---|---|---|
| in-box | uvicorn `:8000/api/health` | 591 | **0** | 4 | 5 | 8 |
| in-box | Next's proxy `:3000/api/health` | 591 | **0** | 5 | 8 | 18 |
| in-box | Next alone `:3000/login` | 591 | **0** | 5 | 11 | 72 |
| laptop → Fly | `/api/health` | 277 | 7 at 3,095–3,155 ms, plus 1 at 2,406 | — | — | 3,155 |
| laptop → Fly | 404 page | 277 | 14 at 3,103–3,178 ms | — | — | 3,178 |

The 490 and 699 ms outliers at 03:17:25–03:17:36 came about 35 s after boot, during the first full pass (03:16:50–03:18:18). They are boot noise.

**The rhythm.** Stalls landed at 03:17:39, 17:54, 18:57, 19:14, 20:13, 20:28, 20:43, 20:59, 21:13, 21:29, 21:45, 22:17, 22:32, 24:19, 24:36, 25:25, 26:12, 26:26, 26:42, 27:01 and 27:17Z. The gaps were 15.1, 63.2, 17.1, 58.1, 15.1, 15.1, 16.1, 14.2, 16.1, 16.1, 31.1, 15.2, 107.2, 17.1, 49.2, 47.1, 14.1, 15.1, 19.1 and 16.1 s.
- Over 577.7 s there were 37 cycles, a mean of **15.6 s**. A strict 15.0 s timer would drift 22 s over that span.
- The long gaps sit within ~2 s of whole multiples.
- The source's cycle is ~15–16 s with several seconds of jitter. It is not a strict timer.

**Fly's proxy log.** `flyctl logs` for 03:16:47–03:28:30Z holds 99 app lines, 1 health line and **no proxy error line**. The pooled-connection race, where Fly reuses a connection Next has already closed after its 50 s `keepAliveTimeout`, normally logs one. `flyctl logs` is lossy, so this weakens the race rather than excluding it. Fly's documented proxy retry backoff runs from 5 ms to 1 s, which does not produce a fixed 3 s. That says nothing about a kernel retransmit timer.

## §E — The box's TCP counters, baseline vs probe (live `21c891f`)

`inspect_live_proc.py --json` was read at 04:23:05 (R0), 04:33:09 (R1) and 04:43:17Z (R2). R0→R1 is a quiet baseline. R1→R2 had the external probe running: `/api/health` and a 404 page, one a second.

| counter (guest kernel, box-wide, loopback included) | baseline, 604.1 s | probe, 607.4 s |
|---|---|---|
| external requests / stalls (3,096–3,150 ms) | — | 573 / **13** (health 8, 404 page 5) |
| `Tcp.RetransSegs` | 0 | **0** |
| `TcpExt.TCPSynRetrans` | 0 | **0** |
| `TcpExt.ListenDrops` / `ListenOverflows` | 0 / 0 | **0 / 0** |
| `TcpExt.TCPTimeouts` / `TCPLostRetransmit` / `TCPAbortOnTimeout` | 0 / 0 / 0 | **0 / 0 / 0** |
| `Tcp.AttemptFails` / `EstabResets` / `InErrs` | 0 / 0 / 0 | 0 / 0 / 0 |
| `Tcp.PassiveOpens` | 85 | 95 |
| `Tcp.ActiveOpens` | 46 | 43 |
| `Tcp.InSegs` / `OutSegs` | 3,732 / 2,445 | 5,523 / 4,863 |

**What it establishes:**
- **The guest kernel resent nothing, dropped no incoming connection, and hit no TCP timeout** in a window that held 13 stalls. A response lost on its way out would have been resent by the guest and counted in `RetransSegs`. A connection refused at a full listen queue would be counted in `ListenDrops`. Both are zero.
- **Fly's proxy reuses pooled connections into the box.** 573 extra requests added about 10 passive opens over the baseline. That is not a connection per request. `PassiveOpens` includes loopback and ssh, so the +10 bounds new proxy connections from above.

**What it does not establish:**
- **A packet lost before it reaches the guest.** A request segment or a SYN dropped upstream is resent by the sender, Fly's side, and the guest's counters never see the first copy. That is the one packet-loss path this box cannot read.
- **Next's handling of a reused keep-alive connection.** The in-box probe used fresh connections. The kernel counters rule out loss on the guest, not a delay inside Node on a reused socket. No process showed CPU for one (ADR 0188 §B), and a Node delay of a fixed 3 s has no mechanism named here.

**Where this leaves #193:** nothing on the machine shows the stall: not uvicorn, not Next, not the guest kernel. What remains is Fly's side of the connection (its proxy or its host networking) or, less likely, a delay in Node on reused sockets.

## §D — The next readings, in order

1. **Done: §E.** The counters were clean in the probe window. The original plan, kept for the record: **the box's own TCP counters**, read-only, before and after a window with the external probe running: `/proc/net/snmp` (`Tcp: RetransSegs, PassiveOpens, AttemptFails, EstabResets, InErrs`) and `/proc/net/netstat` (`TcpExt: ListenOverflows, ListenDrops, TCPTimeouts, TCPSynRetrans`).
   - If retransmits or listen drops rise by about the number of stalls, the 3 s is a lost packet at the machine's edge.
   - `PassiveOpens` against the request count shows whether Fly opens a fresh connection per request or reuses them.
   - No config change is involved: these are `/proc` text files, the same class `inspect_live_proc.py` already reads.
2. **Only if (1) is inconclusive:** move the health check interval from 15 s to 30 s for one probe window, and see whether the rhythm follows. That changes the deployed `fly.live.toml`, which this session was refused permission to edit, so it would go to Joe as a ticket with the reading from (1).

## §F — The 30 s health-check trial (live `14af8f7`)

### The rule, committed before the reading (2026-09-29, session 68)

The trial is the one §D(2) named. `14af8f7` moved `[checks.health]` from 15s to 30s, on Joe's pick. The machine config shows `interval: 30s` (`flyctl machine status -d`, 2026-09-29), and the box has been up since 05:29:51Z.

**The window:**
- 30 minutes, with `scripts/probe_public_latency.py` (#194) keeping connections alive at one request a second per arm, alternating `/api/health` and a 404 page. These are §C's and §E's targets.
- **Arm 1:** public live. This arm decides the outcome.
- **Arm 3:** public demo, as a control. It has always run a 30s check. It is warmed first, because demo's first request returns nothing.
- **Arm 2 was dropped before any data.** It was to be live over 6PN via `fly proxy` to :3000, bypassing the edge. It cannot reach Next: `docker/entrypoint.sh:340` binds `HOSTNAME=0.0.0.0` (IPv4 only), 6PN is IPv6, and the tunnel's connections were reset (`curl` exit 56) while public requests were answered.

**The statistic:** F, the fraction of gaps between consecutive stalls (a stall is ≥ 1,000 ms) that are under 24 s. Under the 15s check it read 14 of 20 (§C) and 7 of 12 (§A run 3). The mean gap is not used, because only some of the ~15.6 s cycles land on a probe request. That is why §A run 1 could have looked like a ~30 s rhythm under the 15s check.

**The outcomes, on arm 1:**
- **MOVED** (the health check is the trigger): at least 12 gaps and none under 24 s. Under the 15s-era null that has probability about 0.42¹² ≈ 3e-5. A stall rate near half the earlier ~2 a minute corroborates this but does not decide it.
  - Keep 30s.
  - A Question for Joe goes under #3: aim the check at :8000, or make it a TCP check, as the next trial.
- **UNMOVED:** F ≥ 0.25. Revert to 15s, per the rule in `14af8f7` (the deploy is pre-approved). With arm 2 gone, the remaining step is a keep-alive mode for the in-box probe, to test Next's handling of reused sockets. After that, #193 closes naming Fly's side.
- **INCONCLUSIVE:** anything else, including fewer than 12 gaps. Extend once by 30 minutes and pool the windows. If it is still inconclusive, revert and record it as such.
- **Zero stalls in about 1,800 requests** (the null expects about 60): make no fix claim. Keep 30s and take a second window later in the day.
- **Stop-loss:** this reading plus one follow-up step, then #193 closes with whatever hop the readings name.

### The reading (2026-09-29 18:21:08–18:51:08Z): UNMOVED

`scripts/probe_public_latency.py` (#194, merged `b725c5a`), keep-alive, no cookie, both arms in one window. The raw CSV is kept outside the repo (operator rule).

| arm | check interval | n | stalls | stall ms | p50 / p95 ms | gaps | under 24 s | **F** | min gap |
|---|---|---|---|---|---|---|---|---|---|
| live, public | 30s (trial) | 1,543 | **41** (health 19, 404-probe path 22) | 3,094–3,127 | 86 / 109 | 40 | 15 | **0.375** | 14.9 s |
| demo, public | 30s (always) | 1,489 | **57** (health 25, 404-probe path 32) | 3,100–3,196 | 93 / 136 | 56 | 26 | **0.464** | 13.9 s |

- **The decision:** F = 0.375 ≥ 0.25 on arm 1, so the outcome is **UNMOVED**. With the check at 30 s, stalls still land about 15 s apart (15 of 40 gaps are 14.9–19.3 s), Per request, live stalled on 2.66% (41/1,543). That is inside the 15s-era range of 2.27–3.79% (§E 13/573, §A run 1 7/286, §A run 3 13/453, §C 21/554), so the rate did not move either. No rate is quotable from one evening. Per the rule in `14af8f7`, the check goes back to 15s.
- **The control rules the check out as a trigger on its own terms.** Demo is a separate app and machine. Its `fly.demo.toml` has set a 30s check since `330fe04` (checked in the repo, not on the machine), and it runs no recorder (`docker/entrypoint.sh` starts `run_loop.py` only outside demo mode). It and it stalls on the same ~15 s rhythm (26 of 56 gaps under 24 s, minimum 13.9 s).
- **What the two arms share.** The image, the region (`ord`), Fly's proxy layer (the edge the laptop reaches, and the proxy on the worker host), possibly the host, and the client: one laptop, its network and one probe process. They do not share a machine or the recorder. §C cleared every process on fresh loopback connections. So the candidates are:
  - Fly's proxy layer or host networking;
  - Next's handling of the pooled connections that proxy reuses;
  - the client's network path.

  No second client has been run. Demo also removes the recorder as a cause, independently of §C.
- **The laptop's load did not contaminate the reading.** The #192 lane ran three full `-n auto` suites on the same laptop during this window. On both arms, no request fell between 500 and 2,900 ms, and there were no transport errors. Every slow request is in the fixed 3,094–3,196 ms cluster, and client-side load does not produce a fixed 3.1 s. This rules out load, not the client's network path, which no reading has yet separated from Fly's side.
- **Audited:** measurement-skeptic, 2026-09-29. The verdict on the first draft was OVERSTATED: the rate comparison, the narrowing to two candidates, and naming Fly without a second client. The numbers and the decision stood, and this version carries the corrections. It also noted, unregistered and weak, that the two arms' stall timings drift apart over the window. That fits separate per-connection clocks better than one source common to both arms.
- **Two deviations from the rule as written:**
  - The probe sleeps 1 s *after* each request, so n is about 1,500 per arm, not 1,800.
  - Without the cookie, live answers `/no-such-page-probe` with Next's `307` to the login page, not a 404. On demo, which runs without auth, the same path answered `404`. Both responses come from Next alone, which is what the target is for. §C and §E sent the cookie.

**What happens next, under the stop-loss:**
1. `fly.live.toml` goes back to `interval = "15s"`, deployed with #191.
2. The one remaining step is a keep-alive mode for `scripts/probe_loopback_latency.py`: reuse one connection per target in-box for 10 minutes. If a reused socket into Next stalls in-box, the cause is Next's keep-alive handling, which the image controls. If it stays clean, the 3 s is added outside the machine. Naming Fly rather than the client's path needs one probe from a second client on another network in the same window. Without it, #193 closes as "outside the machine", not "Fly's side". The second client is `.github/workflows/probe.yml`: the same committed probe, run from a GitHub-hosted runner in the same window as the in-box keep-alive run and the laptop.

## §G — The last step: a reused connection in-box, and a second client (rule fixed before the reading)

**Why this is last.** Under the stop-loss, #193 closes after this window, naming whatever hop it points to.

**The window:**
- 10 minutes, at least 10 minutes after the deploy that ships `e02f5c6` (the keep-alive mode) boots the box. Live runs a 15s check again.
- Three probes run at once:
  1. **In-box:** `scripts/probe_loopback_latency.py --keepalive --seconds 600`, one persistent HTTP/1.1 connection per port, run by path over ssh.
  2. **Laptop:** `scripts/probe_public_latency.py`, live only, 600 s, keep-alive (the §F instrument).
  3. **Second client:** `.github/workflows/probe.yml` with `seconds=600`, the same probe from a GitHub-hosted runner on live and demo.

**The rules:**
- **The in-box probe decides "ours or not ours".**
  - **Ours:** at least 3 answers of 2,900 ms or more on `next-proxy` or `next-only`, with `connections opened` well under the request count, while the laptop arm stalls. That puts the stall in Next's handling of reused connections, which the image controls. #193 becomes a fix ticket.
  - **Not ours:** 0 answers of 2,900 ms or more on any target, while the laptop arm shows at least 5 stalls. The 3 s is added outside the machine.
  - **Inconclusive:** anything else, including a laptop arm with fewer than 5 stalls, because then the window had no stall to explain.
- **The second client names the side, not whether it is ours.**
  - **Server side:** the runner's live arm shows at least 5 stalls of 2,900–3,400 ms. Then the laptop's network path is not the cause, and the 3 s is on Fly's side.
  - **Client side:** 0 stalls in 400 or more runner requests on each arm, while the laptop shows at least 5. The laptop's path is implicated.
  - **Unnamed:** anything else, or the runner not running. #193 closes as "outside the machine", with no side named.
- If the ssh run or the workflow dispatch is refused, the reading goes ahead with what ran. The missing arm's clause is recorded as not taken.

### The reading (2026-09-29, live `b139c4e`, booted 19:07:21Z, check at 15s): NOT SEEN IN-BOX (reuse every 1 s or less), SERVER SIDE

The labels are the rule's clauses. Here "not ours" means only that no in-box stall was seen at reuse every 1 s or less.

The window opened at 19:16:54Z with the runner dispatch. The in-box and laptop probes started seconds later and ran 660 s each, a little longer than the rule's 10 minutes so they would cover the runner's 600 s after its startup. The runner's probe step (19:17:04.34–19:27:05.24Z, from its step log) fell inside both. The laptop ran 19:17:00.743–19:28:00.623Z (first and last CSV rows). The in-box start, ~19:17:00Z, is inferred from the ssh output's file timestamps, because that output carries none of its own.

**Deviations:** the window opened about 9 min 33 s after boot (19:07:21Z boot, 19:16:54Z dispatch), not the 10 minutes or more the rule set. Both local probes ran 660 s, not 600 s.

| arm | n | answers ≥ 2,900 ms | stall ms | other |
|---|---|---|---|---|
| **in-box, keep-alive** (`--keepalive --seconds 660`) | 650 per target, 1,950 in all | **0** | none | 0 errors. p50 3–5 ms, max 8 / 25 / 79 ms (uvicorn / next-proxy / next-only). **2 connections opened** for 1,950 requests, one per port. |
| **laptop**, live | 566 | **15** | 3,095–3,129 | F = 0.500 (7 of 14 gaps under 24 s), minimum gap 14.9 s |
| **GitHub runner**, live (run 36618116075) | 517 | **15** | 3,089–3,106 | F = 0.429, minimum gap 15.9 s |
| GitHub runner, demo | 495 | 15 | range 3,100–20,834: the runner's summary prints only the extremes, and its CSV is not uploaded | F = 0.214. The 20.8 s maximum is demo only, and no clause reads it. |

- **In-box: the "not ours" clause.** No answer took 2,900 ms or more on any target, while the laptop arm showed 15 stalls. Two connections, one into Next and one into uvicorn, were reused every 0.3–1 s and never stalled. The 3 s is spent outside the machine. That locates the delay, not what triggers it. §E had already cleared the guest kernel, and §C every process over fresh connections.
- **Runner: server side.** The runner's live arm showed 15 stalls of 3,089–3,106 ms, on a separate client on a separate network (a GitHub-hosted runner), with the same fixed length and the same ~15 s rhythm. So the laptop's network path is not the cause.
- **What that names:** Fly's side of the connection, meaning its proxy layer (edge or worker-host proxy) or the host's networking between that proxy and the guest. This set of readings cannot say which.
- **What it does not establish:**
  - **That nothing in the image triggers it.** A pooled connection that sits idle and is then closed by Next was never exercised. The keep-alive mode reuses every 1 s or less. This hop has failed that way before, fixed in the image on 2026-08-19 (`docker/entrypoint.sh`, `KEEP_ALIVE_TIMEOUT=50000`), and Fly's pool idle times are unmeasured.
  - **Whether stalls line up with new proxy→guest connections.** Stall times were never compared with the times :3000 accepted a new connection. That comparison is what would separate a cause entirely inside Fly from a close triggered by Next.
  - **Which Fly edge each client reached.** Not recorded; the region suffix on `Fly-Request-Id` would name it.
  - **Whether the laptop and the runner stalled on the same events.** The runner's CSV was not uploaded, and §F already saw the stall timings drift apart, as a per-connection clock would.
  - A mechanism. A dropped SYN or request segment on the proxy's side, resent after a 3 s timer, fits the fixed length, and the guest would never count it (§E). It is a hypothesis, not a reading.

**Under the stop-loss, #193 closes: the 3 s is spent outside the machine, on Fly's side of the connection.**
- Nothing inside the box stalled: not over a fresh connection (§C), not in the guest kernel (§E), and not over a connection reused every 1 s or less (§G).
- A second client on another network stalled the same way, so the laptop's path is not the cause.
- This does not establish that nothing in the image triggers it. A pooled connection closed by Next after sitting idle, the 2026-08-19 failure on this hop, was not exercised.

**If it is ever reopened, start here:** log each new connection :3000 accepts, then compare those times with the stall times from `scripts/probe_public_latency.py` in the same window.
