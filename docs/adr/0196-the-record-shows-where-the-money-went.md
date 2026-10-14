# 0196 — The record shows where the money went, and the build screens teach their own words

**Status:** Accepted on Joe's word, 2026-10-14. He asked, verbatim: *"look at
my bet history. you can see that I am not winning parlays. consult with the
sharp agent and evaluate how i can make better bets and add tool tips.
contemplate other ways we can get winning parlays."* He answered two scope
questions with option buttons the same session: tooltips **plus** a
"where the money went" strip on Your bets, and the sizing vocabulary
(`unit`, `longshot`) **in**. Numbered on `main` after `git fetch`
(`docs/adr/README.md`).
**Date:** 2026-10-14
**Schema:** unchanged.
**Amends:** #355's scope (its leg-**count** half is built here, #397; the
same-game vs cross-sport half stays on #355 behind #331's census).
**Leaves standing:** ADR 0071 (price transparency, never rank by the gap,
no nagging); ADR 0189 (sports factors lead a build, no leg cap, correlation
refused); ADR 0193 (pick-source tags, never sorted by result); ADR 0195 §2
(no sizing rule, no stop rule, parlays as the main product are Joe's
choices); #287 (the summary line says only what the prices say); ADR 0038
(nothing here claims an edge).

## 1. What was read, and what it said

The sharp-bettor reviewed Joe's whole settled record, read from the live
desk's own `/api/bets` that day. The numbers stay on his private page
(operator data never enters the repo, ADR 0062 §4 and the standing rule);
the *shape* of the reading is the decision's ground and is recorded here
without them:

- Singles and combinations both won **inside the range the prices paid
  imply**. The legs, read one at a time by league and kind, hit at or above
  expectation nearly everywhere with a leg CLV median slightly below zero.
  The picks are market-quality; they are not the loss.
- The loss sits in the **shape of the tickets**: the lowest price bands
  carry most of the stake and almost all of the net loss, the longest
  tickets won almost never, and the largest single losses were large
  stakes on very low prices. The fee is real and is the smallest of the
  three.
- Paying above the desk's joint chance did **not** separate winners from
  losers — consistent with the settled signal result, and one more reason
  the gap is shown and never ranked by.
- What it does not establish: that the legs are *good* (many small cells;
  one hot cell is expected by chance); that long shots lose more than their
  price (the lowest band is `too_few`); anything by pick source (nearly all
  untagged); leg detail on the combinations that predate ADR 0194.

The sharp-bettor's verdict, which Joe has: there is no trick that wins
parlays. Fewer legs, a price floor, a flat stake and asking the makers twice
make the losing smaller and slower. Each of those is **his rule, not the
desk's** — the desk teaches the words and shows the numbers.

## 2. Decision

1. **The build screens teach their own words (#396).** Nine glossary keys —
   `implied_chance`, `one_in`, `books_joint`, `quote_spread`, `correlation`,
   `too_few`, `stake_weighted`, `longshot`, `unit` — render as tap-open
   `<Term>` on the Take-it cost line, the maker-quote list, the parlay
   cards' leg facts (hover-only `title=` spans become tappable `<Hint>`s),
   the same-game builder, Check a parlay and Your bets. `leg`, `clv`
   (sign convention), `stake` and `bankroll` (both cited caps ADR 0112
   removed) are corrected.
   - **No threshold-triggered word on the ticket.** The sharp-bettor's
     suggested price floor was read off the record; a word that appears
     when a ticket crosses it is that floor on screen (ADR 0071 decision 2,
     #239 C). `longshot` renders only on Your bets' existing lowest band
     label.
   - `unit` defines a word and recommends no size; `stake` carries no money
     figure (pinned). `correlation` and `books_joint` say what multiplying
     assumes and that the makers price same-game legs in their quote; the
     desk does not compute correlation (ADR 0189).
2. **Your bets shows where the money went (#397).** A `by_shape` block on
   `/api/bets`, combinations only: staked and net per price band on the
   existing `EXPECTED_BUCKETS` edges, and per **exact** leg count,
   ascending, with the `too_few` gate per cell and a "no leg list" row for
   combinations with no recorded legs. Rendered by `ShapeStrip` under the
   by-source strip. Lifetime settled record only; no today window (the
   chase trigger `tonight` refuses); fixed order; no colour by sign; not a
   chart.
   - It lives **beside** `summary`, not inside it, because #287's pinned
     test bans a net figure in the summary payload and its reason holds:
     the expected line says only what the prices say.
   - **No 15c edge and no "5+" bin.** Both cuts were chosen after reading
     the record. The private page labels them as descriptions, not
     findings.
3. **The write-up is a private page**, as ADR 0195's was; NEXT.md links it.

## 3. What this does not establish

- That any shape wins. The strip describes where the money went; no rule
  follows from it (#320), and the desk enforces no floor, cap or stake.
- That the legs are good, or that any source is worth tailing (ADR 0193 §3).
- That a definition is correct — `test_glossary_coverage.py` pins reach and
  length, not truth.
