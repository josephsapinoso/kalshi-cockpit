"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  buildGameCard,
  displayZoneLabel,
  fetchGameCards,
  formatKickoff,
  mintGameCombo,
  type GameScriptCard as CardData,
  type GameScriptCards,
  type GameScriptLeg,
} from "@/lib/api";
import AskTheMarket from "@/components/AskTheMarket";
import Term from "@/components/Term";
import { Button, SectionLabel } from "@/components/ui";

/**
 * The game-script card (#216, ADR 0190): one game, a short story, two or
 * three legs with Kalshi's own single-leg ask beside each, what would kill
 * it, and the makers' quote one tap away.
 *
 * **No combined or "as if independent" figure is computed or shown, and none
 * may be** (ADR 0189). Each ask below is one leg's, read by the server. The
 * desk has no model of how same-game legs move together, so the only price
 * for the whole ticket is the one the makers quote through `<AskTheMarket>`.
 *
 * **Nothing here orders anything** (ADR 0071). The cards arrive in kickoff
 * order from the server and are drawn in the order received; a card is an
 * opinion, and an opinion that ranked itself would be a claim.
 *
 * A game with no built card is listed with its reason, never dropped and
 * never drawn as an empty row: "no card today: budget" and "no clean story:
 * ..." are facts about the desk, and hiding them would read as a game the
 * desk had not looked at.
 */

const NO_COMBINED_CHANCE_LINE =
  "The desk shows no combined chance for these picks: it doesn't know how " +
  "they move together. The makers' quote prices that in.";

function kickoffText(ms: number): string {
  return `${formatKickoff(ms)} ${displayZoneLabel(ms)}`;
}

function fixtureOf(gameEventTicker: string): string {
  return gameEventTicker.split("-").slice(1).join("-") || gameEventTicker;
}

/** One built card. Also used on `/game/<event>` and in the `/parlays` list. */
export default function GameScriptCard({
  card,
  heading = false,
}: {
  card: CardData;
  /** Show the game's own heading (the list does; the game page already has one). */
  heading?: boolean;
}) {
  const [mint, setMint] = useState<
    | { kind: "idle" }
    | { kind: "minting" }
    | { kind: "minted"; ticker: string; words: string }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  const ask = async () => {
    setMint({ kind: "minting" });
    const result = await mintGameCombo(
      card.game_event_ticker,
      card.legs.map((leg) => ({
        market_ticker: leg.market_ticker,
        event_ticker: leg.event_ticker,
        side: leg.side,
      })),
    );
    if (!result.ok) {
      setMint({ kind: "refused", words: result.refusal });
      return;
    }
    if (result.value.status === "minted" && result.value.minted_market_ticker) {
      setMint({
        kind: "minted",
        ticker: result.value.minted_market_ticker,
        words: result.value.words,
      });
    } else {
      setMint({ kind: "refused", words: result.value.words });
    }
  };

  if (card.status !== "built") {
    return <NoCard card={card} heading={heading} />;
  }

  return (
    <article className="rounded-xl border border-border bg-card p-4">
      {heading && <GameHeading card={card} />}
      <SectionLabel>
        <Term k="game_script_card">Game-script card</Term>
      </SectionLabel>
      <p className="mt-2 max-w-[65ch] text-sm leading-relaxed">{card.story}</p>

      <ul className="mt-3 divide-y divide-border">
        {card.legs.map((leg) => (
          <LegRow key={`${leg.market_ticker}-${leg.side}`} leg={leg} />
        ))}
      </ul>
      <p className="mt-2 max-w-[65ch] text-xs text-muted">
        {NO_COMBINED_CHANCE_LINE}
      </p>

      <p className="mt-3 max-w-[65ch] text-sm">
        <span className="font-semibold">
          <Term k="drop_if">Drop it if</Term>:
        </span>{" "}
        {card.drop_if}
      </p>
      <p className="mt-1 max-w-[65ch] text-xs text-muted">
        <Term k="inactives">Inactives</Term> come out 90 minutes before
        kickoff and are not covered.
      </p>

      <div className="mt-3">
        <Button
          onClick={ask}
          disabled={mint.kind === "minting" || card.legs.length < 2}
        >
          {mint.kind === "minting" ? "Building…" : "Ask the market"}
        </Button>
        {card.combo_ticker && mint.kind === "idle" && (
          <p className="mt-2 text-xs text-muted">
            This card&rsquo;s legs were built into a combination before.
          </p>
        )}
        {mint.kind === "refused" && (
          <p className="mt-2 text-sm text-accent-2">{mint.words}</p>
        )}
        {mint.kind === "minted" && (
          <div className="mt-2 space-y-2">
            <p className="text-sm text-muted">{mint.words}</p>
            <AskTheMarket marketTicker={mint.ticker} />
          </div>
        )}
      </div>
    </article>
  );
}

