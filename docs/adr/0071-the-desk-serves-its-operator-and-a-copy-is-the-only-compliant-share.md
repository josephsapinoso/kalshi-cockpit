# 0071 — The desk serves its operator, and a copy is the only compliant way to share it

Accepted 2026-08-24. Joe's direction, taken as a structured interview (the
`grilling` skill) rather than a plan review: seventeen questions over five
rounds, every answer his. Two background audits supplied the facts —
a runtime trace of what the deployed system actually spends, and a
primary-source review of odds vendors and platform terms.

This ADR exists because the interview settled the project's **purpose**, and
purpose is the thing every future session re-derives badly. ADR 0038 closed
the hunt but said nothing about what the tool is *for* afterwards. That
question now has an answer.

## 1. What this overturns, and what it does not

**Not overturned: ADR 0038.** The hunt stays closed. Nothing here reopens a
quadrant, and §2.5 below actively *narrows* what the screen may claim.

**Not overturned: the 2026-08-21 strip ruling.** That ruling removed the
edge point estimate — `+X.Xc`, the tone class, the mark — from the landing
slate rows, because the screen was claiming an edge the record does not
support. §2.5 puts two plain prices back on those rows with no sign, no
arrow and no colour. The ruling's substance was that the screen stops
*claiming*; two prices side by side claim nothing unless they are drawn as
a comparison. Joe confirmed this reading explicitly (Q17).

**Corrected: CLAUDE.md's "the recorder keeps running because it costs
nothing."** True of the LLM fleet — the runner imports `review_retired`,
which refuses every row and calls nothing (`backend/agents/review.py:406`).
**False of the odds feed**, which is the thing the recorder was raised to
buy: ~576 credits/day, ~17,300/month against an 18,000 self-cap on a 20,000
paid tier (`fly.live.toml:242-250`). The sentence was written when a sweep
cost 2 credits under `h2h`; `ODDS_MARKETS = "h2h,spreads"` doubled it on
2026-08-23 and the sentence was never revisited.

**Withdrawn: a claim this session made and then refuted.** A subagent
reported `/api/ledger`, `/api/bets` and `/api/results` as unauthenticated on
live, and it was relayed to Joe as a live privacy leak. It is not one. The
agent read the FastAPI layer, found no `require_auth`, and stopped there;
the gate is one layer up. `uvicorn` binds loopback and is never published,
`/api/*` is reachable only through Next's rewrite, and
`frontend/src/middleware.ts` runs *before* rewrites, matching every path but
static build assets. Verified against the deployed instance, not the source:

    /api/health  -> 200
    /api/bets    -> 401
    /api/ledger  -> 401
    /api/results -> 401
    /api/gate    -> 401

The route docstrings (`routes.py:2285-2291`, `:2377-2382`, `:2414-2418`) say
all of this at length. They were not read. See `tasks/lessons.md`.

## 2. The decisions

1. **The tool is a personal betting desk first, a portfolio repo second, and
   a hunting instrument not at all.** Joe bets by hand whether or not the
   cockpit exists — he confirmed this directly, and the record agrees: the
   parlay desk was built *after* a bet he had already decided he wanted.
   The desk's job is therefore to inform and record bets that are happening
   anyway, not to manufacture action and not to abstain on his behalf.
   Portfolio value is a byproduct of writing honestly, not a second design
   target.

2. **The tool's job at the moment of a bet is price transparency.** Of the
   three candidate jobs put to Joe — tell him what he is paying, brake the
   bad bets, or keep a clean record — he chose the first. So: show what
   Kalshi charges and what the sharp consensus says it is worth. Do not
   nag, and do not editorialise. The clean record (2) follows as a
   byproduct; braking (3) is reserved for the case where a screen would
   otherwise state something false, which is a correctness duty and not a
   product stance.

3. **Sharing means a copy, not a visit — and the reason is legal, not
   technical.** Kalshi's Developer Agreement §3 limits API use to
   "facilitating a member's own trading"; §3.1 forbids "collecting,
   caching, aggregating, or storing data" for other purposes and states
   plainly: *"You may not share such data or content with third parties in
   any manner without prior written authorization from Kalshi."* §3.7
   forbids sublicensing. A hosted instance showing friends Kalshi-derived
   screens is therefore non-compliant absent written permission; a friend
   running their own copy on their own key is the permitted case, because
   it *is* their own trading. Joe chose the copy shape before this finding
   arrived; the finding ratifies it.

   **This is why the recommendation given to him mid-session — host it and
   gate the LLM button — was wrong, and it is recorded rather than quietly
   dropped.** The cost reasoning behind it was sound (viewers spend nothing;
   see §3) and led to the wrong answer anyway, because the binding
   constraint was never cost.

