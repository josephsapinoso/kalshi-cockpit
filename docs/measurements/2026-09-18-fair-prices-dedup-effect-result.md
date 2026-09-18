# Result — did the `fair_prices` dedup deliver?

**VERDICT: DEDUP DELIVERING.** `rho ≈ 0.0044` against a registered threshold of
`0.25`; the two parts fall on the same side of it; the preservation probe
returned **0 violations**; all five preconditions answered YES.

Registration: `docs/measurements/2026-09-17-preregistration-fair-prices-dedup.md`,
including **Amendment 1 (2026-09-18)**, which resolved the windows before `Q1`
ran and corrected §3's expected day counts.

The read was taken **2026-09-18T08:10:02Z** (`snapshot_ms 1789719002569`),
inside §9.2's run window of 07:00Z–11:00Z. One `mode=ro` session against
`file:/data/cockpit.db?mode=ro`. `Q1` then `Q2`, then stop. `Q1` took
**16,159 ms**; `Q2` took **18 ms**.

**No `dbstat` read was taken inside the registered session** (§9.4) and no byte
figure is quoted below. **That is narrower than §0.4's declared blindness, and
the difference is disclosed in §0 rather than left for a reader to find.**

**Read §11 and §12 before quoting any of this.** In particular: **zero existing
bytes were reclaimed**; this is a statement about an insert rate over two named
past windows; the *denominator* — how many pricing passes ran in each window —
was never measured, so this is **not** a measurement of the duplication rate;
and it is not evidence that the 4 GB box is sufficient or that the 503 stops.

---

## 0. DISCLOSURE — the declared blindness was broken before this look, and by us

§0.4 of the registration listed, under *"Not seen, not queried, not
requested"*: **"any `db-sizes` output after 2026-09-09T19:49Z; the live file
size today."** That blindness did not hold, and the breach is on this repo's own
record rather than in anything the venue did.

    2026-09-18 (thirty-first session), tasks/NEXT.md:337
        "`inspect_live_db.py db-sizes` walks `dbstat` -- the whole 6.3 GB file
         through a 3 GB page cache -- and was run during the diagnosis before
         its description was read. Killed locally at 180 s; the remote process
         was not confirmed dead."

    2026-09-18T03:16:52Z, the only comment on #58, ~5 hours before Q1
        the file is 6.3 GB, growing ~137 MB/day on a two-point read

    tasks/NEXT.md:299-300, read by THIS session at session start, before Q1
        "~100 days at ~137 MB/day, a two-point slope"

So a `dbstat` walk of the live file ran on 2026-09-18 before the look; the byte
slope was published to the very ticket this look feeds; and the session taking
the look read that slope before opening a connection. **§1.2's table puts
"dedup does nothing" at 326.6 MB/day and "dedup works" at 141.0 MB/day.
~137 MB/day sits on the second row.** The answer was therefore knowable on byte
evidence before `Q1` ran, and §0.3's *"the mechanism ran blind; the measurement
does not have to"* is no longer true of this look.

**What this does and does not spoil:**

- **The threshold is uncontaminated.** `0.25` was fixed on 2026-09-17, derived
  in §6.2 from figures on the record before 2026-09-09, and the byte read
  postdates it.
- **The windows are uncontaminated.** They were resolved from the deploy
  record, not from any count or byte figure — the ordering is evidenced in §1
  P2 and §2, and §4's sensitivity table shows no available resolution could have
  been outcome-driven.
- **The analyst was not blind.** A reader entitled to §0.4's assurance should
  know that. That is what this section is for.
- **The byte slope agrees with the row-rate result.** Recorded here as an
  **unregistered observation**, not as confirmation this registration earned.
  Corroboration you do not declare is worse than corroboration you claim.

**Also a deviation from §8.3, and the better call of the two:** §8.3 says the
session writing this document "opens a sub-issue of map #3". It did not — #58 is
already an open sub-issue of #3 and its title *is* the §8.3 PASS-branch
question. The result was carried there as a comment rather than duplicated into
a new ticket.

---

## 1. The §9.1 precondition answers

