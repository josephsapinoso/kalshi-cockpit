import Link from "next/link";
import { SHELL_WIDTH } from "@/lib/shell";

/**
 * The screens the nav budget could not afford, and what each is for.
 *
 * **This is not a nav overflow menu and must not become one.** `Nav.tsx` opens
 * by stating that six links is a budget rather than a coincidence: a seventh
 * pushes the Gate — the screen that says whether money can move — off the row
 * at 390px. Two pages lost that trade on their merits, and both losses are
 * recorded there:
 *
 * - **`/builder`** prices sportsbook parlays. It cannot change a bet on this
 *   venue, and for a beginner it can change one in the wrong direction.
 * - **`/rejections`** aggregates the suppression codes, and Slate is a strict
 *   superset of it — every row now carries its own reason. The aggregate is
 *   still the fastest read when a single rule is refusing everything.
 *
 * **What this fixes is a smaller and more embarrassing thing.** That comment
 * says twice that the pages are "still served for anyone who wants it", and
 * until now there was **no inbound link anywhere in the application** — not in
 * the nav, not contextually, not here. The escape hatch it named did not
 * exist. This tool is operated from a phone, where "type the URL" is not a
 * route a real person takes, so a served page with no link is unreachable in
 * practice however true it is that the server answers.
 *
 * So: the footer is where a screen goes when it is worth keeping and not worth
 * a nav slot. **A page that is not worth either belongs in a delete commit**,
 * and moving one here to avoid making that call is the failure mode to watch
 * for. Neither of these two is that: one is the fastest diagnostic on the
 * system and the other is a deliberate "don't" calculator.
 */
// **The 2026-08-22 every-page review emptied most of this list, on Joe's
// approval, and each exit is a decision rather than a tidy-up:**
//
// - **`/bets` moved UP, into the nav** (Scout's slot; see `Nav.tsx`). A
//   betting desk's own record outranks every diagnostic here.
// - **`/builder` is DELETED** — the delete commit this file's docstring
//   said such a page belongs in. Its red "Price it" was the brightest CTA
//   in the cockpit and it priced sportsbook parlays — the highest-hold
//   product any book sells — for a novice, off-platform and uncapped.
// - **`/rejections` is DELETED and folded into the Slate** — the Slate was
//   already a strict superset per-row; it now carries the per-code counts
//   as a disclosure, so the aggregate lives beside the rows it aggregates.
// - **`/dashboards` lost this slot** (Joe approved). It is a dev screen:
//   on the deployed box its only state is a 503 whose remedy is two shell
//   commands. Still served for the developer who just ran dbt; reachable
//   by URL and recorded as exempt in `test_every_screen_is_reachable.py`.
// - **`/slate` lost this slot** — a byte-identical re-export of `/`,
//   kept served for bookmarks; a link to the page you are on is furniture.
const SECONDARY = [
  {
    // The stopped study's record (Amendment 2, stopped without result).
    // The FORM retired 2026-08-22 (ADR 0065): a typed P(YES) becomes the
    // manual ticket's first field, where it has a consumer (bet_clv).
    // This page keeps the entries already logged and their revision flags.
    href: "/estimate",
    label: "Estimates",
    blurb:
      "The stopped study's record of typed P(YES) numbers. The form is retired — the ticket asks instead.",
  },
];

export default function Footer() {
  return (
    <footer className="mt-16 border-t">
      <div className={`${SHELL_WIDTH} px-5 py-8 xl:px-8`}>
        <h2 className="text-xs font-semibold uppercase tracking-wide text-muted">
          Also served
        </h2>
        <ul className="mt-3 space-y-2">
          {SECONDARY.map((link) => (
            <li key={link.href}>
              <Link
                href={link.href}
                className="text-sm font-semibold text-accent hover:underline"
              >
                {link.label}
              </Link>
              {/* The blurb is the point, not decoration. A bare link named
                  "Builder" invites a beginner to open a parlay calculator
                  expecting a Kalshi feature; saying what it does and that the
                  answer is usually "don't" is the whole reason it lost its nav
                  slot rather than being deleted. */}
              <span className="ml-2 text-sm text-muted">{link.blurb}</span>
            </li>
          ))}
        </ul>
      </div>
    </footer>
  );
}