4. **Making the repo runnable by a stranger stays aspiration, with one
   exception taken now.** The tax is paid up front for a cloner who may
   never exist, so no config generalisation, no setup-doc program, no
   second-operator abstractions. The exception: **Kalshi's read endpoints
   are free and public** — `/markets`, `/events`, `/markets/{t}/orderbook`
   all answer 200 unauthenticated, a fact this repo measured by hand on
   2026-08-09 and recorded at `backend/kalshi/rest.py:405-408` — and
   `KalshiRestClient.request` signs them anyway (`rest.py:218-227`). A
   client that falls back to unauthenticated reads when no key is
   configured removes the single largest barrier to someone running this,
   for the least work. Keep the key when present: rate limits are keyed per
   account, so a signed read is still the better read.

   **Shipped 2026-08-24 as `KALSHI_PUBLIC_READ_ONLY`, and it is an opt-in
   rather than the fallback this paragraph first described.** The wording
   above says "when no key is configured", which would make a missing
   credential degrade silently — and on the live instance that is the worse
   failure, not the safer one: the runner would look healthy while writing no
   portfolio, no fills and no settlements, which is exactly what
   `docker/entrypoint.sh:110-116` refuses to start into. So the flag must be
   set deliberately; unset, a missing key raises as it always has.

   Three properties, each mutation-verified red:

   - The boundary is an **allowlist** (`PUBLIC_READ_PREFIXES = ("/markets",
     "/events")` in `backend/kalshi/rest.py`), so a Kalshi endpoint this repo
     has never measured defaults to *refused* rather than reachable.
   - It is checked on **method and path together** — a POST to `/markets` is
     not a market-data read — and on a word boundary, so `/markets` cannot
     admit a future `/marketsecret`.
   - It refuses **before the transport**, outside the retry loop, so a missing
     credential is one clear `KalshiCredentialsRequired` rather than four
     retries with backoff ending in a 401 that reads like a broken key.

   The WebSocket refuses at construction instead: Kalshi authenticates
   `/trade-api/ws/v2` at the handshake, so unlike REST it has no public half.

   Premise re-verified against the live venue on the day of the change, not
   inherited from the 2026-08-09 measurement: `/markets`, `/events` and
   `/markets/{ticker}/orderbook` answered 200 with no headers,
   `/portfolio/balance` answered 401. That re-check was not ceremony — ADR
   0012's pinned combo endpoint had gone dead by 2026-08-23, so a Kalshi path
   measured once is not a Kalshi path measured.

   **Not done, and deliberately:** nothing wires this into `docker/entrypoint.sh`
   or the runner's startup, so setting the flag today gets you a client that
   can read, not an instance that boots keyless end to end. That is the next
   slice, and it is the one that needs the entrypoint's refusal rewritten
   rather than bypassed.

