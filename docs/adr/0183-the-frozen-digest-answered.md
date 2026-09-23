# 0183 — the frozen digest, answered: seven tickets and one new question, 2026-09-23

**Status:** Accepted on Joe's answers, 2026-09-23 ~20:00Z. He gave them one
ticket at a time with option buttons (`AskUserQuestion`), recommendation
first. Numbered 0183 on `main` after `git fetch`, 0182 being the highest.
**Date:** 2026-09-23
**Schema:** none.
**Tickets:** #127, #119, #71, #78, #79, #97, #122 (map #3). The new question
has its own build task under #80.
**Amends:** ADR 0180 (the watcher's population and its daily allowance on
live); ADR 0054's `kalshi_quotes` exemption (now bounded); the
`SHARD_HEADROOM` paragraph behind ADRs 0164/0165.
**Leaves standing:** ADR 0112 (no ceiling of ours on a hand bet); ADR 0115
(no resting offers); ADR 0178 §7 (`fee_cost` unread); ADR 0088 (the scout
flags a leg and never gates one; no per-leg paid button).

---

## 1. Why he asked: "why isn't the desk reviewing my parlays?"

Two reasons, and only the first is about budget.

1. **The day's tokens were gone.** Live `/api/scout` read at 19:47Z showed
   `tokens_today` 525,808 against `AGENT_MAX_TOKENS_PER_DAY` 500,000, after
   three unattended convenings (briefings 15, 16 and 17). The tap path checks
   the ceilings directly, so his own taps are refused until the 10:00Z roll.
   This is #127's finding, seen on a second day.
2. **The desk never looked at his parlays.** A convening briefs one game.
   The unattended watcher read only the desk's own ladder cards
   (`scout_watch.py`, `build_ladder_payload_widening`). Nothing read
   `parlay_positions`. A KXMVE ticker cannot be resolved to a fixture at all
   (`_resolve_scout_fixture` joins through `recommendations`). The Skeptic
   reviewer was retired by ADR 0062 and deleted by ADR 0106, and it only
   ever looked at single markets.

## 2. The answers

| ticket | question | answer | what changes |
|---|---|---|---|
| #127 | unattended scouting spends the whole token day | **(B) 2 a day, not 3** | `fly.live.toml` `SCOUT_AUTO_MAX_CONVENINGS_PER_DAY = "2"`; the code default stays 3 |
| #119 | a quiet tonight sends the watcher to tomorrow's games | **(b) tonight's games only** | the watcher reads `build_ladder_payload`, not the widening builder; the screen still widens |
| new | the desk never scouts parlays he holds | **held parlays first** | the watcher tries fixtures from open positions' pending legs (tonight's horizon) before the ladder; same brakes, one convening a cycle |
| #71 | the combinations shard keeps a 10% margin | **(A) 99%** | `SHARD_HEADROOM = 0.99`; the refusal's figure is now FLOORED to the cent (see §3) |
| #78 | an accepted quote might rest a remainder | **(a) accept the risk** | nothing; 11 of 11 accepts filled whole on 09-18 and the venue defaults against partial fills |
| #79 | the parlay builder multiplies suppressed legs | **(a) refuse them outright** | a leg whose side carries a `suppressed_reason` never enters the pool |
| #97 | a combination fill's `fee_cost` is unread | **(a) leave it unread** | nothing; ADR 0178 §7 stands |
| #122 | the recommended-market quote exemption has no age | **(A) bound it at 60 days** | `prune_quotes` deletes a recommended ticker's quotes after 60 days; `prune-frontier` counts them |

## 3. One defect found while building #71

The refusal printed the wall with `:.2f`, which rounds. At 0.90 the example
shard ($3.9359 → $3.5423) happened to round down. At 0.99 it walls at
$3.8965 and printed **"$3.90", a figure the same check then refuses.** The
number he is told he can ask for is now `floor` to the cent. The test
`test_nearly_all_of_the_shard_can_be_asked_for` asks for the printed figure
and must pass. It went red when the floor was removed.

## 4. What #122 does not do

It returns no disk. With no `VACUUM` (#58), freed pages are reused, so the
exempt share stops rising. Closing-line work older than sixty days loses its
Kalshi series: that is the decision, not a side effect. The kalshi_quotes
prune and #139's odds_snapshots prune both take the write lock on the slow
cadence, and on the first night both have backlogs.

## 5. What #127's answer does not settle

It does not settle which ceiling binds first. #118 read D (not separable).
Two convenings are ~350K tokens on the two measured days, which leaves
roughly one tap. Any reading of that is a new look (#137's instrument, a new
registration).
