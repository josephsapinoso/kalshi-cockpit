"use client";

import { useState } from "react";

import { checkParlay, formatAge } from "@/lib/api";
import type { CheckedParlayResult } from "@/lib/api";
import AskTheMarket from "@/components/AskTheMarket";
import Term from "@/components/Term";
import { Button, Stat } from "@/components/ui";

/**
 * "Check a parlay someone else built" — issue #165, #167.
 *
 * 82 of Joe's 142 settled parlays were never priced on this desk because
 * they are a friend's parlays he tails (copies) rather than ones he built
 * here. Joe's decision on #164 (2026-09-25): build a box where he pastes the
 * link or ticker and sees what the desk shows for its own cards — each leg's
 * desk chance, the chance every leg hits, the fair price and the book's ask
 * — then buys through the existing `<AskTheMarket>` panel. Price
 * transparency at the moment of a bet, not a verdict (ADR 0071).
 *
 * **A null chance is never 0.** A leg the desk has no consensus for (a prop,
 * another sport) renders "no desk reading for this leg", never `0%` or a
 * blank — `0` is a real chance and would be indistinguishable from one. Same
 * rule for the joint: `fair.no_joint_reason` says WHY there is no number
 * rather than a screen inventing one.
 *
 * **No sort, no rank, no verdict.** The legs render in the order the server
 * sent them; nothing here orders by the gap between fair value and the ask,
 * which is the consensus-vs-Kalshi gap under another name and `beta =
 * -0.141` means ranking by it puts the least trustworthy rows first (ADR
 * 0071 s2.5).
 */
export default function CheckAParlay() {
  const [text, setText] = useState("");
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "working" }
    | { kind: "done"; value: CheckedParlayResult }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  const check = async () => {
    const pasted = text.trim();
    if (!pasted) {
      setState({
        kind: "refused",
        words:
          "Paste a kalshi.com link or a KXMVE ticker before checking. " +
          "Nothing was checked.",
      });
      return;
    }
    setState({ kind: "working" });
    try {
      const result = await checkParlay(pasted);
      setState(
        result.ok
          ? { kind: "done", value: result.value }
          : { kind: "refused", words: result.refusal },
      );
    } catch (error) {
      setState({
        kind: "refused",
        words: `The check could not be completed (${
          error instanceof Error ? error.message : "unknown error"
        }). Nothing was checked.`,
      });
    }
  };

  return (
    <section
      aria-label="Check a parlay someone else built"
      className="mt-8 rounded-xl border border-border bg-card p-5"
    >
      <h2 className="text-sm font-semibold uppercase tracking-widest">
        Check a parlay someone else built
      </h2>
      <p className="mt-1 max-w-[60ch] text-xs leading-snug text-muted">
        Paste the kalshi.com link, or the KXMVE ticker, of a parlay someone
        else built. The desk reads it the same way it reads its own cards:
        each leg&rsquo;s chance, the chance every leg hits, and the fair
        price against Kalshi&rsquo;s own ask.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          id="check-a-parlay-input"
          type="text"
          inputMode="text"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="kalshi.com/... or KXMVE..."
          className="min-w-0 flex-1 rounded-lg border border-border bg-transparent px-2 py-1 text-sm"
        />
        <Button
          tone="primary"
          onClick={check}
          disabled={state.kind === "working"}
        >
          {state.kind === "working" ? "Checking…" : "Check"}
        </Button>
      </div>

      {state.kind === "refused" && (
        <p className="mt-2 text-sm text-accent-2">{state.words}</p>
      )}
      {state.kind === "done" && <CheckedResult value={state.value} />}
    </section>
  );
}

function CheckedResult({ value }: { value: CheckedParlayResult }) {
  return (
    <div className="mt-4 space-y-3 text-sm">
      <ol className="divide-y divide-border">
        {value.legs.map((leg) => (
          <li key={leg.market_ticker} className="py-2">
            <p className="font-semibold">{leg.label}</p>
            <p className="text-xs uppercase tracking-wide text-muted">
              {leg.side}
            </p>
            {/* **The unknown-leg branch, keyed on `chance === null`, never on
                a falsy chance.** `0` is a real probability and must render as
                a real probability -- so this checks for `null` explicitly
                rather than `!leg.chance`, which a mutation to `?? 0` or
                `|| 0` would make indistinguishable from a genuine 0% read. */}
            {leg.chance === null ? (
              <p className="text-xs text-accent-2">
                No desk reading for this leg
                {leg.unknown_reason ? ` — ${leg.unknown_reason}` : ""}.
              </p>
            ) : (
              <p className="tabular text-sm">{leg.chance_display}</p>
            )}
          </li>
        ))}
      </ol>

      {value.fair.no_joint_reason === null ? (
        <div className="grid grid-cols-2 gap-3 rounded-lg bg-accent-soft p-3">
          <Stat
            label={
              <>
                <Term k="joint_chance">Chance</Term> every{" "}
                <Term k="leg">leg</Term> hits
              </>
            }
            value={value.fair.conservative_percent_display ?? "—"}
          />
          <Stat
            label={<Term k="fair_value">Fair price</Term>}
            value={value.fair.fair_cost_display ?? "—"}
          />
        </div>
      ) : (
        <p className="text-sm text-muted">
          {value.fair.no_joint_reason === "unknown_leg"
            ? "The desk has no reading for every leg, so it cannot say a " +
              "chance for the whole parlay."
            : "Two legs are on the same game, and the desk does not price " +
              "same-game combinations."}
        </p>
      )}

      {value.status === "book_empty" || value.quoted === null ? (
        <p className="text-sm text-muted">{value.words}</p>
      ) : (
        <Stat
          label={<>Kalshi&rsquo;s book</>}
          value={value.quoted.ask_display}
          sub={
            value.quoted.depth_display ??
            `read ${formatAge(Date.now() - value.quoted.quoted_ms)}`
          }
        />
      )}

      {value.hold_display !== null && (
        <p className="text-xs text-muted">
          <Term k="hold">Hold</Term>: {value.hold_display}
        </p>
      )}

      <p className="text-xs leading-snug text-muted">
        {value.notes.unquoted} {value.notes.fee}
      </p>

      <AskTheMarket marketTicker={value.minted_market_ticker} />
    </div>
  );
}
