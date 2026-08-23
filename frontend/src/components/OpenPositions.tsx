import { DISPLAY_TIME_ZONE, type OpenPositionsBlock } from "@/lib/api";

/**
 * What is open at the venue right now — one line, on the slate and on /bets
 * (slice B3, 2026-08-22: the review's largest hole was that nothing showed
 * what was at risk on any screen).
 *
 * Honesty rules, all server-enforced and only rendered here:
 *
 * - **The count is counted, not parsed.** It is the number of position rows
 *   the venue returned to the 12-hour poll; the per-row shape has never been
 *   observed, so no claim is made about any single row.
 * - **The value refuses more often than it reads.** The venue's own
 *   `portfolio_value` is pinned only at zero; a non-zero value arrives as a
 *   refusal with its reason in `value_refusal`, and those words render —
 *   never $0.00, which would report "nothing at risk" off a number nobody
 *   could read.
 * - **Stale refuses in words**, with the clock kept, so "not read since"
 *   is what appears rather than a silently old figure.
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

  if (block.count === null) {
    return (
      <p className="text-xs text-muted">
        Open positions{" "}
        {block.count_as_of_ms !== null
          ? `not read since ${clock(block.count_as_of_ms)}`
          : "never read yet"}{" "}
        — the positions mirror is behind, which is not the same as nothing at
        risk.
      </p>
    );
  }

  if (block.count === 0) {
    return (
      <p className="text-xs text-muted">
        No open positions at the venue, as of{" "}
        {clock(block.count_as_of_ms!)}.
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
        {" "}
        {block.value_display !== null
          ? `· ${block.value_display} at risk`
          : `· value unreadable — ${block.value_refusal ?? "not read"}`}{" "}
        · as of {clock(block.count_as_of_ms!)}
      </span>
    </p>
  );
}

function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}
