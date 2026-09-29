# 0189 — Sports factors lead the parlay build, and a same-game combination is built with no combined chance

**Status:** Accepted on Joe's word, 2026-09-29 (session 70, option buttons; #200).  Numbered 0189 on `main`: 0188 was the highest and no lane held a DRAFT.
**Date:** 2026-09-29
**Schema:** none. `parlay_lookups.card_key` has no CHECK, so `'game'` needs no migration.
**Tickets:** story #197 under epic #83; #198 (leg census), #201 (rest chip), #202 (game page), #205 (read throttle), #206 (/hedge title); Joe's answers #200
**Extends:** ADR 0071 (a desk for bets that happen anyway), ADR 0187 (a combination the desk did not build is recorded as a lookup), ADR 0164/0165 (RFQ and Take it read the lookup row)
**Leaves standing:** ADR 0071 §2.5 (a per-row fact is shown, never ranked by); ADR 0012 §5 and `core/correlation.py` (no same-game correlation without a measurement); ADR 0036/0037 (no in-house model from public data); ADR 0038 (the tool's hunt is closed); ADR 0112 (no brake of ours bounds a hand bet)

## 1. What Joe decided

He asked to "explore making more parlay options, and stronger ones", with a generic parlay guide pasted in. Mid-session he added, verbatim: **"the kalshi edge shouldnt be a big determinant here. I care less about what the booking is here compared to other places and more about the sports-related factors above all else."**

With option buttons (#200) he picked **all four factors**: who's playing, game-script (same-game) combos, schedule and rest, and matchup stats. He also picked **all four sport groups**: NFL, NBA, MLB postseason, and CFB/NHL.

## 2. The decision

1. **Sports factors lead a parlay build; the consensus-vs-Kalshi price is a fact on the row.** This is his 2026-08-21 ruling ("the edge-finder should have been a feature, but not a determiner"), applied to parlays. The price is still shown everywhere it was. It no longer organizes anything new.
2. **Rest is shown on every parlay leg (#201).** For each team it gives days of rest, back-to-back (nightly leagues) and short week (NFL/NCAAF). It is computed from `odds_fixtures`, the trigger-maintained one-row-per-game schedule: no new source, no credits, no tokens. No previous game on record is `None`, never 0. A failed read leaves the fact null and never fails the card.
3. **A same-game combination is built on `/game/<event>` with no combined chance (#202).** The page lists every leg Kalshi's open catch-all collections accept for one fixture, in a fixed order. Each leg shows its own consensus chance, or "no desk price" with a reason. The scout desk sits beside them, on tap. Joe ticks 2+ legs, the desk mints the combination and writes a `parlay_lookups` row with `card_key = 'game'` and a **NULL fair joint**, and the makers price it by RFQ.
   - **The desk now mints combinations whose legs it cannot price.** Until now a mint required every leg in the candidate pool (`parlays.py:2898-2932`). That rule served a desk that sells priced cards. Here the legs are Joe's picks on sports grounds, so an unpriced leg is shown as unpriced and not refused.
4. **Correlation stays refused.** The page never computes a joint. Its copy says the desk doesn't know how these legs move together and that the makers' quote prices it in. Building our own same-game correlation would be an in-house model from public data (ADR 0036/0037).

## 3. Facts this rests on (measured 2026-09-29)

- **The leg census (#198)** covered 94 of Joe's combos since 2026-09-10. The desk already has a pricing path for almost every leg he plays: the top unpriced kind, `KXNFLTD`, was in 2 of 94 (2.1%). Same-game combos were 5 of 94 (5.3%). Both are under the 10% bar fixed before the count. So "more options" is not a pricing gap, and the rest chip goes on the cross-game legs he actually bets as well as on the new page. This is a count on one account, not a forecast.
- **Same-game combos mint through the catch-alls.** `KXMVENFLSINGLEGAME` and `KXMVENBASINGLEGAME` have **no open collection**. Same-game combos are minted through `KXMVESPORTSMULTIGAMEEXTENDED-R`, `KXMVECROSSCATEGORY-R` and `-SHARD1-R`, all on `exchange_index 1` (kalshi-platform, public GETs over all 1,389 collections).
- **Venue limits.** Game, spread, total, team-total, 1H/1Q and first-TD events allow one rung per combination (`size_max 1`). Prop events allow several.
- **`POST /api/parlays/lookup` cannot carry a same-game set.** It runs `joint_for` *after* the mint, outside any try (`parlays.py:3263`), so a same-game set would mint and then 500 with no row written. The game page is built beside it, not through it.
- **`GET /markets` does not batch comma-joined `event_ticker`s.** It returned `markets: []` (no single-ticker control). The page keeps at most 2 reads in flight on the shared 8/s combo client, so it cannot queue ahead of an armed order or RFQ accept.

## 4. Killed, so no session re-derives them

- **A "strongest parlays today" feed.** It would rank by a gap measured negative (ADR 0071) and need an unmeasured same-game correlation.
- **Any default same-game correlation.**
- **Pitcher splits or strikeout Overs from public rate data** (ADR 0036/0037).
- **Alternate lines and buying points.** 0 of 35,448 alternate rungs carried an Under price, so there is no two-sided consensus.
- **A leg cap from the guide's "2–4 legs".** It is a line of copy, not a ceiling (ADR 0112).
- **Showing matchup facts is not killed.** It is deferred: each needs a data provider (#197). Claiming any factor is an edge stays refused.

## 5. What this does not establish

- Whether any sports factor predicts anything. The chip and the scout notes are information, not a signal, and nothing measures them.
- A same-game mint's wire response on the live venue. It was stubbed in tests; the first real one is the post-deploy check.
- That the maker's quote on a same-game combination is fair. There is no desk figure to set it against, by design.
- Whether `GET /markets` batches in some other form (repeated params, another separator).
