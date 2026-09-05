# `backend/api/routes.py` — the split map, taken before the split

**Status: a plan, not a decision.** Nothing here has been executed. It exists
because `routes.py` is **333,958 bytes** against the Read tool's 262,144-byte
ceiling, so **no session can read it**, and every session that needs it greps
blind. `tests/test_session_files_are_readable.py:73-76` holds it on a ratchet
(it may shrink, it may not grow) and that ratchet is a holding action, not a
fix. **71,814 bytes have to come out** — roughly ten times what docstring
relocation bought on `inspect_live_db.py`, so trimming prose will not reach it.

Taken read-only on 2026-09-04 by an `Explore` agent, then spot-checked against
the file: 45 `@app.` decorators, `return app` at line 5829, `_signal_cache` at
5856, `_serialise` at 6425, `_slate_filter_sql` at 6252, `backend/api/__init__.py`
empty (0 bytes), the ratchet at 333,958, and `test_board_sized_to_zero.py:252`
requiring the `/api/board` and `/api/slate` decorators to be adjacent in one
file. The only `nonlocal`/`app.state`/`APIRouter` hit in the whole file is a
comment at line 615 explaining why `quotes` is a dict.

## 1. The shape

`create_app` runs **495–5829** (269,838 bytes) and holds all 45 handlers as
closures. Above it: imports and `logger` (1–172), `recorder_fields` (174) and
`cap_display` (193), 18 Pydantic models (214–494). Below it: the signal cache
and payload (5830–6008), `_replay` (6009), nine small DB writers (6059–6223),
`_gate_open` (6224), and the serialisation core ending in `_serialise`
(6425–6754, 18,785 bytes).

**Closure locals every handler draws on**, all defined before the first
decorator at line 825: `app_config` 550, `gate` 551, `risk` 552, `staleness`
553, `odds` 556, `thresholds` 564, `quotes` 616 (mutable cache), `live_quotes`
620, `combo_clients` 635, `combo_api` 637, `hub` 648, `lifespan` 659, `app`
679, `require_auth` 698, `get_conn` 721, plus two health helpers. Defined
mid-body and still in scope: `_resolve_scout_fixture` 2156, `_run_scout_desk`
2206, `_refresh_quote` 4206, `_place_order` 4240 (39 KB), `manual_config` 4983
and six manual helpers.

## 2. What makes the split safe

- **No handler calls another handler.** All 45 names were scanned for non-`def`
  call sites; zero hits.
- **No `nonlocal`, no `global`, no `app.state`, no `APIRouter`.**
- **One genuinely shared dependency:** `_serialise`, used by board, slate,
  market **and** ledger. Everything else has exactly one consumer.

## 3. What makes it dangerous

Fourteen tests read `routes.py` **as source text** or import a symbol from its
namespace. Each breaks silently or loudly on a move, and a monkeypatch pinned
to a name that has moved does not fail — it patches nothing and the test
passes while testing the wrong thing.

| Pin | Where | What it holds |
|---|---|---|
| `RATCHETED_EXEMPTIONS` | `test_session_files_are_readable.py:76` | fails on growth **and** once the file is under the ceiling — delete it last, by design |
| two `OrderPlacer(` constructions | `test_manual_orders.py:768-781` | counts exactly 2, at 4755 and 5702 — which land in **different** modules |
| `place_manual_order` body slice | `test_manual_orders.py:788-799` | needs `rest=` and the dry-run branch |
| `manual_store.is_combo_ticker` | `test_manual_orders.py:1188-1201` | AST parse of the file |
| `max_odds_age_ms=staleness.max_odds_age_s * 1000` | `test_suppression.py:790-808` | occurrences at 2009, 3138, 3187, 3242 |
| `assert_kalshi_quote_age_limits_agree(` | `test_suppression.py:954` | line 576, stays in `routes.py` |
| `assert_risk_day_start_agrees(` | `test_risk_day_agreement.py:169` | line 584, stays |
| `loop_idle_interval_ms=loop_idle_interval_ms_from_env()` | `test_watcher_decides_from_fresh_facts.py:396` | line 2022 |
| `f.overround` | `test_fair_value_steps.py:45,60` | 2047, 2120 |
| board prose | `test_board_screen.py:672` | 1070–1072 |
| **board/slate decorator adjacency** | `test_board_sized_to_zero.py:252` | requires both decorators in one file |
| slate sort preamble | `test_slate_sort_carries_no_claim.py:45,67,96` | `inspect.getsource`, a 1,600-char preamble |
| `OrderPlacer(dry_run=…)` AST scan | `test_execution.py:380` | across production files |
| `size_position` has a caller in `routes.py` | `test_has_callers.py:827` | it is at 4555, inside `_place_order` |
| `BILLED_PATH_SOURCE` keyed on `routes.py` | `test_has_callers.py:1407` | the scout's billed path |

