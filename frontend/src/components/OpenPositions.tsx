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
 * - **Staked is what Joe asked for, and it is now DERIVED rather than always
 *   refused (ADR 0107, schema v33).** This bullet said "the money on the open
 *   positions is not derivable from the mirror" — true when the mirror kept
 *   no rows, and false since `venue_positions` records them: the server sums
 *   `exposure_tenths` over the rows of the newest poll that kept its own, and
 *   sends `staked_display`. It still refuses more often than it reads, and
 *   the five refusals are each a genuinely unreadable state rather than a
 *   zero (`backend/bets.py`); `staked_refusal` carries the words and this
 *   renders them **in every branch**, which it did not before. Never $0.00
 *   beside a non-zero count. Omitted entirely when the backend predates the
 *   field.
 * - **Every branch shows the server's own reason (2026-09-05).** The two
 *   early returns used to swallow it: `count === null` printed one hardcoded
 *   sentence for four distinct refusals — naming a cause that is wrong for
 *   two of them — and `count === 0` returned before `StakedNow`, hiding an
 *   integrity refusal that is reachable at a zero count. A refusal the server
 *   worded carefully and the screen replaced with its own guess is worse than
 *   no refusal, because it reads as knowledge.
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
 *   unsigned rule. This is commitment, not performance. The staked figure is
 *   a sibling of the count, never added to the value, the balance or the net
 *   strip; `tests/test_bets_sections.py` pins the words this file may not
 *   contain.
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
          : "never read yet"}
        {/* The server's own reason, not a substitute for it. This clause read
            "the positions mirror is behind" for every one of the four states
            that reach here, and it is FALSE in two of them: the server
            distinguishes "no positions poll has succeeded yet" (nothing is
            behind -- nothing has happened), "no positions poll has kept its
            rows yet", "not read in the last 30 minutes", and a record it
            could not read at all. Four refusals, carefully worded in
            `backend/bets.py`, arriving as one sentence that named the wrong
            cause. */}
        {typeof block.staked_refusal === "string"
          ? ` — ${block.staked_refusal}`
          : ""}
        . That is not the same as nothing at risk.
      </p>
    );
  }

  if (block.count === 0) {
    return (
      <p className="text-xs text-muted">
        No open positions at the venue
        {counted !== null ? `, counted ${stampText(counted)}` : ""}.
        {/* An empty-but-fresh snapshot is count 0 AND $0.00 (ADR 0107 §5),
            and this branch returned before `StakedNow` could say either --
            the state the live account has been in since v33 deployed.

            The $0.00 itself is deliberately still not printed: "No open
            positions" already says it, and two spellings of nothing on one
            line is noise, not transparency. What must not be swallowed is a
            REFUSAL at count 0, which is reachable and is an integrity
            failure: `STAKED_MIRROR_MISMATCH` fires when the mirror holds
            rows under a poll that counted zero, i.e. the table disagrees
            with the read that wrote it. Silence there would report "nothing
            open" off a record that contradicts itself. */}
        {typeof block.staked_display !== "string" &&
        typeof block.staked_refusal === "string" ? (
          <span> Staked on them: {block.staked_refusal}.</span>
        ) : null}
      </p>
    );
  }

  return (
    <div>
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
      <StakedNow block={block} />
    </div>
  );
}

/**
 * The money on the open positions, unsigned — or the server's reason it
 * cannot be said. Renders nothing when the backend predates the field
 * (the old state, not a refusal). No clock: there is no read behind the
 * refusal to stamp, and a stamp on the words would imply one.
 */
function StakedNow({ block }: { block: OpenPositionsBlock }) {
  if (typeof block.staked_display === "string") {
    return (
      <p className="mt-1 text-xs">
        {/* "on what is still open" is inside the BOLD span on purpose.
            `/slate` mounts this component and `TonightStrip` seven lines
            apart (`app/slate/page.tsx`), and both printed a bold
            "$X staked" for two different numbers: this one is the money on
            positions open right now, TonightStrip's is the money committed
            since the day roll. A position opened yesterday and still held is
            in this figure and not in that one; a bet placed and settled
            today is in that one and not in this. The muted qualifiers did
            distinguish them and the bold text -- which is what the eye takes
            -- did not. Only this side is changed: TonightStrip's "staked"
            is the older use and ADR 0107 §3 cites it as the precedent this
            figure was named to match, so the newcomer is what disambiguates. */}
        <span className="font-semibold tabular">
          {block.staked_display} staked on what is still open
        </span>
        <span className="text-muted"> — your own money in, not a value.</span>
      </p>
    );
  }
  if (typeof block.staked_refusal === "string") {
    return (
      <p className="mt-1 text-xs text-muted">
        Staked on them: {block.staked_refusal}.
      </p>
    );
  }
  return null;
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
