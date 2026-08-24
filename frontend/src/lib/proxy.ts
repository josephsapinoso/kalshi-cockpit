/**
 * The shared mechanics of a token-holding route handler.
 *
 * There are seven of these (`/refresh-odds`, `/scout-desk`, `/log-estimate`,
 * `/revise-estimate`, `/lockout`, `/pass`, `/parlay-lookup`) and the seventh
 * was hand-copied from the sixth — flagged by the 2026-08-24 code review.
 * They exist because the browser deliberately never holds `APP_AUTH_TOKEN`:
 * `lib/session.ts` issues a cookie that proves knowledge of it without
 * carrying it, so the token stays server-side and these handlers hold it.
 *
 * **What is shared here is only the mechanics** — the backend origin, the
 * demo refusal, the transport guard, and relaying the upstream answer. Each
 * handler keeps its own validation and its own words, because those are the
 * parts that differ and the parts a reader needs to see at the callsite: a
 * pass says "nothing was recorded", the scout desk says "nothing was sent
 * and nothing was spent", and a lookup says "nothing was created". Folding
 * those into one function would make seven different promises into one vague
 * one, which is the opposite of the honesty rule they were written for.
 *
 * What this does NOT do: authenticate. `middleware.ts` gates every one of
 * these paths through `JSON_ROUTE_HANDLERS`, so an unauthenticated call gets
 * a JSON 401 rather than an HTML login redirect that a `fetch` would read as
 * success. A new handler must be added to that set — this module cannot do
 * it, and `tests/test_token_proxy_routes.py` is what catches the omission.
 */

import { NextResponse } from "next/server";

/** The Python backend, over loopback inside the container. */
export const BACKEND = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";

/**
 * The bearer token, or `null` on the demo instance (which holds none).
 * Callers refuse in their own words rather than being handed a generic one.
 */
export function backendToken(): string | null {
  return process.env.APP_AUTH_TOKEN ?? null;
}

/**
 * "This is the demo instance. It holds no credentials, so {what} from here.",
 * 403.
 *
 * Only for the three handlers that actually say this (`/pass`,
 * `/scout-desk`, `/parlay-lookup`). The other four refuse in genuinely
 * different terms — the lockout is "the operator's own note to themselves
 * and the demo has no operator", `/refresh-odds` answers 200 with a typed
 * `OddsRefreshResult` because its caller reads that shape — and flattening
 * those into this sentence would make four accurate refusals into one vague
 * one. They keep their own words and use only the mechanics below.
 */
export function demoRefusal(what: string): NextResponse {
  return NextResponse.json(
    {
      detail:
        "This is the demo instance. It holds no credentials, so " +
        `${what} from here.`,
    },
    { status: 403 },
  );
}

/** The request body as JSON, or a 400 — never a throw into the framework. */
export async function readJsonBody(
  request: Request,
): Promise<{ ok: true; body: unknown } | { ok: false; response: NextResponse }> {
  try {
    return { ok: true, body: await request.json() };
  } catch {
    return {
      ok: false,
      response: NextResponse.json(
        { detail: "The request body was not JSON." },
        { status: 400 },
      ),
    };
  }
}

/**
 * Call the backend and relay its answer verbatim.
 *
 * `unreachable` is the caller's own sentence for a transport failure, and it
 * must say what did NOT happen — that is the whole content of the message to
 * someone whose tap vanished. The upstream body is relayed as-is because the
 * backend owns the refusal words; a null body (a proxy page, an empty 502)
 * becomes a detail naming the status rather than a silent success.
 */
export async function relayToBackend(
  path: string,
  init: {
    method: string;
    token: string;
    body?: unknown;
    /**
     * The detail used when the backend answers with a body that is not JSON.
     * Two wordings exist across the seven handlers and both are kept: the
     * estimate/lockout family names the symptom, the rest name the status.
     */
    unreadable?: string;
  },
  unreachable: string,
): Promise<NextResponse> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${init.token}`,
  };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}${path}`, {
      method: init.method,
      headers,
      cache: "no-store",
      ...(init.body !== undefined
        ? { body: JSON.stringify(init.body) }
        : {}),
    });
  } catch {
    return NextResponse.json({ detail: unreachable }, { status: 502 });
  }

  const payload: unknown = await upstream.json().catch(() => null);
  return NextResponse.json(
    payload ?? {
      detail: init.unreadable ?? `backend returned ${upstream.status}`,
    },
    { status: upstream.status },
  );
}
