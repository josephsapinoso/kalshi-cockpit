import { SHELL_WIDTH } from "@/lib/shell";
import { fetchSlate, fetchWindow, formatAge } from "@/lib/api";
import type { ActionableWindow, Slate } from "@/lib/api";
import { anAutomaticBuyIsComing } from "@/lib/nextOddsWindow";

import GoodChancePicks from "@/components/GoodChancePicks";
import RefreshWhenPriced from "@/components/RefreshWhenPriced";
import TonightStrip from "@/components/TonightStrip";

export const dynamic = "force-dynamic";

/**
 * The ranked list, in the "Picks" nav slot (decision-map #8, ratified by Joe
 * 2026-08-27). Until this page existed the word "Picks" opened `/board`,
 * a screen on which nothing has been a pick for the life of the record.
 *
 * What this is: tonight's price-comparison sheet, one line per game the desk
 * could price — which side the sharp sportsbooks make more likely, the chance
 * they give it, and what Kalshi charges for it. The ordering is the market's
 * opinion, never the desk's: the server sorts on one stored column,
 * `fair_probability`, and this page renders that block whole through the
 * same `GoodChancePicks` component the Games screen renders (a promotion,
 * not a move — the block stays on Games too). The chance≠edge sentence is the
 * server's own and renders verbatim inside the block, and
 * `tests/test_slate_picks.py` fails the build if any key readable as profit
 * ever rides the payload.
 *
 * What it is not, and the pins that keep it so (`tests/test_picks_screen.py`):
 *
 * - **No order route.** No ticket trigger, no buy button, no manual ticket,
 *   no market search that opens one. A row links to the game's own screen,
 *   which carries its own price and its own ticket; nothing here does. This
 *   is the only screen in the product on which the word "Picks" opens no
 *   door to real money, and #8 counted that as the reason the promotion is
 *   safe — refusing it would have kept a live IOC button on every row of the
 *   highest-traffic slot.
 * - **No credit-spending refresh control as the empty-night content.**
 *   `RefreshOddsPanel` stays on Games. "Act to make the list non-empty" is
 *   the chase affordance in its purest form.
 * - **No headline counting how many picks ranked.** A number that rises when
 *   there is more to bet on is a number the screen is not allowed to grow.
 * - **The money line travels; the deposit arithmetic does not.** Cash and
 *   the per-bet cap come from the same `/api/slate` payload, so this is not
 *   the one screen naming bettable sides with no money context on it. "One
 *   contract at 50c needs a $X balance" is honest apparatus beside the
 *   refusal machinery on Games and a funnel beside a favourites list at
 *   11pm; every cap is a percentage of the observed balance, so a deposit
 *   raises all three at once.
 *
 * The empty states are drawn as different facts, because on this project's
 * own measurements the empty night is the ordinary one (#20): a payload with
 * no picks block (a backend one version behind), a block that ranked nothing
 * (the recorder's window held no game it could price), a slate that is not
 * current (the last pass is old), and an unreachable backend each say a
 * different thing, and a page that drew them alike would read "no data" as
 * "nothing worth betting".
 *
 * **It heals itself, and for one day it did not.** This is a one-shot
 * server render, and the screen it took the nav word from (`/slate`) mounts
 * `RefreshWhenPriced` so that the sweep a cold open triggers — landing a
 * median 3.3 s after the first heartbeat, per the visit-freshness read of
 * 2026-09-02 — re-renders the page in place. The watcher did not come with
 * the promotion. Compose that with the same read's other figure, that on
 * 21 of 45 cold opens no upcoming fixture was inside the limit, and this
 * screen rendered "N games not ranked: the consensus is too old to speak"
 * on half of Joe's opens and held it for as long as he sat there, while the
 * answer had been in the database since second three. That is the literal
 * mechanism behind his stated reason for not opening the desk, on the
 * screen the nav word "Picks" opens, shipped the day after he said it.
 *
 * The gate is `not_ranked.stale_consensus > 0` — a game is being withheld
 * by the clock, so a rising `fixtures_fresh` can change what the list says.
 * Deliberately `some`, where the Slate gates on the *whole* screen being
 * unpriced: this list only ever grows under the watcher, and a game
 * appearing beneath the ones already read is not the reflow that rule
 * exists to prevent. The empty "nothing ranked" state is NOT gated in: it
 * means the recorder's window held no priced game, and a sweep landing
 * raises `fixtures_fresh` before the runner has evaluated anything, so the
 * one refresh the watcher would fire there shows the same empty screen.
 * Whether a buy is actually coming is `anAutomaticBuyIsComing`, as on the
 * Slate; past it the watcher says nothing is due rather than polling.
 */