5. **The consensus-vs-Kalshi gap is displayed per row and never ranked
   by.** Joe asked for the "Likely winners" block to be re-sorted by that
   gap, and the recommendation was withdrawn on the measurement: `beta =
   -0.141` (ADR 0021, 0034) means the gap has *negative* pass-through to
   Kalshi's own close. Ranking by it would put the least trustworthy rows
   at the top of the screen — an opinion about which row matters most,
   from a project that measured it has none to offer. A per-row fact is
   transparency; an ordering is a claim. So: both prices on the row,
   ordering unchanged.

   **Shipped 2026-08-24, and it cost `breakeven_win_rate` its place on the
   row — which was not foreseen when Joe approved it.** The two cannot share
   a row: `edge_tenths` is exactly `1000 × (fair − breakeven)`, an identity
   proven against live payloads by `tests/test_api.py:1264-1310`, so fair
   beside break-even hands back by subtraction precisely the number the
   2026-08-21 ruling deleted. Put to Joe as a swap and approved 2026-08-24.

   Break-even lost, on the merits rather than by elimination: it is the ask
   with the fee added, not a third fact, while fair is the only one of the
   three the row did not already carry. The 2026-08-20 convening's own
   reasoning permits this — item 6 argued the row needs a number that makes
   the price a decision, not that the number must be break-even. Precedent
   was already shipped in the same direction: `ConsensusPanel.tsx` renders
   fair% and is *forbidden* break-even (`tests/test_desk_panels.py:94`).

   `TestBreakevenShipsAloneOnTheScreen` became
   `TestFairAndBreakevenNeverShareTheRow`: same property, inverted direction,
   dated docstring, mutation-verified red by restoring the break-even span.
   **`breakeven_win_rate` left the component, not the wire** —
   `test_api.py::TestBreakevenShipsAlone` still requires it on every priced
   row of the payload.

   Three things the swap forced, each worth its own line:

   - **The row's units stay unlike on purpose.** Ask through `format_price`
     (`34.2c`), fair through `format_probability` (`60.2%`).
     `core/prices.py:130-143` records why: a fair value rendered as `53.8c`
     beside a real ask at the same type size is "the one place a
     left-to-right scan reads the wrong number as the thing you pay".
   - **A latent bug went with it.** The break-even span was conditional, so a
     row with no tradeable price dropped a grid child and shifted every
     column from `Books` rightward one track left at xl. The fair cell is
     unconditional and pinned as such; the failure was silent and visible
     only as a misaligned desktop row. The swap also removed this row's one
     piece of client-side arithmetic on a probability.
   - **The screen had to say the gap is not profit.** Two numbers side by
     side invite a subtraction, and the remainder is not money: a fee sits
     between them, and this project measured the remainder and it did not
     pay. A footer paragraph says both, in prose, with no per-row figure —
     and it is where `Term k="breakeven"` now lives, the slate row having
     been its only renderer. This is the narrow case ADR 0071 section 2.2
     reserves for braking: not nagging, but refusing to let the screen imply
     something false.

6. **The odds feed follows attention, not the clock.** The 12-hour
   `ODDS_DESK_WINDOW_UTC` sweeps every 10 minutes whether or not anyone
   has opened the site, which is where ~576 credits/day goes. Replaced by
   a frontend heartbeat — sweep while a page is open — over a slow hourly
   floor, so a cold open is stale by minutes rather than half a day. The
   existing `RefreshOddsButton` stays as the instant override. Joe chose
   this over a narrower fixed window and over a manual wake button.

7. **The scout desk moves off Opus.** `AGENT_MODEL` is unset in
   `fly.live.toml`, so the desk has been running `claude-opus-5` by
   default — four metered calls plus web search per convening. Its work is
   synthesis of documents it has just fetched, which is the shape where a
   cheaper model gives up least. Caps unchanged. If one seat proves to
   need the horsepower, promote that seat, not the desk.

   Recorded alongside: **the search cap binds before the call cap.** A
   convening reserves `STAFF_PAIR_SEARCHES_WORST_CASE = 12`
   (`scout_desk.py:70`), so 60 searches/day allows 5 convenings while 24
   calls/day allows 6. `fly.live.toml:289`'s comment treats the call cap as
   "the money control"; it is not the binding one.

   **The switch turns prompt caching off, knowingly.** Found while making the
   change, not before it: the minimum cacheable prefix is model-specific and
   not monotonic across releases — **512 tokens on Claude Opus 5, 1024 on
   Sonnet 5** (`scripts/measure_agent_cache_prefix.py:47-50`) — while this
   repo's cache breakpoint sits on a prefix measured at **738–985 tokens**
   (`agents/base.py`, above `HOUSE_CONTEXT`, 2026-08-08). Every one of those
   clears 512 and none clears 1024, so `cache_creation_input_tokens` and
   `cache_read_input_tokens` are now 0 on every live call — silently, which
   the module already warns is the only way a cache fails.

   Taken anyway, and the arithmetic is why: a Sonnet call uncached is cheaper
   than an Opus call cached, and `structured_call`'s own docstring already
   priced the caching at "a fraction of a cent a call against a ~$0.084
   ceiling", recovered *across* passes rather than within one and usually
   missing the 5-minute ephemeral TTL at `RUNNER_INTERVAL_S = 900`. Padding a
   system prompt past 1024 tokens to win that back would cost more in input
   tokens than it saves. **Do not treat the zeroes as a defect.**

   **Not measured, and it is free to measure:** the 2026-08-08 prefix table
   covers skeptic, scout and historian. The four seats that actually spend
   money today (`agents/scout_desk.py`, `agents/pro_bettor.py`) have never had
   their prefixes counted, so whether any clears 1024 is unknown.
   `count_tokens` is not billed.

