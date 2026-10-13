"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

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
import { keyNumberWords } from "@/components/ParlayCards";
import ManualTicket from "@/components/ManualTicket";
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
  belowHeading,
}: {
  eventTicker: string;
  /** The raw `?legs=` value; ticked once, when the listing first arrives. */
  initialLegs?: string;
  /**
   * What sits between the game's heading and the leg menu -- the page passes
   * the game-script card panel, so the title and kickoff come first on the
   * page (Joe, 2026-10-02) without a second read of the listing.
   */
  belowHeading?: ReactNode;
}) {
  const [data, setData] = useState<GameLegsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  // market_ticker -> the side ticked on it. One side per market by shape.
  const [ticked, setTicked] = useState<Record<string, Side>>({});
  const [query, setQuery] = useState("");
  // Which groups are open; every group starts collapsed except those holding
  // a ticked leg (pre-ticked `?legs=` included), decided once per listing.
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
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
        const opened: Record<string, boolean> = {};
        for (const group of payload.groups) {
          if (group.legs.some((leg) => leg.market_ticker in wanted)) {
            opened[group.series] = true;
          }
        }
        setOpenGroups(opened);
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

  // Joe's search text is the only thing that hides a leg. Text only, and the
  // server's order is kept.
  const visible = useMemo(() => {
    const map = new Map<string, GameLeg[]>();
    for (const group of data?.groups ?? []) {
      map.set(group.series, group.legs.filter((leg) => legMatches(leg, query)));
    }
    return map;
  }, [data, query]);

  const jumpTo = useCallback((group: GameLegGroup) => {
    setOpenGroups((current) => ({ ...current, [group.series]: true }));
    // Let the group open before scrolling to it.
    window.setTimeout(() => {
      document
        .getElementById(groupAnchor(group))
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 0);
  }, []);

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
        {belowHeading}
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
        {belowHeading}
        <p className="mt-6 text-sm text-muted">Reading Kalshi&rsquo;s legs for this game…</p>
      </>
    );
  }

  return (
    <>
    <GameHeading eventTicker={eventTicker} data={data} />
    {belowHeading}
    <div className="mt-6 grid gap-6 pb-24 lg:grid-cols-[minmax(0,1fr)_22rem] lg:pb-0">
      <div className="min-w-0 space-y-4">
        <p className="max-w-[65ch] text-sm text-muted">
          Tick two or more <Term k="leg">legs</Term> to build a{" "}
          <Term k="same_game_parlay">same-game parlay</Term>. Kalshi lists{" "}
          {data.leg_count} legs on this game. Where the desk has its own
          chance for a leg it shows it; where it does not, it says why. To bet
          one leg on its own, as a <Term k="single">single</Term>, use
          &ldquo;Bet this one alone&rdquo; on its row.
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

        <JumpStrip
          groups={data.groups}
          visible={visible}
          ticked={ticked}
          legsByMarket={legsByMarket}
          query={query}
          onQuery={setQuery}
          onJump={jumpTo}
        />

        {query.trim() !== "" && (
          <p className="text-xs text-muted">
            Showing legs whose words match &ldquo;{query.trim()}&rdquo;. Clear
            the search to see every leg.
          </p>
        )}

        {data.groups.map((group) => {
          const legs = visible.get(group.series) ?? [];
          const searching = query.trim() !== "";
          if (searching && legs.length === 0) return null;
          return (
            <Group
              key={group.series}
              group={group}
              legs={legs}
              open={searching || openGroups[group.series] === true}
              onOpenChange={(isOpen) =>
                setOpenGroups((current) => ({ ...current, [group.series]: isOpen }))
              }
              ticked={ticked}
              legsByMarket={legsByMarket}
              onToggle={toggle}
            />
          );
        })}
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
  // Rest is the GAME's, copied onto every leg by the server
  // (game_builder.py:616), so it is drawn once, here, from the first leg that
  // carries it -- not once per leg.
  const leg = data?.groups.flatMap((g) => g.legs).find((l) => l.rest);
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
      {leg && <RestChip rest={leg.rest} />}
    </div>
  );
}

/**
 * Case-insensitive text match over what Joe can read on a leg. The search
 * box is the ONLY thing that ever hides a leg (#378), and it filters by text
 * alone: never by chance, price, rest or anything else (ADR 0071).
 */
function legMatches(leg: GameLeg, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (q === "") return true;
  return [leg.title, leg.yes_label, leg.no_label, leg.player].some(
    (field) => field !== null && field !== undefined && field.toLowerCase().includes(q),
  );
}

/**
 * One screen row: a single leg, or -- inside a one-rung group -- every rung
 * of one Kalshi event (a ladder), in the server's order of first appearance.
 */
type LegRow = { key: string; legs: GameLeg[] };

function rowsOf(group: GameLegGroup, legs: GameLeg[]): LegRow[] {
  if (!group.one_per_event) {
    return legs.map((leg) => ({ key: leg.market_ticker, legs: [leg] }));
  }
  const rows: LegRow[] = [];
  const byEvent = new Map<string, LegRow>();
  for (const leg of legs) {
    const existing = byEvent.get(leg.event_ticker);
    if (existing) {
      existing.legs.push(leg);
    } else {
      const row = { key: leg.event_ticker, legs: [leg] };
      byEvent.set(leg.event_ticker, row);
      rows.push(row);
    }
  }
  return rows;
}

