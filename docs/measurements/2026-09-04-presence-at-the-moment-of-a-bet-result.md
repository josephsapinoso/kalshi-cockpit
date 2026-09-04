# RESULT — UNRESOLVED — CONCENTRATION: is the desk present at the moment Joe actually bets?

**Registration:** `2026-09-03-presence-at-the-moment-of-a-bet-registration.md`,
with Amendment 1 (§A–§F). **Analyzer:** `scripts/analyse_bet_presence.py`.
**Look taken:** 2026-09-04, on four `inspect_live_db.py --json` captures written
01:13–01:14Z (after `W_end = 2026-09-04T00:00:00Z`). **Audited** by
`measurement-skeptic` before this file was written; its four blockers are
addressed below and its wording corrections are applied.

This is an operator-behaviour reading, `n = 1` operator. It enters no signal
record and no sentence here may be quoted about edge, `beta`, the gate or the
fee bar.

## 1. The registered verdict

    VERDICT   UNRESOLVED — CONCENTRATION

The primary arm cleared and the mandatory §3.3 leave-one-day-out did not
survive under every admissible reading of "the largest-contributing budget
day". Under §6.3 that is a downgrade, and it is the whole of the verdict.

## 2. What was measured

Window `[2026-08-25T16:03:35Z, 2026-09-04T00:00:00Z)`, `W_start = MIN(seen_ms)`
over `desk_attention`. 69 desk visits at the inspector's 300,000 ms gap.

    population                       post-exclusion
      hand fills in section C          62
      UNCLASSIFIABLE (pre-W_start)     33
      taker, in window                 27   -> the primary
      maker, in window                  1   (descriptive only)
      EXCLUDED-BY-TICKER                1   (a maker fill; the primary is unchanged by the exclusion)
      engine                            0
    §2.4 exclusion (Amendment 1 E0–E4)
      manual_orders real rows           0
      desk combo orders |O|             5   4 CLEARED-BY-VENUE (cancel_reduced_by == count), 1 residual
      RESIDUAL CONTAMINATION BOUND      1 order, 1 fill excluded — zero taker fills

    S = 12 sittings at 60 min   D = 7 budget days
      S at 30 min 12, at 120 min 11 (the unit is not gap-sensitive)
      fills per sitting  [4, 3, 1, 1, 4, 3, 1, 3, 1, 1, 3, 2]   largest 14.8%
      sittings per day   {08-25: 2, 08-26: 3, 08-27: 1, 08-28: 3, 08-30: 1, 08-31: 1, 09-03: 1}   largest 25.0%

