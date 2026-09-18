"use client";

import { useState } from "react";

import { acceptComboQuote, askMarketToPrice } from "@/lib/api";
import type { ComboRfqAcceptResult, ComboRfqResult } from "@/lib/api";

/**
 * "Nobody is selling this" was wrong, and this is the control that fixes it.
 *
 * A combination's public order book is empty *by design between requests*:
 * its price lives in private maker quotes answering a Request for Quote. The
 * empty-book screen therefore told Joe a combination could not be bought on
 * markets that makers were pricing all day -- on 2026-09-17 the exact card he
 * was refused drew three quotes in 107 milliseconds.
 *
 * So this renders where that dead end used to: a button that asks, and the
 * prices that come back.
 *
 * **Asking is free and commits nothing.** Only accepting a quote binds the
 * requester. The button says so before it is tapped, because the previous
 * version of this screen sent Joe to the Kalshi app to do by hand what it
 * could have done itself.
 *
 * **Taking a quote is built, and armed.** `<TakeIt>` below is the second tap
 * of B = (ii) — Joe sees the maker's price, then confirms it, with no ceiling
 * typed in advance because an RFQ tells you the price *after* you ask. Since
 * 2026-09-17 `RFQ_ACCEPTS_ARE_DRY_RUNS` is False and that button spends real
 * money. The unarmed branch stays and renders a refusal rather than a button,
 * because a control labelled "Take it" that silently does nothing is this
 * repo's named failure — the armed state travels with the price, so the
 * screen says which it is up front rather than this comment guessing.
 *
 * **What this must never become.** The gap between a quote and the card's
 * fair value is the consensus-vs-Kalshi gap under another name, and
 * `beta = -0.141` means ordering by it puts the least trustworthy rows first
 * (ADR 0071 s2.5). The two numbers sit side by side; nothing sorts cards by
 * their difference, and no copy here calls a quote cheap, good, or an edge.
 */
export default function AskTheMarket({
  marketTicker,
  targetCostDollars,
}: {
  marketTicker: string;
  /** Kalshi's own fixed-point dollar string, e.g. `"5.0000"`. */
  targetCostDollars: string;
}) {
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "asking" }
    | { kind: "answered"; value: ComboRfqResult }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  const ask = async () => {
    setState({ kind: "asking" });
    try {
      const result = await askMarketToPrice(marketTicker, targetCostDollars);
      setState(
        result.ok
          ? { kind: "answered", value: result.value }
          : { kind: "refused", words: result.refusal },
      );
    } catch (error) {
      setState({
        kind: "refused",
        words: `The price request could not be completed (${
          error instanceof Error ? error.message : "unknown error"
        }). Nothing was bought.`,
      });
    }
  };

  return (
    <div className="mt-2">
      {state.kind === "idle" && (
        <>
          <button
            onClick={ask}
            className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white"
          >
            Ask the market for a price
          </button>
          <p className="mt-1 text-[11px] leading-snug text-muted">
            Sends a real request to Kalshi&rsquo;s market makers and shows what
            they quote. This is how a combination is actually priced &mdash; the
            order book above is empty on almost every combination, whether or
            not anyone would sell it. Asking costs nothing and commits you to
            nothing.
          </p>
        </>
      )}

      {state.kind === "asking" && (
        <p className="text-sm text-muted">
          Asking the market&hellip; makers usually answer in well under a
          second.
        </p>
      )}

      {state.kind === "refused" && (
        <>
          <p className="text-sm text-accent-2">{state.words}</p>
          <RetryButton onClick={() => setState({ kind: "idle" })} />
        </>
      )}

      {state.kind === "answered" && (
        <>
          <Quotes value={state.value} />
          {/* Re-asking is always offered, including after a good answer.
              A quote is live state -- the request is withdrawn as soon as it
              is read, so what is on screen is a price that WAS offered, not
              one still standing. Hiding the retry would imply otherwise. */}
          <RetryButton onClick={() => setState({ kind: "idle" })} />
        </>
      )}
    </div>
  );
}

function RetryButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="mt-2 rounded border border-border px-3 py-1.5 text-sm font-semibold"
    >
      Ask again
    </button>
  );
}