/** The words every rung's title starts with, trimmed to a whole word. */
function commonTitle(legs: GameLeg[]): string {
  const first = legs[0].title;
  let end = first.length;
  for (const leg of legs) {
    let i = 0;
    while (i < end && i < leg.title.length && leg.title[i] === first[i]) i++;
    end = i;
  }
  const cut = first.slice(0, end);
  const trimmed = cut.includes(" ") ? cut.slice(0, cut.lastIndexOf(" ")) : "";
  return trimmed.trim() === "" ? first : trimmed.trim();
}

/** What distinguishes one rung from its siblings: its title past the common words. */
function rungLabel(leg: GameLeg, common: string): string {
  const rest = leg.title.startsWith(common) ? leg.title.slice(common.length).trim() : "";
  return rest !== "" ? rest : (leg.yes_label ?? leg.title);
}

function SideButton({
  leg,
  side,
  checked,
  sideBlocked,
  prefix,
  onToggle,
}: {
  leg: GameLeg;
  side: Side;
  checked: boolean;
  sideBlocked: boolean;
  /** For a ladder rung: which rung this button is. */
  prefix?: string;
  onToggle: (leg: GameLeg, side: Side) => void;
}) {
  const ask = (leg as GameLegListed).listed?.[side]?.ask_display ?? null;
  return (
    <button
      type="button"
      aria-pressed={checked}
      disabled={sideBlocked}
      onClick={() => onToggle(leg, side)}
      className={`tabular min-h-9 rounded-md border px-2.5 py-1 text-xs font-semibold ${
        checked
          ? "border-accent bg-accent-fill text-white"
          : "border-border bg-card"
      } ${sideBlocked ? "opacity-50" : ""}`}
    >
      {prefix ? `${prefix} ` : ""}
      {side.toUpperCase()} {ask ?? "no ask"}
    </button>
  );
}

/**
 * Everything about one leg that is not the title and the price buttons:
 * the listed ask's depth and read time, the desk's chance (or the reason it
 * has none), and the single bet. Opened by tap, never by default.
 */
function LegDetails({ leg }: { leg: GameLeg }) {
  return (
    <div className="mt-1 space-y-0.5">
      {leg.allowed_sides.map((side) => {
        const facts = leg.sides[side];
        const sideWords = side === "yes" ? leg.yes_label : leg.no_label;
        return (
          <p key={`chance-${side}`} className="text-[11px] text-muted">
            <span className="font-mono uppercase">{side}</span>
            {sideWords && sideLabelAddsWords(leg.title, sideWords) && (
              <> {sideWords}</>
            )}
            {" · desk chance "}
            <span className="tabular">
              {facts && facts.chance !== null ? facts.chance_display : "no desk price"}
            </span>
          </p>
        );
      })}
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
      {/* Bet this leg alone (#356). One ticket per allowed side, each
          opened on the side its own row names: ManualTicket falls back
          to the OTHER side when the preferred one has no ask, so a
          side with no readable ask is not offered at all rather than
          opening on a contract the row did not name. No ordering and
          no mark: the ask and the chance are facts on the row. */}
      {leg.allowed_sides.map((side) => {
        const facts = leg.sides[side];
        const askTenths =
          (leg as GameLegListed).listed?.[side]?.ask_tenths ?? null;
        if (askTenths === null) return null;
        const sideWords = side === "yes" ? leg.yes_label : leg.no_label;
        return (
          <ManualTicket
            key={`single-${side}`}
            ticker={leg.market_ticker}
            preferSide={side}
            variant="inline"
            openLabel={`Bet this one alone: ${side.toUpperCase()}${
              sideWords && sideLabelAddsWords(leg.title, sideWords)
                ? ` ${sideWords}`
                : ""
            }`}
            note={
              facts && facts.chance !== null
                ? "One leg, on its own. This is not a parlay — it wins or loses by itself."
                : "One leg, on its own, and the desk has no price for it. Nothing on this product says what it is worth — your own number is the only estimate there is."
            }
          />
        );
      })}
    </div>
  );
}

