import Link from "next/link";
import { SHELL_WIDTH } from "@/lib/shell";

/**
 * The screens the nav budget could not afford, and what each is for.
 *
 * **READ THE COMMENT BELOW THIS DOCSTRING FIRST.** The two pages named here
 * were both DELETED in the 2026-08-22 review; this docstring describes the
 * footer as it was built and is kept for the reasoning, not the inventory.
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
 * said twice that the pages were "still served for anyone who wants it" (it
 * went on saying it after both were deleted, and was corrected 2026-08-29),
 * and until then there was **no inbound link anywhere in the application** — not in
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
    // manual ticket's first field, asked before the price is revealed and
    // required by the route. It is RECORDED there, not consumed -- this
    // comment claimed "where it has a consumer (bet_clv)" until 2026-08-29
    // and that was never true: nothing in the tree SELECTs `p_yes_bp`, and
    // `bet_clv` scores entry price against the closing mid without it.
    // This page keeps the entries already logged and their revision flags.
    href: "/estimate",
    label: "Estimates",
    blurb:
      "The stopped study's record of typed P(YES) numbers. The form is retired — the ticket asks instead.",
  },
  {
    // ADR 0078. Here rather than in the nav: it is empty until Joe has
    // recorded a ticket, and a nav slot is the six-link budget (ADR 0073).
    // Here rather than only linked from /bets, because `/bets` is where he
    // goes to READ what settled — a screen nobody can find is served and
    // unlinked, which the reachability test correctly calls the one option
    // that is not a decision.
    href: "/hedge",
    label: "Hedging",
    blurb:
      "Parlays you already hold, priced against what the other side costs on Kalshi right now. Says what a hedge locks in — never that you should take it.",
  },
  {
    // Demoted from the nav 2026-08-24 when the Parlay desk took its slot
    // (Joe's call: promote parlays, demote what is not day-to-day). This is
    // the engine's evidence base — every candidate row with its factors —
    // read when auditing the record, not when placing a bet.
    href: "/ledger",
    label: "Evidence",
    blurb:
      "Every candidate the engine has recorded, with its factors and suppression reason. The audit trail, not a betting screen.",
  },
  {
    // Demoted from the nav 2026-09-02 when the ranked list took the "Picks"
    // slot (#8, ratified by Joe 2026-08-27; the word is his, #29). This is
    // the engine's working kept in the open -- every candidate it priced in
    // its last half-hour, and what stopped each one -- consulted after a
    // question, not scanned nightly. The footer is the link, deliberately:
    // #8 struck the in-page link from the foot of Picks because every row
    // here carries a live hand-bet button, and a next-step affordance under
    // a favourites list is the chase shape. Its sibling above is the same
    // subject on the other clock: `/ledger` is the whole record, this is
    // one window anchored on the recorder's last pass.
    //
    // "The reason that stopped it -- a named check, or the fee bar": #9
    // wrote "the named rule" and recorded the caveat that only the rejected
    // bucket carries one. Measured on live 2026-09-02, 82 of 122 rows in the
    // window were refused by the fee bar alone with no rule named, so the
    // universal reading was false on two rows in three and #9's own
    // exactness fix is taken.
    href: "/board",
    label: "Refusals",
    blurb:
      "The candidates the engine priced in its last half-hour of recording, each with the reason that stopped it — a named check, or the fee bar. Nearly all are refused — the ordinary night.",
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