Each was answered, in writing, **before any connection to the live database was
opened** — `scratchpad/dedup_look_params.md`, last written 08:07:46Z against a
connection opened at 08:10:02Z. None of the five is a database query, and none
became one.

### P1 — the downsampler is off — **YES**

    live container, `printenv | grep -i downsample`  -> NO_DOWNSAMPLE_ENV
    `flyctl secrets list -a kalshi-cockpit`          -> no downsample name
    `fly.live.toml`                                  -> no DOWNSAMPLE entry, ever
                                                        (`git log -S DOWNSAMPLE --` empty)
    backend/config.py:1042-1043   enabled=_bool(..., False)
                                  dry_run=_bool(..., True)

`fair_price_downsample.run` refuses on **either** flag and both default to
refusing, so two independent env vars would have had to be set. Neither has ever
appeared in the repo config and neither is on the box.

**Residual, stated rather than hidden:** a secret set and later unset would not
appear in `flyctl secrets list`. The per-day series in §3 is also inconsistent
with a 14-day deletion window having run — 09-01..09-09 are all present at full
magnitude, and D1's window would have cut the earliest of them by now. That is
corroboration from the registered output, not a sixth precondition.

### P2 — the v36 deploy instant is established — **YES for the UTC day, which is all §3 needs. The instant inside the day is NOT settled, and §3 of the registration was wrong by a day.**

§3.1/§3.2 used the **commit** instant (2026-09-09T21:56:46Z, `e8ec6ff`) as a
proxy for the **deploy** instant. The derivation is Amendment 1; the short form:

    e8ec6ff        committed 2026-09-09T21:56:46Z. `git log -S` on
                   `confirmed_oldest_book_age_ms` and on `_FAIR_PRICE_KEY_COLUMNS`
                   each return this one commit -- the v36 migration and the dedup
                   shipped together
    2026-09-09     session close: live is still `2126dde`, "nothing from this
                   session is deployed", "Schema v35 -> v36, migrated but not
                   yet deployed" (tasks/archive/next-2026-09-11.md:37)
    2126dde        does not contain e8ec6ff (git merge-base --is-ancestor)
    run 34437560202  created 2026-09-10T04:32:13Z, completed 04:36:45Z, sha
                   324a53f -- the first `deploy.yml` run containing e8ec6ff

> **The UTC day containing the v36 deploy instant is 2026-09-10.** The instant
> inside that day is somewhere in `[2026-09-09T21:56Z, 2026-09-10T04:36Z]` and
> §5 explains why 04:36Z is probably the wrong end of it.

`flyctl releases` retains 25 releases (oldest 2026-09-15) and cannot reach that
far back; the GitHub deploy-run list can, and is what was used. **Only the day
enters §3**, and every candidate instant in that interval yields the same day
except one — see §5, which is why that section exists and why nothing was moved.

### P3 — no `DELETE FROM fair_prices` outside the downsampler module — **YES**

    rg "DELETE FROM fair_prices" backend/
      backend/store/fair_price_downsample.py:660   (docstring)
      backend/store/fair_price_downsample.py:695   (the statement)

### P4 — a single read-only session, exactly `Q1` and `Q2` — **YES, and measured rather than asserted**

One `python -c` on the box, one connection, two `execute` calls, in §9.3's fixed
order. The harness timed itself around the whole session:

    snapshot_end_ms - snapshot_ms   16,177 ms
    q1_ms + q2_ms                   16,159 + 18 = 16,177 ms
    unaccounted                          0 ms

**Zero milliseconds are unaccounted for**, which leaves no room for a third
statement. That is a measurement of the precondition, not a promise about it.

The harness was **rehearsed in full — both `Q1` and `Q2` executed end to end,
not merely `EXPLAIN`ed — against the local `data/demo.db`**, to catch a syntax
error before spending a live session. No number from that database is quoted
anywhere (§3.5).

### P5 — §4's clustering floor — **YES, at exactly its minimum**

    post >= 6 complete UTC days            6   MET, ZERO margin
    post contains 2026-09-13 (NFL Sunday)  YES
    post contains >= 1 MLB weekday         YES  (09-11 Fri, 09-15 Tue, 09-16 Wed)
    pre  >= 6 complete UTC days            9   MET

