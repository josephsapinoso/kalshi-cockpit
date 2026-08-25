/**
 * The heartbeat's server side: session cookie in, bearer token out.
 *
 * Same shape and same reasoning as `/pass` and `/scout-desk`. The backend's
 * `POST /api/desk/attention` is a mutation and every mutating route is gated
 * (CLAUDE.md Security), while the browser deliberately does not hold
 * `APP_AUTH_TOKEN` -- `lib/session.ts` issues a cookie that proves knowledge of
 * it without carrying it -- so the token stays here.
 *
 * Deliberately at `/desk-attention` rather than under `/api/`, because that
 * prefix belongs to the `next.config.ts` rewrite; `middleware.ts` names this
 * path in `JSON_ROUTE_HANDLERS` so an unauthenticated call gets a JSON 401
 * rather than an HTML login redirect a `fetch` would read as success.
 *
 * ## What this widens, and it is the one thing on this route worth arguing over
 *
 * A stamp here makes the odds feed spend money. That is the whole point --
 * ADR 0071 section 2.6, the feed follows attention rather than a clock -- and it
 * is also the reason this handler is not simply "a cheap write". A caller that
 * hammers it keeps the desk permanently attended, which is ~1,152 credits/day at
 * two sports and ~2,304 at four, against a 20,000/month tier.
 *
 * Three things bound that, and only the third is here:
 *
 *  1. `Nav.tsx` stamps at most once a minute and only while
 *     `document.visibilityState === "visible"`. Politeness, not a guarantee.
 *  2. The backend's attention TTL means a stamp buys at most five minutes of
 *     attended cadence. Bounds the tail, not the rate.
 *  3. **The attention daily slice** (`DEFAULT_ATTENTION_DAILY_CREDITS`, 300 of
 *     700) is the hard one. Past it the desk stops re-buying at the attended
 *     cadence and keeps its hourly floor, so the worst a flood of stamps can do
 *     is spend that slice early.
 *
 * So this route is not rate-limited and does not need to be: the ceiling lives
 * where the money is spent, not where the claim is made. A rate limit here
 * would be a second, weaker copy of a control that already exists -- and the
 * session gate above already means the caller is Joe.
 *
 * The body is empty on purpose. The stamp's time is the *server's* `now_ms`,
 * never a client-supplied one: a timestamp from the browser is a number a
 * caller chooses, and the only thing it could usefully be chosen to be is the
 * future.
 */

import { backendToken, demoRefusal, relayToBackend } from "@/lib/proxy";

export async function POST() {
  const token = backendToken();
  if (!token) {
    // The demo. It holds no credentials and buys no odds, so there is nothing
    // for attention to drive. Saying so is the honest answer rather than a 500.
    return demoRefusal("the desk has no odds feed to wake");
  }

  return relayToBackend(
    "/api/desk/attention",
    { method: "POST", token, body: {} },
    // Deliberately unlike the other handlers' refusals. Nothing the reader
    // did has failed -- a missed heartbeat costs one delayed sweep and the
    // next poll retries in a minute -- so this must not read like a lost
    // action. `Nav.tsx` swallows it and shows nothing.
    "The cockpit backend did not answer the heartbeat. The odds feed may be a few minutes behind.",
  );
}
