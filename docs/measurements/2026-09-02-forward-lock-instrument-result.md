# Forward-lock instrument result — **UNRESOLVED — TEMPO-CONFOUNDED** (§7 C5)

Reading **2026-09-02T19:01Z**, against the live instance.
Registration: `docs/measurements/2026-09-01-forward-lock-instrument-registration.md`
(blob `f5328a0e0205f308229a489225f6b0f075a4a581`, committed in `feca481` before
any post-`T0` burst was read; Amendment 1 written blind the same day).

This is the file §10 of the registration requires — *"Whatever the verdict,
**one** file is written ... with the verdict in its H1 title"* (registration
lines 587-594). It had not been written for either of the two earlier looks
(the 2026-09-01 `E = 52` reading and the 2026-09-02T16:26Z `C4/C5` reading);
both were recorded in `tasks/NEXT.md` only. This file is the registered
destination for all three, and the verdict in its title is the one the
registration's own decision rule produces on the newest reading.

> **Read the verdict as the registration spells it, not as the evidence
> invites.** `E`, `K` and `E_n` on this reading each satisfy the FIX CONFIRMED
> clause of §6.3, and the arm they were measured on was **40% busier** than the
> pre-fix baseline — more collision opportunity, not less — and still carried
> zero bursts. §7 forbids reading that as confirmation because precondition C5
> fails, and §6.1 says a precondition *"can only convert a verdict into
> UNRESOLVED; it cannot manufacture a positive one"* (lines 349-353). **The
> registration wins.** The reasoning for why it should is in §3 below, and the
> partner's ruling on what happens next is in
> `docs/adr/DRAFT-p5-forward-lock-terminated-tempo-confounded.md`.

## 0. The reading, verbatim

Taken from a laptop with:

    flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py forward-lock"

and quoted as given. It cannot be re-run from the lane that wrote this file,
so nothing below is a re-computation; every number is this reading's.

    T0     2026-09-01T17:52:17.849Z
    E      294 fast cycles   (E* = 160 — reached)
    K      0 bursts post-T0 (collapsed by matched cycle)
    H      0 fast, in band [5.000, 8.000]s
    E_n    1.0000   (alarm at 200.0)
    p0     0.00999
    13 journal bursts, all pre-T0, excluded by §2.2; 0 straddlers
    C1 PASS  MIN poll_log 2026-08-18T08:16:53Z <= T0; MAX 2026-09-02T19:01:25Z >= newest burst
    C2 PASS  T0 exists
    C3 PASS  A_pre = 0.87 h (median of 11 aged pre-fix bursts of 13); 235 fast cycles at age >= A_pre, need 30
    C4 PASS  median wal_kb post-T0 = 2711 vs pre-fix q25 = 2711; n=2002/1859 samples
    C5 FAIL  post-T0 = 79.64/h vs pre-fix = 56.81/h; tolerance ±25% (ceiling 71.01/h)
    VERDICT  UNRESOLVED — C5

The instrument prints the failed precondition's *label* (`C5`); §7 names the
same state **UNRESOLVED — TEMPO-CONFOUNDED** (line 470). They are one verdict
with two spellings, and this file uses the registration's.

The instrument that produced it is `scripts/inspect_live_db.py forward-lock`,
whose C3/C4/C5 arithmetic landed in `3a78fbf` (2026-09-02). Only that code
prints all six preconditions, which is how the reading is known to have come
from it; the live SHA at 19:01Z was not captured with the reading and is not
asserted here.

## 1. The counts first — `n` before the effect size

The registered quantities of §6.3 (lines 392-404), in the order the
registration defines them:

| quantity | value | what it is |
|---|---:|---|
| `T0` | 2026-09-01T17:52:17.849Z | `MIN(polled_ms) WHERE endpoint = 'mirror'` — the in-database deploy marker, §2.1 |
| `E` | **294** fast cycles | distinct post-`T0` `poll_log` stamps carrying no `mirror` row; `E* = 160` (§0.2, line 61), **reached** |
| `K` | **0** bursts | journal lines, `consecutive_failures == 1`, matched cycle at or after `T0`, collapsed by cycle |
| `H` | **0** | FAST-matched bursts with offset in `B = [5.000, 8.000]` s |
| `E_n` | **1.0000** | the running e-value; alarm at 200 (§6.2); no FAST-matched burst, so no factor applied |
| `p0` | 0.00999 | `3.000 / C`; the planning value was 0.00999 (§5, line 327), so `C` has not moved and §8's amendment trigger (lines 502-505) did not fire |

Exposure: 25.15 h of wall clock from `T0` to the reading, 294 fast cycles —
about 11.7 cycles an hour against the ~12/h the registration planned on.

