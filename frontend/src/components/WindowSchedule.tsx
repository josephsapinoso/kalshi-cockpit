import type { ActionableWindow } from "@/lib/api";
import { formatClock, formatUntil } from "@/lib/api";

/**
 * When to actually look, for the rest of the budget day.
 *
 * `WindowBanner` answers "can I act right now, and when is the next chance".
 * This answers a different question that the Board could not answer at all:
 * **"when should I open this?"** The odds budget affords one or two sweeps a
 * day and each leaves the slate priceable for fifteen minutes, so the tool is
 * worth looking at for well under an hour out of twenty-four. Anyone reading
 * the Board outside those minutes is reading rows nobody can act on, and until
 * now nothing on the page said which minutes those were.
 *
 * **The schedule is the planner's own, not a second copy of it.**
 * `slots_planned` is computed by `plan_sweep_slots` -- the same function the
 * runner spends credits with -- and has been serialised on `/api/window` since
 * before this component existed, unread. Nothing here recomputes a slot time; a
 * screen and a control that derive one schedule by two paths eventually
 * disagree, and the screen is the one that gets believed.
 *
 * ## The window shown is wider than the sweep, deliberately
 *
 * A slot is a *permission to fire*, not a firing: the pass may spend its credit
 * anywhere in `[fire_from, fire_until]`, and which minute it picks depends on
 * when a loop iteration lands. Freshness then runs `max_odds_age_s` from the
 * moment it fires. So the earliest a row can be priceable is `fire_from`, and
 * the latest is `fire_until + max_odds_age_s` -- and **that envelope is what a
 * human needs**, because it is the interval that is guaranteed to contain the
 * fresh period. Showing the sweep window alone would tell someone to look at
 * 16:51 and stop at 17:21, missing up to fifteen minutes of the only time the
 * tool works.
 *
 * It is an envelope and it is labelled as one. The fresh period inside it is
 * about fifteen minutes long, not the forty-five the envelope spans.
 *
 * ## What this does not promise, and the distinction is the whole point
 *
 * **A window is when a bet *could* be priced, never that one exists.** Most
 * windows open onto an empty Board -- that is the expected result of the
 * strategy, not a failure of it, and `actionable` has been zero for the life of
 * the project. A schedule that read as "be here at 16:51 and there will be
 * something" would be the single most misleading element on the page, so the
 * copy says "priceable", never "bettable", and the footer says so outright.
 *
 * **And a planned slot may never fire.** The budget can refuse it, the fixtures
 * can move, the loop can be down. `sweeps_remaining_today` is shown beside the
 * list because a schedule with no credits behind it is a wish.
 *
 * Times render in the reader's own timezone via `formatClock`. The rest of this
 * app speaks UTC because the venue does; a human deciding when to pick up a
 * phone does not.
 */
export default function WindowSchedule({
  window: w,
}: {
  window: ActionableWindow;
}) {
  const freshnessMs = w.max_odds_age_s * 1000;
  const slots = w.slots_planned ?? [];

  return (
    <section className="mb-8 rounded-2xl border border-[color:var(--border)] bg-card">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pt-4">
        <h2 className="text-sm font-semibold uppercase tracking-wide">
          When to look today
        </h2>
        <span className="text-sm text-muted">
          {w.sweeps_remaining_today} sweep
          {w.sweeps_remaining_today === 1 ? "" : "s"} left ·{" "}
          {w.spent_today} of {w.daily_budget} credits spent
        </span>
      </div>

      {slots.length === 0 ? (
        /* **A planner with nothing planned is a state, not a gap.** It happens
           for two unrelated reasons -- the day's credits are gone, or no
           fixture is close enough to schedule against -- and they need
           opposite responses from a reader. `sweeps_remaining_today`
           separates them, so it is quoted rather than left to be inferred
           from an empty list. */
        <p className="px-5 py-4 text-sm text-muted">
          {w.sweeps_remaining_today === 0
            ? "No sweeps left in today's budget, so nothing further will be priceable until the budget day rolls over."
            : "No window is scheduled. Credits remain, but no fixture is close enough to plan a sweep against yet."}
        </p>
      ) : (
        <ol className="mt-3 divide-y divide-[color:var(--border)]">
          {slots.map((s) => {
            const lookUntil = s.fire_until_ms + freshnessMs;
            const untilStart = s.fire_from_ms - w.now_ms;
            /* **Today these are the same instant, and saying so beats printing
               it twice.** `slots_for_sport` sets `fire_until = anchor -
               max_odds_age_ms`, so the envelope always ends exactly at the
               first kickoff — which is the planner's guarantee that a pick
               surfaced at the last possible second is still a pre-game bet.
               The first render of this component showed "4:51 PM – 5:36 PM …
               first kickoff 5:36 PM" and read as a bug.

               It is still *derived*, not assumed. If the planner ever took a
               wider lead the envelope would close before the kickoff, and then
               the two are different facts and both are shown. Rendering
               `anchor_commence_ms` as the range end instead would be the
               shortcut that silently over-promises in that world. */
            const closesAtFirstPitch = lookUntil >= s.anchor_commence_ms;
            return (
              <li
                key={`${s.sport_key}-${s.fire_from_ms}`}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 py-3"
              >
                <span className="font-mono text-base tabular-nums">
                  {formatClock(s.fire_from_ms)} – {formatClock(lookUntil)}
                </span>
                <span className="text-sm text-muted">
                  {untilStart > 0 ? formatUntil(untilStart) : "now"}
                </span>
                <span className="text-sm">
                  {s.games_covered} game{s.games_covered === 1 ? "" : "s"}
                </span>
                <span className="text-sm text-muted">{s.sport_key}</span>
                {/* The deadline the window exists to beat. A window that
                    closed after the game started would have priced nothing
                    worth having. */}
                <span className="text-sm text-muted">
                  {closesAtFirstPitch
                    ? "closes at first pitch"
                    : `first kickoff ${formatClock(s.anchor_commence_ms)}`}
                </span>
              </li>
            );
          })}
        </ol>
      )}

      <p className="border-t border-[color:var(--border)] px-5 py-3 text-xs text-muted">
        The range is the outer envelope: the sweep fires somewhere in its slot
        and odds stay fresh for {Math.round(freshnessMs / 60_000)} minutes after
        it, so the priceable stretch inside is about that long, not the whole
        range. <strong>A window is when a bet could be priced, not that one
        exists</strong> — most windows open onto an empty Board, which is the
        expected result. A planned sweep can also be refused by the budget or
        missed if the loop is down.
      </p>
    </section>
  );
}
