/**
 * Session cookie for the live cockpit.
 *
 * Why the cookie is NOT the token
 * ------------------------------
 * `APP_AUTH_TOKEN` is the bearer that authorises `POST /api/orders` -- the one
 * route that can spend money. Storing it in a cookie would mean any XSS, any
 * shared browser, any screenshot of devtools hands over order authority.
 *
 * So the cookie carries `<expiry>.<hmac>` where the HMAC is keyed on the token
 * and signs only the expiry. It proves the holder knew the token at some point;
 * it does not reveal it and cannot be replayed as one. Compromising the cookie
 * costs you read access to the cockpit, not the ability to trade.
 *
 * Why presence of the token is the switch
 * ---------------------------------------
 * The demo instance is the portfolio link and must stay open; the live instance
 * must not. Rather than branch on `INSTANCE_MODE` -- which can be set wrong --
 * the gate turns on exactly when `APP_AUTH_TOKEN` exists. The backend already
 * *refuses to boot* in live mode without it, so "live but unauthenticated" is
 * not a reachable configuration.
 */

const ENCODER = new TextEncoder();

export const COOKIE_NAME = "cockpit_session";

/** Thirty days. This is a phone-first tool; re-typing a 43-character token on a
 *  handset is the kind of friction that gets a login disabled entirely. */
export const SESSION_MAX_AGE_S = 60 * 60 * 24 * 30;

/** The shared secret, or `null` on an instance that has none (the demo). */
export function sessionSecret(): string | null {
  const token = process.env.APP_AUTH_TOKEN;
  return token && token.length > 0 ? token : null;
}

async function hmac(secret: string, message: string): Promise<string> {
  // Web Crypto rather than node:crypto: this module is imported by middleware,
  // which runs on the Edge runtime where node:crypto is unavailable.
  const key = await crypto.subtle.importKey(
    "raw",
    ENCODER.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign("HMAC", key, ENCODER.encode(message));
  return Array.from(new Uint8Array(signature))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Length-independent comparison, so a wrong guess leaks no timing signal. */
function constantTimeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

export async function issueSession(secret: string, now = Date.now()): Promise<string> {
  const expiry = String(now + SESSION_MAX_AGE_S * 1000);
  return `${expiry}.${await hmac(secret, expiry)}`;
}

export async function verifySession(
  value: string | undefined,
  secret: string,
  now = Date.now(),
): Promise<boolean> {
  if (!value) return false;
  const separator = value.lastIndexOf(".");
  if (separator <= 0) return false;

  const expiry = value.slice(0, separator);
  const signature = value.slice(separator + 1);

  // Signature first, then expiry. Checking expiry first would let an unsigned
  // cookie decide how much work we do, and reversing the order costs nothing.
  if (!constantTimeEqual(signature, await hmac(secret, expiry))) return false;

  const expiresAt = Number(expiry);
  return Number.isFinite(expiresAt) && expiresAt > now;
}

/** Whether the supplied token is the shared secret. */
export function tokenMatches(supplied: string, secret: string): boolean {
  return constantTimeEqual(supplied, secret);
}
