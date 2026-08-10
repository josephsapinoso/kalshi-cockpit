import type { ActionableWindow } from "@/lib/api";
import {
  formatAge,
  formatClock,
  formatDuration,
  formatUntil,
} from "@/lib/api";

/**
 * How long a `last_look` may be before the loop is presumed stopped.
 *
 * Two full passes. `scripts/run_loop.py` defaults `--interval` to 900s and
 * `runner.sweep_odds` writes an `odds_sweep_log` row on *every* full pass —
 * served, skipped, refused or empty — so silence past two intervals is not the
 * loop being quiet, it is the loop being absent. One interval would flap on
 * jitter; two is the smallest gap that cannot be a late pass.
 */
const LOOK_SILENT_MS = 2 * 900_000;

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
}: {
  window: ActionableWindow;
  surfaced: number;
  expired?: number;
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
        {explain(w, surfaced, expired)}
      </p>

      <SweepTrace window={w} />

      <dl className="mt-0 flex flex-wrap gap-x-6 gap-y-2 border-t px-5 py-3 font-mono text-xs text-muted">
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
 * Did the loop look, when did it last sweep, and how far apart are those.
 *
 * The readout that makes silence legible reached the API on 2026-08-10 and
 * stopped there: the three fields were on the wire and no component read them,
 * so the failure they were built to expose was still invisible on the only
 * device this tool is used from. That is not an observability fix, it is a
 * column in a JSON blob.
 *
 * The gap is rendered as its own chip between the two ages rather than left for
 * the reader to subtract, because subtracting two relative ages on a phone is
 * exactly the step nobody performs. Three states, three tones:
 *
 *   no log at all   `null` — never looked. Amber, and it says "blind", because
 *                   an empty trace read as a dash is the calm-looking version of
 *                   the outage itself.
 *   loop silent     nothing recorded in two full passes. Red: the process is
 *                   gone, and the fresh-looking Board underneath it is a record,
 *                   not a market.
 *   nothing swept   the loop is alive and has declined every pass since the
 *                   budget day opened. Amber. This is the 17-hour shape.
 *
 * "Since the budget day opened" is the boundary rather than an invented number
 * of hours: `budget_day_start_ms` is already on the payload, the day's whole
 * allowance is two sweeps, and a day with none of them spent is a fact rather
 * than a threshold somebody chose.
 */
function SweepTrace({ window: w }: { window: ActionableWindow }) {
  if (w.last_look_ms === null) {
    return (
      <Trace
        tone="warn"
        left="looked never"
        gap="no sweep log"
        right={
          w.last_sweep_ms === null
            ? "swept never"
            : `swept ${formatAge(w.now_ms - w.last_sweep_ms)}`
        }
        headline={
          "No pass has ever recorded a decision about odds here. That is " +
          "blind, not clear: nothing below distinguishes a loop that " +
          "declined to sweep from a loop that is not running."
        }
      />
    );
  }

  const lookAge = w.now_ms - w.last_look_ms;
  const silent = lookAge > LOOK_SILENT_MS;
  // A sweep from before the budget day opened has not been paid for out of
  // today's allowance, so today's two sweeps are both still unspent.
  const sweptThisDay =
    w.last_sweep_ms !== null && w.last_sweep_ms >= w.budget_day_start_ms;
  const gapMs = w.last_sweep_ms === null ? null : w.last_look_ms - w.last_sweep_ms;

  const tone: Tone = silent ? "alarm" : sweptThisDay ? "calm" : "warn";
  const outcome = w.last_look_outcome ?? "unrecorded";

  const headline = silent
    ? `Nothing has looked at odds in ${formatDuration(lookAge)}. Two full ` +
      `passes write a row whatever they decide, so this is the recording loop ` +
      `being stopped — every price below is a record, not an offer.`
    : sweptThisDay
      ? `The loop looked ${formatAge(lookAge)} and the day's sweeps have run.`
      : `The loop is alive and declining: it looked ${formatAge(lookAge)}, and ` +
        `${
          gapMs === null
            ? "no sweep has ever been served"
            : `nothing has swept in ${formatDuration(gapMs)}`
        } — not since the budget day opened at ${formatClock(
          w.budget_day_start_ms,
        )}. A loop that looks and never spends is the failure that ran 17 ` +
        `hours unnoticed, and it looks identical to a quiet market from here.`;

  return (
    <Trace
      tone={tone}
      left={`looked ${formatAge(lookAge)}`}
      gap={
        gapMs === null
          ? "never swept"
          : `gap ${formatDuration(Math.max(0, gapMs))}`
      }
      right={
        w.last_sweep_ms === null
          ? "swept never"
          : `swept ${formatAge(w.now_ms - w.last_sweep_ms)}`
      }
      headline={headline}
      outcome={outcome}
      detail={w.last_look_detail}
    />
  );
}

type Tone = "calm" | "warn" | "alarm";

const TONE_TEXT: Record<Tone, string> = {
  calm: "text-muted",
  warn: "text-accent-2",
  alarm: "text-negative",
};

const TONE_CHIP: Record<Tone, string> = {
  calm: "border-[color:var(--border)] text-muted",
  warn: "border-[color:var(--accent-2)] text-accent-2 font-bold",
  alarm: "border-[color:var(--negative)] bg-accent-soft text-negative font-bold",
};

/** The strip itself. Split out so all three states render the same shape. */
function Trace({
  tone,
  left,
  gap,
  right,
  headline,
  outcome,
  detail,
}: {
  tone: Tone;
  left: string;
  gap: string;
  right: string;
  headline: string;
  outcome?: string;
  detail?: string | null;
}) {
  return (
    <div className="mt-4 border-t px-5 py-3">
      <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
        <span className="tabular text-foreground">{left}</span>
        <span aria-hidden className="text-muted">
          ——
        </span>
        <span
          className={`tabular rounded-full border px-2 py-0.5 ${TONE_CHIP[tone]}`}
        >
          {gap}
        </span>
        <span aria-hidden className="text-muted">
          ——
        </span>
        <span className="tabular text-foreground">{right}</span>
      </div>

      <p className={`mt-2 text-xs leading-relaxed ${TONE_TEXT[tone]}`}>
        {headline}
      </p>

      {outcome !== undefined && (
        <p className="mt-1 font-mono text-[11px] leading-relaxed text-muted">
          <span className="uppercase tracking-widest">{outcome}</span>
          {detail ? ` · ${detail}` : " · no reason recorded"}
        </p>
      )}
    </div>
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
    //
    // The explanation has been wrong twice and for the same reason — it named a
    // cause instead of reading the state. First it asserted every such row had
    // a stale Kalshi quote; then it deferred to the cards to name "the limit it
    // broke". Neither survives the order-time refresh: the Kalshi price is
    // re-read at the moment of the order, so a row that is not bettable during
    // an open window has outlived the consensus that was swept to open it.
    return (
      `The window is open and the ${expired} sized ${
        expired === 1 ? "row" : "rows"
      } below predate the sweep that opened it, so the consensus behind ` +
      `${expired === 1 ? "it" : "them"} has already aged out. The Kalshi price ` +
      "is re-read at the moment of the order and never expires a row on its own."
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
  // Third version of this sentence, and the first that does not assert
  // something the cards under it can contradict. It said rows expire sooner
  // than the window (true, and the defect), then that a quote pass re-checks
  // each one every few seconds (true only while the runner is keeping up, and
  // the cards say plainly when it is not). What is true unconditionally is that
  // the price is re-read from Kalshi at the moment of the order, so a row lasts
  // exactly as long as the consensus this banner is counting down.
  return (
    `${surfaced} row${surfaced === 1 ? " is" : "s are"} bettable right now, ` +
    "and each lasts as long as this window does — the Kalshi price behind it " +
    "is re-read from the exchange at the moment of the order, so only the " +
    "consensus ages. Any card showing a price older than the quote limit says " +
    "so, and its size and cost will move when the order is priced."
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
