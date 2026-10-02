"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  buildGameCard,
  DISPLAY_TIME_ZONE,
  displayZoneLabel,
  fetchGameCards,
  formatAge,
  formatKickoff,
  mintGameCombo,
  type GameScriptCard as CardData,
  type GameScriptCards,
  type GameScriptLeg,
} from "@/lib/api";
import AskTheMarket from "@/components/AskTheMarket";
import Term from "@/components/Term";
import { Button, SectionLabel } from "@/components/ui";
import { leagueLabel } from "@/lib/leagueLabel";
import { sideLabelAddsWords } from "@/lib/sideLabel";

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

/** Why a card shows one leg fewer than its scout picked. Kalshi refuses a
 * "team wins" leg beside "that team wins by N+", and dropping it changes
 * nothing about when the ticket pays. */
const DROPPED_WIN_LINE =
  "The scout also picked this team to win. That pick is left off: winning " +
  "by the margin above already includes winning, so the ticket pays on " +
  "exactly the same results, and Kalshi refuses the pair.";

/** Inactives come out this long before kickoff (the card's own footnote). */
const INACTIVES_LEAD_MS = 90 * 60_000;

/**
 * How old this card is (#246), in plain words, from `built_ms`.
 *
 * A card written at T-24h predates the inactives list, so when it was built
 * before its game's inactives time it says so. **Shown only**: nothing on this
 * card is gated on age. Read after mount, never during render, so the server's
 * clock cannot disagree with the client's in the markup.
 */
