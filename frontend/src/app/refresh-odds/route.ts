/**
 * The refresh button's server side: session cookie in, bearer token out.
 *
 * **Why this file has to exist.** `POST /api/odds/refresh` on the Python
 * backend requires `APP_AUTH_TOKEN`, and the browser deliberately does not have
 * it -- `lib/session.ts` issues a cookie that *proves knowledge* of the token
 * without carrying it, precisely so a stolen cookie cannot place an order. The
 * ticket solves this by making the operator type the token per order. A refresh
 * button cannot: it is tapped on a handset, several times an evening, and a
 * 43-character paste each time is the kind of friction that gets a feature
 * disabled rather than used.
 *
 * So the token stays server-side and this handler holds it.
 *
 * **What that widens, stated plainly rather than glossed.** `lib/session.ts`
 * says compromising the cookie "costs you read access to the cockpit, not the
 * ability to trade". After this route, it also costs a bounded amount of the
 * odds plan: whoever holds the cookie can spend up to
 * `ondemand.DEFAULT_MANUAL_DAILY_CREDITS` (150) of a 600-credit day, against a
 * 13,000-credit month. That is real and it is not zero. It is accepted because
 * the ceiling is enforced server-side and cannot be raised from the client, and
 * because the alternative -- a button nobody can press from a phone -- is a
 * feature that does not exist. **It does not widen toward money:** the order
 * path still demands the token itself, and nothing here touches it.
 *
 * **Deliberately at `/refresh-odds` rather than under `/api/`**, for the reason
 * `/session` is: `next.config.ts` rewrites `/api/:path*` to the Python backend,
 * and a route handler competing with a rewrite for one prefix works until
 * someone reorders the config. `middleware.ts` names this path so an
 * unauthenticated call gets a 401 with JSON rather than a redirect to an HTML
 * login page, which a `fetch` would follow and read as success.
 *
 * **The one handler that does NOT use `lib/proxy.ts`'s relay, deliberately.**
 * The other six answer a transport failure with a 502 carrying a `detail`.
 * This one answers **200 with a typed `OddsRefreshResult`** -- `accepted:
 * false`, `estimated_credits: 0` -- because `lib/api.ts:refreshOdds` reads
 * that shape and a bare `detail` would reach the screen as "no odds
 * available", which is a different and much worse claim than "the request
 * did not arrive". Routing it through the shared relay would silently change
 * that contract, so it keeps its own fetch. It shares `backendToken` and
 * `BACKEND`, which is all it can share without losing the distinction.
 */

import { NextResponse, type NextRequest } from "next/server";

import { BACKEND, backendToken } from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    // The demo. It holds no credentials, reaches no network and runs no chain
    // runner, so there is nothing to refresh and nothing that could pay for it.
    return NextResponse.json(
      {
        accepted: false,
        detail:
          "This is the demo instance. Its slate is seeded, so there are no " +
          "live odds to buy.",
        estimated_credits: 0,
        retry_after_ms: 0,
      },
      { status: 200 },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { detail: "The request body was not JSON." },
      { status: 400 },
    );
  }

  // Forwarded rather than reconstructed: the backend validates `sport_key` and
  // `odds_event_id` against `odds_snapshots` and against a charset, and it is
  // the side that has to be right. Re-validating here would be a second
  // implementation of one rule, and the two would drift.
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/odds/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      cache: "no-store",
      body: JSON.stringify(body),
    });
  } catch (error) {
    return NextResponse.json(
      {
        accepted: false,
        detail: `The cockpit backend did not answer (${
          error instanceof Error ? error.message : "network error"
        }). No credits were spent.`,
        estimated_credits: 0,
        retry_after_ms: 0,
      },
      { status: 200 },
    );
  }

  const answer: unknown = await upstream.json().catch(() => null);
  // The status is passed through unchanged. A 422 from the backend's own
  // validation must not arrive at the browser as a 200 carrying a refusal --
  // those are different failures and the client renders them differently.
  return NextResponse.json(answer ?? { detail: "Unreadable response." }, {
    status: upstream.status,
  });
}
