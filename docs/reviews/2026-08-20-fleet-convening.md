# The fleet convening, 2026-08-20 — why three weeks produced nothing Joe uses

Joe called this review himself, as a complaint: three weeks in, the site has
not been useful for his betting at all. The desk comments are not helpful, the
sharp-bettor persona was expected to be more insightful, the scout should be
analysing head-to-heads, spreads, and qualifying props, and the cockpit should
feel expert. Engineering safety first: an idea is only useful if it does not
break anything.

The partner chaired; the seats were the review fleet. What follows is the
partner's synthesis, verbatim except for this header. Every file:line claim in
it is the partner's or a seat's and is to be **re-verified at build time** —
that is the standing rule, and item 1 of the plan begins with exactly that
verification.

Nothing in this document was deployed on 2026-08-20. The window-gate
measurement rode the live box that day and nothing was allowed to touch it.

---

Confirmed at `backend/estimate_match.py:193-233`, and this is the one defect actively writing false data. The candidate set is `FROM venue_settlements WHERE ticker = ?` — settlements only. If a market has not *settled* within 24h of the estimate, line 227 stamps it:

```python
# He estimated and did not bet.
"UPDATE bet_estimates SET match_status = 'unmatched_no_position' WHERE id = ?"
```

It asserts he did not bet, on a bet he made — and line 180 (`WHERE match_status IS NULL OR match_status = ''`) then excludes the row from every future pass. Permanent, and self-concealing.

---

# The call

**Joe is right, the product is aimed at a question that is answered, and the fix is mostly not new features — it is unblocking things this repo already built and never connected.** Five instruments that would answer his complaint exist in the codebase right now and reach no screen: `/slate`, `breakeven_win_rate`, `portfolio_value_tenths`, the venue mirror of his own 41 bets, and the desk itself. Three weeks produced nothing he uses because the one screen he lands on is the one screen guaranteed to be empty, and the good screen is behind a nav word a beginner cannot distinguish from three others.

**I am not funding the scout, and I am funding spreads as a 4-credit measurement rather than a build.** Details below, with the two places I was wrong.

## A. Why three weeks produced nothing

Four causes, all verified, in order of contribution.

**1. He lands on the empty screen by design.** `/` is the Board — the filter whose output has been `surfaced: 0` on **1,005 consecutive passes** in `live.log`. `/slate` is the screen showing every game with edge as a *column not a gate* — and its own docstring says it was built because **Joe made that exact point on 2026-08-09**. He asked for it, it shipped, and it is nav item #2 labelled "Slate" beside "Board", "Log" and "Ledger". Four words a beginner cannot tell apart.

**2. The board is structurally unreachable at his bankroll.** This is the finding I'd put in front of him. The suppression ceiling is `edge_ceiling_tenths = 40.0` (4.0c) — above that, `suspicious_edge` fires. At a $20.66 bankroll and a 50c ask, Kelly needs **+6.6c** to afford *one contract*. **There is no edge value that both survives the suspicion check and sizes to one contract, across the entire 20c–80c band.** Two limits on one quantity, and nobody carried the note in `fly.live.toml:346` about the reference bankroll one step further to the deployed one.

**3. And the screen mislabels that as a market fact.** `stake_below_one_contract` comes from the *clamp* path, so `sizing.refused` is False, so `engine.py:254` writes no reason, so `routes.py:882` buckets it as **`no_edge`**. The Board says "No edge." The truth is "there was an edge and you cannot afford a contract of it."

**4. The desk is invisible on his phone.** `slate/page.tsx:241` wraps it in `hidden ... sm:inline-flex` — hidden below 640px. **Joe has never seen the desk on the device he bets from.** His complaint is a verdict on something he can only have met on a laptop.

## Two things I got wrong in this review, both flattering my own argument

I am recording these because the pattern matters more than the errors.

**I called spreads dead on venue mechanics.** I quoted the pooled half-spread of 59.6 tenths on Kalshi spread markets. The parts do not agree: `2026-08-09-halfspread-dispersion.md:194-201` shows 836 of 1,071 rows are 2+ days from kickoff at mean 51.4, while the 180–720 minute cell is **5.0 tenths, sd 0.0**. I quoted a pooled number without printing the largest contributor's share — the exact failure CLAUDE.md's measurement rules exist to stop, committed while citing those rules.

**I said Joe lost 60% of his bankroll.** Balance falls when a position is *opened*. The $8.31 reading carries 3 open positions. `schema.sql:924` has `portfolio_value_tenths` specifically to separate these, and it is **written by `portfolio_poll.py:430` and read by nothing.** The honest figure: $20.66 → $15.92 **with zero open positions** is a clean realised loss of **$4.74, 23%, in ~36 hours**.

