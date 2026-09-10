# Disclosed unregistered look — two reads of the registered shard-1 population on 2026-09-10, three days before the run

**Written 2026-09-10, the day the looks happened, before the registered run
fires on 2026-09-13.** This document exists because two sets of observations
were taken today against the population registered as Arm D of
`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md`
(`KXMVECROSSCATEGORY-SHARD1`), neither of them under that registration, and
**one of them touches the registered primary quantity in the falsifying
direction.**

They cannot be unseen. The only remaining choice is whether they are written
down before Sunday or discovered afterwards, and the second option is the one
that produces a dishonest result document.

**This document changes nothing in the registration.** The registration is not
edited; §11 below states, field by field, what stays fixed. This is a
disclosure and a costing, not an amendment. It is deliberately **not** an ADR
and takes no ADR ordinal.

**No live read was taken to write this, and none was taken to correct it.**
Every figure here is reported from the two looks as they were relayed to the
registrar.

> ### CORRECTION BLOCK — 2026-09-10, same day, after the missing fields were recovered from the observing agent's transcript by recall, with no re-observation
>
> Four things moved. Three of them move **toward** a tidier story, so they are
> flagged here rather than edited in silently:
>
> 1. **The three `TO BE FILLED` fields are filled** (§2.2). Both tickers are
>    literally `KXMVECROSSCATEGORY-SHARD1-*`; **§7.1's "the answer is known"
>    stands and needs no in-place correction.**
> 2. **"Still present on a re-read nine minutes later" was wrong** and it was
>    the registrar's own paraphrase of the brief. There was no nine-minute
>    re-read. Nine minutes is elapsed time **from mint**. The one true re-read
>    interval is **5m00s**, on one of the two books. Corrected in §2.2. *This
>    weakens the persistence evidence and is recorded for that reason.*
> 3. **Look 1 created nothing.** It was unauthenticated `GET` only — no
>    `lookup_combo`, no `multivariate_event_collections` POST, no credential in
>    the process. §7.2's write-contamination finding therefore applies **only**
>    to this session's own taps, not to the falsifying look. *This materially
>    reduces the charge against Look 1 and is flagged as such.*
> 4. **The tap count went the other way: 6 → 12** (rows 47–58; rows 53–58 were
>    taken after the first draft of this document existed, all `book_empty`).
>    §8.3's dual-reporting instruction is **re-keyed away from row numbers** so
>    it cannot go stale a third time.
>
> One thing was **added**, not corrected: §2.4, an observation that both
> quoted books were **two-sided within minutes of being minted** — which bears
> on a claim outside this registration entirely.
>
> ### SECOND CORRECTION BLOCK — 2026-09-10, later the same day
>
> 5. **§2.4's open minter field is CLOSED, NEGATIVE.** Neither quoted book was
>    desk-minted (§2.2.1, three independent lines, no wire read). Consequences
>    applied where the conditionals were already written: the `book_empty`
>    screen copy is **not** at risk and ADR 0138 stands (§8.1); the
>    self-minting confound **survives intact** (§8.5).
> 6. **A step further was proposed and is REFUSED.** The suggestion that two
>    quoted non-desk books are *weak positive evidence for* the self-minting
>    story overreaches: the likelihood ratio is ≈ 1.004 (§8.5). It is recorded
>    as **no evidence**, not as weak directional evidence. The refusal runs
>    against the tidier story and against the desk's existing belief, which is
>    why it is flagged here rather than buried in §8.

---

## 0. Summary, stated before the detail so it cannot be buried

| | |
|---|---|
| **What was looked at** | `KXMVECROSSCATEGORY-SHARD1` combination order books — the literal series Amendment 2 §12.1 fixes as Arm D's entire population |
| **When** | 2026-09-10. Look 1: reads from ~13:45Z to 13:52:43.615032Z. Look 2: twelve taps, 13:47Z onward |
| **Registered run** | 2026-09-13, five slots, C1 15:30Z through C5 2026-09-14 00:45Z |
| **Registered primary quantity touched** | **Yes, by both looks.** Presence of at least one level on `yes_dollars` |
| **Falsifying observation seen early** | **Yes — Look 1.** Two shard-1 books, each with one resting YES level and one resting NO level, sizes 10.00, spreads ~4c and ~4.1c |
| **Series confirmed** | **Yes, twice over** — ticker text and the `series_ticker=` query parameter |
| **The one inferential test in the registration (Arm A S2 Fisher, α = 0.01)** | **Untouched.** Its population is the two non-shard series; neither look read them |
| **Alpha, population, stopping rule, decision rule for 2026-09-13** | **UNCHANGED.** Quoted verbatim in §11 |
| **Is the Sunday primary compromised?** | **Not statistically. Materially, yes, in two named ways** — the answer is known in advance (§7.1) and the sampling frame has been altered by this desk's own writes (§7.2, and it is Look 2's writes, not Look 1's) |
| **`EXIT_PRACTICAL`** | **Met as an observation, exactly at the registered boundary** (§2.3.1). It does **not** fire the registered consequence, and §2.3.1 says why |
| **Corrections owed** | Four, all concrete, in §8. None is an alpha adjustment, and §8.4 says why an alpha adjustment would be theatre |
| **The §2.4 minter field** | **RESOLVED NEGATIVE, same day, from the record only** — neither quoted book was desk-minted (§2.2.1). The self-minting confound therefore **survives intact**, and the step beyond that **overreaches** (§8.5) |

---

## 1. The exact registered predicate each look touches

Quoted from the registration so that "touches the registration" is not a
judgement call:

> §1: *"the rate of eligible combination books with at least one level on
> `yes_dollars` is greater than zero."* Comparison baseline 0 of 40.

> §1: *"A single resting YES bid for one contract falsifies the universal
> claim while leaving the operational one standing."*

> §2 / §11.2, eligibility, unmodified: a `/markets` row with **non-empty
> `mve_selected_legs`** and a **readable `yes_ask`** by `readable_quote`
> (`0 < ask < 1`). *"A `0.0000` ask is not an ask."*

> §12.1: *"Arm D's population is the literal ticker
> `KXMVECROSSCATEGORY-SHARD1`, and nothing else."*

