# Forward-lock instrument result — **UNRESOLVED — C4/C5** (§7: WAL-CONFOUNDED and TEMPO-CONFOUNDED at the registered look)

Registered look **2026-09-02T16:26Z**, `E = 263`; unregistered re-read
**2026-09-02T19:01Z**, `E = 294`, both against the live instance.
Registration: `docs/measurements/2026-09-01-forward-lock-instrument-registration.md`
(blob `f5328a0e0205f308229a489225f6b0f075a4a581`, committed in `feca481` before
any post-`T0` burst was read; Amendment 1 written blind the same day).

This is the file §10 of the registration requires — *"Whatever the verdict,
**one** file is written ... with the verdict in its H1 title"* (registration
lines 587-594). It had not been written for any earlier reading; the
2026-09-01 `E = 52` reading and the 16:26Z reading were recorded in
`tasks/NEXT.md` only. This file is the registered destination for all of them.

**Which reading is the look.** §6.2 registers the rate arm as *"a single look
at `E*`, no early stopping"* (lines 386-390) and §8 makes `E* = 160` the
primary stop (lines 482-487). The first reading taken past `E* = 160` was the
16:26Z reading at `E = 263` (`tasks/NEXT.md:278-286`, commit `fbede83`), and
that is the registered look; its verdict, **UNRESOLVED — C4/C5**, is the one
in this file's title. The 19:01Z reading was taken afterwards to see which way
the tempo was moving. It is an **unregistered re-read**, it is reported here
in full because it is the more complete transcript and because C4 flipped and
C5 moved between the two, and nothing in it is a P5 verdict.

> **Read the verdict as the registration spells it, not as the evidence
> invites.** At both readings `E`, `K` and `E_n` each satisfy the FIX
> CONFIRMED clause of §6.3, and the post-`T0` arm was 30-40% **busier** than
> the pre-fix baseline — which §3.2(2) below argues is more collision
> opportunity, and §6.2 below records as not established — and still carried
> zero bursts. §7 forbids reading that as confirmation because C5 fails (and
> C4 failed at the look), and §6.1 says a precondition *"can only convert a
> verdict into UNRESOLVED; it cannot manufacture a positive one"* (lines
> 349-353). **The registration wins.** §3 below says why it should, and the
> partner's ruling on what happens next is in
> `docs/adr/DRAFT-p5-forward-lock-terminated-tempo-confounded.md`.

Every `scripts/inspect_live_db.py:NNNN` citation below is to the **repo copy**
at this branch's HEAD (`fbede83` and after). It was not diffed against
`/app/scripts/inspect_live_db.py` on the live box at either reading.

## 0. The readings, transcribed

Both were taken from a laptop with:

    flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py forward-lock"

Neither can be re-run from the lane that wrote this file. **Reformatted from
the instrument's tables**, which print as six-column sections; nothing below
is a re-computation, and where a figure is derived rather than printed it is
marked so.

### 0.1 The registered look — 16:26Z, as recorded (`tasks/NEXT.md:278-286`, `fbede83`)

    E    263 fast cycles   (E* = 160 — PAST IT)
    K    0 bursts          H = 0     E_n = 1.0000
    C1 PASS   C2 PASS   C3 PASS   C6 PASS
    C4 FAIL   median wal_kb post-T0 2,699 vs pre-fix q25 2,711
    C5 FAIL   post-T0 73.92/h vs pre-fix 56.81/h
    VERDICT   UNRESOLVED - C4/C5

The instrument prints the failed preconditions' *labels*; §7 names the same
states **WAL-CONFOUNDED** (line 465) and **TEMPO-CONFOUNDED** (line 470).
This summary is the only transcript of that look in the record; C3's figures
at 16:26Z were `A_pre = 0.87 h` and 214 aged cycles (same source).

### 0.2 The unregistered re-read — 19:01Z, transcribed from the instrument's tables

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

Three transcription notes:

- **The ceiling figure is derived** (56.81 × 1.25 = 71.01) and is not printed
  by the instrument; the instrument prints `tolerance +/-25%`
  (`inspect_live_db.py:3016-3020`).
