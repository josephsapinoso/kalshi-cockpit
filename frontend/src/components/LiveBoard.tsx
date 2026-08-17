"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import OpportunityCard from "@/components/OpportunityCard";
import { TicketTrigger } from "@/components/TicketProvider";
import type { Recommendation } from "@/lib/api";
import { liveSizing } from "@/lib/liveSizing";

/**
 * The ticker: the bettable rows, with Kalshi's prices pushed in live.
 *
 * **Nothing here computes money.** Every field this component renders arrives
 * already derived from the server — the ask, the edge, the size. The fee curve
 * is an unresolved hedge between two disagreeing sources (`core/fees.py`), and
 * shipping a second copy of it to the browser so this could subtract it would
 * put two implementations of a money calculation one refresh apart. That is the
 * failure `tasks/lessons.md` records three times. This file merges and paints.
 *
 * **A stopped ticker must look stopped.** The one failure a live feed
 * introduces that a polled page does not have is frozen prices that look
 * current — the half-dead container problem, moved into the browser. So the
 * server heartbeats on a fixed interval whether or not anything moved, and this
 * component treats silence as a fault: past `SILENT_MS` with no frame of any
 * kind, the header says so and the rows revert to their recorded ages.
 */

/** No frame of any kind for this long and the feed is presumed gone. */
const SILENT_MS = 25_000;

type Quote = {
  id: number;
  ticker: string;
  side: string;
  ask_tenths: number;
  ask_display: string;
  ask_dollars: number;
  edge_tenths: number;
  edge_cents: number;
  depth_at_ask: number | null;
  contracts: number;
  observed_ms: number;
};

type Status = "connecting" | "live" | "idle" | "down" | "silent" | "disabled";

// How often the age strings are re-rendered. A quote is bettable for 30s, so a
// second is fine resolution and cheap: it re-renders text, nothing refetches.
const AGE_TICK_MS = 1_000;

