/**
 * The scout desk's server side: session cookie in, bearer token out.
 *
 * Same shape and same reasoning as `/refresh-odds`: the backend's
 * `POST /api/scout/{ticker}` requires `APP_AUTH_TOKEN` because it spends
 * money (three metered Anthropic calls per convening, ADR 0060), and the
 * browser deliberately does not hold that token -- `lib/session.ts` issues a
 * cookie that proves knowledge of it without carrying it. A button tapped on
 * a phone cannot demand a 43-character paste per tap, so the token stays
 * server-side and this handler holds it.
 *
 * **What that widens, stated plainly.** Whoever holds the session cookie can
 * now also spend from the Anthropic day: up to `AGENT_MAX_CALLS_PER_DAY` (24)
 * calls, shared with the Skeptic, at roughly a dime's worth of tokens per
 * three-call briefing. The ceiling is enforced server-side by `AgentBudget`
 * against the `agent_calls` table and cannot be raised from the client.
 * **It does not widen toward money on the exchange:** the order path still
 * demands the token itself, and nothing here touches it.
 *
 * Deliberately at `/scout-desk` rather than under `/api/`, because that
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
    // The demo. It holds no credentials and no Anthropic key; the desk does
    // not exist here, and saying so is the honest answer rather than a 500.
    return demoRefusal("the scout desk cannot be sent");
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return parsed.response;
  const body = parsed.body;

  const ticker =
    body && typeof body === "object" && "ticker" in body
      ? String((body as { ticker: unknown }).ticker)
      : "";
  if (!ticker) {
    return NextResponse.json(
      { detail: "No ticker named. The desk needs a game to be sent on." },
      { status: 400 },
    );
  }

  // Forwarded rather than reconstructed: the backend owns fixture resolution,
  // the running-convening check and the budget refusal, and it is the side
  // that has to be right.
  return relayToBackend(
    `/api/scout/${encodeURIComponent(ticker)}`,
    { method: "POST", token },
    "The cockpit backend did not answer. Nothing was sent and nothing was spent.",
  );
}
