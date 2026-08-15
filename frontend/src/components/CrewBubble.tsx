"use client";

import { useState } from "react";
import type { SlateRowData } from "@/lib/api";

/**
 * The dispatch bubble: a crew portrait and what that member actually found.
 *
 * **The crew is this repo's own, and it is fictional on purpose.** Joe asked
 * for Billy Walters and his team. `.claude/agents/sharp-bettor.md` is explicit
 * that the persona "does not speak as any of them, does not put invented quotes
 * in a real person's mouth"; Walters is a living person and a portrait of him
 * saying something he never said is not a thing this product ships. The house
 * crew already exists in `backend/agents/` — the Skeptic, the Scout, the
 * Historian — and they are the ones on screen.
 *
 * **Every line is derived from the row, never written for flavour.** A bubble
 * that invented plausible-sounding commentary would be an unfalsifiable opinion
 * rendered in the same weight as measured numbers, which is exactly what the
 * agents package refuses to do: "anything producing a number is deterministic
 * code; LLM agents do research, triage and learning." So the Skeptic reads back
 * the suppression codes the server computed, and the Scout reports that it has
 * not looked — because it has not.
 *
 * **Silence and a disconnected wire are different states.** The Scout is
 * quarantined by ADR 0022 and has never been called by anything that runs. Its
 * line therefore says so, rather than rendering an empty findings list that
 * would read as "nothing to report".
 *
 * Hover is desktop-only by nature, so nothing here may be the sole route to
 * information: every fact in the bubble is also a column on the row.
 */

type CrewMember = {
  name: string;
  /** Monogram rather than an image: no asset pipeline, no likeness. */
  initial: string;
  role: string;
  className: string;
};

const SKEPTIC: CrewMember = {
  name: "The Skeptic",
  initial: "S",
  role: "argues a flagged edge is a bug",
  className: "bg-accent-soft text-accent border-accent/40",
};

const SCOUT: CrewMember = {
  name: "The Scout",
  initial: "R",
  role: "injuries, lineups, weather, travel",
  className: "border-border bg-card text-muted",
};

/**
 * What the Skeptic can say about this row, from what the server computed.
 *
 * The suppression codes are shown verbatim, as they are everywhere else in this
 * product: translating them here would give one rule two names, and the codes
 * are what `/api/suppression` counts.
 */
function skepticLine(row: SlateRowData): string {
  if (row.suppressed_reason) {
    return `I refused this one: ${row.suppressed_reason}.`;
  }
  if (row.suggested_contracts > 0) {
    return "Nothing of mine refused this row. That is not the same as my liking it.";
  }
  return "No rule refused this row. There was also no edge left after fees.";
}

/**
 * The Scout's line, which is an admission rather than a report.
 *
 * `backend/agents/scout.py` researches exactly the things Joe asked for and is
 * called by nothing — ADR 0022 quarantines it, and `tests/test_has_callers.py`
 * turns red if anything wires it up without the spend being budgeted first.
 */
function scoutLine(): string {
  return "I have not looked at this game. I am not switched on yet — nobody has budgeted the calls.";
}

export default function CrewBubble({ row }: { row: SlateRowData }) {
  const [open, setOpen] = useState(false);

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      /* Focus as well as hover: a keyboard user gets the same bubble, and a
         touch user gets the columns on the row itself. */
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-label="What the desk found"
        className="rounded-full border border-border px-2 py-0.5 font-mono text-[0.65rem] text-muted transition-colors hover:border-accent/50 hover:text-accent"
      >
        desk
      </button>

      {open && (
        <span
          role="tooltip"
          /* `right-0` and a max width so a bubble on the last column cannot
             push the document wider than the viewport — the failure
             `scripts/check_mobile.py` exists to catch, and the one the nav
             already produced once. */
          className="absolute right-0 top-full z-20 mt-2 w-[min(22rem,80vw)] rounded-lg border border-border bg-card p-3 text-left shadow-lg"
        >
          {[
            { who: SKEPTIC, says: skepticLine(row) },
            { who: SCOUT, says: scoutLine() },
          ].map(({ who, says }) => (
            <span key={who.name} className="mb-3 flex gap-2 last:mb-0">
              <span
                aria-hidden
                className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border font-mono text-xs font-bold ${who.className}`}
              >
                {who.initial}
              </span>
              <span className="min-w-0">
                <span className="block text-xs font-semibold tracking-tight">
                  {who.name}
                  <span className="ml-1 font-normal text-muted">
                    — {who.role}
                  </span>
                </span>
                <span className="block text-xs leading-snug text-muted">
                  {says}
                </span>
              </span>
            </span>
          ))}
          <span className="mt-2 block border-t border-border pt-2 font-mono text-[0.6rem] uppercase tracking-widest text-muted">
            House crew. Not real people, and no forecast.
          </span>
        </span>
      )}
    </span>
  );
}
