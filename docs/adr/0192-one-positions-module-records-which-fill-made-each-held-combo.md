# 0192 — One positions module records which fill made each held combo; the hand-bet order path leaves `create_app`

**Status:** Accepted on Joe's word, 2026-10-01 (architecture review candidates A + B, grilled in eight option-button questions with every recommendation taken). Numbered 0192 on `main` after `git fetch`: 0191 was the highest and no lane held a draft.
**Date:** 2026-10-01
**Schema:** v60 (planned, slice S1): three nullable columns on `parlay_positions`. Not built by this ADR.
**Tickets:** story #263 under epic #82; tasks #264 (S1), #265 (S2, blocked by S1), #266 (S3, blocked by S2).
**Supersedes in part:** ADR 0160 §2.1 ("`parlay_positions.stake_tenths` keeps the sent price, forever"), **for rows written after S2 only**. ADR 0160 §2.3 (no backfill) and the rest of 0160 stand, and the read-time join it built remains the path for every row written before v60.
**Amends:** the routes-split stop (`docs/decisions/2026-09-04-routes-split-map.md`), which killed step 7 "until a named constraint the remaining ~194 KB actually violates". The constraint is named in §1.
**Leaves standing:**
- ADR 0063: `gate.py` never reads the manual or position tables, and no `recommendations` row is synthesised.
- ADR 0112 + Amd 1: no ceiling returns. The six correctness checks of §3 are moved, not changed.
- ADR 0164/0165: nothing on the spend paths retries, and the intent row is written before the venue call.
- ADR 0169: writing a position never raises, and `None` is never an error the caller may hide.
- ADR 0143 §3.5: `record_outcome` cannot unwind the order.
- ADR 0145: the entry fee is still added at read time.
- ADR 0178: the RFQ path reads `/portfolio/fills` and writes a position either way.

## 1. Why

**A held combo is written in four places with two opposite conventions.** One insert site exists (`backend/hedge.py:477` and `:502`, inside `record_position`), but four callers decide what goes into it:

| caller | stake written from | fractional fill |
|---|---|---|
| hand-bet order path, `routes.py:4657` `_record_combo_position` | the **sent** price (`contracts * fill_price_tenths`, `:4723`) | **refused**: no position, and a note says so (`:4310–4328`) |
| RFQ accept, `combo_rfq.py:1352` `_record_accepted_position` | the **venue's** average price when `/portfolio/fills` answers usably, otherwise the quote's (ADR 0178) | **recorded**, provided `contracts × 1000` is a whole number of tenths; finer sizes are refused (`:1446–1452`) |
| hand entry, `routers/hedge.py:105` | typed cents × 10 | n/a |
| venue adoption, `hedge.py:1455` `adopt_venue_combo` | `venue_positions.exposure_tenths` | the venue's count |

**The row does not say which fill produced it.** `/hedge` reconstructs that on every read. `hedge.stake_bases` (`hedge.py:677–1015`) joins `manual_orders` on `(ticker, submitted_ms)` and `combo_rfq_quotes ⋈ combo_rfqs` on `(ticker, accepted_ms)` against the position's `(combo_ticker, placed_ms)`. It stores an `_AMBIGUOUS` sentinel when two rows share a key, and walks twelve named reasons to decide whether the stake shown is the venue's or the recorded figure. ADR 0145 already called a figure that depends on "an incidental equality" one that "a refactor breaks silently". ADR 0160 §5 named the missing link column as "the obvious follow-up … a second decision and a schema version". This ADR is that decision.

**The armed path's orchestration is reachable only over HTTP.** `place_manual_order` is about 750 lines (`routes.py:3683–4432`) nested inside the `create_app` closure (lines 250–4432). Its only test surface is HTTP plus name patches in the `routes` namespace. Both bugs it has shipped were in that orchestration, not in the store module beneath it: the missing position write (fixed 2026-09-09) and the truncating `int(filled)` (fixed 2026-09-15). And `routes.py` is now **249,220 bytes, 12,924 under the Read tool's 262,144-byte ceiling** (`tests/test_session_files_are_readable.py:86`). That ceiling is the binding constraint the 2026-09-04 split stopped for lack of. It is close again.

## 2. The decision

### 2.1 A positions module owns every write (candidate A)

