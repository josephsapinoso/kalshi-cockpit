import Link from "next/link";

import type { ListFilter, ParlayWindow } from "@/lib/api";
import { listFilterQuery } from "@/lib/api";

/**
 * Which kickoff window the parlay cards are built from (2026-09-06).
 *
 * **Why this exists.** On the evening of 2026-09-06 the live desk held one
 * fixture and every card read "needs 2 fresh games and the slate has 1",
 * while eight Monday fixtures sat in the database carrying 12–31 books of
 * fresh consensus each. The bound was Joe's own rule — parlays should finish
 * out with the evening games — and it is still the default. What changed is
 * that at 8pm on a Sunday that rule makes the screen structurally empty, and
 * a screen that is always empty in the evening is one nobody opens in the
 * evening. He asked for the window to become a control.
 *
 * **Links, not a client control.** The page is a server component and the
 * window is a server decision; a `Link` puts the choice in the URL, which
 * means it survives a reload, can be bookmarked, and needs no client state.
 * Same mechanism as `FilterBar`, deliberately — two pickers on one screen
 * behaving differently is a thing the reader has to learn twice.
 *
 * **The words are the server's.** `choices` and the active `words` come off
 * the payload, so the list of windows exists in exactly one place. A
 * hardcoded copy here is the one that goes stale when a window is added, and
 * it would go stale silently: the buttons would still render.
 *
 * **It renders nothing when the server sent no echo.** An older backend, or
 * a cached payload from before this shipped, has no `window` key — and a
 * picker that cannot say which window is active is worse than no picker,
 * because every option looks equally unselected.
 */
export default function WindowPicker({
  window,
  filter,
  pathname = "/parlays",
}: {
  window: ParlayWindow | undefined;
  filter: ListFilter;
  pathname?: string;
}) {
  if (!window || window.choices.length < 2) return null;

  // The league/kickoff cut has to survive the window change, or picking a
  // window silently clears a filter the reader set a moment ago.
  const cut = listFilterQuery(filter);
  const href = (key: string) =>
    cut ? `${pathname}${cut}&horizon=${key}` : `${pathname}?horizon=${key}`;

  return (
    <nav aria-label="Kickoff window" className="mt-4">
      <div className="flex flex-wrap gap-2">
        {window.choices.map((choice) => {
          const active = choice.key === window.key;
          return (
            <Link
              key={choice.key}
              href={href(choice.key)}
              aria-current={active ? "true" : undefined}
              className={`min-h-11 rounded border px-3 py-2 text-sm font-semibold ${
                active
                  ? "border-foreground text-foreground"
                  : "border-border text-muted"
              }`}
            >
              {LABELS[choice.key] ?? choice.key}
            </Link>
          );
        })}
      </div>
      {/*
        The server's own sentence for the ACTIVE window, under the buttons.
        The button labels are short enough to be ambiguous on their own —
        "Through tomorrow" does not say whether it includes tonight — and
        this is the line that resolves it, in the words the payload supplied.

        **When the window is not tonight it also corrects the lede above
        it.** That lede is ratified copy and says "cut from tonight's games";
        rewording it to match a control would be editing Joe's approved
        sentence as a side effect of shipping a feature, which
        `tests/test_tab_ledes.py` exists to prevent. So the page does the
        other honest thing: it leaves the sentence alone and says plainly,
        immediately above the cards, that a wider window is in force.
      */}
      <p className="mt-2 text-xs leading-snug text-muted">
        {window.key !== "tonight" && (
          <span className="font-semibold text-foreground">
            Wider than tonight —{" "}
          </span>
        )}
        {window.words}.
      </p>
      {/*
        **The desk chose this window, and says so.** `widened_words` is
        present only when the reader named no window and `tonight` built
        nothing at all — measured on live 2026-09-10, where the tonight pool
        held one game and all seven cards refused while the same slate built
        six one day out. Without this line the reader sees tomorrow's cards
        under a window he did not pick and has no way to tell.

        It carries the settlement caveat rather than only the window change,
        because Joe's rule was never about the window: it was "I'd want to
        see my parlays finish out by the time the evening games end". The
        server owns the sentence; rewording it here would put the caveat in
        two places, and only one of them would get corrected.
      */}
      {window.widened_words && (
        <p className="mt-2 rounded border border-border px-3 py-2 text-xs leading-snug text-muted">
          <span className="font-semibold text-foreground">
            Nothing tonight —{" "}
          </span>
          {window.widened_words}
        </p>
      )}
    </nav>
  );
}

/**
 * Short button text per window key. Not the source of truth for WHICH
 * windows exist — that is the payload's `choices` — only for how a known key
 * is abbreviated on a 390px screen, where the server's full sentence does
 * not fit on a button. An unknown key falls through to the key itself, which
 * is ugly and visible rather than absent and silent.
 */
const LABELS: Record<string, string> = {
  tonight: "Tonight",
  tomorrow: "Through tomorrow",
  "48h": "Next two nights",
};
