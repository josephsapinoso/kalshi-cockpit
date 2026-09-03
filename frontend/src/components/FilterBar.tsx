import Link from "next/link";

import { listFilterQuery, type ListFilter } from "@/lib/api";
import { leagueLabel } from "@/lib/leagueLabel";

/**
 * The sticky bar that cuts a list down — by league, and by how soon the game
 * starts. Decision-map #15, resolved by Joe 2026-09-02 as option A: not in
 * the nav (six-link budget), a bar shared by the list screens (Games, Picks,
 * the parlay desk).
 *
 * **Two cuts and no third.** League and kickoff window are free — the data
 * is on every row. Market type is not a cut (#12 dropped props, so there is
 * nothing to cut by). The consensus-vs-Kalshi gap is not a cut and not an
 * ordering, and may never be offered here: it measured negative (`beta =
 * -0.141`), so cutting or ranking on it keeps the least trustworthy rows
 * (ADR 0071 section 2.5). `tests/test_list_filters.py` greps this file for
 * any such word.
 *
 * **Links, not state.** Every chip is a plain `Link` to the same page with
 * the cut in the query string; the page is a server component that reads
 * `searchParams` and sends the same string to the API (`listFilterQuery` is
 * used on both ends so the URL and the request cannot disagree). A cut is
 * therefore shareable, survives a reload, and needs no client JavaScript.
 * `prefetch={false}` on each chip is load-bearing: the list pages are
 * `force-dynamic`, and a dozen prefetched chips would be a dozen `/api/slate`
 * reads — each of them one book query per row — on every scroll past the
 * bar.
 *
 * **The chips are the leagues the server accepts**, which is the set of
 * leagues the desk can price at all (`IN_SCOPE_LEAGUES`' sport keys), not
 * the leagues with a game tonight — no payload carries that without
 * breaking the unfiltered read's byte-identity, and a chip for an
 * off-season league honestly returns an empty list that says so. The test
 * pins this list as a subset of the server's so no chip is a 422 one tap
 * away. Labels go through `leagueLabel`, so the chip and the row's league
 * tag say the same word.
 *
 * **Under the nav, never over it.** `Nav.tsx` is `sticky top-0 z-50`. This
 * bar sticks at `--nav-height` (a CSS variable the shell may set; 69px is
 * the nav's height measured in headless Chrome at 390, 768 and 1280px) at
 * `z-30`, so a nav change can move the bar by setting one variable rather
 * than editing this file. Both stack inside the content column, so the bar
 * never reaches wider than the page (`scripts/check_mobile.py` measures
 * that at 390px).
 *
 * **Small on a phone.** Below `sm` the chips live in a closed `<details>`
 * whose summary names the current cut, so the sticky footprint is one row
 * and the cut is never invisible; from `sm` up the chips render inline. Both
 * forms are server-rendered — `<details>` needs no script to open.
 */

//: The odds feed's sport keys, one per line so the test can read them.
//: Ordered by the deployment's season as it stands, not alphabetically —
//: the first chips are the ones with games tonight.
const LEAGUES: readonly string[] = [
  "baseball_mlb",
  "basketball_wnba",
  "americanfootball_nfl",
  "americanfootball_ncaaf",
  "basketball_nba",
  "icehockey_nhl",
];

//: Kickoff windows, in hours. "Next three hours" is the ticket's own
//: example; the rest widen it to the evening, the night, and the day. The
//: server accepts 1..168 and refuses the rest.
const WINDOW_HOURS: readonly number[] = [3, 6, 12, 24];

export default function FilterBar({
  pathname,
  filter,
  note,
}: {
  /** The page's own path, so each chip links back to the same screen. */
  pathname: string;
  /** The cut currently applied, as read from the URL. */
  filter: ListFilter;
  /**
   * What the cut removed, worded by the page from the server's echo
   * (`filter.hidden`) — "12 rows hidden by this cut". `null` when there is
   * nothing to say. A cut list must never read as the whole list.
   */
  note?: string | null;
}) {
  const active = filter.league !== null || filter.withinHours !== null;
  const summary = [
    filter.league === null ? "All leagues" : leagueLabel(filter.league),
    filter.withinHours === null
      ? "any start time"
      : `starts within ${filter.withinHours}h`,
  ].join(" · ");

  const chips = (
    <div className="flex flex-col gap-2">
      <Group label="League">
        <Chip
          href={`${pathname}${listFilterQuery({ ...filter, league: null })}`}
          active={filter.league === null}
        >
          All
        </Chip>
        {LEAGUES.map((key) => (
          <Chip
            key={key}
            href={`${pathname}${listFilterQuery({ ...filter, league: key })}`}
            active={filter.league === key}
          >
            {leagueLabel(key)}
          </Chip>
        ))}
        {/* A league in the URL that is not a chip still needs a chip, or
            the active cut has no visible control. The server has already
            accepted it by the time this renders (a refused value is a 422
            and the page draws that instead). */}
        {filter.league !== null && !LEAGUES.includes(filter.league) && (
          <Chip href={`${pathname}${listFilterQuery(filter)}`} active>
            {leagueLabel(filter.league)}
          </Chip>
        )}
      </Group>
      <Group label="Starts within">
        <Chip
          href={`${pathname}${listFilterQuery({ ...filter, withinHours: null })}`}
          active={filter.withinHours === null}
        >
          Any time
        </Chip>
        {WINDOW_HOURS.map((h) => (
          <Chip
            key={h}
            href={`${pathname}${listFilterQuery({ ...filter, withinHours: String(h) })}`}
            active={filter.withinHours === String(h)}
          >
            {h}h
          </Chip>
        ))}
        {filter.withinHours !== null &&
          !WINDOW_HOURS.map(String).includes(filter.withinHours) && (
            <Chip href={`${pathname}${listFilterQuery(filter)}`} active>
              {filter.withinHours}h
            </Chip>
          )}
      </Group>
      {active && (
        <p className="text-xs text-muted">
          {note ? `${note} ` : ""}
          <Link
            href={pathname}
            prefetch={false}
            className="font-semibold text-foreground hover:underline"
          >
            Show everything
          </Link>
        </p>
      )}
    </div>
  );

  return (
    <nav
      aria-label="Cut this list"
      className="sticky z-30 mt-6 border-y border-border bg-background/95 py-2 backdrop-blur-md"
      style={{ top: "var(--nav-height, 69px)" }}
    >
      {/* Phone: one row, the current cut in words, chips behind a tap. */}
      <details className="sm:hidden">
        <summary className="flex min-h-[40px] cursor-pointer list-none items-center justify-between gap-3 text-sm">
          <span>
            <span className="text-[0.65rem] font-semibold uppercase tracking-widest text-muted">
              Showing
            </span>{" "}
            <span className={active ? "font-semibold" : "text-muted"}>
              {summary}
            </span>
          </span>
          <span aria-hidden className="text-muted">
            ▾
          </span>
        </summary>
        <div className="pb-2 pt-3">{chips}</div>
      </details>
      {/* Wider screens: the chips inline, always visible. */}
      <div className="hidden sm:block">{chips}</div>
    </nav>
  );
}

function Group({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="mr-1 text-[0.65rem] font-semibold uppercase tracking-widest text-muted">
        {label}
      </span>
      {children}
    </div>
  );
}

function Chip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      prefetch={false}
      aria-current={active ? "true" : undefined}
      className={`inline-flex min-h-[36px] items-center rounded-full border px-3 text-sm transition-colors ${
        active
          ? "border-foreground bg-foreground text-background"
          : "border-border text-muted hover:border-border-strong hover:text-foreground"
      }`}
    >
      {children}
    </Link>
  );
}
