"use client";

import { useState } from "react";

import { lookupParlay } from "@/lib/api";
import type { ParlayCardData, ParlayLookupResult } from "@/lib/api";
import Term from "@/components/Term";

/**
 * The one money-adjacent control on the parlay desk (ADR 0070).
 *
 * The tap mints a real combination market on Kalshi — no money moves, it is
 * exactly what the app does when anyone taps legs — and prices it off the
 * minted market's ORDER BOOK, never the list row. The button says what the
 * tap does before it is tapped; `bg-accent` is lawful here and nowhere else
 * on this screen (red = money-adjacent action).
 *
 * Every state renders in words: priced (quoted cost, contracts, payout,
 * hold, the server's verdict verbatim), an empty book (the captured reality
 * of a fresh combo — an honest refusal, not a price), no collection, and a
 * refusal (409 when the slate drifted). Nothing is retried silently.
 */
export default function PriceOnKalshi({ card }: { card: ParlayCardData }) {
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "working" }
    | { kind: "done"; value: ParlayLookupResult }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  if (card.not_built_reason !== null || card.legs.length < 2) return null;

  const stake =
    card.at_stakes.find((s) => s.is_default) ?? card.at_stakes[0] ?? null;

  const tap = async () => {
    setState({ kind: "working" });
    const result = await lookupParlay(
      card.key,
      stake?.stake_cents ?? 500,
      card.legs.map((l) => ({
        event_ticker: l.event_ticker,
        market_ticker: l.ticker,
      })),
    );
    if (result.ok) {
      setState({ kind: "done", value: result.value });
    } else {
      setState({ kind: "refused", words: result.refusal });
    }
  };

  return (
    <div className="mt-3 border-t border-border pt-3">
      {state.kind === "idle" && (
        <>
          <button
            onClick={tap}
            className="rounded bg-accent px-3 py-1.5 text-sm font-semibold text-white"
          >
            Price on Kalshi
          </button>
          <p className="mt-1 text-[11px] leading-snug text-muted">
            Creates this combination on the exchange (no money moves) and
            reads what it would actually cost from its order book.
          </p>
        </>
      )}
      {state.kind === "working" && (
        <p className="text-sm text-muted">Asking Kalshi…</p>
      )}
      {state.kind === "refused" && (
        <p className="text-sm text-accent-2">{state.words}</p>
      )}
      {state.kind === "done" && <Result value={state.value} />}
    </div>
  );
}

function Result({ value }: { value: ParlayLookupResult }) {
  if (value.status === "no_collection" || value.status === "book_empty") {
    return <p className="text-sm text-muted">{value.words}</p>;
  }
  return (
    <div className="space-y-1 text-sm">
      <p className="font-semibold">
        Kalshi&rsquo;s book: {value.quoted.ask_display}
      </p>
      {value.quoted.depth_display && (
        <p className="text-xs text-muted">{value.quoted.depth_display}</p>
      )}
      <p className="tabular">
        {value.quoted.at_stake.stake_display} →{" "}
        {value.quoted.at_stake.contracts_display} contracts →{" "}
        {value.quoted.at_stake.payout_display} if all hit
      </p>
      <p className="text-xs text-muted">
        Fair value {value.fair.fair_cost_display} ·{" "}
        <Term k="hold">hold</Term> {value.hold_display}
      </p>
      <p className="text-xs text-muted">{value.verdict}</p>
      <p className="text-[11px] leading-snug text-muted">
        {value.notes.enter_only} {value.notes.fee}
      </p>
    </div>
  );
}