§4's named INCONCLUSIVE trigger — *"if the v36 deploy instant turns out to be
later than 2026-09-11T00:00:00Z"* — does not fire, and the trigger is
**equivalent to the floor** rather than an extra condition: a deploy inside
09-10 gives an excluded day of 09-10 and a 6-day post window (floor met); a
deploy after 09-11T00:00Z gives an excluded day of 09-11 and a 5-day post window
(floor breached). The registration drew its boundary one day beyond where the
deploy landed. The floor is met at exactly its minimum, and **`G_post = 6`
rather than 7 is one day from having returned INCONCLUSIVE.**

---

## 2. The deploy instant and the two resolved windows

    V36 DEPLOY: UTC day 2026-09-10 (instant within it not settled -- §5)

    EXCLUDED DAY  2026-09-10                                   (§3.3)
    PRE  WINDOW   [1788220800000, 1788998400000)
                  2026-09-01 .. 2026-09-09    G_pre  = 9       (§3 expected 8)
    POST WINDOW   [1789084800000, 1789603200000)
                  2026-09-11 .. 2026-09-16    G_post = 6       (§3 expected 7)

Both boundaries were fixed in writing at 08:07:46Z, before the 08:10:02Z
connection, and **neither was moved in response to any count** (§6.3). §4 makes
that verifiable by arithmetic rather than by assertion.

---

## 3. The per-day counts, in full

`Q1`, verbatim as registered, both bounds present,
`market IN ('h2h','spreads','totals')`.

| day | h2h | spreads | totals | window |
|---|---:|---:|---:|---|
| 2026-09-01 | 221,372 | 283,782 | 0 | PRE |
| 2026-09-02 | 393,446 | 426,712 | 0 | PRE |
| 2026-09-03 | 333,416 | 405,212 | 0 | PRE |
| 2026-09-04 | 423,268 | 451,700 | 0 | PRE |
| 2026-09-05 | 469,712 | 437,384 | 0 | PRE |
| 2026-09-06 | 275,752 | 285,382 | 0 | PRE |
| 2026-09-07 | 307,634 | 363,848 | 0 | PRE |
| 2026-09-08 | 359,462 | 386,054 | 0 | PRE |
| 2026-09-09 | 394,392 | 418,706 | 0 | PRE |
| **2026-09-10** | **2,132** | **1,772** | **0** | **EXCLUDED** |
| 2026-09-11 | 1,944 | 1,848 | 0 | POST |
| 2026-09-12 | 2,534 | 2,958 | 0 | POST |
| 2026-09-13 | 1,285 | 1,172 | 0 | POST |
| 2026-09-14 | 1,693 | 1,803 | 0 | POST |
| 2026-09-15 | 956 | 901 | 631 | POST |
| 2026-09-16 | 1,256 | 1,163 | 1,116 | POST |

**No day carries a verdict** (§6.1, §11.8). Three observations, each context and
not a test:

1. **`totals` has zero pre-window rows**, exactly as §3.4 predicted when it
   excluded them from `rho` for having no denominator. **Its first rows appear
   2026-09-15, not 09-14** as §11.5's table dates the change, so the `totals`
   upward confound applies to 2 of the 6 post days rather than to the window.
2. **The pre-window per-day figures range 2.1x** (221,372 to 469,712 on h2h).
   The pre window is not a flat baseline, which is why §4 prints the series and
   §5.1 declines to attach a standard error to a ratio of its mean.
3. **The excluded day is discussed in §5, on its own, because the obvious
   reading of it is wrong by a factor of 36.**

### The plan, and what was and was not observed

    SEARCH fair_prices USING COVERING INDEX idx_fair_market_computed
        (market=? AND computed_ms>? AND computed_ms<?)

**That plan was read from the local `data/demo.db`, not from live.** The live
plan was deliberately not read, because `EXPLAIN QUERY PLAN` would have been a
third statement and P4 fixes the query set at two. So index-only execution on
live is **inferred from the schema, not observed**: `idx_fair_market_computed`
is `(market, computed_ms DESC)`, `Q1` references only those two columns, and
both bounds are present. SQLite can choose differently given live's own
statistics, and nothing here rules that out.

