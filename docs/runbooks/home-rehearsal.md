# Home rehearsal: is the desk faster served from the home desktop over Tailscale?

**Status:** registered 2026-11-13, before any reading. Nothing below has been run.
**Why:** Joe saw a self-hosted Kalshi desk (ALSHI, Reddit r/BuildWithClaude) that runs on a
home machine reached over Tailscale, and asked whether copying that would make this desk
faster and cheaper than Fly. The plan is phased; this is Phase 0. **Live does not move until
this rehearsal reads GO and Joe answers the hosting ticket.**

What the repo already says about speed, so the rehearsal tests the right thing:

- About 1 in 20–40 requests stalls a fixed ~3.1 s, and the stall sits **outside the machine,
  on Fly's side** (`docs/measurements/2026-09-28-a-fixed-3-second-stall-sits-upstream-of-uvicorn.md`, #193).
- The SQLite file is about twice the Fly box's 4 GB of memory, so route time depends on
  page-cache residency (ADR 0188 §2: 74.8 s cold vs 2.15 s warm on one read).
- CPU is not the cost: the box read 1.3% busy (ADR 0188 §B). A language or framework change
  is not on the table.
- The Kalshi WebSocket feed already exists and runs (`backend/kalshi/ws.py`, `backend/live.py`,
  ADR 0119). Hosting does not change it.

## What the copy is, and what it cannot do

`docker-compose.home.yml` runs the production image with `SERVE_ONLY=1`
(`docker/entrypoint.sh`). The entrypoint refuses to boot unless `KALSHI_PUBLIC_READ_ONLY=true`,
and refuses if a Kalshi key is present. So the copy:

- **records nothing**: no chain runner, no odds sweeps, no credits spent;
- **cannot place an order or an RFQ**: every credentialed Kalshi path refuses by construction;
- **spends no tokens and pushes nothing**: the compose file blanks every credential in
  `.env.example` over whatever `.env.home` contains (`tests/test_home_compose_is_serve_only.py`);
- **has no live ticker**: Kalshi's WebSocket authenticates at the handshake, so the quote hub
  logs `KalshiCredentialsRequired` every 120 s and pages show recorded prices. Expected, and
  harmless for timing.

It is a snapshot: its prices stop at the moment of the copy.

## Steps

### 1. Fly's monthly cost (Joe, 2 minutes)

