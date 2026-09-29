import { SHELL_WIDTH } from "@/lib/shell";
import GameLegs from "@/components/GameLegs";

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
}: {
  params: Promise<{ event: string }>;
}) {
  const { event } = await params;
  const eventTicker = decodeURIComponent(event);
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      <h1 className="display text-4xl sm:text-5xl">Same-game parlay</h1>
      <p className="mt-2 font-mono text-xs text-muted">{eventTicker}</p>
      <GameLegs eventTicker={eventTicker} />
    </div>
  );
}
