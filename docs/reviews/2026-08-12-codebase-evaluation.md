# Codebase Evaluation - 2026-08-12

## Scope

Repository: `C:\Users\josep\Documents\Claude\Projects\kalshi_betting_tool`

I evaluated the backend, frontend, tests, CI configuration, repo instructions,
and current project task notes. I did not call Kalshi, Fly.io, GitHub, or any
live service. I did not inspect `.env` contents or secret material.

This is a sampled code review and verification pass, not a formal audit of
every line. The strongest coverage came from reading the money path, Kalshi REST
client, scoring path, fee/sizing code, auth boundary, tests, and CI.

## Verification Run

| Command | Result |
| --- | --- |
| `.\.venv\Scripts\python.exe -m ruff check .` | Passed: `All checks passed!` |
| `.\.venv\Scripts\python.exe -m pytest -q` | Passed: `2494 passed, 1 warning in 519.56s (0:08:39)` |
| `npm run build` from `frontend` | Passed in ~75.7s; emitted one Next.js middleware deprecation warning |

Pytest warning observed:

```text
StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.
```

Next.js build warning observed:

```text
The "middleware" file convention is deprecated. Please use "proxy" instead.
```

## Executive Summary

This is a notably disciplined measurement-first codebase. The central risk
model is stated honestly, tests encode many past production failures, money is
represented in integer tenths of a cent, and the live order path revalidates
state server-side instead of trusting UI affordances.

I did not find a current P0 issue or a reachable live-money execution path with
the code as written. The backend has `ORDERS_ARE_DRY_RUNS = True` in
`backend/store/orders.py:129`, and `POST /api/orders` is behind backend auth at
`backend/api/routes.py:1268`. The order path then rechecks recommendation
freshness, game timing, quotes, sizing, risk caps, exposure, and gate state
before it reaches `OrderPlacer` at `backend/api/routes.py:1798`.

The main active risk is narrower and familiar to this repo: one CLV-critical
Kalshi wrapper still collapses a renamed or missing response envelope into an
ordinary empty list. That is exactly the class of defect the repository already
documents and tests against elsewhere.

## Findings

### P1 - Missing `candlesticks` envelope is treated as "no candles"

`backend/kalshi/rest.py` has a strong helper contract for envelope parsing:
`_require_list()` at `backend/kalshi/rest.py:102` explicitly distinguishes a
missing key from a real empty list. Its docstring names this as the repo's
single most-repeated defect class.

The CLV primitive does not use that helper:

- `backend/kalshi/rest.py:476` defines `candlesticks()`.
- `backend/kalshi/rest.py:502` returns `payload.get("candlesticks") or []`.
- `backend/scoring.py:162` consumes `kalshi_client.candlesticks()`.
- `backend/scoring.py:226` increments `candles_missing` when the returned list
  is empty.

That means a Kalshi response like `{"candlestickz": [...]}` or any other
renamed/missing envelope would be recorded as "this market has no history"
instead of "the parser no longer understands the wire format." Because this
feeds CLV scoring, the failure mode can quietly remove evidence from the live
gate and measurement loop.

The codebase already knows this specific weakness. `scripts/reconcile_candle_ask.py:681`
comments that `rest.candlesticks` uses `payload.get("candlesticks") or []`, so a
renamed key is indistinguishable from missing history. Existing tests cover the
same rename-vs-empty problem for paginated lists, fills, settlements, and
orderbooks in `tests/test_rest.py:331`, `tests/test_rest.py:376`, and
`tests/test_rest.py:453`, but I did not find the equivalent REST-client test
for `candlesticks()`.

Recommended fix: make `candlesticks()` call `_require_list(payload,
"candlesticks", "/series/{series}/markets/{ticker}/candlesticks")`, then add
the discriminating tests: renamed envelope raises, real empty `candlesticks: []`
returns `[]`.

### P2 - `positions()` and `orders()` repeat the same quiet-empty pattern

The portfolio methods below still use the older parsing pattern:

- `backend/kalshi/rest.py:509` defines `positions()`.
- `backend/kalshi/rest.py:511` returns `payload.get("market_positions") or []`.
- `backend/kalshi/rest.py:513` defines `orders()`.
- `backend/kalshi/rest.py:517` returns `payload.get("orders") or []`.

The adjacent `fills()` and `settlements()` methods have already been hardened:

- `backend/kalshi/rest.py:519` defines `fills()`.
- `backend/kalshi/rest.py:567` calls `_require_list(payload, "fills", ...)`.
- `backend/kalshi/rest.py:569` defines `settlements()`.
- `backend/kalshi/rest.py:605` calls `_require_list(payload, "settlements", ...)`.

I did not find a current production caller of `positions()` or
`KalshiRestClient.orders()` in the sampled search, so this is lower severity
than `candlesticks()`. It is still worth fixing now because reconciliation,
cancel, portfolio, or exposure tooling is likely to reach for these methods.
Future code should not inherit the same "renamed means empty" behavior that the
repo has already rejected.

Recommended fix: move `positions()` and `orders()` onto `_require_list()` and
add the same renamed-envelope and genuine-empty tests used for fills and
settlements.

### P2 - The live frontend auth boundary uses a deprecated Next.js convention

`npm run build` passed, but Next emitted:

```text
The "middleware" file convention is deprecated. Please use "proxy" instead.
```

The affected file is not decorative. `frontend/src/middleware.ts:36` implements
the gate in front of the live cockpit, and `frontend/src/middleware.ts:64` to
`frontend/src/middleware.ts:68` defines the matcher that covers pages and
proxied API routes.