---

## 4. The windows could not have been chosen to suit the answer, and here is the arithmetic

§6.3's prohibition is on moving a boundary *in response to the counts*. The
ordering evidence is in §1 P2. The stronger answer does not depend on trusting
it — `rho` under **every** window resolution available:

| pre | post | `rho` |
|---|---|---:|
| 09-01..09-09 (G=9) | 09-11..09-16 (G=6) | **0.004410** ← as run |
| 09-01..09-08 (G=8) | 09-11..09-16 (G=6) | 0.004467 |
| 09-01..09-09 (G=9) | 09-10..09-16 (G=7) | 0.004536 |
| 09-01..09-08 (G=8) | 09-10..09-16 (G=7) | 0.004595 ← §3's expectation |

Max/min = **1.042**. Every resolution is 54–57x below the cut. **No choice of
boundary available in this data could have changed the verdict**, so the §6.3
question closes on arithmetic rather than on an ordering claim.

---

## 5. The excluded day, and why 04:36Z is probably the wrong instant

2026-09-10 came back at **3,904** deciding rows — post-window magnitude, not
pre-window magnitude. The tempting reading is that this corroborates a 04:36Z
deploy: ~4.6 hours of unconditional inserts, then ~19.4 deduped. **That reading
is refuted by the document's own numbers.**

    pre-window mean          737,470 rows/day  =  30,728 rows/hour
    4.6h at that rate        ~141,349 rows expected from the pre-deploy segment ALONE
    observed, ALL of 09-10      3,904 rows
    over-prediction               36x

Inverted: the insert rate over 00:00–04:36Z was **at most ~849 rows/hour, 2.8%
of the pre-window mean** — an upper bound, since some of 09-10's rows are
post-deploy. So the excluded day does **not** corroborate a 04:36Z instant.

**The better-supported account, and it reconciles a third fact:** the deploy of
`324a53f` at 04:32Z logged its boot migration as **`v36 -> v37`**
(`tasks/archive/next-2026-09-15.md:2092`). A database already at v36 means
**v36 was applied by an earlier boot** — so `e8ec6ff` reached live before the
04:32Z run, by a deploy that left no `deploy.yml` record, i.e. a local
`flyctl deploy`. Three facts then agree:

    09-09 at full pre-dedup magnitude    -> v36 was NOT live during 09-09
    09-10 at post-dedup magnitude all day -> v36 WAS live from ~00:00Z on 09-10
    the 04:32Z boot log says v36 -> v37   -> v36 was applied before that boot

Together they place the deploy **late on 2026-09-09 UTC**, after the 21:56Z
commit.

**The competing explanation is weak, and worth naming to dismiss.** A collapse
in pass volume (the odds credit cap binds, `decide_sweeps` returns `fire=()`)
would stop *sweeps* — but pre-dedup, `write_fair_price` inserted on the 15s
quote pass too, re-deriving consensus from stored odds. Re-inserting an
unchanged consensus every 15–20s **is** ADR 0133's finding. So a credit cap
would not have stopped inserts in the pre-dedup regime, and cannot explain 2.8%.

**Nothing was moved, and nothing needs to be.** Under a late-09-09 instant the
excluded day would be 09-09 and the windows would be §3's original expectation,
`G_pre = 8` / `G_post = 7` — the fourth row of §4's table, `rho = 0.004595`,
the same verdict. Two further consequences, both conservative:

- The pre window as run **includes** 09-09, which under this reading contains an
  hour or two of deduped operation. That **understates** `R_pre` and therefore
  **overstates** `rho`. The reported figure errs against the dedup.
- The post window as run **excludes** 09-10, which under this reading is a
  legitimate post day. Dropping it costs one cluster and moves `rho` by 2.9%.

**Re-resolving the windows would be an A2 amendment, it would move `rho` by at
most 4.2%, and §6.3 forbids doing it in response to these counts anyway.** It is
recorded here as an open fact about the deploy record, not as a pending
correction to the verdict.

---

## 6. The per-market `rho`s, and §6.3's parts-agree gate

Computed on `('h2h','spreads')` only (§3.4).

