/**
 * The leg scout's server side: session cookie in, bearer token out (#151,
 * ADR 0186).
 *
 * Same shape and same reasoning as `/scout-desk`: `POST /api/leg-verdicts`
 * spends metered Anthropic calls inside the shared `AgentBudget`
 * (`backend/agents/leg_verdict.py`), so it requires `APP_AUTH_TOKEN` and the
 * browser deliberately does not hold that token -- `lib/session.ts` issues a
 * cookie that proves knowledge of it without carrying it.
 *
 * **The `GET` half of this feature does not come through here.**
 * `fetchLegVerdicts` in `lib/api.ts` reads `GET /api/leg-verdicts` directly
 * through `next.config.ts`'s `/api/:path*` rewrite, the same as `/api/board`
 * or `/api/parlays` -- it spends nothing, so it needs no token to hold.
 * Only the `POST`, which can fire a seat, needs this handler.
 *
 * A 503 from the backend (the seat switched off) is relayed verbatim rather
 * than translated: `<LegVerdicts>` reads the body's own words, not this
 * status code.
 *
 * Deliberately at `/leg-verdicts` rather than under `/api/`, because that
 * prefix belongs to the `next.config.ts` rewrite; `middleware.ts` names this
 * path so an unauthenticated call gets JSON 401 rather than an HTML login
 * redirect a `fetch` would read as success.
 */

import { NextResponse, type NextRequest } from "next/server";

import {
  backendToken,
  demoRefusal,
  readJsonBody,
  relayToBackend,
} from "@/lib/proxy";

export async function POST(request: NextRequest) {
  const token = backendToken();
  if (!token) {
    // The demo. It holds no credentials and no Anthropic key; the seat does
    // not exist here, and saying so is the honest answer rather than a 500.
    return demoRefusal("leg verdicts cannot be requested");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body;

  return relayToBackend(
    "/api/leg-verdicts",
    { method: "POST", token, body },
    "The cockpit backend did not answer. Nothing was sent and nothing was spent.",
  );
}
