# 0068 — The desk is present fully: five areas, nothing behind a reveal

**Date:** 2026-08-23
**Status:** Accepted.
**Amends**, on the owner's word, the market page's 2026-08-21 clause that
fair never appears on a single-game page; **keeps** edge, EV, and size off
that page, and break-even off any block that shows fair%.

## 1. What happened

Joe, 2026-08-23, after the empty-board frustration (ADR 0067's context):
*"I would also prefer the desk to be present fully. I don't want to hover
over every game anymore. I want to see a separate area for the 1) skeptic
2) willy balters 3) the scout 4) specific team/sport specialist and 5) the
consensus."*

The screen already had most of these facts — behind reveals. The master's
read and the staff filings sat in `<details>` elements; the consensus facts
were spread across slate-row Hints; the skeptic existed only as a
`suppressed_reason` string. The owner rejected the reveal pattern outright.

## 2. The decision

**`/market/[ticker]` renders five named areas, all fully present:
Consensus · Skeptic · Scout · Specialists · Willy Balters.** An anchored
in-page nav row links to each — navigation is allowed, concealment is not.
The one `<details>` that survives in the desk is the SpendDisclosure meter
(chrome, not desk content); the chart's `<details>` predates this ruling
and stays (the chart was never one of the five areas).

Per area:

1. **Consensus** (`ConsensusPanel.tsx`, free): the devigged consensus
   chance (`fair_percent_display`, side named explicitly — a NO row's
   chance is the chance the YES team loses), the anchored book set,
   `anchored_on_sharp` with the soft-fallback warning, the width, the full
   book distribution (`DispersionStrip`), Kalshi's own drift — and the
   standing explainer Joe asked the site to carry: pitchers, bullpens,
   weather, umpires and lineups are already priced into the sharp line
   (ADR 0036/0037 as product copy), so the tool computes none of them; the
   scouts hunt only news newer than the line.
2. **Skeptic** (`SkepticPanel.tsx`, free — the scheduled LLM Skeptic stays
   retired, ADR 0062): the twelve mechanical checks with per-row verdicts,
   reconstructed exactly from `suppressed_reason` by
   `suppression.gauntlet_view` (fail-only checks report `not_taken` when
   their value-present sibling ran; `sizing:` refusals pass through;
   unknown codes surface). Codes render verbatim with the gloss as caption
   (ADR 0050), and the as-of caption always renders — verdicts are facts
   about when the row was judged.
3. **Scout**: the existing desk, with the master's read out of its
   `<details>`.
4. **Specialists**: the staff scouts ARE the per-team specialists; their
   full filings render in their own section (already persisted in
   `scout_briefings.staff_json`, already served — this was rendering work
   only). Every state renders in words: filed ≠ filed-nothing ≠ running ≠
   never-sent.
5. **Willy Balters**: the seat is ADR 0069's; until it lands the section
   states so honestly rather than the nav linking into nothing.

**The backend change:** `/api/market/{ticker}` joins `fair_prices`, serves
the book distribution and drift with the slate's own helpers, and serves
the `gauntlet` — and deliberately does NOT serve `breakeven_win_rate`,
because fair% renders on this screen and the pair reconstructs the edge by
subtraction.

## 3. Guards

`tests/test_desk_panels.py` (all-five nav, no `<details>` in the free
panels, exactly one `<details>` in the desk — mutation-verified red — the
explainer pinned, no break-even/edge token in the Consensus panel, codes
verbatim + gloss + as-of in the Skeptic panel);
`tests/test_gauntlet_view.py` (two-way vocabulary pin, branch-pair
`not_taken` and dropped-family mutations red); `tests/test_api.py`
market-detail additions (panels' facts served, full board on a clean row,
no break-even key).