**Descriptive context, reported as §2.2 and §2.4 require and entering neither
arm:** 13 journal bursts exist, every one of them pre-`T0` and excluded by
§2.2's discarded interval; **0 straddlers** (§2.4). §2.3's UNCOUNTABLE class
(lines 205-206) and §3's merge-adjacent count (lines 248-250) are not in the
quoted reading; the instrument as built does not print either, and this file
does not invent a figure for them. That is a §11 shortfall — *"the shortfall is
written into the result document"* (lines 622-624) — and it does not bear on
the verdict, because both are descriptive reports with no threshold attached.

## 2. The preconditions, each by name

§6.3 conditions FIX CONFIRMED on *"every precondition C1 to C6 of §7"* (lines
413-415), and a failed one is *"never shortened to UNRESOLVED alone"* (lines
418-420). The instrument implements that at `scripts/inspect_live_db.py:2891-2903`:
a precondition that is uncomputable is not a pass, and every failed name is
carried into the verdict string.

| check | state | reading | note |
|---|---|---|---|
| C1 `poll_log` spans the window | PASS | MIN 2026-08-18T08:16:53Z ≤ `T0`; MAX 2026-09-02T19:01:25Z ≥ newest burst | |
| C2 `T0` exists | PASS | 2026-09-01T17:52:17.849Z | |
| C3 restart coverage | PASS | `A_pre` = 0.87 h, median of 11 aged pre-fix bursts of 13; **235** fast cycles at age ≥ `A_pre`, need 30 | computed from `loop_rss.jsonl` restart markers; the 2.0 h fallback (line 457) was not needed |
| C4 WAL comparability | PASS | median `wal_kb` post-`T0` = 2,711 vs pre-fix q25 = 2,711; n = 2,002 / 1,859 | **on the boundary**: `c4_ok` is `>=` (`inspect_live_db.py:2821-2825`) and the two figures are equal to the kilobyte |
| C5 victim tempo | **FAIL** | post-`T0` = **79.64/h** vs pre-fix = **56.81/h**; tolerance ±25%, ceiling 71.01/h | **+40.2%**, above the ceiling by 8.63/h; the direction is *busier* |
| C6 `lambda_0` supports `E*` | PASS | `E*` stays 160 | see §6 below on what the instrument's `lambda_0` actually is |

**C4 flipped between looks and C5 moved away.** At 16:26Z C4 read 2,699 vs
2,711 — a FAIL by 12 KB, 0.44% — and at 19:01Z it read 2,711 vs 2,711, a PASS
by zero. Nothing was changed between the two readings; the post-`T0` median
moved 12 KB on ~200 more samples. That is what a comparison sitting on its own
threshold looks like, and it is why the 16:26Z entry in `tasks/NEXT.md` said
*"do not treat this as a finding about WAL"*. It still is not one. C5 went the
other way: 73.92/h (+30.1%) at 16:26Z, 79.64/h (+40.2%) at 19:01Z. §4 below
has the arithmetic of why.

## 3. The verdict, and the case against it stated in full

    VERDICT   UNRESOLVED — TEMPO-CONFOUNDED   (§7 C5, registration line 470)

**What §10's UNRESOLVED branch requires recorded** (line 585; Amendment 1 A3,
line 707 — *"Nothing credited; `E`, `K` and the failed precondition
recorded"*):

    E                     294 fast cycles post-T0
    K                     0 bursts
    failed precondition   C5 — victim tempo comparability
                          post-T0 79.64/h vs pre-fix 56.81/h, tolerance ±25%

### 3.1 Against interest: what the evidence would license if §7 were not there

Every clause of §6.3's FIX CONFIRMED except one holds on this reading:

- `E >= 160` — 294, reached at roughly 1.8× the floor.
- `K = 0` — no burst of any kind, fast or mirror, in the whole post-`T0`
  exposure.
- `E_n < 200` — 1.0000; no FAST-matched burst exists to move it.
- C1, C2, C3, C4, C6 — all hold.

Under the planning `lambda_0 = 0.0338` (§0.1, line 45), the one-sided exact
binomial of §5 gives `P(K = 0 | rate unchanged) = (1 − 0.0338)^294 ≈ 4.1 × 10⁻⁵`
— two orders of magnitude inside the 0.005 the registration asked for.

And the one clause that fails, fails in the direction that makes the null
*harder* to survive, not easier. §7's stated worry for C5 is *"Fewer passes
means fewer collisions regardless of the fix"* (line 467). The post-`T0` arm
carried **more** passes — 40% more victim writes per hour landing on the same
database — so the fix was tested against more collision opportunity than the
pre-fix rate was measured under, and produced none. A reader who saw only
`C5 FAIL` would assume the flattering confound. It is the opposite one.

