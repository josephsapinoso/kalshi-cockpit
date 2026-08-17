import Link from "next/link";
import HowToRead from "@/components/HowToRead";
import LiveBoard from "@/components/LiveBoard";
import SlateRow, { type SlateState } from "@/components/SlateRow";
import { TicketProvider } from "@/components/TicketProvider";
import WindowBanner from "@/components/WindowBanner";
import RefreshOddsPanel from "@/components/RefreshOddsPanel";
import SignalStrip from "@/components/SignalStrip";
import WindowSchedule from "@/components/WindowSchedule";
import {
  fetchBoard,
  fetchHealth,
  fetchSignal,
  fetchWindow,
  formatAge,
  formatDuration,
} from "@/lib/api";
import type { ActionableWindow, Signal } from "@/lib/api";

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
  // Same treatment, same reason. `beta` is context for the cards, not a
  // precondition of them: an unreachable signal endpoint must not turn a page
  // full of prices into "Backend unreachable", and `SignalStrip` renders
  // nothing at all rather than a placeholder that could read as a measured zero.
  let signal: Signal | null = null;
  try {
    [board, health] = await Promise.all([
      fetchBoard(showRejected),
      fetchHealth(),
    ]);
    actionable = await fetchWindow().catch(() => null);
    signal = await fetchSignal().catch(() => null);
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

        {/* **Directly beneath the banner, because they answer consecutive
            questions.** The banner says whether this instant is usable; the
            schedule says which instants today are. Split apart on the page, a
            reader who learns "closed" from the first has no reason to keep
            scrolling for the second, which is the one that tells them when to
            come back. */}
        {actionable && <WindowSchedule window={actionable} />}

        {/* Third in the same sequence, and it is the one that can change the
            answer. The banner says whether now is usable and the schedule says
            which instants today are; this says what to do when the answer to
            both is "not now" and the games are still hours away. */}
        <RefreshOddsPanel />

        {/* **When this slate was recorded, whenever that is not now.**
            The rows below carry no date of their own, so without this a slate
            from last night and a slate from ninety seconds ago draw
            identically — which is exactly how a hundred rows from across the
            whole record came to be read as today's board. Shown only when the
            slate is not current: a line saying "this is current" on every page
            load is a line nobody reads by the third time. */}
        {!board.slate.is_current && board.slate.age_ms !== null && (
          <div className="mb-8 rounded-2xl border border-accent-2/50 bg-card p-4">
            <p className="text-sm text-muted">
              <span className="font-semibold text-accent-2">
                Not a live slate.
              </span>{" "}
              These are the last decisions this instance recorded,{" "}
              {formatAge(board.slate.age_ms)}. Nothing here is bettable, and the
              prices are a record rather than an offer. A slate older than{" "}
              {formatDuration(board.slate.window_ms)} means the recording loop
              is not running, not that the market is quiet.
            </p>
          </div>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-3 border-y py-4">
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

        {/* **The central fact, which was in the payload and on no screen.**
            The counts above are correctly *this slate's* now, and that
            windowing quietly took away the Board's only statement about the
            record: "Bettable now: 0" reads as a quiet half-hour when what it
            actually reports is zero actionable across the entire life of the
            database. Both numbers come off the server — `recorded_total`, and
            the gate's own `suppressed_reason IS NULL AND reference_contracts >
            0` — because a zero typed in here would go on reading as a finding
            on the day it stopped being one. */}
        <p className="mb-8 max-w-xl text-sm leading-relaxed text-muted">
          Bettable now{" "}
          <span className="font-semibold text-foreground">
            {board.counts.surfaced}
          </span>{" "}
          &mdash; and{" "}
          <span className="font-semibold text-foreground">
            {board.slate.actionable_total}
          </span>{" "}
          of {board.slate.recorded_total}{" "}
          {board.slate.recorded_total === 1 ? "decision" : "decisions"} ever
          recorded. The second pair is the whole record rather than this slate,
          and it is what the gate counts towards opening.
        </p>

        {/* **Immediately above the cards, because it is what they are worth.**
            Every row below is generated by the consensus edge number, and that
            number has been measured against Kalshi's own close. Until now the
            result appeared nowhere in this app — a reader could study a full
            board of edges with no way to learn that the signal producing them
            has been tested. Placed here rather than at the top of the page on
            purpose: read as a header it is a disclaimer nobody reaches the end
            of, read directly above the cards it is a caption on them. */}
        <div className="mb-8">
          <SignalStrip signal={signal} now={Date.now()} />
        </div>

        {board.surfaced.length === 0 ? (
          <div className="rounded-2xl border bg-card p-7">
            {/* Two ways to have nothing to bet, and they mean opposite things
                about whether the machinery is working. Printing the no-edge
                explanation over an expired slate would report a quiet market
                when what actually happened is that the clock ran out. */}
            <h2 className="text-xl font-bold tracking-tight">
              {board.slate.anchor_ms === null
                ? "Nothing recorded yet"
                : board.expired.length > 0
                  ? "Nothing bettable now"
                  : "Nothing to bet"}
            </h2>
            <p className="mt-2 max-w-lg text-sm leading-relaxed text-muted">
              {board.slate.anchor_ms === null ? (
                <>
                  {/* The third state, and it was drawn as the first. A database
                      that has never recorded a decision and a slate on which
                      nothing has an edge are opposite findings: one says the
                      loop has not run, the other says it has and the market is
                      priced. */}
                  This database holds no recommendations at all, so the engine
                  has not yet priced anything — which is a different statement
                  from &ldquo;nothing had an edge&rdquo;. Nothing has been
                  judged.
                </>
              ) : board.expired.length > 0 ? (
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
            {/* **What the slate is a slice of.** These rows are the current
                slate and nothing older, which is the fix to a Board that ranked
                the whole record by apparent edge. Both halves are stated: the
                history left off, and — when the window itself is longer than
                one page — the rows inside it that this response did not carry.
                A truncation nobody is told about is the same defect in a
                smaller frame. */}
            <p className="mt-2 max-w-xl text-xs text-muted">
              {board.slate.truncated && (
                <>
                  Showing {board.slate.returned} of {board.slate.in_window} in
                  this slate.{" "}
                </>
              )}
              {/* The other way a row leaves this list, and it used to leave it
                  without a trace: counted inside the window by the timestamp
                  the query filtered on, then put back outside it by the
                  freshness the server actually measured. Named separately from
                  the truncation above because the two drops have nothing to do
                  with each other, and reading a re-decision as a page limit
                  would send anyone looking in the wrong place. */}
              {board.slate.off_basis > 0 && (
                <>
                  {board.slate.off_basis}{" "}
                  {board.slate.off_basis === 1 ? "row was" : "rows were"} inside
                  this slate by the recorded timestamp and outside it by the
                  freshness the server measured, so{" "}
                  {board.slate.off_basis === 1 ? "it is" : "they are"} counted
                  in the window above and listed nowhere below.{" "}
                </>
              )}
              {board.slate.older_than_window > 0 && (
                <>
                  A further {board.slate.older_than_window} recorded{" "}
                  {board.slate.older_than_window === 1 ? "decision is" : "decisions are"}{" "}
                  older than this slate and{" "}
                  {board.slate.older_than_window === 1 ? "is" : "are"} history
                  rather than a board — read{" "}
                  <Link href="/ledger" className="underline">
                    the ledger
                  </Link>{" "}
                  for those.
                </>
              )}
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

        {/* **Below the prices, not above them.** The copy is good and is
            unchanged; the placement was the defect. Sitting between the counts
            and the cards it is ~1,700px of a ~9,000px page, so every phone load
            scrolls past a lesson to reach a price — and a block that has to be
            scrolled past to do the thing you opened the page for gets swiped
            through like a cookie banner, which is the exact failure its own
            docstring warns about. A permanent block is read once and
            remembered; it does not need to be first. */}
        <div className="mt-14">
          <HowToRead />
        </div>
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