| | `R_pre` (rows/day) | `R_post` (rows/day) | `rho` |
|---|---:|---:|---:|
| `h2h` | 353,161.6 | 1,611.3 | **0.004563** |
| `spreads` | 384,308.9 | 1,640.8 | **0.004270** |

**Both fall on the same side of 0.25, so §6.3's SPLIT branch does not fire.**
They **differ from each other by 6.9%** — they do not agree to three decimal
places, and an earlier draft of this document said they did.

No standard error is computed on either, and none may be printed beside them
(§4): the six post-window days share one recorder, one config, one book list,
one odds cadence and one season, and are **not six independent replications**.

---

## 7. The largest day's share

**2026-09-12, 5,492 of 19,513 post-window deciding rows = 28.1%.**

Below the 50% line §4 fixed, so no first-paragraph statement of concentration is
owed. Recorded because §4 requires it beside `rho` whichever way it comes out.

---

## 8. `rho`

    R_pre  =  6,637,234 rows / 9 days  =  737,470.4 rows/day
    R_post =     19,513 rows / 6 days  =    3,252.2 rows/day

    rho = R_post / R_pre ≈ 0.0044          threshold 0.25

The further digits (`0.004410`) are **exact arithmetic on census counts, not
precision**: the generalisation error is unquantified by design (§4), so
quoting `rho` beyond two significant figures asserts nothing.

### The assumption-free version, which is the one worth carrying

A ratio of window means depends on how the days are pooled. These do not:

| post day | deciding rows | vs the pre-window mean | below 0.25 by |
|---|---:|---:|---:|
| 2026-09-11 | 3,792 | 0.00514 | 49x |
| 2026-09-12 | 5,492 | 0.00745 | 34x |
| 2026-09-13 | 2,457 | 0.00333 | 75x |
| 2026-09-14 | 3,496 | 0.00474 | 53x |
| 2026-09-15 | 1,857 | 0.00252 | 99x |
| 2026-09-16 | 2,419 | 0.00328 | 76x |

A 3.0x spread across the post days, and **every single day is at least 34x below
the cut.** Stronger still, the **worst of all 54 day-pairings** — the quietest
pre day (09-01, 505,154) against the busiest post day (09-12, 5,492) — gives
**0.0109, still 23x below 0.25**. That bound needs no pooling, no weighting and
no independence assumption.

**Context, no threshold attached** (§5.2): the `confirmed_ms` gap distribution
and the count of post-window rows with `confirmed_ms IS NOT NULL` were **not
read**. Obtaining them needs a third query, which P4 forbids. **That is a defect
in the registration, recorded here: §5.2 requires printing quantities §9.3's
query set cannot produce.** The conflict was resolved in favour of P4.

---

## 9. The preservation probe

`Q2`, `market = 'h2h'`, the single UTC day **2026-09-13**, fixed in advance by
§5.3. Key = `(link_id, market, outcome_name, outcome_description,
outcome_point)`. Both of §7.1's conditions were tested:

    per row   COALESCE(confirmed_ms, computed_ms) >= computed_ms
    per pair  computed_ms(next) > COALESCE(confirmed_ms, computed_ms)(prev)

> **VIOLATIONS: 0.** `Q2` ran in 18 ms.

**PRESERVATION VIOLATED does not fire.** ADR 0133's non-destructive claim is not
falsified by this probe.

**The probe's power is unquantified, and that matters more than the zero.**

- **The per-row condition is close to unfalsifiable.** `eff_ms` is
  `COALESCE(confirmed_ms, computed_ms)`, so an unconfirmed row satisfies it by
  construction, and `runner.py:1245-1249` writes `confirmed_ms` as the current
  pass's instant while `computed_ms` is frozen
  (`_FAIR_PRICE_FROZEN_COLUMNS`, `runner.py:1092-1094`). It could only fail on a
  confirmation stamped before its own row's freeze.
- **The pair condition is the real test, and its `n` was not returned.** The
  number of adjacent pairs examined is `1,285 − (distinct keys present that
  day)`, which `Q2`'s registered return set (a violation count plus the first
  20) never asked for. **So "0 violations" means no violation was observed among
  an unknown number of pairs.** Obtaining the pair count is an A2 amendment.
  This is a second registration defect: §5.3 specified what to return without
  specifying the denominator that makes it readable.