function Quotes({ value }: { value: ComboRfqResult }) {
  if (value.status === "no_quotes" || value.quotes.length === 0) {
    return <p className="text-sm text-muted">{value.words}</p>;
  }

  const best = value.quotes[0];

  return (
    <div className="space-y-1 text-sm">
      {/* Every price string on this screen is rendered by the backend, through
          the same renderer the order book path uses. A second formatter in
          TypeScript is how two surfaces start disagreeing about what 59.3c
          means on a market that ticks in deci-cents. */}
      <p className="font-semibold tabular">
        Best quote: {best.ask_display}
        {best.contracts !== null && (
          <span className="font-normal text-muted">
            {" "}
            &middot; {best.contracts.toFixed(2)} contracts
          </span>
        )}
      </p>

      {/* Fair value beside the quote, never subtracted into a verdict. */}
      {value.fair_display !== null && (
        <p className="text-xs text-muted tabular">
          Fair value {value.fair_display}
        </p>
      )}

      {/* Every maker, because the spread between them is worth real money and
          a screen showing only the best one hides that there was a choice. */}
      {value.quotes.length > 1 && (
        <ul className="text-xs text-muted tabular">
          {value.quotes.slice(1).map((q) => (
            <li key={q.quote_id}>
              also {q.ask_display}
              {q.contracts !== null && ` · ${q.contracts.toFixed(2)} contracts`}
            </li>
          ))}
        </ul>
      )}

      <p className="text-[11px] leading-snug text-muted">{value.words}</p>

      {/* The second tap. It is a separate component because it SPENDS and the
          block above does not, and because its result has states the price
          block has never had -- a maker who does not confirm, and an outcome
          nobody can see. */}
      <TakeIt
        rfqId={value.rfq_id}
        quote={best}
        armed={value.accepts_are_armed}
      />
    </div>
  );
}

/**
 * The second tap of B = (ii): Joe has seen the quote, now he takes it.
 *
 * **No typed ceiling, by his decision.** An RFQ hands you the maker's price
 * *after* you ask, so a number typed in advance would be a guess at the one
 * you are about to be told. What guards the spend is that the price on screen
 * is the price the server accepts — it reads its own record of this quote and
 * ignores anything the browser might send.
 *
 * **Three outcomes, and only one of them is a fill.** A maker has about three
 * seconds to stand behind a quote on a combination; they may decline, and
 * that is normal rather than a fault. And an acceptance whose answer is lost
 * is an *unknown* — the RFQ path has no idempotency key, so nothing here ever
 * retries, and the words say to go and look instead.
 */
function TakeIt({
  rfqId,
  quote,
  armed,
}: {
  rfqId: string;
  quote: ComboRfqResult["quotes"][number];
  /** False while the accept path is unarmed — the button says so up front. */
  armed: boolean;
}) {
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "sending" }
    | { kind: "done"; value: ComboRfqAcceptResult }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  const take = async () => {
    setState({ kind: "sending" });
    try {
      const result = await acceptComboQuote(rfqId, quote.quote_id);
      setState(
        result.ok
          ? { kind: "done", value: result.value }
          : { kind: "refused", words: result.refusal },
      );
    } catch (error) {
      setState({
        kind: "refused",
        words:
          `The acceptance did not complete (${
            error instanceof Error ? error.message : "unknown error"
          }). It may still have reached Kalshi — check the app before ` +
          "tapping anything else.",
      });
    }
  };

  if (state.kind === "done") {
    return (
      <p
        className={`mt-2 text-xs leading-snug ${
          state.value.filled ? "font-semibold" : "text-accent-2"
        }`}
      >
        {state.value.words}
      </p>
    );
  }

  if (state.kind === "refused") {
    // No retry button, deliberately. Every other refusal on this screen offers
    // one; this is the only path where a second tap could be a second real
    // trade, and a button is an invitation.
    return (
      <p className="mt-2 text-xs leading-snug text-accent-2">{state.words}</p>
    );
  }

  // **Unarmed: say so instead of offering the button.** A control labelled
  // "Take it" that silently does nothing is the failure this repo has named
  // and repeated three times — a screen promising an action the server does
  // not perform. While `RFQ_ACCEPTS_ARE_DRY_RUNS` is True there is nothing to
  // offer, so nothing is offered.
  if (!armed) {
    return (
      <p className="mt-2 text-[11px] leading-snug text-accent-2">
        Taking a quote is built but not switched on, so this desk cannot buy
        it for you yet. The price above is real: buy the combination in the
        Kalshi app and you now know what it should cost before you look.
      </p>
    );
  }

  return (
    <div className="mt-2">
      <button
        onClick={take}
        disabled={state.kind === "sending"}
        className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
      >
        {state.kind === "sending"
          ? "Taking it…"
          : `Take it at ${quote.ask_display}`}
      </button>
      <p className="mt-1 text-[11px] leading-snug text-muted">
        Buys this combination at the price above. The maker has a few seconds
        to confirm and may decline, which costs you nothing.
      </p>
    </div>
  );
}
