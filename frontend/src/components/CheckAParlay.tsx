"use client";

import { useState } from "react";

import {
  checkParlay,
  displayZoneLabel,
  formatAge,
  formatKickoff,
  requestLegVerdicts,
} from "@/lib/api";
import type { CheckedParlayResult, LegVerdictsResult } from "@/lib/api";
import AskTheMarket, { ParlayCostLine } from "@/components/AskTheMarket";
import LegVerdicts from "@/components/LegVerdicts";
import { RestChip } from "@/components/ParlayCards";
import Term from "@/components/Term";
import { ParlayLegsContext, tenthsFromDisplay } from "@/lib/parlayCost";
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

/** Mirrors `LEG_VERDICT_MAX_LEGS` in `lib/api.ts`, which cuts to the same. */
const SCOUT_LEG_LIMIT = 8;

/**
 * "Ask the scouts" (#325): the leg scouts' read on every checked leg, on ONE
 * tap. **Tap only**: `requestLegVerdicts` is called from this button's click
 * handler and nowhere else -- not on load, not on paste, not from a watcher
 * (leg-verdict registration, Amendment 1). A check can be days out and the
 * seat refuses a started game, so nothing here is automatic. The scouts get
 * the same input as for any other leg; they are not told whose parlay it is.
 * An opinion shown beside the legs, never a gate, and it sorts nothing.
 */
function AskTheScouts({ value }: { value: CheckedParlayResult }) {
  const allLegs = value.legs.map((leg) => ({
    ticker: leg.market_ticker,
    side: leg.side,
  }));
  const legs = allLegs.slice(0, SCOUT_LEG_LIMIT);
  const unchecked = allLegs.length - legs.length;
  const [posted, setPosted] = useState<LegVerdictsResult | null>(null);
  const [requestedAtMs, setRequestedAtMs] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    setBusy(true);
    setRequestedAtMs(Date.now());
    setPosted(await requestLegVerdicts(legs, "check_button", null));
    setBusy(false);
  };

  return (
    <div>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <Button
          tone="quiet"
          className="-ml-2"
          onClick={ask}
          disabled={busy || legs.length === 0}
        >
          {busy ? "Asking the scouts…" : "Ask the scouts"}
        </Button>
        <span className="max-w-[65ch] text-xs text-muted">
          Asks the scouts about each leg, in about 20 seconds. It uses part of
          today&rsquo;s scout allowance, and a game that has started is
          refused.
        </span>
      </div>
      {unchecked > 0 && (
        <p className="mt-1 max-w-[65ch] text-xs text-accent-2">
          Only the first {SCOUT_LEG_LIMIT} of {allLegs.length} legs are asked
          about. The other {unchecked} {unchecked === 1 ? "is" : "are"} not.
        </p>
      )}
      {requestedAtMs !== null && (
        <LegVerdicts
          legs={legs}
          requestedAtMs={requestedAtMs}
          hideUnasked
          posted={posted}
        />
      )}
    </div>
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
            <p className="tabular text-xs text-muted">
              {leg.commence_ms === null
                ? "time unknown"
                : `${formatKickoff(leg.commence_ms)} ${displayZoneLabel(leg.commence_ms)}`}
            </p>
            <RestChip rest={leg.rest} />
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
            {/* #325: the singles screen's probable-bug reading, a fact on the
                row. Never sorts, never blocks. A leg with no desk price is
                "unknown", never read as clean. */}
            {leg.probable_bug_status === "bug" && (
              <p className="text-xs text-accent-2">
                The singles screen calls this price a probable bug:{" "}
                {leg.probable_bug_reason}.
              </p>
            )}
            {leg.probable_bug_status === "unknown" && (
              <p className="text-xs text-muted">No desk price.</p>
            )}
            {/* #303: a chance read off the books' other lines says so, and
                says how many books spoke -- often fewer than the main line. */}
            {leg.line_source === "alternate" && leg.alt_books_used !== null && (
              <p className="text-xs text-muted">
                From the books’ <Term k="alt_line">other lines</Term> at this
                exact number · {leg.alt_books_used.length}{" "}
                {leg.alt_books_used.length === 1 ? "book" : "books"}
              </p>
            )}
          </li>
        ))}
      </ol>

      {/* #303: a buy the inbox REFUSED is said in its own words. An accepted
          one needs no line here -- its legs already carry the server
          `buying_line` words, which it sets only on acceptance. */}
      {value.alt_buys
        .filter((buy) => !buy.accepted)
        .map((buy) => (
          <p key={buy.odds_event_id} className="text-xs text-muted">
            Could not buy this game’s other lines: {buy.detail}
          </p>
        ))}

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
            // The age always shows, depth or not: a price with no clock is
            // the defect ADR 0092 and #67 fixed on every other surface.
            [
              value.quoted.depth_display,
              `read ${formatAge(Date.now() - value.quoted.quoted_ms)}`,
            ]
              .filter(Boolean)
              .join(" · ")
          }
        />
      )}

      {value.hold_display !== null && (
        <p className="text-xs text-muted">
          <Term k="hold">Hold</Term>: {value.hold_display}
        </p>
      )}

      {/* #325: how cards from this source have done so far. A fixed line in
          a fixed place: no colour, no verdict, nothing sorted by it. */}
      {value.friend_source_line && (
        <p className="text-xs text-muted">{value.friend_source_line}</p>
      )}

      <AskTheScouts key={value.minted_market_ticker} value={value} />

      {/* #328. No per-leg Kalshi ask and no served fee on this payload, so
          the line stops at "wins about 1 in N": the fee and singles clauses
          need a coefficient and the legs' asks, and are left out rather than
          guessed. Absent when the book has no ask. */}
      {value.quoted !== null && (
        <ParlayLegsContext.Provider
          value={{ legCount: value.legs.length, legAsksTenths: null }}
        >
          <ParlayCostLine
            priceTenths={tenthsFromDisplay(value.quoted.ask_display)}
            coefficient={null}
          />
        </ParlayLegsContext.Provider>
      )}

      <p className="text-xs leading-snug text-muted">
        {value.notes.unquoted} {value.notes.fee}
      </p>

      {/* Only where asking can work (#166 round 2): the RFQ path is
          hard-coded to shard 1, and a closed market draws no quotes. The
          reading above stands either way; only the button is withheld. */}
      {value.rfq_available ? (
        <ParlayLegsContext.Provider
          value={{ legCount: value.legs.length, legAsksTenths: null }}
        >
          <AskTheMarket marketTicker={value.minted_market_ticker} />
        </ParlayLegsContext.Provider>
      ) : (
        <p className="text-sm text-muted">
          {value.rfq_unavailable_reason ??
            "Asking the makers is not available for this combination."}
        </p>
      )}
    </div>
  );
}
