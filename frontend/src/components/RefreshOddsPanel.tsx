import {
  DISPLAY_TIME_ZONE,
  fetchRefreshable,
  formatClock,
  formatUntil,
} from "@/lib/api";
import type { ActionableWindow, Refreshable } from "@/lib/api";
import RefreshOddsButton from "@/components/RefreshOddsButton";

/**
 * The way out of a slate that is grey because of a clock.
 *
 * **Why this exists at all.** `_live_ages` re-checks the stored consensus
 * against *now* on every read, so `actionable` goes false `MAX_ODDS_AGE_S`
 * after the sweep that priced a row. The rolling refresh (ADR 0030) keeps that
 * open across a planned kickoff cluster and nothing else, which is the right
 * default and covers the hour before first pitch. Two hours out it covers
 * nothing, and a person looking at the board then sees every row struck through
 * with the games and the prices both entirely real. Joe put it exactly:
 * *"if you collect odds at a particular time and I look at it two or three
 * hours later, all of them are gonna be disqualified."*
 *
 * **What it is careful not to promise.** Refreshing buys a *fresh price*. It
 * does not make a row bettable, and it cannot produce an edge that was not
 * there — `actionable` has been 0 on this instance for every market type for
 * the life of the record. Every string below is written against that, the same
 * way `WindowSchedule` says *priceable* and never *bettable*.
 *
 * **Two prices, and the gap is why they are separate buttons.** Team lines are
 * one metered call for the whole slate. One fixture's player props are billed
 * per market key per region *on top of* that call, which is more than four
 * times as much for one game. A single "refresh" button would hide that, and
 * the largest credit accident in this project's history was a 6-credit request
 * that spent 266.
 */
export default async function RefreshOddsPanel({
  actionable,
}: {
  /**
   * The sweep timetable, passed down rather than fetched again. The panel
   * used to borrow its context from *position* — it sat below the banner and
   * schedule, so a reader had met "next sweep in 12 min" before reaching a
   * spend button. A panel that states its own preconditions inline can be
   * placed anywhere a layout needs it; one that borrows them cannot.
   */
  actionable: ActionableWindow | null;
}) {
  let data: Refreshable;
  try {
    data = await fetchRefreshable();
  } catch {
    // Silent rather than an error box. This is an accessory to the page it sits
    // on; a red panel here would read as the board being broken.
    return null;
  }

  if (data.sports.length === 0) {
    return (
      <section className="mt-6 rounded-xl border p-4">
        <h2 className="text-sm font-bold">Refresh the odds</h2>
        <p className="mt-2 text-sm text-muted">
          No fixture is stored inside the next 24 hours, so there is no slate to
          buy a price for.
        </p>
      </section>
    );
  }

  return (
    <section className="mt-6 rounded-xl border p-4">
      <h2 className="text-sm font-bold">Refresh the odds</h2>
      <p className="mt-2 max-w-prose text-sm text-muted">
        {data.note} Taps have reserved{" "}
        <span className="font-semibold text-foreground">
          {data.manual_credits_spent_today} of {data.manual_daily_credits}
        </span>{" "}
        credits set aside for them today, kept apart from the scheduled windows
        — those are what build the record. The whole day has spent{" "}
        {data.day_credits_spent} of {data.day_credits_budget}. The same button
        waits {Math.round(data.cooldown_ms / 60000)} minutes between taps,
        because the books&apos; own scrape is slower than that and a second
        call would buy the same numbers at the same age.
      </p>
      {/* The alternative to spending, stated beside the spend buttons: the
          planner may be about to buy these same lines anyway. Rendered only
          when a sweep is actually scheduled — "no sweep is coming" is the
          case where the button is the only path to a fresh price, and saying
          nothing is the honest version of that. */}
      {actionable !== null && actionable.next_sweep_ms !== null && (
        <p className="mt-2 max-w-prose text-sm text-muted">
          The next scheduled sweep is{" "}
          <span className="font-semibold text-foreground">
            in {formatUntil(actionable.next_sweep_ms - actionable.now_ms)}
          </span>{" "}
          and buys these same team lines out of the day&apos;s budget. A tap
          buys the same numbers sooner, out of the taps&apos; share.
        </p>
      )}

      {data.sports.map((sport) => (
        <div key={sport.sport_key} className="mt-4 border-t pt-4">
          <h3 className="font-mono text-sm font-semibold">{sport.sport_key}</h3>

          <RefreshOddsButton
            className="mt-2"
            sportKey={sport.sport_key}
            label="Team lines, whole slate"
            credits={sport.team_credits}
          />

          <details className="mt-3">
            <summary className="cursor-pointer text-sm font-semibold">
              Player props, one game at a time ({sport.prop_credits} credits
              each)
            </summary>
            <p className="mt-2 max-w-prose text-xs text-muted">
              Props are billed per game, so this is the expensive half and is
              deliberately not a single button for the slate. Refreshing all{" "}
              {sport.fixtures.length} would cost{" "}
              {sport.fixtures.length * sport.prop_credits} credits.
            </p>
            <ul className="mt-2 space-y-3">
              {sport.fixtures.map((fixture) => (
                <li key={fixture.odds_event_id}>
                  <RefreshOddsButton
                    sportKey={sport.sport_key}
                    oddsEventId={fixture.odds_event_id}
                    label={`${fixture.title} — ${formatClock(
                      fixture.commence_ms,
                    )}`}
                    credits={sport.prop_credits}
                  />
                </li>
              ))}
            </ul>
          </details>
        </div>
      ))}

      <p className="mt-4 text-xs text-muted">
        Kickoffs in {DISPLAY_TIME_ZONE}.
      </p>
    </section>
  );
}