- **§5.3's stated reason for choosing 09-13 is not established.** It calls it
  "the highest-pass-rate day", and 09-13 is the **second-quietest** of the six
  post days by the only volume measure this look produced (1,285 h2h rows
  against 2,534 on 09-12). Passes were never counted, so the claim is neither
  confirmed nor refuted — but it should not be restated as the probe's
  justification now that 1,285 has been seen.
- **A clean probe does not establish the property globally** (§7.1). One market,
  one day.
- **Rows were selected by `computed_ms` inside the day**, so a key whose previous
  row was written before 2026-09-13 contributes no adjacent pair across the
  boundary.

And the probe tests §7.1's *value series* only. **"Non-destructive" remains true
of the value series and false of the observation series** (§7.5). §7.2, §7.3 and
§7.4 are unaffected: which odds instant a confirmed pass consumed is still gone,
per-pass `oldest_book_age_ms` is still overwritten, and last-value-carried-
forward can still assert a value stood at an instant at which nothing was
observed.

---

## 10. The §6.3 verdict, verbatim

> - **If `rho <= 0.25` AND the parts agree AND the preservation probe is clean
>   AND every precondition is YES** — the verdict is **DEDUP DELIVERING**.
>   §8.1 applies. **That is a verdict about the growth slope and about nothing
>   else**; it authorises no build, no arming, no schema change and no claim
>   about bytes on disk.

All four conjuncts hold: `rho ≈ 0.0044 <= 0.25`; `rho_h2h` and `rho_spreads`
both `<= 0.25`; 0 violations; P1–P5 all YES.

**§8.1's consequence table, applied:**

| | |
|---|---|
| **On screen** | **Nothing.** No screen reads `fair_prices` row counts and none is changed by this. |
| **On the box** | **Nothing.** The 4 GB scale is Joe's decision in #55 and was not conditioned on this result. |
| **Built** | Nothing. No ADR, no migration, no `SCHEMA_VERSION` bump. |
| **Written** | This document; a correction to #55 Amendment 1 replacing the `~2.9 GB` row with the slope figure and the note that the dedup shipped 2026-09-09; the result carried into #58. |
| **Killed** | **`fair_prices` as a growth lever. It is spent. No plan may name it again.** The named residual is `odds_snapshots` — no retention rule, no owner — and naming it is all this document does about it. |

**§11.5's registered a fortiori argument applies** — two of the four changes
inside the post window push `rho` up (NFL season live in post and not in pre;
`totals` keys, on 2 of 6 days). That asymmetry was registered on 2026-09-17,
before the number existed, precisely so this sentence could not be invented
afterwards.

**It does not license the sentence "so the true dedup effect is at least this
strong", which an earlier draft of this document contained.** §11.5 — reproduced
verbatim below — says this measurement does not establish that ADR 0133 caused
whatever `rho` shows, and §12's pass-volume caveat is a confound that points the
other way. "A fortiori" is a claim about the listed confounds, not about the
dedup's true effect.

**The question that reaches Joe is §8.3's PASS branch**, and the ticket it
belongs to already exists: **#58**, whose title is that question.

---

## 11. WHAT THIS DOES NOT ESTABLISH — §11 of the registration, reproduced verbatim

