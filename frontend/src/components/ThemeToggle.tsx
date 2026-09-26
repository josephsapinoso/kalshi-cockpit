"use client";

import { useEffect, useState } from "react";

import { applyThemeColor } from "@/lib/theme";

/**
 * Two-state theme control, persisted to localStorage. Dark unless the reader
 * chose light: the HUD (2026-09-26) is a dark design, and it no longer
 * follows the system.
 *
 * The icon renders `null` until mounted so the server and client markup match
 * -- reading localStorage during render would produce a hydration mismatch.
 */
export default function ThemeToggle() {
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | null>(null);

  useEffect(() => {
    setMounted(true);
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || stored === "light") setTheme(stored);
  }, []);

  function toggle() {
    const current = theme ?? "dark";
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
    document.documentElement.dataset.theme = next;
    // The status bar of an installed app, and the browser chrome tint
    // elsewhere. The `<meta name="theme-color">` pair in `app/layout.tsx` is
    // keyed on `prefers-color-scheme`, which cannot see a forced theme, so a
    // toggle that skipped this would leave a black bar over a cream page.
    applyThemeColor(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle colour theme"
      className="grid h-9 w-9 place-items-center rounded-full border text-muted transition-colors hover:bg-accent-soft hover:text-foreground"
    >
      {mounted ? (theme === "light" ? "☾" : "☀") : null}
    </button>
  );
}
