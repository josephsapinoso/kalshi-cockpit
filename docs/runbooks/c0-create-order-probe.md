# C0 — capture Kalshi's real create-order response (Joe runs this, nobody else)

**Total worst case: under $0.14.** One sitting, about five minutes.

## What this is for

The only code in this repo that reads a create-order response —
`_read_response` at `backend/kalshi/orders.py:496` — was transcribed from
Kalshi's published OpenAPI spec and **has never seen a real payload**, because
this project has never placed an order. This venue has renamed wire fields out
from under spec-transcribed parsers three times (`data["yes"]` vs
`yes_dollars_fp`, `multivariate_event_collections` vs
`multivariate_contracts`, `orderbook` vs `orderbook_fp`), so whether the
response's fields really are named `order_id` / `fill_count` /
`remaining_count`, and whether they carry the `_fp` / `_dollars` suffix
conventions, is a guess until observed.

ADR 0063 makes this observation a **blocking prerequisite** for the manual
order path: if the parser cannot read a live response, the order is recorded
as `unrecognised_response`, and one such order would permanently occupy the
exposure budget (~$1.02 at current caps). A few cents spent observing the
shape now is what prevents that.

The probe is run by **you**, on your account, with your money. The assistant
built the instrument and never runs it — that split is recorded in ADR 0063.

## What it does (four probes, each priced before it fires)

| # | probe | what it observes | worst case |
|---|-------|------------------|------------|
| 1 | IOC limit buy, 1 contract @ 1c | the **non-fill** response shape | $0.0107 |
| 2 | the identical body re-sent, **same `client_order_id`** | what a **duplicate** returns (idempotency) | $0.0107 if Kalshi treats it as new — itself a finding |
| 3 | IOC limit buy, 1 contract @ the derived ask — **refused if the ask is over 10c** | the **fill** response shape, incl. the fee fields | $0.1063 |
| 4 | GTC limit buy @ 1c, then DELETE it | the **resting** create shape and the **cancel** response | $0.0107 (fills at 1c before the cancel lands) |

Fees are the flat 0.07 taker coefficient — the fee at 1c is $0.0007 and at
10c is $0.0063, so every "worst case" above already includes it.

Each probe prints exactly what it is about to send and its worst-case cost
before sending, and the script asks you to **type the ticker back** once,
after showing you the live orderbook, before anything is sent. Every raw
response — expected or not — is captured; a surprise status does not stop the
run, because the surprise is the data.

No cancel endpoint has ever been observed by this project either, so probe 4
tries the V2-shaped path first (`DELETE /portfolio/events/orders/{id}`) and
falls back to the legacy `DELETE /portfolio/orders/{id}` on a 404/405. If
**both** fail, the script says so: open the Kalshi app and cancel the 1c
order there. Its worst case while resting is a $0.01 fill.

## Prerequisites

The script refuses to run unless **all three** hold:

1. the `--i-am-joe-and-this-spends-money` flag is passed,
2. `INSTANCE_MODE=live` (demo, unset, or anything else refuses), and
3. `KALSHI_API_KEY` + `KALSHI_PRIVATE_KEY_PATH` load cleanly.

Two ways to satisfy 2 and 3 — **use the laptop path**:

**A. Laptop with the live key (works today, recommended).** Your repo `.env`
with `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY_PATH` (the RSA PEM at
`~/.kalshi/private_key_2.pem`), and `INSTANCE_MODE=live` set for this run.
This is the same path every capture script in this repo uses
(`scripts/capture_fills_fixture.py` precedent). The full live `AppConfig` is
deliberately **not** required — no `APP_AUTH_TOKEN`, no public
`COCKPIT_BASE_URL` — because those guard the cockpit server, not a probe.

**B. `flyctl ssh console` on the live app — only after this commit is
deployed.** The running image only contains scripts that existed when it was
built, so this path does not work until a deploy that includes
`scripts/probe_create_order.py`. When it does: the entrypoint materialises
the key to tmpfs but exports its path only inside its own process tree, so
the ssh shell needs one export first:

```
flyctl ssh console -a kalshi-cockpit
cd /app
export KALSHI_PRIVATE_KEY_PATH=/dev/shm/kalshi/private_key.pem
/opt/venv/bin/python scripts/probe_create_order.py ...
```

Note the capture file then lands on the machine, not your laptop
(`flyctl sftp get` to retrieve it). The laptop path avoids all of this.

## The command

Pick a market and a side where **your side's ask is at or under 10c** (a
longshot — probe 3 refuses above that, and the run still completes without
it). Then, from the repo root:

```
.venv\Scripts\python.exe scripts\probe_create_order.py --i-am-joe-and-this-spends-money --ticker <TICKER> --side yes
```

`--side` is `yes` or `no` — the side the probes buy. Any probe can be dropped
individually: `--skip-shape`, `--skip-duplicate`, `--skip-fill`,
`--skip-cancel`. (Skipping probe 1 also skips probe 2, which re-sends
probe 1's exact body.)

The script shows you the book, prints the priced plan, and waits for you to
type the ticker back. Anything else aborts with nothing sent.

## What comes out, and what to send back

The run writes every raw response (status + full JSON body) to:

```
data/captures/create_order_probe_<UTC-timestamp>.json
```

and prints the file's **SHA-256** at the end.

**Send back: the SHA-256 and the printed statuses. The capture file itself
stays on your machine.** `data/` is gitignored — verified with
`git check-ignore data/captures`, which matches the `data/` rule at
`.gitignore:33` — and the file must never be committed or pasted: it is a
real account's order history, and operator data never enters the repo (your
standing ruling). There is no credential in it, but that is not the bar.

## After the run

Synthetic fixtures get **hand-written from the observed shape** — same
precedent as the MLB payloads under ADR 0035, where the committed fixture is
synthetic and a shape assertion keeps it honest. The raw capture is never
committed and never becomes a fixture directly. Those fixtures are what
`_read_response`'s tests then load, replacing spec-transcription with
observation, and they are what the manual-order path (ADR 0063) builds on.

## What this run does not establish

One ticker, one day, one series: the shapes may not generalise, so the parser
keeps refusing loudly on any missing field. At most two fills at extreme
prices pin nothing new about the fee model. One duplicate observation is not
a licence to retry blindly. And nothing here touches settlement (H4 stays
untested).