- **The instrument prints a `median cycle gap C` row** (`:2933-2935`) that
  was not carried into the reading as it was handed to this lane. `C` is
  therefore **derived** here from the printed `p0`: `3.000 / 0.00999 ≈ 300.3
  s`. The planning value was 300.415 s (§5, line 327), so §8's amendment
  trigger — `C` moving more than 10% (lines 502-505) — did not fire on any
  reading of `p0` consistent with the printed figure.
- The seventh line compresses the instrument's population table. The "excluded
  by §2.2" phrasing is the instrument's, and §1.2 below corrects it.

The instrument's C3/C4/C5 arithmetic landed in `3a78fbf` (2026-09-02). Only
that code prints all six preconditions, which is how both readings are known
to have come from it; the live SHA at either reading was not captured and is
not asserted here.

## 1. The counts first — `n` before the effect size

### 1.1 The registered quantities of §6.3 (lines 392-404)

Marked **S** where the value is sourced from a reading as printed, **D** where
it is derived here.

| quantity | 16:26Z (look) | 19:01Z (re-read) | what it is |
|---|---:|---:|---|
| `T0` | — | 2026-09-01T17:52:17.849Z **S** | `MIN(polled_ms) WHERE endpoint = 'mirror'`, §2.1; the 16:26Z summary does not restate it |
| `E` | **263 S** | **294 S** | distinct post-`T0` `poll_log` stamps with no `mirror` row; `E* = 160` (§0.2, line 61), reached at both |
| `K` | **0 S** | **0 S** | journal bursts, `consecutive_failures == 1`, matched cycle at or after `T0`, collapsed by cycle |
| `H` | **0 S** | **0 S** | FAST-matched bursts with offset in `B = [5.000, 8.000]` s |
| `E_n` | 1.0000 **S** | 1.0000 **S** | the running e-value; alarm at 200 (§6.2); no FAST-matched burst, so no factor applied |
| `p0` | — | 0.00999 **S** | `3.000 / C`; planning value 0.00999 (line 327) |
| `C` | — | ≈ 300.3 s **D** | from `p0`; the instrument's own row was not transcribed |
| wall clock from `T0` | 22.56 h **D** | 25.15 h **D** | ~11.7 fast cycles/h against the ~12/h planned |

The 2026-09-01 reading at `E = 52` (`tasks/NEXT.md`, the superseded "§11 IS
BUILT" entry; commit `7722339`) is the only other reading in the record and
was below `E*`; §6.3's last sentence forbade quoting any rate verdict from it.

### 1.2 Descriptive context, entering neither arm

**Thirteen journal bursts exist and every one of them is before ADR 0091's
deploy** — `ms < ADR_0091_DEPLOY_MS`, 2026-08-31T15:29:19Z
(`inspect_live_db.py:2785`), 13 of 13. **§2.2's discarded interval,
2026-08-31T15:29:19Z → `T0` (26.4 h), contains none of them, and neither does
the post-`T0` exposure.** The instrument's phrasing "excluded by §2.2" is
therefore loose: the interval excluded nothing because nothing fell in it.
Reported as the descriptive context §2.2 permits (lines 176-178); it may not
enter either arm or produce a verdict. **0 straddlers** (§2.4) — **S**, from
the 19:01Z reading. "11 aged pre-fix bursts of 13" — **S**.

**§2.3's UNCOUNTABLE class is required *"whatever the verdict"* (lines
205-206) and the instrument does not report it.** A journal line whose
`consecutive_failures` is missing or non-integer is, by §2.3's own argument
(lines 190-193), precisely how a lock killing a row's own write manifests —
and `inspect_live_db.py:2653` drops such a line with the same `continue` that
drops a repeat inside a burst, without distinguishing them. So as the
instrument computes it, **`K = 0` is a floor in this respect**: an uncountable
post-`T0` line would be invisible to it. This is a §11 shortfall — *"the
shortfall is written into the result document"* (lines 622-624) — and it
bears on the verdict's meaning even though it cannot move UNRESOLVED
anywhere. §3's merge-adjacent count (lines 248-250) is likewise not printed;
that one is descriptive with no threshold attached.

