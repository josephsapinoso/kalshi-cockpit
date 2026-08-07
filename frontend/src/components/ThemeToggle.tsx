"use client";

import { useEffect, useState } from "react";

/**
 * Three-state theme control, matching the personal site: follow system by
 * default, with an explicit override persisted to localStorage.
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
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const current = theme ?? (prefersDark ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    setTheme(next);
    localStorage.setItem("theme", next);
    document.documentElement.dataset.theme = next;
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Toggle colour theme"
      className="grid h-9 w-9 place-items-center rounded-full border text-muted transition-colors hover:bg-accent-soft hover:text-foreground"
    >
      {mounted ? (theme === "dark" ? "☀" : "☾") : null}
    </button>
  );
}
