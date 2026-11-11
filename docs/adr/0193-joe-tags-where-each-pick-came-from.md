# 0193 — Joe tags where each pick came from, and /bets splits its expected line by that tag

**Status:** Accepted on Joe's word, 2026-10-02. He bet off the desk's recommendations, asked "can you track them and learn from them", and chose "Yes, add the tag" (AskUserQuestion) over a read-only review. Numbered 0193 on `main` after `git fetch`: 0192 was the highest.
**Date:** 2026-10-02
**Schema:** v63, a new table `pick_sources` (tableless version).
**Amends:** the /bets "no breakdown" stance (`backend/bets.py` module docstring, `frontend/src/app/bets/page.tsx` header), and only by adding one more per-group view of the line #287 already serves.
**Leaves standing:**
- ADR 0190 §2.7: no performance registration is made on the game-script cards. This is a record, not a look.
- ADR 0186: leg verdicts are still never joined to a position by the desk. A `verdict` tag is Joe's word, not a join.
- The leg-verdict preregistration's rule that "bought is never a split" governs `leg_verdicts` and is not touched.
- ADR 0071 §2.5: no ordering by result anywhere.
- ADR 0038: nothing here claims an edge.

## 1. Why

Joe follows five kinds of advice: game-script cards, leg verdicts, parlay presets, picks from a Claude chat, and a friend's links. He wants to know how each one does. The record holds every bet but cannot say which advice a bet came from:
- `parlay_positions.parlay_lookup_id` is the newest lookup for the ticker, which is a guess.
- Verdicts are deliberately never joined to a position.
- A chat pick or a friend's link leaves no trace.

## 2. Decision

1. **A tag is stored only by Joe's tap.** It is one of `card`, `verdict`, `preset`, `chat`, `friend` or `own`, kept one per ticker in `pick_sources`. Tapping the chosen chip again clears it.
   - Untagged is NULL. It is summarised as `untagged`, never as `own`.
2. **Suggestions only where the record proves them.** A `game_script_cards.combo_ticker` stamp suggests `card`, and a ladder preset key in `parlay_positions.label` suggests `preset`. A suggestion is drawn dashed and is never stored.
3. **The per-source line reuses #287's machinery, unchanged.**
   - It is wins and losses plus `expected_block`, per kind and never pooled.
   - It lists sources in fixed order and never sorts them by result.
   - A source below 5 expected wins or losses on either side shows `too_few` and no range.
   - Singles show counts only until a source alone reaches 30 settled bets.
4. **The write route touches one table.** `POST /api/pick-sources` is auth-gated and writes only `pick_sources`. A test pins that its handler names no order, RFQ, hedge or positions call.

## 3. What this does not establish

- **That a tag is true.** It is Joe's word after the fact, and a bet built from two sources carries one tag.
- **That any source beats the price.** The line compares results against the prices paid. With a handful of settled parlays, the line says "too few" and nothing else, and that is the correct answer.
- **That a hand-recorded sportsbook slip can be tagged.** It has no ticker, so it cannot be.

## Amendment 1 (2026-11-11): a tailed pick carries the name it came from

**Status:** Accepted on Joe's answers by option button, 2026-11-11. **Schema:** v69 (with ADR 0197). **Tickets:** #420 (the columns), #422 (the chip and the per-name lines), #424 (the name on Check a parlay).

**Why.** Joe said the picks he copies come from sharps he sees on Kalshi's own feed and from a friend, and asked which of them is worth following. One `friend` tag cannot answer that: it pools every person he tails into one line. Asked whether the desk should keep a record per named sharp, he chose "Yes, per name".

**Decision.**

1. **`pick_sources.tailed_from`** holds who a tailed pick came from, in his own word: a Kalshi handle or a person's name, trimmed, at most 40 characters, matched case-folded. Only a `friend` tag can carry one (a CHECK on the column), and NULL means "tailed, no name given", never a person. The key stays `friend` so existing rows and the CHECK on `source` hold; its label on screen becomes "Tailed pick".
2. **`parlay_lookups.tailed_from`** holds the name typed into "Who is this from?" on Check a parlay. A bought ticker whose check carried a name is *offered* that name; the tag still exists only after his tap (§2 of this ADR, unchanged).
3. **Names are never inferred and never backfilled.** Joe chose names going forward only; the tickets settled before this amendment stay untagged, and untagged is still counted on its own and never read as `own`.
4. **The per-name line is the per-source line, one level down.** Wins and losses plus `expected_block`, per kind; `too_few` and no rate below 5 expected each side; names listed in first-used order and never sorted by any result (ADR 0071 §2.5). No "best", no ranking, no colour tied to a result.

**What this does not establish.** That a name is right: it is his word, and one handle may be typed two ways. That any named source beats the price: at the pace he tails, one name needs on the order of a hundred settled tickets before its line can say anything but "too few", and until then that is the correct answer. Nothing about the tickets settled before 2026-11-11.
