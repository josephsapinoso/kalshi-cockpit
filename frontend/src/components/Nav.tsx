"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "./ThemeToggle";
import { SHELL_WIDTH } from "@/lib/shell";
import { fetchWindow } from "@/lib/api";
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
const LINKS = [
  { href: "/", label: "Board" },
  { href: "/slate", label: "Slate" },
  { href: "/estimate", label: "Log" },
  { href: "/ledger", label: "Ledger" },
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
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-white">
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
