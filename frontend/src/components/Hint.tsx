"use client";

/**
 * A fact chip that explains itself when tapped — `Term`'s machinery for
 * text that is NOT a glossary word.
 *
 * The slate's columns and the signal strip carried their caveats in `title=`
 * attributes, which a phone cannot open and a desktop only reveals to a
 * reader who thinks to hover (2026-08-22 review, A6 — `soft fallback` was
 * the sharpest case: the most consequential caveat in the product, invisible
 * on the device the account owner mostly uses). Hint renders the chip with
 * the same dotted-underline affordance as `Term`, opens the explanation on
 * tap or click, and keeps `title=` at the call sites so desktop hover still
 * works as a shortcut. Both platforms, one component.
 *
 * Definitions here are per-instance sentences (they interpolate the row's
 * own numbers), which is exactly what `lib/glossary.ts` must not hold — a
 * glossary entry is one fixed teaching sentence. A reusable TERM belongs in
 * the glossary; a row-specific CAVEAT belongs here.
 *
 * Same load-bearing shape as `Term`: a `span[role=button]` (valid inside
 * `TicketTrigger`'s real button), capture-phase swallow on the dismissing
 * tap, Enter/Space toggle, Escape closes.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";

export default function Hint({
  hint,
  children,
  className = "",
}: {
  /** The explanation the tap reveals — a sentence, not a label. */
  hint: string;
  children: ReactNode;
  /** Extra classes for the chip text itself (tone, size). */
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
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
      // preventDefault as well as stopPropagation — same reason as Term:
      // inside an anchor row, a tap on the hint must not also navigate.
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <span
        role="button"
        tabIndex={0}
        aria-expanded={open}
        title={hint}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen((v) => !v);
          }
        }}
        className={`cursor-help border-b border-dotted border-current ${className}`}
      >
        {children}
      </span>
      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-40 mb-2 block w-64 max-w-[80vw] -translate-x-1/2 rounded-xl border bg-card p-3 text-left text-xs font-normal normal-case leading-relaxed tracking-normal text-foreground shadow-lg"
        >
          {hint}
        </span>
      )}
    </span>
  );
}