Read the last two Fly invoices (fly.io dashboard → Billing). Write the monthly total for the
`kalshi-cockpit` app, and separately the demo, into the result doc. The repo carries no
trustworthy figure (ADR 0002's correction).

### 2. Install on the desktop (Windows)

1. Docker Desktop with the WSL2 backend.
2. Tailscale for Windows, signed in. Tailscale on the phone, same account.
3. Tailscale admin console → DNS: MagicDNS on, HTTPS certificates on.
4. `git clone` this repo and check out **the commit live runs**: read `build.git_sha` from
   `https://kalshi-cockpit.fly.dev/api/health`. The same commit means `migrate_db.py` leaves
   the copy's schema alone.

### 3. Copy the live database

The live volume filled once (2026-08-16) and the machine died. The snapshot script refuses
unless free space exceeds 1.5 times the file plus 1 GiB.

The script ships in the image from the commit that adds it, so live must be on that commit or
later (deploy workflow, `confirm_live`). Then, from the laptop, **outside a game window**,
because reading the whole file evicts the box's page cache and the desk will be slow for a
while afterwards:

```bash
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_disk.py"
```

```bash
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/snapshot_live_db.py --out /data/rehearsal-copy.db"
```

```bash
flyctl ssh sftp get /data/rehearsal-copy.db ./rehearsal-copy.db -a kalshi-cockpit
```

```bash
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/snapshot_live_db.py --delete /data/rehearsal-copy.db"
```

If the snapshot refuses for space, stop. Do not free space on the live volume to make room;
that is its own decision (ADR 0182).

### 4. Start the copy

Create `.env.home` in the repo root (gitignored by `.env.*`):

```
APP_AUTH_TOKEN=<the same token as live, so one cookie times both arms>
COCKPIT_BASE_URL=https://<machine>.<tailnet>.ts.net
```

The copy holds no Kalshi key, so sharing the login token gives it nothing to spend.

Load the copy into the named volume, then start it:

```bash
docker compose -f docker-compose.home.yml create
```

```bash
docker run --rm -v kalshi-cockpit_cockpit_home_data:/data -v "%CD%":/in alpine sh -c "cp /in/rehearsal-copy.db /data/cockpit.db && chown 10001:10001 /data/cockpit.db"
```

```bash
docker compose -f docker-compose.home.yml up -d --build
```

The volume name is prefixed with the folder name. `docker volume ls` shows it. In PowerShell
use `${PWD}` in place of `%CD%`.

Check the boot log says `SERVE_ONLY=1 -- serving a copy: no key, no chain runner`:

```bash
docker compose -f docker-compose.home.yml logs cockpit
```

### 5. Put it on the tailnet

```bash
tailscale serve --bg 3000
```

Open `https://<machine>.<tailnet>.ts.net` on the phone with Wi-Fi off. It should load. With
Tailscale switched off on the phone it must not. **Do not use `tailscale funnel`**: it
publishes to the internet.

### 6. Time both arms in the same window

Run from the laptop on a network that is **not the home network** (a phone hotspot), so both
arms cross the internet the way the phone does. First record how the tailnet path is routed:

```bash
tailscale ping <machine>
```

"via DERP" means a relay; "via <ip>" means direct. Record which.

Stall count, both arms at once, 30 minutes:

```bash
python scripts/probe_public_latency.py --base-url https://kalshi-cockpit.fly.dev --base-url https://<machine>.<tailnet>.ts.net --seconds 1800 --out ../rehearsal-stalls.csv
```

Route timing, 20 reps per route, one arm after the other:

```bash
python scripts/time_live_routes.py 20
```

```bash
TIMING_BASE_URL=https://<machine>.<tailnet>.ts.net python scripts/time_live_routes.py 20
```

## Decision rule (fixed before the reading)

Let a **stall** be a response of 2,900 ms or more on the stall probe.

- **The window must contain the phenomenon.** If the Fly arm shows fewer than 5 stalls in the
  30 minutes, the window cannot test it: **UNRESOLVED**, re-run once on another day. A second
  quiet window ends the rehearsal as UNRESOLVED.
- **GO** when the home arm has **0 stalls** in a window where Fly has 5 or more, **and** the
  home median is at or below Fly's on at least 6 of the 8 API routes `time_live_routes.py`
  times by default.
- **NO-GO** when the home arm has any stall, or the home median is slower than Fly's on 3 or
  more of those routes.
- Anything else is **UNRESOLVED**.

Report `n`, median and max per route per arm, and the tailnet path (direct or DERP). Run
`measurement-skeptic` over the result before it enters `docs/measurements/`.

## What this does not establish

- **Anything about uptime.** A desktop that sleeps, updates or loses power stops the hedge
  pushes and the recorder while it is down. The rehearsal cannot price that; Joe weighs it in
  the hosting ticket.
- **The cold path.** Both arms warm as the timing runs. The home machine's memory decides
  whether the whole file stays resident; record its RAM and the file size.
- **The copy under load.** No recorder writes to it, so it is lighter than live will be.
- **The phone's own network.** The laptop on a hotspot approximates it. One window is one
  window.

## After the reading

Open a sub-issue of map #302: `Move live to the home desktop? — rehearsal reads <GO|NO-GO|UNRESOLVED>`,
with the invoice figure, the timing table and the uptime costs above. Then stop the copy and
delete the volume:

```bash
docker compose -f docker-compose.home.yml down -v
```

The cutover (Phase 2: Windows hardening, key rotation, a dead-man alert, nightly backups, the
workflows that assume Fly) is planned only if Joe answers that ticket yes.