> ### 11.1 It does not establish that a single existing byte was reclaimed
>
> **Zero were.** §B6.3, and §0.1 above. The file was 5.07 GB before ADR 0133 and
> 5.07 GB the instant after. A PASS is a statement about a **slope over a future
> interval** and every sentence quoting it must name the interval.
>
> ### 11.2 It does not establish that the file will stop growing
>
> The non-family term — ~141.0 MB/day at the last measured interval, dominated by
> `odds_snapshots` — is untouched by ADR 0133, has **no retention rule**, is
> "deliberately out of scope rather than forgotten"
> (`backend/store/retention.py:53-55`), and is **not measured here**. A PASS moves
> the growth from 326.6 to ~141 MB/day. It does not move it to zero, and 141
> MB/day alone exhausts the 4 GB box's residency advantage in about two weeks
> (§1.2).
>
> ### 11.3 It does not establish that the 4 GB box is sufficient
>
> §1.2 establishes the opposite, by arithmetic, before the box is bought: no
> achievable value of `rho` buys a billing month of >=50% residency. The box is a
> stopgap of weeks.
>
> ### 11.4 It does not establish that residency is what binds the 74.8 s query
>
> #55 Amendment 1's own caveat, reproduced because it is the one most likely to be
> dropped: the 74.8 s query was `ladder_candidates`, **not** a `fair_prices` read.
> Shrinking `fair_prices` growth frees cache *for* it; that mechanism is
> **plausible rather than demonstrated**. Relax residency and the plan, IOPS or
> the 25 s ceiling itself may bind. Nothing here tests that, and a PASS is not
> evidence that the 503 stops.
>
> ### 11.5 It does not establish that ADR 0133 caused whatever `rho` shows — and the asymmetry is registered
>
> Four things moved inside the post window besides the dedup:
>
> | change | date | direction on `rho` |
> |---|---|---|
> | `totals` markets bought (ADR 0152) | 2026-09-14 | **up** (new keys) — excluded from `rho` by §3.4, but props/rungs interact |
> | NFL regular season live; not live in the pre window | from ~09-10 | **up** (more fixtures, more keys) |
> | ten named books replace regions (ADR 0155) | 2026-09-15 | **either** — a changed `books_used` payload forces inserts |
> | `idx_fair_market_confirmed` (v37) | 2026-09-10 | none on a **row** count; would matter for a byte count |
>
> **Two push `rho` up, so a PASS is a fortiori. A FAIL is NOT.** A FAIL is
> consistent with "the dedup works and the book list churned", and §8.2 therefore
> forbids a revert and fixes the five hypotheses in order. **This asymmetry is
> registered now because a FAIL write-up would otherwise be free to pick the
> flattering attribution.**
>
> ### 11.6 It does not run §B7's successor, and that is a refusal with a reason
>
> §B7 asked for a registered measurement of the duplication **rate** — correctly
> keyed, multiple days, at least one NFL Sunday. **Post-deploy that is impossible**
> (§0.2). **Pre-deploy it is possible and pointless**: the decision it would have
> authorised was taken on 2026-09-09, so running it now is an audit of a shipped
> change, it authorises nothing, and it costs a full window-function scan over
> millions of pre-deploy rows — the exact read §9.4 declines. **Stated as a
> refusal rather than left as an omission**, so a later session does not read this
> document as having forgotten it.
>
> ### 11.7 It does not establish anything about props
>
> Excluded by §3.4 on a query-plan ground. The prop arm of the ladder may
> duplicate at a completely different rate and nothing here would see it.
>
> ### 11.8 It does not establish the duplication rate on any particular day
>
> `rho` is a ratio of two window means over `G_pre = 8` and `G_post = 7` days that
> are **not independent replications** (§4). The per-day series is printed, but no
> day carries a verdict, and no standard error exists for any of them.
>
> ### 11.9 Its byte context is not measured and decays
>
> No `dbstat` read is taken (§9.4). Every byte figure in this document comes from
> the two dated reads of §B2.1 — 2026-09-01T16:40Z and 2026-09-09T19:49Z — and
> the second is already eight days old. **Re-run `scripts/inspect_live_db.py
> db-sizes` before quoting a family or file size**, and note that it is itself a
> full-file walk that belongs in its own run window. The `~3.5 GB cache on a 4 GB
> box` figure is inherited from #55 Amendment 1 and is **unverified**; if it is
> wrong the residency table in §1.2 moves, but §6.2(3) means the threshold does
> not.

**Two things in that block are contradicted by this document and are flagged
rather than edited** (§12 of the registration: pre-fix text stays readable as
what was actually registered).

1. **§11.8's `G_pre = 8` and `G_post = 7`.** Amendment 1 resolved them to
   **9 and 6**; §2 above carries the correct figures. Everything §11.8 asserts —
   not independent replications, no day carries a verdict, no standard error
   exists — is unaffected by which two integers they are.