> §4: `EXIT_ANY` = ≥ 1 level on `yes_dollars`, any size, any price.
> `EXIT_PRACTICAL` = ≥ 10 contracts resting on YES at a single price on a
> single book. `EXIT_AT_CEILING` = ≥ 250.

The dependent variable of the registered primary is **presence of a level on
`yes_dollars` for a shard-1 combination book**. Both looks read shard-1
combination books and both produced a value of that variable. There is no
reading under which this is outside the registration's subject matter.

---

## 2. Look 1 — the falsifying one, and it was not this session's to take

### 2.1 What was done, and why

A `kalshi-platform` subagent was dispatched on 2026-09-10 to answer a
**product** question, unrelated to this registration: *when does a freshly
minted combination book acquire its first resting NO bid?* That question is
about entry and about latency after minting. Answering it required reading
live shard-1 order books.

**The route was not the registered instrument.** It was not
`scripts/measure_combo_book_presence.py`, it did not apply §2's eligibility
predicate, it did not run at a registered slot, and it produced no
`--json`/stdout artifact pair of the shape §7 requires.

**The route, now recorded exactly** (this was an open field in the first draft
and it matters, so it is stated in full):

    GET /trade-api/v2/markets?series_ticker=...&status=open&limit=1000  (with cursor)
    GET /markets/{ticker}
    GET /markets/{ticker}/orderbook?depth=5

issued via `urllib.request` with only an `Accept` header. **No credential was
loaded into the process. No `multivariate_event_collections` POST. No
`lookup_combo`. No desk route. Look 1 created nothing, modified nothing, and
added no market to Arm D's sampling frame.**

**The intent was not to peek.** Nothing here alleges otherwise, and the motive
does not change the accounting: an observation of the registered dependent
variable, taken outside the registration, three days before the run, is a look
whatever it was looking for. The registrar's rule is that intent is not a
defence, because intent is exactly what cannot be checked afterwards. What
*does* change the accounting is the write question, and on that Look 1 is
clean.

### 2.2 What was seen — the fields, filled

**The two tickers, verbatim:**

    KXMVECROSSCATEGORY-SHARD1-S202662C6B3CFEC6-5D18E47B21C
    KXMVECROSSCATEGORY-SHARD1-S2026D379AC93CBF-7772CD6AC5F

Both are literally prefixed `KXMVECROSSCATEGORY-SHARD1-`; neither is on the
unsharded `KXMVECROSSCATEGORY` nor on `KXMVESPORTSMULTIGAMEEXTENDED`. The
series is fixed twice over — by the ticker text **and** by the
`series_ticker=KXMVECROSSCATEGORY-SHARD1` query parameter used to find them.
**These are observations of Arm D's registered population.**

**The levels, verbatim from the payload, both books at the same read,
2026-09-10T13:52:43.615032Z, `depth=5` requested:**

    ...5D18E47B21C   yes_dollars [['0.0980', '10.00']]   no_dollars [['0.8610', '10.00']]
    ...7772CD6AC5F   yes_dollars [['0.0570', '10.00']]   no_dollars [['0.9020', '10.00']]

One level per side on each book. `depth=5` was requested and one level
returned, so **the single-level shape is complete within the requested depth,
not a truncation artefact.**

**Timestamps** (venue `created_time` for the mints; observation clock
otherwise):

| event | book `...5D18E47B21C` | book `...7772CD6AC5F` |
|---|---|---|
| `created_time` (venue clock) | 13:43:30.222636Z | 13:45:34.187576Z |
| first read | **NOT RECORDED**, bounded to 13:45:17.900202Z–13:46:39.391076Z | 13:46:39.391076Z |
| re-read | none recorded | 13:51:39.391935Z (**5m00s** interval) |
| exact-levels read | 13:52:43.615032Z | 13:52:43.615032Z |

**Correction to the first draft, in the direction that weakens the finding.**
The first draft said *"still present on a re-read approximately nine minutes
later"*. That was the registrar's paraphrase and it was wrong. **There was no
nine-minute re-read.** Nine minutes is elapsed time **from mint** to the
13:52:43Z read. The only true re-read interval in the record is **5m00s, on
one book**. The persistence evidence is therefore: one book quoted at three
separate reads spanning 6m04s, one book quoted at two reads spanning at most
7m26s. That is still persistence; it is less persistence than the first draft
claimed.

**Clustering.** `G_eff = 2`, not 1. `...5D18E47B21C`'s legs verbatim:
`['KXEPLGAME-26SEP13MUNMCI-MUN', 'KXNFLGAME-26SEP13BALIND-IND']` (2 legs).
`...7772CD6AC5F`'s leg **membership is not recorded**; only its leg date set,
`('26SEP11',)`. They differ on three recorded axes — different market tickers,
different collection-hash segment (`S202662C6B3CFEC6` vs `S2026D379AC93CBF`),
disjoint leg date sets (26SEP13 vs 26SEP11) — so under §3's cluster key the
leg sets **cannot** be identical, though the second's membership is unknown.
`G_eff = 2` is therefore established; the second cluster's identity is not.

**Still open, and one field now closed:**

| field | status |
|---|---|
| exact `yes_dollars` prices/sizes at the **earlier** reads | **Unrecoverable.** The earlier observations recorded only the YES level *count* (`yes 1`) and the top NO level. So "10.00 at 0.0980" is a fact about **13:52:43Z only**, and no claim about size at 13:46Z is licensed |
| whether either book was **eligible** under §2 (readable `yes_ask` on the list row) | **Not directly recorded**, but a resting NO bid at 0.8610 / 0.9020 derives a `yes_ask` of 0.1390 / 0.0980 by `1 − best_no_bid`, both strictly inside `0 < ask < 1`. Eligibility is therefore **inferable and near-certain**, and it is written as inferred rather than measured |
| leg membership of `...7772CD6AC5F` | not recorded |
| **who minted these two books** | **CLOSED NEGATIVE** — neither was desk-minted. §2.2.1 |

#### 2.2.1 The minter field, closed NEGATIVE — and closed against the tidier story

Resolved 2026-09-10 **from the record only; no wire read, by the registrar or
by the coordinator.** Three lines, each sufficient alone:

1. **Grep.** The captured `parlay-lookups-tail -n 50` output — all 46 rows as
   of that morning — searched for `S202662C6B3CFEC6-5D18E47B21C` and
   `S2026D379AC93CBF-7772CD6AC5F`: **0 hits each.**
2. **Structural, and independent of the grep — this is the strong line.**
   `...5D18E47B21C`'s recorded legs include `KXEPLGAME-26SEP13MUNMCI-MUN`:
   **English Premier League, which this desk does not carry.** The sport set is
   NCAAF, NFL, MLB, WNBA, so no card this desk can build contains an EPL leg,
   and that combination cannot have come from a desk tap under any
   circumstances. Unlike line 1 it does not depend on any capture being
   complete.
3. **Enumeration.** Every shard-1 ticker `parlay_lookups` recorded on
   2026-09-10 in rows 43–46 (07:09Z) and 47–52 (13:47–13:51Z), disjoint from
   both:

       07:09:18.116Z  S2026F5310CC5321-AC3CA136377
       07:09:21.595Z  S2026928CCB78399-64342DFA711
       07:09:22.917Z  S2026F5310CC5321-AC3CA136377
       13:47:03.789Z  S20261CB777A7654-AEACD1EABF7
       13:47:06.154Z  S20261DE2D499FD6-45BBE137585
       13:51:07.907Z  S2026F58E3D91450-6227B6ACAB1
       13:51:09.470Z  S20269E80D6E68E4-0654C4F7DEB
       13:51:34.543Z  S20269E80D6E68E4-0654C4F7DEB
       13:51:35.944Z  S2026928CCB78399-64342DFA711

   Rows 53–58 were minted at ~14:0xZ and ~14:1xZ, **after** both books'
   `created_time` of 13:43:30Z and 13:45:34Z, so they cannot be these either.

**Two things fall out of that enumeration that nobody asked for, and they
matter more than the resolution does.**

**(a) Nine lookup rows produced six distinct tickers.**
`S2026F5310CC5321-AC3CA136377` appears at 07:09:18 and 07:09:22;
`S20269E80D6E68E4-0654C4F7DEB` at 13:51:09 and 13:51:34; and
`S2026928CCB78399-64342DFA711` at **07:09:21 and 13:51:35 — fourteen hours
apart.** A tap that returns a ticker another tap already returned **did not
create it**. So a non-null `minted_market_ticker` does **not** mean "this tap
minted this market", and at least three of those nine rows demonstrably
created nothing. §7.2's contamination figure moves down accordingly, and
§8.3's keying is left deliberately over-inclusive for the reason given there.

**(b) That is the missing pre-existence flag, made visible in the data.** The
only reason (a) is knowable is that tickers happened to repeat inside one
captured window. For a ticker that does not repeat, the table cannot say
whether the lookup created it or found it. That is exactly the column §8.5
says a future registration must fix — and here is what its absence costs,
measured on nine rows of this desk's own record.

### 2.3 What it licenses, and what it does not

**Licensed, today, without Sunday:**

- The universal sentence *"no combination book read here has carried a YES
  bid"* is **falsified as written**, on the series Joe's money is in, as of
  2026-09-10. The series check is settled (§2.2), so this is no longer
  conditional. §0 of the registration is explicit that the falsifying branch is
  *"fully powered at k = 1"* and needs no `n`, no threshold and no interval. A
  universal claim dies to one counterexample regardless of which instrument
  saw it.
