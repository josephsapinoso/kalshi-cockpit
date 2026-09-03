"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "./ThemeToggle";
import MarketSearch from "./MarketSearch";
import { SHELL_WIDTH } from "@/lib/shell";
import { fetchWindow, recordAttention } from "@/lib/api";
import { HEARTBEAT_INTERVAL_MS } from "@/lib/nextOddsWindow";
import { windowChip } from "@/lib/windowChip";
import type { Chip } from "@/lib/windowChip";

// Four links and a search button, since 2026-09-02 (decision-map #18, Joe's
// option A). The count is a budget rather than a coincidence: the row scrolls
// rather than clipping the page -- that is what `min-w-0 overflow-x-auto`
// below is for -- but whatever it scrolls is out of sight, and for the two
// weeks before #18 the six-link row was ALREADY scrolling. The ticket measured
// it: at 390px the row's scrollWidth was 424 against a clientWidth of 318,
// Playbook off-screen at 390 and Gate off at 320, while every sentence in
// this file that said "Gate keeps its visible slot at 390px" was a comment
// nobody had measured. The history below is kept as it was written, and
// every "six" in it describes the row before #18.
//
// **`/builder` AND `/rejections` NO LONGER EXIST. Corrected 2026-08-29.**
// This comment said in four separate places that they were "still served",
// and `frontend/src/app/` has held no `builder/` or `rejections/` directory
// since they were deleted (Footer.tsx's own list records both deletions:
// `/builder` deleted, `/rejections` folded into the Slate as a disclosure).
// A nav comment is where the next session goes to learn what the app has, so
// the error propagated into a written brief before anyone opened the folder.
// The history below is kept, in the past tense it always belonged in; what
// is deleted is described as deleted. `/dashboards` DOES still exist and is
// still served -- it is the only one of the three the phrase was ever true
// of, which is exactly why the sentence survived so long.
//
// Rejections took Builder's slot. Builder priced sportsbook parlays: it could
// not change a bet on this venue, and for a beginner it could change one in
// the wrong direction. Rejections answered "which check is refusing
// everything", which on a board showing 0 actionable of ~200 is the only
// question there is. `/builder` was later deleted outright.
//
// **Slate then took Rejections' slot, 2026-08-15, and the trade is the same
// shape.** Rejections aggregated the suppression codes across the slate; Slate
// shows every row with its own reason attached, beside the factors the record
// already holds and had never rendered. The aggregate is a strict summary of
// what the per-row screen now shows, so keeping both would spend a link on a
// projection of the other. `/rejections` was deleted in the 2026-08-22 review
// and its counts now render as a disclosure at the foot of the Slate, off the
// same rows -- which is what makes the two views incapable of disagreeing.
// **Log then took Data's slot, 2026-08-18, same trade again.** The calibration
// study (registration 2026-08-17) makes logging an estimate the one action
// performed before every hand bet, on a phone, on a clock -- the flow is
// budgeted at twelve seconds and a link that must be hunted for blows the
// budget. Data renders dbt marts that are read weekly at most, and
// `/dashboards` is still served (it is exempt in
// `tests/test_every_screen_is_reachable.py`, reached by typing the URL after
// a dbt build).
//
// **The Slate became the landing screen and the words became plain,
// 2026-08-20** (fleet convening, docs/reviews/2026-08-20-fleet-convening.md).
// "Board", "Slate", "Log", "Ledger" were four nouns a beginner cannot tell
// apart, and the one the app opened on was the screen that had shown nothing
// for 1,005 straight passes. "Games" is every game today; "Picks" is the
// filter's output, still one tap away at `/board`. "Log" stays -- it is the
// action the calibration study budgets twelve seconds for -- and "Ledger"
// stayed because its page was titled that, on the reasoning that renaming a
// tab away from its own page title trades one confusion for another. **That
// reasoning is superseded 2026-08-22** -- see the slot's own comment below.
// **Log's slot is retired, 2026-08-21, and nothing takes it.** Joe stopped
// the calibration study (Amendment 2, 2026-08-20, stopped without result):
// a nav slot opening a form that feeds a stopped study is quiet
// misdirection, and the twelve-second budget that earned the slot died
// with the study. `/estimate` is still served -- the page renders the
// terminal state at the top -- and is reached from the footer, exactly as
// `/dashboards` is reached by URL. (This sentence used to add `/builder` and
// `/rejections` to that list; both are deleted -- see the correction at the
// top of this comment.)
// **Scout takes the open sixth slot, 2026-08-21** (betting-desk item 6:
// metered first, promoted in the same change -- the desk arrives in the nav
// already wearing its meter). It is the one feature Joe asked for by shape
// (ADR 0060) on a tool he has ruled is a betting desk (ADR 0062), and its
// page is where today's Anthropic spend is read before sending it again.
// Placed before this slot so Gate keeps its visible slot at 390px: with six
// links the row scrolls, and the one that scrolls off is Playbook -- still
// the newest-least-urgent trade the comment below records.
// **Your bets takes Scout's slot, 2026-08-22** (the every-page review; Joe
// approved the swap). Two reasons, both the betting-desk ruling's: his own
// settled record is the screen a betting desk exists to serve, and the
// standalone Scout index was absorbed into the game screens the desk is
// sent from anyway -- its meter now rides `ScoutDesk` as a disclosure, so
// the page the slot pointed at no longer exists. Same position, so Gate
// keeps its visible slot at 390px and Playbook stays the link that scrolls.
// **This slot stops being called "Ledger", 2026-08-22.** `/bets` shipped
// 2026-08-21 as Joe's own settled-bet record -- the thing "Ledger" names in
// ordinary speech -- and the earlier convening's reason for keeping this
// label ("renaming a tab away from its own page title trades one confusion
// for another") stopped applying the day a second, truer claimant to the
// word existed. The partner's later nav-swap item would have moved `/bets`
// into this slot under that name; it was dropped once Scout took the open
// sixth slot, so `/bets` stays in the footer -- but the rename half of that
// item still stands on its own: this page is the engine's evidence base,
// not anyone's ledger, and it should stop reading as one. Route unchanged
// (`/ledger`, matching `/api/ledger`) -- only the label and the page's own
// heading move, the same pattern `/board` followed under "Picks" until
// 2026-09-02 (see the last entry below).
// **Parlays takes Evidence's slot, 2026-08-24** (Joe asked to promote the
// parlay link and demote whatever is not day-to-day). Same trade shape as
// every swap above: the Parlay desk is a screen bets are placed from --
// three daily cards, opened daily -- while Evidence is the engine's record,
// read for analysis at most weekly. Gate keeps its slot (it is the money
// interlock, the reason the budget is six), and Playbook stays the link
// that scrolls at 390px. `/ledger` moves to the footer, exactly as
// `/estimate` did -- served, linked, and one tap further away.
// **"Picks" opens the ranked list, 2026-09-02** (decision-map #8, ratified
// by Joe 2026-08-27; #29 named what it displaced). For two weeks the word
// opened `/board`, a screen on which nothing has been a pick in the life of
// the record and every row carried a live hand-bet button. The slot now
// opens `/picks` -- the "likely winners" block Games already renders, as a
// screen of its own with no order route on it -- and `/board` goes to the
// footer as "Refusals", with the sentence that says what it is. A promotion
// rather than a move: the block stays on Games too. Same six links, same
// order, so Gate keeps its visible slot at 390px and Playbook still scrolls.
// **Gate and Playbook go to the footer and search comes to the header,
// 2026-09-02** (decision-map #18, Joe's option A; the two are Footer.tsx's
// first entries and keep their names). The row that stays is the four screens
// a bet is looked at or read back from on the day: every game, the ranked
// list, the parlay cards, his own record. Gate is the screen that says
// whether the ENGINE may move money, and it is read, never acted on -- its
// number is a games-against-300 count that no plan waits for -- so a tap
// further away costs nothing that a scrolled-off slot was not already
// costing. Playbook is reference. What the freed width buys is the search:
// half the time Joe arrives already knowing his game, and until now the only
// way to name one was a collapsed line at the foot of the longest page. The
// search is the button beside the logo below, and it opens the same
// `MarketSearch` the Games and market screens host -- reached from here, not
// rebuilt here.
const LINKS = [
  { href: "/", label: "Games" },
  { href: "/picks", label: "Picks" },
  { href: "/parlays", label: "Parlays" },
  { href: "/bets", label: "Your bets" },
];

