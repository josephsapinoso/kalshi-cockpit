"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  displayZoneLabel,
  fetchGameLegs,
  formatKickoff,
  mintGameCombo,
  type GameLeg,
  type GameLegGroup,
  type GameLegs as GameLegsData,
} from "@/lib/api";
import AskTheMarket from "@/components/AskTheMarket";
import { CheckTheseLegs } from "@/components/GameScriptCard";
import { RestChip } from "@/components/ParlayCards";
import ScoutDesk from "@/components/ScoutDesk";
import Term from "@/components/Term";
import { Button, SectionLabel } from "@/components/ui";
import { formatClock } from "@/lib/format";
import { leagueLabel } from "@/lib/leagueLabel";
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

const IMPLIED_WIN_LINE =
  "Winning by a margin already guarantees the win, and Kalshi refuses both " +
  "in one combination. Untick the cover to tick the win.";

/**
 * The market ticker of a ticked YES cover ("that team wins by N+") on the same
 * game and team as `leg`, when `leg` is that team's moneyline; else `null`.
 * Mirrors `drop_implied_win_legs` (backend/store/game_script_cards.py), which
 * the server uses to refuse the pair; the screen only keeps the pair from
 * being ticked by accident.
 */
function coverTickedFor(
  leg: GameLeg,
  ticked: Record<string, Side>,
  legsByMarket: Map<string, GameLeg>,
): string | null {
  if (leg.kind !== "GAME") return null;
  const [, fixture, team] = leg.market_ticker.split("-");
  for (const [market, side] of Object.entries(ticked)) {
    if (side !== "yes") continue;
    const other = legsByMarket.get(market);
    if (!other || other.kind !== "SPREAD") continue;
    const [, otherFixture, otherTeam] = market.split("-");
    if (
      otherFixture === fixture &&
      otherTeam !== undefined &&
      otherTeam.replace(/\d+$/, "") === team
    ) {
      return market;
    }
  }
  return null;
}

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

/**
 * `ticker:side,ticker:side` from a card's "Change a leg" link (#295), as
 * `[ticker, side]` pairs. Anything that is not `<ticker>:yes|no` is dropped
 * here; whether the ticker is on this game's listing is checked against the
 * listing in `preTick`, never assumed.
 */
export function parseLegsParam(raw: string | undefined): [string, Side][] {
  if (!raw) return [];
  const out: [string, Side][] = [];
  for (const part of raw.split(",")) {
    const [ticker, side, ...extra] = part.trim().split(":");
    if (!ticker || extra.length > 0) continue;
    const s = (side ?? "").toLowerCase();
    if (s === "yes" || s === "no") out.push([ticker.toUpperCase(), s]);
  }
  return out;
}

/**
 * The legs of `raw` that the listing really offers, on a side that leg
 * allows, one per one-rung event. **A leg named in the URL that is not in the
 * listing is ignored, never invented** (#295): the page never ticks a box the
 * server did not list, so a stale or hand-edited link ticks fewer legs, not
 * different ones.
 */
function preTick(raw: string | undefined, listing: GameLegsData): Record<string, Side> {
  const byMarket = new Map<string, GameLeg>();
  for (const group of listing.groups) {
    for (const leg of group.legs) byMarket.set(leg.market_ticker, leg);
  }
  const ticked: Record<string, Side> = {};
  const takenEvents = new Set<string>();
  for (const [ticker, side] of parseLegsParam(raw)) {
    const leg = byMarket.get(ticker);
    if (!leg || !leg.allowed_sides.includes(side) || ticker in ticked) continue;
    if (leg.one_per_event) {
      if (takenEvents.has(leg.event_ticker)) continue;
      takenEvents.add(leg.event_ticker);
    }
    ticked[ticker] = side;
  }
  return ticked;
}

