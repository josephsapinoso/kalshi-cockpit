/**
 * The same-game builder's mint: session cookie in, bearer token out (#202).
 *
 * Same shape as `/parlay-lookup`, copied from it. The backend's
 * `POST /api/game/{event}/mint` is auth-gated because it creates a real
 * combination market on the exchange -- no money moves, and it is what the
 * Kalshi app does when anyone ticks legs -- so the browser deliberately never
 * holds the token and this handler does. Asking makers a price
 * (`/parlay-rfq`) and taking one (`/parlay-rfq-accept`) are separate doors;
 * this one only creates the thing they are asked about.
 *
 * **The game rides in the BODY, not the path.** `middleware.ts` matches
 * `JSON_ROUTE_HANDLERS` by exact path, so a dynamic segment here would miss
 * the set and an unauthenticated call would get an HTML login redirect a
 * `fetch` reads as success (the same reason `/parlay-bid-cancel` carries its
 * id in the body). The event ticker is shape-checked before it is spliced
 * into the backend path; the backend re-validates it and every leg.
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
    return demoRefusal("a combination cannot be created");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body as
    | { event_ticker?: unknown; legs?: unknown }
    | null;

  const event =
    typeof body?.event_ticker === "string" ? body.event_ticker.trim() : "";
  if (!GAME_EVENT.test(event)) {
    return NextResponse.json(
      { detail: "That is not a game's event ticker. Nothing was created." },
      { status: 400 },
    );
  }

  return relayToBackend(
    `/api/game/${event}/mint`,
    { method: "POST", token, body: { legs: body?.legs ?? [] } },
    "The cockpit backend did not answer. Nothing was created -- but if the " +
      "request got as far as Kalshi the combination may exist; check before " +
      "ticking again.",
  );
}
