/**
 * Sign in to the live cockpit.
 *
 * A single shared token rather than accounts: there is exactly one operator,
 * and a user table would be more surface for no benefit. The token is the same
 * `APP_AUTH_TOKEN` that authorises orders, but it is exchanged here for a
 * cookie that cannot be replayed as one -- see `lib/session.ts`.
 */

export const metadata = { title: "Sign in — Kalshi Cockpit" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; error?: string }>;
}) {
  const { next = "/", error } = await searchParams;

  return (
    <div className="mx-auto max-w-md px-4 py-16 sm:py-24">
      <header className="mb-8">
        <h1 className="display text-3xl sm:text-4xl">Sign in</h1>
        <p className="mt-3 text-lg text-muted">
          This instance holds live credentials and a running record. The demo is
          public; this is not.
        </p>
      </header>

      <form
        method="POST"
        action="/session"
        className="rounded-2xl border bg-card p-6"
      >
        <input type="hidden" name="next" value={next} />

        <label
          htmlFor="token"
          className="block text-xs font-semibold uppercase tracking-widest text-muted"
        >
          Access token
        </label>
        <input
          id="token"
          name="token"
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          // `font-mono` because the token is 43 opaque characters and telling
          // an l from a 1 on a phone otherwise depends on the font.
          className="mt-2 w-full rounded-lg border bg-transparent px-3 py-2 font-mono text-sm"
          placeholder="APP_AUTH_TOKEN"
        />

        {error ? (
          <p
            role="alert"
            className="mt-3 text-sm font-semibold text-[var(--negative)]"
          >
            That token was not accepted.
          </p>
        ) : null}

        <button
          type="submit"
          className="mt-5 w-full rounded-lg bg-accent px-4 py-2.5 text-sm font-semibold text-white"
        >
          Sign in
        </button>

        <p className="mt-4 text-sm text-muted">
          Signing in grants read access to the cockpit. It does not arm trading
          &mdash; the gate is a separate, deliberate act and is locked until the
          record earns it.
        </p>
      </form>
    </div>
  );
}
