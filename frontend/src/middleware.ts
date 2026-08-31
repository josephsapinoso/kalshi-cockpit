/**
 * The gate in front of the live cockpit.
 *
 * Why here and not in the backend: uvicorn binds `127.0.0.1:8000` inside the
 * container and is never published. The only public surface is Next on 3000,
 * and `/api/*` is reachable only because `next.config.ts` rewrites it. Next
 * middleware runs *before* rewrites, so one gate here covers every page and
 * every proxied API route -- while server components keep calling the backend
 * directly over loopback with no token to manage.
 *
 * The demo instance has no `APP_AUTH_TOKEN` and is therefore ungated, which is
 * what the portfolio link needs.
 *
 * **It also sets the framing headers, on every response including the demo's.**
 * See `FRAME_HEADERS` below.
 */

import { NextResponse, type NextRequest } from "next/server";

import { COOKIE_NAME, sessionSecret, verifySession } from "@/lib/session";

/**
 * Paths that must answer without a session.
 *
 * `/api/health` is the load-bearing one. Fly's health check
 * (`[checks.health] path = "/api/health"` in fly.live.toml) arrives with no
 * cookie, so gating it would fail every check, restart the machine, fail again,
 * and present as a crash loop caused by adding a login page.
 */
const PUBLIC_PATHS = new Set([
  "/login",
  "/session",
  "/api/health",
  "/favicon.ico",
  "/icon.svg",
  "/robots.txt",
]);

/**
 * Gated paths that are called by `fetch` and answer JSON.
 *
 * These are Next route handlers, so they are not under `/api/` -- that prefix
 * belongs to the rewrite -- but a redirect to the login page would reach them
 * as an HTML body behind a 200, which every JSON client reads as success.
 */
const JSON_ROUTE_HANDLERS = new Set([
  "/refresh-odds",
  "/scout-desk",
  "/log-estimate",
  "/revise-estimate",
  "/lockout",
  "/pass",
  "/parlay-lookup",
  // Both spend-adjacent: `/parlay-bid` rests a real bid, `/parlay-bid-cancel`
  // takes it back. Exact-match handlers, which is why the cancel carries its
  // id in the body rather than the path -- a dynamic segment would miss this
  // set and fall through to the HTML login redirect a fetch reads as success.
  "/parlay-bid",
  "/parlay-bid-cancel",
  "/desk-attention",
  "/hedge-position",
  "/hedge-resolve",
  "/hedge-close",
]);

/**
 * Refuse to be framed by anyone but ourselves.
 *
 * **The exposure this closes.** Until 2026-08-31 the live cockpit sent neither
 * header, so any page on the internet could load it in an invisible iframe,
 * float a decoy over it, and have a signed-in reader click a control they
 * could not see. The controls behind this gate include `POST /api/manual-
 * orders`, which sends a REAL immediate-or-cancel order to Kalshi
 * (`MANUAL_ORDERS_ARE_DRY_RUNS = false` since 2026-08-26, ADR 0073), and the
 * bid and hedge paths beside it. Server-side re-validation does not help: a
 * clickjacked click is a genuine click from a genuine session, and every
 * check passes.
 *
 * **`self`, not `DENY`, and the reason is that it costs nothing.** An attacker
 * cannot serve a page from this origin, so same-origin framing is not a way
 * in; `DENY` would block only *our own* embedding and buys no security for it.
 * One thing it keeps working is the 390px verification harness recorded in
 * `tasks/NEXT.md` — a same-origin iframe is the only way found so far to get a
 * true phone viewport against an authed page, and `DENY` would have deleted
 * that tool in exchange for nothing.
 *
 * **Both headers, deliberately.** `frame-ancestors` supersedes
 * `X-Frame-Options` and wins wherever both are understood; the legacy header
 * stays for anything that does not implement CSP. They say the same thing, so
 * they cannot disagree.
 *
 * **This is not a full CSP and does not pretend to be.** A `script-src` or
 * `style-src` on this app is a separate change with a real chance of breaking
 * a page, and shipping it inside a framing fix would mean one deploy that
 * cannot be reasoned about. Framing is the exposure that was found; framing is
 * what this closes.
 */
const FRAME_HEADERS: ReadonlyArray<readonly [string, string]> = [
  ["Content-Security-Policy", "frame-ancestors 'self'"],
  ["X-Frame-Options", "SAMEORIGIN"],
];

/**
 * Applied to EVERY return path, including the demo's ungated one and the 401.
 *
 * Set on one funnel rather than at each `return`, because this middleware has
 * five exits and a header added at four of them is a header that is absent
 * exactly where somebody later adds a sixth.
 */
function withFrameHeaders(response: NextResponse): NextResponse {
  for (const [name, value] of FRAME_HEADERS) response.headers.set(name, value);
  return response;
}

export async function middleware(request: NextRequest) {
  const secret = sessionSecret();
  // No shared secret configured -- this is the demo. Nothing to protect.
  if (!secret) return withFrameHeaders(NextResponse.next());

  const { pathname } = request.nextUrl;
  if (PUBLIC_PATHS.has(pathname)) return withFrameHeaders(NextResponse.next());

  if (await verifySession(request.cookies.get(COOKIE_NAME)?.value, secret)) {
    return withFrameHeaders(NextResponse.next());
  }

  // An API caller gets a status code it can act on. Redirecting these would
  // hand a JSON client an HTML login page and a 200, which reads as success.
  //
  // `/refresh-odds` is a route handler rather than a rewritten backend path --
  // it lives outside `/api/` so it cannot race the rewrite in `next.config.ts`
  // -- but it is called by `fetch` and answers JSON, so it needs this branch
  // and not the redirect below.
  if (pathname.startsWith("/api/") || JSON_ROUTE_HANDLERS.has(pathname)) {
    return withFrameHeaders(
      NextResponse.json(
        { detail: "Not authenticated. Sign in at /login." },
        { status: 401 },
      ),
    );
  }

  const login = new URL("/login", request.url);
  // Preserved so a deep link survives the round trip -- the difference between
  // opening a phone notification and landing where you meant to.
  if (pathname !== "/") login.searchParams.set("next", pathname);
  return withFrameHeaders(NextResponse.redirect(login));
}

export const config = {
  // Everything except Next's own static output. Those are hashed build assets
  // with nothing sensitive in them, and gating them would break the login page
  // itself.
  matcher: ["/((?!_next/static|_next/image).*)"],
};
