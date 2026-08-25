import { formatClock, formatUntil } from "@/lib/api";
import type { ActionableWindow, Refreshable } from "@/lib/api";
import { readNextWindow } from "@/lib/nextOddsWindow";
import { leagueLabel } from "@/lib/leagueLabel";

import RefreshOddsButton from "@/components/RefreshOddsButton";
import Term from "@/components/Term";

/**
 * The exit beside the stale count: a time, a tap, and one teaching sentence.
 *
 * Three parts, each honest on its own:
 *
 * - **What stale means.** The comparison aged out; the pick did not go bad.
 *   Staleness is a validity check — the two prices must be from the same
 *   moment to be comparable at all — and it is never a weighted factor, so
 *   the answer to 33 stale rows is a fresh read, never a softer gate.
 * - **When the next window opens.** From `readNextWindow` over `/api/window`,
 *   which publishes `window_status().next_call_ms` — the scheduler's own
 *   planning through `firing_for_slot`, the predicate the loop spends with
 *   (backend/odds/timing.py: "one predicate, two callers"). No window left →
 *   the sentence says which reason holds, never a fake time; timetable
 *   unreadable → a refusal in words, never 0.
 * - **The tap.** The existing `RefreshOddsButton` → `/refresh-odds` →
 *   `POST /api/odds/refresh` path, unchanged — this is a new caller, not a
 *   new gate. The credit cost is on the button before the tap (the
 *   ScoutDesk precedent), and the server re-checks cooldown, the taps'
 *   daily slice and the odds budget before any money leaves; the button
 *   renders whatever refusal it answers with, verbatim.
 *
 * Neutral treatment throughout (ADR 0061 §3): a refresh affordance is not a
 * warning and not money, so no `accent-2` and no `bg-accent` — the pill
 * shape is TonightStrip's, at the 44px control height.
 */
export default function StaleOddsExit({
  actionable,
  refreshable,
}: {
  actionable: ActionableWindow | null;
  refreshable: Refreshable | null;
}) {
  const reading = readNextWindow(actionable);
  return (
    <div className="mt-2 max-w-[65ch] space-y-2">
      <p className="text-xs leading-snug text-muted">
        <Term k="stale">Stale</Term> is a clock verdict, not a quality one:
        the sportsbook side of this comparison has aged out, so these rows
        are unpriced — not bad bets. Staleness is a validity check, never a
        weighted factor; the exit is a fresh read, not a softer bar.
      </p>
      <p className="text-xs leading-snug text-muted">
        {reading.kind === "scheduled" ? (
          <>
            The next scheduled odds window opens at{" "}
            <span className="font-semibold text-foreground">
              {formatClock(reading.open_ms)}
            </span>{" "}
            ({formatUntil(reading.open_ms - reading.now_ms)}), when the
            planner re-buys these lines out of the day&rsquo;s budget.
          </>
        ) : (
          reading.sentence
        )}
      </p>
      {refreshable === null ? (
        <p className="text-xs leading-snug text-muted">
          Whether a tap can refresh these lines could not be read, so no
          button is offered here — the refresh panel on this page is the
          fallback.
        </p>
      ) : refreshable.sports.length === 0 ? (
        <p className="text-xs leading-snug text-muted">
          Nothing to refresh: no fixture is stored inside the next 24 hours.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {refreshable.sports.map((sport) => (
            <RefreshOddsButton
              key={sport.sport_key}
              sportKey={sport.sport_key}
              label={`Refresh ${leagueLabel(sport.sport_key)} lines now`}
              credits={sport.team_credits}
              buttonClassName="min-h-11 rounded-full border border-border px-4 py-2 text-xs font-semibold disabled:opacity-50"
            />
          ))}
        </div>
      )}
    </div>
  );
}