export default function LiveBoard({
  rows,
  enabled,
  quoteLimitMs,
  oddsLimitMs,
}: {
  rows: Recommendation[];
  /** False on the demo instance, which holds no Kalshi credentials. */
  enabled: boolean;
  quoteLimitMs: number;
  oddsLimitMs: number;
}) {
  const [quotes, setQuotes] = useState<Map<number, Quote>>(new Map());
  const [status, setStatus] = useState<Status>(
    enabled ? "connecting" : "disabled",
  );
  const [reason, setReason] = useState<string | null>(null);
  const [lastFrameMs, setLastFrameMs] = useState<number | null>(null);
  // Direction of the last move per row, for the flash. Held in a ref because it
  // is written while computing the next state and must not itself re-render.
  const previous = useRef<Map<number, number>>(new Map());
  const [moves, setMoves] = useState<Map<number, "up" | "down">>(new Map());

  useEffect(() => {
    if (!enabled) return;

    const source = new EventSource("/api/stream/quotes");

    source.onmessage = (message) => {
      setLastFrameMs(Date.now());
      const event = JSON.parse(message.data);

      // `down` arrives the moment the feed dies; the heartbeat repeats it, so a
      // tab that was asleep through the event still learns about it.
      if (event.type === "down" || event.down) {
        setStatus("down");
        setReason(event.reason ?? event.down ?? null);
        return;
      }
      if (event.type === "idle") {
        setStatus("idle");
        return;
      }
      if (event.type === "quotes" || event.type === "snapshot") {
        setReason(null);
        setStatus("live");
        const incoming: Quote[] = event.quotes ?? [];
        const nextMoves = new Map<number, "up" | "down">();
        setQuotes((current) => {
          const next = new Map(current);
          for (const quote of incoming) {
            const before = previous.current.get(quote.id);
            if (before !== undefined && before !== quote.ask_tenths) {
              nextMoves.set(quote.id, quote.ask_tenths > before ? "up" : "down");
            }
            previous.current.set(quote.id, quote.ask_tenths);
            next.set(quote.id, quote);
          }
          return next;
        });
        if (nextMoves.size) setMoves(nextMoves);
        return;
      }
      if (event.type === "up") {
        setStatus("live");
        setReason(null);
      }
    };

    // EventSource reconnects on its own, so this is a display concern rather
    // than a retry one. Saying "reconnecting" is the honest state: the prices on
    // screen are the last ones that arrived, and nothing is refreshing them.
    source.onerror = () => setStatus((s) => (s === "down" ? s : "connecting"));

    return () => source.close();
  }, [enabled]);

  // Silence detection. The server sends something at least every ten seconds,
  // so nothing for twenty-five means the connection is up and dead — which is
  // precisely the state that would otherwise render as a calm market.
  useEffect(() => {
    if (!enabled || lastFrameMs === null) return;
    const timer = setInterval(() => {
      if (Date.now() - lastFrameMs > SILENT_MS) setStatus("silent");
    }, 5_000);
    return () => clearInterval(timer);
  }, [enabled, lastFrameMs]);

  // **The age strings must advance whether or not anything is streaming.**
  //
  // Every other clock on this screen was driven by an arriving frame, so with
  // the feed off, idle, or dead, `merged` never recomputed and a card kept
  // rendering "quote 32s ago" indefinitely. A price is bettable for 30s; one
  // frozen at 32s while five minutes pass reads as *nearly fresh* when it is
  // long dead. That is the half-dead-container failure this component's
  // docstring exists to prevent -- prevented for the streaming case only.
  //
  // Unconditional, and deliberately not gated on `enabled`: the disabled case
  // is the one where nothing else was updating it.
  const [now, setNow] = useState<number | null>(null);
  const mountedAt = useRef<number | null>(null);
  useEffect(() => {
    mountedAt.current = Date.now();
    setNow(Date.now());
    const timer = setInterval(() => setNow(Date.now()), AGE_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  // Elapsed since hydration. `null` until the first client tick, so the server
  // render and the first client render agree and hydration does not mismatch.
  //
  // Mount-relative rather than absolute, and the tradeoff is deliberate. The
  // row carries a *relative* age computed on the server, so the unaccounted
  // gap is server-render-to-hydration -- bounded, and typically well under a
  // second. The alternative is to derive an absolute observation time from a
  // server `now_ms`, which imports client/server clock skew that is unbounded
  // and silent. A small bounded error beats an unbounded one, and this is the
  // direction the repo already chose for `occurrence_datetime`: record the
  // discrepancy rather than correct it away.
  const elapsed = now !== null && mountedAt.current !== null
    ? Math.max(0, now - mountedAt.current)
    : 0;

  // A flash is a one-shot. Without clearing it the animation would replay on
  // every unrelated re-render, so the page would twitch at random.
  useEffect(() => {
    if (!moves.size) return;
    const timer = setTimeout(() => setMoves(new Map()), 1_200);
    return () => clearTimeout(timer);
  }, [moves]);

  const streaming = status === "live";

  const merged = useMemo(
    () =>
      rows.map((row) => {
        const quote = streaming ? quotes.get(row.id) : undefined;
        if (!quote) {
          // No live quote, so age the recorded one by hand. `null` stays
          // `null`: an age the server could not compute is unknown, and
          // starting an unknown at zero and counting up would invent the one
          // number this card exists to be honest about.
          return {
            row: {
              ...row,
              quote_age_now_ms:
                row.quote_age_now_ms == null
                  ? row.quote_age_now_ms
                  : row.quote_age_now_ms + elapsed,
              odds_age_now_ms:
                row.odds_age_now_ms == null
                  ? row.odds_age_now_ms
                  : row.odds_age_now_ms + elapsed,
            } as Recommendation,
            move: undefined,
          };
        }
        return {
          // The live numbers replace the recorded ones, and `price_is_current`
          // with them: the card's "this price was read 4m ago" note is about a
          // recorded price, and there is no longer one on screen.
          row: {
            ...row,
            ask_tenths: quote.ask_tenths,
            ask_display: quote.ask_display,
            ask_dollars: quote.ask_dollars,
            edge_tenths: quote.edge_tenths,
            edge_cents: quote.edge_cents,
            depth_at_ask: quote.depth_at_ask,
            suggested_contracts: quote.contracts,
            // `now` rather than a fresh `Date.now()`, so this ages on the tick
            // between frames instead of only when one arrives. A streaming
            // feed that goes quiet for two minutes must show two minutes.
            quote_age_now_ms: Math.max(0, (now ?? Date.now()) - quote.observed_ms),
            price_is_current: true,
            freshness_confirmed: false,
          } as Recommendation,
          move: moves.get(row.id),
        };
      }),
    [rows, quotes, moves, streaming, now, elapsed],
  );

  return (
    <>
      {/* Rendered unconditionally. Hiding it when the feed is disabled left the
          one case with no other indicator at all: no banner, and until the tick
          above, no moving clock either -- so a dead feed and a healthy quiet one
          were pixel-identical. */}
      <FeedStatus status={status} reason={reason} />
      <div className="grid gap-4 sm:grid-cols-2">
        {merged.map(({ row, move }) => {
          const isLive = streaming && quotes.has(row.id);
          // The feed re-sizes rows with the same `size_position` the order
          // endpoint uses, so it can legitimately reach zero when the price
          // moves. A card at zero must stop being tappable in the same frame
          // it stops being sized -- otherwise the sheet opens on a size the
          // server has already decided to refuse. Server-side re-validation
          // would reject it, which is why this is a correctness fix on the
          // screen and not a hole in the order path.
          const card = (
            <OpportunityCard
              rec={row}
              live={isLive}
              direction={move}
              quoteLimitMs={quoteLimitMs}
              oddsLimitMs={oddsLimitMs}
            />
          );
          return (
          <div key={row.id} className={move ? `tick-${move}` : undefined}>
            {/* The ticket opens on the *merged* row, so the sheet shows the
                price the ticker is showing rather than the recorded one it
                replaced. The sheet still calls the endpoint with nothing but an
                id and a size, so a live price on screen cannot become a live
                price the server was asked to honour. */}
            {liveSizing({ suggested_contracts: row.suggested_contracts, live: isLive })
              .offerable ? (
              <TicketTrigger rec={row}>{card}</TicketTrigger>
            ) : (
              card
            )}
          </div>
          );
        })}
      </div>
    </>
  );
}

function FeedStatus({
  status,
  reason,
}: {
  status: Status;
  reason: string | null;
}) {
  // Every state says what the prices on screen currently are, because that is
  // the only question the reader has. "Reconnecting" without "these prices are
  // the last ones that arrived" is a status for the developer, not the user.
  const copy: Record<Status, { label: string; detail: string; tone: string }> = {
    connecting: {
      label: "CONNECTING",
      detail: "Prices below are the recorded ones until the feed opens.",
      tone: "text-muted",
    },
    live: {
      label: "LIVE",
      detail:
        "Kalshi prices are streaming. The edge and the size are recomputed on " +
        "the server as the book moves; the consensus behind the fair value is " +
        "not, and still ages.",
      tone: "text-positive",
    },
    idle: {
      label: "NO LIVE ROWS",
      detail:
        "Nothing is bettable, so there is nothing to stream. Not a fault — it " +
        "is the state for most of the day.",
      tone: "text-muted",
    },
    down: {
      label: "FEED DOWN",
      detail:
        reason ??
        "The Kalshi feed could not be re-established. Every price below is " +
        "frozen at its last value.",
      tone: "text-negative",
    },
    silent: {
      label: "FEED SILENT",
      detail:
        "The connection is open and nothing has arrived, including the " +
        "heartbeat. Treat every price below as frozen.",
      tone: "text-negative",
    },
    disabled: {
      label: "NO LIVE FEED",
      detail:
        "This instance holds no Kalshi credentials, so nothing is streaming. " +
        "Every price below is the one recorded when the page loaded and is " +
        "ageing — read the age on each card, not the price alone.",
      tone: "text-muted",
    },
  };
  const { label, detail, tone } = copy[status];

  return (
    <div className="mb-4 flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-xl border px-4 py-3">
      <span
        className={`inline-flex items-center gap-2 font-mono text-xs font-bold tracking-widest ${tone}`}
      >
        <span
          aria-hidden
          className={`inline-block h-2 w-2 rounded-full bg-current ${
            status === "live" ? "feed-live" : ""
          }`}
        />
        {label}
      </span>
      <span className="min-w-0 text-xs leading-relaxed text-muted">{detail}</span>
    </div>
  );
}
