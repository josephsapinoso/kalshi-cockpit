# 0187 — A parlay the desk did not build is recorded as a lookup read off the venue

**Status:** Accepted on Joe's word, 2026-09-25 (sessions 60–61, option buttons).  Numbered 0187 on `main`: 0186 was the highest and no lane held a DRAFT.
**Date:** 2026-09-25
**Schema:** none. `parlay_lookups.card_key` has no CHECK constraint, so the new value `'checked'` needs no migration.
**Tickets:** story #165 under epic #83; tasks #166 (backend), #167 (screen), #168 (/bets); screenshot half split to #169
**Extends:** ADR 0164/0165 (RFQ and Take it read "the record" from `parlay_lookups`), and the #96 precedent that a combination's legs are read off the venue's own market
**Leaves standing:** ADR 0071 (a per-row fact may be shown, never ranked by); ADR 0046 (no fee-net EV near a combination price); ADR 0112 (no brake of ours bounds a hand bet, and this adds none); ADR 0063 (`gate.py` reads none of this)

## 1. What Joe decided

#164, 2026-09-25: 82 of his 142 settled parlays (58%) carried no desk reading, because **"its my friend's parlay"**: he tails parlays a friend builds. Asked whether the desk should check a parlay someone else built: **"yes, build that."**

Session 61, option buttons:
- What does a friend send? **A kalshi.com link, and sometimes a screenshot.**
- What should the desk do with a screenshot? **Link now, screenshot later** (#169).
- A sample link? **None to hand.** The URL shape comes instead from two public kalshi.com combination pages that kalshi-platform found by web search (`/markets/<series>/<slug>/<event>`). It is still unconfirmed against a link a friend actually sent.

## 2. The decision

`POST /api/parlays/check` takes pasted text and finds the combination's **market** ticker in it. A kalshi.com link carries the series and the event, never the market (kalshi-platform review, 2026-09-25), so the check prefers a market-shaped token, resolves an event-shaped one through the venue, and refuses unless that event has exactly one market. It then reads that combination's legs from `GET /markets/{ticker}` (`mve_legs`). Each leg is priced from the desk's candidate pool with the combinability filter off (a minted ticker proves its legs combine), and the conservative joint comes from `joint_for`. The check reads the book, then writes **one `parlay_lookups` row with `card_key = 'checked'`**.

That row is the whole integration. Ask the market (`combo_rfq._recorded_lookup`), Take it and /bets (`bets.chance_when_priced`) all read `parlay_lookups` by ticker, so all three see a friend's parlay without a line of change.

**This widens what "the record" means.** Until now, `_recorded_lookup` found only combinations the desk itself had minted from a card. It now also finds combinations the desk read off the venue. The legs are still the venue's own, never the request's. That is the same rule #96 applied to a held combination with no lookup, and the reason `_recorded_lookup` refuses a ticker with no row.

## 3. Rules that hold

- **An unreadable leg is unknown, never 0.** A leg the desk has no consensus for (a prop it does not carry, a started game, a stale price) shows "no desk reading for this leg" with the reason. The whole-parlay chance is then `NULL`, and the row is still written.
- **Same-game legs get no joint.** Their correlation is unmeasured (ADR 0012 §5), so each leg shows its own chance and no product is taken.
- **No verdict, no ranking.** The check shows facts; it never says take or pass, and it fires no leg verdict (#151 costs about 51K tokens a verdict and is Joe's tap, not this one's).
- **Asking the makers is offered only on shard 1 and only while the market is active.** The RFQ path hard-codes `exchange_index=1`, and an unsharded KXMVE market carries `exchange_index: 0` (`tests/fixtures/combo_priced_markets.json`). On any other shard or status, the check still shows its reading and says why asking is unavailable (`rfq_available`). Making `combo_rfq` shard-aware is a separate decision.
- **It costs** two or three Kalshi reads per check, with zero odds credits and zero tokens. It never mints a market.

## 4. What this does not establish

- Whether the desk's chance on a friend's parlay is any good. The signal is settled negative for planning (CLAUDE.md). This is transparency at the moment of a bet, not an edge.
- How many of the 82 the check could have read. That is measured once the path is live (#169).
- Whether a link a friend actually sends has the `/markets/<series>/<slug>/<event>` shape. That shape comes from two public pages. Both of their events return zero markets today, so the refusal path is the only one they exercise. On 2026-09-25, one of Joe's own combination events did resolve to exactly one market through `GET /markets?event_ticker=`.
- That a ticker's name gives its shard. Joe's `KXMVECROSSCATEGORY-S2026E88B8F612C7-BC51BCBD213` has no `SHARD1` in its name and carries `exchange_index: 1`, so the check reads the field and never parses the name.