**The journal has written nothing of any kind since before the fix, and the
hook's liveness after `T0` is not established.** Read live at ~19:40Z on
2026-09-02 (`python -c` over `sqlite3` and the file, run over `flyctl ssh
console`): `/data/loop_failures.jsonl` is **36 lines / 25,083 bytes**; the
newest line of *any* kind — failure, diagnosis or rollback — carries
`ms = 1788174060409` = **2026-08-31T11:01:00Z** (`pass_number` 21), and the
`loop_failures` table's `MAX(failed_ms)` is the same value over its 23 rows.
So the whole post-`T0` window, and the discarded interval before it, contain
**no journal write at all**. That is consistent with "there were no bursts",
and it is *also* consistent with "the hook wrote nothing", because the journal
is written only by the failure hook (§9.1, lines 518-522) and a silent hook
and a quiet database leave the same file. Nothing in this measurement
separates them. `K = 0` is a statement about the journal; the journal's own
liveness after 2026-08-31T11:01Z is assumed, not shown. (It also tightens
§1.2's floor: with zero post-`T0` lines of any kind, the post-`T0` UNCOUNTABLE
class is empty *as a matter of the file*; the instrument still does not say
so, and the shortfall stands.)

## 2. The preconditions, each by name, at both readings

§6.3 conditions FIX CONFIRMED on *"every precondition C1 to C6 of §7"* (lines
413-415), and a failed one is *"never shortened to UNRESOLVED alone"* (lines
418-420). The instrument implements that at `inspect_live_db.py:2891-2903`: a
precondition that is uncomputable is not a pass, and every failed name is
carried into the verdict string.

| check | 16:26Z (look) | 19:01Z (re-read) | note |
|---|---|---|---|
| C1 `poll_log` spans the window | PASS | PASS — MIN 2026-08-18T08:16:53Z ≤ `T0`; MAX 2026-09-02T19:01:25Z ≥ newest burst (**S**) | |
| C2 `T0` exists | PASS | PASS — 2026-09-01T17:52:17.849Z | |
| C3 restart coverage | PASS — 214 aged cycles | PASS — `A_pre` = 0.87 h, median of 11 aged pre-fix bursts of 13; **235** fast cycles at age ≥ `A_pre`, need 30 | the 2.0 h fallback (line 457) was not needed at either |
| C4 WAL comparability | **FAIL** — 2,699 vs 2,711 | PASS — 2,711 vs 2,711; n = 2,002 / 1,859 | a FAIL by 12 KB (0.44%) that became a PASS by 0 KB; `c4_ok` is `>=` (`:2821-2825`) |
| C5 victim tempo | **FAIL** — 73.92/h vs 56.81/h (+30.1%) | **FAIL** — 79.64/h vs 56.81/h (+40.2%); ceiling 71.01/h (**D**) | two-sided ±25%; the direction is *busier* at both |
| C6 `lambda_0` supports `E*` | PASS | PASS — `E*` stays 160 | **the `"PASS"` string is a hardcoded literal** (`:3021`); C6 is never in the failed-precondition list (`:2891-2897`). §6.3 below |

**C4 flipped between the readings and C5 moved away.** Nothing was changed
between them; the post-`T0` WAL median moved 12 KB on ~335 more samples (§4's
derivation; the printed `n` went to 2,002). A comparison sitting on its own
threshold does this, and the 16:26Z entry in `tasks/NEXT.md` was right to say
*"do not treat this as a finding about WAL"*. C5 went the other way, and §4
has the arithmetic.

## 3. The verdict, and the case against it stated in full

    VERDICT   UNRESOLVED — C4/C5     at the registered look, 16:26Z
              (§7: WAL-CONFOUNDED, line 465; TEMPO-CONFOUNDED, line 470)

    re-read   UNRESOLVED — C5        at 19:01Z, unregistered

