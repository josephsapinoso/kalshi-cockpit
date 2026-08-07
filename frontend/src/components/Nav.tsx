"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import ThemeToggle from "./ThemeToggle";

const LINKS = [
  { href: "/", label: "Board" },
  { href: "/builder", label: "Builder" },
  { href: "/dashboards", label: "Data" },
  { href: "/ledger", label: "Ledger" },
  { href: "/gate", label: "Gate" },
];

export default function Nav() {
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);

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
      <nav className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-4 sm:px-6">
        <Link href="/" className="flex shrink-0 items-center gap-3">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-sm font-bold text-white">
            K
          </span>
          <span className="hidden text-sm font-semibold tracking-tight sm:inline">
            Cockpit
          </span>
        </Link>

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
