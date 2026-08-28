import {
  DISPLAY_TIME_ZONE,
  fetchRefreshable,
  formatClock,
  formatUntil,
} from "@/lib/api";
import type { ActionableWindow, Refreshable } from "@/lib/api";
import RefreshOddsButton from "@/components/RefreshOddsButton";
import { leagueLabel } from "@/lib/leagueLabel";
import { readNextWindow } from "@/lib/nextOddsWindow";

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
 * **The status line is the first thing in the panel, and the credit accounting
 * is the last.** Until 2026-08-28 the order was reversed: a ~430-character
 * paragraph about credit pools sat on top (8 lines at 390px, 11 at 320px), so
 * the first state-bearing sentence began roughly 230px in - and on the 04:38Z
 * screen that sentence was the false one, *"the next scheduled sweep is now"*,
 * rendered in the same minute the loop refused that exact sweep. Nothing above
 * it was news. The owner review reports never having made a decision with any
 * of the four credit numbers, so they are a caption now and not a headline
 * (ADR 0050's precedent: a caption, never a translation).
 *
 * **Three states, and the middle one is why this was rebuilt.** The panel used
 * to render them identically. `readNextWindow` classifies - the same reading
 * `StaleOddsExit` uses, so there is one spelling and not two, which is the rule
 * half one applied on the backend and this is its other half.
 *
 * **The tap control is present and unchanged in all three states** - same size,
 * position, label and caption. That is where ADR 0071 section 2.1 sits: the
 * panel's job when the desk goes quiet is to **withdraw a false reason to
 * wait**, not to supply a reason to spend. Adding "and 150 credits are sitting
 * there" would push it past neutral the other way, and
 * argument-from-unspent-allowance is the shape the reference apps use. A
 * control that grows when the system goes quiet is the desk saying "now would
 * be a good time."
 *
 * **Colour: `--accent-2` ink on the slice-spent line, and nothing else.** Every
 * refusal in the app is ochre (ADR 0081 section 3) and this is a refusal, but a
 * soft ground would make it the loudest thing on the Games screen on most
 * visit-hours, and ADR 0071 calls the slice *"a hard ceiling and the reason the
 * design is safe"*. Nothing is broken; a red banner would be a false alarm
 * three nights in four.
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

  const reading = readNextWindow(actionable);

  return (
    <section className="mt-6 rounded-xl border p-4">
      <h2 className="text-sm font-bold">Refresh the odds</h2>

      {/* First child, deliberately. This is the only sentence in the panel a
          reader needs before deciding whether to wait or to tap. */}
      {reading.kind === "due_now" || reading.kind === "scheduled" ? (
        <p className="mt-2 max-w-prose text-sm text-foreground">
          <span aria-hidden="true">&#8635;</span> Automatic buying is running
          {/* Narrowing for the type-checker, not a runtime guard, and the
              difference matters to anyone tempted to delete it:
              `readNextWindow(null)` returns `unknown`, so reaching this branch
              already proves `actionable` is non-null -- but that implication
              runs through a function TS does not follow. */}
          {actionable !== null && (
            <>
              {" "}
              — new prices land about every{" "}
              {Math.round(actionable.refresh_interval_s / 60)} minutes while
              this page is open
            </>
          )}
          {reading.kind === "scheduled" && (
            <>
              . The next is{" "}
              <span className="font-semibold">
                {formatUntil(reading.open_ms - reading.now_ms)}
              </span>{" "}
              ({formatClock(reading.open_ms)}), out of the day&apos;s budget
            </>
          )}
          .
        </p>
      ) : reading.kind === "slice_spent" ? (
        <p className="mt-2 max-w-prose text-sm text-accent-2">
          <span aria-hidden="true">&#9632;</span> Today&apos;s automatic buying
          is done — the desk buys by itself until it reaches the day&apos;s
          allowance, and it
          {reading.spent_at_ms === null ? (
            <> has</>
          ) : (
            <>
              {" "}
              did at{" "}
              <span className="font-semibold">
                {formatClock(reading.spent_at_ms)}
              </span>
            </>
          )}
          . Nothing further is bought automatically{" "}
          <span className="font-semibold">while this page is open</span>
          {reading.floor_resumes_ms === null ? (
            <>
              , and no stored fixture is close enough for the slow hourly buy
              to want one either
            </>
          ) : (
            <>
              ; the slow hourly buy resumes once you stop looking, from about{" "}
              <span className="font-semibold">
                {formatClock(reading.floor_resumes_ms)}
              </span>
            </>
          )}
          .
        </p>
      ) : reading.kind === "nothing_to_schedule" ||
        reading.kind === "budget_spent" ? (
        <p className="mt-2 max-w-prose text-sm text-muted">
          <span aria-hidden="true">&#9675;</span>{" "}
          {reading.kind === "budget_spent"
            ? "No automatic buying is left today — the day's odds budget is spent, so nothing re-buys these lines before it rolls over."
            : "No automatic buying is due — no kickoff is close enough yet for the planner to open a window for."}
        </p>
      ) : (
        /* `unknown` and `loop_stalled`. Both are faults rather than quiet, so
           the panel uses the reading's own words rather than inventing a
           calmer sentence for a screen that has one. */
        <p className="mt-2 max-w-prose text-sm text-accent-2">
          {reading.sentence}
        </p>
      )}

      {data.sports.map((sport) => (
        <div key={sport.sport_key} className="mt-4 border-t pt-4">
          {/* The league in a bettor's words; the vendor key survives in
              title= for anyone debugging the feed (2026-08-22 review). */}
          <h3 className="text-sm font-semibold" title={sport.sport_key}>
            {leagueLabel(sport.sport_key)}
          </h3>

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

      {/* Demoted from the top of the panel on 2026-08-28. A caption, not a
          headline: whether *this* tap will be refused is answered by whether
          the button is disabled and by the verbatim refusal it returns. */}
      <p className="mt-4 max-w-prose text-xs text-muted">
        {data.note} Taps have reserved {data.manual_credits_spent_today} of{" "}
        {data.manual_daily_credits} credits set aside for them today, kept
        apart from the scheduled windows — those are what build the record.
        The whole day has spent {data.day_credits_spent} of{" "}
        {data.day_credits_budget}. The same button waits{" "}
        {Math.round(data.cooldown_ms / 60000)} minutes between taps, because
        the books&apos; own scrape is slower than that and a second call would
        buy the same numbers at the same age.
      </p>

      <p className="mt-2 text-xs text-muted">
        Kickoffs in {DISPLAY_TIME_ZONE}.
      </p>
    </section>
  );
}
