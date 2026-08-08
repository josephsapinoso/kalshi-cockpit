"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import OpportunityCard from "@/components/OpportunityCard";
import type { Recommendation } from "@/lib/api";

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

type Status = "connecting" | "live" | "idle" | "down" | "silent";

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
  const [status, setStatus] = useState<Status>(enabled ? "connecting" : "idle");
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
        if (!quote) return { row, move: undefined };
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
            quote_age_now_ms: Math.max(0, Date.now() - quote.observed_ms),
            price_is_current: true,
            freshness_confirmed: false,
          } as Recommendation,
          move: moves.get(row.id),
        };
      }),
    [rows, quotes, moves, streaming],
  );

  return (
    <>
      {enabled && <FeedStatus status={status} reason={reason} />}
      <div className="grid gap-4 sm:grid-cols-2">
        {merged.map(({ row, move }) => (
          <div key={row.id} className={move ? `tick-${move}` : undefined}>
            <OpportunityCard
              rec={row}
              live={streaming && quotes.has(row.id)}
              direction={move}
              quoteLimitMs={quoteLimitMs}
              oddsLimitMs={oddsLimitMs}
            />
          </div>
        ))}
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