function CardAge({ card }: { card: CardData }) {
  const [nowMs, setNowMs] = useState<number | null>(null);
  // Once per mount: a card's age is read when it is looked at, and this
  // component never polls (the card test bars timers on this file).
  useEffect(() => {
    setNowMs(Date.now());
  }, []);
  if (nowMs === null) return null;
  const age = formatAge(Math.max(0, nowMs - card.built_ms));
  const beforeInactives =
    card.built_ms < card.kickoff_ms - INACTIVES_LEAD_MS;
  return (
    <p className="mt-1 text-xs text-muted">
      Written {age}
      {beforeInactives ? ", before inactives" : ""}.
    </p>
  );
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

      {/* The compact face (#221): one line per pick and nothing that needs a
          scroll. Every leg row carries the game's kickoff, because a pick
          with no time on it is a pick you cannot place in the day. */}
      <ul className="divide-y divide-border">
        {card.legs.map((leg) => (
          <LegRow
            key={`${leg.market_ticker}-${leg.side}`}
            leg={leg}
            kickoffMs={card.kickoff_ms}
          />
        ))}
      </ul>
      <p className="mt-2 max-w-[65ch] text-xs text-muted">
        {NO_COMBINED_CHANCE_LINE}
      </p>
      <CardAge card={card} />

      {/* The reasoning, one tap away rather than in the way. */}
      <details className="mt-3 rounded border border-border p-3">
        <summary className="min-h-[36px] cursor-pointer text-sm font-semibold">
          Why this card
        </summary>
        <SectionLabel>
          <Term k="game_script_card">Game-script card</Term>
        </SectionLabel>
        <p className="mt-2 max-w-[65ch] text-sm leading-relaxed">
          {card.story}
        </p>
        {card.dropped_legs.length > 0 && (
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            {DROPPED_WIN_LINE}
          </p>
        )}
        <p className="mt-3 max-w-[65ch] text-sm">
          <span className="font-semibold">
            <Term k="drop_if">Drop it if</Term>:
          </span>{" "}
          {card.drop_if}
        </p>
        {card.sources && card.sources.length > 0 && (
          <ul className="mt-2 max-w-[65ch] space-y-1 text-xs text-muted">
            {card.sources.map((source) => (
              <li key={source.url}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2"
                >
                  {source.url}
                </a>
                {source.published ? ` (${source.published})` : ""}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 max-w-[65ch] text-xs text-muted">
          <Term k="inactives">Inactives</Term>: {card.inactives_line}
        </p>
      </details>

      <div className="mt-3">
        <Button
          onClick={ask}
          disabled={mint.kind === "minting" || card.legs.length < 2}
        >
          {mint.kind === "minting" ? "Building…" : "Get a price"}
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
    <div className="mb-2">
      <Link
        href={`/game/${encodeURIComponent(card.game_event_ticker)}`}
        className="font-mono text-sm text-accent underline-offset-4 hover:underline"
      >
        {card.game_title ?? fixtureOf(card.game_event_ticker)}
      </Link>
      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
        <span className="tabular">kickoff {kickoffText(card.kickoff_ms)}</span>
        <span className="rounded border border-border px-1 font-mono text-[0.65rem] uppercase tracking-wide">
          {leagueLabel(card.sport_key)}
        </span>
      </p>
    </div>
  );
}

function LegRow({
  leg,
  kickoffMs,
}: {
  leg: GameScriptLeg;
  kickoffMs: number;
}) {
  return (
    <li className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2">
      <span className="min-w-0 text-sm">
        <span className="font-mono text-xs font-semibold uppercase">
          {leg.side}
        </span>{" "}
        {leg.title}
        {leg.side_label && sideLabelAddsWords(leg.title, leg.side_label) ? (
          <span className="text-xs text-muted"> ({leg.side_label})</span>
        ) : null}
      </span>
      <span className="tabular text-xs text-muted">
        {kickoffText(kickoffMs)} ·{" "}
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
      {/* The game's own name, so the page is not headed by a raw ticker
          alone (seen live 2026-09-30); the ticker stays below the h1. */}
      {card?.game_title && (
        <h2 className="text-xl font-semibold">{card.game_title}</h2>
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

type DayChoice = "today" | "tomorrow" | "all";

/** The calendar day of a moment in the desk's own zone, as `YYYY-MM-DD`. */
function dayKey(ms: number): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: DISPLAY_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(ms));
}

/** The calendar day after `key`, by date arithmetic rather than by adding 24
 * hours, so a daylight-saving night cannot skip or repeat a day. */
function nextDayKey(key: string): string {
  const [y, m, d] = key.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d + 1)).toISOString().slice(0, 10);
}

/** Day and league chips over the list. They cut it; they never order it. */
function ListFilters({
  day,
  onDay,
  league,
  onLeague,
  leagues,
}: {
  day: DayChoice;
  onDay: (next: DayChoice) => void;
  league: string | null;
  onLeague: (next: string | null) => void;
  leagues: string[];
}) {
  const days: { key: DayChoice; label: string }[] = [
    { key: "today", label: "Today" },
    { key: "tomorrow", label: "Tomorrow" },
    { key: "all", label: "All" },
  ];
  return (
    <div className="mt-4 flex flex-col gap-2">
      <div
        role="group"
        aria-label="Day"
        className="flex flex-wrap items-center gap-1.5"
      >
        {days.map((choice) => (
          <FilterChip
            key={choice.key}
            active={day === choice.key}
            onClick={() => onDay(choice.key)}
          >
            {choice.label}
          </FilterChip>
        ))}
      </div>
      {leagues.length > 1 && (
        <div
          role="group"
          aria-label="League"
          className="flex flex-wrap items-center gap-1.5"
        >
          <FilterChip active={league === null} onClick={() => onLeague(null)}>
            All leagues
          </FilterChip>
          {leagues.map((key) => (
            <FilterChip
              key={key}
              active={league === key}
              onClick={() => onLeague(key)}
            >
              {leagueLabel(key)}
            </FilterChip>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`inline-flex min-h-[40px] items-center rounded-full border px-3 text-sm transition-colors ${
        active
          ? "border-foreground font-semibold text-foreground"
          : "border-border text-muted"
      }`}
    >
      {children}
    </button>
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
  const [day, setDay] = useState<DayChoice>("all");
  const [league, setLeague] = useState<string | null>(null);

  const cards = data?.cards ?? [];
  const todayKey = dayKey(data?.now_ms ?? 0);
  const tomorrowKey = nextDayKey(todayKey);
  const matches = (card: CardData): boolean => {
    const key = dayKey(card.kickoff_ms);
    const dayOk =
      day === "all" ||
      (day === "today" && key === todayKey) ||
      (day === "tomorrow" && key === tomorrowKey);
    return dayOk && (league === null || card.sport_key === league);
  };
  const shownCount = cards.filter(matches).length;
  const hiddenCount = cards.length - shownCount;
  // The leagues on the list, in the order the list first meets them.
  const leaguesPresent = cards
    .map((card) => card.sport_key)
    .filter((key, index, all) => all.indexOf(key) === index);

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
    <section aria-label="Game-script parlays" className="mt-4">
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
        <>
          <ListFilters
            day={day}
            onDay={setDay}
            league={league}
            onLeague={setLeague}
            leagues={leaguesPresent}
          />
          <p className="mt-2 text-xs text-muted" aria-live="polite">
            {hiddenCount > 0
              ? `${hiddenCount} ${hiddenCount === 1 ? "game" : "games"} hidden by this filter.`
              : "Every game the desk has a card for is shown."}
          </p>
          {shownCount === 0 && (
            <p className="mt-3 max-w-[65ch] text-sm text-muted">
              No game matches this filter. Choose All to see every game.
            </p>
          )}
          {/* The filter is a test per card inside the map, so the list keeps
              the server's kickoff order by construction: nothing is sorted,
              reversed or rebuilt (ADR 0071). Two columns from md up. */}
          <ul className="mt-4 grid gap-4 md:grid-cols-2">
            {data.cards.map((card) =>
              matches(card) ? (
                <li key={card.id}>
                  <GameScriptCard card={card} heading />
                </li>
              ) : null,
            )}
          </ul>
        </>
      )}
    </section>
  );
}
