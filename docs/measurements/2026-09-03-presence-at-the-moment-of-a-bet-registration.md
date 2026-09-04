# PRE-REGISTRATION — is the desk present at the moment Joe actually bets?

**Written 2026-09-03, before any `fills` row has been read.** At the time of
writing no query has been run against the live `fills` table for this question,
by this agent or any other in this session, and the window this document fixes
does not close until **2026-09-04T00:00:00Z**. Every threshold, every band
edge, the unit, the exclusions, the stopping rule and the decision rule are
fixed below so that none of them can be chosen after the answer is visible.

It exists because ADR 0071 §2.2 makes a claim about a *moment* — *"the tool's
job at the moment of a bet is price transparency"* — and nothing in this repo
has ever checked that the tool is at that moment. The partner's hypothesis,
handed to this registration, is that it is not: Joe bets in the Kalshi app and
glances at the desk separately, and the two events do not coincide. Funding
work on "the moment of a bet" before measuring it would be building on a
sentence.

**This is not a signal measurement and it enters no signal record.** It is an
operator-behaviour reading with `n = 1 operator`, in the same class as
`2026-09-02-visit-freshness-first-read.md` and
`2026-09-03-desk-dwell-and-the-watcher-off-switch.md`. It has nothing to do
with `beta`, the gate, the 0.63-point cost headroom, or the 52.00%/51.75%
break-even bar, and no verdict here may be quoted in a sentence about edge.
The measurement rules in CLAUDE.md apply to it in full anyway, because the
failure modes they exist to catch — an inflated `n`, a bucket edge chosen
afterwards, a pooled number hiding one contributor — are not specific to
prices.

---

## 0. THE POWER CHECK, WHICH COMES BEFORE EVERYTHING ELSE

**Can this measurement answer this question at the `n` available?** For the
question as the partner asked it — is the desk *absent* — yes, decisively, at
a sample size that is plausibly already in the record. For the middle case, no,
and the sample size that would buy the middle is computed here rather than
discovered after the run.

### 0.1 The planning value for `n`, and why the fill count is the wrong one

The only committed figure on the rate of hand betting is
`2026-08-18-hand-fill-fee-calibration-result.md`: **25 fills, all taker, all
buys, `created_time` 2026-08-10..17** — eight days, ~3.1 fills/day.

**That is not 25 observations and this is the whole design problem.** The same
document records that *"10 of the 12 are UFC fills placed in one sitting
(2026-08-16, 01:00–03:22Z)"*. One evening supplied 40% of the record. A
measurement that counted fills would be the `clv-coverage` defect again — the
gate that counted 400 rows on one ticker as 400 observations, fixed by
clustering per game. **The unit here is the sitting (§3), not the fill.**

Planning value, stated as a band rather than a point because the observed
clustering ratio is 25 fills across an unknown number of sittings with at
least one sitting of 10:

    hand fills, pre-window rate      ~3.1 / day
    fills per sitting, observed      >= 2.1 (25 fills, one sitting of 10)
    planning sittings per day        1.0 - 1.5
    window length at the §8 close    ~10 days (first heartbeat -> 2026-09-04T00Z)
    PLANNING S                       10 - 15 sittings

`S` is genuinely unknown to the author of this document and the design does not
depend on guessing it right: §7 makes the instrument **refuse to compute the
decision statistic at all** below the registered floor, so a shortfall produces
a refusal rather than a number.

### 0.2 The floor, which is arithmetic and not a preference

The gap arm (§6) rejects "the desk is present at half the bets or more" by an
exact one-sided binomial lower tail against `p = 0.5` at `alpha = 0.005`.

    S = 6   no critical value exists.  0 of 6 gives p = 0.0156 > 0.005.
    S = 8   k* = 0.  P(K = 0 | 8, 0.5) = 0.0039.  DECLARABLE.

**`S_min = 8` is where the arm becomes declarable at all.** Below it the
measurement cannot return its own primary verdict however the data fall, so
running the statistic there would return a number with no threshold it could
cross — the shape ADR 0016 refuses.

A second floor, on days rather than sittings, is registered in §3.3 for the
independence reason: eight sittings in one evening are not eight draws.

### 0.3 The detectable effect, stated before committing

`theta` is the chance-coverage rate — the share of the permutation null's
draws that land desk-present (§5.2). It is not known in advance; the table
therefore runs across the plausible range. `k*` is the smallest count that
declares at `alpha = 0.005`.

**Presence arm — can we show the desk IS there more than chance?**

| S | theta | k* | power @ p=0.8 | power @ p=0.5 | power @ p=0.3 |
|---|---|---|---|---|---|
| 8 | 0.08 | 4 | 0.990 | 0.637 | 0.194 |
| 8 | 0.15 | 5 | 0.944 | 0.363 | 0.058 |
| 8 | 0.25 | 6 | 0.797 | 0.145 | 0.011 |
| 15 | 0.15 | 7 | 0.999 | 0.696 | 0.131 |
| 25 | 0.15 | 10 | 1.000 | 0.885 | 0.189 |
| 25 | 0.25 | 13 | 1.000 | 0.500 | 0.017 |

**Gap arm — can we show the desk is NOT there?**

| S | k* | actual alpha | power @ p=0.0 | power @ p=0.1 | power @ p=0.2 | power @ p=0.3 |
|---|---|---|---|---|---|---|
| 8 | 0 | 0.0039 | 1.000 | 0.430 | 0.168 | 0.058 |
| 12 | 1 | 0.0032 | 1.000 | 0.659 | 0.275 | 0.085 |
| 15 | 2 | 0.0037 | 1.000 | 0.816 | 0.398 | 0.127 |
| 25 | 5 | 0.0020 | 1.000 | 0.967 | 0.617 | 0.193 |

**Read across the rows, which is the step ADR 0021's power check printed and
nobody took.** At `S = 8` this design resolves two things and not a third:

- **"The desk is essentially never there" (`p ≈ 0`): power 1.000.** This is
  the partner's hypothesis as stated, and the design is powered against
  exactly it.
- **"The desk is almost always there" (`p ≈ 0.8`): power 0.80–0.99**
  depending on `theta`.
- **"The desk is there about half the time" (`p ≈ 0.5`): power 0.15–0.64.**
  It returns UNRESOLVED most of the time, and an UNRESOLVED here must never
  be read as "the gap is real".

**The middle is the most likely truth for a behavioural variable, and it costs
about 25 sittings** — roughly three weeks at the planning rate — to reach 0.885
power against `p = 0.5` on the presence arm and 0.617 against `p = 0.2` on the
gap arm. **That is a separate registration and is not authorised here.** It is
written down so the number is not discovered after the time is spent.

### 0.4 Why this is READY and not UNDERPOWERED, said against interest

CLAUDE.md's standing calibration — *"a design that can only resolve effects
larger than a point is not measuring the thing this project exists to
measure"* — is about the 0.38–0.63 points of cost headroom, and it does not
transfer. The quantity here is a behavioural share, and both edges of it are
decision-bearing: "the desk is at ~0% of his bets" and "the desk is at ~80% of
his bets" imply opposite roadmaps (§10). There is no fee bar this has to clear.

**What would make this UNDERPOWERED is a small `S`, not a small effect**, and
§7's structural refusal converts that case into a refusal rather than a
flattering number.

---

## 1. The claim under test, as something that can come back false

**H1 (gap arm), one-sided:** among Joe's hand-bet sittings on Kalshi inside
the window, the share whose first fill is **desk-present** (§4) is **below**
0.5.

**H2 (presence arm), one-sided:** that same share is **above** what the
day-shift permutation null of §5.2 produces by chance.

Both directions are declared here. Neither may be computed two-sided and
reported one-sided, or the reverse.

**The two arms do different jobs and the bias makes them unequal.** §9.1's
bias — a backgrounded tab stamps nothing — runs toward reading a bet as
desk-absent. So **H1 clearing is weak evidence** (it is what the instrument's
own blindness predicts anyway) and **H2 clearing is strong evidence** (it
survives a bias pushing the other way). Any write-up that treats them as
symmetric is wrong.

