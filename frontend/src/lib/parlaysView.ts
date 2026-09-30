/**
 * The three sections of `/parlays`, one at a time (#221).
 *
 * Joe uses the desk from a phone and said the page made him scroll a lot: a
 * check box, a list of game-script cards and six parlay cards, stacked. The
 * page now draws ONE of them, chosen by `?view=`, so every section is still
 * a link and a reload keeps it.
 *
 * **The default is `scripts`.** An address with no `view`, or one this file
 * does not know, is the game-script list: an unknown value falls back rather
 * than drawing an empty page.
 *
 * **The cut survives the switch.** `league`, `within_hours` and `horizon` are
 * carried on every link, so choosing another section and coming back never
 * clears a filter set a moment ago (the same rule `WindowPicker` keeps).
 */

export type ParlaysView = "scripts" | "cards" | "check";

export const DEFAULT_PARLAYS_VIEW: ParlaysView = "scripts";

//: One per line so the test can read them. The order is the switch's order.
export const PARLAYS_VIEWS: readonly { key: ParlaysView; label: string }[] = [
  { key: "scripts", label: "Game scripts" },
  { key: "cards", label: "Parlay cards" },
  { key: "check", label: "Check a parlay" },
];

/** The selected section from a page's `searchParams`. Unknown means default. */
export function readParlaysView(raw: string | string[] | undefined): ParlaysView {
  const first = Array.isArray(raw) ? raw[0] : raw;
  const hit = PARLAYS_VIEWS.find((v) => v.key === first);
  return hit ? hit.key : DEFAULT_PARLAYS_VIEW;
}

/** Query params carried across a view switch. */
const KEPT_PARAMS = ["league", "within_hours", "horizon"] as const;

/** `/parlays?view=...` plus whichever cut params are in the address. */
export function parlaysViewHref(
  view: ParlaysView,
  params: Partial<Record<(typeof KEPT_PARAMS)[number], string | string[]>>,
): string {
  const qs = new URLSearchParams();
  qs.set("view", view);
  for (const key of KEPT_PARAMS) {
    const raw = params[key];
    const first = Array.isArray(raw) ? raw[0] : raw;
    if (first !== undefined) qs.set(key, first);
  }
  return `/parlays?${qs.toString()}`;
}

/** Append `keep` (e.g. `view=cards`) to a link that already has, or lacks, a
 * query string. Used by the pickers that live inside one view, so a chip tap
 * stays in that view. */
export function withKept(href: string, keep: string | null | undefined): string {
  if (!keep) return href;
  return `${href}${href.includes("?") ? "&" : "?"}${keep}`;
}