function Group({
  group,
  legs,
  open,
  onOpenChange,
  ticked,
  legsByMarket,
  onToggle,
}: {
  group: GameLegGroup;
  /** The group's legs that survive Joe's search text; the server's order. */
  legs: GameLeg[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
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
  const rows = rowsOf(group, legs);
  return (
    <details
      id={groupAnchor(group)}
      open={open}
      onToggle={(e) => onOpenChange(e.currentTarget.open)}
      className="scroll-mt-44 rounded-xl border border-border bg-card"
    >
      <summary className="cursor-pointer px-4 py-3 text-sm font-semibold">
        {group.label}{" "}
        <span className="font-mono text-xs font-normal text-muted">
          {legs.length} legs
          {group.one_per_event ? " · pick one" : ""}
        </span>
      </summary>
      <ul className="divide-y divide-border px-4 pb-2">
        {rows.map((row) => {
          const ladder = row.legs.length > 1;
          const common = ladder ? commonTitle(row.legs) : "";
          return (
            <li key={row.key} className="py-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <p className="min-w-0 flex-1 basis-40 text-sm">
                  {ladder ? common : row.legs[0].title}
                  {!ladder && row.legs[0].key_number ? (
                    <span className="ml-2 whitespace-nowrap text-xs text-muted">
                      <Term k="key_number">{keyNumberWords(row.legs[0].key_number)}</Term>
                    </span>
                  ) : null}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {row.legs.map((leg) => {
                    const holder = takenBy.get(leg.event_ticker);
                    const blocked =
                      leg.one_per_event &&
                      holder !== undefined &&
                      holder !== leg.market_ticker;
                    // The win leg of a team whose cover is ticked (#277).
                    // Greyed only when it is NOT itself ticked, so a pair
                    // ticked in the other order can still be unticked; the
                    // Build button refuses that pair too.
                    const impliedByCover = coverTickedFor(leg, ticked, legsByMarket);
                    const winGreyed =
                      impliedByCover !== null && ticked[leg.market_ticker] !== "yes";
                    return leg.allowed_sides.map((side) => {
                      const sideBlocked = blocked || (side === "yes" && winGreyed);
                      return (
                        <SideButton
                          key={`${leg.market_ticker}-${side}`}
                          leg={leg}
                          side={side}
                          checked={ticked[leg.market_ticker] === side}
                          sideBlocked={sideBlocked}
                          prefix={ladder ? rungLabel(leg, common) : undefined}
                          onToggle={onToggle}
                        />
                      );
                    });
                  })}
                </div>
              </div>
              <details className="mt-1">
                <summary className="cursor-pointer text-[11px] text-muted">
                  Depth, desk chance, bet alone
                </summary>
                {row.legs.map((leg) => (
                  <div key={leg.market_ticker} className="mt-1">
                    {ladder && (
                      <p className="text-xs font-semibold">
                        {rungLabel(leg, common)}
                        {leg.key_number ? (
                          <span className="ml-2 whitespace-nowrap font-normal text-muted">
                            <Term k="key_number">{keyNumberWords(leg.key_number)}</Term>
                          </span>
                        ) : null}
                      </p>
                    )}
                    <LegDetails leg={leg} />
                  </div>
                ))}
              </details>
              {row.legs.map((leg) => {
                const holder = takenBy.get(leg.event_ticker);
                const blocked =
                  leg.one_per_event &&
                  holder !== undefined &&
                  holder !== leg.market_ticker;
                const impliedByCover = coverTickedFor(leg, ticked, legsByMarket);
                return (
                  <div key={`notes-${leg.market_ticker}`}>
                    {blocked && !ladder && (
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
                  </div>
                );
              })}
              {ladder && row.legs.some((leg) => {
                const holder = takenBy.get(leg.event_ticker);
                return holder !== undefined && holder !== leg.market_ticker;
              }) && (
                <p className="mt-0.5 text-[11px] text-muted">
                  Kalshi takes one rung from this event, and one is already
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

/** The DOM id a jump chip scrolls to. */
function groupAnchor(group: GameLegGroup): string {
  return `game-group-${group.series}`;
}

/**
 * Sticky strip of one chip per group, with the search box. A chip opens its
 * group and scrolls to it. The chips follow the server's order and count what
 * is there; none is ranked and none is dropped (a group the search empties
 * stays, at zero, so Joe sees that it was searched).
 */
function JumpStrip({
  groups,
  visible,
  ticked,
  legsByMarket,
  query,
  onQuery,
  onJump,
}: {
  groups: GameLegGroup[];
  visible: Map<string, GameLeg[]>;
  ticked: Record<string, Side>;
  legsByMarket: Map<string, GameLeg>;
  query: string;
  onQuery: (q: string) => void;
  onJump: (group: GameLegGroup) => void;
}) {
  return (
    <nav
      aria-label="Jump to a group of legs"
      style={{ top: "var(--nav-height, 69px)" }}
      className="sticky z-30 -mx-1 space-y-2 border-b border-border bg-background px-1 py-2"
    >
      <input
        type="search"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
        placeholder="Search legs (team, player, line)"
        aria-label="Search legs"
        className="w-full rounded-md border border-border bg-card px-3 py-1.5 text-sm"
      />
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {groups.map((group) => {
          const count = visible.get(group.series)?.length ?? 0;
          const tickedHere = Object.keys(ticked).filter(
            (market) => legsByMarket.get(market)?.series === group.series,
          ).length;
          return (
            <button
              key={group.series}
              type="button"
              onClick={() => onJump(group)}
              className="shrink-0 whitespace-nowrap rounded-full border border-border bg-card px-3 py-1 text-xs"
            >
              {group.label}{" "}
              <span className="font-mono text-muted">{count}</span>
              {tickedHere > 0 && (
                <span className="tabular ml-1.5 rounded-full bg-accent-fill px-1.5 text-white">
                  {tickedHere}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