- Two-sided quoting on a shard-1 combination is a state the venue permits, and
  it persisted across multiple reads (§2.2's corrected spans).

**Not licensed, and each of these is a sentence somebody would otherwise
write:**

- **No rate.** Two books out of an unrecorded denominator is not `k/n`. The
  scan denominator was never captured (that is what §5's S3 exists for), so no
  proportion, no Wilson interval, and no comparison to 0-of-40 can be computed
  from Look 1 at all.
- **Nothing about fillability.** §9 stands with full force: a resting bid is a
  stored quote, and minutes of persistence are consistent with a real exit
  **and** with a maker who cancels when an order arrives. No order was placed
  and none should be placed to find out without its own registration.
- **Nothing structural, in either direction.** §9's prohibition on any
  sentence beginning "structurally" applies to a positive exactly as it
  applies to a null.
- **Nothing about Joe's own positions.** These are two specific combinations;
  a resting bid on one is not an exit for another (§11.9).
- **Nothing about size at any time other than 13:52:43Z** (§2.2).

#### 2.3.1 `EXIT_PRACTICAL`: met as an observation, exactly at the registered boundary, and it does NOT fire the registered consequence

The number is now measured rather than recalled, so the registrar scores it
rather than declining.

> §4, registered: `EXIT_PRACTICAL` = **≥ 10 contracts resting on YES at a
> single price on a single book.**

**The unit, settled from this repo's own parser rather than assumed.**
`backend/kalshi/orderbook.py` documents *"Prices are integer tenths of a cent
throughout. Quantities are floats — Kalshi sends fractional sizes"*, and its
`MAX_PLAUSIBLE_QUANTITY` exists *"to catch a units error (dollars read as
contracts)"*. The second element of a level is therefore **contracts**. So:

    ...5D18E47B21C   10.00 contracts resting on YES at 0.0980
    ...7772CD6AC5F   10.00 contracts resting on YES at 0.0570

**`EXIT_PRACTICAL` is met, at exactly 10.00 against a threshold of ≥ 10.**

**The ruling is robust to the unit question anyway**, which is why it is safe
to make. Under the alternative reading (10.00 = dollars of notional) the sizes
are ~102 and ~175 contracts — still ≥ 10, still **< 250**. So
`EXIT_PRACTICAL` is met and **`EXIT_AT_CEILING` is NOT met under either
reading**. `COMBO_MAX_CONTRACTS` is untouched by this document.

**It lands exactly on the registered edge, and the edge is not re-argued.**
A threshold met at precisely its boundary is where post-hoc re-argument is
most tempting — *"only 10, barely"* — and that re-argument is forbidden by the
same principle that fixed the cut in advance. The cut said ≥ 10 before any
book was read. It is met.

**Recorded against interest, because the registrar owes it:** ten contracts at
9.8c is **about one dollar** of exit proceeds. The registered
`EXIT_PRACTICAL` threshold, on first contact with data, turns out to describe
a one-dollar exit. **That is a finding about the threshold, not about the
product, and it is not grounds to move the threshold** — it is grounds for
Sunday's result document to print the *dollar value* of every level beside the
contract count, so nobody reads "practical exit demonstrated" as "a position
can be closed."

**It does not fire the registered consequence.** §6 and §11.7 condition every
consequence on *"any capture on 2026-09-13"*. **A look outside the
registration does not trigger the registered decision rule.** So this document
does **not** reopen ADR 0078's "only exit" framing, does not move
`COMBO_EXIT_CENSUS_BOOKS_WITH_YES_BID`, and does not move
`COMBO_MAX_CONTRACTS`. If Sunday's captures meet `EXIT_PRACTICAL`, the
consequence fires **from Sunday's captures** — and everyone now knows in
advance that it probably will, which is one more instance of §7.1's cost.

### 2.4 ADDED: both quoted books were two-sided within minutes of being minted

This is an observation, it is outside the registration entirely, and it bears
on a different claim than the one Sunday is testing. It is recorded here with
its timestamps because it was seen today and would otherwise live only in a
subagent transcript.

    ...5D18E47B21C   minted 13:43:30.222636Z, observed quoted two-sided
                     by 13:46:39.391076Z at the latest  -> <= 3m09s from mint
                     (possibly as early as 1m47s; the first read is bounded, not recorded)

    ...7772CD6AC5F   minted 13:45:34.187576Z, observed quoted two-sided
                     at 13:46:39.391076Z                -> 1m05s from mint

**This is two observations. It is not a rate and may not become one.** There
is no denominator: nobody counted how many freshly minted books were checked
and found empty in the same window. Two books quoted quickly says the state
occurs; it says nothing whatever about how often.

**What it bears on.** `backend/parlays.py`'s `book_empty` branch tells the
reader *"Every freshly minted combo book this tool has read looked exactly
like this"* and *"nothing in this desk's own record shows an empty combo book
turning into a quoted one on a later ask"*, and ADR 0138 rests on the same
`book_empty` framing. Those are **two separate claims** and this observation
touches only the first:

**RESOLVED 2026-09-10: neither book was desk-minted** (§2.2.1). What follows
is therefore settled rather than conditional, and it settles in the direction
that leaves the existing copy alone.

- **Claim (1), "every freshly minted combo book *this tool* has read looked
  exactly like this":** **NOT at risk. It survives untouched.** This tool
  neither minted nor read these two books — a `kalshi-platform` subagent read
  them over public GETs. The sentence is about what *this tool* has read, and
  §2.4 does not enter its extension.
- **Claim (2), "nothing in this desk's own record shows an empty combo book
  turning into a quoted one on a later ask":** **untouched, as it already
  was.** Both books were quoted on their first recorded read; neither was ever
  observed empty and then quoted.

**So §2.4 changes no screen text and reopens no ADR. ADR 0138 stands.** What
it establishes is narrower and still worth having: a combination book, minted
by someone other than this desk, was two-sided within about a minute of coming
into existence. That is a fact about the venue's market-making, on `n = 2`,
with no denominator — and §8.5 rules on the one inference somebody will want to
draw from it.

---

## 3. Look 2 — twelve deliberate taps, benign on their face, disclosed anyway

### 3.1 What was done

**Twelve** "Price on Kalshi" taps on the live desk on 2026-09-10, recorded as
`parlay_lookups` rows **47–58**. Rows 47–52 ran 13:47Z–13:51Z, on the product
question of whether spread-legged combinations are ever quoted. Rows **53–58**
were six further lookups (48h and next-day horizons, moneyline cards) taken
**after the first draft of this document existed**; every one returned
`book_empty`.

Each tap runs `backend/parlays.py`'s lookup path, which calls
`lookup_combo(..., allow_market_creation=True)` and then reads the resulting
combination's order book. Every one was a `KXMVECROSSCATEGORY-SHARD1`
combination — **the registered Arm D population, exactly.**

### 3.2 What was recorded

| row(s) | what was recorded | which registered quantity it is |
|---|---|---|
| 47, 48, 52 | `yes_levels=0` | **the registered primary quantity**, negative |
| 53–58 | `book_empty` | the registered primary quantity, negative |
| 49 | priced off a resting NO bid, `no_bid` 698 tenths | the S2-shaped quantity (a `no_dollars` level present), on shard 1 |
| 50 | priced off a resting NO bid, `no_bid` 816 tenths | as above |
| 51 | priced off a resting NO bid, `no_bid` 813 tenths | as above |

**Every one of these is consistent with the 0-of-40 baseline and none is
falsifying.** That is true and it is not the point. They are twelve
observations of the registered dependent variable on the registered
population, taken outside the registration, three days early. The disclosure
standard is not "did it change the answer"; it is "was the registered quantity
observed".

### 3.3 Two precision points that de-escalate, and one that escalates

**De-escalating, and both are real:**

1. **The `yes_levels=0` / `book_empty` rows are on books the registered
   eligibility rule would have excluded.** `status='book_empty'` is reached
   when `ask_tenths is None`, i.e. when there is **no resting NO bid** — so
   the list row would carry no readable `yes_ask`, and §2's eligibility
   predicate (`0 < ask < 1`) rejects it. These are therefore observations of
   the numerator variable on rows outside the registered denominator. They
   cannot bias a rate they were never in. *(They can still enter the frame
   later — see §7.2.)*
2. **The only inferential test in the whole registration is untouched.** §5's
   S2 — Fisher exact, two-sided, α = 0.01, on the share of books carrying a
   `no_dollars` level — is registered against the baseline **33 of 40**, and
   that baseline and that test belong to **Arm A**
   (`KXMVESPORTSMULTIGAMEEXTENDED` and `KXMVECROSSCATEGORY`). **Neither look
   read either of those series.** §11.3 separately and explicitly **forbids**
   any difference-of-proportions test of shard-1 rates against the 40. So
   rows 49–51's NO-side observations cannot contaminate the α = 0.01 test,
   because there is no shard-1 S2 test to contaminate. *(Recorded because the
   task that commissioned this document described S2 as sitting on shard 1. It
   does not; §5 and §11.3 place it on Arm A only. That distinction is what
   keeps the single inferential test clean.)*

**Escalating, and it is the sharpest cost in this document:**

3. **These taps did not only observe the population. They wrote to it.**
   `lookup_combo(allow_market_creation=True)` *creates a market on the
   exchange* when the combination does not already exist —
   `backend/kalshi/combos.py`'s module docstring calls it *"an outward-facing
   write"*, which is why the flag exists rather than defaulting on. The
   registration's §8 refuses `multivariate_event_collections` **for exactly
   this reason**: *"that endpoint can create a market on the exchange and is
   refused here. ... this run creates nothing."* Look 2 created up to **twelve**
   shard-1 markets, dated today, three days before a run that samples the
   **newest-first, truncated** page of that series (§12.3). Treated in full in
   §7.2. **This charge attaches to Look 2 alone. Look 1 was unauthenticated
   `GET` only and created nothing** (§2.1).

### 3.4 The unregistered 2×2, disclosed

A 2×2 on quote rate by leg type (spread-legged vs. not) was computed from
`parlay_lookups` after these taps. It is disclosed here in full and it is
**not a finding**:

- `n` is small, and the cell boundaries (what counts as "spread-legged") were
  fixed **after** it was visible which taps priced. That is the exact ordering
  this registrar exists to prevent, and it makes the 2×2 uninterpretable
  rather than merely weak.
- It is **not in the registration's multiplicity count** (§5: five captures ×
  two secondary comparisons = ten cells, one pooled inferential test). It
  cannot be added to that count retrospectively, and it may **not** appear in
  the 2026-09-13 result document as a supporting cell.