Symbols imported by name and needing a re-export shim: `create_app` (30+ test
files, `backend/main.py:61`, `docker/entrypoint.sh:253` as `--factory`),
`recorder_fields`, `_signal_payload`, `_signal_cache`, `_decode_books_used`,
`_slate_filter_sql`, `_serialise`. Monkeypatch targets in the `routes`
namespace: `KalshiRestClient`, `OrderPlacer`, `reserve_order`, `record_outcome`.

## 4. The proposed cut

A plain `register(app, *, app_config, gate, risk, ...) -> None` per module — a
closure factory, so **handler bodies move byte-identical**: no `Depends`
rewiring, no router prefix, no `app.state`. `create_app` calls each `register`
in today's order, preserving route registration order.

| File | Contents | Est. bytes |
|---|---|---|
| `routes.py` (kept) | imports, prologue 495–824, health/stream, 12 `register()` calls, re-export shims | ~36,000 |
| `api/schemas.py` | the 18 models, 214–494 | ~12,500 |
| `api/serialise.py` | `_serialise` and its six helpers | ~29,000 |
| `api/routers/board.py` | 996–2155 | ~65,000 |
| `api/routers/orders.py` | 4183–4981 + writers | ~46,500 |
| `api/routers/manual.py` | 4983–5827 + writers | ~44,000 |
| `api/routers/{scout,ledger,status,parlays,hedge,odds,estimates}.py` | | 7,000–21,000 each |

Largest result 65 KB; `routes.py` drops to ~36 KB.

## 5. The order, and why it is this order

Run the full suite between steps. Each step is independently revertable.

1. **`schemas.py`** — pure move, zero pins. Safest possible first step.
2. **`serialise.py`** — move, then import the four pinned names back into
   `routes.py` so three tests pass unchanged.
3. **`hedge`, `scout`, `parlays`, `odds`** — nearly pin-free. Note `test_suppression.py:790`
   scans `routes.py` for a string that also lives at 2009 in `window`; either
   keep `window` in `routes.py` or update that test in the same commit.
4. **`status`** — carries `_signal_cache`; re-export it and `_signal_payload`.
5. **`ledger`, `estimates`.**
6. **`board`** — the pin-heavy one; six tests change in the same commit.
7. **`orders` then `manual`, together** — `test_manual_orders.py:768` counts
   `OrderPlacer(` across one file and the two constructions land in different
   modules, so that assertion becomes a two-file scan.
8. **Delete the ratchet.** It self-fails once the file is under the ceiling.

## What this does not establish

- **That the split is worth doing now.** It is a per-session tax, not an
  outage. The decision is the next session's, with the partner.
- **That the byte estimates are exact.** They are line-range sums; the
  `register()` boilerplate and re-export shims add a few hundred bytes per file.
- **That the pin list is complete.** It is every pin found by grepping `tests/`
  for `routes.py`, `from backend.api.routes import` and `monkeypatch.setattr`
  on that namespace. A pin written between this map and the split is not here,
  so **re-run those greps before starting**, not just after.

## Executed — 2026-09-05, steps 1–5 and step 8

