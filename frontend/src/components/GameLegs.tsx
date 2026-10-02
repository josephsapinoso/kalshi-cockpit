"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  fetchGameLegs,
  mintGameCombo,
  type GameLeg,
  type GameLegGroup,
  type GameLegs as GameLegsData,
} from "@/lib/api";
import AskTheMarket from "@/components/AskTheMarket";
import ScoutDesk from "@/components/ScoutDesk";
import Term from "@/components/Term";
import { Button, SectionLabel } from "@/components/ui";
import { formatClock } from "@/lib/format";
import { sideLabelAddsWords } from "@/lib/sideLabel";

/**
 * The same-game parlay builder (#202): every leg Kalshi offers on one game,
 * the scout desk beside them, and a mint button once two are ticked.
 *
 * Joe's answer to #200 was to lead with the sports factors and keep price
 * secondary, so the desk's own chance is shown where it has one and its
 * absence is SHOWN, in words, where it does not -- most props, first-half and
 * quarter markets, team totals and touchdown scorers have no desk reading.
 * A leg with no chance is never hidden and never drawn as 0%.
 *
 * **No combined chance is computed or shown, and none may be.** The desk has
 * no model of how legs of one game move together, so any single number for
 * the whole ticket would be invented. The sentence below says so, and the
 * makers' quote (asked for through `<AskTheMarket>` after the mint) is where
 * that link gets priced.
 *
 * **The order is the server's, fixed, and never a function of any chance or
 * price** (ADR 0071): nothing on this component sorts or ranks. The
 * one-rung-per-event rule the server enforces is enforced here too, so a
 * refusal is the rare case rather than the common one.
 */

const NO_COMBINED_CHANCE_LINE =
  "The desk doesn't know how these legs move together, so it shows no " +
  "combined chance. The makers' quote prices that in.";

const EXTRA_LEG_LINE =
  "Each extra leg is one more thing a maker can charge for.";

type Side = "yes" | "no";

/**
 * Kalshi's ask for one side as the listing printed it (#276), integer tenths
 * from the server; `null` is "unreadable", never zero. Depth at the YES ask is
 * the YES ask size; depth at the NO ask is the size of the resting YES bid.
 * The type lives here because `GameLeg` is not this lane's file.
 */
type ListedSide = {
  ask_tenths: number | null;
  ask_display: string | null;
  size: number | null;
  size_display: string | null;
};
type GameLegListed = GameLeg & {
  listed?: { read_ms: number } & Partial<Record<Side, ListedSide>>;
};

function ListedAsk({ leg, side }: { leg: GameLeg; side: Side }) {
  const listed = (leg as GameLegListed).listed;
  const facts = listed?.[side];
  return (
    <p className="mt-0.5 text-[11px] text-muted">
      {side.toUpperCase()}:{" "}
      <Term k="ask">Kalshi ask, as listed</Term>{" "}
      {facts && facts.ask_display !== null ? (
        <>
          <span className="tabular">{facts.ask_display}</span>
          {facts.size_display !== null && (
            <>
              {" "}&middot; <Term k="depth">depth</Term>{" "}
              <span className="tabular">{facts.size_display}</span> at that price
            </>
          )}
          {listed && <> &middot; read {formatClock(listed.read_ms)}</>}
        </>
      ) : (
        <>none readable{listed ? <> &middot; read {formatClock(listed.read_ms)}</> : null}</>
      )}
    </p>
  );
}