- **It has since been shown to be confounded**, independently: a
  `measurement-skeptic` audit found that *"spreads are not quoted"* and
  *"self-minted tickers are not quoted"* are **observationally identical** in
  `parlay_lookups`, which records no pre-existence flag. §8.5 rules on what
  §2.4 does and does not do to that confound.
- If "do spread-legged combinations quote more often?" is worth answering, it
  needs **its own pre-registration**, written before any further tap, with the
  leg-type partition **and** a pre-existence flag fixed in advance — and it now
  starts from a contaminated position, because the direction has already been
  seen. That is a cost of having looked, and it is charged here rather than
  forgotten.

---

## 4. The route, for each look, stated so the difference is not blurred

| | Look 1 | Look 2 | The registered run |
|---|---|---|---|
| instrument | unauthenticated `urllib.request` GETs by a `kalshi-platform` subagent | the live cockpit's "Price on Kalshi" tap | `scripts/measure_combo_book_presence.py --series KXMVECROSSCATEGORY-SHARD1 --max-books 25 --depth 10` |
| depth requested | 5 | the route's own | 10 |
| eligibility predicate applied | none — but inferable post hoc (§2.2) | none — the tap prices whatever card was built | §2's, unmodified |
| denominator captured | **no** | no (twelve taps are not a scan) | yes, S3, via captured stdout |
| clustering / `G_eff` | 2, established post hoc (§2.2) | not computed | required field (§3, §11.5) |
| credential in process | **no** | yes (authed desk session) | no — §8 |
| **creates a market on the exchange** | **no** | **yes** | **no — explicitly refused (§8)** |
| opens the cockpit UI | no | **yes** — see §9 | forbidden (§8) |
| artifact | agent transcript | `parlay_lookups` rows 47–58 | committed JSON + stdout per slot |

---

## 5. What the two looks jointly do and do not license anyone to conclude

**Do:**

- Assert, today, that the screen sentence *"Every combination book this repo
  has ever read had no YES bid — 40 of 40, across three runs on two dates"* is
  **false as written**, or true only under a reading of *"this repo has read"*
  so narrow that the reader will not supply it. The series check is settled, so
  this is unconditional. It is a live-surface copy problem **today**, not a
  Sunday problem. See §8.1.
- Assert that resting YES bids on shard-1 combinations are a state the venue
  produced at least twice on 2026-09-10, at 9.8c and 5.7c, ten contracts each.
- Assert that a combination book **this desk did not create** (§2.2.1) can be
  two-sided within about a minute of being minted (§2.4) — and nothing beyond
  that, per §8.5.

**Do not:**

- Quote any rate, from either look, for anything.
- Claim shard 1 is more or less liquid than the non-shard series (§11.3
  forbids this and neither look could support it anyway).
- Fire any registered consequence (§2.3.1). This document moves no constant,
  no screen text, no ceiling, and reopens no ADR.
- Treat either look as a substitute for Arm D. The run still fires.

---

## 6. The baselines are on a different population, and shard 1 has never been censused

Flagged, not resolved, and deliberately not pre-empting Sunday:

- **`0 of 40` (the YES-bid baseline) and `33 of 40` (the S2 NO-side baseline)
  were both measured on `KXMVESPORTSMULTIGAMEEXTENDED` and
  `KXMVECROSSCATEGORY`.** The registration's own §1 `FOUND 2026-09-09` block
  established that `series_ticker=KXMVECROSSCATEGORY` returns **only**
  non-shard tickers, that the two row sets are disjoint, and that across all
  three recorded runs the count of `SHARD1` tickers is **zero**.
- **`KXMVECROSSCATEGORY-SHARD1` has never been censused by any instrument in
  this repo.** Amendment 1 §11.3 records that Arm D has **no baseline at all**.
- Therefore **neither look can be compared to either baseline**, and today's
  observations are not "a departure from 0 of 40" — they are the first
  book-level observations of a population with no prior.
- What the size of that population is, what its quote rate is, and what its
  YES-bid rate is remain **unmeasured**, and this document takes no position
  on any of them. That is Sunday's question and it stays Sunday's question.

---

## 7. What the disclosure costs. Stated without softening.

### 7.1 The Sunday primary is not statistically compromised, and it is materially compromised. Both, and they are different things.