Both errors ran in the direction that made my case easier. That is the pattern to watch, and it is mine, not a subagent's.

## B. The desk: replace it, don't tune it

There are no prompts to improve. It is three static TypeScript template functions; two of the three voices say the same sentence on every row, and the Scout's line is a permanent admission that it is switched off. Willy has five branches, and two hardcode *"None of these books is anchored sharp"* while the row's own `anchored_on_sharp` may be `true` with Pinnacle in `books_used` — a sentence that contradicts the pixel beside it.

**Decision: kill the bubble and the avatars. Replace with one always-visible line per row on the phone, priority-ordered** — staleness, then old-consensus, then the tape, then the bar. Plus a **provenance disclosure** panel (labelled rows, no faces) carrying what the bubble carried.

**Willy does not become an LLM voice on the Board.** Per-row prose is the one thing every seat that reviews harm independently refused, and I agree: it is the most persuasive object in the product sitting on the least supported claim.

## C. The scout: not funded, and the ask names the wrong component

`backend/agents/scout.py` **cannot do what Joe asked.** Its schema has no numeric field and its system prompt explicitly bans estimating "any probability, fair price, line, or point spread." It returns sourced injury/lineup/weather context for *one* game. "Analyse all the h2h games and spreads" is `runner.py` plus a devig grouping — not this module. ADR 0040 declared quarantine settled; nothing here overturns it.

**What Joe actually asked for is `/slate`, and it already exists.** The fix is surfacing it, not wiring an agent.

**Spreads — I was wrong, and the answer is a measurement, not a build.** The venue side is *better* than the h2h already traded: `KXMLBSPREAD` within 24h of start quotes **1.0c median width with 13,517 median ask depth**, against the moneyline's 1,280 — ten times deeper at the same width. And **15 of 15 games have a sharp book quoting both sides at a Kalshi-listed line**, versus all three actionable h2h rows ever written being `anchored_on_sharp = 0`.

But four things block it, and one would silently produce wrong prices:

| blocker | file |
|---|---|
| moneyline-only filter | `runner.py:1499` |
| linker refuses non-2-sided events | `match/linker.py:280` |
| **`book_quotes_for_event` does not group by `outcome_point`** | `runner.py:367-397` |
| cluster key would inflate `n_clusters` ~3× | `analysis/clv_signal.py:134` |

The third is the dangerous one: pass `market="spreads"` today and books quoting ±1.0 pool with books quoting ±1.5 under the same team name, and the devig returns a number without complaint. A single half-point mismatch moves the probability **4.0 points on totals, 7.1 on runlines** — 2–4× the entire fee bar being hunted. The fourth is the signature trap again: one game becomes three Kalshi event tickers, so G=300 arrives three times sooner on evidence that is not three times as independent, and `clv_signal.py:78` says changing that key is an amendment.

**So: buy ONE `spreads,totals` sweep on one MLB slate. 4 credits above the h2h already bought.** Match `outcome_point` exactly, devig worst-of-four, compare to Kalshi's derived ask net of fees. If the fee-net edge is centred at or below zero — as h2h is — it dies for 4 credits and no blocker gets written. **Registration first.**

**Props: refused.** 10 market keys × 2 regions = **20 credits per fixture**; a 15-game slate is 300/day. The monthly 13,000 caps sustainable spend at ~419/day, so full-slate props is 82–94% of the month. On 2026-08-15 a prop sweep spent **384 of 400 in one pass** and took every other sweep down with it. On-demand already exists (ADR 0032) and has never fired.

## D. The professional cockpit

"Expert" here means **an instrument that shows its readings even when it has nothing to report.** Today ~520 words and ~2,000px of prose sit between the top of the Board and the first number.

The empty state becomes a readings table — bar, closest, refused, no-edge, books age, quote age, β, verdict — not a shrug. Numbers get fixed decimals and tabular figures; colour states direction only. And per the graphic seat: green currently means **fourteen different things**, eight of them unsupported, and `--positive` is 2.2× louder than `--negative` in dark and 0.65× in light — the palette's argument flips with the ambient light.

## E. The plan — blast radius first

**Nothing deploys today.** The window-gate measurement is mid-flight; any deploy restarts the box. Everything below is *build and test locally today, ship tomorrow.*

