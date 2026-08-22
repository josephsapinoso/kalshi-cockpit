"use client";

/**
 * A word that explains itself when tapped.
 *
 * Phone-first, which rules hover out: the term renders with a dotted
 * underline, a tap opens a small definition card, and a tap anywhere else —
 * or Escape — closes it. Definitions live in `lib/glossary.ts` only, so one
 * word never accumulates two explanations.
 *
 * **A span with a button role, not a real `<button>`, and that is
 * load-bearing.** On the Board every offerable card is wrapped in
 * `TicketTrigger`, which IS a `<button>`; a nested button is invalid HTML
 * and hydrates unpredictably. The span form is valid anywhere text is, and
 * `stopPropagation` on the tap keeps "explain this word" from also opening
 * a ticket — a definition must never be one bubble away from a money sheet.
 * Keyboard: Enter and Space toggle, matching real button semantics.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

import { GLOSSARY, type GlossaryKey } from "@/lib/glossary";

export default function Term({
  k,
  children,
}: {
  k: GlossaryKey;
  /** Optional display text; defaults to the glossary label. */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const entry = GLOSSARY[k];

  useEffect(() => {
    if (!open) return;
    // Capture phase, and the dismissing tap is SWALLOWED. Without both, a
    // tap that closes the popover falls through to whatever sits under it --
    // on the Board that is TicketTrigger, so "stop explaining a word" opened
    // a money sheet. Closing must consume the tap entirely.
    const away = (event: MouseEvent | PointerEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) {
        setOpen(false);
        event.stopPropagation();
        event.preventDefault();
      }
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", away, true);
    document.addEventListener("click", away, true);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("pointerdown", away, true);
      document.removeEventListener("click", away, true);
      document.removeEventListener("keydown", key);
    };
  }, [open]);

  return (
    <span
      ref={root}
      className="relative inline-block"
      // preventDefault as well as stopPropagation: inside a <Link> row
      // (/bets since 2026-08-22) the anchor's default navigation fires on
      // any child click regardless of bubbling — "explain CLV" must not
      // also open the market screen.
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <span
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen((v) => !v);
          }
        }}
        className="cursor-help border-b border-dotted border-current"
      >
        {children ?? entry.label}
      </span>
      {open && (
        <span
          role="tooltip"
          // `left-1/2 -translate-x-1/2` centres the card on the term, and the
          // max-width keeps it inside a 390px viewport; `normal-case` and
          // `font-normal` undo any uppercase label styling it sits inside.
          className="absolute bottom-full left-1/2 z-40 mb-2 block w-64 max-w-[80vw] -translate-x-1/2 rounded-xl border bg-card p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
        >
          <span className="mb-1 block font-semibold">{entry.label}</span>
          {entry.definition}
        </span>
      )}
    </span>
  );
}
