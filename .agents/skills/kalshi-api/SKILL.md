---
name: kalshi-api
description: Kalshi API reference for this repo - RSA-PSS request signing, the derived-ask identity, market discovery via /events, orderbook_delta and sequence gaps, settled-market quirks, and the fee formula. Use when touching backend/kalshi/*, backend/core/fees.py, backend/core/prices.py, or when debugging 401s, missing market data, or "the prices look wrong".
---

# Kalshi API

Ported from the previous project and updated with what this one has settled.
Everything here was verified against live behaviour or against a captured
payload. Where a claim is still **unresolved**, it says so explicitly rather
than picking the likelier option — the whole reason this file exists is that
guessing on these cost hours last time.

## Authentication: RSA-PSS, not ED25519

The previous project's README and AGENTS.md claimed ED25519 for most of its
life while the code did RSA-PSS. **Anyone who generates an ED25519 key will
fail to authenticate**, with errors that look like bad credentials.

- Algorithm: RSA-PSS, MGF1(SHA-256), `salt_length = PSS.MAX_LENGTH`, digest SHA-256
- Signature base64-encoded

The signed message is exactly, with no separators:

```
{timestamp_ms}{HTTP_METHOD}{path}
```

For WebSocket the message is the literal `{timestamp_ms}GET/trade-api/ws/v2`.

| Header | Value |
|---|---|
| `KALSHI-ACCESS-KEY` | the API key **id** (an identifier, not a secret blob) |
| `KALSHI-ACCESS-SIGNATURE` | base64 RSA-PSS signature |
| `KALSHI-ACCESS-TIMESTAMP` | the same milliseconds used in the message |

### Sign the FULL path — verified

Kalshi signs the full request path **including `/trade-api/v2`**. Confirmed
empirically by firing one identical request both ways:

```
full path (/trade-api/v2/portfolio/balance)  -> 200 OK
bare path (/portfolio/balance)               -> 401
```

A 401 here is indistinguishable from bad credentials, which is what makes it
expensive to debug.

Use `backend/kalshi/auth.py:signed_path(base_url, path)`. It derives the prefix
from `base_url` with `urlsplit` so the signed string and the requested URL
cannot drift apart.

**Never `rstrip("/trade-api/v2")`.** `rstrip` removes a *character set*, not a
suffix. It happens to work for `https://api.elections.kalshi.com/trade-api/v2`
(it stops at the `m` of `.com`) but silently eats hostname characters for any
base URL ending in any of `/ t r a d e - p i v 2`, including a trailing slash.
Use `removesuffix`.

### Query strings are NOT signed — RESOLVED 2026-08-06

Settled by `scripts/verify_auth.py` on an otherwise identical
`GET /portfolio/fills?limit=1`:

```
query sent, signed WITHOUT it  -> 200 OK
query sent, signed WITH it     -> 401
```

**Kalshi signs the path only.** Send the query on the URL; leave it out of the
signature. `SIGN_QUERY_STRING = False` in `backend/kalshi/auth.py`.

This **contradicts the project handoff brief**, which stated that query params
must be appended to the path before signing. The brief is wrong on this point.
The previous repo's skill file was right. Where a document and the live API
disagree, the API wins — and this is exactly the class of error that presents
as "bad credentials" and eats an afternoon.

## Order book semantics — read before trusting any price

**Kalshi publishes YES bids and NO bids only.** Asks are *derived*:

```
yes_ask = 1000 - best_no_bid    (tenths)
no_ask  = 1000 - best_yes_bid
```

In this repo that derivation lives in exactly one place —
`backend/store/db.py:derive_yes_ask` / `derive_no_ask` / `ask_for_side` — so no
call site can accidentally treat a mid as a tradeable price.

Three consequences that bite:

1. **Every EV calculation must buy at the derived ask, never the mid.**
   Bucketing on the mid while transacting at the ask is how the previous
   project produced a `+25.4 point` "edge" that lost $4.92 a market.
2. **"yes_ask staleness" is really "no_bid staleness."** The derived level
   inherits `last_updated` from the underlying bid, so one stale level produces
   *two* stale signals.
3. **Depth on the "ask" side is really the opposing bid's quantity.**

## Prices are not whole cents

Roughly a quarter of tradeable markets use `deci_cent` or `tapered_deci_cent`
tick structures. The API quotes prices as dollar strings like `"0.2400"`.

Canonical internal unit is **integer tenths of a cent**, 0..1000
(`backend/core/prices.py`). Validated on 152 live order book levels across five
markets spanning both tick structures: zero prices off the tenths grid,
observed range 1..962.

- Parse with `Decimal` and an explicit `ROUND_HALF_UP`. `int(float(s) * 1000)`
  happens to be correct for all 999 current values — that is luck, not a
  guarantee, and it would break silently if Kalshi widened to 5 decimals.
- **Quantities are floats, not ints.** 42 of 152 sampled levels were fractional.

## Market discovery — never paginate `/markets`

`/markets` is ~99.8% `KXMVE` auto-generated combinatorial junk. A 25,000-row
scan returned **zero** markets with any volume; a 12,000-row sweep returned
**2** real markets.

Use instead:

```
GET /events?status=open&limit=200&with_nested_markets=true
```

One request returns ~1,500 real markets in ~0.2s and excludes MVE entirely.
Filter `KXMVE` on **both** `event_ticker` and `market.ticker` anyway — belt and
braces, and cheap.

**Settled events do NOT return nested markets.** For history you must walk
`/events?status=settled` first, then call `/markets?event_ticker=X` per event.

## Wire-format field names — pinned by capture

From the real `/events?with_nested_markets=true` capture in
`tests/fixtures/events_sports_nested.json` (2026-08-06). The legacy names
`yes_bid` and `volume_24h` **no longer exist**. Full market field set (47):

```
ticker, event_ticker, title, subtitle, yes_sub_title, no_sub_title,
yes_bid_dollars, yes_ask_dollars, no_bid_dollars, no_ask_dollars,
yes_bid_size_fp, yes_ask_size_fp,
previous_yes_bid_dollars, previous_yes_ask_dollars, previous_price_dollars,
last_price_dollars, settlement_value_dollars, notional_value_dollars,
liquidity_dollars, volume_fp, volume_24h_fp, open_interest_fp,
price_level_structure, price_ranges, market_type, strike_type,
custom_strike, floor_strike, primary_participant_key,
open_time, close_time, expiration_time, expected_expiration_time,
latest_expiration_time, settlement_ts, settlement_timer_seconds,
occurrence_datetime, created_time, updated_time,
can_close_early, early_close_condition, expiration_value,
exchange_index, result, status, rules_primary, rules_secondary
```

Note `no_bid_dollars` / `no_ask_dollars`: market **summaries** do publish both
sides' asks, even though the order book *feed* publishes bids only. The derived
identity was checked against 2,145 of these real quotes —
`yes_ask == 1000 - no_bid` held on every one, zero violations.

Tick structures observed on game markets: `linear_cent` (2,085) and
`center_half_edge_half_cent` (60). Zero prices off the tenths grid.

Settled markets report `status: "finalized"`, **not** `"settled"`, and prices
come back only as `*_dollars` decimal strings.

**Wire-format tests must load from `tests/fixtures/`, never hand-constructed
payloads.** The previous project's `apply_snapshot` read `data["yes"]` while
Kalshi sent `yes_dollars_fp` — every order book parsed to zero levels,
silently, for the project's entire life, while 305 synthetic tests passed.

## Game-level tickers — RESOLVED 2026-08-06

**Per-game markets exist**, across many leagues, with moneyline + spread +
total for the major ones. Full findings and the scope decision are in
`docs/adr/0001-league-scope-from-discovery-spike.md`.

```
KXNFLGAME-26SEP14DENKC-KC
└──┬────┘ └────┬─────┘ └┬┘
series      event id   outcome

event_ticker = KXNFLGAME-26SEP14DENKC   (everything before the final dash)
```

Event id is `{YY}{MON}{DD}[{HHMM}]{AWAY}{HOME}`. The `{HHMM}` appears only when
a league plays two games between the same pair on one date (MLB doubleheaders):
`KXMLBGAME-26AUG092020HOUSD-HOU`.

Confirmed series: `KXMLBGAME` / `KXMLBSPREAD` / `KXMLBTOTAL` / `KXMLBRFI` /
`KXMLBKS`, `KXNFLGAME`, `KXNCAAFGAME`, `KXWNBAGAME` / `KXWNBASPREAD` /
`KXWNBATOTAL`, `KXCFLSPREAD`, many `KX{LEAGUE}GAME` soccer series, `KXNPBGAME`,
`KXLMBGAME`, and esports (`KXLOLGAME`, `KXVALORANTGAME`).

**Do not parse the ticker for team identity.** Every market carries
`yes_sub_title` in plain text (`"Kansas City"`, `"Notre Dame"`,
`"Michigan St."`) and the event `title` is `"Away vs Home"`. Match on those via
an alias table, not on ticker abbreviations.

NFL and NCAAF list weeks ahead of kickoff, so an empty slate is not evidence a
league is absent. NBA/NHL game series were not observed in the August sample —
both out of season, and the walk hit its page cap, so "not observed" is not
"does not exist".

## WebSocket

- Channel: `orderbook_delta`
- **One subscribe command per ticker.** Kalshi accepts a `market_tickers` array;
  the previous project didn't use it, so N markets meant N round trips.
- Server replies `subscribed` with a `sid`, used only for unsubscribe.

### Sequence gaps — the previous project had NO handling for this

`orderbook_delta` carries a `seq`. Without gap detection a dropped or reordered
frame **silently corrupts the book permanently** — there is no error and
nothing triggers a resync. If numbers "look wrong but nothing errored", this is
the first suspect.

On a gap: drop the book and re-snapshot. Do not attempt to patch forward.

### Reconnection

Exponential backoff capped at 60s. Add jitter (the previous project had none).
After repeated failures the old client broke out of its loop and sat there with
a stale display forever — no exit, no alert, no supervisor. Fail loudly.

**Application-level receive timeout is mandatory.** This exists because of a
real incident: ping/pong stayed healthy while data silently stopped for 16
minutes. **TCP liveness does not imply data flow.**

### Snapshots vs deltas

- **Snapshot**: clears all sides and repopulates from `[[price, qty], ...]`.
  An *empty* snapshot arriving over existing data was deliberately ignored to
  avoid wiping state on reconnect — which also means a genuinely emptied book
  stays populated. Know which behaviour you want.
- **Delta**: `{price, delta, side}`, added to existing quantity, level deleted
  at `<= 0`.

## Historical quotes — the CLV primitive

```
GET /series/{series}/markets/{ticker}/candlesticks
    ?start_ts=&end_ts=&period_interval=<minutes>
```

Returns `yes_bid`/`yes_ask` open/high/low/close per period. **This is the only
way to read a past Kalshi quote**, which makes it the foundation of
closing-line value.

Read at a fixed horizon before close, not from `last_price`: the last trade in
a settled market usually happens *after* the outcome is effectively known, so
`last_price` has already converged and any "edge" measured against it is
convergence, not signal. Re-run at a second horizon — if the result moves, it
was convergence.

## Fees

Formula and provenance are documented at length in `backend/core/fees.py`.
Short version:

- Kalshi's official PDF returns **HTTP 429** to automated fetches. It did when
  the previous project was written and it still does.
- Secondary sources now **disagree**: single `0.07` coefficient rounded up per
  *order*, versus a ~`0.06` sports multiplier rounded to nearest cent per
  *contract*. Neither dominates; they differ by 14% at 50c and reverse at 20c.
- `calculate_fee` returns the **maximum** across candidates. Understating a fee
  makes a losing bet look profitable and corrupts the measurement record;
  overstating one only costs a marginal bet.
- **A bet held to settlement pays ONE fee.** Trading pays two. This is the
  venue's actual advantage.
- Fees peak at 50c and are symmetric, so in percentage terms **cheap contracts
  are the most expensive**.

Resolve it with real fills: `/portfolio/fills` reports the fee actually
charged. Store `fee_predicted` beside `fee_actual` and treat any mismatch as
stop-the-line.

## Endpoints in use

| Path | Purpose |
|---|---|
| `GET /events?with_nested_markets=true` | discovery — the only sane universe walk |
| `GET /markets?event_ticker=X` | settled-event markets (nested absent) |
| `GET /markets/{ticker}/orderbook` | depth probe |
| `GET /series/{s}/markets/{t}/candlesticks` | historical quotes → CLV |
| `POST /portfolio/orders` | place |
| `DELETE /portfolio/orders/{id}` | cancel |
| `GET /portfolio/orders` / `positions` / `balance` / `fills` | account state |

**Rate limiting is on us.** The previous project had no rate limiting, no 429
handling, no `Retry-After`, and no retry anywhere. Its discovery routine fired
up to 100 sequential requests, each opening a fresh client, inside a bare
`except Exception: continue` that misreported throttled markets as illiquid.

## Time zones

Store epoch **milliseconds, UTC, as integers** everywhere. The previous project
parsed tz-aware timestamps then called `.replace(tzinfo=None)`, which *discards*
the offset instead of converting — every `seconds_to_close` was wrong by the
local UTC offset. Integers cannot be wrong in that way.

## Credentials

- `KALSHI_API_KEY` — the key **id**, not a secret blob
- `KALSHI_PRIVATE_KEY_PATH` — path to the RSA `.pem`, kept **outside** the repo
- `.env`, `*.pem`, `*.key` are gitignored from the first commit

**Never read, echo, log, or write the private key.** If it is ever pasted into
a transcript, treat it as compromised and rotate it. `verify_auth.py` prints
pass/fail only — never key material.
