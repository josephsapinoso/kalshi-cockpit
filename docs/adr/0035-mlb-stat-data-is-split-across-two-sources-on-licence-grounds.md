# ADR 0035 — MLB stat data is split across two sources, on licence grounds

**Date:** 2026-08-16
**Status:** Accepted
**Supersedes:** nothing. First decision about a non-Kalshi, non-Odds-API source.

## I am not a lawyer and this is not legal advice

This ADR is **risk-reduction engineering**. It records what the terms say
verbatim, which uses collide with them, and an architecture that avoids the
collisions. It does not decide whether any particular use is lawful, and no
sentence here should be quoted as if it did.

**If this project ever runs materially more than $100, manages anyone else's
money, or sells a signal, stop and pay a lawyer for thirty minutes.** That is
cheap relative to the exposure, and the answer would replace this file.

## Context

The next build needs MLB statistics: expected plate appearances by lineup slot,
per-PA and per-batter-faced rates, today's confirmed lineup, and today's probable
starter. Nothing in this repo has ever read a baseball statistics source —
verified: no `statsapi`, `baseballsavant`, `pybaseball`, `retrosheet` or
`fangraphs` reference anywhere in the tree, and no baseball package in
`requirements.txt`.

`statsapi.mlb.com` answers every one of those questions, free, with no API key
and no auth header. It was probed live on 2026-08-16 and works.

**Its terms are the problem.** Fetched verbatim from
`gdx.mlb.com/components/copyright.txt`, which the API's own `copyright` field
points to:

> "Only individual, non-commercial, non-bulk use of the Materials is permitted"

> "any other use of the Materials is prohibited without prior written
> authorization from MLBAM"

> "Authorized users of the Materials are prohibited from using the Materials in
> any commercial manner other than as expressly authorized by MLBAM"

Three facts about this project collide with that language, and they are of very
different sizes.

1. **This repo is intended to go public** (CLAUDE.md). And CLAUDE.md:177 requires
   that *"wire-format tests load captured payloads from `tests/fixtures/`, never
   hand-constructed ones."* Following that convention for MLBAM data would commit
   MLBAM Materials into a public GitHub repository. **That is redistribution, it
   is the clearest collision of the three, and it is entirely avoidable.**
2. **The model would poll.** Every game, on a schedule. "Non-bulk" is undefined
   in the notice and a 5-minute cron across a 15-game slate is at best arguable.
3. **It informs real-money bets.** Whether one person betting $100 of their own
   money is "commercial" is genuinely unclear. What is *not* unclear is the
   direction of travel: MLB granted **Sportradar an eight-year exclusive licence
   as global distributor of MLB betting and media data**, from the 2025 season.
   Using MLBAM's free feed to price bets is squarely the use MLB has licensed
   exclusively to someone else. That does not make it unlawful for an individual;
   it does mean nobody should expect a sympathetic reading.

## Decision

**Split the data by what it actually is, and take each from the source whose
licence permits that use.**

### 1. Everything historical and derived comes from Retrosheet

Retrosheet's terms are explicitly permissive, and unusually so:

> Recipients "are free to make any desired use of the information, including
> (but not limited to) selling it, giving it away, or producing a commercial
> product based upon the data."

One requirement, and it is a notice, not a restriction:

> "The information used here was obtained free of charge from and is copyrighted
> by Retrosheet."

**That notice is mandatory and must appear prominently.** It goes in `README.md`
and in the module docstring of any file that reads Retrosheet-derived data.

This covers the bulk-derivation work, which is the part that most looked like
"bulk use":

- **expected PA by lineup slot** — the 4.641 → 3.737 monotonic table, currently
  derived from 270 team-games of MLBAM boxscores. Re-derive it from Retrosheet.
- **per-PA and per-batter-faced baseline rates**, and the handedness splits.
- **any backfill, any multi-season aggregate, anything resembling a bulk pull.**

Retrosheet is historical — it lags the current season — which is exactly right
for a baseline that should not be refit intraday anyway.

### 2. Only the thin live layer comes from MLBAM, and it stays thin

Two facts per game per day, and nothing else:

- today's **probable starter** (`schedule?hydrate=probablePitcher`)
- today's **confirmed lineup**, if the batter ladders are ever built
  (`schedule?hydrate=lineups`)

