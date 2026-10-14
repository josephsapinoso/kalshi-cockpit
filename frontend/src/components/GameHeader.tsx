import Link from "next/link";

import { gameHeaderParts } from "@/lib/gameEvent";
import PageTitle from "@/components/PageTitle";

/**
 * The head of `/game/<event>` (#389): a way back to Games, then the teams,
 * league and kickoff on one line -- `San Diego @ Houston · MLB · Tue 5:01 PM`.
 * The ticker appears only when the listing carries no names. Pure header
 * data: nothing here touches a leg, a price or an order.
 */
export default function GameHeader({
  eventTicker,
  title,
  league,
  kickoff,
}: {
  eventTicker: string;
  title: string | null;
  league: string | null;
  kickoff: string | null;
}) {
  const parts = gameHeaderParts(title, league, kickoff);
  return (
    <div>
      <p className="text-sm">
        <Link href="/" className="font-semibold text-accent underline">
          &larr; Games
        </Link>
      </p>
      <div className="mt-2">
        <PageTitle variant="detail">
          {parts.title ?? (
            <span className="font-mono text-base font-normal text-muted">
              {eventTicker}
            </span>
          )}
          {parts.rest.length > 0 && (
            <span className="tabular text-muted">
              {parts.rest.map((part) => ` · ${part}`).join("")}
            </span>
          )}
        </PageTitle>
      </div>
    </div>
  );
}