**That is the strongest form the evidence could have taken, and it is exactly
why it may not be written up as FIX CONFIRMED.**

### 3.2 Why the registration wins anyway

Three reasons, in descending order of how much they matter:

1. **The tolerance was registered two-sided, before the data, and the
   registration says a rule chosen afterwards is the freedom it exists to
   remove.** §7 C5 reads *"within plus or minus 25%"* (lines 468-470) and the
   instrument implements `abs(post_tempo - pre_tempo) / pre_tempo <=
   C5_TEMPO_TOLERANCE` (`inspect_live_db.py:2840-2845`). §1 fixes the
   principle for the arms — *"Neither may be reported one-sided after having
   been computed two-sided, or the reverse"* (lines 116-117) — and there is no
   honest reading under which a precondition gets a looser standard than the
   statistic it guards. Deciding **now**, with +40% on the screen, that only
   the downward direction was ever meant would be choosing the rule by the
   answer. The argument that the tolerance *should* have been one-sided may
   well be right; it is a design note for the next comparability check anyone
   registers, and it is worth nothing here.

2. **Busier is not the same population, and the registration says a verdict
   does not generalise across tempo.** §9.8 (lines 569-571): a verdict here
   does not generalise to *"a different pass tempo ... conditions of the
   window, not constants of the system"*. C5 exists because the two arms must
   be the same window in the respects that move the outcome, and "the
   direction of the difference happens to be unflattering to the null" is a
   statement about *this* difference, not a demonstration that tempo cannot
   also change the mechanism. A busier runner takes the write lock more often
   and holds it in shorter pieces; whether that raises or lowers the chance
   that a poller cycle's hold expires someone's 5 s busy wait is not something
   this registration measured. The direction argument is plausible. It is not
   registered, and plausible-and-unregistered is what §6.1 calls
   manufacturing a positive.

3. **`E_n = 1.0000` is silence, not exoneration, and §1 already said so.** The
   signature arm *"cannot clear, for the same reason the attribution design
   could not: an absence of in-band bursts is what its null predicts anyway"*
   (lines 119-122). Only the rate arm can credit the fix, and the rate arm is
   the one C5 guards.

So: **UNRESOLVED**, named. Not "no signal", not "the fix did nothing" — §0.3
forbids that reading in as many words (lines 77-80) — and not FIX CONFIRMED.

## 4. Why C5 is moving away, from the instrument's own arithmetic

`post_tempo = lines_per_hour(t0, None)` and
`pre_tempo = lines_per_hour(None, ADR_0091_DEPLOY_MS)`
(`inspect_live_db.py:2838-2839`). `lines_per_hour` (2827-2836) is
`len(window) / span_h` over every `loop_rss.jsonl` sample in the window — so
`post_tempo` is a **cumulative mean from `T0` to the newest sample**, against a
pre-fix mean over a **fixed** window whose edge is `ADR_0091_DEPLOY_MS`
(2026-08-31T15:29:19Z, line 2383).

Two looks 2.58 h apart let the marginal rate be recovered:

    16:26Z   22.57 h post-T0   73.92/h   ->  ~1,668 lines
    19:01Z   25.15 h post-T0   79.64/h   ->  ~2,003 lines
    marginal, 16:26Z-19:01Z    ~335 lines / 2.58 h  =  ~130/h

The runner was writing at roughly **2.3× the pre-fix tempo** in that window,
and a cumulative mean can only approach a marginal rate that high from below.
For the cumulative figure to fall back inside the ceiling from where it stood
at 19:01Z, the runner would need about **15 h at exactly the pre-fix tempo**
(56.81/h), or about **7 h at 40/h**, or **3 h of total silence** — and every
hour above 71/h pushes those figures out. The record does not say a quiet
window of that size is coming: the feed follows fixtures and attention
(CLAUDE.md, ADR 0071 §2.6), and NCAAF and NFL enter the feed with no config
change (`backend/kalshi/discovery.py:237-238`, as ADR 0095 §2 records).