One module, `backend/positions.py`, is the only caller of the `parlay_positions` / `parlay_position_legs` inserts. Its interface takes **a fill that happened**:
- the source (`manual_order`, `rfq_quote`, `hand` or `adopted`) and that row's id;
- the combo ticker and its legs;
- the venue's count and average price when known, and the sent or quoted price.

It owns, in one place:
- the stake rule (§2.3);
- the fractional rule (§2.4);
- leg recovery from `parlay_lookups`;
- the stake checks (§2.5).

`hedge.record_position` becomes its internal insert. The four callers in §1 call the module and stop computing stakes. `hedge.py`, `bets.py`, `scout_watch.py` and `hedge_watch.py` keep reading the tables, and their `UPDATE` paths (`resolve_leg`, `close_position`) are untouched.

### 2.2 The row records which fill produced it (schema v60)

Three nullable columns go on `parlay_positions`, added by a `_MIGRATIONS` column step on the v54/v55 template (`db.py:1561–1583`):
- `fill_source TEXT CHECK (fill_source IN ('manual_order','rfq_quote','hand','adopted'))`;
- `fill_ref INTEGER`: the `manual_orders.id` or `combo_rfq_quotes` row id, NULL for `hand` and `adopted`;
- `stake_basis TEXT` with `stake_basis_reason TEXT`: §2.5's outcome, stored.

All three are set at write time, only by the positions module. **No foreign key and no join on timestamps.** The id is the link.

### 2.3 New rows store the venue's price (supersedes ADR 0160 §2.1 for new rows)

A position written from a fill stores **the venue's own average fill price × the venue's count** when §2.5 calls that fill usable. Otherwise it stores the sent (order path) or quoted (RFQ path) price × the count. `stake_basis` says which (`venue_fill` / `as_recorded`), and `stake_basis_reason` says why.

**`/hedge` shows the same number it shows today for these rows.** ADR 0160's read already displays `venue_avg_fill_price_tenths × count` wherever the link is provable. This moves that computation from every read to the one write, and makes both fill paths agree on what the column means.

**Why this is now acceptable when ADR 0160 refused it:**
- ADR 0160 §2.1 gave four grounds.
  - "It is the armed path." That is still true, so §4 adds a kalshi-platform review and a lone deploy.
  - "There is no key to the order." §2.2 adds one.
  - "ADR 0145 is the precedent." 0145's precedent was that a correction applies to *stored* rows without rewriting them. §2.6 keeps that.
  - "It is reversible by deletion." So is this: delete the write-side basis and the read path in §2.6 still serves every row.
- ADR 0178 already writes the venue's price on the RFQ path, so the table has carried two meanings for one column since 2026-09-18. One of them had to go.

### 2.4 A fractional fill is recorded on both paths (the RFQ rule)

The hand-bet path's refusal (`routes.py:4310–4328`) is replaced by the RFQ path's rule (`combo_rfq.py:1440–1457`):
- A fill whose `count × 1000` is a whole number of tenths is **recorded at the venue's count**. Its stake is rounded once, to the nearest tenth of a cent.
- A count finer than that is still refused, and it is said out loud.

**Why:** a real bet `/hedge` cannot see is worse than a fractional count. The refusal was added (2026-09-15, ADR 0151) to stop `int(filled)` truncating silently, the flattering direction. Recording at the venue's exact count is not truncation, and the RFQ path has done it since ADR 0178. No real hand-bet fill has been fractional yet, so this changes no existing row.

### 2.5 The stake checks run once, at write, and are stored

The twelve checks `stake_basis_for` runs on every read are the guards on whether a venue figure is trustworthy. They now run inside the positions module for a linked row, and the outcome is stored in `stake_basis` / `stake_basis_reason`:
- no venue price;
- no or unusable venue count;
- fractional venue count (now only the finer-than-a-tenth case);
- contract count disagrees;
- side convention unresolved (a `side = 'no'` order is still refused, not guessed);
- the ambiguous and unmatched cases. With an id link these can no longer arise from a shared key; they can only mean the referenced row is missing.

`/hedge` reads the stored basis for a row with `fill_source` set. The reason vocabulary served on `/api/hedge` (`stake_basis` ∈ {`venue_fill`, `as_recorded`} plus the named reasons) is unchanged, so no screen and no glossary entry moves.

### 2.6 No backfill; old rows keep the read path