### 1.1 Weakened quantifiers, on purpose

Five sentences that would otherwise be universals, corrected at registration
time where it costs nothing rather than at audit time where it costs the
finding:

- Not *"Joe never bets through the desk"* — `manual_orders` held 0 rows at the
  2026-09-02 `manual-orders-audit` census, which is a fact about eight days,
  not a property. §2.4's exclusion exists precisely because a non-zero count is
  possible, and if it excludes nothing that is a reported result.
- Not *"a backgrounded tab always reads as absent"* — `Nav.tsx:251` registers a
  `visibilitychange` listener that stamps immediately on return, so a tab
  brought back inside the halo reads as present.
- Not *"every hand fill is a bet decided at that instant"* — a resting (maker)
  order fills when the market comes to it, hours after the decision. §2.3
  restricts the primary to taker fills for that reason.
- Not *"`fills` is the record of Joe's bets"* — it is the record of his bets
  **on Kalshi**, mirrored through a poller that can miss (§9.6). ADR 0078
  exists because he also bets at sportsbooks, and those are invisible here.
- Not *"`desk_attention` measures looking"* — it is `(id, seen_ms)` and cannot
  separate a reader from a tab left open, which is the caveat CLAUDE.md already
  carries and which one 2.6-hour "visit" on 20260902 demonstrates.

---

## 2. The population, and the exclusions

### 2.1 Where the window starts, and why the boundary lives in the database

    W_start = MIN(seen_ms) FROM desk_attention

`desk_attention` was created by schema v21 in commit `49f1f43`
(2026-08-25T15:08:36Z), so no heartbeat can predate it and the first row is a
durable, in-database instrument marker. `W_start` does **not** depend on a
guessed deploy date or on a Fly release timestamp.

**Every hand fill before `W_start` is UNCLASSIFIABLE, not absent.** There was
no instrument. Those fills are counted and reported as an `UNCLASSIFIABLE`
class; they enter no arm and produce no verdict. The pre-window record — the
25 fills of 2026-08-10..17 — is planning input for §0 only.

### 2.2 Where it ends

    W_end = 2026-09-04T00:00:00Z    (1788652800000)

Fixed here. **No read of the fills population may be taken before `W_end`**,
because a read on a half-open window is a read whose length was chosen by the
analyst. See §8 for the one registered extension and its trigger.

### 2.3 Which fills count

Rows of `fills` with:

    source     = 'venue_hand'
    is_taker   = 1
    filled_ms >= W_start
    filled_ms <  W_end

Exclusions, each with the reason it is independent of the outcome:

| rule | why it does not reference the distance-to-visit |
|---|---|
| `source = 'engine'` | a different population; the order path, not a person. `ORDERS_ARE_DRY_RUNS = True` so it should be empty, and its count is reported either way. |
| `is_taker = 0` | for a **maker** fill the fill instant is not the decision instant, so its timestamp does not answer the question asked. References the order type, never the timing. |
| `filled_ms < W_start` | no instrument existed. §2.1. |
| `filled_ms >= W_end` | outside the registered window. §2.2. |
| joins a desk-placed order | §2.4. References the order path, never the timing. |

**No exclusion on ticker, series, sport, price, size, fee, outcome, or
settlement.** Naming these is not padding: an exclusion on ticker would let
`KXMVE` combos be dropped after they were seen to fall the wrong way, and an
exclusion on size would let "he was only messing about" be applied to the
inconvenient sittings.

**Expected to be near-empty, and reported as a result either way:** the
2026-08-10..17 capture was *"25 fills (all taker, all buys)"*, so the
`is_taker = 0` rule is expected to remove few or none. If maker fills are
present they get their own descriptive distance table (§5.4) and **no
verdict**.

### 2.4 The circularity exclusion, and the refusal that may go with it

A fill caused by an order **the desk itself placed** is desk-present by
construction and would make the measurement a tautology. Two live paths exist:

- `manual_orders` — `MANUAL_ORDERS_ARE_DRY_RUNS = False` since 2026-08-26.
- `combo_orders` — `COMBO_ORDERS_ARE_DRY_RUNS = False`
  (`backend/store/combo_orders.py:79`). **The partner's design did not name
  this path.** The desk places real resting bids on minted `KXMVE`
  combinations, and a fill on one arrives in `fills` tagged `venue_hand` like
  any other, because `portfolio_poll.py` tags everything it mirrors that way.

**Rule:** a fill whose `fills.venue_order_id` equals a
`manual_orders.kalshi_order_id` or a `combo_orders.kalshi_order_id` is
excluded, and the excluded count is reported.

**Two refusals attach to this rule, both fixed now:**

- `venue_order_id` is NULL on pre-v18 rows and on any fill whose payload
  omitted it. A NULL cannot be matched. Such fills are **kept** — refusing a
  real fill over a missing join key is the wrong way round, the same argument
  `fills`' own schema comment makes — and their count is reported as an
  `UNJOINABLE` class bounding the residual contamination. That contamination
  biases toward **refuting** the gap (§9.3).
- If `manual_orders` or non-dry-run `combo_orders` carry rows in the window
  and the inspector cannot emit their `kalshi_order_id`s, the exclusion cannot
  be executed and the verdict is **UNRESOLVED — EXCLUSION UNEXECUTABLE**. It
  is not silently skipped.

**This is the live specimen this project already has one of**, and it is
registered in the same shape: a combo experiment pre-registered an exclusion
and correctly refused to activate it when the sample was too thin. Here the
rule is expected to exclude **zero** rows, because `manual_orders` had 0 rows
lifetime at the 2026-09-02 census. If it excludes any, that is itself a
finding and is reported before any verdict.

---

## 3. The unit — the sitting, not the fill

### 3.1 The definition, so two people get the same integer

    SITTING_GAP_MS = 3_600_000    (60 minutes)

A **sitting** is a maximal run of in-population fills with no gap over
`SITTING_GAP_MS` between consecutive `filled_ms`. A sitting's timestamp for
every test is its **first fill's `filled_ms`** — the instant the sitting's
first bet was struck, which is the "moment of a bet" ADR 0071 names.

**Why 60 minutes, argued from something rather than chosen:** it is longer
than the ~15-minute mean inter-fill spacing of the one documented multi-fill
sitting (10 UFC fills over 2 h 22 m on 2026-08-16) so that sitting does not
shatter into ten "moments", and it is the desk's own hourly floor cadence,
which is the coarsest clock anything in this system runs on.

**Reported beside it and forbidden from carrying any verdict:** the sitting
count at 30 minutes and at 120 minutes. That is a sensitivity display. The
primary is 60 and does not move.

### 3.2 Why the fill is the wrong unit, said plainly

One sitting supplied 10 of 25 fills in the only capture this repo has. Counting
fills would put 40% of the weight on one evening and report `n = 25` for what
is closer to `n = 8`. This is the same defect as the 400-rows-on-one-ticker
gate and as `G = 311` being 4.26 effective clusters, and it is the single most
common place `n` gets inflated after the fact.

### 3.3 The clustering variable, and the second floor

**Sittings inside one budget day are not independent draws** — same evening,
same slate, same browser tab state, one mood. The clustering variable is the
**budget day** (10:00Z boundary, as `credits-day` defines it).

Three consequences, all registered:

- `D` = the number of distinct budget days carrying at least one sitting is
  reported beside `S`, always.
- **`D_min = 5`.** Below it the verdict is **UNRESOLVED — TOO FEW DAYS**,
  whatever `S` is.
- **Leave-one-day-out is required, not optional.** The verdict is recomputed
  with the largest-contributing budget day dropped. **If the verdict flips, it
  is downgraded to UNRESOLVED — CONCENTRATION.** The largest day's share of
  sittings is printed beside every pooled figure, per CLAUDE.md's rule that a
  pooled number is not a finding until the parts agree.

---

## 4. The cut — the band edges, fixed in advance

