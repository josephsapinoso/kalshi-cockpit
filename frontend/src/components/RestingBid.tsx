"use client";

import { useState } from "react";

import { placeComboBid } from "@/lib/api";
import type { ParlayCardData } from "@/lib/api";

/**
 * Buy this parlay from the desk — by making the offer, not taking one.
 *
 * ADR 0084. Every other buy control in this app takes a price that is already
 * resting. A combination has nothing resting to take: **40 of 40 combination
 * books this tool has read carried no YES bid**, which is exactly why "Price
 * on Kalshi" keeps coming back with an empty book. So this control does the
 * only thing that can work — it rests Joe's own bid at his own price and waits
 * for someone to take it.
 *
 * **The words never promise a fill, and that is the whole design.** A resting
 * bid is an offer standing, not a bet placed. A screen that said "bought" or
 * showed a payout would be describing a position he does not have, and on an
 * enter-only market with no counterparty in evidence that is the most likely
 * outcome, not the edge case.
 *
 * Three things are Joe's to choose and one is not:
 *
 * - **The price** is his. The card's fair value is shown beside the field as a
 *   reference and the control never moves his number towards it in either
 *   direction (ADR 0071 §2.5: the consensus-vs-Kalshi gap may be shown and
 *   never ranked by).
 * - **The stake** is his, capped server-side at the same $3 the hand-bet path
 *   uses — one ceiling, not two.
 * - **The acknowledgement** is not optional. Enter-only means the only exit is
 *   the outcome.
 * - **The cancel deadline** is not his either: the desk withdraws the bid when
 *   the first leg kicks off, because a fill after that is a bet on a game
 *   already under way at a price computed before it started.
 *
 * Rendered on every built card regardless of what the book said, unlike
 * `ManualTicket`, which needs a price. That is the point: the empty book is
 * the normal case here and it is precisely when this control is the only way
 * in.
 */
export default function RestingBid({ card }: { card: ParlayCardData }) {
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [stake, setStake] = useState("");
  const [ack, setAck] = useState(false);
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "working" }
    | { kind: "done"; words: string }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  if (card.not_built_reason !== null || card.legs.length < 2) return null;

  // The fair value in tenths, as a reference for the price field. Parsed from
  // the card's own conservative joint rather than recomputed: two numbers on
  // one screen that disagree by a rounding step is a bug report waiting to be
  // filed.
  const fairTenths = card.joint
    ? Math.round(card.joint.conservative * 1000)
    : null;

  const priceTenths = Math.round(parseFloat(price) * 10);
  const stakeCents = Math.round(parseFloat(stake) * 100);
  const priceOk = Number.isFinite(priceTenths) && priceTenths > 0 && priceTenths < 1000;
  const stakeOk = Number.isFinite(stakeCents) && stakeCents > 0;
  const contracts = priceOk && stakeOk ? Math.floor(stakeCents * 10 / priceTenths) : 0;
  const ready = priceOk && stakeOk && ack && contracts > 0;

  const submit = async () => {
    if (!ready) return;
    setState({ kind: "working" });
    try {
      const result = await placeComboBid({
        cardKey: card.key,
        legs: card.legs.map((l) => ({
          event_ticker: l.event_ticker,
          market_ticker: l.ticker,
        })),
        priceTenths,
        stakeCents,
      });
      setState(
        result.ok
          ? { kind: "done", words: result.value.words }
          : { kind: "refused", words: result.refusal },
      );
    } catch (error) {
      setState({
        kind: "refused",
        words:
          `The bid could not be sent (${
            error instanceof Error ? error.message : "unknown error"
          }). Check the resting bids panel before trying again.`,
      });
    }
  };

  if (!open) {
    return (
      <div className="mt-3 border-t border-border pt-3">
        <button
          onClick={() => setOpen(true)}
          className="rounded border border-border px-3 py-1.5 text-sm font-semibold"
        >
          Bid on this parlay
        </button>
        <p className="mt-1 text-[11px] leading-snug text-muted">
          Nobody is offering this combination, so you cannot buy it outright.
          This puts <em>your</em> price on the exchange and waits for someone
          to take it.
        </p>
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 border-t border-border pt-3">
      <p className="text-sm font-semibold">Rest a bid</p>

      <div className="flex flex-wrap items-end gap-3">
        <label className="text-xs text-muted">
          Your price (cents)
          <input
            inputMode="decimal"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder={fairTenths ? (fairTenths / 10).toFixed(1) : "22"}
            /* 44px min height: this is a money field on a phone. */
            className="mt-1 block w-28 min-h-[44px] rounded border border-border bg-transparent px-2 tabular"
          />
        </label>
        <label className="text-xs text-muted">
          Stake (dollars)
          <input
            inputMode="decimal"
            value={stake}
            onChange={(e) => setStake(e.target.value)}
            placeholder="2.00"
            className="mt-1 block w-28 min-h-[44px] rounded border border-border bg-transparent px-2 tabular"
          />
        </label>
      </div>

      {card.joint && (
        <p className="text-xs text-muted">
          The consensus says it is worth{" "}
          <span className="tabular">{card.joint.fair_cost_display}</span>. Bid
          below that and you are asking for a better price than the books
          imply; bid above it and you are paying up. Neither is a
          recommendation — the desk does not rank by that gap.
        </p>
      )}

      {ready && (
        <p className="text-sm tabular">
          {contracts} contracts at {(priceTenths / 10).toFixed(1)}c ={" "}
          {"$"}
          {((contracts * priceTenths) / 1000).toFixed(2)} committed if the whole
          bid is taken.
        </p>
      )}
      {priceOk && stakeOk && contracts === 0 && (
        <p className="text-sm text-accent-2">
          That stake buys no whole contracts at that price.
        </p>
      )}

      <label className="flex items-start gap-2 text-xs leading-snug text-muted">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
          className="mt-0.5 min-h-[20px] min-w-[20px]"
        />
        <span>
          I understand a combination is <strong>enter-only</strong>:
          no combination book this tool has read had anyone bidding on the
          other side, so the only way out is waiting for the outcome. The fee
          model for combinations is unverified.
        </span>
      </label>

      {state.kind === "idle" && (
        <div className="flex gap-2">
          <button
            onClick={submit}
            disabled={!ready}
            className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            Place resting bid
          </button>
          <button
            onClick={() => setOpen(false)}
            className="rounded border border-border px-3 py-1.5 text-sm"
          >
            Cancel
          </button>
        </div>
      )}
      {state.kind === "working" && (
        <p className="text-sm text-muted">Placing the bid…</p>
      )}
      {(state.kind === "done" || state.kind === "refused") && (
        <p
          className={`text-sm ${
            state.kind === "refused" ? "text-accent-2" : ""
          }`}
        >
          {state.words}
        </p>
      )}

      <p className="text-[11px] leading-snug text-muted">
        The desk cancels this automatically when the first game starts. It is
        an offer standing, not a bet placed — nobody has to take it.
      </p>
    </div>
  );
}