**The four registered tests** (alpha 0.005 each, family-wise 0.02):

    B5  (±5 min, primary)   K = 8 of 12
        gap arm       p_gap  = P(K <= 8 | 12, 0.5) = 0.9270      not cleared
        presence arm  p_perm = 0.0004  (10,000 day-shift draws, seed 20260903)   CLEARED
                      critical value under the realised null k* = 7; observed 8 — one sitting of slack
        theta_wall = 0.124 (descriptive; the permutation's own chance coverage is 0.216)
    B30 (±30 min, secondary) K = 8 of 12
        gap arm       p_gap = 0.9270                             not cleared
        presence arm  p_perm = 0.0203                            not cleared

**Leave-one-day-out (§3.3), on the primary.** Two budget days tie for largest
at 3 sittings each, so both are dropped in turn:

    drop 2026-08-26 (3 sittings)   K = 7 of 9   p_perm 0.0001   -> PRESENCE GAP REFUTED
    drop 2026-08-28 (3 sittings)   K = 5 of 9   p_perm 0.0163   -> UNRESOLVED — NEITHER ARM CLEARED

The verdict flips under the second. **Downgraded to UNRESOLVED — CONCENTRATION.**

Distances from each sitting's first fill to the nearest visit, in minutes:
`0, 0, 0, 0, 0, 0, 0, 0, 36.8, 70.9, 101.4, 171.9`. Zero sittings within 60 s
of a band edge (closest 5.41 min), so C6's skew assumption does not bind.

## 3. The defect the audit caught, and why the verdict is the downgrade

The analyzer as first run broke the two-way tie with `max(per_day,
key=per_day.get)`, which returns the first tied key in insertion order — the
earlier day — and that day happened to be the one whose removal leaves the
verdict standing. The other tied day holds **3 of the 8 inside-visit sittings**,
the largest single contribution to `K`, and dropping it does not clear. Nothing
in the registration chose between the two; §3.3 and §6.3 say "*the*
largest-contributing budget day", a definite article over a set of two.

The analyzer now drops every tied day and downgrades if any flips
(`test_a_tie_for_largest_day_drops_every_tied_day_and_downgrades_if_any_flips`,
mutation observed red by restoring the single `max()`). This is the
conservative reading and the only one that does not let dict order resolve a
registered downgrade. Under Amendment 1 §C a further repair-and-re-run is
terminal for this registration; none is taken. The statistics above are the
single computation of the decision statistic this registration permits, and
they are unchanged by the fix — only the downgrade's application changed.

**The concentration is real, not a technicality.** Two budget days (08-25 and
08-28) supply 5 of the 8 inside-visit sittings — 62.5% of the evidence from 2
of 7 days. Three of seven single-day drops return UNRESOLVED. The pooled
8-of-12 does not survive the parts test, which is exactly what §3.3 exists to
detect.

## 4. Preconditions

- **C1** `S = 12 >= 8`, `D = 7 >= 5`. Met. §0.3's presence-arm power table has
  no `S = 12` row; the realised critical value is `k* = 7`, which the
  measurement met by one.
- **C2** `visit-freshness --since 20260801`, before schema v21. Met.
- **C3** No section truncated. Met (section C 62 rows, combo tail 5 of 500).
- **C4** (as re-worded in Amendment 1 §B.4) Executed by venue clearance on 4
  orders and ticker attribution on 1; excluded 1 maker fill and 0 taker fills.
  Met.
- **C5 — NOT EXECUTED. The population is declared a FLOOR.** `poll_log WHERE
  endpoint = 'fills'` is emitted by no subcommand; the only `poll_log` section
  in the captures is `endpoint = 'balance'`. Per §7 the verdict may still be
  declared with §9.6's direction stated: fills lost to an outage read as
  desk-**absent**, biasing toward the gap arm (which did not clear) and away
  from the presence arm (which did). The bias does not favour the result.
- **C6** `|skew| <= 60 s` assumed; closest sitting to a band edge 5.41 min.
  Met with margin.
- **E0** All four captures written after `W_end` (01:13:20Z–01:14:28Z on
  2026-09-04, filesystem write times corroborated by the git chronology:
  analyzer commit 01:13:01Z, amendment commit 01:30:06Z, run 01:30:12Z).
  Amendment 1 §A.3's claim that the read was early was the author's local date
  and is superseded by §F. **These four captures carry no `generated_at`, so
  E0 rests on file metadata and the commit chronology, not on anything
  tamper-evident.** That is a fact about this look and not about the
  instrument from here on: `inspect_live_db.py --json` stamps
  `generated_at_ms` and `generated_at` from the server clock as of
  2026-09-04, and the analyzer prefers that stamp and prints which clock it
  used, falling back to the file mtime only when the key is absent. Re-running
  the analyzer after that change reproduces every figure above and adds only
  the four provenance lines, each reading `from mtime`.

**§8's blind re-check of §10.** §10 was re-read in full at ~01:05Z on
2026-09-04, before the analyzer was written and before any capture was taken,
as part of reading the whole registration — and that re-read was not written
down at the time, which the audit correctly flagged. It is recorded here after
the fact: §10 stood unchanged. Because the verdict is UNRESOLVED, §10's action
row for it is *"nothing is funded on presence, and nothing is killed"*, so the
undischarged recording changes no action.

**Looks at the decision statistic: one.** The first run (2026-09-04T01:1xZ)
returned at the exclusion branch above the first distance computation, in code
(`d2f51de:scripts/analyse_bet_presence.py` line 498 returns, line 512 is the
first `distance_ms`). The second run computed the statistics once; the
tie-break fix re-applied §3.3 to the same numbers.

## 5. What survives, said the only way it may be said

> On 27 taker hand fills **on Kalshi** forming 12 sittings across 7 budget
> days between 2026-08-25T16:03Z and 2026-09-04T00:00Z, the first fill of 8
> sittings fell inside a `desk_attention` visit. A day-shifted permutation
> holding hour-of-day fixed puts the chance rate at 2.60 of 12 (`p_perm =
> 0.0004`, `k* = 7`, robust across 8 seeds and to 200,000 draws). The eight
> containing visits were 2.7 to 31.1 minutes long, with the fill landing 1 to
> 9 minutes after the visit opened — none of the five multi-hour visits
> contains a sitting, so the co-occurrence is not a tab left open. Zero
> sittings sit within 60 s of a band edge, and the circularity exclusion
> removed no taker fill.
>
> **The registered verdict is UNRESOLVED — CONCENTRATION**, because 5 of the 8
> inside-visit sittings come from two budget days and the finding does not
> survive dropping one of them. Descriptively, the hypothesis that the desk is
> *essentially never* present at a Kalshi hand bet — the partner's hypothesis
> as §0.3 states it — is not what the record shows: the desk was open at
> two-thirds of sittings, about three times the day-shifted chance rate. A
> third of sittings had no desk within 5 minutes, and in three of them none
> within an hour.

What it does not extend to: whether the desk *caused* the bet (§9.1); **his
bets off Kalshi**, which `fills` cannot see (ADR 0078 exists because he places
sportsbook parlays); what the open screen said — *presence is necessary for the
job and is not the job* (§9.7); a reader as opposed to a tab (§9.3 — though the
visit durations above make that reading unlikely for these eight); or any month
but this one (§9.8).

**Wording the audit forbids, and this file obeys:** `p_perm = 0.0004` never
appears without `k* = 7`; "the desk is at the moment of a bet" does not stand
alone; "does NOT survive B30" is explained — the identical 8 sittings are
present at both bands, and B30 fails only because a wider halo raises the
null's chance coverage from 0.216 to 0.345 while adding no observation. B30 was
registered to catch the deliberate app-switch case and caught zero additional
sittings, which is its own small finding.

## 6. What this buys, under §10

**UNRESOLVED: nothing is funded on presence, and nothing is killed.** `S = 12`,
`D = 7` and the failed downgrade are recorded so a successor starts from a
number. §8's extension does not fire — its trigger is `S`/`D` only and both
are above floor — so this registration is **closed**. A successor, if the
question is worth reopening, must fix the tie-break rule and the
leave-one-day-out's exposure at `D ≈ 7` in advance, and §0.3 already prices
the middle case (`p ≈ 0.5–0.7`, which is where 8/12 sits) at ~25 sittings.

For planning, the partner's premise — "the desk is not present at the moment he
bets, so build presence" — is not supported by the record and no work on it may
be funded from this measurement. Equally, "presence is solved" may not be
written. What the descriptive result does license is a different question:
when the desk *is* open at a bet (8 of 12 times here), what does the screen he
has open say, and does it say the thing ADR 0071 §2.2 names as the job.

## 7. Free riders (§11.4)

Not built and not reported. The inspector has no subcommand for the seven
census counts and the registration says nothing is blocked by their absence.

## 8. Instruments and files

- Captures (gitignored, dev machine): `data/live-snapshots/presence-*-20260904.json`.
- Analyzer output: `data/live-snapshots/presence-analyzer-output-20260904.txt`
  (reproduces byte-identically; the skeptic re-ran it).
- Analyzer: `scripts/analyse_bet_presence.py`; tests
  `tests/test_analyse_bet_presence.py` (21, including the tie-break pin).
- No ticker string, price, size, fee or P&L appears in this file, the analyzer
  output, or the audit.