| # | Item | Blast radius | Joe sees | Cost | Verified by |
|---|---|---|---|---|---|
| **1** | **Fix `estimate_match` premature expiry** + repair pass | `estimate_match.py` only; runs in poller, not the scheduler under test. **Wrong if:** re-stamps rows incorrectly | nothing | 0 credits, S | Guard disabled → test fails; repair pass count reconciles against `fills` |
| **2** | **Caption the fake guard.** `/gate` advertises a kill switch that structurally cannot see a hand bet (`settlements.order_id` is `NOT NULL REFERENCES orders(id)`) | one line of copy | "These caps govern orders this tool would place. They do not see bets you place in the Kalshi app." | 0, XS | Copy test |
| **3** | **Make `/slate` the landing screen; rename nav to plain words** | pure frontend | **The screen he asked for in August is the one he lands on** | 0, S | 390px screenshot |
| **4** | **Promote `Anchor` to the phone**; data above prose; status line | pure frontend | The most important caveat stops being desktop-only | 0, S | `check_mobile.py` |
| **5** | **Cash + open-exposure line**, denominated on **his own $10 reload line**, never $100; delete `(you're net up $X)` | reads `venue_balance_snapshots`; A7 permits | His actual money, where he decides | 0, S | No signed P&L renders |
| **6** | **Break-even at this price**, alone — **no consensus fair beside it** | wires `ev.py:146`, currently callerless | The number that makes him a better bettor | 0, M | Identity test: fair must not co-render |
| **7** | **Write coverage properly** — register the definition *first* | schema + matcher | nothing | 0, M | Amendment recorded before computing |
| **8** | **Spread falsification test** | measurement only | nothing | **4 credits**, M | Pre-registration before the sweep |
| **9** | **Capture `/series` as a fixture; test `fee_multiplier` against 11 fills** | measurement | possibly 51.75% → 50.88% | 0, S | Predicts all 11 to $0.0001 |
| **10** | **One-tap self-lockout** → 423 until 10:00Z | reuses existing 423 shape | The first way to say "not tonight" | 0, S | Guard verified by disabling |

**Explicitly dropped:** wiring the scout; per-game LLM prose; a divergence leaderboard or any sort control; scheduled props; `us`-only regions (would delete the sharp anchor — Pinnacle is `eu`-only); a fair-value overlay on the chart; any running P&L or percentage of his money.

## Debates I resolved

**Break-even vs β.** Sharp-bettor wanted break-even *and* fair value on the row. Adjudicated and refused, on an exact identity: `edge_tenths == 1000 * (fair_probability - breakeven_win_rate(ask, contracts))`. They are the minuend and subtrahend of the measured-negative quantity; adjacency hands Joe `edge_tenths` by subtraction to the last decimal. **Break-even ships alone.**

**Silence vs display.** Tilt-prone argued P&L is the chase trigger; retail argued silence is why he lost. Resolved on form: the display exists, shows **cash and open exposure separately, never summed**, denominated on the $10 line Joe himself set — not the $100 study ceiling, which reads as 88% of budget remaining to a man holding $8.31.

**The study.** Keep it running, but it is **VALID-BUT-IMPAIRED** and its likely verdict is `INSUFFICIENT`, not contaminated — 4 settled positions in the observable window matched zero estimates. Fix the matcher, register coverage, declare the Board as an already-live undeclared anchoring channel via an A9 that **records rather than permits**, and set a **30-day feasibility checkpoint with thresholds picked now**. I am naming my own interest: a contaminated study frees the product, and I am the one asking. That goes in the amendment.

## Dissents worth preserving

- **Tilt-prone still refuses per-game prose outright**, and would rank a badly-framed money display as *more* harmful than silence. It is right that the form carries the whole risk.
- **Measurement-skeptic holds that even the on-open panel inherits Joe's unrecorded selection N** — he performed the argmax, we stopped instrumenting it. Mitigation: log the open regardless of what renders.
- **The `fee_multiplier` finding rests on one uncommitted live read** — it appears in zero fixtures and zero backend files. It is good news, so it gets more scrutiny, not less. Item 9 is a verification, not a fact.
- **"Fee as a share of winnings climbs toward both extremes" is false.** It is exactly `0.07 × price`, monotone increasing. The 12% figure was round-trip against a 6% settlement figure. The corrected line — **"the fee is 7% of the price, as a share of what you stand to win"** — is exact and is the best teaching sentence in this review.

## First vertical slice next session

**Item 1, plus items 2 and 3 behind it.** Fix the matcher that is stamping "he did not bet" on bets Joe made, run the repair pass, and reconcile the count against `fills WHERE source='venue_hand'`. Then caption the guard that lies, and make `/slate` the landing screen with plain-word nav.

That is one commit of data integrity and one of "Joe finally lands on the screen he asked for five months of sessions ago" — demoable on his phone, zero credits, zero risk to the order path, and nothing touching the scheduler under measurement today.
