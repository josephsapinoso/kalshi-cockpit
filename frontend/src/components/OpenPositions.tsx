import { DISPLAY_TIME_ZONE, type OpenPositionsBlock } from "@/lib/api";
import {
  countStamp,
  describeAge,
  valueStamp,
  type Stamp,
} from "@/lib/openPositionsStamps";

/**
 * What is open at the venue right now — one line, on the slate and on /bets
 * (slice B3, 2026-08-22: the review's largest hole was that nothing showed
 * what was at risk on any screen).
 *
 * Honesty rules, all server-enforced and only rendered here:
 *
 * - **The count is counted, not parsed.** It is the number of position rows
 *   the venue returned to the positions poll (the 5-minute cadence since
 *   2026-08-29; the 12-hour mirror before that); the per-row shape has never
 *   been observed, so no claim is made about any single row.
 * - **The value refuses more often than it reads.** The venue's own
 *   `portfolio_value` is pinned only at zero; a non-zero value arrives as a
 *   refusal with its reason in `value_refusal`, and those words render —
 *   never $0.00, which would report "nothing at risk" off a number nobody
 *   could read.
 * - **Stale refuses in words**, with the clock kept, so "not read since"
 *   is what appears rather than a silently old figure.
 * - **Each figure wears its own clock** (2026-08-29). The line used to read
 *   "· $0.00 at risk · as of 7:47 AM" off `count_as_of_ms` alone — the
 *   twelve-hour mirror's stamp, which on a container that never lives twelve
 *   hours is the boot time, and which therefore stopped moving until the next
 *   restart. Both reads now ride the five-minute cadence, and the reads stay
 *   separated on the line rather than averaged into one stamp: a shared
 *   cadence is not a shared read, and a positions poll that fails while the
 *   balance succeeds leaves the two clocks hours apart — exactly what one
 *   borrowed stamp would hide. Ages come from the server, never from
 *   `Date.now()`: a clock invented at render time would be a second lie in
 *   the same place.
 * - **No P&L, no mark-to-market, never summed with cash** — TonightStrip's
 *   unsigned rule. This is commitment, not performance.
 *
 * `block` is optional: a deployed backend one version behind omits the key,
 * and rendering nothing is correct there (the old state, not a refusal).
 */
export default function OpenPositions({
  block,
}: {
  block?: OpenPositionsBlock | null;
}) {
  if (!block) return null;

  const counted = countStamp(block);
  const valued = valueStamp(block);

  if (block.count === null) {
    return (
      <p className="text-xs text-muted">
        Open positions{" "}
        {counted !== null
          ? `not read since ${stampText(counted)}`
          : "never read yet"}{" "}
        — the positions mirror is behind, which is not the same as nothing at
        risk.
      </p>
    );
  }

  if (block.count === 0) {
    return (
      <p className="text-xs text-muted">
        No open positions at the venue
        {counted !== null ? `, counted ${stampText(counted)}` : ""}.
      </p>
    );
  }

  return (
    <p className="text-sm">
      <span className="font-semibold tabular">
        Open now: {block.count}{" "}
        {block.count === 1 ? "position" : "positions"}
      </span>
      <span className="text-muted">
        {counted !== null ? ` (counted ${stampText(counted)})` : ""}
        {" · "}
        {block.value_display !== null
          ? `${block.value_display} at risk`
          : `value unreadable — ${block.value_refusal ?? "not read"}`}
        {/* The value's own stamp, never the count's. Omitted entirely when
            the balance has never been observed — no clock beats a borrowed
            one on a money figure. */}
        {valued !== null ? ` (read ${stampText(valued)})` : ""}
      </span>
    </p>
  );
}

/** "7:47 AM, 6h ago" — the clock, and how stale it is. The age is dropped
 *  when the server did not send one (a backend one version behind); the
 *  clock is never dropped when it exists. */
function stampText(s: Stamp): string {
  const age = describeAge(s.ageMs);
  const at = clock(s.asOfMs);
  return age === null ? at : `${at}, ${age}`;
}

function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}
