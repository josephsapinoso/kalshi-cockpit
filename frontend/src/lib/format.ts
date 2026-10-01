/**
 * How the desk writes a time, an age, a duration, dollars from tenths and a
 * percent. React-free and import-free, so node can run it directly
 * (`tests/test_one_format_module.py`) -- a `.tsx` file cannot be run that way,
 * which is why none of these could be tested while they lived in components.
 *
 * **Moved, not unified (#261).** Every function here was lifted verbatim from
 * where it was defined. Several look like each other and are NOT: they round
 * differently at 59_999 ms, 89_999 ms or 90_000 ms, or spell the unit
 * differently, and a displayed string must not change. Each lookalike is
 * therefore its own named function with a one-line reason beside it; two
 * would merge only if they agreed on every boundary the test pins, and none
 * did. `lib/api.ts` re-exports the ones it used to define.
 *
 * Does not establish: that any screen calls the right one for its sentence.
 */

/** Freshness band for a quote age. Drives colour, so the eye reads it. */
export function freshness(ageMs: number, limitMs: number) {
  if (ageMs <= limitMs * 0.5) return "fresh" as const;
  if (ageMs <= limitMs) return "aging" as const;
  return "stale" as const;
}

export function formatAge(ms: number): string {
  if (ms < 1000) return "just now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s ago`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m ago`;
  return `${(ms / 3_600_000).toFixed(1)}h ago`;
}

/**
 * The same duration as a *length* rather than a point in time.
 *
 * "quote 40s ago" reads correctly in a metadata row and "this price is 40s ago"
 * does not. Two functions rather than one with a flag, because the difference is
 * grammatical and shows up only when the string is read in a sentence — which
 * is exactly where nothing automated in this repo would catch it.
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return "under a second";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  return `${(ms / 3_600_000).toFixed(1)}h`;
}

/**
 * The one timezone every human-facing clock on this product renders in.
 *
 * **Pinned to a zone, not left to the device, and that is the point.** These
 * used to pass `undefined` as the locale, which renders in whatever the browser
 * says -- so the same slot read 16:51 on the phone, 19:51 on a laptop borrowed
 * in another zone, and something else again in a screenshot pasted into a chat.
 * A schedule whose times depend on which screen is reading it cannot be quoted,
 * compared against a previous session, or acted on with any confidence.
 *
 * `America/Los_Angeles`, not a fixed -8 offset, so the switch to and from
 * daylight saving is handled by the platform rather than by us being wrong for
 * eight months of the year. In August this renders PDT; the label is drawn from
 * the same formatter, so it says PDT rather than claiming PST.
 *
 * **The record stays UTC.** Every millisecond on the wire, in the database and
 * in `docs/measurements` is UTC, and none of that changes -- this is a display
 * decision at the last possible moment. The mixing that let a three-hour offset
 * hide for eleven build steps was in *stored* and *compared* values, not in
 * what a phone prints.
 */
export const DISPLAY_TIME_ZONE = "America/Los_Angeles";

/** `PDT` / `PST`, drawn from the formatter so it cannot claim the wrong one. */
export function displayZoneLabel(ms: number = Date.now()): string {
  const part = new Intl.DateTimeFormat("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    timeZoneName: "short",
  })
    .formatToParts(new Date(ms))
    .find((p) => p.type === "timeZoneName");
  return part?.value ?? "PT";
}

/** A clock time, for a moment the user has to act at rather than react to. */
export function formatClock(ms: number | null): string {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "in 12m" / "in 3h 20m". Used for a future instant; `formatAge` is the past. */
export function formatUntil(ms: number): string {
  if (ms <= 0) return "now";
  const minutes = Math.round(ms / 60_000);
  if (minutes < 1) return "in under a minute";
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  return `in ${hours}h ${minutes % 60}m`;
}

export function formatKickoff(ms: number | null): string {
  if (!ms) return "";
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

// ---- lookalikes lifted from components, kept separate on purpose ----

// formatAgeShort: bare unit (no "ago"), rounds 60-89s to seconds and hours to a whole number; differs from formatAge.
/** "12s" / "3m" / "2h" -- rounded to the unit a glance can use. */
export function formatAgeShort(ms: number): string {
  if (ms < 90_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 90 * 60_000) return `${Math.round(ms / 60_000)}m`;
  return `${Math.round(ms / 3_600_000)}h`;
}

// ageWords: spaced units ("40 s", "12 min"), seconds floored to 1; differs from formatDuration.
/**
 * A server-sent duration in plain words: "40 s", "12 min", "1.3 h". Every
 * input here is a number the server measured on its own clock; nothing on
 * this screen subtracts two timestamps to make one.
 */
export function ageWords(ms: number): string {
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))} s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)} min`;
  return `${(ms / 3_600_000).toFixed(1)} h`;
}

// describeQuoteAgeFloor: floors rather than rounds, null/negative -> null; differs from formatAge.
/**
 * How old a Kalshi quote or a venue positions read is, at second precision.
 *
 * `describeAge` in `lib/openPositionsStamps.ts` answers the same question at
 * minute precision, which is right for a figure that moves every five
 * minutes and wrong here: `MAX_KALSHI_QUOTE_AGE_S` is 30 seconds, so a quote
 * halfway to stale would read "just now" under that formatter and the whole
 * point of showing the age -- letting Joe see a price about to be refused
 * before the refusal fires -- would be lost.
 */
export function describeQuoteAgeFloor(ms: number | null | undefined): string | null {
  if (ms === null || ms === undefined || ms < 0) return null;
  const seconds = Math.floor(ms / 1000);
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

// scoutAge: floors to minutes, sentence-fragment wording (" Filed ..."); differs from every age above.
/** How old a briefing is, in the coarsest unit that is still honest. */
export function scoutAge(ms: number | null): string {
  if (ms === null) return "";
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return " Filed just now.";
  if (minutes < 60) return ` Filed ${minutes}m ago.`;
  return ` Filed ${Math.floor(minutes / 60)}h ago.`;
}

// formatCountdown: takes SECONDS not ms, "1m 05s" shape.
export function formatCountdown(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

// dollarsFromTenths: integer tenths of a cent to "$1.23", sign before the dollar mark.
export function dollarsFromTenths(tenths: number): string {
  const sign = tenths < 0 ? "-" : "";
  return `${sign}$${(Math.abs(tenths) / 1000).toFixed(2)}`;
}

// formatBankroll: whole dollars with thousands separators; input is dollars, not tenths.
/**
 * `$1,000`, from the server's `reference_bankroll_dollars`. One place, so the
 * page's sentence and the row's caption cannot print two different figures.
 */
export function formatBankroll(dollars: number): string {
  return `$${Math.round(dollars).toLocaleString("en-US")}`;
}

// pctFromTenths: input is tenths of a cent (price), one decimal trimmed when whole; differs from pctFromFraction.
export function pctFromTenths(tenths: number): string {
  // One decimal, trimmed when whole: ~25% of Kalshi markets tick in
  // deci-cents, and the one screen entirely about price must not round the
  // tick away.
  return `${(tenths / 10).toFixed(1).replace(/\.0$/, "")}%`;
}

// pctFromFraction: input is a 0-1 fraction, rounded to a whole percent; differs from pctFromTenths.
export function pctFromFraction(fraction: number): string {
  return `${Math.round(fraction * 100)}%`;
}

