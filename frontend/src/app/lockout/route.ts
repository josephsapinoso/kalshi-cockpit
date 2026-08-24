/**
 * The self-lockout's server side: session cookie in, bearer token out.
 *
 * Same pattern as `/log-estimate` and for the same reason -- the backend
 * route requires `APP_AUTH_TOKEN`, the browser deliberately does not carry
 * it, and "not tonight" has to be one tap, because a lockout that takes
 * typing a 43-character token is a lockout that loses to the impulse it
 * exists to interrupt.
 *
 * Upstream is `/api/desk/lockout` since 2026-08-21: the lockout outlived
 * the study that named its old route (`/api/estimates/lockout`, still
 * served, deprecated). Same table, same clock, one line changed here.
 *
 * What a stolen cookie buys here: the ability to engage Joe's own "not
 * tonight" note until the next day roll. Annoying, self-limiting, and
 * biased in the safe direction -- the attack makes betting harder, not
 * easier. There is no disengage endpoint on the backend for it to call.
 */

import { type NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { backendToken, relayToBackend } from "@/lib/proxy";

export async function POST(_request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return NextResponse.json(
      {
        detail:
          "This is the demo instance. The lockout is the operator's own " +
          "note to themselves, and the demo has no operator.",
      },
      { status: 403 },
    );
  }

  return relayToBackend(
    "/api/desk/lockout",
    {
      method: "POST",
      token,
      unreadable: "The backend answered with something that was not JSON.",
    },
    "The backend could not be reached. You are NOT locked out.",
  );
}