**And the baseline itself is leaving the file.** `loop_rss.jsonl` is capped at
2 MiB and trimmed to 1 MiB, whole newest lines, once it crosses
(`scripts/run_loop.py:175-176`, deployed 2026-09-02). At the measured 286.6
B/line that is a trim from ~7,300 lines to ~3,660. At 19:01Z the file held
~1,859 pre-fix samples, the ~26 h discarded interval, and ~2,003 post-`T0`
samples — on the order of 5,400 lines — and the post-`T0` arm alone will exceed
3,660 before the trim fires. So the first trim, which at ~80-130 lines/h is
roughly a day away, removes **every pre-fix sample**: `pre_tempo` and
`pre_wal_q25` become `None`, C4 and C5 report NOT COMPUTED, and C3's `A_pre`
falls to the 2.0 h fallback. Under `inspect_live_db.py:2849-2856` NOT COMPUTED
is not a pass, so the verdict would then read UNRESOLVED — C4/C5 **regardless
of tempo**. The quiet-period path back exists in arithmetic and is closing on
two clocks at once. This estimate uses the printed sample counts, which count
lines carrying `wal_kb`; if the file carries lines without it the roll-off is
sooner, not later.

## 5. What this reading closes, and what it does not

- **It does not credit ADR 0091.** Nothing in §10's UNRESOLVED row credits
  anything, and Amendment 1 A3 left that row *"Unchanged"* (line 707).
- **It does not refute ADR 0091.** `K = 0` on 294 cycles is not a refutation
  of anything, and `H = 0` cannot be one by §1's own argument.
- **It does not raise `E*`.** C6 holds; `E*` stays 160.
- **It does not amend C5.** See §3.2(1). The tolerance stands at ±25%,
  two-sided, in `C5_TEMPO_TOLERANCE` (`inspect_live_db.py:2397`) and in the
  registration (lines 468-470).
- **It does not open the §0.4 successor.** That registration was *"not
  authorised here"* at line 100 and was killed by the partner on 2026-09-01
  (`tasks/NEXT.md`, the 2026-09-02 entry's "Killed by the partner" paragraph).

What happens to P5 as an open item is a **ruling**, not a measurement, and it
is in the draft ADR beside this file rather than here.

## 6. What this does not establish

Per CLAUDE.md's measurement rules, and checked against the schema rather than
written as modesty:

1. **That the `database is locked` symptom is gone.** `K = 0` is a statement
   about the chain runner's own failure hook over 25 h of exposure on one
   tempo. §9.1: lock failures inside the poller, `bid_watch`, `hedge_watch` or
   the API never reach the journal; the absolute rate is a floor.
2. **That the busier arm is a *harder* test rather than a *different* one.**
   §3.2(2). The direction argument is stated against interest and is not a
   registered finding.
3. **That `4.1 × 10⁻⁵` is the p-value of anything.** It is the exact binomial
   §5 would have quoted under FIX CONFIRMED, computed on the **planning**
   `lambda_0 = 0.0338`. The instrument's own C6 recomputation is `k_count /
   e_count` (`inspect_live_db.py:2733`) — the *post-`T0`* rate, which at `K =
   0` is zero and falls back to the registered `E*` by construction (lines
   2742-2746). §0.1 says the instrument *"recomputes `lambda_0` from
   `poll_log` at analysis time"* meaning the pre-fix rate; as built it does
   not, and C6 therefore passes on the planning value rather than on a
   measurement. That is a §11 shortfall recorded here, and it would matter
   only on a FIX CONFIRMED branch this reading does not reach.
4. **That C4 holds in any sense stronger than "equal on this reading."** It
   failed by 0.44% at 16:26Z and passed by 0 KB at 19:01Z. Two windows whose
   WAL medians coincide to the kilobyte are near-identical arms, and a third
   reading could put it either side again.
5. **That 56.81/h is *the* pre-fix tempo.** It is the mean over whatever
   pre-deploy lines the capped file still held on 2026-09-02, ending at
   `ADR_0091_DEPLOY_MS`; the file's start (2026-08-18 for `poll_log`, later for
   `loop_rss`) is not a registered boundary. The comparison is
   registration-fixed at its *edge* and file-dependent at its *start*.
6. **Anything about the 2026-08-31T15:29Z .. `T0` interval.** §2.2 excludes it
   from both arms; 13 bursts sit in the pre-fix journal and none in the
   interval or after. (§2.2, line 164, describes `T0` as *"roughly nineteen
   hours"* after the deploy; it is 26.4 h. `T0` is derived from the database, so the arms
   are unaffected; the prose is off by seven hours and is noted rather than
   corrected in a registered file.)
7. **Anything about the retention prune or the `TRUNCATE` checkpoint** —
   ADR 0091's named remaining suspects. §10's FIX CONFIRMED row was the only
   branch that bought *"the right not to chase two suspects nobody has
   scheduled"* (Amendment 1 A3, line 704), and it was not reached.
8. **That the verdict would survive a re-read.** It would not, in the direction
   §4 gives: the next reading will show C5 further out or NOT COMPUTED. This
   file records the 19:01Z reading; it does not promise the number is stable.
