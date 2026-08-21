# The market screen direction — partner convening, 2026-08-21

Convened on Joe's instruction ("make the market site more useful. ask the
partner to consult with the relevant agents"). Seven agents consulted:
ui-designer, graphic-designer, retail-bettor, sharp-bettor,
tilt-prone-gambler, disciplined-gambler, runtime-realist.

## The ruling that resolved the fleet's disagreement

**Render the venue's facts. Never the tool's opinion.** Ask, quote age,
market status, start time — what you transact against — belong on the page.
Fair, edge, EV, suggested size, Kelly, suppression reason are the refuted
consensus signal (`beta = -0.141`, ADR 0038) and do not go on a single-game
page, now or later: a per-game screen is where a number gets read without the
200 other rows saying no.

## Built the same day (commit history has the details)

1. ScoutDesk above the chart; chart into a closed `<details>` whose summary
   carries "history, not a quote" (the headline used to start below the fold
   at every width).
2. `clear` tiles unlit — only `fresh` carries hue; an annunciator panel is
   dark at rest.
3. The verdict strip is binary — the count was the one number the backend
   schema structurally forbids, manufactured client-side.
4. The board is completed server-side (`complete_board`): missing tile →
   `unconfirmed`, duplicates collapse to most-alarming, `clear` must be
   earned by a matching `searched_for` or finding. Mutation-verified.
5. Glyph as primary channel (▲ / ○ / ? / blank), `text-background` on the
   gold chip (was 2.06:1 in dark), `--border-strong` for the dashed border,
   state rendered verbatim with the model's note as caption (ADR 0050).
6. Header: `Away @ Home`, `YES = team`, league · start · status — clock from
   the linked odds fixture, never `kalshi_events.commence_ms` (ADR 0006).
7. Quote strip: live ages via `now_ms`/`staleness` (were frozen at write
   time); a stale ask is refused outright, not greyed.
8. `close_ms` + `market_status` served and stated — a settled market no
   longer renders like a live one.

## Explicitly NOT doing — named so nobody proposes them in six weeks

- **Fair / edge / EV / size / Kelly / suppression on this page.** ADR 0038.
- **Consensus fair on the price axis, movement alerts, "sharp money"
  colouring, steam indicators.** Each restates a refuted signal or a
  strategy measured to live at ~400ms.
- **The bid/ask history band.** The spread is 1.0c on all 48 bars of the
  committed fixture — a caption, not a chart. (sharp-bettor retracted his
  own proposal after measuring; the lesson is the method.)
- **The NO line and the candlestick toggle.** NO = 1000 − YES; OHLC are one
  number on every real bar. Ranges reduced to Today/All.
- **DispersionStrip, devig readings, book_count, anchored_on_sharp** — need
  a `fair_prices` join and are not a 90-second read.
- **Any model/quant panel** — `model_probability` is NULL forever.
- **A link into `/estimate`** — the study is stopped without result.

## Later, maybe (not committed)

A recorded Pass affordance; an open-position marker without a signed P&L;
per-ticker re-send cap with prior briefings kept; the ADR 0047 desktop
two-column layout; ui-designer's fifth tile state `one_side` for a half-dark
desk.

## Caveats

None of this is verifiable on the demo (no Kalshi creds, stale build) — it
needs a signed-in look at live. The daily-loss context and money framing on
this page remain absent by design; tilt-prone-gambler's observation that the
market page is "the guard-free room" is the standing reason the opinion
columns stay off it.