8. **The fair-value parlay payout keeps its number and loses its
   authority.** `_at_stake_fair` (`backend/parlays.py:326`) computes
   contracts and payout from fair probability alone, with no depth cap,
   because no Kalshi book has been consulted when the card renders. That is
   honest — nothing has been quoted — but it is the larger number and it
   arrives first, so a reader trusts it over the depth-capped figure that
   replaces it after "Price on Kalshi". The two are restyled so an estimate
   cannot be mistaken for a price. The number itself stays: removing it
   would leave the card unable to say what a stake buys.

   **Shipped 2026-08-24.** The estimate lost its bold (the default stake row
   was `font-semibold` — the largest, least-supported figure on the card was
   also the heaviest), went italic and muted behind an inset rule, and its
   heading now reads *"If it priced at fair value — an estimate, not a
   quote"* rather than *"At fair value, a stake would buy"*, which was true
   and read as a price to anyone who did not already know what fair value
   means. The quoted line in `PriceOnKalshi` gained the bold the estimate
   gave up, so the change cannot be half-applied: `tests/
   test_parlay_estimate_is_not_a_price.py` asserts across both components and
   is red if either moves alone.

   A caption names *why* the quote will be smaller — it is capped by resting
   depth and the estimate is not. Without the reason, a reader who taps and
   sees a smaller number concludes the tool was wrong, rather than that the
   venue's book is thin. Five guards mutation-verified red.

   **The section heading kept its `font-semibold`, and the first version of
   the test wrongly failed it.** An 11px uppercase label is not a number, and
   emphasising a label lends no authority to the figures under it. The
   assertion was narrowed to the `<ul>` of stake rows — recorded because a
   guard scoped one element too wide would have forced a cosmetic edit to
   satisfy a claim it was not making.

## 3. What the audits established, and what they did not

**Viewers cost nothing.** Every third-party fetch happens in the background
runner; the API process opens the database read-only and holds no odds
client; the frontend never calls a vendor directly. The one human-triggered
spend, `POST /api/odds/refresh`, sits behind auth *and* a credit ceiling.
Joe's stated constraint — that sharing must not spend his quota — was never
at risk from viewers, and the decision in §2.3 rests on licensing alone.

**The vendor is right and cheap.** The Odds API's free 500-credit tier
includes Pinnacle, Betfair Exchange and Matchbook — the exact three books
`runner.py:150` devigs from — while excluding DraftKings and FanDuel; the
paid 20K tier is $30/month. Their terms permit display inside user-facing
applications and forbid only re-serving raw data as a data product. No
alternative pairs those three books with comparable terms: Pinnacle closed
direct public API access on 2025-07-23, so every route to them is now a
reseller.

**Not established: what any of this actually costs in dollars.**
`fly.live.toml:278-283` flags the Anthropic rate as `[ASSUMED, uncited]`,
and the invoice numbers are a closed question (2026-08-22, ADR 0062 §4 —
Joe declined; do not reopen). The reliable quantities are counts, not bills.

**Not established: whether the scout desk has ever been convened on live**,
and so whether any Anthropic money has been spent at all. `scout_briefings`
on the deployed volume answers it; the local database is not that record.

**Not established: whether `ODDS_DAILY_CREDIT_BUDGET = 700` has ever
bound.** The ~576/day figure is the design arithmetic, not a measurement.
`api_credits` summed per budget-day on the live volume is the instrument,
and §2.6 should be measured against it after deploy rather than assumed to
have saved what it was built to save.

## 4. Stale numbers found while establishing the above

Four sites carry figures that were true before 2026-08-23 changed
`ODDS_MARKETS` to `h2h,spreads`, doubling a sweep from 2 credits to 4:

- `backend/live.py:28-36` — states `h2h`, "a sweep costs 2", 600/day,
  13,000/month. Four wrong numbers in the file whose stated purpose is
  carrying sourced numbers.
- `.env.example:68` — "the live instance is at 600/day and 13,000/month".
- `backend/odds/ondemand.py:81` and `fly.live.toml:382` — price a prop tap
  at 26 credits (6 + 20 under the retired three-market config); it computes
  to 4 + 20 = 24 today.

These are corrections, not decisions, and are made without further ruling.