**Not statistically compromised, and the reason is in the registration's own
words.** §5: *"The primary is not a significance test at all and does not
consume multiplicity: observing a resting order is an observation, not a
fluctuation."* There is no alpha attached to the primary, so there is no alpha
for an early look to spend. The sequential-looking hazard this repo has
measured elsewhere (a threshold re-evaluated against an accumulating database
crosses under a true zero with probability 1; measured at 13.7%, a floor)
applies to **thresholded tests on accumulating data**. The Arm D primary is
neither. **An adjusted alpha is not owed and would be theatre** — see §8.4.

**Materially compromised, in one specific and serious way: the answer is known
before the run.** Sunday can no longer *discover* that shard-1 books carry
resting YES bids. It is known, on named tickers, as of 2026-09-10. What Sunday
can still do is measure the **rate**, the **depth against §4's three fixed
thresholds**, the **`G_eff`**, and the **five-slot time profile** — none of
which either look supplies. That is a real and worthwhile measurement, but it
is a different headline from the one the registration wrote, and the write-up
must say so. §8.2 fixes the wording.

**The null branch is damaged, and this is where the dishonest sentence would
live.** If Sunday returns zero YES levels across all five slots and ≥ 10
distinct books, §11.7 licenses adding a scope clause and the shard constants.
Written without this document, that null reads as *"shard-1 combination books
showed no resting YES bid"* — which, three days after two named ones did, is
false by omission. A null on Sunday is now evidence about **Sunday**, not about
the series. §8.2 fixes that wording too.

**And one asymmetric hazard, named now while it is still cheap.** Knowing the
answer creates the freedom to not run, to run fewer slots, or to characterise
a thin day as bad luck. **Fixed here: the run fires exactly as registered, all
five slots, and the result document is written whatever it returns. Any
cancellation, truncation, slot-drop, or instrument change after today is
itself a reportable event and must be recorded in the result document with its
reason.**

### 7.2 The sampling frame has been altered by this desk's own writes — by Look 2, not Look 1

This is the cost that is not about looking at all.

Amendment 2 §12.3 registered, before any data, that Arm D *"samples the newest
slice of shard 1, not a random sample of it"*, and that newly minted
combinations are *"plausibly less likely to carry a resting order, which is the
direction that would flatter a null."*

Look 2 **created or re-touched up to twelve shard-1 markets on 2026-09-10**
(`parlay_lookups` rows 47–58), at the front of that newest-first page. That
count is an upper bound and is now known to be loose: of the nine rows whose
tickers §2.2.1 enumerates, three returned a ticker an earlier tap had already
returned and therefore created nothing — **six distinct tickers from nine
rows**, with rows 53–58 unenumerated here. Three rows (49, 50, 51) came back
with a resting NO bid and therefore a **readable ask**, which is precisely
§2's eligibility predicate. If those asks persist to Sunday, **those rows are
eligible for Arm D**, and they are rows this desk created or touched, for cards
this desk built, three days earlier. The nine `book_empty` rows are not
eligible *today*, but nothing stops one acquiring an ask before Sunday, so they
belong in the disclosure set too.

The scale matters: Arm D's cap is 25 against **13 eligible observed in the
newest 1,000** on the midweek probe. Desk-minted eligible rows against a pool
of that order are not a rounding error. And their age (§12.3's S4 descriptive
secondary) will be ~3 days, at the young end of whatever distribution Sunday
returns.

**Look 1 contributed nothing to this.** Unauthenticated `GET` only (§2.1).
The first draft of this document did not know that and implied otherwise; the
correction is recorded in the block at the top because it runs in the
exculpatory direction.

**No new exclusion is created here, and none may be created on the day.** §2 is
explicit: *"No exclusion may be added on the day. If the day produces a
category nobody anticipated, it is reported in full and the verdict is computed
both with and without it, both figures printed."* That clause already covers
this exactly, and invoking it is the correct response rather than inventing a
rule after the fact. §8.3 states the concrete reporting obligation.

### 7.3 What is unaffected

- **Arm A entirely** — population, selection, the S2 Fisher test, α = 0.01,
  the ten-cell multiplicity count. Neither look read those two series.
- **Arms B and C.** Untouched; §11.10's expectation that Arm C aborts stands.
- **`COMBO_MAX_CONTRACTS`.** `EXIT_AT_CEILING` is not met under either unit
  reading (§2.3.1).
- **The 300-game gate, `beta`, ADR 0038, the 0.63-point cost headroom.** §9's
  prohibition holds: no number in this document may appear in a sentence about
  edge. Nothing here is evidence about edge.
- **The concurrent attended-NFL-Sunday odds measurement.** Neither look
  occurred on 2026-09-13. Today's UI use is a separate matter and is §9.

---

## 8. Corrections owed, named concretely

### 8.1 A screen-copy correction, owed now, not on Sunday

