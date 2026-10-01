/**
 * Wire types for the scout desk, briefings, lessons and playbooks.
 *
 * Types only (#262, ADR 0191 sec 2.5): `import type` and nothing at runtime, and
 * never an import from `api.ts`. `api.ts` re-exports every name here.
 */

import type { ConfigVersion } from "./signal";

export type Lesson = {
  id: number;
  created_ms: number;
  title: string;
  body: string;
  evidence: Record<string, unknown> | null;
  sample_size: number | null;
  proposed_config_diff: Record<string, unknown> | null;
  /**
   * Three states. `null` is "nobody has decided" and `false` is "rejected" --
   * collapsing them would turn every proposal awaiting a human into one a
   * human refused.
   */
  accepted_by_user: boolean | null;
};

export type Playbook = {
  config_versions: ConfigVersion[];
  current_version: number | null;
  lessons: Lesson[];
  proposals_awaiting_approval: Lesson[];
  /**
   * The distinction this screen must not collapse. `lessons` has no writer --
   * its one writer, the Historian, never ran and was deleted on 2026-09-05 --
   * so an empty list means nothing can write one, not that the record
   * contains nothing worth learning. The name is historical; the value is
   * whether a lesson row exists, and on every deployed instance it is false.
   */
  historian_has_run: boolean;
  note: string;
  min_rows_to_mean_anything: number;
};

/**
 * The scout desk (ADR 0060): two staff scouts and a master, sent on one game.
 *
 * The desk never outputs a probability, a price, or "bet it" -- its schema
 * has no field to put one in, which is enforcement rather than etiquette.
 * Everything numeric on this screen still comes from the deterministic
 * pipeline; the desk carries sourced facts and the master's qualitative read.
 */
export type ScoutFinding = {
  category:
    | "injury"
    | "lineup"
    | "weather"
    | "rest_travel"
    | "matchup"
    | "venue"
    | "sentiment"
    | "other";
  fact: string;
  source: string;
  source_url: string | null;
  reported_when: string;
  likely_already_priced: boolean;
  affects_side: string | null;
};

export type ScoutStaffReport = {
  game: string;
  findings: ScoutFinding[];
  summary: string;
  searched_for: string[];
};

/** `report: null` means that scout FILED nothing (the call failed) -- a
 * different fact from a report whose findings list is empty. */
export type ScoutStaffNote = {
  role: "home" | "away";
  team: string;
  report: ScoutStaffReport | null;
};

/** One instrument on the desk's board. States are words, never scores:
 * `unconfirmed` is a warning (searched, could not verify), not an all-clear. */
export type BoardTile = {
  category:
    | "lineup"
    | "injury"
    | "weather"
    | "rest_travel"
    | "matchup"
    | "venue"
    | "sentiment"
    | "other";
  state: "fresh" | "stale_only" | "unconfirmed" | "clear";
  note: string;
};

export type DeskBriefing = {
  /** Absent on briefings filed before the board existed (2026-08-21). */
  board?: BoardTile[];
  headline: string;
  assessment: string;
  what_matters: string[];
  conflicts: string[];
  unanswered: string[];
};

/**
 * Willy Balters' take (ADR 0069) — the pro-bettor seat's filing. Words
 * only, like every desk schema: no field can carry a forecast. The
 * character is a house fiction; the panel says so on screen.
 */
export type SharpTake = {
  headline: string;
  read: string;
  discipline: string[];
  would_change_my_mind: string[];
};

export type ScoutBriefingState =
  | { state: "never_sent" }
  | {
      state: "sent";
      id: number;
      status: "running" | "complete" | "partial" | "failed" | "refused";
      gone_quiet: boolean;
      ticker: string;
      event_title: string;
      league: string;
      home_team: string;
      away_team: string;
      commence_ms: number | null;
      requested_ms: number;
      completed_ms: number | null;
      refusal_reason: string | null;
      staff: ScoutStaffNote[] | null;
      briefing: DeskBriefing | null;
      /** `null` (or absent, one server version back): the seat filed
       * nothing here, or the briefing predates the seat. */
      sharp?: SharpTake | null;
      model: string;
    };

export type SendDeskResult =
  | { accepted: true; id: number }
  | { accepted: false; status: number; detail: string };

export type RecordPassResult =
  | { recorded: true; id: number }
  | { recorded: false; status: number; detail: string };

/**
 * What the market screen renders of `/api/market/{ticker}` — the venue's own
 * facts (what you transact against), never the tool's opinion of them. The
 * payload also carries fair/edge/EV fields; they are deliberately not typed
 * here, because a single-game page is the screen with the least context to
 * hold a refuted signal's numbers honestly (ADR 0038).
 */
/**
 * The Skeptic panel's board (ADR 0068): every mechanical check's verdict,
 * reconstructed server-side from the stored `suppressed_reason`. `judged_ms`
 * is the basis the verdicts are facts about — the screen must caption it,
 * because "passed at 19:02" and "passes now" are different claims. `sizing`
 * carries `sizing:`-prefixed refusals verbatim; `unknown` carries codes this
 * build's vocabulary does not name, so a newer server's rule still renders.
 */
export type Gauntlet = {
  checks: { code: string; verdict: "passed" | "refused" | "not_taken" }[];
  sizing: string[];
  unknown: string[];
  judged_ms?: number | null;
};

/**
 * The desk's own screen (`/scout`): what it has done, and what today cost.
 *
 * `spend` is the v17 token meter -- counts in the three units that actually
 * bill (calls, web searches, tokens), never dollars: the per-token rate in
 * this repo is assumed, not invoiced, and a number on a screen outranks the
 * caveat attached to it. `spend: null` means no Anthropic account is
 * configured (the demo) -- there is no meter to read, which is a different
 * fact from a meter reading zero.
 */
export type ScoutOverviewRow = {
  id: number;
  ticker: string;
  event_title: string;
  league: string;
  home_team: string;
  away_team: string;
  commence_ms: number | null;
  requested_ms: number;
  completed_ms: number | null;
  status: "running" | "complete" | "partial" | "failed" | "refused";
  gone_quiet: boolean;
  refusal_reason: string | null;
  has_briefing: boolean;
};

export type ScoutSpend = {
  calls_today: number;
  calls_daily_budget: number;
  searches_today: number;
  searches_daily_budget: number;
  tokens_today: number;
  tokens_daily_budget: number;
  /** Calls whose usage never came back -- the sums above do not cover them. */
  calls_unmetered_today: number;
  day_start_ms: number;
};

export type ScoutOverview = {
  briefings: ScoutOverviewRow[];
  spend: ScoutSpend | null;
};