A sitting is **desk-present at band `B`** if its first fill's `filled_ms` lies
within `[visit.start_ms - B, visit.end_ms + B]` for at least one visit, where
visits are `desk_attention` heartbeats clustered by `inspect_live_db.py
visit-freshness` at its own `--gap-ms` default.

    PRIMARY    B5  = 300_000 ms    (+/- 5 minutes)
    SECONDARY  B30 = 1_800_000 ms  (+/- 30 minutes)

**`B5 = 300,000` is `DEFAULT_ATTENTION_TTL_MS`** (`backend/odds/attention.py:60`)
— the backend's own definition of how long the desk stays open after a stamp,
and the same constant `_cluster_visits` uses to end a visit. Within it, the
deployed loop itself still judged the desk attended. The edge is taken from
code, not from convenience.

**`B30` exists for one named mechanism and not as a second bite.** The
heartbeat only fires while `document.visibilityState === "visible"`
(`Nav.tsx:246`). A phone user who reads the desk and then switches to the
Kalshi app stops stamping at the switch, so a bet placed after a deliberate
app switch can sit tens of minutes past the last heartbeat while being exactly
the case ADR 0071 describes as success. `B30` is that case. It is **secondary**
and may qualify the primary, never overturn it.

**Descriptive only, no verdict, no threshold:** the raw minutes from each
sitting to the nearest visit interval, and the counts at 0 (strictly inside a
visit), ≤5, ≤30, ≤60, ≤180 and >180 minutes. Printing the whole distribution is
what stops a future reader inventing a band; attaching a verdict to any of
these edges is forbidden.

**Bucket on the thing transacted, not a convenient proxy.** The repo's rule is
about asks and mids; its transferable form is that the bucketing variable must
be the quantity the claim is about. Here the claim is about a *moment*, so the
bucketing variable is a **time distance**, and the timestamp used is the
venue's own fill time — never `settled_ms`, never `position_first_seen_ms`,
never the poll instant, all of which are recorded after the fact and have
already converged on the outcome in the sense CLAUDE.md warns about.

---

## 5. The statistic, named as an estimator

### 5.1 What is being estimated

**A proportion**: `p` = the share of independent sittings that are desk-present
at band `B`. `K` sittings of `S`. Not a mean, not a difference of paired
proportions, not a game-clustered mean. `sqrt(p(1-p)/n)` is the default that
comes to mind and it is **not used**, because `S` is expected in the single or
low double digits and CLAUDE.md requires ≥5 expected outcomes on each side
before a normal approximation may speak. **Exact binomial tails throughout.**

### 5.2 The null for the presence arm, which is not "50/50"

Testing `p` against a fixed constant would be meaningless here: some of the
time Joe has the desk open anyway, so a bet lands inside a visit by
coincidence at a rate set by how much he browses.

**Primary null: an independent per-sitting day-shift permutation.** For each
sitting, draw an integer `d` uniformly from the admissible shift set

    Adm = { d in {-14..-1, 1..14} : first_fill_ms + d*86_400_000 in [W_start, W_end) }

