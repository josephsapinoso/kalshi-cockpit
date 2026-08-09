import Link from "next/link";
import HowToRead from "@/components/HowToRead";
import LiveBoard from "@/components/LiveBoard";
import SlateRow, { type SlateState } from "@/components/SlateRow";
import { TicketProvider } from "@/components/TicketProvider";
import WindowBanner from "@/components/WindowBanner";
import { fetchBoard, fetchHealth, fetchWindow } from "@/lib/api";
import type { ActionableWindow } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function BoardPage({
  searchParams,
}: {
  searchParams: Promise<{ rejected?: string }>;
}) {
  const params = await searchParams;
  /**
   * **Rejected rows are visible by default**, and `?rejected=0` hides them.
   *
   * The parameter used to be `?suppressed=1` and defaulted to off, so the
   * ordinary state of this page was a blank screen with a count of things it
   * was not showing. On a slate where 0 of ~200 rows are actionable, the ones
   * that were refused are the only content the board has, and which check
   * refused them is the most useful thing on it.
   *
   * Nothing about the decision changed: every row below carries zero
   * contracts, no ticket opens on one, and the order endpoint re-derives
   * suppression and staleness inside the request regardless of what this page
   * chose to draw.
   */
  const showRejected = params.rejected !== "0";

  let board, health;
  // The window is fetched separately and allowed to fail on its own. It is
  // context for the Board, not a precondition of it: losing the timetable must
  // not turn a page full of prices into "Backend unreachable".
  let actionable: ActionableWindow | null = null;
  try {
    [board, health] = await Promise.all([
      fetchBoard(showRejected),
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

  // Of the rows that are live, how many are showing a price older than the
  // quote limit. Read from the server rather than recomputed here: the split
  // between "bettable" and "priced now" is a decision the order endpoint makes,
  // and a page that derived it separately would eventually disagree with it.
  const priceStale = board.counts.price_stale ?? 0;

  /**
   * Everything the engine judged and will not bet, in one list.
   *
   * Ordered expired → rejected → no-edge, which is decreasing order of "the
   * machinery found something". `no_edge` and `suppressed` arrive empty unless
   * the page asked for them, so this collapses to the expired rows alone when
   * rejected rows are hidden.
   */
  const rest: { rec: (typeof board.expired)[number]; state: SlateState }[] = [
    ...board.expired.map((rec) => ({ rec, state: "expired" as SlateState })),
    ...board.suppressed.map((rec) => ({ rec, state: "rejected" as SlateState })),
    ...board.no_edge.map((rec) => ({ rec, state: "no-edge" as SlateState })),
  ];

  /** Rows the server counted and this page asked it not to send. */
  const hidden = showRejected
    ? 0
    : board.counts.suppressed + board.counts.no_edge;

  return (
    <Shell>
      {/* One sheet for the whole page. The limits come from the same payload
          the cards are rendered from, so the ticket and the card under it can
          never be judging freshness against different numbers. */}
      <TicketProvider
        instanceMode={health.instance_mode}
        quoteLimitMs={board.staleness.max_kalshi_quote_age_s * 1000}
        oddsLimitMs={board.staleness.max_odds_age_s * 1000}
      >
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
          />
        )}

        <div className="mb-8 flex flex-wrap items-center gap-3 border-y py-4">
          <Stat label="Bettable now" value={board.counts.surfaced} accent />
          {/* Shown only when it is non-zero, because it is a qualifier on the
              number to its left rather than a category of its own. */}
          {priceStale > 0 && <Stat label="Price re-read on order" value={priceStale} />}
          <Stat label="Expired" value={board.counts.expired} />
          <Stat label="Suppressed" value={board.counts.suppressed} />
          <Stat label="No edge" value={board.counts.no_edge} />
          <Link
            href={showRejected ? "/?rejected=0" : "/"}
            className="ml-auto rounded-full border px-4 py-2 text-sm font-semibold transition-colors hover:bg-card"
          >
            {showRejected ? "Hide rejected" : "Show rejected"}
          </Link>
        </div>

        <HowToRead />

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
                  {/* One cause now, and it is stated rather than counted. This
                      once asserted every expired row had a stale Kalshi quote,
                      then counted which of the two clocks had run out. Neither
                      survives the order-time refresh: a stale quote no longer
                      expires a row at all, so everything here has outlived its
                      sportsbook consensus. */}
                  The engine did find something — {board.expired.length}{" "}
                  {board.expired.length === 1 ? "bet" : "bets"}, listed below —
                  and the sportsbook consensus behind{" "}
                  {board.expired.length === 1 ? "it" : "them"} is past its{" "}
                  {Math.round(board.staleness.max_odds_age_s / 60)}-minute limit.
                  Only an odds credit refreshes that, so this is a budget
                  problem, not a quiet market.
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
          /* A client component, and only for the bettable rows. Expired and
             suppressed cards below are history and must not move -- a ticker
             that animated a row nobody can bet would be movement that means
             nothing, which is the failure the Board already had once when it
             ranked every row ever written. */
          <LiveBoard
            rows={board.surfaced}
            enabled={health.live_quotes_available === true}
            quoteLimitMs={board.staleness.max_kalshi_quote_age_s * 1000}
            oddsLimitMs={board.staleness.max_odds_age_s * 1000}
          />
        )}

        {/* **The rest of the slate, one line per row.**
            Three states that used to be a card grid each, or hidden entirely.
            A card per rejected row is unscannable at ~200 decisions, and a
            card is also the wrong shape: it is the format the bettable rows
            use, and these cannot be bet.

            Nothing in this list is tappable. There is no ticket for a row the
            server will refuse, and offering a sheet with a permanently dead
            Confirm would suggest the decision is reversible from here. The
            expired rows lost their ticket in this change and that is the
            trade: one line each, no order path, and the reason in words. */}
        {(rest.length > 0 || hidden > 0) && (
          <section className="mt-14">
            <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
              The rest of the slate
            </h2>
            <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
              {rest.length > 0 ? (
                <>
                  {rest.length}{" "}
                  {rest.length === 1 ? "candidate" : "candidates"} the engine
                  judged and will not bet.{" "}
                </>
              ) : (
                <>Nothing here, because this view is hiding it.{" "}</>
              )}
              Rejected rows are shown by default: a board that hides what it
              refused cannot be read as evidence about the rules doing the
              refusing, and with nothing bettable most days this is the entire
              content of the page.{" "}
              {board.expired.length > 0 && (
                <>
                  The <span className="font-mono text-xs">EXPIRED</span> rows
                  were sized and are past the{" "}
                  {Math.round(board.staleness.max_odds_age_s / 60)}
                  {/* Explicit, not a literal space after the expression. JSX
                      collapsed that one and rendered "15minutes" -- the same
                      defect `tasks/lessons.md` already records. No automated
                      check in this repo sees it; only reading the page does. */}
                  {" "}minute consensus limit, which only an odds credit
                  refreshes.{" "}
                </>
              )}
              Suppression and staleness still decide what is bettable; they
              stopped deciding what is visible.
            </p>
            <div className="mt-6 divide-y border-y">
              {rest.map(({ rec, state }) => (
                <SlateRow
                  key={rec.id}
                  rec={rec}
                  state={state}
                  oddsLimitMs={board.staleness.max_odds_age_s * 1000}
                />
              ))}
            </div>
            {/* Outside the list's own guard, deliberately. With the rejected
                rows hidden and nothing expired, `rest` is empty -- and a
                section that vanishes entirely is how a page comes to look like
                it found nothing when it is only declining to show it. */}
            {hidden > 0 && (
              <p className="mt-4 text-sm text-muted">
                {hidden} further {hidden === 1 ? "row is" : "rows are"} hidden.{" "}
                <Link href="/" className="underline">
                  Show rejected
                </Link>
                .
              </p>
            )}
          </section>
        )}
      </TicketProvider>
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