**What §10's UNRESOLVED branch requires recorded** (line 585; Amendment 1 A3,
line 707 — *"Nothing credited; `E`, `K` and the failed precondition
recorded"*):

    E                      263 fast cycles post-T0 at the look (294 at the re-read)
    K                      0 bursts at both
    failed preconditions   C4 — WAL comparability, 2,699 vs 2,711 wal_kb (look only)
                           C5 — victim tempo, 73.92/h vs 56.81/h at the look,
                                79.64/h at the re-read; tolerance ±25% two-sided

### 3.1 Against interest: what the evidence would license if §7 were not there

At both readings, every clause of §6.3's FIX CONFIRMED except the
preconditions holds:

- `E >= 160` — 263 at the look, 294 at the re-read.
- `K = 0` — no burst of any kind, fast or mirror, in the whole post-`T0`
  exposure, subject to §1.2's two caveats on what the journal can show.
- `E_n < 200` — 1.0000; no FAST-matched burst exists to move it.
- C1, C2, C3, C6 — hold at both; C4 held at the re-read.

Under the planning `lambda_0 = 0.0338` (§0.1, line 45), the one-sided exact
binomial of §5 gives `P(K = 0 | rate unchanged) = (1 − 0.0338)^263 ≈ 1.2 ×
10⁻⁴` at the look and `≈ 4.1 × 10⁻⁵` at the re-read — both well inside the
0.005 the registration asked for.

And the precondition that fails at both readings fails in a direction §7 did
not name as the confound. §7's stated worry for C5 is *"Fewer passes means
fewer collisions regardless of the fix"* (line 467). The post-`T0` arm carried
**more** passes — 30-40% more victim writes per hour landing on the same
database. §3.2(2) argues that is more collision opportunity, not less; §6.2
records that the argument is not established. A reader who saw only `C5 FAIL`
would assume the flattering direction. It is the other one.

**That is the strongest form the evidence could have taken, and it is exactly
why it may not be written up as FIX CONFIRMED.**

### 3.2 Why the registration wins anyway

Three reasons, in descending order of how much they matter:

