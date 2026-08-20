# The mid-window cadence dropouts are the freshness measure working, gated by one laggard book

Taken 2026-08-20 ~19:30Z, against the live database via the new whitelisted
`window-freshness` query (`scripts/inspect_live_db.py`, shipped to live in
`faa46b9`). Artifacts, committed beside this file:

- `2026-08-20-window-freshness-at-dropout1.json` (`--at 2026-08-20T15:28:55Z`)
- `2026-08-20-window-freshness-at-dropout2.json` (`--at 2026-08-20T16:18:50Z`)

This was the top open item of the 2026-08-20 17:00Z handoff: two mid-window
cadence dropouts, 15:28:50→15:34:54 (~370s) and 16:18:49→16:26:34 (~465s),
total log silence between healthy quote passes, every in-pass decision line
reading "window is open".

## 1. Both dropouts are the bounded-sleep branch, by arithmetic

The handoff had fitted dropout 1 to `Tempo.interval_s()`'s bounded sleep and
called dropout 2 unexplained ("468s matches nothing cleanly"). It matches
exactly once the bound is computed from the *actual* last sweep rather than
the nominal refresh minute:

```
last served sweep      16:16:37.974          (sweep-log pull, row max)
+ 600s refresh         16:26:37.974          <- next_wake_ms
pass ends              ~16:18:49
until_s                ~468s -> sleep drawn from [until/1.15, until]
observed wake          16:26:34.860          <- 3s inside the bound
```

Dropout 1 is the same branch against the 15:26:06.904 sweep (+600s =
15:36:06.9; wake 15:34:54). The bounded-sleep branch runs **only when
`tempo.window_open` is False**, so at the end of both trigger passes the
window read closed.

## 2. Why it read closed: the oldest book's own stamp, not our fetch

`ActionableWindow.is_open` is `fixtures_fresh > 0`, and `fixture_freshness`
ages each fixture by the **oldest contributing book's `last_update`**
(falling back to fetch time), per the rule "a consensus is only as fresh as
the stalest price in it". Measured retrospectively at the two instants:

| instant | MLB fixtures | every fixture's age | oldest stamp | book |
|---|---|---|---|---|
| 15:28:55Z | 9 of 9 | **924s** (> 900s limit) | 15:13:31Z | everygame |
| 16:18:50Z | 9 of 9 | **916s** (> 900s limit) | 16:03:34Z | everygame |

One book — `everygame`, quoted on all 9 MLB fixtures both times — carried a
stamp **755s / 784s old at the moment of the sweep**. So the slate's
freshness lifetime after each sweep was 900 − ~770 ≈ **2–2.5 minutes**, out
of a 600s refresh interval. The window opens on the sweep, every fixture
crosses the 900s limit together ~2 minutes later, `is_open` flips False, and
the cadence — correctly, given that flag — sleeps to the next refresh.

The 15:34:54 wake, the 15:36 refresh and each later refresh reset the
stamps, which is why the cadence looked healthy between the two dropouts:
the other 31 books' stamps sat within ~3 minutes of each fetch and
everygame's happened to as well.

## 3. Two corrections to the handoff's hypothesis

- **The flag was not stale.** `run_forever` evaluates `interval_s()` *after*
  the pass, and `tempo.window_open = window.is_open` is assigned at the end
  of that same pass from a fresh `window_now()`. The staleness-family
  hypothesis ("the cadence still reads the flag assigned at the END of the
  previous pass") is refuted; the flag was current and correct.
- **"Window is open" in the pass log is a different quantity.** That line is
  `decide_sweeps`' *slot* view — kickoff times plus a served sweep inside the
  refresh interval. `is_open` is the *consensus-freshness* view — book
  stamps against the 900s limit. Both were telling the truth; they share a
  word, not a definition. The 16:26:34 pass line says it plainly: "odds are
  9.9min old" (fetch-age) beside a window flag that had read closed for
  eight minutes (stamp-age).

## 4. What this does not establish

- **Whether everygame contributed to the runner's consensus.** The runner
  (`book_quotes_for_event`) drops books that fail to quote every outcome and
  then takes the same worst-book age. If everygame quoted both h2h sides —
  near-universal for moneylines, but **not verified for these passes** — the
  runner's `odds_age_ms` also read >900s, every row would have been
  suppressed `stale_odds`, and the sleeps skipped passes that could have
  confirmed nothing. If it was one-sided, the runner was fresher than the
  window flag and the sleeps cost real quote coverage. Deciding which needs
  the outcome rows, which no whitelisted query currently emits. everygame
  appears in **zero** committed odds captures (2026-08-07 fixture, both
  repeat-poll sets), so it is new to the feed and nothing on file answers it.
- **Why everygame's stamp lags.** The 2026-08-11 repeat-poll result
  restricts `last_update` to a book-scoped scrape stamp; a 13-minute lag
  cannot separate "the book has not repriced" from "the aggregator has not
  re-crawled it".
- **Any fix.** Excluding stale books from the consensus instead of letting
  the stalest gate the slate changes the devig population — rule 2 territory,
  an ADR-sized decision, and with the hunt closed (ADR 0038) it competes
  against "accept ~2-minute effective windows and record honestly".

## 5. Cost, restated

~14 minutes of a 60-minute window with no quote passes — during which every
recommendation was, on the likely branch, suppressed as stale anyway. The
loop, the gate fix (ADR 0057), and the bounded sleep all behaved exactly as
designed. The finding is about the freshness *definition*: with a laggard
book on every fixture, `max_odds_age_ms − laggard_lag_at_fetch` is the real
window length, and the 600s refresh interval assumes it is `max_odds_age_ms`.