// Which link a page lights. A market page is a game's own screen, reached
// from a Games row or a Picks row, and the nav cannot know which -- so it
// lights Games, the screen that holds every game. Before 2026-09-02 no link
// lit on `/market/[ticker]` at all. `/slate` is `/` re-exported for bookmarks
// and lights the same link.
function lights(href: string, pathname: string): boolean {
  if (pathname === href) return true;
  return href === "/" && (pathname === "/slate" || pathname.startsWith("/market/"));
}

export default function Nav() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  // The window chip's fact, fetched on mount and once a minute after. `null`
  // renders nothing at all: an unreachable timetable must not put a state
  // claim in the chrome of every page. Only xl viewports render the chip, but
  // the fetch is cheap and gating it on a media query would put layout state
  // into data state.
  const [chip, setChip] = useState<Chip | null>(null);
  // The header search. Closed until the button is pressed, and closed again
  // on every navigation and on Escape: the panel is a layer over whatever
  // page is open, and a layer that outlives the page it was opened on reads
  // as part of the next one. While closed nothing is mounted -- the search
  // is the one control here that can reach a market no screen priced, and
  // it opens a hand-bet ticket, so it exists on the page only while asked
  // for. (The Picks screen's "no door to money" rule, #8, is about what the
  // PAGE renders and is pinned on the page's source; this button asks for a
  // typed name before anything with a price appears.)
  const [searchOpen, setSearchOpen] = useState(false);

  useEffect(() => {
    setSearchOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!searchOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSearchOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [searchOpen]);

  // Gated on visibility exactly as the heartbeat below is, and for a weaker
  // version of the same reason: a backgrounded tab was fetching the timetable
  // once a minute for a chip nobody could see, for as long as the tab lived.
  // No credits ride on it -- `/api/window` reads stored state -- so this is a
  // request loop with no reader, not a spend. It resumes on `visibilitychange`
  // so the chip is current the moment the tab is, rather than up to a minute
  // later. Same interval as the heartbeat, imported rather than retyped.
  useEffect(() => {
    let cancelled = false;
    const load = () => {
      if (document.visibilityState !== "visible") return;
      fetchWindow()
        .then((w) => {
          if (!cancelled) setChip(windowChip(w));
        })
        .catch(() => {
          if (!cancelled) setChip(null);
        });
    };
    load();
    const timer = setInterval(load, HEARTBEAT_INTERVAL_MS);
    document.addEventListener("visibilitychange", load);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", load);
    };
  }, []);

  // The heartbeat. This is what the odds feed follows instead of a clock
  // (ADR 0071 §2.6): while a page is open, the desk re-buys on the ten-minute
  // refresh cadence; when nothing is open, it falls back to an hourly floor.
  //
  // **`document.visibilityState === "visible"` is the single most load-bearing
  // line in this change**, and it is worth saying why rather than trusting the
  // reader to infer it. The design it replaces cost ~576 credits/day. This one
  // costs ~1,152/day at two sports — and ~2,304 at four, past the whole
  // 20,000/month plan — *if a tab is left open and stamping around the clock*.
  // A backgrounded tab is exactly that tab. So the guard is not a politeness
  // about wasted requests; it is the difference between the new design being
  // cheaper than the old one and being twice its price.
  //
  // It is deliberately not the only control. The backend's attention slice
  // (300 of 700 credits a day) is the hard ceiling and does not depend on any
  // browser behaving — see `odds/timing.py`. This is the brace; that is the
  // belt. A guard that can be defeated by a browser bug should never be the
  // only thing between a design and its worst case.
  //
  // A `visibilitychange` listener rides alongside the interval so returning to
  // a tab stamps immediately rather than up to a minute later. Coming back to
  // the desk is the moment freshness matters most, and it is also the moment a
  // person is most likely to read a stale price as a live one.
  //
  // Failures are swallowed. A missed heartbeat costs one delayed sweep and the
  // next tick retries; surfacing it would put an error in the chrome of every
  // page for something the reader cannot act on and did not ask for.
  useEffect(() => {
    const beat = () => {
      if (document.visibilityState !== "visible") return;
      void recordAttention().catch(() => {});
    };
    beat();
    const timer = setInterval(beat, HEARTBEAT_INTERVAL_MS);
    document.addEventListener("visibilitychange", beat);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", beat);
    };
  }, []);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`sticky top-0 z-50 transition-colors ${
        scrolled
          ? "border-b bg-background/80 backdrop-blur-md"
          : "border-b border-transparent"
      }`}
    >
      {/*
        Two things here are load-bearing on a phone, and both were learned by
        measuring rather than looking. Adding the Builder and Data links pushed
        this row 39px past a 390px viewport, which widened the *document* — so
        every page silently lost its right edge, body copy included, while the
        nav itself still looked fine.

        `min-w-0` lets the link row shrink below its content width, and
        `overflow-x-auto` gives it somewhere to put the excess. Together they
        mean a sixth link degrades to a scroll instead of clipping the page.
        The tighter mobile padding is what makes all five fit today.

        The search button sits OUTSIDE the scrolling row, beside the logo,
        for two reasons that are both about the phone. It must never be the
        thing that scrolls off -- it is the header affordance #18 traded two
        nav slots for. And its thumb target is a pseudo-element grown past
        its 32px box to 44px: inside an `overflow-x-auto` row that overhang
        would become a vertical scrollbar, and outside it it costs the row no
        height, so the header stays exactly as tall as it was (69px, 68 of
        nav and 1 of border) and the sticky filter bar the list screens hang
        under it is not moved.

        Measured 2026-09-02 over CDP at 390px (the #18 build, four links):
        with the six-link row's spacing kept, the four links ended at x=356
        inside a row whose right edge was 374 -- but the theme toggle at the
        row's end ran to 398, so the row still scrolled by 24px and the one
        control past the edge was the toggle. Every base-width gap below is
        the tight one for that reason (`px-1.5`, `gap-0`, `ml-0.5`, a 32px
        search tile), widening at `sm:` back to what it was. After:
        scrollWidth equal to clientWidth with 10px to spare, and nothing past
        the edge. The theme toggle keeps its 36px: it is the tallest thing in
        the row, so shrinking it would have moved the header's height, and
        the fit did not need it. At 320px the row still scrolls -- "Your
        bets" is cut and the toggle is off -- which the ticket asked to have
        measured rather than promised; it is recorded here and not fixed here.
      */}
      <nav
        className={`${SHELL_WIDTH} flex items-center justify-between gap-1.5 px-4 py-4 sm:gap-2 sm:px-6 xl:px-8`}
      >
        <div className="flex shrink-0 items-center gap-1.5 sm:gap-3">
          <Link href="/" className="flex shrink-0 items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent-fill text-sm font-bold text-white">
              K
            </span>
            <span className="hidden text-sm font-semibold tracking-tight sm:inline">
              Cockpit
            </span>
          </Link>
          <button
            type="button"
            onClick={() => setSearchOpen((open) => !open)}
            aria-label="Search markets"
            aria-expanded={searchOpen}
            aria-controls="market-search-panel"
            className={`relative grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-colors before:absolute before:-inset-1.5 before:content-[''] hover:bg-accent-soft hover:text-foreground ${
              searchOpen ? "bg-accent-soft text-foreground" : "text-muted"
            }`}
          >
            <svg
              aria-hidden
              viewBox="0 0 20 20"
              className="h-4 w-4"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <circle cx="8.5" cy="8.5" r="5.5" />
              <path d="M13 13l4.5 4.5" />
            </svg>
          </button>
        </div>

        {/* State, not navigation, and muted ink at every state on purpose:
            "open" means the recorder's prices are fresh, never that there is
            something to bet, and a green chip here would read as permission.
            Hidden below xl — the phone's four-link budget is not renegotiated
            by a desktop feature. See lib/windowChip.ts. */}
        {chip !== null && (
          <span className="hidden shrink-0 items-center gap-2 font-mono text-xs text-muted xl:flex">
            <span
              aria-hidden
              className={`inline-block h-2 w-2 rounded-full ${
                chip.state === "open" ? "bg-current" : "border border-current"
              }`}
            />
            {chip.label}
          </span>
        )}

        <div className="flex min-w-0 items-center gap-0 overflow-x-auto sm:gap-1">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              aria-current={lights(link.href, pathname) ? "page" : undefined}
              className={`shrink-0 rounded-full px-1.5 py-1.5 text-sm transition-colors hover:bg-accent-soft hover:text-foreground sm:px-3 ${
                lights(link.href, pathname) ? "text-foreground" : "text-muted"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <div className="ml-0.5 shrink-0 sm:ml-2">
            <ThemeToggle />
          </div>
        </div>
      </nav>
      {/* The panel hangs off the header's bottom edge as a layer, so opening
          it changes nothing about the header's own height. Its own opaque
          background matters: the header is transparent until the page is
          scrolled, and a translucent panel over a slate row would be prices
          showing through a search box. */}
      {searchOpen && (
        <div
          id="market-search-panel"
          className="absolute inset-x-0 top-full max-h-[75vh] overflow-y-auto border-b bg-background"
        >
          <div className={`${SHELL_WIDTH} px-4 pb-4 sm:px-6 xl:px-8`}>
            <MarketSearch open heading="Search the venue" />
          </div>
        </div>
      )}
    </header>
  );
}