Rows written before v60 keep `fill_source IS NULL` and are served exactly as today by ADR 0160's read-time join, `_AMBIGUOUS` sentinels included. That path is **not deleted**. It retires on its own as those positions close, and a later ADR may remove it once a census reads zero open unlinked rows. All three of ADR 0160 §2.3's grounds still hold:
- partial reach;
- no key for old rows;
- a rewrite would move a live figure in the direction that raises the displayed hedge outcome.

### 2.7 The hand-bet order path leaves `create_app` (candidate B)

`place_manual_order`'s body (checks 0–13, venue reads, the IOC send, outcome writing, the position step and the response wording) moves to `backend/manual_order.py`. Its shape is the one `combo_rfq.accept_quote_for_joe` already has:
- **In:** a connection, a venue port (the live quote source and REST client), a placer port and a clock.
- **Out:** the result body.

The route becomes a thin adapter. Step 13 calls the positions module of §2.1. The checks themselves (idempotency, desk lockout, KXMVE acknowledgement, stale-ask refusal, depth at the ask, existing-position check, shard collateral, and reserve-then-check under the write lock) **move byte for byte. None is added, removed or loosened** (ADR 0112 §3–§4).

### 2.8 Location pins keep their claims

About fourteen tests pin where this code lives. Each one keeps **what it asserts** and is pointed at the code's new location:
- `test_manual_orders.py:1327`: exactly two `OrderPlacer(` constructions, each passed its allowed dry-run constant. It now counts across the production tree.
- `:1353`: the armed path builds a REST client under `if not manual_store.MANUAL_ORDERS_ARE_DRY_RUNS:`. It now reads `manual_order.py`.
- `test_combo_fill_is_watched_for_a_hedge.py:565`: the patch on `routes._record_combo_position` moves to the positions module.
- `test_stake_basis_is_the_venue_fill.py:594`, which asserts no `venue_` literal inside `_record_combo_position`, is **retired with a pointer to this ADR**. The claim it pinned, "the order path writes the sent price", is the one §2.3 reverses. Its replacement asserts the opposite claim for linked rows. `TestNothingIsBackfilled` stays as written.
- Each repointed pin is mutation-checked again: disable the guard and watch it go red.

The board/slate adjacency pin (`test_board_sized_to_zero.py:252`) is not touched, because the board does not move.

## 3. What does not change

- **`gate.py`** reads none of these tables (ADR 0063, ADR 0078 D4).
- **No retry anywhere.** A lost venue response on either spend path is still UNKNOWN, still written as such, and still never resent.
- **ADR 0169's "nothing on this path raises".** The positions module returns `None` with a logged reason rather than raising into a trade that has already spent.
- **ADR 0145's entry fee** is still added at read time, beside whichever stake is stored.
- **`manual_orders`** is not altered, and `record_outcome` keeps its signature.

## 4. Delivery

All of this is main-session work, under the CLAUDE.md money-path rule. It ships in three slices, each deployed alone, with `/hedge` read on live after each:

1. **S1:** v60 plus `backend/positions.py`. The RFQ accept, hand-entry and venue-adoption writers move onto it, and `/hedge` reads the stored basis for rows with `fill_source` set. The hand-bet order path is untouched in S1.
2. **S2:** the hand-bet order path writes through the positions module, which brings in §2.3's venue price and §2.4's fractional rule. **kalshi-platform review before merge.**
3. **S3:** `place_manual_order` moves to `backend/manual_order.py`, and §2.8's pins are repointed. **kalshi-platform review before merge.** routes.py's byte count is read before and after.

## 5. Proof

Each slice names its test in its ticket. Across the whole story:
- a linked row's `/api/hedge` stake equals what ADR 0160's read path computes for the same fill. A fixture is run through both paths;
- a fractional hand-bet fill at 2.5 contracts writes a position at 2.5, while a count finer than a tenth writes none and says so;
- an unlinked (pre-v60) row is served byte-identically before and after S1;
- two `OrderPlacer(` constructions exist in production after S3, each with its constant.

## 6. Do not

- Backfill `fill_source`, `fill_ref` or `stake_basis` on pre-v60 rows (§2.6).
- Delete ADR 0160's read-time join while any open position has `fill_source IS NULL`.
- Add, remove or loosen a check while moving the order path (§2.7).
- Let any caller insert into `parlay_positions` except the positions module.