export default async function PicksPage() {
  let data: Slate;
  let actionable: ActionableWindow | null = null;
  try {
    data = await fetchSlate();
    // Its own catch: the watcher needs a baseline count and nothing else on
    // this page does, so a timetable that will not answer costs the watcher
    // and not the list.
    actionable = await fetchWindow().catch(() => null);
  } catch {
    return (
      <Shell>
        <h1 className="text-2xl font-extrabold tracking-tight">Picks</h1>
        <p className="mt-4 max-w-prose text-muted">
          Backend unreachable. Nothing is drawn on purpose: a list that
          rendered without data would look like &ldquo;no favourites
          tonight&rdquo; rather than &ldquo;no connection&rdquo;.
        </p>
      </Shell>
    );
  }

  const { slate } = data;
  const picks = data.picks ?? null;
  const skipped = picks
    ? picks.not_ranked.stale_consensus + picks.not_ranked.favorite_unpriced
    : 0;
  /** The block renders nothing at all for this pair; the page must say why. */
  const nothingToRank = picks !== null && picks.ranked.length === 0 && skipped === 0;

  return (
    <Shell>
      <header>
        {/* "Picks", matching its own nav label: one screen, one name, the
            rule Games settled on 2026-08-22 and Refusals on 2026-09-02
            (#29). The block below keeps its own heading, "Likely winners
            tonight", because it is the same block Games renders. */}
        <h1 className="text-2xl font-extrabold tracking-tight">Picks</h1>
        {/* The #9 lede for this slot, ratified 2026-08-27. It names the
            ordering and disarms it in the same breath; on a desk whose
            measured signal is negative, a screen labelled "Picks" and sorted
            descending is the hardest slot in the set, and the length of the
            disarming clause is a ratified cost. */}
        <p className="mt-2 max-w-prose text-sm text-muted">
          One line for each game the desk could price: the side the
          sportsbooks make more likely, the chance they give it, and what
          Kalshi charges &mdash; ordered by that chance, which is not a claim
          that any of them is worth buying.
        </p>
      </header>

      {/* The safety envelope, from the same payload (#8 amendment 2): cash
          and the per-bet cap, and the "Not tonight" control. Cash and open
          positions are never summed; neither is shown beside the other here.
          An unobserved balance renders its refusal in words rather than
          nothing — the same rule as Games. */}
      {data.money && (
        <p className="mt-4 text-sm">
          <span className="font-semibold tabular">
            {data.money.cash_display === null
              ? "Cash unread"
              : `${data.money.cash_display} in the account.`}
          </span>
          {data.money.per_bet_cap_display !== null ? (
            <span className="text-muted">
              {" "}
              Your cap is {data.money.per_bet_cap_display} a bet.
            </span>
          ) : (
            <span className="text-accent-2">
              {" "}
              No caps can be derived &mdash;{" "}
              {data.money.caps_basis.refusal ?? "balance unobserved"}.
            </span>
          )}
        </p>
      )}
      {data.tonight && <TonightStrip tonight={data.tonight} />}

      {/* When these readings were taken, whenever that is not now. The
          block's own "too old to speak" count is about the consensus behind
          each game; this is about the recorder's last pass, which is the
          other way a quiet list is a stale one rather than an empty one. */}
      {!slate.is_current && slate.age_ms !== null && (
        <p className="mt-6 max-w-prose text-sm text-accent-2">
          Not a live reading. The desk&rsquo;s last recording pass was{" "}
          {formatAge(slate.age_ms)}, so the chances and prices below are what
          it last read, not what the books and Kalshi say now.
        </p>
      )}

      {picks === null ? (
        /* The demo backend, and any backend one version behind, answers
           `/api/slate` with no `picks` key at all. Drawn as its own fact:
           "not available on this instance" is a statement about the wire,
           and rendering nothing here would be a healthy silence over it. */
        <section className="mt-8 rounded-2xl border border-edge bg-card p-5">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Not available on this instance
          </h2>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">
            The ranked list is not available on this instance: the backend
            answered without a picks block, which is a version fact rather
            than a night with no favourites. Nothing here is a reading of
            tonight&rsquo;s games.
          </p>
        </section>
      ) : nothingToRank ? (
        /* `GoodChancePicks` returns null for this pair, so without this the
           tab opens to an h1 and whitespace — the indictment #8 levelled at
           the screen this one replaced in the slot. */
        <section className="mt-8 rounded-2xl border border-edge bg-card p-5">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Nothing ranked
          </h2>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-muted">
            No game is ranked tonight, and none was counted out either: the
            consensus was too old to speak on none, and the favourite&rsquo;s
            side was unpriced on none &mdash; the desk priced no game at all
            in its last half-hour of recording. That is a fact about the
            recorder&rsquo;s window, not a verdict on tonight&rsquo;s games.
          </p>
        </section>
      ) : (
        <GoodChancePicks picks={picks} />
      )}

      {/* The self-heal, beneath the block that names the games it is waiting
          on. Gated on a game being withheld by the clock and on a timetable
          to measure against; see the docstring for why `some`, and why the
          empty state is left out. It polls `/api/window` and spends
          nothing — the credit-spending controls stay on Games. */}
      {actionable && picks !== null && picks.not_ranked.stale_consensus > 0 && (
        <div className="mt-3 max-w-[65ch]">
          <RefreshWhenPriced
            renderedFresh={actionable.fixtures_fresh}
            automaticBuyIsComing={anAutomaticBuyIsComing(actionable)}
          />
        </div>
      )}

      {/* Where the engine's own reasons live, said in words rather than
          linked. #8 struck the link from the foot of this screen on purpose:
          every row it would lead to carries a live hand-bet button, and a
          next-step affordance under a favourites list is the chase shape.
          The footer on every page carries the link and its sentence. */}
      {picks !== null && picks.ranked.length === 0 && (
        <p className="mt-3 max-w-prose text-xs text-muted">
          The engine&rsquo;s reason for each candidate it refused tonight is
          on Refusals, listed in the footer of this page.
        </p>
      )}

      {/* The truncation admission travels with the block (#8 amendment 5):
          the same sentence Games renders, because picks are ranked after
          the row query's limit and a game lost to that limit is counted in
          neither exclusion the block prints. The limit is not raised —
          `/api/slate` runs one quote query per returned row and nobody has
          measured five times that. */}
      {slate.truncated && (
        <p className="mt-6 max-w-prose text-xs text-muted">
          {slate.in_window} rows are in the window and {slate.returned} are shown
          {slate.off_basis > 0
            ? `; ${slate.off_basis} were dropped by the second freshness reading`
            : ""}
          . A game on the rows left out is ranked nowhere above and counted in
          neither exclusion.
        </p>
      )}
    </Shell>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-6 py-12 sm:py-16 xl:px-8`}>{children}</div>
  );
}
