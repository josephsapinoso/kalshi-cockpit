"use client";

/**
 * Find a market to hand-bet that no screen surfaced.
 *
 * The slate and the Picks board show what the recorder priced, which is
 * moneylines, spreads, totals and the prop ladders `PROP_SERIES` names — and
 * only for fixtures it matched to a sportsbook. The ticket has always read
 * ANY ticker (`/api/manual/market/{ticker}` is deliberately not
 * recommendation-scoped); the only thing missing was a way to name one.
 *
 * **It serves no prices, and that is the design rather than an omission.**
 * `/api/manual/search` delegates to `estimates.search_markets`, whose SELECT
 * carries no quote column at all. So ADR 0065's masking survives this
 * screen: there is no way to browse for an ask, type the number it put in
 * your head, and call that your estimate. Every row here opens a ticket
 * whose first field is still P(YES), and `priceAlreadyVisible` is false
 * because nothing on this list is a price.
 *
 * Combination markets never appear: discovery excludes `KXMVE` from
 * `kalshi_markets` outright, and a combination has no ticker at all until a
 * parlay card mints one. That door is on the parlay desk, with its own
 * acknowledgement (ADR 0073).
 *
 * Closed by default, and behind a `<details>` on both screens that host it.
 * A search box is the one control on this product that can reach a market
 * nothing has looked at, which makes it the most useful affordance here and
 * the one least suited to sitting open beside tonight's slate.
 *
 * **A third host since 2026-09-02: the header (decision-map #18, Joe's
 * option A).** `Nav.tsx` mounts this behind a search button, and only while
 * that button is pressed -- so the "closed by default" above still holds,
 * one layer up. `open` is what that host passes: the reader has just asked
 * for the search, so the disclosure arrives open and the input focused
 * rather than making him tap the summary a second time. The two page hosts
 * pass nothing and are unchanged.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { DISPLAY_TIME_ZONE, searchManualMarkets, type EstimateMarket } from "@/lib/api";
import ManualTicket from "@/components/ManualTicket";
import Term from "@/components/Term";

/** Below this the route returns nothing, so asking is pure latency. */
const MIN_QUERY = 2;
/** Long enough that typing a team name is one request, not eight. */
const DEBOUNCE_MS = 250;

type State =
  | { name: "idle" }
  | { name: "searching" }
  | { name: "results"; markets: EstimateMarket[] }
  | { name: "failed"; words: string };

export default function MarketSearch({
  heading = "Bet a market that isn't listed",
  open = false,
}: {
  heading?: string;
  /** Arrive expanded with the input focused: the header host, where the
   *  reader has already tapped a button to ask for this. */
  open?: boolean;
}) {
  // Two hosts can be mounted at once (the header panel over a page that
  // also carries the search), so the label/input pair cannot share a fixed id.
  const inputId = useId();
  const [query, setQuery] = useState("");
  const [state, setState] = useState<State>({ name: "idle" });
  const [chosen, setChosen] = useState<EstimateMarket | null>(null);
  // Every response is stamped with the query that asked for it, so a slow
  // answer to an abandoned query cannot overwrite a fast answer to the
  // current one. Not theoretical: the shortest query is the slowest (a
  // two-character LIKE matches most of the table).
  const latest = useRef("");

  const run = useCallback(async (text: string) => {
    latest.current = text;
    if (text.trim().length < MIN_QUERY) {
      setState({ name: "idle" });
      return;
    }
    setState({ name: "searching" });
    try {
      const body = await searchManualMarkets(text.trim());
      if (latest.current !== text) return;
      setState({ name: "results", markets: body.markets });
    } catch (error) {
      if (latest.current !== text) return;
      setState({
        name: "failed",
        words:
          error instanceof Error
            ? error.message
            : "the search did not answer.",
      });
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void run(query), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, run]);

  return (
    <details
      open={open || undefined}
      className="mt-6 rounded-2xl border border-edge bg-card px-4 py-3 sm:px-6"
    >
      <summary className="cursor-pointer text-sm font-semibold">
        {heading}
        <span className="ml-2 font-normal text-muted">
          — any open market on the venue, including props the recorder never
          priced
        </span>
      </summary>

      <div className="mt-3">
        <label
          htmlFor={inputId}
          className="text-xs font-semibold uppercase tracking-widest text-muted"
        >
          Team, player, or ticker
        </label>
        <input
          id={inputId}
          autoFocus={open}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setChosen(null);
          }}
          autoComplete="off"
          placeholder="Ohtani"
          className="mt-1 w-full max-w-sm rounded-xl border bg-background px-3 py-2.5 text-sm"
        />
        <p className="mt-1 max-w-[65ch] text-xs text-muted">
          No prices in this list, on purpose — the ticket still asks for your
          own number first. Nothing here carries a{" "}
          <Term k="consensus">consensus</Term> fair value either: these are
          markets the recorder never priced, so the only two numbers in the
          ticket are yours and the venue&rsquo;s.
        </p>
      </div>

      {state.name === "searching" && (
        <p className="mt-3 text-sm text-muted">Looking&hellip;</p>
      )}

      {state.name === "failed" && (
        <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-muted">
          {state.words} Nothing was searched; the ticket is unaffected.
        </p>
      )}

      {state.name === "results" && state.markets.length === 0 && (
        <p className="mt-3 max-w-[65ch] text-sm text-muted">
          Nothing open matches that. The list is what discovery has walked —
          a market that closed, or one in a series this instance does not
          walk, will not be here.
        </p>
      )}

      {state.name === "results" && state.markets.length > 0 && (
        <ul className="mt-3 divide-y divide-border">
          {state.markets.map((market) => (
            <li key={market.ticker} className="py-2">
              <button
                onClick={() =>
                  setChosen(
                    chosen?.ticker === market.ticker ? null : market,
                  )
                }
                className="flex min-h-11 w-full flex-wrap items-baseline gap-x-2 gap-y-0.5 text-left"
              >
                <span className="min-w-0 text-sm font-semibold tracking-tight">
                  {market.title ?? market.ticker}
                </span>
                {market.player_name && (
                  <span className="text-xs text-muted">
                    {market.player_name}
                  </span>
                )}
                <span className="ml-auto shrink-0 font-mono text-[11px] text-muted">
                  {closes(market.close_ms)}
                </span>
              </button>
              <p className="font-mono text-[11px] text-muted">
                {market.ticker}
              </p>
              {chosen?.ticker === market.ticker && (
                <ManualTicket
                  ticker={market.ticker}
                  variant="inline"
                  openLabel="Open the ticket"
                  note="A market no screen here priced. Nothing on this product says what it is worth — your own number is the only estimate there is."
                />
              )}
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** When it closes, in the display zone the rest of the product uses. */
function closes(ms: number | null): string {
  if (ms === null) return "—";
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
