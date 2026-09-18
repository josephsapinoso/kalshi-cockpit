"use client";

import { useEffect, useState } from "react";

import { acceptComboQuote, askMarketToPrice, formatAge } from "@/lib/api";
import type { ComboRfqAcceptResult, ComboRfqResult } from "@/lib/api";
import Term from "@/components/Term";

/**
 * "Nobody is selling this" was wrong, and this is the control that fixes it.
 *
 * A combination's public order book is empty *by design between requests*:
 * its price lives in private maker quotes answering a Request for Quote. The
 * empty-book screen therefore told Joe a combination could not be bought on
 * markets that makers were pricing all day -- on 2026-09-17 the exact card he
 * was refused drew three quotes in 107 milliseconds.
 *
 * So this renders where that dead end used to: a size he types, a button that
 * asks, and the prices that come back.
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
 * **He types the size — issue #62, answered (A) on 2026-09-18.** It used to
 * be a hardcoded $5.00, trimmed server-side to 90% of the combinations shard.
 * Two limits on one quantity, swapping over at $5.5556 of balance with no
 * change in symptom because nothing printed the dollars. Now one number is
 * typed and the shard is a wall that refuses before the makers are asked.
 *
 * **What this must never become.** The gap between a quote and the card's
 * fair value is the consensus-vs-Kalshi gap under another name, and
 * `beta = -0.141` means ordering by it puts the least trustworthy rows first
 * (ADR 0071 s2.5). The two numbers sit side by side; nothing sorts cards by
 * their difference, and no copy here calls a quote cheap, good, or an edge.
 */

/** Where the last size he asked for is kept. Per-browser, per-device. */
const SIZE_KEY = "cockpit.rfq.size";

/**
 * The size used when he has never typed one on this device.
 *
 * **Not a recommendation.** It is the size the one measured RFQ happened to
 * be fired at, which is exactly why it stopped being hardcoded into the call.
 */
const DEFAULT_SIZE = "5.00";

function rememberedSize(): string {
  try {
    return window.localStorage.getItem(SIZE_KEY) ?? DEFAULT_SIZE;
  } catch {
    // Private mode, blocked site data, or a server render. A remembered
    // convenience that throws must not take the price control down with it.
    return DEFAULT_SIZE;
  }
}

