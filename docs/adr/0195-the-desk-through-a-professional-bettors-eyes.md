# 0195 — The desk through a professional bettor's eyes: what a pro keeps, what goes, and what the spend was

Accepted 2026-10-10. Joe's ask, verbatim (2026-10-09): *"Now imagine you are
famous better Billy Walters. Evaluate the site through his eyes and critique
the platform. He knows his stuff really well and is a wildly successful
bettor. Improve the site based on the recommendations and take away the
useless stuff."* Three contested calls were put to him with option buttons
the same day and he answered all three with the recommended option
(#349 A, #350 A, #351 A). This ADR records the review, the decisions, and
the one measurement that carried them.

## 1. How the review was done, and what it is not

The repo's `sharp-bettor` agent reviewed **real rendered screens**, not the
JSX: `scripts/check_mobile.py --shots` captured every served page of the
public demo instance (build `0fe9e677`, a few commits behind main) at 390
and 1440 px through headless Chrome, and the reviewer read the PNGs. It
reviewed through the lens of Billy Walters's *publicly documented* approach
— his 2023 memoir and public interviews, as summarised in secondary sources
it cites — and it does **not** speak as him or put words in his mouth
(`.claude/agents/sharp-bettor.md`'s rule). What the public record supports
and the review leaned on: bet the number, not the team; line shopping and
the best price; key numbers in football (3 and 7); sizing in units of 1–3%
of bankroll; a dim view of parlays and of touts; discipline about chasing.
Closing line value as the scoreboard is general professional practice; the
review could not source it to Walters personally and says so.

The `partner` then ranked the critique, ran one cheap bounded live read
(`inspect_live_db.py agent-spend --days 14`), argued back where the critique
overreached, and returned the dispatch table the build followed. Main
verified every defect claim against `de880d1c` before anything was asked of
Joe. The `measurement-skeptic` audited the spend aggregation before a number
entered this file or `CLAUDE.md` (§3).

## 2. What a professional sees, and what was decided

**Keep (earns its place).** Ask in cents, quote age and depth at the ask on
every row; fair value as a devigged percentage, worst of four methods; the
line-shop hint (YES here vs NO there — the review called it "the most
professional feature on the desk"); the ticket's live re-read and the
server-side staleness refusal; Check a parlay; the RFQ ask/take and the
sell-side RFQ exit; Your bets' expected-vs-actual, net, W/L, the money chart
and the pick-source tags; the exposure line; the Playbook's pre-bet steps;
the gate interlock in code.

**Defects, verified on main, fixed as free lanes (#341, #343, #344).**

- The one panel that teaches what the vig is showed it wrong on every market
  page: `core/devig.overround()` returns `sum − 1` (the margin) and that is
  what `fair_prices.overround` stores, while `FairValueSteps.tsx` rendered it
  as the sum — "their chances come to 3.3% — not 100%", a house cut of "−96.7
  points". `schema.sql` documented the column as the sum, and
  `tests/test_fair_value_steps.py` pinned the wrong arithmetic as source
  text, which is why it was green. Display fixed, storage untouched, comment
  corrected (#341).
- The skeptic panel on `/market` printed the engine's `reason_text` —
  "(+1.7c after fees). Sized at 1." — the edge-and-size language ADR 0071
  §2.5 took off the row, on the betting screen (#341).
- Stale copy: Picks said "not ranked" on a kickoff-ordered list (#235 A);
  the Playbook drill told Joe to "log the estimate anyway" after the log was
  retired (ADR 0094/0131); the Games server note ended "and combined into
  nothing"; Your bets' "Record it below" linked the top of the page (#343,
  #344, main).
- A Games row said a price was stale three times, and on a phone the first
  row sat ~2.5 screens down behind explanatory prose (#344).

**Deleted — Joe's (A) to #351.** `/board` (Refusals), `/ledger` (Evidence),
`/estimate` (Estimates) and `/dashboards`, with the components only they
imported and their footer entries (#342). The review's phrase was "a museum
of a strategy that will never trade": Refusals drew the engine's edge in
green over a stream that carries nothing on live by construction; Evidence
is the engine's record at "0 / 300"; Estimates records a study stopped
2026-08-20 and its copy contradicted ADR 0131; Dashboards returned 503 on
live. Gate and Playbook stay in the footer. **The gate interlock, `POST
/api/orders` and the bid path are untouched**; the dead backend routes are
#347, main-owned, deferred. This amends ADR 0098 and #8 (the record of that
is in ADR 0098's amendment).

**Automatic game-script cards off, cards on tap only, token ceiling 9M →
2.5M — Joe's (A) to #349.** ADR 0190 Amendment 2 carries the reading and
the changes. The review's reading of a T-24h card: the slowest information a
bettor can buy, before MLB lineups and most NFL injury designations, in the
shape of a tout's card.

**Parlay pushes off, ladder view kept — Joe's (A) to #350.** A new
`PARLAY_PUSHES_ENABLED` read (`backend/config.py`, `.env.example`,
`"false"` in `fly.live.toml`) is handed to the main `Alerter`, whose
`parlay_cards_could_send` and `parlay_cards` both read it, so the runner
skips the ladder build the push needed as well as the send
(`tests/test_parlay_pushes_have_a_switch.py`, both guards mutation-verified
red). ADR 0076's amendment records it. Ground: ADR 0071 §2.1, the desk does
not manufacture action.

**Leg verdicts show their own take rate (#345).** A base rate, not an
accuracy figure (#320 forbids the latter): verdicts said "take" on 153 of
179 decided in the window, arriving in bursts of about 29 taps.

**Refused or deferred, with the reason — so the scope narrowing is explicit.**
Merging Picks into Games (overturns ADR 0100/#235 A for layout churn); an
`/ops` page (a shuffle); stake as % of balance on the ticket (he tops up a
shard per bet, so the ratio is meaningless, and it edges toward the brakes
ADR 0112 removed); a dollar spend line on screen (the rate is uncited and
Joe declined invoice figures, ADR 0062 §4; tokens reached him in #349);
per-leg CLV on combo legs (after #331's census says the data exists in
useful numbers); the key-number flag (#348, unscheduled: one new feature at
a time, after the cuts); cutting the scout desk or renaming the "Willy"
seat (#209 A stands, the seat recorded ~0 spend in 14 days, and Joe named it,
ADR 0069); the backend no-op sweep (#347: zero spend, nothing Joe sees,
~20 registry pins red per removal).

**Where Joe's settled choices diverge from a professional's, and stay his:**
parlays as the main product; no sizing rule; no stop rule (#239 C). The
review's drills work around them, and they are in the write-up, not here.

## 3. The measurement

`inspect_live_db.py agent-spend --days 14`, run on the live box 2026-10-09
~20:00Z, budget days from 2026-09-26T10:00Z; the partner's aggregation
audited row by row by `measurement-skeptic` (453 rows, ids 118–570, no gaps).
"Tokens" is input + output as recorded; **every figure is a floor** because
92 of 453 calls carry NULL usage (81 inside the 2026-10-05 credit outage) and
a budget refusal never reaches `agent_calls` at all.

| | calls | tokens recorded | share |
|---|---|---|---|
| game_script + recheck | 244 (75 unmetered) | 29,245,494 | 74.1% |
| leg_verdict | 199 (10 unmetered) | 10,118,514 | 25.6% |
| scout desk + pro seat | 10 (7 unmetered) | 110,780 | 0.3% |
| **all** | **453** | **39,474,788** | |

Per day since cards began, ten complete budget days 20260929–20261008:
mean 3.35M, median 2.56M, range 1.51M–7.20M; one day (20261004, the only
Sunday) is 21.5% of it. The three no-card days before (0926–0928) averaged
1.01M. A built card (n = 105): median 178K, mean 200K, sd 139K, range
40K–817K; by day the mean runs 74K–505K, and the Sunday carries 26% of
built-card tokens with 10% of the cards. Outcomes of the 229 card calls:
built 105, filed_nothing 80 (75 of them the unmetered outage retry loop),
skip 30 (mean 170K — the model's own decline, a finished status, not a
failure), search_failed 11, invalid 3. Excluding the outage day: 100 built
of 154. Leg verdicts (n = 189 metered): mean 53.5K; take 153, pass 26,
over_length 10, filed_nothing 10; busiest day 1.21M (2026-09-30).

**What the window does not contain:** no calls before 2026-09-26T10:00Z;
no cards before budget day 20260929; nothing after ~20:00Z on 10-09; no
budget refusals; no sport, game or tap-vs-watcher column, so "NFL Sunday"
cannot be read from it; no dollars. The wording Joe was asked with ("about
half the card calls build nothing") overstated the failure share; the
correction is on #349 and he was invited to change his answer there.

**Side finding, recorded on #338:** on 20261004 the day passed the 4.5M
unattended line at call 333 and six card calls followed; `CARD_TOKEN_ESTIMATE`
reserves 290K while that day's calls averaged 448K. Moot while the watcher
is off; relevant the day it returns.

## 4. What this does not change

ADR 0071 (purpose; never rank by the gap); ADR 0038 (the hunt is closed);
ADR 0189/#200 (sports factors lead a parlay build); ADR 0112/#239 C (no
brakes, no stop rule); ADR 0100 (the nav); ADR 0115/0127 (the bid path kept
disarmed); the gate (never lowered or bypassed — deleting its *record
screens* is not touching the interlock, and `/gate` stays). The on-tap paths
that spend — "Build card", leg verdicts, "Send the scouts" — are untouched:
a spend Joe taps for is his.
