"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "./ThemeToggle";
import { SHELL_WIDTH } from "@/lib/shell";
import { fetchWindow, recordAttention } from "@/lib/api";
import { windowChip } from "@/lib/windowChip";
import type { Chip } from "@/lib/windowChip";

// Six links, and the count is a budget rather than a coincidence. A seventh
// does not clip the page -- the row scrolls, which is what `min-w-0
// overflow-x-auto` below is for -- but it does push the last item out of sight,
// and the Gate is the screen that says whether money can move. So adding one
// means removing one.
//
// Rejections took Builder's slot. Builder prices sportsbook parlays: it cannot
// change a bet on this venue, and for a beginner it can change one in the wrong
// direction. Rejections answers "which check is refusing everything", which on
// a board showing 0 actionable of ~200 is the only question there is. The page
// is still served at `/builder` for anyone who wants it.
//
// **Slate then took Rejections' slot, 2026-08-15, and the trade is the same
// shape.** Rejections aggregates the suppression codes across the slate; Slate
// shows every row with its own reason attached, beside the factors the record
// already holds and had never rendered. The aggregate is a strict summary of
// what the per-row screen now shows, so keeping both would spend a link on a
// projection of the other. `/rejections` is still served, exactly as
// `/builder` is, and its counts are still the fastest read when one rule is
// refusing everything.
// **Log then took Data's slot, 2026-08-18, same trade again.** The calibration
// study (registration 2026-08-17) makes logging an estimate the one action
// performed before every hand bet, on a phone, on a clock -- the flow is
// budgeted at twelve seconds and a link that must be hunted for blows the
// budget. Data renders dbt marts that are read weekly at most, and
// `/dashboards` is still served, exactly as `/builder` and `/rejections` are.
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
// terminal state at the top -- exactly as `/builder`, `/rejections` and
// `/dashboards` are.
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
// heading move, the same pattern `/board` follows under "Picks".
// **Parlays takes Evidence's slot, 2026-08-24** (Joe asked to promote the
// parlay link and demote whatever is not day-to-day). Same trade shape as
// every swap above: the Parlay desk is a screen bets are placed from --
// three daily cards, opened daily -- while Evidence is the engine's record,
// read for analysis at most weekly. Gate keeps its slot (it is the money
// interlock, the reason the budget is six), and Playbook stays the link
// that scrolls at 390px. `/ledger` moves to the footer, exactly as
// `/estimate` did -- served, linked, and one tap further away.
const LINKS = [
  { href: "/", label: "Games" },
  { href: "/board", label: "Picks" },
  { href: "/parlays", label: "Parlays" },
  { href: "/bets", label: "Your bets" },
  // Gate before Playbook, and the order is load-bearing at 390px: the newest
  // and least urgent page is the one that scrolls off.
  { href: "/gate", label: "Gate" },
  { href: "/playbook", label: "Playbook" },
];

export default function Nav() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  // The window chip's fact, fetched on mount and once a minute after. `null`
  // renders nothing at all: an unreachable timetable must not put a state
  // claim in the chrome of every page. Only xl viewports render the chip, but
  // the fetch is cheap and gating it on a media query would put layout state
  // into data state.
  const [chip, setChip] = useState<Chip | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fetchWindow()
        .then((w) => {
          if (!cancelled) setChip(windowChip(w));
        })
        .catch(() => {
          if (!cancelled) setChip(null);
        });
    load();
    const timer = setInterval(load, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
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
    const timer = setInterval(beat, 60_000);
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
      */}
      <nav
        className={`${SHELL_WIDTH} flex items-center justify-between gap-2 px-4 py-4 sm:px-6 xl:px-8`}
      >
        <Link href="/" className="flex shrink-0 items-center gap-3">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent-fill text-sm font-bold text-white">
            K
          </span>
          <span className="hidden text-sm font-semibold tracking-tight sm:inline">
            Cockpit
          </span>
        </Link>

        {/* State, not navigation, and muted ink at every state on purpose:
            "open" means the recorder's prices are fresh, never that there is
            something to bet, and a green chip here would read as permission.
            Hidden below xl — the phone's six-link budget is not renegotiated
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

        <div className="flex min-w-0 items-center gap-0.5 overflow-x-auto sm:gap-1">
          {LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`shrink-0 rounded-full px-2 py-1.5 text-sm transition-colors hover:bg-accent-soft hover:text-foreground sm:px-3 ${
                pathname === link.href ? "text-foreground" : "text-muted"
              }`}
            >
              {link.label}
            </Link>
          ))}
          <div className="ml-1 shrink-0 sm:ml-2">
            <ThemeToggle />
          </div>
        </div>
      </nav>
    </header>
  );
}
