# 0076 — The parlay push becomes a schedule and a debounce

**Date:** 2026-08-27
**Status:** Accepted.
**Owner of the decision:** Joe. Asked what time the card should land and how
many pushes a day at the worst, he chose **4pm Eastern** ("most MLB and WNBA
slates are set, evening games haven't started") and **keep 6 total**.
**Overrides** ADR 0072's "one mechanism, same event seen twice".
**Touches nothing decided by** ADR 0038 (the hunt is closed), ADR 0071 §2.5
(no ranking by the gap), or ADR 0071 §2.4 (no tap-to-buy in a chat client).

## 1. What ADR 0072 got wrong, and it was not the dedupe

ADR 0072 shipped parlay cards to Discord and treated Joe's two stated triggers
— a daily card and a material-change alert — as **one mechanism**.
`scripts/run_loop.py` said so in its own words:

> *"The daily card is the first build after the slate turns over; the
> material-change alert is any later pass whose legs differ. Same event seen
> twice, so one call rather than a scheduled push plus a watcher that could
> disagree with it."*

That is elegant and it is false, and the measurement is on live. The day's
whole push ceiling was spent in **four minutes**:

    22:41:43Z  safe: LADATL-LAD | BOSMIA-BOS | MILNYM-MIL   (all MLB)
    22:45:10Z  safe: CHICONN-CHI | PDXDAL-DAL | GSCONN-GS   (all WNBA)

The card composition swapped sport entirely and all three rungs re-pushed.

**Both pushes were correct under the dedupe rule.** `notifications
UNIQUE (kind, key)` did exactly what it was built to do; the legs really had
changed. The cause is upstream: sports are swept on **independent clocks**,
`build_ladder` drops legs whose consensus is older than `MAX_ODDS_AGE_S`, and
the ranking is by probability. So a sport enters the pool when it is swept,
leaves when it ages out, and whichever sport is currently fresh owns the top of
every card. The 22:21Z payload carried `excluded: {"stale_consensus": 7}`.

**The specific error is that "the first build after the slate turns over" is
the least trustworthy build there is**, not the most. It is the one most
contaminated by which sport happened to be swept last — and a deploy or a
day-roll is exactly when that is most arbitrary.

## 2. The decision: two channels

### 2.1 A scheduled card, `kind = 'parlay_daily'`

Fires on the first ladder build at or after `PARLAY_CARD_UTC_HOUR`, keyed on
`<day_start_ms>:<card_key>` so it goes once per rung per **budget** day.
Budget day and not calendar day, for `daily_digest`'s reason: a boundary that
disagrees with the credit meter's would split one night's slate across two
reports.

**Immune to churn by construction rather than by policy.** Whatever the ladder
says at the stated hour is the day's card. It is deliberately **not** debounced
— a debounce could delay or skip the one push that is supposed to be
guaranteed, and Joe picked the hour on the basis that the card would be there.

**The cost is stated rather than hidden:** the scheduled card can land on a
composition that would not have survived the debounce. It is bounded to one
ladder a day, which is what makes that acceptable.

**20:00Z is 4pm Eastern only while EDT is in force.** From the first Sunday in
November the same constant lands at 3pm Eastern. That is written into
`configured_parlay_card_utc_hour`'s docstring and `.env.example` rather than
left to be discovered in the winter. A UTC hour is what the budget day already
cuts on and what a loop with no locale can act on; a card that tracks a local
hour across a DST boundary is a different and larger decision.

### 2.2 A two-build debounce on the change channel

A composition must hold for `PARLAY_DEBOUNCE_BUILDS = 2` **consecutive** ladder
builds before `kind = 'parlay_card'` will announce it. An alternation then never
announces, because neither composition ever repeats back to back.

**Consecutive, and that is the whole design.** "Seen twice ever" is satisfied by
exactly the pattern being suppressed: under churn the same two compositions
alternate, so each is seen many times. State is one row per card slot in
`parlay_card_candidates` (schema v23), **replaced** on a different key rather
than accumulated, and **deleted** when the slot builds nothing — appear, vanish,
reappear is not two in a row.

**A table and not a dict**, for `notifications`' own argument: this box
restarts, and a policy that forgets on restart re-announces on restart. The
live failure was found *after a deploy*.

**The cost:** a composition waits one build. Builds are gated on
`counts.odds_sweeps > 0 or kind == "full"`, so ~10 minutes while someone is
looking and up to an hour when nobody is. That delay is the feature. The gate
is also what makes the debounce mean anything — counting byte-identical
rebuilds towards a run would let a quiet slate satisfy it by doing nothing.

### 2.3 The ceiling is now a day total across two channels

`MAX_PARLAY_PUSHES_PER_DAY` drops **6 → 3** and counts the change channel only.
The scheduled card does not spend it and cannot run away: its own key bounds it
at `len(PUSHED_CARD_KEYS)` a day. 3 + 3 keeps the worst-case day exactly where
the original constant's reasoning put it ("six is two full ladders"), which is
the number Joe answered when the split was put to him.

`test_the_two_channels_sum_to_the_total_joe_chose` asserts the **sum**, because
that is what he decided: moving either half while preserving the total is a
refactor, moving the total is his call.

### 2.4 A scheduled push burns the change key for the same composition

The two channels have different `kind`s, so `UNIQUE (kind, key)` does not see
across them. Without this the card sent at the stated hour is re-announced by
the change channel as soon as it has held two builds, **having changed
nothing** — the split would double every card it exists to de-duplicate. So a
scheduled send also claims `('parlay_card', parlay_key(card))`.

Claimed even on a **failed** delivery, because a change alert re-sending what
the daily card could not deliver would arrive as if the card had changed.

**The asymmetry runs one way only.** A change alert earlier in the day does not
stop the scheduled card re-sending the same legs at the stated hour. The daily
card is the product; the change alert is a nudge. At most one duplicate a day
is the price, and it is inside the ceiling Joe chose.

### 2.5 `held` is a fourth outcome, not a flavour of `skipped`

A card waiting out the debounce was a genuine candidate that was **not**
deduped. Filing it under `alerts_deduped` would report the dedupe working when
what is working is the debounce, and the two have opposite remedies: a stuck
`skipped` means the ladder is rebuilding identically, a stuck `held` means it is
churning. Same distinction `PUSHED_CARD_KEYS` already draws for screen-only
cuts, which are neither sent nor skipped — and are not tracked at all, so a key
promoted into the pushed set later starts from zero rather than inheriting a run
it never earned.

## 3. What this does not decide

- **Whether the three screen-only cuts join the phone.** `PUSHED_CARD_KEYS`
  stays `{safe, middle, lottery}`. Six rungs against a 3-push change ceiling
  and a 6-slot day is a separate decision about Joe's attention.
- **Whether the debounce should be longer than two.** Two is the smallest number
  that suppresses an alternation, which is the shape the churn actually has.
  Raising it is cheap and needs a reason from the record, not from taste.
- **Anything about whether a card is worth buying.** No edge is claimed anywhere
  in this path and none was measured (ADR 0038). This changes *when* a card is
  announced and never *which* card, and in particular introduces no ordering —
  ADR 0071 §2.5 forbids ranking by the consensus-vs-Kalshi gap and nothing here
  ranks by anything.

## 4. How it was verified

- **Twelve mutations observed red**, including replacing rather than
  accumulating the run, not deleting the row on an unbuilt slot, comparing only
  the leading ticker, and dropping the change-key burn.
- **Two mutations came back GREEN and were not kept as passes.**
  1. *Re-query the ceiling per card instead of incrementing locally.* The code's
     own comment claimed this was a guard. It is not: `_send` commits before
     returning, so a re-query sees exactly what the increment counted. The
     comment and the test docstring were corrected rather than the mutation
     dropped — the claim was wrong and the record says so.
  2. *Let the scheduled card spend the change ceiling.* The test asserted the
     **ledger** (`_parlay_pushes_today == 0`) where the property is
     **behavioural**. A new test drives the one narrow state in which the two
     channels meet — one rung taking the scheduled branch while another falls
     through settled, in the same call — and that one is red.
- **Driven against a real payload**, not hand-written card dicts: a seeded
  database, `build_ladder_payload`, and a `DiscordNotifier` with only `_post`
  stubbed. Held, released after two builds, silent on the third, scheduled card
  at 20:00Z on its own key, silent for the rest of the hour. Six embeds on the
  worst-case day, which is the number Joe chose.
