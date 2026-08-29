/**
 * Which clock each open-positions figure is allowed to be stamped with.
 *
 * The bug this exists to make impossible (fixed 2026-08-29): the line read
 * "Open now: 1 position · $0.00 at risk · as of 7:47 AM", and 7:47 AM was
 * `count_as_of_ms` — the positions poll, which runs only on
 * `portfolio_poll.poll_portfolio`'s twelve-hour mirror. The first mirror
 * cycle runs at process start and this instance's containers do not survive
 * twelve hours, so that stamp was the container's boot time and it stopped
 * moving until the next restart. It sat after the dollars-at-risk figure,
 * which is re-read every five minutes and carries its own, minutes-fresh
 * `value_as_of_ms` — present in the payload and thrown away by the renderer.
 *
 * So: **two producers, two cadences, two stamps.** A figure is stamped with
 * the read that produced *it* or it is not stamped at all. React-free on
 * purpose — `tests/test_open_positions_stamp.py` runs these functions under
 * node, because a substring assertion passes unchanged on a renderer that
 * puts the wrong clock on the right number.
 *
 * No arithmetic on money here and none anywhere near it: the ages are
 * computed server-side against the same `now_ms` the staleness bounds use
 * (`backend/bets.py::open_positions`), so nothing subtracts a browser
 * millisecond from a server one.
 */
import type { OpenPositionsBlock } from "@/lib/api";

/** One read: when it happened, and how old it was when the server answered.
 *  `ageMs` is null only if a backend one version behind omits the field. */
export type Stamp = { asOfMs: number; ageMs: number | null };

/**
 * When the COUNT was read — `poll_log`'s newest successful 'positions' row.
 * Null when the record carries no successful positions poll at all, in which
 * case the screen must say "never read yet" and show no clock.
 */
export function countStamp(block: OpenPositionsBlock): Stamp | null {
  return stamp(block.count_as_of_ms, block.count_age_ms ?? null);
}

/**
 * When the VALUE was read — the newest `venue_balance_snapshots` row, on the
 * five-minute balance cadence. **Never `count_as_of_ms`.** Null when no
 * snapshot has ever been taken; the figure is then a refusal in words and
 * carries no clock, rather than borrowing the count's.
 */
export function valueStamp(block: OpenPositionsBlock): Stamp | null {
  return stamp(block.value_as_of_ms, block.value_age_ms ?? null);
}

function stamp(asOfMs: number | null, ageMs: number | null): Stamp | null {
  // Unreadable resolves to absent, never to 0 and never to the current
  // clock: a fabricated "just now" on a money line is the failure this
  // module was written to remove, not a fallback for it.
  if (asOfMs === null || asOfMs === undefined) return null;
  return { asOfMs, ageMs: ageMs ?? null };
}

/**
 * How old a read is, in words, coarse enough that nobody reads a wall-clock
 * time as a promise of freshness. Null age (a backend one version behind)
 * returns null and the caller renders the clock alone — the old behaviour,
 * which is honest about *when* even when it cannot say *how long ago*.
 */
export function describeAge(ageMs: number | null): string | null {
  if (ageMs === null || ageMs < 0) return null;
  const minutes = Math.floor(ageMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
