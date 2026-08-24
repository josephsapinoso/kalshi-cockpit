import { leagueLabel } from "@/lib/leagueLabel";

/**
 * Which sport a game row is, said outright.
 *
 * Joe's report (2026-08-24): anywhere a game renders — Games, Picks, the
 * parlay cards — the name alone ("LAC", "Sparks") does not say which sport
 * it is, and a reader juggling MLB and WNBA on one slate can mistake one
 * for the other. The fix is a small tag beside the name, through
 * `leagueLabel` so the vendor's `baseball_mlb` reads "MLB".
 *
 * `null`/`undefined` renders nothing: an unlinked row has no recorded
 * league, and inventing one from the ticker's series prefix would be a
 * guess wearing a fact's clothes (the unreadable-resolves-to-`None` rule).
 */
export default function LeagueTag({
  league,
}: {
  league: string | null | undefined;
}) {
  if (!league) return null;
  return (
    <span className="shrink-0 rounded border border-border px-1 py-px font-mono text-[0.6rem] uppercase tracking-wide text-muted">
      {leagueLabel(league)}
    </span>
  );
}
