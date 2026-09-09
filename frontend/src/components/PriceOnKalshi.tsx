"use client";

import { useState } from "react";

import { lookupParlay } from "@/lib/api";
import type { ParlayCardData, ParlayLookupResult } from "@/lib/api";
import ManualTicket from "@/components/ManualTicket";
import Term from "@/components/Term";

/**
 * The one money-adjacent control on the parlay desk (ADR 0070).
 *
 * The tap mints a real combination market on Kalshi — no money moves, it is
 * exactly what the app does when anyone taps legs — and prices it off the
 * minted market's ORDER BOOK, never the list row. The button says what the
 * tap does before it is tapped; `bg-accent-fill` is lawful here and nowhere
 * else
 * on this screen (red = money-adjacent action).
 *
 * Every state renders in words: priced (quoted cost, contracts, payout,
 * hold, the server's verdict verbatim), an empty book (the captured reality
 * of a fresh combo — an honest refusal, not a price), no collection, and a
 * refusal (409 naming the leg that cannot be priced, and why). Nothing is
 * retried silently.
 *
 * **Every non-final state offers a way back.** An empty book is the
 * *expected* first answer on a fresh combo and its own words say "try again
 * shortly" — so a second tap has to be reachable without reloading the page.
 * Same for a refusal, and its words changed on 2026-08-30: a 409 used to say
 * the slate had moved and to refresh, which was advice that could not work —
 * the ladder re-ranks on every request, so reloading restarted the same race
 * Joe was already losing. It now names the leg that is no longer buyable, and
 * the retry re-sends the same legs because those are still the card he
 * tapped. A priced answer is final and
 * carries no retry: re-asking a question already answered is how a screen
 * invites tapping for a better number.
 *
 * **The second tap is safe, and that was measured before this button
 * shipped** (2026-08-24): posting the same legs again returns 200 with the
 * same `market_ticker`, so a retry re-reads the existing market's book
 * rather than minting another or being refused. See
 * `tests/fixtures/combo_lookup_repeat.json`. Had it come back 409, this
 * control would have been wrong to add.
 *
 * **A priced answer now carries a buy control (ADR 0073), and it is the
 * narrowest one in the product.** One contract, an acknowledgement typed
 * through before the confirm unlocks, a fee priced by a hedged coefficient
 * because the measured model undercharges on combos (ADR 0046), and no
 * payout figure. It renders only on `status === "priced"`: an empty book is
 * the expected first answer on a fresh combination and there is nothing to
 * buy there, which the existing words already say better than a disabled
 * button would.
 *
 * **This block said "expect it to refuse" and had the book backwards.
 * Corrected 2026-09-08 against the committed captures.**
 *
 * What is true, and is the only thing 40-of-40 establishes: no combination
 * book this repo has read has ever carried a resting **YES** bid. That is the
 * EXIT. It says nothing about getting in.
 *
 * Entry is the opposite of what this comment claimed. **33 of those same 40
 * rows carried a resting NO bid** (16 of 20 in E2, 6 of 9 in E3, 11 of 11 in
 * the 2026-08-18 run) — and a resting NO bid IS the ask you buy at, by the
 * derived-ask identity. Depths run to 683 units. The old text got 3-of-20 and
 * 3-of-9 from the `volume` column and reported it as the resting-bid rate;
 * those are the rows that had ever TRADED, a different and much rarer thing.
 * The "deepest 18 units at 13c" was attributed to 2026-08-09 and did not come
 * from it: it is the 2026-08-18 run's within-run maximum, and 2026-08-09's own
 * captures reach 413 and 683.
 *
 * So the depth check does not kill nearly every combo order, and a screen
 * telling Joe to expect refusal was steering him off a book that was quoted
 * five times in six. It renders only on `status === "priced"`; when the book
 * is genuinely empty the existing words already say so.
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
    // `lookupParlay` never throws -- but a throw here would strand the card
    // in "working" with its only button unmounted, so the guard is kept
    // rather than resting on the other module's promise.
    try {
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
    } catch (error) {
      setState({
        kind: "refused",
        words: `The lookup could not be completed (${
          error instanceof Error ? error.message : "unknown error"
        }). Nothing was priced.`,
      });
    }
  };

  const again = () => setState({ kind: "idle" });
  const retryable =
    state.kind === "refused" ||
    (state.kind === "done" && state.value.status !== "priced");

  return (
    <div className="mt-3 border-t border-border pt-3">
      {state.kind === "idle" && (
        <>
          <button
            onClick={tap}
            className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white"
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
      {retryable && (
        // Not `bg-accent-fill`: the filled slot is the money-adjacent
        // *first* tap.
        // A retry of a refusal is the same action, but the screen has
        // already said what it does, so it does not shout twice.
        <button
          onClick={again}
          className="mt-2 rounded border border-border px-3 py-1.5 text-sm font-semibold"
        >
          Ask Kalshi again
        </button>
      )}
    </div>
  );
}

function Result({ value }: { value: ParlayLookupResult }) {
  // Every non-priced status must be listed here. The fallthrough below reads
  // `value.quoted`, which only `priced` has, so a status missing from this
  // guard does not degrade -- it renders undefined into the price line.
  if (
    value.status === "no_collection" ||
    value.status === "book_empty" ||
    value.status === "legs_not_combinable"
  ) {
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
      {/*
        The stake line is bounded by the book (server-side). When depth is
        unreadable there is no contracts/payout to render at all -- only the
        note saying so, which is the honest answer rather than a number
        nobody can fill.
      */}
      {/*
        Bold, because this is the price and the fair-value estimate on the
        card above is not (ADR 0071 section 2.8). The estimate is the larger
        pair and it renders first; if the two carried equal weight the reader
        would keep the one they saw first, which is the one nobody offered.
      */}
      {value.quoted.at_stake.payout_display !== null && (
        <p className="tabular font-semibold">
          {value.quoted.at_stake.stake_display} →{" "}
          {value.quoted.at_stake.contracts_display} contracts (
          {value.quoted.at_stake.cost_display}) →{" "}
          {value.quoted.at_stake.payout_display} if all hit
        </p>
      )}
      {value.quoted.at_stake.depth_note && (
        <p className="text-xs text-accent-2">
          {value.quoted.at_stake.depth_note}
        </p>
      )}
      <p className="text-xs text-muted">
        Fair value {value.fair.fair_cost_display} ·{" "}
        <Term k="hold">hold</Term> {value.hold_display}
      </p>
      <p className="text-xs text-muted">{value.verdict}</p>
      <p className="text-[11px] leading-snug text-muted">
        {value.notes.unquoted} {value.notes.fee}
      </p>
      {/* The buy, on the minted market's own ticker — two lines under the
          ask, which is the whole purpose of this block. */}
      <ManualTicket
        ticker={value.minted_market_ticker}
        variant="inline"
        openLabel="Buy this combination"
        note="One combination, one contract. There is no resting YES bid on any combination book this tool has read, so the only exit is the outcome — and the fee here is a ceiling, not a quote."
      />
    </div>
  );
}