1. **The tolerance was registered two-sided, before the data, and the
   registration says a rule chosen afterwards is the freedom it exists to
   remove.** §7 C5 reads *"within plus or minus 25%"* (lines 468-470) and the
   instrument implements `abs(post_tempo - pre_tempo) / pre_tempo <=
   C5_TEMPO_TOLERANCE` (`inspect_live_db.py:2840-2845`;
   `tests/test_forward_lock_instrument.py::test_a_doubled_pass_tempo_also_fails_c5`
   pins the shape, and goes red under a one-sided mutation). §1 fixes the
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
   registered, and plausible-and-unregistered is what §6.1 calls manufacturing
   a positive. (The ADR's ground (b) adds a sharper version: one candidate
   driver of the tempo change is ADR 0091's own fix.)

3. **`E_n = 1.0000` is silence, not exoneration, and §1 already said so.** The
   signature arm *"cannot clear, for the same reason the attribution design
   could not: an absence of in-band bursts is what its null predicts anyway"*
   (lines 119-122). Only the rate arm can credit the fix, and the rate arm is
   the one C4 and C5 guard.

So: **UNRESOLVED**, named. Not "no signal", not "the fix did nothing" — §0.3
forbids that reading in as many words (lines 77-80) — and not FIX CONFIRMED.

## 4. Why C5 is moving away, from the instrument's own arithmetic

`post_tempo = lines_per_hour(t0, None)` and
`pre_tempo = lines_per_hour(None, ADR_0091_DEPLOY_MS)`
(`inspect_live_db.py:2838-2839`). `lines_per_hour` (`:2828-2836`) is
`len(window) / span_h` over every `loop_rss.jsonl` sample in the window, the
span running from the window's first sample to its last — so `post_tempo` is
a **cumulative mean from `T0` to the newest sample**, against a pre-fix mean
over a **fixed** window whose edge is `ADR_0091_DEPLOY_MS`
(2026-08-31T15:29:19Z, `:2383`).

### 4.1 The marginal rate between the two readings

    16:26Z   22.56 h post-T0   73.92/h   ->  ~1,668 lines
    19:01Z   25.15 h post-T0   79.64/h   ->  ~2,003 lines
    marginal, 16:26Z-19:01Z    ~335 lines / 2.59 h  =  ~129.5/h

Two cross-checks on the derivation: the 19:01Z product reproduces the
instrument's printed `n = 2002` to within a line, and `E` going 263 → 294 is
31 fast cycles at the planning `C = 300.415 s` = 2.588 h, agreeing with the
2.583 h of wall clock between the readings to 0.2%.

The runner was writing at roughly **2.3× the pre-fix tempo** in that window,
and a cumulative mean can only approach a marginal rate that high from below.
From where the mean stood at 19:01Z, coming back inside the ceiling takes
about **15 h at exactly the pre-fix tempo** (56.81/h) or about **7 h at
40/h** — and every hour above 71/h pushes those out. **A silence does not
move the mean at all**, because the span ends at the newest sample; what a
silence buys is a *gap* which, once broken by a single line, puts the mean
under the ceiling — **3.08 h** of gap from the 19:01Z state.

### 4.2 The baseline is leaving the file, in hours

`loop_rss.jsonl` is capped at 2 MiB and trimmed to the newest whole lines
within 1 MiB once it crosses (`RSS_LOG_CAP_BYTES`, `RSS_LOG_KEEP_BYTES`,
`scripts/run_loop.py:175-176`, deployed 2026-09-02). **The pre-fix window
survives the first trim if and only if it is itself larger than
`RSS_LOG_KEEP_BYTES`.** It is not: the pre-fix block is at most 1,859 samples
carrying `wal_kb` plus the 708 lines that predate the field
(`tests/test_forward_lock_instrument.py:434-437`, from a 5,532-line snapshot)
— **≤ 2,567 lines ≈ 736 KB** at the 286.6 B/line `run_loop.py:155-161`
measured on 2026-09-01, and still under 1 MiB at 400 B/line. Margin 30-45%
whichever width is right, and the width error runs the same way: a wider line
makes the block bigger but makes the trim come sooner too.

**Reconciling the size estimates, because three are in the record.**
`run_loop.py:160-161` measured 4,047 lines / 1,159,863 B on 2026-09-01 and
projected the cap for about 2026-09-04 at ~379 KB/day. The first draft of this
file estimated "roughly a day" from the 19:01Z sample counts at 286.6 B/line.
**Measured at ~19:40Z on 2026-09-02, live `/data/loop_rss.jsonl` was
1,900,412 bytes — 90.6% of the 2,097,152-byte cap** — so the trim is
**hours** away, not a day. The preserved copy (below) is 6,066 lines /
1,900,780 B = **313 B/line**, wider than the 286.6 the projection assumed;
the `wal_ckpt_*` fields and `produced_by` widened the line, and that is the
whole difference between "09-04" and "tonight". The direction of every
estimate here is *sooner*.

When the trim fires, `pre_tempo` and `pre_wal_q25` become `None`, C4 and C5
report NOT COMPUTED, and C3's `A_pre` falls to the 2.0 h fallback. NOT
COMPUTED is not a pass (`inspect_live_db.py:2849-2856`), so the deployed
instrument will then read UNRESOLVED — C4/C5 regardless of tempo, and a quiet
period after that point restores nothing on the box.

**The baseline was preserved, out of the repo.** At ~19:40Z a copy was taken
with `flyctl ssh sftp get /data/loop_rss.jsonl` to
`data/live-snapshots/loop_rss-2026-09-02T19Z.jsonl` on the dev machine —
6,066 lines, 1,900,780 bytes, first line `ms = 1788026590715`
(2026-08-29T18:03Z), so it holds the whole pre-fix window — with
`loop_failures.jsonl` beside it. `data/` is gitignored (operator data never
enters the repo), so the copy exists on that one machine only. The loss is
therefore **avertible, and averted for the local copy; the deployed
instrument still loses it.**

## 5. What this reading closes, and what it does not

- **It does not credit ADR 0091.** Nothing in §10's UNRESOLVED row credits
  anything, and Amendment 1 A3 left that row *"Unchanged"* (line 707).
- **It does not refute ADR 0091.** `K = 0` on 263 or 294 cycles is not a
  refutation of anything, and `H = 0` cannot be one by §1's own argument.
- **It does not raise `E*`.** C6 holds on the planning value; `E*` stays 160.
- **It does not amend C5.** See §3.2(1). The tolerance stands at ±25%,
  two-sided, in `C5_TEMPO_TOLERANCE` (`inspect_live_db.py:2397`) and in the
  registration (lines 468-470).
- **It does not open the §0.4 successor.** That registration was *"not
  authorised here"* at line 100 and was killed by the partner on 2026-09-01
  (`tasks/NEXT.md`, the 2026-09-02 entry's "Killed by the partner" paragraph).
- **It does not license a third reading.** §6.2's single look was the 16:26Z
  one; the 19:01Z re-read is reported as what it is.

What happens to P5 as an open item is a **ruling**, not a measurement, and it
is in the draft ADR beside this file rather than here.

## 6. What this does not establish

Per CLAUDE.md's measurement rules, and checked against the schema rather than
written as modesty:

1. **That the `database is locked` symptom is gone.** `K = 0` is a statement
   about the chain runner's own failure hook over ~25 h of exposure on one
   tempo, through a journal that has written nothing of any kind since
   2026-08-31T11:01Z (§1.2). §9.1: lock failures inside the poller,
   `bid_watch`, `hedge_watch` or the API never reach the journal; the absolute
   rate is a floor.
2. **That the busier arm is a *harder* test rather than a *different* one.**
   §3.2(2). The direction argument is stated against interest and is not a
   registered finding.
3. **That C6 was measured.** The instrument's `"PASS"` for C6 is an
   unconditional string literal (`inspect_live_db.py:3021`) and C6 never
   enters the failed list. Its `lambda_0` is `k_count / e_count` (`:2733`) —
   the *post-`T0`* rate, zero at `K = 0`, which falls back to the registered
   `E*` by construction (`:2742-2746`). §0.1 says the instrument *"recomputes
   `lambda_0` from `poll_log` at analysis time"* (lines 49-51), meaning the
   pre-fix rate; as built it does not, so C6 passes on the planning value
   0.0338 rather than on a measurement, and the binomial figures in §3.1 are
   on that planning value too. A §11 shortfall; it would matter only on a FIX
   CONFIRMED branch neither reading reaches.
4. **That C4 holds in any sense stronger than "equal on the re-read."** It
   failed by 0.44% at the look and passed by 0 KB three hours later. Two
   windows whose WAL medians coincide to the kilobyte are near-identical arms,
   and a third reading could put it either side again.
5. **That 56.81/h is *the* pre-fix tempo.** It is the mean over whatever
   pre-deploy lines the capped file held on 2026-09-02, from the file's first
   line (2026-08-29T18:03Z on the preserved copy) to `ADR_0091_DEPLOY_MS`;
   that start is not a registered boundary. The comparison is
   registration-fixed at its *edge* and file-dependent at its *start*.
6. **Anything about the 2026-08-31T15:29Z .. `T0` interval.** §2.2 excludes
   it from both arms, and §1.2 records that it is empty. (§2.2, line 164,
   describes `T0` as *"roughly nineteen hours"* after the deploy; it is 26.4 h.
   `inspect_live_db.py:2573`'s docstring repeats the "~19 hours". `T0` is
   derived from the database, so the arms are unaffected; both sentences are
   off by seven hours and are noted rather than corrected here — the
   registration is a registered file and the script is not this lane's to
   edit.)
7. **Anything about the retention prune or the `TRUNCATE` checkpoint** —
   ADR 0091's named remaining suspects. §10's FIX CONFIRMED row was the only
   branch that bought *"the right not to chase two suspects nobody has
   scheduled"* (Amendment 1 A3, line 704), and it was not reached.
8. **That the verdict would survive a re-read.** It is expected not to, on
   §4's projection and in §4's direction: a later reading shows C5 further
   out, or NOT COMPUTED once the trim fires. This file records two readings;
   it does not promise the number is stable, and it does not license taking a
   third.
