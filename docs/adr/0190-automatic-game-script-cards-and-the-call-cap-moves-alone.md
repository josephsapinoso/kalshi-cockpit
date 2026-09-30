# 0190 — Automatic game-script cards: one same-game parlay card per game at T-24h, and the call cap moves alone

**Status:** Accepted on Joe's word, 2026-09-29 (session 70, his (A) to #212; merge and deploy approved for the whole batch). Numbered 0190 on `main` after `git fetch`: 0189 was the highest and no lane held a DRAFT.
**Date:** 2026-09-29
**Schema:** v59, new table `game_script_cards` (tableless version).
**Tickets:** story #213 under epic #83; tasks #214 (S0, this), #215 (S1 seat + on-demand build), #216 (S2 card UI), #217 (S3a watcher), #218 (S3b arm); Joe's answer #212
**Amends:** ADR 0189 (sports factors lead the parlay build; a same-game combination shows no combined chance) — the desk now proposes the same-game build itself.
**Leaves standing:** ADR 0189 §2.4 (correlation refused; the makers' RFQ quote is the only combined price); ADR 0071 §2.5 (shown, never ranked by); ADR 0038 (no edge claim); ADR 0186 (the leg scout and its budget accounting); the `AGENT_MAX_TOKENS_PER_DAY` and `AGENT_MAX_SEARCHES_PER_DAY` ceilings (1.5M, 100), unmoved.

## 1. What Joe decided

Session 70 built two same-game NFL parlays by hand in chat (GB at TB, IND at WAS): Kalshi's single-leg prices read, a web-researched matchup read, a mint, an RFQ. Nothing was accepted. Joe, verbatim: **"I hope you are automating this and i dont have to go into this CLI for you to this much in-depth. the whole point is to add these to may parlay options."**

On #212 he chose **(A)**: a game-script card is built automatically for every game in his sports as it comes within a day of kickoff, and `AGENT_MAX_CALLS_PER_DAY` rises from 40 to 100. He approved merge and deploy for the whole batch: "go ahead, approve the whole batch". That approval covers no RFQ accept and no spend beyond the calls the cards themselves make.

## 2. The decision

1. **A card is one game, a 2–3 leg same-game story on his four factors** (who's playing, game script, rest, matchups), with sourced facts and `drop_if` conditions — or a `skip` with a reason. On screen each leg shows Kalshi's own single-leg ask beside it; "Ask the market" mints through `backend/game_builder.py` and opens `<AskTheMarket>`.
2. **The seat has `backend/agents/leg_verdict.py`'s shape, not a scout convening.** One metered call, at most 3 searches, ~51K tokens by the leg-verdict analogue (29K–90K, n = 17). A convening costs 170K–380K (`docs/measurements/2026-09-23-unattended-scouting-first-reading.md`).
3. **The model never sees a price.** The server puts the asks on screen at read time. The table has no price, probability, confidence or edge column, and a test pins that.
4. **No combined or "as if independent" figure anywhere** (ADR 0189). A figure of that kind was quoted to Joe in chat on 2026-09-29 as teaching; it is not copy and must not become copy.
5. **Cards appear in kickoff order only** (ADR 0071).
6. **Built once, at T-24h** (`GAME_SCRIPT_LEAD_HOURS = 24`). Sunday's NFL is built Saturday around 17:00Z, after Friday's final injury reports. There is no second refresh; the card says inactives come out 90 minutes before kickoff and are not covered.
7. **Record, not a registration.** A card row stores the `combo_ticker` minted from it, so which cards he bet can be counted. Nothing is registered on it and no performance look is owed.
8. **Armed only after one real card's cost is read** from `inspect_live_db.py agent-spend` (`agent='game_script'`). `GAME_SCRIPT_AUTO_ENABLED` ships `"false"`; #218 turns it on.

## 3. Budget

- **`AGENT_MAX_CALLS_PER_DAY` 40 → 100, alone.** The standing rule (`fly.live.toml`, #157) is that the three ceilings move together. This one moved alone, on Joe's word, because cards are call-heavy and token-light relative to convenings: an NFL Sunday is ~14 cards on top of his taps and the leg verdicts.
- **Tokens bind first, then searches.** An NFL Sunday is ~14 cards, ~714K tokens (406K–1.26M by the analogue's range) and 42 searches. The unattended builder keeps to `SCOUT_AUTO_TAP_TOKEN_SHARE = 0.5`, so cards get ~750K a day and Joe's taps keep the rest.
- **Heavy NBA/NHL nights will run past the card share.** A game past it is a stored `refused_budget` row with the ceiling named, and the screen says so. It is not silently dropped.
- If searches bind on a real Saturday, that is a ticket for Joe with the `agent-spend` reading attached. Nothing here moves tokens or searches.

## 4. Not doing

A scout convening per game; a second NFL refresh; prices in the prompt; any combined or independent figure; any order but kickoff; any performance registration; moving the token or search ceilings.

## Amendment 1 — the cost reading, and the token ceiling moves to 9M (2026-09-30, Joe's (D) to #219)

**The reading (#218).** The first real card was `KXNFLGAME-26OCT01PITCLE`, built on live at `766b017` on 2026-09-30 00:59Z through the tap path (`agent_calls.id` 179, `inspect_live_db.py agent-spend`). It cost **286,120 input + 3,252 output = 289,372 tokens, with 2 searches**, and took 57.9 s end to end through `/game-card`, so the inline POST survives the Fly/Next timeouts. The 60K in §2.2 and §3 was the leg-verdict analogue, and it was ~4.8x low. n = 1: this is a reading, not a rate.

**What it meant.** At the 0.5 unattended share of 1.5M, about 2 automatic cards fit in a day, against the ~14 an NFL Sunday needs. Joe was offered four options: shrink the card first (recommended), arm at ~2 a day, tap only, or raise the ceiling. He chose **(D), raise the ceiling, and set it at 9M**. The share then holds ~15 cards.

**The changes.**
- `AGENT_MAX_TOKENS_PER_DAY` 1.5M → **9M**, alone. Calls (100) and searches (100) are unmoved.
- `CARD_TOKEN_ESTIMATE` 60K → **290K**. Without this, one pass would reserve ~60K a card and line up far more builds than the share holds, and each build checks only the full ceiling. The watcher would then spend into the half kept for Joe's taps.
- `GAME_SCRIPT_AUTO_ENABLED` → **true**.

**Superseded, not deleted:** §3's "tokens stay 1.5M" and "~714K for an NFL Sunday (406K–1.26M)". At the reading, an NFL Sunday of 14 cards is ~4.1M.

**Worst case ~$18 a day** at the $2/$10 per million rate `fly.live.toml` quotes, which has not been re-checked. The Anthropic account's own spend limit must sit above this, or the account refuses first. Re-read `agent-spend` (`agent='game_script'`) after the first automatic Sunday. If the mean moves far from 290K, move `CARD_TOKEN_ESTIMATE` with it.