function GameHeading({ card }: { card: CardData }) {
  return (
    <div className="mb-3">
      <Link
        href={`/game/${encodeURIComponent(card.game_event_ticker)}`}
        className="font-mono text-xs text-accent underline-offset-4 hover:underline"
      >
        {fixtureOf(card.game_event_ticker)}
      </Link>
      <span className="ml-2 text-xs text-muted">
        kickoff {kickoffText(card.kickoff_ms)}
      </span>
    </div>
  );
}

function LegRow({ leg }: { leg: GameScriptLeg }) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
      <span className="min-w-0 text-sm">
        <span className="font-mono text-xs font-semibold uppercase">
          {leg.side}
        </span>{" "}
        {leg.title}
        {leg.side_label ? (
          <span className="text-xs text-muted"> ({leg.side_label})</span>
        ) : null}
      </span>
      <span className="tabular text-xs text-muted">
        {leg.ask_display !== null ? (
          <>Kalshi ask {leg.ask_display}</>
        ) : (
          (leg.ask_unread_reason ?? "Kalshi's ask was not read.")
        )}
      </span>
    </li>
  );
}

/** A game with no built card: its reason, in words. Never an empty row. */
function NoCard({ card, heading }: { card: CardData; heading: boolean }) {
  return (
    <article className="rounded-xl border border-border bg-card p-4">
      {heading && <GameHeading card={card} />}
      <p className="max-w-[65ch] text-sm text-muted">
        {card.no_card_line ?? "No card was built for this game."}
      </p>
    </article>
  );
}

/**
 * The card on `/game/<event>`: the game's latest card, or a "Build card"
 * button when none is stored. A build is one metered model call and can take
 * about a minute, so the wait is shown in words, and a timeout or refusal is
 * a readable message. **Nothing here retries**: a second tap is the reader's.
 */
export function GameCardPanel({ eventTicker }: { eventTicker: string }) {
  const [card, setCard] = useState<CardData | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [buildWords, setBuildWords] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const payload = await fetchGameCards(eventTicker);
      setCard(payload.cards[0] ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "unavailable");
    }
  }, [eventTicker]);

  useEffect(() => {
    void load();
  }, [load]);

  const build = async () => {
    setBuilding(true);
    setBuildWords(null);
    const result = await buildGameCard(eventTicker);
    if (!result.ok) setBuildWords(result.refusal);
    setBuilding(false);
    await load();
  };

  const canBuild = !card || card.status.startsWith("refused");

  return (
    <section aria-label="Game-script card" className="mt-6 space-y-3">
      {card === undefined && !error && (
        <p className="text-sm text-muted">Reading this game&rsquo;s card…</p>
      )}
      {error && (
        <p className="max-w-[65ch] text-sm text-accent-2">
          The card could not be read ({error}).
        </p>
      )}
      {card && <GameScriptCard card={card} />}
      {card === null && !building && (
        <p className="max-w-[65ch] text-sm text-muted">
          No <Term k="game_script_card">game-script card</Term> is stored for
          this game yet.
        </p>
      )}
      {canBuild && card !== undefined && (
        <div>
          <Button onClick={build} disabled={building}>
            {building ? "Building…" : "Build card"}
          </Button>
          {building && (
            <p className="mt-2 max-w-[65ch] text-sm text-muted">
              Reading the news for this game. This takes about a minute; keep
              this page open and don&rsquo;t tap again.
            </p>
          )}
          {buildWords && (
            <p className="mt-2 max-w-[65ch] text-sm text-accent-2">
              {buildWords}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * The "Game-script parlays" section on `/parlays`: every stored card for an
 * upcoming game, in the kickoff order the server returns. Read on the client
 * so the page does not wait on the single-leg book reads behind the asks.
 */
export function GameScriptParlays() {
  const [data, setData] = useState<GameScriptCards | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fetchGameCards()
      .then((payload) => {
        if (live) setData(payload);
      })
      .catch((err) => {
        if (live) setError(err instanceof Error ? err.message : "unavailable");
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <section aria-label="Game-script parlays" className="mt-10">
      <h2 className="display text-2xl sm:text-3xl">Game-script parlays</h2>
      <p className="mt-2 max-w-[65ch] text-sm leading-relaxed text-muted">
        One short story per game with two or three{" "}
        <Term k="same_game_parlay">same-game</Term> picks that fit it, in
        kickoff order. Each pick shows Kalshi&rsquo;s own ask for that pick
        alone; the makers&rsquo; quote is the only price for the whole ticket.
      </p>
      {error && (
        <p className="mt-4 text-sm text-accent-2">
          The cards could not be read ({error}).
        </p>
      )}
      {!data && !error && (
        <p className="mt-4 text-sm text-muted">Reading the stored cards…</p>
      )}
      {data && data.cards.length === 0 && (
        <p className="mt-4 max-w-[65ch] text-sm text-muted">
          No game-script card is stored for an upcoming game. Open a game and
          tap Build card to make one.
        </p>
      )}
      {data && data.cards.length > 0 && (
        <ul className="mt-4 space-y-4">
          {data.cards.map((card) => (
            <li key={card.id}>
              <GameScriptCard card={card} heading />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