export default function AskTheMarket({
  marketTicker,
}: {
  marketTicker: string;
}) {
  const [size, setSize] = useState(DEFAULT_SIZE);
  const [state, setState] = useState<
    | { kind: "idle" }
    | { kind: "asking" }
    | { kind: "answered"; value: ComboRfqResult }
    | { kind: "refused"; words: string }
  >({ kind: "idle" });

  // Read after mount, never during render: the server has no `localStorage`,
  // and reading one during render is how a hydration mismatch starts.
  useEffect(() => setSize(rememberedSize()), []);

  const ask = async () => {
    const typed = Number(size);
    if (!Number.isFinite(typed) || typed <= 0) {
      setState({
        kind: "refused",
        words:
          "Type how much you want to spend, in dollars, before asking for a " +
          "price. A quote is all-or-nothing at the size you ask for.",
      });
      return;
    }
    try {
      window.localStorage.setItem(SIZE_KEY, size);
    } catch {
      // Remembering is a convenience; failing to remember is not a failure.
    }
    setState({ kind: "asking" });
    try {
      const result = await askMarketToPrice(marketTicker, typed.toFixed(4));
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
          <div className="flex flex-wrap items-center gap-2">
            <label
              htmlFor={`rfq-size-${marketTicker}`}
              className="text-sm text-muted"
            >
              Ask for
            </label>
            <div className="flex items-center gap-1">
              <span className="text-sm">$</span>
              <input
                id={`rfq-size-${marketTicker}`}
                type="number"
                inputMode="decimal"
                min="0.01"
                step="0.01"
                value={size}
                onChange={(event) => setSize(event.target.value)}
                className="w-20 rounded border border-border bg-transparent px-2 py-1 text-sm tabular"
              />
            </div>
            <button
              onClick={ask}
              className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white"
            >
              Ask the market for a price
            </button>
          </div>
          <p className="mt-1 text-[11px] leading-snug text-muted">
            Sends a real <Term k="rfq">request for a quote</Term> to
            Kalshi&rsquo;s <Term k="maker">market makers</Term> and shows what
            they quote. This is how a combination is actually priced &mdash;
            the order book is empty on almost every combination, whether or not
            anyone would sell it. Asking costs nothing and commits you to
            nothing. A <Term k="maker_quote">quote</Term> is all-or-nothing at
            the size above, so that is the amount you would spend, not a
            maximum.
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
              A quote is live state: what is on screen is a price that WAS
              offered, not one still standing, so hiding the retry would
              imply otherwise.

              **The request is NOT withdrawn**, which this comment said until
              2026-09-18. `hold_open` defaults True and that is exactly what
              makes the Take-it button below reachable -- withdrawing drops
              the venue's copy of the quotes (measured 2026-09-17: a re-read
              after DELETE came back empty). Asking again reuses the same open
              RFQ and can return the same quote ids at new prices, which is
              why the store now updates them rather than keeping the first. */}
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

/**
 * How old these quotes are — issue #67.
 *
 * **It states an age and claims no expiry**, and the second half of that is
 * the correction. The first version of this block said a quote "has probably
 * expired" past three seconds, which was wrong twice over:
 *
 *  1. **Three seconds is the wrong quantity.** It is the maker's window to
 *     confirm *after an acceptance* (`HVM_CONFIRM_WINDOW_S` in
 *     `backend/kalshi/rfq.py`), not the shelf life of an unaccepted quote.
 *     What this repo has actually measured points the other way: the
 *     2026-09-17 quotes were still `open` forty seconds later, and their RFQ
 *     was still open more than an hour later.
 *  2. **It would have fired on every first paint.** `asked_ms` is stamped at
 *     route entry, before the book read, the balance read, the create and a
 *     mandatory four-second poll — so the payload cannot reach the browser
 *     younger than about 4.5 seconds. A staleness warning that is on 100% of
 *     the time is a warning that gets skipped, which is the failure this
 *     repo keeps naming.
 *
 * The true shelf life is unmeasured, so nothing here asserts one. Past a
 * generous minute it says the price is from a while ago and that asking again
 * is free — both true, neither a claim about whether the quote is dead.
 *
 * **It relabels and never blocks.** Taking a dead quote fails at the venue
 * with the venue's own reason, which is a refusal and not a loss; disabling
 * the button on age would be a new ceiling on a hand bet, and ADR 0112
 * removed all five of those on Joe's word.
 *
 * Ticks on its own: an age rendered once is a stamp that stops being true
 * while the reader looks at it.
 */
const QUOTE_GETTING_ON_MS = 60_000;
const AGE_TICK_MS = 1_000;

function QuotesAge({ askedMs }: { askedMs: number }) {
  const [ageMs, setAgeMs] = useState(() => Date.now() - askedMs);
  useEffect(() => {
    const tick = () => setAgeMs(Date.now() - askedMs);
    tick();
    const timer = setInterval(tick, AGE_TICK_MS);
    return () => clearInterval(timer);
  }, [askedMs]);

  // Clamped for display only, so a client clock behind the server's renders
  // as "just now" rather than as a negative number that reads like a bug.
  // The comparison below uses the raw value, so skew cannot make an old quote
  // look current.
  const shown = formatAge(Math.max(0, ageMs));
  if (ageMs <= QUOTE_GETTING_ON_MS) {
    return (
      <p className="text-[11px] leading-snug text-muted">Asked {shown} ago.</p>
    );
  }
  return (
    <p className="text-[11px] leading-snug text-accent-2">
      Asked <span className="font-semibold">{shown}</span> ago. How long a
      maker leaves a combination quote standing is not something this desk has
      measured, so this may or may not still be takeable &mdash; asking again
      is free and gives you a price with a fresh clock on it.
    </p>
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

      {/* **Both surfaces, never one — issue #66.** Neither dominates: on
          2026-09-17 the public book beat the RFQ on two of three held
          combinations and the RFQ was the only price on the third. A screen
          showing one of them sometimes reports no price when there is one,
          and sometimes shows the worse of the two. No copy ranks them; the
          two numbers sit beside each other and Joe reads them. */}
      {value.book_ask_display !== null && (
        <p className="text-xs text-muted tabular">
          Kalshi&rsquo;s public book: {value.book_ask_display}
        </p>
      )}

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

      <QuotesAge askedMs={value.asked_ms} />

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
 * **The button says what leaves the account — issue #68.** Fee included,
 * because Kalshi charges the combination taker fee on top of the contracts
 * and a per-contract price is not a stake: 8.19 contracts at 59.3c is $4.86
 * of contracts and $5.00 all in. This is #39's settled precedent (Joe's
 * answer A) applied to the second control that spends; the first,
 * `<ManualTicket>`'s Confirm, has printed dollars since then.
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

  // **The dollars go on the button, or the button admits it does not know.**
  // `all_in_display` is null when the maker's size could not be read, and a
  // quote with no size has an unknown cost. Printing the contracts alone
  // there would be a smaller, friendlier, wrong number.
  const label =
    quote.all_in_display === null
      ? "Take it"
      : `Take it — ${quote.all_in_display} all in`;

  return (
    <div className="mt-2">
      <button
        onClick={take}
        disabled={state.kind === "sending"}
        className="rounded bg-accent-fill px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
      >
        {state.kind === "sending" ? "Taking it…" : label}
      </button>
      <p className="mt-1 text-[11px] leading-snug text-muted">
        {quote.all_in_display === null ? (
          <>
            Buys this combination at the price above. This maker did not say
            what size they are quoting, so the desk cannot tell you the total
            before you tap.
          </>
        ) : (
          <>
            Leaves {quote.all_in_display} of the combinations{" "}
            <Term k="shard">shard</Term> &mdash; the contracts at the price
            above plus Kalshi&rsquo;s fee, which is charged on top. The fee is
            estimated high, so the real charge should be a little under.
          </>
        )}{" "}
        The maker has a few seconds to confirm and may decline, which costs you
        nothing.
      </p>
    </div>
  );
}
