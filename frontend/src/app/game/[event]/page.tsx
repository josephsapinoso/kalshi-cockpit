import { SHELL_WIDTH } from "@/lib/shell";
import GameLegs from "@/components/GameLegs";
import { GameCardPanel } from "@/components/GameScriptCard";

export const dynamic = "force-dynamic";

/**
 * One game's same-game parlay builder (#202): `/game/<Kalshi game event
 * ticker>`, for example `/game/KXNFLGAME-26SEP13ATLPIT`.
 *
 * The page is a shell. Every fact on it -- the legs, their order, the desk's
 * chance where it has one -- is read by `<GameLegs>` from
 * `/api/game/{event}/legs`, and the order is the server's, fixed, never a
 * function of a chance or a price (ADR 0071). The two taps that spend nothing
 * but touch the venue (mint, ask) and the one that spends (take) are the
 * existing doors, unchanged.
 */
export default async function GamePage({
  params,
  searchParams,
}: {
  params: Promise<{ event: string }>;
  searchParams: Promise<{ legs?: string | string[] }>;
}) {
  const { event } = await params;
  // `?legs=ticker:side,...` from a card's "Change a leg" link (#295): the
  // legs GameLegs pre-ticks on first load. Read as text here; the component
  // checks each against the live listing and ignores any it does not list.
  const { legs } = await searchParams;
  const initialLegs = Array.isArray(legs) ? legs[0] : legs;
  const eventTicker = decodeURIComponent(event);
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      <h1 className="display text-4xl sm:text-5xl">Same-game parlay</h1>
      {/* The game's title and kickoff lead the page (Joe, 2026-10-02): GameLegs
          draws its heading first and the card panel right under it. */}
      <GameLegs
        eventTicker={eventTicker}
        initialLegs={initialLegs}
        belowHeading={<GameCardPanel eventTicker={eventTicker} />}
      />
    </div>
  );
}
