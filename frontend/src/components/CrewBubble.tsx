"use client";

import { useState } from "react";
import CrewAvatar, { type CrewFace } from "@/components/CrewAvatar";
import type { BookDistribution, SlateRowData } from "@/lib/api";

/**
 * The dispatch bubble: a crew portrait and what that member actually found.
 *
 * **The crew is this repo's own, and it is fictional on purpose.** Joe asked
 * for Billy Walters and his team. `.claude/agents/sharp-bettor.md` is explicit
 * that the persona "does not speak as any of them, does not put invented quotes
 * in a real person's mouth"; Walters is a living person and a portrait of him
 * saying something he never said is not a thing this product ships. **Willy
 * Balters is a fiction with a fiction's name** — Joe's own suggestion, and it
 * is the whole reason he can be on screen at all. The rest of the house crew
 * already exists in `backend/agents/` — the Skeptic, the Scout.
 *
 * **These personas are code, not agents, and that distinction is the point.**
 * Every line below is a pure function of the row: no network call, no model,
 * no Anthropic spend, nothing running on the Kalshi box. The `backend/agents/`
 * modules of the same names are a different thing entirely — they cost money
 * because they fetch and reason about facts the record does not hold (a
 * scratched pitcher, a lineup, weather). **A code persona can voice any fact
 * already on the row, forever, for nothing. It cannot produce a new one.**
 * That boundary is why the Scout's line is an admission rather than a report.
 *
 * **Every line is derived from the row, never written for flavour.** A bubble
 * that invented plausible-sounding commentary would be an unfalsifiable opinion
 * rendered in the same weight as measured numbers, which is exactly what the
 * agents package refuses to do: "anything producing a number is deterministic
 * code; LLM agents do research, triage and learning."
 *
 * **One voice, one data source — and that is a structural guarantee, not a
 * style.** The Skeptic reads suppression codes and nothing else. Willy reads
 * the book distribution and nothing else. The Scout reads nothing at all and
 * says so. Because no line may combine two factors, **no line can become a
 * composite** — which is the prohibition `test_slate.py` and `test_api.py`
 * enforce on the payload, held here by construction rather than by a checker.
 * The moment a persona weighs drift *against* book position, it is a rating
 * and it needs its own ADR (ADR 0021 §9).
 *
 * **Willy exists because the Skeptic was the only voice, and his job is to
 * refuse.** Joe: *"all I see is the Skeptic and he denies everything."* That
 * was a real gap rather than a mood — the row already carried the book
 * distribution and nobody spoke for it. Willy is not a counter-opinion; he is
 * the other half of the record being read aloud.
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
  face: CrewFace;
  role: string;
  className: string;
};

const SKEPTIC: CrewMember = {
  name: "The Skeptic",
  face: "skeptic",
  role: "argues a flagged edge is a bug",
  className: "bg-accent-soft text-accent border-accent/40",
};

const WILLY: CrewMember = {
  name: "Willy Balters",
  face: "willy",
  role: "reads the book distribution",
  className: "border-border border-edge bg-card text-foreground",
};

const SCOUT: CrewMember = {
  name: "The Scout",
  face: "scout",
  role: "injuries, lineups, weather, travel",
  className: "border-border border-edge bg-card text-muted",
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
 * Willy's line, read off the book distribution and nothing else.
 *
 * **`books_below` counts books priced BELOW Kalshi's ask**, so a low count
 * means Kalshi is cheap against the books and a high one means it is dear.
 * Getting that direction backwards would produce an entirely plausible
 * sentence pointing the wrong way, which is the failure mode
 * `runner.py`'s "Kalshi YES is Over" comment exists to prevent on the prop
 * join — same shape, same care.
 *
 * **He never says the books are right.** The Slate's distribution is
 * deliberately unanchored: it is built from per-book devigged fair values with
 * no sharp preference applied, whatever the books happen to be. A gap against
 * that consensus is a gap, not an edge, and his last clause says so rather
 * than leaving the reader to supply it.
 *
 * **His wording is deliberately about anchoring inside THIS distribution, not
 * about the books being soft**, and that distinction was nearly got wrong. An
 * earlier draft of this comment said props carry no sharp book at all. On the
 * live record they do — `pinnacle` is there, and it is in `SHARP_BOOKS`. The
 * claim came from a probe that requested `regions: "us"` while the deployed
 * system runs `us,eu`, and Pinnacle is EU-only. Willy's line does not depend
 * on which books they are, which is why it needed no change.
 *
 * **`null` is not zero, in three separate places.** No distribution at all, a
 * distribution over too few books to be one, and a `percentile` that could not
 * be computed are three different states and get three different sentences.
 */
function willyLine(books: BookDistribution | null): string {
  if (!books) {
    return "No book distribution on this row. I have nothing to read, which is not the same as reading nothing.";
  }
  const { book_count: count, books_below: below, books_unusable: unusable } = books;
  const dropped =
    unusable > 0 ? ` ${unusable} more were dropped before the devig.` : "";

  if (count < 2) {
    return `One usable book.${dropped} That is a price, not a market — I do not read a distribution off a single quote.`;
  }
  if (books.percentile === null) {
    return `Not one of the ${count} usable books prices this below Kalshi's ask.${dropped} None of them is anchored sharp, so read it as agreement, not as confirmation.`;
  }

  const pct = Math.round(books.percentile * 100);
  const where =
    pct <= 25
      ? `Only ${below} of ${count} usable books price this below Kalshi's ask — you would be paying under most of the market's number`
      : pct >= 75
        ? `${below} of ${count} usable books price this below Kalshi's ask — you would be paying over most of the market's number`
        : `Kalshi's ask sits mid-pack: ${below} of ${count} usable books below it`;

  return `${where} (${pct}th percentile).${dropped} None of these books is anchored sharp, so this is where the soft market sits, not where the truth is.`;
}

/**
 * The Scout's line, which is an admission rather than a report.
 *
 * Since ADR 0060 the Scout runs a desk — two staff scouts and a master,
 * metered, sent on demand from the Market screen. This bubble is still a code
 * persona with no network and no data, so its line stays an admission: the
 * desk has not looked *from here*, and the place its work actually appears is
 * named instead of imitated. Rendering a stored briefing in the bubble would
 * break the one-voice-one-data-source rule this component is built on.
 *
 * Takes no argument, deliberately: a Scout line that read the row could drift
 * into inventing context from a price, which is the one thing a scout must not
 * do.
 */
function scoutLine(): string {
  return "I have not looked at this game from here. Open its market screen and send my desk — my staff and I file there.";
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
          className="absolute right-0 top-full z-20 mt-2 w-[min(22rem,80vw)] rounded-lg border border-border border-edge bg-card p-3 text-left shadow-lg"
        >
          {[
            { who: SKEPTIC, says: skepticLine(row) },
            { who: WILLY, says: willyLine(row.books) },
            { who: SCOUT, says: scoutLine() },
          ].map(({ who, says }) => (
            <span key={who.name} className="mb-3 flex gap-2 last:mb-0">
              <span
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border ${who.className}`}
              >
                <CrewAvatar kind={who.face} className="h-5 w-5" />
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