**This note supersedes the "nothing here has been executed" line at the top.**
Steps 1–5 ran on branch `worktree-wf_e0ee5ede-e97-2` off `ef8434b`, one
commit per step, every handler body moved byte-identical (stdlib `tokenize`
on both sides, ignoring only NL/NEWLINE/INDENT/DEDENT/COMMENT positions:
23 + 6 + 19 + 10 + 15 definitions compared, 0 differences). Steps 6 and 7
were **not** funded and did not run: board, slate, window, market and its
candles, orders, manual, health and the stream stay in `routes.py`.

| File | Bytes |
|---|---|
| `backend/api/routes.py` | **193,733** (was 333,958; 68,411 under the ceiling) |
| `backend/api/schemas.py` | 12,774 |
| `backend/api/serialise.py` | 26,493 |
| `backend/api/routers/__init__.py` | 2,490 |
| `backend/api/routers/scout.py` | 16,341 |
| `backend/api/routers/parlays.py` | 18,523 |
| `backend/api/routers/hedge.py` | 6,754 |
| `backend/api/routers/odds.py` | 10,247 |
| `backend/api/routers/status.py` | 21,193 |
| `backend/api/routers/ledger.py` | 19,045 |
| `backend/api/routers/estimates.py` | 21,166 |

Where execution departed from the plan, and why:

- **17 models, not 18.** The map's count was the only thing that changed.
- **Step 8 ran after step 3, not after step 7.** Step 3 alone took
  `routes.py` to 250,903 bytes — under the ceiling — and the ratchet's
  `test_an_exemption_does_not_outlive_its_reason` went red there by design.
  Leaving it red through steps 4 and 5 would have made three commits
  unrevertable on their own, so the dict, its two parametrised tests and
  the `not in` clause were removed in their own commit (`ed17dd4`) between
  steps 3 and 4. The general check now covers the file; observed red with
  the limit lowered to 250,000.
- **`tests/test_has_callers.py`'s allowlist is `BILLED_PATH_CALL_SITES`,
  not `BILLED_PATH_SOURCE`** (that is the string constant for `base.py`).
  The scout key moved to `backend/api/routers/scout.py`; the only edit in
  that file.
- **The one pin the map did not list**:
  `scripts/dry_run_fair_price_downsample.py`'s `F2_KNOWN_READERS`, consumed
  by `check_p1()` which greps `backend/` for the literal `fair_prices` and
  no pytest calls. `serialise.py` (step 2) and `routers/ledger.py` (step 5)
  were added; `routes.py` stays because the board, slate and market-detail
  LEFT JOINs are still there. Verified by running the check before and
  after each entry: `False` naming the new module, then `True`.
- **A re-export can be spelled right and bound wrong, and nothing goes
  red.** `routes.py` re-imports `_signal_cache` from `routers/status.py`
  because `tests/test_clv_signal.py` clears it through the old namespace.
  Binding a *fresh* dict there instead passed 47 of 47 — every case seeds
  identical data, so clearing the wrong dict is invisible.
  `tests/test_routes_reexports.py` is new and pins the identity of every
  re-exported object; it fails under that mutation.
- **The `KalshiRestClient` monkeypatch seam** (`test_parlay_lookup.py:240`,
  `test_combo_bid_routes.py:165`) survives because `parlays.register`
  receives `combo_api` — the closure `create_app` built, which resolves the
  name in `routes`' namespace on the first tap — and the router imports
  neither the class nor `routes`. Verified by making the router build its
  own client over an `httpx.MockTransport`: 27 of 71 failed.
- `test_suppression.py:790` turned out to be a presence check, not a count;
  the `window` occurrence stays and the three in parlays travelled.
- Imports that only moved handlers used were pruned from `routes.py` after
  each step. `ruff --isolated --select F401` on the final file lists four:
  `_decode_books_used`, `_signal_cache`, `_signal_payload` (the deliberate
  re-exports) and `MANUAL_ORDER_MAX_SPEND_TENTHS` (unused before this
  work; untouched).

What this note does not establish: that steps 6 and 7 are worth doing.
`routes.py` is readable now; the remaining 194 KB is the board/slate pair
one test needs adjacent and the order path one test counts constructions
in. Both are pin-heavy and neither is needed for the ceiling.
