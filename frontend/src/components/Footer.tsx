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
const SECONDARY = [
  {
    // Born 2026-08-21 (betting-desk item 1): Joe's own settled bets, read
    // off the venue-settlement mirror. In the footer rather than the nav
    // because the nav's six slots are spent; the nav-swap that would have
    // moved this page into the open slot under "Ledger" was dropped
    // 2026-08-22 (Scout took the slot first), so it stays here. The other
    // half of that item -- renaming `/ledger`'s own "Ledger" label, since
    // this is the page that word actually describes -- shipped on its own;
    // see `Nav.tsx`.
    href: "/bets",
    label: "Your bets",
    blurb:
      "Every settled position the recorder mirrored from your account, with the net.",
  },
  {
    // Lost its nav slot on 2026-08-21: Joe stopped the calibration study
    // (Amendment 2, stopped without result), and a nav slot opening a form
    // that feeds a stopped study is quiet misdirection. The page stays: it
    // renders the terminal state and holds the log's record.
    href: "/estimate",
    label: "Log",
    blurb: "The calibration bet log. The study is stopped; this is its record.",
  },
  {
    // The landing screen's old address. "/" renders the same component since
    // 2026-08-20 (fleet convening item 3), so this link exists for bookmarks
    // and muscle memory, not for a second screen.
    href: "/slate",
    label: "Slate",
    blurb: "The Games screen at its old address — same page the app now opens on.",
  },
  {
    // Lost its nav slot to Log on 2026-08-18 (the calibration study makes
    // logging the per-bet action; dbt marts are read weekly at most).
    href: "/dashboards",
    label: "Data",
    blurb: "The dbt marts: settlement outcomes and headline verdicts, rebuilt nightly.",
  },
  {
    href: "/rejections",
    label: "Rejections",
    blurb: "Which check is refusing everything, counted across the slate.",
  },
  {
    href: "/builder",
    label: "Parlay builder",
    blurb: "The book's hold on a specific ticket. The answer is usually don't.",
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
