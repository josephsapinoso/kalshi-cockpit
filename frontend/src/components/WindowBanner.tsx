import type { ActionableWindow } from "@/lib/api";
import { formatAge, formatClock, formatUntil } from "@/lib/api";

/**
 * Whether anything on this page can be acted on, and when the next chance is.
 *
 * The Board was unreadable in the one way that mattered. Two odds sweeps a day
 * at fifteen minutes of freshness each means the tool is actionable for about
 * half an hour out of twenty-four — and an empty Board, a Board full of expired
 * rows, and a Board during the live window all rendered identically.
 *
 * Three things are deliberately kept apart here, because collapsing any two of
 * them turns a freshness indicator into a buy signal:
 *
 *   "open"   = the sportsbook consensus is fresh enough to price against
 *   bettable = that, AND a Kalshi quote under its own much tighter limit
 *   surfaced = and an edge that survived fees, depth and the suspicion checks
 *
 * The middle one is the trap. Two limits bound one window and the tighter one
 * decides it: books last fifteen minutes, a Kalshi quote thirty seconds. So an
 * open window with zero bettable rows is the ordinary state, and the banner
 * says which of the two closed rather than reporting a single "fresh".
 */
export default function WindowBanner({
  window: w,
  surfaced,
  expired = 0,
  quoteLimitS,
}: {
  window: ActionableWindow;
  surfaced: number;
  expired?: number;
  quoteLimitS?: number;
}) {
  const open = w.is_open;
  const closesIn = w.seconds_remaining;

  return (
    <section
      className={`mb-8 overflow-hidden rounded-2xl border ${
        open ? "border-positive/50" : "border-[color:var(--border)]"
      } bg-card`}
      aria-live="polite"
    >
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-5 pt-4">
        <span
          className={`inline-flex items-center gap-2 text-sm font-bold uppercase tracking-widest ${
            open ? "text-positive" : "text-muted"
          }`}
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              open ? "bg-positive" : "bg-[color:var(--muted)]"
            }`}
            aria-hidden
          />
          {open ? "Window open" : "Window closed"}
        </span>

        {open && closesIn !== null && (
          <span className="tabular text-sm text-muted">
            closes in{" "}
            <strong className="font-bold text-foreground">
              {formatCountdown(closesIn)}
            </strong>
            {w.open_until_ms ? ` (${formatClock(w.open_until_ms)})` : ""}
          </span>
        )}

        {!open && w.next_sweep_ms !== null && (
          <span className="tabular text-sm text-muted">
            next sweep{" "}
            <strong className="font-bold text-foreground">
              {formatUntil(w.next_sweep_ms - w.now_ms)}
            </strong>{" "}
            ({formatClock(w.next_sweep_ms)})
          </span>
        )}
      </div>

      <p className="mt-2 px-5 text-sm leading-relaxed text-muted">
        {explain(w, surfaced, expired, quoteLimitS)}
      </p>

      <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t px-5 py-3 font-mono text-xs text-muted">
        <Item
          label="fixtures fresh"
          value={`${w.fixtures_fresh}/${w.fixtures_upcoming}`}
        />
        <Item
          label="last sweep"
          value={
            w.last_sweep_ms === null
              ? "never"
              : `${formatAge(w.now_ms - w.last_sweep_ms)}${
                  w.last_sweep_sport ? ` · ${w.last_sweep_sport}` : ""
                }`
          }
        />
        <Item
          label="credits today"
          value={`${w.spent_today}/${w.daily_budget} · ${w.sweeps_remaining_today} sweep${
            w.sweeps_remaining_today === 1 ? "" : "s"
          } left`}
        />
      </dl>
    </section>
  );
}

/**
 * The sentence that stops each state being mistaken for another one.
 *
 * Five distinct states, and four of them look like "nothing here" if you only
 * see an empty list.
 */
function explain(
  w: ActionableWindow,
  surfaced: number,
  expired: number,
  quoteLimitS?: number,
): string {
  if (w.fixtures_upcoming === 0) {
    return (
      "No upcoming fixtures have stored odds, so nothing can be priced yet. " +
      "The next pass will fetch a slate if one exists."
    );
  }
  if (!w.is_open) {
    const next =
      w.next_sweep_ms === null
        ? w.sweeps_remaining_today === 0
          ? "Today's odds budget is spent, so the next window is tomorrow."
          : "No kickoff inside the horizon is close enough to be worth a sweep yet."
        : `The next sweep is aimed at ${w.next_sweep_reason ?? "the next cluster of kickoffs"}.`;
    return (
      `The books behind every row are past the ${Math.round(
        w.max_odds_age_s / 60,
      )}-minute limit, so nothing here is bettable — the prices are a record, not an offer. ` +
      next
    );
  }
  if (surfaced === 0 && expired > 0) {
    // The state that would otherwise be read as a bug: green light, sized
    // bets on screen, and none of them placeable.
    return (
      `The books are fresh, but the ${expired} sized ${
        expired === 1 ? "row" : "rows"
      } below are priced against a Kalshi quote older than the ${
        quoteLimitS ?? 30
      }-second limit, so the server will refuse them. Two limits bound this ` +
      "window and the tighter one decides it."
    );
  }
  if (surfaced === 0) {
    return (
      "The books are fresh and nothing cleared the bar. That is the expected " +
      "result: Kalshi prices sports to about two cents, and the venue's fee " +
      "advantage is 0.38 points. An open window is a chance to look, not a " +
      "signal to bet."
    );
  }
  return (
    `${surfaced} row${surfaced === 1 ? " is" : "s are"} bettable right now. ` +
    `Each also needs its Kalshi quote to stay under ${quoteLimitS ?? 30}s, so ` +
    "the individual rows expire sooner than this window does — and the server " +
    "checks again regardless of what this page still shows."
  );
}

function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

function Item({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="uppercase tracking-widest">{label}</dt>
      <dd className="text-foreground">{value}</dd>
    </div>
  );
}
