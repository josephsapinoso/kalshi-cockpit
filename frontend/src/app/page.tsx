import Link from "next/link";
import OpportunityCard from "@/components/OpportunityCard";
import WindowBanner from "@/components/WindowBanner";
import { fetchBoard, fetchHealth, fetchWindow } from "@/lib/api";
import type { ActionableWindow } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function BoardPage({
  searchParams,
}: {
  searchParams: Promise<{ suppressed?: string }>;
}) {
  const params = await searchParams;
  const showSuppressed = params.suppressed === "1";

  let board, health;
  // The window is fetched separately and allowed to fail on its own. It is
  // context for the Board, not a precondition of it: losing the timetable must
  // not turn a page full of prices into "Backend unreachable".
  let actionable: ActionableWindow | null = null;
  try {
    [board, health] = await Promise.all([
      fetchBoard(showSuppressed),
      fetchHealth(),
    ]);
    actionable = await fetchWindow().catch(() => null);
  } catch {
    return (
      <Shell>
        <div className="rounded-2xl border bg-card p-7">
          <h2 className="text-xl font-bold tracking-tight">Backend unreachable</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Start it with{" "}
            <code className="rounded bg-accent-soft px-1.5 py-0.5 font-mono text-xs text-accent">
              python -m backend.main --seed-demo
            </code>
            . Showing nothing is deliberate: a board that renders without data
            would look like &ldquo;no opportunities&rdquo; rather than
            &ldquo;no connection&rdquo;.
          </p>
        </div>
      </Shell>
    );
  }

  return (
    <Shell>
      {health.instance_mode === "demo" && (
        <div className="mb-8 rounded-2xl border border-accent-2/50 bg-card p-4">
          <p className="text-sm text-muted">
            <span className="font-semibold text-accent-2">Demo instance.</span>{" "}
            Synthetic data, no credentials, and no execution path. The numbers
            are shaped to resemble a real slate &mdash; which means mostly no
            edge.
          </p>
        </div>
      )}

      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Board</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Kalshi priced against devigged sportsbook consensus. A bet appears
          only when the edge survives fees, freshness, depth and the suspicion
          checks.
        </p>
      </header>

      {actionable && (
        <WindowBanner
          window={actionable}
          surfaced={board.counts.surfaced}
          expired={board.counts.expired}
          quoteLimitS={board.staleness.max_kalshi_quote_age_s}
        />
      )}

      <div className="mb-8 flex flex-wrap items-center gap-3 border-y py-4">
        <Stat label="Bettable now" value={board.counts.surfaced} accent />
        <Stat label="Expired" value={board.counts.expired} />
        <Stat label="Suppressed" value={board.counts.suppressed} />
        <Stat label="No edge" value={board.counts.no_edge} />
        <Link
          href={showSuppressed ? "/" : "/?suppressed=1"}
          className="ml-auto rounded-full border px-4 py-2 text-sm font-semibold transition-colors hover:bg-card"
        >
          {showSuppressed ? "Hide rejected" : "Show rejected"}
        </Link>
      </div>

      {board.surfaced.length === 0 ? (
        <div className="rounded-2xl border bg-card p-7">
          {/* Two ways to have nothing to bet, and they mean opposite things
              about whether the machinery is working. Printing the no-edge
              explanation over an expired slate would report a quiet market
              when what actually happened is that the clock ran out. */}
          <h2 className="text-xl font-bold tracking-tight">
            {board.expired.length > 0 ? "Nothing bettable now" : "Nothing to bet"}
          </h2>
          <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
            {board.expired.length > 0 ? (
              <>
                The engine did find something — {board.expired.length}{" "}
                {board.expired.length === 1 ? "bet" : "bets"}, listed below —
                and every one of them is now priced against a Kalshi quote past
                its {board.staleness.max_kalshi_quote_age_s}-second limit. That
                is a timing problem, not a quiet market.
              </>
            ) : (
              <>
                {board.note} Kalshi prices sports to about two cents against a
                dozen sub-second market makers, so an empty board is the honest
                result most of the time.
              </>
            )}
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {board.surfaced.map((rec) => (
            <OpportunityCard
              key={rec.id}
              rec={rec}
              quoteLimitMs={board.staleness.max_kalshi_quote_age_s * 1000}
            />
          ))}
        </div>
      )}

      {/* Kept rather than hidden. "There is nothing to bet" and "there was
          something and the moment has passed" are different answers, and only
          one of them means the machinery is working. */}
      {board.expired.length > 0 && (
        <section className="mt-14">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            The moment has passed
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            The engine sized {board.expired.length}{" "}
            {board.expired.length === 1 ? "bet" : "bets"} that can no longer be
            placed: a Kalshi quote is only accepted for{" "}
            {board.staleness.max_kalshi_quote_age_s} seconds, and the recorder
            polls far less often than that. They are shown because a board that
            silently drops them looks identical to a board that never found
            anything.
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {board.expired.map((rec) => (
              <OpportunityCard
                key={rec.id}
                rec={rec}
                expired
                quoteLimitMs={board.staleness.max_kalshi_quote_age_s * 1000}
              />
            ))}
          </div>
        </section>
      )}

      {showSuppressed && board.suppressed.length > 0 && (
        <section className="mt-14">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Rejected, and why
          </h2>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
            Kept rather than discarded. A rule firing constantly is either
            miscalibrated or catching a real upstream problem, and both are
            findings.
          </p>
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {board.suppressed.map((rec) => (
              <OpportunityCard key={rec.id} rec={rec} suppressed />
            ))}
          </div>
        </section>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return <div className="mx-auto max-w-5xl px-6 py-12 sm:py-16">{children}</div>;
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent?: boolean;
}) {
  return (
    <div className="pr-6">
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div
        className={`tabular mt-1 text-2xl font-extrabold tracking-tight ${
          accent ? "text-accent" : "text-foreground"
        }`}
      >
        {value}
      </div>
    </div>
  );
}