This is not a current auth bypass. The build succeeded, and the middleware code
still exists. The risk is upgrade-driven: a future Next.js release or migration
could turn the deprecation into a hard break or an accidental auth gap if the
rename is handled mechanically.

Recommended fix: migrate the auth boundary to the current Next.js `proxy`
convention and keep tests or smoke checks proving that protected pages,
proxied `/api/*` routes, login, session, health, and static assets preserve the
same behavior.

### P3 - Test harness dependency warning should be retired

The full backend test suite passes, but emits a Starlette deprecation warning
about `fastapi.testclient.TestClient` and `httpx2`. Current imports include:

- `tests/test_api.py:15`
- `tests/test_agent_wiring.py:597`
- `tests/test_store.py:729`

This is not a product bug today. It is a dependency-drift risk: the suite is one
of this repo's main safety rails, and a future FastAPI/Starlette/httpx upgrade
could turn a warning into a broad test failure.

Recommended fix: either pin the current compatible stack explicitly, or schedule
the migration path recommended by Starlette/FastAPI and keep the warning budget
at zero afterward.

### P3 - Public README test count is stale

`README.md:218` says:

```text
python -m pytest -q                         # 1,202 tests
```

The current local run reports `2494 passed`. `tasks/todo.md` also contains
older historical counts such as `553 tests` at `tasks/todo.md:329` and
`1,405 tests` at `tasks/todo.md:443`.

The task file can reasonably preserve history, but the README is an onboarding
and public-portfolio surface. A stale test count weakens trust in otherwise
careful documentation.

Recommended fix: update the README to avoid a precise count, or replace it with
the current count and date, for example `pytest suite passed locally on
2026-08-12: 2,494 tests`.

### P3 - Comment and incident-history density is becoming a maintainability risk

The codebase's narrative comments are valuable: they preserve hard-earned
invariants and explain why many defensive checks exist. The density is now high
enough that stale prose is itself a risk.

Examples:

- `backend/api/routes.py` is 2,446 lines.
- `tasks/lessons.md` is 6,563 lines.
- `backend/kalshi/rest.py` correctly documents the missing-envelope problem at
  `_require_list()`, while the same file still has `candlesticks()`,
  `positions()`, and `orders()` using `payload.get(...) or []`.
- The README test count is stale despite the local suite being green.

This matters because the repo is explicitly intended to become public. A reader
should be able to distinguish current operational contracts from historical
incident notes quickly.

Recommended fix: keep module-level comments focused on executable contracts and
link out to ADRs or `tasks/lessons.md` for long incident histories. For the
highest-risk contracts, prefer tests over prose so stale explanations cannot be
the only guard.

### P3 - `round_trip_fee()` has an inconsistent invalid-price contract

`calculate_fee()` returns `None` for untradeable prices at
`backend/core/fees.py:130` and `backend/core/fees.py:161`. That behavior is
documented as important because unreadable prices must not become zero fees.

`round_trip_fee()` then adds the two return values directly:

- `backend/core/fees.py:174` defines `round_trip_fee()`.
- `backend/core/fees.py:181` returns `calculate_fee(entry_tenths, contracts) + calculate_fee(exit_tenths, contracts)`.
- `backend/core/fees.py:184` defines `breakeven_edge_cents()`.
- `backend/core/fees.py:193` calls `round_trip_fee(price_tenths, price_tenths, contracts)`.

For an invalid price, this becomes a `TypeError` from adding `None`, not a clear
refusal contract. I found only test/support callers in the sampled search, so
this is not a current money-path issue. It is still worth tightening because
this file is core pricing infrastructure.

Recommended fix: make `round_trip_fee()` and `breakeven_edge_cents()` either
return `None` for untradeable prices or raise a clear `ValueError`. Add tests
for invalid entry and exit prices so the contract is explicit.

## Strengths Observed

- The live order path is deliberately server-validated. The backend does not
  rely on disabled UI buttons for risk control.
- Demo and live modes are separated in configuration and behavior. Demo mode
  cannot submit orders through the protected backend route.
- Money/risk code consistently uses integer tenths of a cent where it matters.
- The test suite is unusually strong for a project of this size: 2,494 tests
  passed locally, including many tests built around captured payloads and prior
  failure modes.
- CI is present and broad. `.github/workflows/ci.yml` runs ruff, pytest, seeded
  warehouse publishing, `dbt build`, frontend build, and a secret scan.
- The repo's strategic honesty is high. The docs state that the current system
  is consensus-only, that large apparent edges are suspicious, and that Kalshi
  cost headroom remains partly unsettled pending H4.

## Residual Risk and Work Not Performed

- I did not run live Kalshi REST/WebSocket calls, so I did not independently
  verify current wire shapes against the exchange.
- I did not run Docker, Fly deploys, or mobile/browser visual checks.
- I did not run `dbt build` locally in this pass, though CI is configured to run
  it and `tasks/todo.md:208` records it green historically.
- I did not perform a dependency freshness audit against current upstream
  package versions.
- I did not review every frontend component line-by-line; the frontend pass was
  focused on API access, auth/session flow, build health, and top-level UI
  structure.

## Priority Order

1. Fix `candlesticks()` missing-envelope handling and add REST-client tests.
2. Fix `positions()` and `orders()` envelope handling while the pattern is
   fresh.
3. Migrate the Next.js live auth boundary from `middleware` to `proxy`.
4. Resolve the Starlette/FastAPI `TestClient` deprecation warning.
5. Refresh README test-count documentation.
6. Clarify the invalid-price contract for `round_trip_fee()` and
   `breakeven_edge_cents()`.
7. Gradually move long incident prose out of hot code paths and into linked
   ADRs or lessons.