export default function GameLegs({ eventTicker }: { eventTicker: string }) {
  const [data, setData] = useState<GameLegsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // market_ticker -> the side ticked on it. One side per market by shape.
  const [ticked, setTicked] = useState<Record<string, Side>>({});
  const [mint, setMint] = useState<
    | { kind: "idle" }
    | { kind: "minting" }
    | { kind: "minted"; ticker: string; words: string }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  useEffect(() => {
    let live = true;
    fetchGameLegs(eventTicker)
      .then((payload) => {
        if (live) setData(payload);
      })
      .catch((err) => {
        if (live)
          setError(err instanceof Error ? err.message : "unavailable");
      });
    return () => {
      live = false;
    };
  }, [eventTicker]);

  const legsByMarket = useMemo(() => {
    const map = new Map<string, GameLeg>();
    for (const group of data?.groups ?? []) {
      for (const leg of group.legs) map.set(leg.market_ticker, leg);
    }
    return map;
  }, [data]);

  const toggle = useCallback((leg: GameLeg, side: Side) => {
    // Any change to the ticket makes a minted combination stale: it was
    // minted for the OLD set of legs.
    setMint({ kind: "idle" });
    setTicked((current) => {
      const next = { ...current };
      if (next[leg.market_ticker] === side) {
        delete next[leg.market_ticker];
      } else {
        next[leg.market_ticker] = side;
      }
      return next;
    });
  }, []);

  const tickedLegs = Object.entries(ticked)
    .map(([market, side]) => ({ leg: legsByMarket.get(market), side }))
    .filter((t): t is { leg: GameLeg; side: Side } => t.leg !== undefined);

  const build = async () => {
    setMint({ kind: "minting" });
    const result = await mintGameCombo(
      eventTicker,
      tickedLegs.map(({ leg, side }) => ({
        market_ticker: leg.market_ticker,
        event_ticker: leg.event_ticker,
        side,
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

  if (error) {
    return (
      <p className="mt-6 max-w-[65ch] text-sm text-accent-2">
        {error} Nothing was created.
      </p>
    );
  }
  if (!data) {
    return <p className="mt-6 text-sm text-muted">Reading Kalshi&rsquo;s legs for this game…</p>;
  }

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-4">
        <p className="max-w-[65ch] text-sm text-muted">
          Tick two or more <Term k="leg">legs</Term> to build a{" "}
          <Term k="same_game_parlay">same-game parlay</Term>. Kalshi lists{" "}
          {data.leg_count} legs on this game. Where the desk has its own
          chance for a leg it shows it; where it does not, it says why.
        </p>
        <p className="max-w-[65ch] text-sm">{NO_COMBINED_CHANCE_LINE}</p>
        <p className="max-w-[65ch] text-xs text-muted">{EXTRA_LEG_LINE}</p>

        {data.unreadable_events.length > 0 && (
          <div className="rounded-lg border border-accent-2/50 bg-accent-2-soft px-3 py-2 text-xs">
            {data.unreadable_events.map((u) => (
              <p key={u.event_ticker}>{u.words}</p>
            ))}
          </div>
        )}
        {data.skipped_events > 0 && (
          <p className="text-xs text-accent-2">
            {data.skipped_events} more market families on this game are not
            listed here.
          </p>
        )}

        {data.groups.map((group) => (
          <Group
            key={group.series}
            group={group}
            ticked={ticked}
            legsByMarket={legsByMarket}
            onToggle={toggle}
          />
        ))}
      </div>

      <aside className="space-y-4 lg:sticky lg:top-4 lg:self-start">
        {data.game_market_ticker && (
          <section
            aria-label="Scout desk for this game"
            className="rounded-xl border border-border bg-card p-4"
          >
            <SectionLabel>Scout desk</SectionLabel>
            <ScoutDesk ticker={data.game_market_ticker} />
          </section>
        )}

        <section
          aria-label="Your combination"
          className="rounded-xl border border-border bg-card p-4"
        >
          <SectionLabel>Your combination</SectionLabel>
          {tickedLegs.length === 0 ? (
            <p className="mt-2 text-sm text-muted">Nothing ticked yet.</p>
          ) : (
            <ol className="mt-2 space-y-1 text-sm">
              {tickedLegs.map(({ leg, side }) => (
                <li key={leg.market_ticker}>
                  <span className="font-semibold">{side.toUpperCase()}</span>{" "}
                  {leg.title}
                </li>
              ))}
            </ol>
          )}
          <Button
            tone="primary"
            className="mt-3"
            onClick={build}
            disabled={tickedLegs.length < 2 || mint.kind === "minting"}
          >
            {mint.kind === "minting" ? "Building…" : "Build this combination"}
          </Button>
          {tickedLegs.length === 1 && (
            <p className="mt-2 text-xs text-muted">
              Tick one more leg. A combination needs at least two.
            </p>
          )}
          {mint.kind === "refused" && (
            <p className="mt-2 text-sm text-accent-2">{mint.words}</p>
          )}
          {mint.kind === "minted" && (
            <div className="mt-3 space-y-2">
              <p className="text-sm text-muted">{mint.words}</p>
              <AskTheMarket marketTicker={mint.ticker} />
            </div>
          )}
        </section>
      </aside>
    </div>
  );
}

function Group({
  group,
  ticked,
  legsByMarket,
  onToggle,
}: {
  group: GameLegGroup;
  ticked: Record<string, Side>;
  legsByMarket: Map<string, GameLeg>;
  onToggle: (leg: GameLeg, side: Side) => void;
}) {
  // Which one-rung events already have a leg ticked, and on which market:
  // every OTHER leg of that event is switched off, because Kalshi takes one.
  const takenBy = new Map<string, string>();
  for (const market of Object.keys(ticked)) {
    const leg = legsByMarket.get(market);
    if (leg && leg.one_per_event) takenBy.set(leg.event_ticker, market);
  }
  return (
    <details
      open={group.legs.length <= 12}
      className="rounded-xl border border-border bg-card"
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
        {group.label}{" "}
        <span className="font-mono text-xs font-normal text-muted">
          {group.legs.length} legs
          {group.one_per_event ? " · pick one" : ""}
        </span>
      </summary>
      <ul className="divide-y divide-border px-4 pb-2">
        {group.legs.map((leg) => {
          const holder = takenBy.get(leg.event_ticker);
          const blocked =
            leg.one_per_event &&
            holder !== undefined &&
            holder !== leg.market_ticker;
          return (
            <li key={leg.market_ticker} className="py-2">
              <p className="text-sm">{leg.title}</p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {leg.allowed_sides.map((side) => {
                  const facts = leg.sides[side];
                  const checked = ticked[leg.market_ticker] === side;
                  // Kalshi's NO sub-title repeats the YES one, so the server
                  // words the NO side as its opposite (#275); show it when it
                  // says anything the title does not.
                  const sideWords =
                    side === "yes" ? leg.yes_label : leg.no_label;
                  return (
                    <label
                      key={side}
                      className={`flex items-center gap-2 text-sm ${
                        blocked ? "opacity-50" : ""
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={blocked}
                        onChange={() => onToggle(leg, side)}
                      />
                      <span className="font-mono text-xs uppercase">
                        {side}
                      </span>
                      {sideWords &&
                        sideLabelAddsWords(leg.title, sideWords) && (
                          <span className="text-xs">{sideWords}</span>
                        )}
                      <span className="tabular text-xs text-muted">
                        {facts && facts.chance !== null
                          ? facts.chance_display
                          : "no desk price"}
                      </span>
                    </label>
                  );
                })}
              </div>
              {leg.allowed_sides.map((side) => (
                <ListedAsk key={`ask-${side}`} leg={leg} side={side} />
              ))}
              {leg.allowed_sides.map((side) => {
                const facts = leg.sides[side];
                if (!facts || facts.chance !== null) return null;
                return (
                  <p key={side} className="mt-0.5 text-[11px] text-muted">
                    {side.toUpperCase()}: {facts.unknown_reason ?? "unknown"}.
                  </p>
                );
              })}
              {blocked && (
                <p className="mt-0.5 text-[11px] text-muted">
                  Kalshi takes one leg from this group, and one is already
                  ticked.
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