Both come from **one call per slate**, not one per game. Constraints that make
"individual, non-commercial, non-bulk" a defensible description rather than a
hope:

- **One request per slate per poll, never per game.** The hydrate form already
  returns the whole day.
- **Poll on a schedule matched to when the data changes, not on a timer.**
  Probable starters resolve 1–3 days out; lineups were measured complete at
  least 3.2h before first pitch and **0 of 30 changed** between posting and
  first pitch. A handful of polls per day covers it. There is no case for 5-minute
  polling and it is forbidden here.
- **Cache to the database and re-read the cache**, never the endpoint.
- **Stop on the first sign of unwelcome.** No published rate limit and no
  `X-RateLimit-*` headers means the ceiling is discovered by being cut off, on a
  Fly IP that is shared and not ours to burn. A 429 or a block is a stop, not a
  backoff-and-retry.

### 3. No MLBAM payload is ever committed to this repository

**This is the hard line, and it is an explicit, narrow exception to
CLAUDE.md:177.** The wire-format-fixture convention exists because
hand-constructed payloads drift from reality, and that reasoning is sound — but
it was written for Kalshi and The Odds API, whose data we are not prohibited from
redistributing.

For MLBAM:

- **no captured payloads in `tests/fixtures/`**, and no capture script that
  writes one.
- tests use **synthetic** payloads whose *shape* is pinned by a schema assertion,
  with a comment naming this ADR so the next reader does not "fix" the
  inconsistency.
- any real capture used while developing lives in the scratchpad and is
  `.gitignore`d.

This costs real fidelity and the cost is accepted. It is the only one of the
three collisions that is unambiguous, and it is the only one a stranger can see
from outside.

### 4. The source sits behind an interface, so the commercial answer is a config change

If this ever goes commercial — someone else's money, a sold signal, a scaled
bankroll — the fix must not be a rewrite. Reading MLB stats goes behind one
module with a narrow interface, so swapping in a licensed provider
(**SportsDataIO**, transparent tiered pricing from ~$25/mo with MLB coverage and
a commercial licence; **Sportradar** for enterprise, contract-priced, no public
rates) is a config change and a new adapter.

**The trigger for that swap is written down here so it is not a judgement call
later:** the first time this project handles money that is not Joe's own, or
distributes a signal to anyone else, the MLBAM path is turned off.

## Consequences

- **The lineup-slot table has to be re-derived from Retrosheet before it is used
  in anything that prices a bet.** The MLBAM-derived version measured on
  2026-08-16 is a scoping probe, not a production input, and must be labelled
  that way where it appears.
- **A Retrosheet ingestion path is now on the critical path** for the batter
  ladders. It is *not* on the critical path for pitcher strikeouts, which needs
  the probable starter (thin live layer) plus a per-batter-faced rate (Retrosheet
  historical, or current-season MLBAM read once per player rather than polled).
- **`README.md` gains the Retrosheet notice** before any Retrosheet-derived
  number is published.
- **CLAUDE.md gains a one-line exception** to the fixture rule, pointing here.
  A convention with a silent exception is a convention that gets "corrected"
  back.
- **The enforcement risk being low is not the reason to do this.** The realistic
  worst case from MLBAM is an IP block or a cease-and-desist, not a courtroom.
  The reason is the portfolio: this repo is meant to be read by people deciding
  whether to work with Joe, and a public repo that visibly redistributes data it
  was told not to redistribute answers a different question than the one it was
  built to answer.

## What this ADR does not establish

- **It does not establish that the thin-live-layer use is permitted.**
  "Individual, non-commercial, non-bulk" is not defined in the notice, and this
  ADR chooses an architecture that makes the description *defensible* rather than
  one that makes it *certain*. Only MLBAM can make it certain, and the notice
  says how: prior written authorization. Asking is free and has not been done.
- **It does not establish that Retrosheet covers everything needed.** Retrosheet
  lags the current season and its coverage of a given field must be checked
  before the batter build depends on it. Unverified as of this ADR.
- **It does not price the Retrosheet ingestion work.** That is a build estimate
  nobody has made.
- **It says nothing about Kalshi's or The Odds API's terms**, which are separate
  agreements and are unexamined here.
