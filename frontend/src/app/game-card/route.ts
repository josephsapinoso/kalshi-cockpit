/**
 * The same-game card builder: session cookie in, bearer token out (#215).
 *
 * Same shape as `/game-mint`, copied from it. The backend's
 * `POST /api/game/{event}/card` is auth-gated because it spends: one metered
 * model call against the shared daily ceilings (ADR 0190). It mints nothing
 * and moves no money. The browser deliberately never holds the token; this
 * handler does.
 *
 * **The game rides in the BODY, not the path**, for the same reason as
 * `/game-mint`: `middleware.ts` matches `JSON_ROUTE_HANDLERS` by exact path,
 * so a dynamic segment would miss the set and an unauthenticated call would
 * get an HTML login redirect a `fetch` reads as success. The event ticker is
 * shape-checked before it is spliced into the backend path; the backend
 * re-validates it.
 *
 * The mechanics come from `lib/proxy.ts`; this file keeps its own words.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

const GAME_EVENT = /^KX[A-Z0-9]*GAME-[A-Z0-9]+$/;

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    return demoRefusal("a game card cannot be built");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as { event_ticker?: unknown } | null;

  const event =
    typeof body?.event_ticker === "string" ? body.event_ticker.trim() : "";
  if (!GAME_EVENT.test(event)) {
    return NextResponse.json(
      { detail: "That is not a game's event ticker. No card was built." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/game/${event}/card`,
    { method: "POST", token, body: {} },
    "The cockpit backend did not answer. The card may still be building; " +
      "reload the game before tapping again.",
  );
}
