import Link from "next/link";

import { SHELL_WIDTH } from "@/lib/shell";
import {
  DISPLAY_TIME_ZONE,
  fetchScoutOverview,
  type ScoutOverviewRow,
  type ScoutSpend,
} from "@/lib/api";
import CrewAvatar from "@/components/CrewAvatar";

export const dynamic = "force-dynamic";

/**
 * The scout desk's own screen (2026-08-21, betting-desk item 6: metered, then
 * promoted to the nav — the same change, so the desk arrives in the nav
 * already wearing its meter).
 *
 * Two jobs, in this order:
 *
 * 1. **The meter.** What the desk has cost TODAY, in the three units that
 *    actually bill — calls, web searches, tokens — each against its ceiling.
 *    Counts, never dollars: the per-token rate in this repo is assumed, not
 *    invoiced, and a dollar figure on a screen outranks any caveat beside it.
 *    This is the one place Joe can see the day's spend before sending the
 *    desk again; it is protecting a real, freshly-topped-up account.
 * 2. **The record.** Every convening, newest first, linking to the game
 *    screen where its briefing is read and where the next one is sent. This
 *    page deliberately has no send button — the desk is sent from a game,
 *    because a desk sent from a list invites sending it to fill the list.
 *
 * The empty state says how to get a first briefing rather than pretending
 * the desk is broken; `spend: null` (the demo) says there is no account to
 * meter, which is a different fact from a meter reading zero.
 */
export default async function ScoutDeskPage() {
  let overview;
  try {
    overview = await fetchScoutOverview();
  } catch {
    return (
      <Shell>
        <p className="max-w-[65ch] text-muted">Backend unreachable.</p>
      </Shell>
    );
  }

  return (
    <Shell>
      <header className="mb-8">
        <div className="flex items-center gap-3">
          <CrewAvatar kind="scout" className="h-9 w-9 shrink-0" />
          <h1 className="display text-4xl sm:text-5xl">Scout desk</h1>
        </div>
        <p className="mt-3 max-w-[65ch] text-lg text-muted">
          Two staff scouts and a master, sent on one game at a time from that
          game&rsquo;s screen. They file sourced facts — lineups, injuries,
          weather, rest — and never a price, a probability, or a verdict on a
          bet.
        </p>
      </header>

      <SpendMeter spend={overview.spend} />

      <h2 className="mt-10 text-sm font-semibold uppercase tracking-widest text-muted">
        Convenings
      </h2>
      {overview.briefings.length === 0 ? (
        <p className="mt-4 max-w-[65ch] text-sm text-muted">
          The desk has never been sent. Open a game from the Games screen and
          send it from there — a convening is three metered calls and up to a
          dozen web searches, so it starts with a tap, never on a schedule.
        </p>
      ) : (
        <ul className="mt-4 divide-y border-t">
          {overview.briefings.map((row) => (
            <BriefingRow key={row.id} row={row} />
          ))}
        </ul>
      )}
    </Shell>
  );
}

/**
 * Three instruments, one per billing unit. The numbers are the API's own
 * counts rendered verbatim — no percentages, no dollars, no rounding a
 * ceiling into a vibe. `calls_unmetered_today > 0` gets its own line because
 * the token and search sums silently exclude those calls, and a meter that
 * under-counts without saying so is the "receipt, not a brake" defect with a
 * nicer font.
 */
function SpendMeter({ spend }: { spend: ScoutSpend | null }) {
  if (spend === null) {
    return (
      <div className="rounded-2xl border bg-card p-5">
        <p className="max-w-[65ch] text-sm text-muted">
          No Anthropic account is configured on this instance, so there is no
          meter to read and the desk cannot be sent. This is the demo&rsquo;s
          honest state, not an empty meter.
        </p>
      </div>
    );
  }
  const dayStart = new Date(spend.day_start_ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  const units: Array<{ label: string; used: number; budget: number }> = [
    {
      label: "Calls",
      used: spend.calls_today,
      budget: spend.calls_daily_budget,
    },
    {
      label: "Web searches",
      used: spend.searches_today,
      budget: spend.searches_daily_budget,
    },
    {
      label: "Tokens",
      used: spend.tokens_today,
      budget: spend.tokens_daily_budget,
    },
  ];
  return (
    <div className="rounded-2xl border bg-card p-5">
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        Today&rsquo;s spend, all agents
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3">
        {units.map((unit) => (
          <div key={unit.label}>
            <p className="max-w-[65ch] text-[10px] font-semibold uppercase tracking-wide text-muted xl:text-xs">
              {unit.label}
            </p>
            <p className="mt-1 max-w-[65ch] font-mono text-sm font-semibold xl:text-base">
              {unit.used.toLocaleString("en-US")}
              <span className="text-muted">
                {" "}
                of {unit.budget.toLocaleString("en-US")}
              </span>
            </p>
          </div>
        ))}
      </div>
      {spend.calls_unmetered_today > 0 && (
        <p className="mt-3 max-w-[65ch] text-xs text-muted">
          {spend.calls_unmetered_today} of today&rsquo;s calls never reported
          usage — the search and token sums do not cover
          {spend.calls_unmetered_today === 1 ? " it" : " them"}, so read both
          as at-least. The call count is exact either way.
        </p>
      )}
      <p className="mt-3 max-w-[65ch] text-xs text-muted">
        Counts, not dollars — no invoice has confirmed a rate. Each ceiling
        refuses further convenings for the day once crossed; the day rolled at{" "}
        {dayStart}. A convening is 3 calls and up to 12 searches.
      </p>
    </div>
  );
}

/**
 * One convening, as a row that goes where the briefing lives. The status
 * words render verbatim (label-and-caption, ADR 0050); `gone_quiet` is the
 * one decoration, because a `running` that will never finish must not look
 * alive on a screen Joe checks between other obligations.
 */
function BriefingRow({ row }: { row: ScoutOverviewRow }) {
  const requested = new Date(row.requested_ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  return (
    <li>
      <Link
        href={`/market/${encodeURIComponent(row.ticker)}`}
        className="flex items-baseline gap-3 py-4 transition-colors hover:bg-accent-soft"
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold">
            {row.away_team} @ {row.home_team}
          </span>
          <span className="mt-0.5 block text-xs text-muted">
            {row.league} · sent {requested}
          </span>
          {row.status === "refused" && row.refusal_reason && (
            <span className="mt-0.5 block max-w-[65ch] text-xs text-muted">
              {row.refusal_reason}
            </span>
          )}
        </span>
        <span className="shrink-0 font-mono text-xs font-semibold">
          {row.gone_quiet ? "gone quiet" : row.status.replace("_", " ")}
        </span>
      </Link>
    </li>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${SHELL_WIDTH} px-4 py-12 sm:px-6 sm:py-16 xl:px-8`}>
      {children}
    </div>
  );
}