The buy ticket's *"Every combination book this repo has ever read had no YES
bid — 40 of 40, across three runs on two dates"* is a **universal quantifier on
a real-money surface** and Look 1 is a counterexample to it under the reading
its reader will supply. Amendment 1 §11.8 and Amendment 2 §12.4 already ruled
that a scope clause is owed **before C1 at 15:30Z on 2026-09-13**, sourced
never typed, on **both** surfaces (`backend/api/routes.py`'s `combo_note` and
`backend/api/routers/parlays.py`'s 422), pinned by a test verified by removing
the clause and watching it go red.

**Look 1 raises that from owed-by-deadline to owed-now**, and changes what the
clause must say: a sentence beginning *"Every combination book this repo has
ever read"* is now false as written, and the two tickers are in hand. **This
registrar has no authority over real-money screen text and is not changing
it.** The requirement recorded here: the clause must be settled with Joe or the
partner **before** the run, it must not imply a rate that nothing has measured,
and §12.4's "show Joe the diff" instruction stands.

**The `book_empty` string is NOT in the same position, and that is now
settled.** §2.4's minter field resolved negative (§2.2.1): neither quoted book
was desk-minted or desk-read. So *"Every freshly minted combo book this tool
has read looked exactly like this"* and its companion *"nothing in this desk's
own record shows an empty combo book turning into a quoted one on a later
ask"* **both stand, are changed by nothing in this document, and ADR 0138 is
not reopened.** The correction owed in §8.1 is the `combo_note` / 422 scope
clause, and nothing else. Recorded explicitly because the first draft listed
this string as at-risk, and a reader who stopped there would carry a
correction that is no longer owed.

### 8.2 A restated claim for the 2026-09-13 result document

The registered claim, the α, the population, the stopping rule and the
decision rule are unchanged (§11). What changes is what the **result document**
is permitted to say it discovered.

- **The headline may not be a discovery.** If Sunday finds YES levels, the
  licensed headline is of the form: *"A resting YES bid on
  `KXMVECROSSCATEGORY-SHARD1` was first observed on 2026-09-10, outside this
  registration and disclosed at
  `docs/measurements/2026-09-10-disclosed-unregistered-look-combo-exit-shard1.md`.
  The registered run of 2026-09-13 measures the rate, the depth and the time
  profile."* Not *"found on Sunday"*.
- **The null branch's licensed sentence gains a mandatory clause.** §12.3
  already constrains it to *"no resting YES bid on the newest N shard-1
  combinations carrying a readable ask, read at five slots on 2026-09-13"*,
  with "newest" and the age range **in the headline**. That sentence must now
  additionally carry: *"and two named shard-1 books carried resting YES bids on
  2026-09-10 (see the disclosure document)."* A null published without that
  clause is false by omission.
- **`EXIT_PRACTICAL` and `EXIT_AT_CEILING` are scored from Sunday's captures
  only.** §2.3.1's scoring is an observation outside the registration and does
  not fire the registered consequence.
- **Every level reported on Sunday prints its dollar value beside its contract
  count**, per §2.3.1's note against interest.

### 8.3 A required field in the Arm D tables — keyed to a predicate, not to row numbers

Invoking §2's existing both-figures clause, not a new rule. **Re-keyed** after
the tap count moved 6 → 12, so it cannot go stale a third time:

> The result document must report, for every Arm D capture, **how many
> selected rows are markets minted by this desk's own taps on 2026-09-10** —
> identified as **every `parlay_lookups` row whose `requested_ms` falls on
> 2026-09-10 (UTC) and whose `minted_market_ticker` is non-null**, matched by
> market ticker — and must print the Arm D proportion, its Wilson interval and
> its `G_eff` **both with and without them, both figures printed, neither one
> chosen.**

If the two figures disagree, that disagreement is the result and is not
reconciled, exactly as §11.1 already requires for Arm A vs. Arm D.

**Why the predicate is deliberately over-inclusive.** §2.2.1 shows that a
non-null `minted_market_ticker` does **not** mean the tap created the market —
three of nine rows returned a ticker an earlier tap had already returned. The
table cannot distinguish *created* from *found*, so the disclosure set is keyed
to the superset. **Over-inclusion is the safe direction for a disclosure set;
under-inclusion is not.** A row wrongly disclosed costs a line in a table; a
row wrongly omitted costs the disclosure.

**And the sting that was in the tail is drawn.** The §2.2 minter check
resolved negative, so the falsifying observation is **not** a desk-created row.
Sunday's with/without split remains a required table and does **not** become
the headline of the result document.

### 8.4 An adjusted alpha is NOT owed, and refusing one is not a dodge

The temptation is to buy absolution with a smaller α. It would be theatre:

- The **primary** carries no α at all (§5). Shrinking a number that does not
  exist changes nothing.
- The **only** α in the document (S2 Fisher, 0.01) belongs to Arm A, whose
  population neither look touched. Tightening it would penalise a clean test
  for a look taken elsewhere, and would make the registration *look* more
  rigorous while leaving the actual damage — a known answer and a contaminated
  frame — entirely unaddressed.

The corrections that are owed are §8.1, §8.2, §8.3 and §8.5. They are wording,
disclosure, dual reporting and one open field, because that is where the
damage is.

### 8.5 Ruling on the skeptic's confound, since it was asked

The `measurement-skeptic` audit's finding stands on its own: *"spreads are not
quoted"* and *"self-minted tickers are not quoted"* are **observationally
identical** in `parlay_lookups`, because the table records no pre-existence
flag. Nothing in this document resolves that, and the product question is not
the registrar's to adjudicate.

**Ruled, applying the conditional exactly as it was written before the answer
was known: the confound SURVIVES INTACT.** The minter field resolved negative
(§2.2.1) — neither quoted book was desk-minted. Therefore **§2.4 says nothing
whatever about self-minted tickers and must not be cited against the
self-minting story.** Anyone reaching for it would be citing two books this
desk did not mint as evidence about books it did.

**The step further — "weak positive evidence FOR the self-minting story" —
OVERREACHES, and I decline it. Here is the arithmetic rather than an
assertion.**

The proposed inference is: the two books anyone quoted are exactly two this
desk did not create, so self-minted tickers quote less. Score it as a
likelihood ratio, which is the only honest way to weigh `n = 2`:

- Under *"self-minted tickers are never quoted"*: P(both quoted books are
  non-desk) = **1**.
- Under **no association whatsoever**: P(both quoted books are non-desk)
  ≈ `(1 − d)²`, where `d` is the desk's share of the scanned shard-1
  population. At 13:46Z the desk had touched **two** distinct shard-1 tickers
  all day (rows 43–46; every later tap postdates the observation) against a
  scanned page of **≥ 1,000** open rows. So `d ≲ 0.002` and the probability is
  **≈ 0.996**.
- **Likelihood ratio ≈ 1.004.**

That is not weak evidence. **It is no evidence**, and it would have come out
identically had the self-minting story been false. The failure mode is the
base rate: when the desk's mints are two rows in a thousand, finding that two
quoted books came from the other 998 is exactly what independence predicts. **A
result guaranteed under both hypotheses discriminates between them not at
all** — and recording it as directional would be the "correction toward the
tidier story" this registrar exists to catch, the more so because the tidier
story here is the one the desk already believes.

**What would be evidence, and it is registrable.** A **paired** read: the
desk's own shard-1 tickers and a size-matched sample of non-desk shard-1
tickers, read at the same instants, quote rate compared within pair. That has a
denominator on both arms and is not confounded by calendar or liquidity drift.
It needs its own pre-registration and must not be run off the back of today's
looks.

**One thing in the desk's own table is closer to evidence than §2.4 is, and it
points the other way.** Rows 49, 50 and 51 are desk-touched shard-1 tickers
that came back **priced off a resting NO bid** — somebody was quoting them. If
those three were *created* by those taps, then the universal form of
"self-minted tickers are not quoted" is **false on the desk's own record**,
with no help from Look 1 at all. Whether they were created or merely found is
unknowable, because `parlay_lookups` has no pre-existence flag (§2.2.1). **The
same missing column blocks the one line of evidence the desk already owns** —
which is a stronger argument for adding it than anything Look 1 supplies.

**And the structural point, which is free and does not depend on the answer:**
the reason this is even ambiguous is that `parlay_lookups` records no
pre-existence flag, and `lookup_combo`'s response distinguishes a created
market from an existing one at the moment of the call. Whatever the minter
check returns, **any future registration of the spread-quoting question must
fix a pre-existence flag before its first tap**, or it will re-derive the same
unresolvable table.

---

## 9. One further disclosure, small and owed anyway

Look 2 was taken **through the cockpit UI on live**. §8 of the registration
forbids opening the cockpit UI *to run the captures on 2026-09-13*, because a
page-open registers attention and contaminates the concurrent dwell
measurement. Today is not 2026-09-13, so that clause is not breached. But
**twelve** taps on live across 2026-09-10 are a real attention event in
`api_credits` and in the visit-freshness record for the day, and anyone
reading dwell for this week should know they were an agent's product
investigation and not Joe at the desk. Recorded here rather than left to be
inferred from a spike. *(Count corrected from six; the last six taps postdate
the first draft.)*

---

## 10. What this disclosure document itself cannot establish

- **It contains no independent verification.** The registrar took no live read,
  by instruction and by principle. Every figure is relayed from the observing
  agent's transcript and from `parlay_lookups`, recovered by recall with no
  re-observation. The series check is strong because it is doubly redundant
  (ticker text and query parameter); the level values rest on a single
  transcript quotation of a single payload.
- **It cannot recover the counterfactual.** What is unknowable, permanently, is
  what would have been dispatched, tapped or written today had Look 1 come
  back empty. That is the loss this whole practice exists to prevent, and no
  disclosure recovers it. It is charged here as a loss, not repaired.
- **It is not evidence about the product.** Nothing in it is a rate, a
  denominator, or a census. It is a record of what was seen and by what route.
  Two books and twelve taps have no denominator between them.
- **It cannot bind a future author.** It can only make the omission legible.
  §12's line is the enforcement, and it is enforcement by embarrassment, not by
  code.

---

## 11. What is UNCHANGED, stated field by field

**The registration at
`docs/measurements/2026-09-09-preregistration-combo-exit-nfl-sunday.md` is not
edited by this document and must not be.**

| field | status |
|---|---|
| Registered claim (§1) | **UNCHANGED** |
| One-sided direction, forced by the boundary (§1) | **UNCHANGED** |
| Arm A population, eligibility, selection (§2) | **UNCHANGED** |
| Arm D population — the literal ticker `KXMVECROSSCATEGORY-SHARD1` (§12.1) | **UNCHANGED** |
| Exclusions, and the ban on adding one on the day (§2) | **UNCHANGED** |
| Unit, clustering key, `G_eff` as a required field (§3, §11.5) | **UNCHANGED** |
| `EXIT_ANY` / `EXIT_PRACTICAL` / `EXIT_AT_CEILING`, **including the ≥ 10 edge** (§4) | **UNCHANGED** |
| Estimators, S1–S4, the ten-cell multiplicity count (§5, §12.3) | **UNCHANGED** |
| **α = 0.01, Fisher exact, two-sided, Arm A S2 only** (§5) | **UNCHANGED** |
| Decision rule, Arm A (§6) and Arm D (§11.7) | **UNCHANGED** |
| The floor of 10 distinct books; ABORTED-THIN (§6, §11.5) | **UNCHANGED** |
| Stopping rule — five slots, collection ends 2026-09-14 01:15Z, no sixth capture (§7) | **UNCHANGED** |
| Cost, safety, non-interference, no market creation (§8) | **UNCHANGED** |
| Limitations (§9, §11.9) | **UNCHANGED** |
| Result path `docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`, every branch (§10) | **UNCHANGED** |

The registered Arm D decision rule, quoted verbatim so it can be checked
against whatever gets written on Sunday:

> **If any capture records at least one level on `yes_dollars` for a parsed
> shard-1 book (`EXIT_ANY`), the sentence "no combination book read here has
> carried a YES bid" is false on the population Joe actually trades — the
> strongest available falsification — and the buy ticket's `combo_note`, the
> bid route's 422 and `tests/test_combo_book_depth_claims.py` change to a rate
> that names its series; ADR 0078's framing of a leg hedge as "the only exit an
> enter-only combo has" is reopened in a new ADR if `EXIT_PRACTICAL` (≥ 10
> contracts at one price) is also met, and `COMBO_MAX_CONTRACTS` moves only
> under `EXIT_AT_CEILING` (≥ 250 at one price), exactly as §6 already rules.
> If zero YES levels are recorded across all five slots and at least 10 distinct
> shard-1 books were read, that is NOT confirmation (§0): the only licensed
> change is the scope the screens currently lack — the note names the series it
> was measured on, and the two new shard constants in §11.4 record the shard
> census separately. Below 10 distinct books, Arm D is ABORTED-THIN and nothing
> changes.**

---

## 12. The citation obligation

> **Whoever writes `docs/measurements/2026-09-13-combo-exit-nfl-sunday-result.md`
> must cite this document, in the result document's own body and in every
> branch — positive, null, or ABORTED-THIN. A result document that reports
> Sunday's captures without disclosing that the registered primary quantity was
> observed on 2026-09-10, outside the registration, on the registered
> population, on two named tickers, and that up to twelve of the rows in that
> population were minted by this desk on that date, is dishonest by omission.
> That is the standard, it is written down before the run, and it is not
> negotiable afterwards.**