2. **§11.1's "a slope over a future interval."** This document's own header says
   "over two named past windows", and §12's first bullet says the six post days
   may not represent a later six. The past-window reading is the correct one;
   §11.1's wording claims more than the design supports.

---

## 12. Three things this document adds to §11's list

None could have been drafted in advance: each is a property of how the look
actually ran.

### 12.1 The denominator was never measured, so this is NOT the duplication rate

`rho` is a ratio of **insert** rates, and inserts = passes x (1 − suppression):

    rho = (inserts_post / passes_post) x (passes_post / passes_pre)

`rho` equals the suppression complement **only if post-window pass volume
matched pre-window pass volume.** §11.5 lists no entry for pass volume, and
nothing in this look counted passes. §5 above is direct evidence that this
recorder's insert volume can sit at ~2.8% of its daily mean for hours. The
instruments that would separate the two explanations —
`scripts/inspect_live_db.py credits-day` and `sweep-log`, or an
`odds_snapshots` / `api_credits` per-day count — were correctly **not** run
under P4, and running one is an A2 amendment.

**Direction and magnitude.** If post-window passes fell, `rho` is too low and
the dedup's share of the fall is overstated. For `rho <= 0.25` to be a **false**
pass, post-window pass volume would have to be **<= 1.76%** of pre-window
volume, sustained across six days on which the recorder demonstrably inserted
1,857–5,492 rows every single day with an hourly cadence floor running. That is
not a live possibility, and the bound is worth more than leaving the assumption
unstated — but it is a bound on the *verdict*, not on the point estimate, and
the point estimate is not a suppression rate.

### 12.2 It says nothing about a later six days

`G_post = 6` is the floor exactly, and the window is not internally homogeneous:
the last two days are the only two containing `totals` at all and the only two
after ADR 0155 changed the book list. A seventh day would have been a different
mix again.

### 12.3 It establishes nothing about the ~1,700 `totals` rows

Printed as context, no pre-window denominator, excluded from `rho` before any
count existed. A reader must not infer from their smallness that `totals` dedups
at the same rate: **two days is not a series.**

---

## 13. What this look cost

`Q1` **16,159 ms**, `Q2` **18 ms**, on the live box, inside the registered
window. Recorded as bare protocol facts beside §9.2's snapshot instant.

**They support no inference and none is drawn here.** An earlier draft used them
to compare against `API_READ_BUDGET_MS`, to claim the plan lesson of ADR 0141,
and to assert a counterfactual pre-dedup cost — all on `n = 1`, on a quantity
the registration never registered, and against a cache state that was disturbed
in both directions by unrecorded amounts: 48 live route requests at ~08:06Z
(`scratchpad/timing.txt`), four minutes before `Q1`, and a `dbstat` walk of the
whole file earlier the same day whose remote process was never confirmed dead
(§0). A wall time taken under those conditions measures the conditions.

---

## 14. Audit trail

Drafted from the look's own output, then audited by the `measurement-skeptic`
agent before commit, per CLAUDE.md's rule that the audit is owed *especially*
when a result is good news. The audit reproduced all nine reported figures
independently from the raw output and returned eight blockers, every one of
which is resolved above: the §0 blindness disclosure, the §0 §8.3 deviation, the
§5 rewrite, the removal of the "true dedup effect" and "lands on ~0.004"
sentences, §9's probe-power statement, §13's deleted inferences, §6's corrected
agreement claim, and §12.1's pass-volume caveat.

**One of its findings was itself corrected here rather than adopted.** The audit
read the excluded day as showing that insert volume over 00:00–04:36Z was near
zero, and offered the odds credit cap as the mechanism. §5 shows that mechanism
cannot work in the pre-dedup regime — the 15s quote pass inserted from stored
odds — and supplies a better-evidenced account, including the `v36 -> v37` boot
log that places the deploy late on 09-09. The audit's arithmetic was right; its
explanation was not.

The raw output, the pre-run parameter file, the exact statements and the
reduction arithmetic were kept in the session scratchpad and are reproduced in
full in §1–§9. Nothing in this document is taken from an agent's report without
re-derivation.