export default function GameLegs({
  eventTicker,
  initialLegs,
}: {
  eventTicker: string;
  /** The raw `?legs=` value; ticked once, when the listing first arrives. */
  initialLegs?: string;
}) {
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
        if (!live) return;
        setData(payload);
        const wanted = preTick(initialLegs, payload);
        if (Object.keys(wanted).length > 0) setTicked(wanted);
      })
      .catch((err) => {
        if (live)
          setError(err instanceof Error ? err.message : "unavailable");
      });
    return () => {
      live = false;
    };
    // `initialLegs` is read once per game: a later edit to the ticket is the
    // reader's, and a re-run here would tick his legs back.
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  // A ticked YES win beside that team's ticked YES cover: Kalshi refuses it,
  // and so does the server before any venue call (#277). Build is off.
  const impliedPair = tickedLegs.some(
    ({ leg, side }) =>
      side === "yes" && coverTickedFor(leg, ticked, legsByMarket) !== null,
  );

  const buildDisabled =
    tickedLegs.length < 2 || mint.kind === "minting" || impliedPair;

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
      <>
        <GameHeading eventTicker={eventTicker} data={null} />
        <p className="mt-6 max-w-[65ch] text-sm text-accent-2">
          {error} Nothing was created.
        </p>
      </>
    );
  }
  if (!data) {
    return (
      <>
        <GameHeading eventTicker={eventTicker} data={null} />
        <p className="mt-6 text-sm text-muted">Reading Kalshi&rsquo;s legs for this game…</p>
      </>
    );
  }

  return (
    <>
    <GameHeading eventTicker={eventTicker} data={data} />
    <div className="mt-6 grid gap-6 pb-24 lg:grid-cols-[minmax(0,1fr)_22rem] lg:pb-0">
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
          id="your-combination"
          aria-label="Your combination"
          className="scroll-mt-16 rounded-xl border border-border bg-card p-4"
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
            disabled={buildDisabled}
          >
            {mint.kind === "minting" ? "Building…" : "Build this combination"}
          </Button>
          {impliedPair && (
            <p className="mt-2 text-xs text-accent-2">{IMPLIED_WIN_LINE}</p>
          )}
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
          {/* Tap-only, and apart from Build and Ask the market: it needs no
              minted combination, and nothing here starts it. Keyed by the
              ticked set, so a verdict for the old legs never sits beside a
              new ticket. */}
          <CheckTheseLegs
            key={tickedLegs.map(({ leg, side }) => `${leg.market_ticker}:${side}`).join("|")}
            legs={tickedLegs.map(({ leg, side }) => ({
              ticker: leg.market_ticker,
              side,
            }))}
            cardKey={`game_legs:${eventTicker}`}
          />
        </section>
      </aside>

      {/* Below lg the combination panel sits under the whole menu, so the
          count and Build ride at the bottom of the screen (#278). It calls the
          same build() and reads the same buildDisabled as the panel's button;
          from lg up it is not drawn and the desktop layout is unchanged. */}
      <div
        aria-label="Build bar"
        className="sheet-safe-bottom fixed inset-x-0 bottom-0 z-40 flex items-center justify-between gap-3 border-t border-border bg-card px-4 pt-3 lg:hidden"
      >
        <span className="tabular text-sm">
          {tickedLegs.length} {tickedLegs.length === 1 ? "leg" : "legs"} ticked
        </span>
        <Button
          tone="primary"
          disabled={buildDisabled}
          onClick={async () => {
            await build();
            document
              .getElementById("your-combination")
              ?.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        >
          {mint.kind === "minting" ? "Building…" : "Build"}
        </Button>
      </div>
    </div>
    </>
  );
}

/**
 * The game's own name, kickoff and league (#293), where the page used to
 * print only the raw ticker. Each part is shown only when the listing could
 * say it; with none, the ticker stays as the fallback, never a guess.
 */
function GameHeading({
  eventTicker,
  data,
}: {
  eventTicker: string;
  data: GameLegsData | null;
}) {
  const title = data?.game_title ?? null;
  const kickoff = data?.kickoff_ms ?? null;
  const sport = data?.sport_key ?? null;
  return (
    <div className="mt-2">
      <p className="max-w-[65ch] text-base font-semibold">
        {title ?? <span className="font-mono text-xs font-normal text-muted">{eventTicker}</span>}
      </p>
      {(kickoff !== null || sport) && (
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
          {kickoff !== null && (
            <span className="tabular">
              kickoff {formatKickoff(kickoff)} {displayZoneLabel(kickoff)}
            </span>
          )}
          {sport && (
            <span className="rounded border border-border px-1 font-mono text-[0.65rem] uppercase tracking-wide">
              {leagueLabel(sport)}
            </span>
          )}
        </p>
      )}
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
          // The win leg of a team whose cover is ticked (#277). Greyed only
          // when it is NOT itself ticked, so a pair ticked in the other order
          // can still be unticked; the Build button refuses that pair too.
          const impliedByCover = coverTickedFor(leg, ticked, legsByMarket);
          const winGreyed =
            impliedByCover !== null && ticked[leg.market_ticker] !== "yes";
          return (
            <li key={leg.market_ticker} className="py-2">
              <p className="text-sm">{leg.title}</p>
              <RestChip rest={leg.rest} />
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {leg.allowed_sides.map((side) => {
                  const facts = leg.sides[side];
                  const checked = ticked[leg.market_ticker] === side;
                  // Kalshi's NO sub-title repeats the YES one, so the server
                  // words the NO side as its opposite (#275); show it when it
                  // says anything the title does not.
                  const sideWords =
                    side === "yes" ? leg.yes_label : leg.no_label;
                  const sideBlocked =
                    blocked || (side === "yes" && winGreyed);
                  return (
                    <label
                      key={side}
                      className={`flex items-center gap-2 text-sm ${
                        sideBlocked ? "opacity-50" : ""
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={sideBlocked}
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
              {impliedByCover !== null && (
                <p className="mt-0.5 text-[11px] text-muted">
                  {IMPLIED_WIN_LINE}
                </p>
              )}
            </li>
          );
        })}
      </ul>
    </details>
  );
}
