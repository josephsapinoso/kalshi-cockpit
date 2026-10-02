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