apply it, and recompute `K` against the **unshifted** visit intervals.
**10,000 draws, `random.Random(20260903)`.**

    p_perm = (1 + #{draws with K* >= K_obs}) / 10001

Whole-day shifts hold **hour of day** fixed, which is the confound that
matters: both betting and desk-opening concentrate in evening game hours, and a
naive wall-clock null would credit that coincidence as presence.

**Refusal:** if any sitting has `|Adm| < 4`, the permutation is not computed,
the presence arm reports **UNRESOLVED — PERMUTATION INFEASIBLE**, and only
the descriptive statistic below is printed.

**Reported beside it, descriptive only:** `theta_wall` = the halo-dilated
attended share of wall clock over the window, and the exact binomial tail
`P(K >= K_obs | S, theta_wall)`. This is a sanity check on the permutation and
**carries no verdict**, because it ignores the hour-of-day confound in the
direction that flatters presence (§9.4).

### 5.3 The null for the gap arm

`H0: p >= 0.5`, rejected by the exact one-sided lower binomial tail
`P(K <= K_obs | S, 0.5)`.

**0.5 is fixed here and argued:** ADR 0071 §2.2 states the tool's job *at the
moment of a bet*. A tool that is at fewer than half of the moments it names as
its job is not doing that job. It is a threshold on the product claim, not on a
statistical convention, and it is set before any count exists.

### 5.4 What is reported and never tested

- The distance distribution of §4.
- The maker-fill subset's distance table.
- Sittings per budget day, and the largest day's share of `S`.
- Fills per sitting, and the largest sitting's share of fills.
- `S` at `SITTING_GAP_MS` of 30 and 120 minutes.
- The share of sittings with **any** fill desk-present, beside the primary's
  first-fill rule.
- The counts of every refused/excluded class: `UNCLASSIFIABLE` (pre-`W_start`),
  `UNJOINABLE` (NULL `venue_order_id`), engine fills, maker fills, and fills
  excluded by §2.4.

---

## 6. The decision rule, with the multiplicity already counted

### 6.1 The tests, counted

**Four.** Gap arm and presence arm, each at `B5` and at `B30`. Family-wise
alpha **0.02**; Bonferroni gives **alpha = 0.005 per test**. Under pure noise
at four tests and 0.005 each, the expected number of false findings is
**0.02**.

This matters here more than the arithmetic suggests: this repo has already
produced a 20-point "finding" from data generated with no edge in it, and ten
cells at two standard errors give about 0.46 false findings by chance. Four
cells at 0.005 give 0.02.

**§7's preconditions are refusals, not tests.** A precondition can only turn a
verdict into UNRESOLVED; it can never manufacture one, so it adds nothing to
the multiplicity count.

### 6.2 The record is looked at ONCE, and the instrument enforces it

**This is not an accumulating record checked repeatedly.** A threshold
re-evaluated on every request against a growing database is not one look but
thousands, and under a true zero it crosses eventually with probability 1 —
measured in this repo at 13.7%, and that is a floor. That failure is removed
here by construction rather than by an always-valid boundary:

- The window closes at a fixed instant (§2.2) and no read may precede it.
- **The analyzer must refuse to compute or print `K`, any band count, any
  distance, or any p-value when `S < S_min` or `D < D_min`**, printing
  `SAMPLE NOT REACHED: S = <n> of 8, D = <d> of 5` instead. This is the same
  structural refusal `forward-lock` uses for `E*`.
- §8's one extension is triggered **only** by `S` and `D`, never by `K`. So at
  most one computation of the decision statistic ever occurs, and the per-test
  alpha is not inflated by the extension.

### 6.3 THE DECISION RULE, VERBATIM

> **Let `W_start = MIN(seen_ms) FROM desk_attention` and
> `W_end = 2026-09-04T00:00:00Z`. Let the population be rows of `fills` with
> `source = 'venue_hand'`, `is_taker = 1`, `filled_ms` in `[W_start, W_end)`,
> excluding any row whose `venue_order_id` matches a
> `manual_orders.kalshi_order_id` or a `combo_orders.kalshi_order_id`. Let a
> SITTING be a maximal run of those fills with no gap over 3,600,000 ms, timed
> at its first fill. Let `S` be the number of sittings and `D` the number of
> distinct budget days (10:00Z boundary) carrying one. Let `K5` be the number
> of sittings whose first fill lies within 300,000 ms of some
> `desk_attention` visit interval, and `K30` the same at 1,800,000 ms. Let
> `p_perm` be the one-sided permutation p-value of §5.2 and `p_gap` the exact
> binomial `P(K <= K_obs | S, 0.5)`.**
>
> **UNRESOLVED — TOO FEW SITTINGS** if `S < 8`. **UNRESOLVED — TOO FEW DAYS**
> if `D < 5`. In either case no count, distance or p-value may be computed,
> printed or quoted, and `S` and `D` are recorded so the next look starts from
> a number.
>
> **PRESENCE GAP SUPPORTED — the desk is not at the moment of a bet** if
> `S >= 8`, `D >= 5`, and `p_gap <= 0.005` at `B5`. **This verdict is WEAK by
> construction** (§9.1) and every sentence quoting it must say so.
>
> **PRESENCE GAP REFUTED — the desk is at the moment of a bet** if `S >= 8`,
> `D >= 5`, and `p_perm <= 0.005` at `B5`. **This verdict is STRONG by
> construction**, because the instrument's blindness pushes the other way.
>
> **PARTIAL PRESENCE** if both fire at `B5`: the desk is present more often
> than chance and at fewer than half of sittings. This is a real state, not a
> contradiction, and it is named here so it cannot be reported as whichever of
> the two suits the reader.
>
> **UNRESOLVED** in every other case, including `S >= 8` and `D >= 5` with
> neither arm clearing, and any failed precondition — in which case the verdict
> is reported as **UNRESOLVED — <name of the failed precondition>** and is
> never shortened to UNRESOLVED alone.
>
> **Any verdict is DOWNGRADED to UNRESOLVED — CONCENTRATION if it flips when
> the largest-contributing budget day is dropped.**
>
> **The `B30` arm may qualify a verdict and may never produce one on its own.**
> Its two p-values are reported at the same 0.005 threshold and their only
> licensed use is the sentence "the primary verdict does / does not survive a
> 30-minute halo."

### 6.4 What falsifies the partner's hypothesis

**`K5 >= k*` at `S`, with `p_perm <= 0.005`** — the desk is open at his bets
more often than a day-shifted version of his own browsing would produce. At
`S = 8` and `theta = 0.15` that is **5 of 8 sittings**. It would mean the
premise behind funding "get the desk to the moment of a bet" is false, and the
open question becomes what the desk *says* at that moment, which is a different
project.

---

## 7. Preconditions — refusals that block a verdict

**C1 — `S >= 8` and `D >= 5`.** §0.2, §3.3. Structural: the analyzer computes
nothing else below them.

**C2 — the visit table spans the window.** `visit-freshness` must be run with
an explicit `--since` at or before `W_start`'s budget day. **Its `--since`
defaults to the last 7 days**, which would silently truncate a 10-day window
and read pre-truncation fills as desk-absent. A run without an explicit
`--since` is not admissible evidence.

**C3 — no section truncated.** `_fetch` binds `LIMIT effective + 1` and sets
`truncated`; `--limit` defaults to 2000. Every section used must report
`truncated = false`. A truncated fills section is a population cut by a row
cap.

**C4 — the exclusion is executable.** §2.4. If `manual_orders` or non-dry-run
`combo_orders` carry window rows whose `kalshi_order_id` cannot be read, the
verdict is UNRESOLVED — EXCLUSION UNEXECUTABLE.

**C5 — fills-poll coverage, reported as a floor.** `poll_fills` calls
`client.fills(limit=200)` on a ~5-minute cadence with `INSERT OR IGNORE` and
no cursor, so completeness holds unless more than 200 fills accumulated between
two successful polls. `poll_log WHERE endpoint = 'fills'` is the instrument for
this and **no existing subcommand emits it** (§11). If it cannot be read, the
population is declared a **FLOOR** in the write-up and the verdict may still be
declared, with §9.6's direction of bias stated beside it. `parse_fill`
refusals are logged only as warnings and are durably counted nowhere, so the
floor is a floor for that reason too.

**C6 — the clock-skew assumption is stated, not assumed silently.**
`fills.filled_ms` comes from Kalshi's `created_time`
(`portfolio_poll.py:207`); `desk_attention.seen_ms` is written from the Fly
machine's own clock (`routes.py:3964`, *"the time is the server's, never the
caller's"*). These are two clocks and no measurement of their offset exists in
this repo. **The registered assumption is `|skew| <= 60 s`**, one heartbeat
interval. The primary band is 300 s, so the primary verdict flips only if skew
exceeds five minutes. The write-up must state this and must report how many
sittings sit within 60 s of a band edge — if any verdict depends on those, it
is downgraded to UNRESOLVED — SKEW-SENSITIVE.

---

## 8. The stopping rule

**Primary close: `W_end = 2026-09-04T00:00:00Z`.** Fixed. The look is taken on
or after that instant and not before.

**One extension, triggered only by sample size.** If the primary look returns
`S < 8` or `D < 5`, the window extends **once** to
**`W_end' = 2026-09-18T00:00:00Z`** and the look is retaken. The trigger
references `S` and `D` only; **`K` is not computed at the primary look in that
branch**, so no statistic is seen before the extension is decided.

**Terminal.** If the backstop look also returns `S < 8` or `D < 5`, the verdict
is **UNRESOLVED — TOO FEW SITTINGS (TERMINAL)**, the question is closed rather
than extended again, and `S` and `D` are recorded. "When we have enough" would
mean "when it looks good"; two fixed dates and a stop is the whole of the rule.

**Amendment trigger.** If `DEFAULT_ATTENTION_TTL_MS`, `HEARTBEAT_INTERVAL_MS`,
`MANUAL_ORDERS_ARE_DRY_RUNS` or `COMBO_ORDERS_ARE_DRY_RUNS` changes before the
look, the affected band or exclusion is recomputed and the amendment is written
into this file, dated, **before** the look is taken.

**Re-check §10 blind, immediately before the look.** It is the section least
protected by pre-registration and the one most likely to have decayed — the
lesson Amendment 1 of the forward-lock registration wrote down.

---

## 9. What this cannot establish

Drafted before the run, and each line checked against code or schema rather
than written as modesty. A caveat list written afterwards is selected to be
survivable.

1. **Causation, in either direction.** "He opened the desk because he was about
   to bet" and "he happened to be looking" produce identical rows. Presence is
   co-occurrence.

2. **Whether he would have used the desk had it been present.** The 8 days
   `manual_orders` has been armed with 0 rows is evidence about a button, not
   about a counterfactual.

3. **A tab from a reader.** `desk_attention` is `(id, seen_ms)` and nothing
   else. A page left visible on a second monitor stamps exactly like a page
   being read; one 2.6-hour "visit" carries most of budget day 20260902.
   Adding a session column would be a claim about a future that does not exist
   (`attention.py`'s own note).

4. **Bets placed anywhere but Kalshi.** ADR 0078 exists *because* Joe places
   sportsbook parlays, and `fills` cannot see one. Even PRESENCE GAP REFUTED
   says nothing about the off-venue half of his betting, and no verdict here
   may be written as a statement about "his bets" without that qualifier.

5. **Entries from exits.** Kalshi's fill payload carries an action; the `fills`
   schema does not, so a closing sale is indistinguishable from an opening buy.
   The population mixes them and cannot be split.

6. **Fills the poller never saw.** `poll_fills` reads the newest 200 with no
   cursor; a longer outage with more than 200 intervening fills loses rows
   permanently, and `parse_fill` refusals are counted nowhere durable. The
   population is a **floor**. Direction: during a whole-instance outage the
   fill is usually recovered on the next poll while the heartbeats are lost
   outright, so an outage reads as desk-**absent** — biasing toward SUPPORTING
   the gap, i.e. toward the weak verdict.

7. **That the desk being open means transparency was delivered.** ADR 0071's
   job is showing what Kalshi charges against what the consensus says it is
   worth. Whether the screen he had open was `/board`, `/hedge` or the
   changelog is not recorded. **Presence is necessary for the job and is not
   the job.**

8. **A rate.** `n = 1` operator, one instance, one window, and a
   likely-bimodal one (sub-minute opens plus occasional multi-hour tabs).
   Nothing here generalises to anybody, including to Joe next month.

9. **Anything about `beta`, the gate, the actionable population, the fee
   coefficient or the cost headroom.** No column read here touches them, and
   `gate.py` may not read `manual_orders`, `parlay_positions` or `combo_orders`
   in either direction.

10. **Money.** `h4-balance-spans` section C carries `price_tenths`, `count` and
    `fee_actual` beside `filled_ms`. **Only `filled_ms`, `source`, `is_taker`
    and `venue_order_id` may enter this analysis or the write-up.** No P&L, no
    win rate, no typed estimate, no settled outcome — those belong to ADR
    0044's stopped study and to the fee registrations, and an inspector that
    leaked one would let a rule be chosen after an answer.

### 9.1–9.4 The four biases, with directions stated

- **9.1 (toward SUPPORTING the gap, and it is the largest).** The heartbeat is
  gated on `document.visibilityState === "visible"` (`Nav.tsx:246`). A
  backgrounded tab, a phone with the Kalshi app in front, a locked screen — all
  read as absent. Since Joe bets *in the Kalshi app*, the very act of placing
  the bet backgrounds the desk. **This is why GAP SUPPORTED is weak and GAP
  REFUTED is strong**, and it is the single most important sentence in this
  document.
- **9.2 (toward SUPPORTING the gap).** Heartbeats lost to an instance outage,
  while the fill is recovered. §9.6.
- **9.3 (toward REFUTING the gap).** A desk-placed order whose fill has a NULL
  `venue_order_id` survives §2.4's exclusion and is desk-present by
  construction. Bounded by the reported `UNJOINABLE` count and by the window
  counts of `manual_orders` and non-dry-run `combo_orders`.
- **9.4 (toward REFUTING the gap).** `theta_wall` ignores that both betting and
  browsing concentrate in evening hours, so it understates chance coverage.
  This is exactly why it carries no verdict and the day-shift permutation does.

---

## 10. What is built if it clears, what is killed if it does not

**Re-checked blind on 2026-09-03, and to be re-checked blind again immediately
before the look.**

| verdict | what it buys |
|---|---|
| **PRESENCE GAP SUPPORTED** (weak) | The "moment of a bet" is confirmed as unoccupied, and work aimed at *getting the desk into that moment* becomes fundable — a push at the moment, a share-target, a surface that survives an app switch. `manual_orders` becomes a **candidate** for retirement rather than extension; this verdict does not on its own authorise removing it, because its 0 rows were already known and are not this measurement's finding. |
| **PRESENCE GAP REFUTED** (strong) | The desk **is** at the moment of a bet, and the roadmap item "make it present" is **killed** — the purchase is the right not to build it. The open question becomes what the screen says there, which is ADR 0071 §2.2's other half and a different registration. |
| **PARTIAL PRESENCE** | Both above, scoped: presence is real and thin. The named next step is the same "get it into the moment" work, sized against the measured share rather than against a guess. |
| **UNRESOLVED (any reason)** | **Nothing is funded on presence, and nothing is killed.** `S`, `D` and the failed precondition are recorded so the next look starts from a number. This is a real outcome and it is cheaper than the alternative, which is building on a sentence. |

**Is this decision-relevant? Yes in three of four branches, and the honest
qualification is that the two extreme branches are the ones the design can
actually reach at `S = 8` (§0.3).** The middle — PARTIAL PRESENCE — is the
branch most likely to be true and least likely to be reached, and if the look
returns UNRESOLVED for that reason the correct reading is "we cannot tell",
not "no gap".

**The negative branch has an address, before the run.** Whatever the verdict,
**one** file is written:

    docs/measurements/<YYYY-MM-DD>-presence-at-the-moment-of-a-bet-result.md

with the verdict in its H1 title. One file for every branch is the point: a
registration whose negative branch has no destination produces a negative
result that quietly never gets written.

---

## 11. Instruments, and how the read is executed

`scripts/inspect_live_db.py` is the only thing permitted to run against the
live box. It opens `mode=ro`, has no free-form SQL argument, spends no credits
and no tokens, and touches no money path.

### 11.1 The two reads the primary needs — no new code

    flyctl ssh console -a kalshi-cockpit -C \
      "python /app/scripts/inspect_live_db.py h4-balance-spans --limit 5000 --json"

    flyctl ssh console -a kalshi-cockpit -C \
      "python /app/scripts/inspect_live_db.py visit-freshness --since 20260801 --limit 5000 --json"

- **Section C of `h4-balance-spans`** is the fills half:
  `SELECT id, ticker, filled_ms, count, price_tenths, is_taker, fee_actual,
  source FROM fills WHERE filled_ms >= :study_start ORDER BY filled_ms`, where
  `_H4_STUDY_START_MS = 1787044503594` = **2026-08-18T09:15:03Z**. That is 7
  days before `W_start`, so the section covers the whole registered window.
  Sections A, B, D, E of the same output belong to the H4 registration and are
  **not read here**.
- **`--since 20260801`** is mandatory and precedes schema v21, so the reported
  `start_ms` in the "visit window" section **is** `MIN(seen_ms)` over the whole
  table and is `W_start`. Omitting `--since` silently truncates to 7 days (C2).

### 11.2 The two reads the exclusion needs

    flyctl ssh console -a kalshi-cockpit -C \
      "python /app/scripts/inspect_live_db.py manual-orders-audit --json"

    flyctl ssh console -a kalshi-cockpit -C \
      "python /app/scripts/inspect_live_db.py combo-bids-tail -n 500 --json"

`manual-orders-audit` gives the census (`n_rows`, `submitted_ms` range) and is
counts-only by design. `combo-bids-tail` emits `kalshi_order_id`, `status`,
`dry_run` and `placed_ms`, which is what §2.4 joins on. If `manual-orders-audit`
reports `n_rows > 0`, C4 fires unless the ids can be obtained.

### 11.3 The analyzer, committed before the pull

`scripts/analyse_bet_presence.py`, implementing §3 through §6 exactly, with the
`S < 8` / `D < 5` refusal of §6.2 as a hard branch and with the seeded
permutation of §5.2. **Committed before the two reads of §11.1 are run**, as
Look 1's analyzer was. Building it does not amend this registration; if any
part cannot be built as specified, the shortfall is written into the result
document and the affected arm reports UNRESOLVED.

### 11.4 Free riders — counts only, no inference, and no subcommand exists

The partner asked for four census counts to ride along. **All four tables and
columns exist and were verified against `backend/store/schema.sql`.** What does
not exist is a read path: the inspector has no free-form SQL argument, and none
of its 36 subcommands emits these counts. So they need one new subcommand,
whose SQL is fixed here so the build is against a specification:

    SELECT COUNT(*) FROM parlay_positions
    SELECT COUNT(*) FROM scout_briefings
    SELECT COUNT(*) FROM agent_calls
    SELECT COUNT(*) FROM recommendations WHERE suppressed_reason = 'skeptic_unreviewed'

Three more added here, because they are the closest things in the schema to
"the desk was used at a decision" and leaving them out would make the census
look tidier than the record is:

    SELECT COUNT(*) FROM desk_passes
    SELECT COUNT(*) FROM bet_estimates
    SELECT COUNT(*) FROM parlay_lookups

**Rules on all seven: counts only; no timestamps joined to anything here; no
verdict; no hypothesis; they enter no arm and no multiplicity count.** They
answer ADR 0071 §3's *"not established: whether the scout desk has ever been
convened on live"* and nothing more. **If the subcommand is not built, they are
simply not reported and nothing is blocked.** A count with a story attached is
how the next unregistered finding gets written.

---

## 12. Corrections made to the proposed design, recorded because the reasons recur

Verified against the code, not inherited from the brief.

1. **The unit was the fill; it is now the sitting.** 10 of 25 fills in the only
   capture came from one evening.
2. **`combo_orders` was not named as a circularity path.**
   `COMBO_ORDERS_ARE_DRY_RUNS = False`, so a desk-placed resting bid on a
   `KXMVE` combination fills into `fills` tagged `venue_hand` like everything
   else. §2.4 now excludes both paths.
3. **Maker fills were not separated.** A resting order's fill instant is not
   its decision instant. The primary is taker-only.
4. **`h4-balance-spans` section C is the right subcommand and its floor was
   unstated** — it starts at 2026-08-18T09:15:03Z, not at the beginning of
   `fills`. It covers the registered window with 7 days to spare; it would not
   cover an earlier one.
5. **`visit-freshness` defaults `--since` to 7 days**, which is shorter than
   the window. An explicit `--since` is now a precondition.
6. **The four "free rider" counts have no read path.** All four tables exist;
   the inspector cannot emit them. §11.4 makes that a specified build task
   rather than an assumption.
7. **The window start is now in-database** (`MIN(seen_ms)`), not the
   2026-08-25 commit date of `49f1f43`, which is a code date and not a data
   date.
8. **"Distance in minutes, report counts at ±N" had no null.** A share of bets
   inside a visit is meaningless without the rate at which that happens by
   coincidence; §5.2 supplies a day-shift permutation that holds hour-of-day
   fixed.
9. **The clock-skew note was to be "stated"; it is now a precondition** with a
   named assumption, a named band, and a downgrade if any verdict depends on a
   sitting within 60 s of an edge.

---

## Provenance

Written and committed before the window closes at 2026-09-04T00:00:00Z and
before any `fills` row was read for this question. The author computed the
power tables of §0.3 from the binomial directly and took the planning rate
from a committed 2026-08-18 document covering 2026-08-10..17 — a period that
ends **7 days before** `W_start` and can therefore carry no information about
the in-window outcome.

---

## AMENDMENT 1 — 2026-09-03, written blind, before `K` exists

**Nothing below was decided with a decision statistic visible.** At the time of
writing, `K5`, `K30`, any distance-to-visit, `p_gap`, `p_perm` and `theta_wall`
have not been computed by any agent or person. The analyzer's first run reached
its §2.4 branch and returned before the first distance was taken; the author of
this amendment has been told the sample-size and precondition facts recorded in
A.2 below and nothing else. **Looks at the decision statistic so far: zero.**

This amendment settles two things, both of which had to be settled before the
admissible look: a wrong integer beside a right date (A), and an exclusion that
cannot be executed by the join it names (B).

---

### A. `W_end`: the integer is a transcription error; the date is authoritative

#### A.1 The correction

§2.2 reads `W_end = 2026-09-04T00:00:00Z    (1788652800000)`. **Those two
values are not the same instant.**

    1788652800000   =  2026-09-06T00:00:00Z    <- the integer as printed, WRONG
    1788480000000   =  2026-09-04T00:00:00Z    <- the registered instant

**The date is authoritative and the integer is corrected to `1788480000000`.**
The rule applied — and it is the rule, not a convenience — is that *a value
that is argued for outranks a value that is merely transcribed from it*. The
date is argued for in §8 ("Primary close"), is the instant §2.2's own
prohibition is written against, and appears as an ISO string at five separate
places in this file (the opening paragraph, §2.2, §6.3's verbatim decision
rule, §8 and the Provenance note). The integer appears **once**, in one
parenthesis, and is derived from the date rather than the date from it. §0.1
corroborates independently: its planning table records the window length "at
the §8 close" as `~10 days` from the first heartbeat, which is 9.37 days to
2026-09-04T00:00:00Z and 11.37 days to 2026-09-06T00:00:00Z.

This is the same shape as the repo's `None`-never-`0` convention: the derived
artifact yields to the source, and a reader is never asked to guess which of two
disagreeing values was meant.

The extension date is given its integer here too, so the same error cannot
recur at the backstop look: **`W_end' = 2026-09-18T00:00:00Z = 1789689600000`**.

#### A.2 What the wrong integer had already produced, stated in full

`scripts/analyse_bet_presence.py` was committed at `d2f51de` before the four
live reads, with `W_END_MS = 1_788_652_800_000`. It ran once under that
constant. **Everything it printed before returning is recorded here so that
nothing seen is left undeclared:**

    S = 12 sittings at SITTING_GAP_MS = 3,600,000 ms
    D = 7 budget days
    27 taker fills in window   2 maker   33 UNCLASSIFIABLE (pre-W_start)   0 engine
    manual_orders real rows 0;  combo_orders real, in window 5
    VERDICT   UNRESOLVED — EXCLUSION UNEXECUTABLE

No band count, no distance, no p-value: the analyzer's §2.4 branch returns
before the descriptive block that computes the first distance, so blindness on
the decision statistic is intact and complete.

The analyzer's constant has since been corrected to `1_788_480_000_000` with
the reason in a comment. §6.3's verbatim decision rule needs no edit — it
quotes the date and never the integer. Two consequences of the correction that
are not cosmetic, recorded before the look because they change an instrument:

- **§5.2's admissible shift set shrinks.** `Adm` is the non-zero day-shifts in
  `{-14..-1, 1..14}` that keep a shifted sitting inside `[W_start, W_end)`. A
  9.37-day window admits fewer shifts per sitting than an 11.37-day one, so
  §5.2's `|Adm| < 4` refusal now bites marginally sooner. The refusal threshold
  itself is **unchanged at 4** and is not being renegotiated with the window.
- **The permutation seed and draw count are unchanged** — `random.Random(20260903)`,
  10,000 draws — so the null is the registered one computed over a corrected
  support, not a new null.

#### A.3 The read preceded `W_end`, which §2.2 forbids. Recorded, not excused.

**SUPERSEDED by §F below (2026-09-04T01:30Z): the premise of this section is
false.** The captures were written at 01:13–01:14Z on 2026-09-04 UTC, after
`W_end`; the "2026-09-03" here was the author's local date. The text is kept as
written because the reasoning about what a premature read would have cost is
correct and the discard it orders was never executed. Read §F for what stands.

The four captures were taken on **2026-09-03**, before the window closed at
2026-09-04T00:00:00Z. §2.2 says *"No read of the fills population may be taken
before `W_end`"*, and under either the right instant or the wrong one, that read
was early. It is written here rather than absorbed, because a registration that
quietly forgives its own violations is a document, not an instrument.

**Why it did not hand anyone a choice**, argued rather than asserted: the only
quantities disclosed are `S`, `D`, the class census and the exclusion census.
§8's extension trigger references `S` and `D` **only**, and §8 fixed the
consequence of *both* branches — extend once to 2026-09-18, or proceed — before
either number existed. So seeing `S = 12` and `D = 7` selected nothing that was
not already selected on 2026-09-03 in advance. No band edge, no threshold, no
population rule and no stopping decision is available for revision by anyone who
knows those two integers.

**What it costs, and the repair:** the 2026-09-03 captures are **not admissible
evidence for the verdict** and are hereby discarded for that purpose. They may
be quoted only for the sample-size facts already disclosed in A.2. The
admissible look runs on a **fresh set of the same four captures taken at or
after 2026-09-04T00:00:00Z**, from the inspector **as currently deployed**, with
C3's `truncated = false` re-checked on every section used. No deploy, no code
change on the live box, no credits and no tokens: `inspect_live_db.py` opens
`mode=ro` and the four subcommands already exist.

**The figures in A.2 are neither a floor nor a ceiling on the registered `S`
and `D`.** The window will have grown by up to 9.4 hours (which can only add
sittings) and the exclusion of B below may remove fills (which can only remove
them). They are a provisional reading and are not to be quoted as the result.

---

### B. §2.4 cannot be executed by the join it names. The substitute, fixed now.

#### B.1 The defect, verified against the code rather than inherited

- `h4-balance-spans` section C is
  `SELECT id, ticker, filled_ms, count, price_tenths, is_taker, fee_actual,
  source FROM fills ...` (`scripts/inspect_live_db.py:5165`). **There is no
  `venue_order_id`.** `grep -c venue_order_id scripts/inspect_live_db.py`
  returns **0**: no subcommand in the inspector emits that column, so the
  registered join `fills.venue_order_id = combo_orders.kalshi_order_id` cannot
  be run against any capture this instrument can produce. The column exists in
  `backend/store/schema.sql` (`fills.venue_order_id TEXT`, nullable); the read
  path does not.
- The **manual half is executable by emptiness**: `manual-orders-audit`
  section A reports `n_rows = 0`, `real_orders = 0`, lifetime. A rule that
  excludes nothing from an empty table is executed, not skipped, and §1.1
  already forbids reading that 0 as a property.
- The **combo half is not empty**: `combo-bids-tail -n 500` returned **5 rows,
  the whole table**, all `dry_run = 0`, all `placed_ms` inside the window — 4
  `cancelled` with `cancel_reason = "the first leg has started"` and 1
  `resting`.

**C4's letter did not fire and its purpose did.** C4 says the verdict is
UNRESOLVED — EXCLUSION UNEXECUTABLE if desk-placed orders exist in the window
*"and the inspector cannot emit their `kalshi_order_id`s"*. The inspector emits
them perfectly well; what it cannot emit is the **fills side** of the join. The
analyzer implemented the purpose and refused. **That refusal is ratified as
correct**, and C4 is re-worded in B.4 so that its letter and its purpose
coincide from here on. The general lesson, which is the one to carry: *a
precondition written as the failure of one named mechanism will not fire when a
different mechanism fails the same way.* Write preconditions on the capability,
never on the route to it.

#### B.2 The ruling — the exclusion is executed by a substitute route, fixed here

**Route: (a) with (b) as a fixed fallback, under a fixed precedence.** Each
desk-placed order is cleared by the **venue's own statement** where one exists,
and by **ticker attribution** where one does not. Neither branch reads a fill's
timing, a distance, a visit, a price, an outcome, or anything a verdict depends
on; the set of excluded rows is determined entirely on the *order* side, which
is what §2.3's exclusion table demands of every rule in it.

**(a) The venue-cleared branch.** `combo_orders.cancel_reduced_by` is written
only from the venue's reply to `DELETE /portfolio/orders/{id}`
(`backend/bid_watch.py:89`, `backend/api/routes.py:3358`, both via
`record_cancel`), and the schema comment names it *"the venue's own word for how
much of it was still working at that moment."* A cancel that returns
`reduced_by == count` says the **entire** quantity was still resting when it was
withdrawn; a resting order that never gave up a contract has never filled, and
after a full withdrawal it cannot. So **no row of `fills` descends from it**,
for any window, without reference to any fill.

This is the branch that answers `combo-bids-tail`'s own docstring warning —
*"not whether a bid is still resting AT THE VENUE... this is what the desk
believes"*. `status` and `cancelled_ms` are the desk's belief and are used only
as a guard. `cancel_reduced_by` is the venue's sentence, and it is the load-
bearing field. A failed cancel writes no row at all: `bid_watch` logs and leaves
the bid working precisely so the table cannot claim a cancel that did not
happen.

**(b) The ticker-attributed branch, for orders (a) cannot clear.** For a
desk-placed order with no venue statement — the one `resting` row, and any
future partial-fill-then-cancel — a fill descending from it would necessarily
carry that order's `ticker`. So: **every in-population fill whose `ticker`
matches one of those orders is excluded and counted.** The exclusion is
executed conservatively — it removes more than §2.4 would — and the direction
of that over-exclusion is stated in B.5.

Both branches together satisfy §2.4's stated purpose exactly: *"a fill caused by
an order the desk itself placed... would make the measurement a tautology."*
Every desk-placed order is either proved to have caused no fill, or has every
fill it could have caused removed.

#### B.3 §9.10 is amended: `ticker` is admitted as a join key, and as nothing else

§9.10's allow-list — *"Only `filled_ms`, `source`, `is_taker` and
`venue_order_id` may enter this analysis or the write-up"* — is amended to add
**`ticker`**, under four constraints that preserve both of the purposes the
original serves:

1. **No ticker string is printed** — not by the analyzer, not in the result
   document, not in any commit message. Counts only. (This also honours the
   standing ruling that operator data never enters the repo: a ticker names what
   he bet on.)
2. **No grouping, bucketing, splitting, ordering or reporting by ticker,
   series, sport, or any function of a ticker.** §2.3's *"No exclusion on
   ticker, series, sport, price, size, fee, outcome, or settlement"* **stands
   unamended** and is not weakened by this.
3. **The only operation permitted is equality against a set `T` of tickers read
   from the desk's own order tables** (`combo_orders`, and `manual_orders`
   section E if it ever becomes non-empty). `T` is derived from the order side
   and never from `fills`, so no fill can be dropped for how it fell — which is
   the precise hazard §2.3 was written against ("an exclusion on ticker would
   let `KXMVE` combos be dropped after they were seen to fall the wrong way").
4. **§9.10's own purpose is untouched.** It is headed *"Money"*, and the columns
   it exists to keep out are `price_tenths`, `count` and `fee_actual` on the
   fills row, which remain forbidden. `fills.ticker` carries no price, no size,
   no fee, no P&L and no settled outcome. `combo_orders.count` is read on the
   **order** row, as one side of the `reduced_by == count` identity; it is a
   quantity of a cancelled bid, never a fill's size, is never printed, and never
   enters any statistic.

**`venue_order_id` stays on the allow-list** and stays unreadable. §2.4's
`UNJOINABLE` class (fills with a NULL join key) is therefore **vacuous and is
withdrawn** — under this instrument every fill is unjoinable by that key, so the
count would be the whole population and would bound nothing. It is replaced by
the **RESIDUAL CONTAMINATION BOUND** of B.5, which bounds the same thing from
the order side, where the information actually is.

#### B.4 C4 is re-worded, on the capability rather than on one route to it

> **C4 — the exclusion is executable.** §2.4. For every desk-placed,
> non-dry-run order in `manual_orders` or `combo_orders` with
> `placed_ms < W_end`, the analyzer must establish, by a route registered in
> this file before the look, **either (i) that no fill descends from it, or
> (ii) which in-population fills may descend from it, so that they can be
> dropped and counted.** Emptiness of the table is the trivial case of (i).
> If any such order can be neither cleared under (i) nor attributed under (ii),
> the verdict is **UNRESOLVED — EXCLUSION UNEXECUTABLE**. The failure of any
> *particular* join, query or column is not itself the trigger; the trigger is
> the absence of any registered route to (i) or (ii).

Note the widened order window: `placed_ms < W_end`, **not** `placed_ms >=
W_start`. An order placed before the window opened can still fill inside it.
On the committed record this changes nothing — all 5 combo rows are in-window
and `manual_orders` is empty lifetime — but the rule as written was narrower
than the contamination it guards against, and that is fixed here rather than
after a row appears.

The manual half keeps a route if it ever becomes non-empty:
`manual-orders-audit` section E (`_SQL_MANUAL_TICKERS`, *"E. rows per ticker,
largest first, with its share"*) emits the ticker set lifetime and ungrouped by
window, which is branch (b) over-inclusively — safe in the same direction. If
that section is absent from a capture and `real_orders > 0`, C4 fires.

#### B.5 The bias directions, stated before the look

- **Branch (b) over-excludes, and the direction is toward the WEAK verdict.**
  A hand bet Joe placed himself, in the Kalshi app, on the same combination
  ticker the desk was resting a bid on, is dropped though it belongs in the
  population. Such a row is one where the desk had minted and displayed that
  exact combination, so removing it removes a row that leans desk-present.
  That biases toward **PRESENCE GAP SUPPORTED**, which §1 and §9.1 already
  record as the weak verdict, and away from the strong one. It also lowers `S`,
  biasing toward the refusal branch. Both are conservative with respect to the
  finding that would be worth anything. **The count is reported; if it is 0 the
  bias is nil**, and the report must say which.
- **§9.3 is re-based.** Its bound was the `UNJOINABLE` count; it is now the
  RESIDUAL CONTAMINATION BOUND — the number of desk-placed orders not cleared
  under (a), together with the number of fills excluded under (b). Its
  direction (toward REFUTING the gap, if contamination survives) is unchanged,
  and under this route no contamination survives unless (b) is itself
  unexecutable, in which case C4 fires instead.
- **Clock skew (C6) does not reach either branch.** Neither compares a fill
  clock to a heartbeat clock; (a) compares two integers on one order row and
  (b) compares two strings.

#### B.6 THE OPERATIONAL RULE THE ANALYZER MUST IMPLEMENT, VERBATIM

> **E0 — captures.** All four captures are taken at or after
> `W_end = 1788480000000` (2026-09-04T00:00:00Z). Section C of
> `h4-balance-spans` and the `combo_orders` tail must both report
> `truncated = false`, and the combo tail's returned row count must be strictly
> less than its `requested`, so that the tail is the whole table. Otherwise:
> **UNRESOLVED — EXCLUSION UNEXECUTABLE**.
>
> **E1 — the manual half.** If `manual-orders-audit` section A reports
> `real_orders > 0`, take the ticker set from section E and pass it to E4; if
> section E is absent, **UNRESOLVED — EXCLUSION UNEXECUTABLE**. If
> `real_orders = 0`, the manual half contributes no tickers and is executed by
> emptiness.
>
> **E2 — the desk-order set.** `O` = every `combo_orders` row with
> `dry_run = 0` and `placed_ms < W_end`. Report `|O|`.
>
> **E3 — venue clearance.** An order `o` in `O` is **CLEARED-BY-VENUE** iff
> `o.status = 'cancelled'` **and** `o.cancelled_ms` is not null **and**
> `o.cancel_reduced_by` is not null **and**
> `float(o.cancel_reduced_by) == float(o.count)`. Every other `o` joins the
> residual set `R`. Report `|CLEARED-BY-VENUE|` and `|R|`.
>
> **E4 — ticker attribution.** `T` = the set of `o.ticker` for `o` in `R`,
> plus any tickers from E1. Report `|T|` as an integer; **print no element of
> `T`**. Every fill with `source = 'venue_hand'`, `filled_ms` in
> `[W_start, W_end)` and `ticker` in `T` is **EXCLUDED-BY-TICKER**, at both
> `is_taker` values. Report the excluded count.
>
> **E5 — ordering.** E4's exclusion is a **population** rule and is applied
> **before** sittings are formed, so an excluded fill can neither start a
> sitting nor bridge two. `S` and `D` are computed on the post-exclusion
> population, and the §6.2 floor refusal (`S < 8` or `D < 5`) is evaluated
> **after** E0-E4, not before them. This inverts the order of the two refusal
> branches as the analyzer first shipped them.
>
> **E6 — the bound.** Report `RESIDUAL CONTAMINATION BOUND` = `|R|` orders and
> the EXCLUDED-BY-TICKER fill count, beside every verdict, in place of the
> withdrawn `UNJOINABLE` line.
>
> **E7 — nothing else changes.** `W_start`, `SITTING_GAP_MS = 3,600,000`,
> `B5 = 300,000`, `B30 = 1,800,000`, `S_min = 8`, `D_min = 5`, `alpha = 0.005`
> per test, four tests, the seeded 10,000-draw permutation, the leave-one-day-out
> downgrade and §6.3's verbatim decision rule are **untouched**.

#### B.7 The routes considered and rejected, with the reason

- **Ticker alone for all five orders (candidate b, unaided).** Rejected as the
  primary because it over-excludes where a strictly better, venue-sourced proof
  exists for four of the five. Kept as the fallback exactly where no such proof
  exists. Using the coarse key when the exact one is available would throw away
  population for nothing.
- **A new inspector column and a deploy (candidate c).** Rejected. It puts the
  admissible look **after a code change to the only instrument permitted against
  the live box**, authored by someone who has already seen `S`, `D` and the
  census — the shape this whole document exists to prevent. `inspect_live_db.py`
  is additionally being edited by another lane as this is written, so the
  deployed instrument would change identity mid-measurement. And it buys
  nothing: every column E1-E4 needs is already emitted by the four registered
  subcommands, so the substitute route requires **no change to the inspector and
  no deploy**.
- **Standing on UNRESOLVED — EXCLUSION UNEXECUTABLE (option 1).** Rejected, and
  the reason is worth stating because it is the branch that looked most
  disciplined. §8's only extension trigger is `S` and `D`; a refusal for an
  unexecutable exclusion is not in it, so option 1 does not extend the window —
  **it closes the question**. That would spend the entire registration on a
  defect in the analyzer's *reach*, which is repairable blind, at no cost, with
  no deploy, and without seeing anything. §10 records that UNRESOLVED funds
  nothing and kills nothing; taking it here would purchase nothing at all.
  Refusing when a rule cannot be executed is right; refusing when it *can* be
  executed by a route fixed before the answer exists is not rigour, it is
  waste.

---

### C. Look accounting, multiplicity, and §8

- **Looks at the decision statistic to date: 0.** The 2026-09-03 run returned
  at its §2.4 branch, above the line where the first distance is computed.
- **Looks after the re-run: 1.** §6.2's *"the record is looked at ONCE"* is
  preserved exactly, and this amendment is the reason it still is: had the
  analyzer computed distances before refusing, this repair would have been a
  second look.
- **The multiplicity is unchanged: four tests, family-wise 0.02, Bonferroni
  0.005 each.** E0-E6 are preconditions and exclusions. A precondition can only
  turn a verdict into UNRESOLVED and can never manufacture one, so per §6.1 it
  adds nothing to the count. No test is added, removed or re-aimed here.
- **§8 is intact and is not amended.** Its extension trigger still references
  `S` and `D` only, its one extension is still to `W_end' = 2026-09-18T00:00:00Z`
  (`1789689600000`), and its terminal branch is unchanged. If the admissible
  look returns `S < 8` or `D < 5` on the post-exclusion population, the
  extension fires and `K` is still never computed — so at most one computation
  of the decision statistic can ever occur.
- **If the corrected analyzer refuses again for a reason other than `S`/`D`**,
  that refusal is terminal for this registration. No further repair-and-re-run
  is authorised here; a third attempt would need a successor registration, and
  the reason is that repairs made after two refusals are no longer plainly
  independent of what the refusals revealed.

### D. §8's blind re-check of §10, taken now

§10 was re-read blind on 2026-09-03 with no statistic visible and **stands
unchanged**: the four branches, what each funds and what each kills, are as
registered. This amendment does **not** discharge §8's requirement that §10 be
re-checked immediately before the admissible look, which now falls on a
different day than the one §10 was written on.

### F. Correction to this amendment, 2026-09-04T01:30Z — the captures were not early

*(Numbered F because a §E already existed below when this was appended; the
two carried the same letter until the audit noticed.)*

Amendment 1 states in §C and its summary that *"the four captures were taken
2026-09-03, before `W_end`"* and discards them. That sentence read the date in
the author's local clock (America/Los_Angeles, where it was still the evening
of the 3rd). In UTC, which is the clock every timestamp in this registration
uses, the four capture files were written at:

    h4-balance-spans        2026-09-04T01:13:20Z
    visit-freshness         2026-09-04T01:14:17Z
    manual-orders-audit     2026-09-04T01:14:23Z
    combo-bids-tail         2026-09-04T01:14:28Z

all after `W_end = 2026-09-04T00:00:00Z`. **E0 is satisfied by the existing
captures**, and they are the admissible set. They are used rather than
re-taken, because a second pull of the same population would be a second read
of the record for no gain, and §6.2 prefers exactly one. Nothing else in
Amendment 1 changes: the ruling on §2.4 (B.2–B.6), the correction of the
integer (A), and the look accounting (C: zero looks at the decision statistic
so far, one after the run) all stand. The analyzer now reads each capture
file's write time and refuses under E0 if any precedes `W_end`, so this check
is executed rather than asserted.

### E. What Amendment 1 does not repair

- It does not recover the `venue_order_id` join. The exact per-fill attribution
  §2.4 specified remains impossible with this instrument; what B.2 supplies is
  a **coarser** exclusion whose error is one-directional and reported.
- It does not make the 2026-09-03 read not have happened. It discards its
  captures for the verdict and records what was seen.
- It does not touch §9's list of what the measurement cannot establish. Every
  line there — causation, a tab from a reader, off-venue bets, entries from
  exits, the poller's floor — survives this amendment intact.
- It does not change the power position. §0.3's tables are computed from `S`
  and the binomial and are unaffected by which rows the exclusion removes,
  except through `S` itself, which §6.2's floor already governs.
