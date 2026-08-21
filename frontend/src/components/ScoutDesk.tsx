"use client";

/**
 * The scout desk on one game's screen (ADR 0060) — rendered as instruments,
 * not prose.
 *
 * Joe's design: a master scout with a staff — one specialist per team, each
 * covering their own side's player status, team status, and (for the host's
 * scout) the venue — and the master collecting their notes. After reading the
 * first real briefing he asked for a cockpit: "I am more of a visual guy …
 * It's a lot of words." So the screen leads with a verdict strip and a board
 * of six category tiles, and every paragraph lives behind a tap. It must be
 * good at both widths — he reads on the desktop and the phone.
 *
 * The colours make honest claims (the graphic-designer's standing rule):
 * - gold (accent-2) is reserved for FRESH — the market may not know this yet;
 * - a dashed border and "?" is UNCHECKED — searched, could not verify.
 *   A gap must never render as calm; the first briefing's most useful fact
 *   was an unchecked weather instrument.
 * - muted is old news; green (positive) is checked-and-clear.
 *
 * Honesty rules carried over from v1, all load-bearing:
 * - **No number renders here that could feed a bet.** The desk's schema has
 *   no field for one; this component adds none, and the tiles are words.
 * - **"Filed nothing" is not "found nothing".** A dead scout renders as a
 *   dark side of the desk, an empty filing as "looked, nothing noteworthy".
 * - **A convening that went quiet says so.** The POST answers `accepted`,
 *   never `briefed`; a `running` row past the backend's patience window is
 *   rendered as gone quiet rather than spinning forever.
 *
 * Briefings stored before the board existed have no `board` field; the tiles
 * are then derived from the staff's own category flags, and a category with
 * no filed note renders "no notes" — that derivation cannot tell clear from
 * unchecked, and does not pretend to.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DISPLAY_TIME_ZONE,
  fetchScoutBriefing,
  sendScoutDesk,
  type BoardTile,
  type ScoutBriefingState,
  type ScoutStaffNote,
} from "@/lib/api";
import CrewAvatar from "@/components/CrewAvatar";

const POLL_MS = 5_000;

const CATEGORY_ORDER: BoardTile["category"][] = [
  "lineup",
  "injury",
  "weather",
  "rest_travel",
  "venue",
  "other",
];

const CATEGORY_LABELS: Record<string, string> = {
  injury: "Injuries",
  lineup: "Lineups",
  weather: "Weather",
  rest_travel: "Rest & travel",
  venue: "Venue",
  other: "Notes",
};

type TileState = BoardTile["state"] | "no_notes";

const TILE_STATES: Record<
  TileState,
  { word: string; className: string; dot: string }
> = {
  fresh: {
    word: "FRESH",
    className: "border-accent-2 text-accent-2",
    dot: "bg-accent-2",
  },
  unconfirmed: {
    word: "UNCHECKED ?",
    className: "border-dashed",
    dot: "bg-muted",
  },
  stale_only: {
    word: "old news",
    className: "text-muted",
    dot: "bg-muted",
  },
  clear: {
    word: "clear",
    className: "text-positive",
    dot: "bg-positive",
  },
  no_notes: {
    word: "no notes",
    className: "text-muted opacity-60",
    dot: "bg-muted",
  },
};

function when(ms: number): string {
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Everything not flagged as already priced, straight from the raw filings —
 * the one count the verdict strip states, and it is a count of facts, never
 * a rating. */
function freshFindings(staff: ScoutStaffNote[] | null): number {
  if (!staff) return 0;
  return staff.reduce(
    (sum, note) =>
      sum +
      (note.report
        ? note.report.findings.filter((f) => !f.likely_already_priced).length
        : 0),
    0,
  );
}

/** Fallback for briefings stored before the master filled a board: derive
 * tile states from the staff's own category flags. Cannot tell "clear" from
 * "unchecked", so a silent category says "no notes" instead of guessing. */
function deriveBoard(staff: ScoutStaffNote[] | null): BoardTile[] {
  return CATEGORY_ORDER.flatMap((category) => {
    const findings = (staff ?? []).flatMap((note) =>
      note.report
        ? note.report.findings.filter((f) => f.category === category)
        : [],
    );
    if (findings.length === 0) return [];
    const fresh = findings.find((f) => !f.likely_already_priced);
    return [
      {
        category,
        state: fresh ? "fresh" : "stale_only",
        note: fresh ? fresh.fact.slice(0, 60) : "all likely priced in",
      } as BoardTile,
    ];
  });
}

function Board({ tiles, derived }: { tiles: BoardTile[]; derived: boolean }) {
  const byCategory = new Map(tiles.map((t) => [t.category, t]));
  return (
    <div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
        {CATEGORY_ORDER.map((category) => {
          const tile = byCategory.get(category);
          const state: TileState = tile ? tile.state : "no_notes";
          const style = TILE_STATES[state];
          return (
            <div
              key={category}
              className={`rounded-xl border p-2 ${style.className}`}
            >
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">
                {CATEGORY_LABELS[category]}
              </p>
              <p className="mt-1 flex items-center gap-1.5 text-xs font-semibold">
                <span
                  className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`}
                />
                {style.word}
              </p>
              {tile?.note && (
                <p className="mt-1 line-clamp-2 text-[11px] leading-tight text-muted">
                  {tile.note}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {derived && (
        <p className="mt-1.5 text-[11px] text-muted">
          Board derived from the staff&rsquo;s filings — this briefing predates
          the master&rsquo;s own board, so &ldquo;no notes&rdquo; may mean
          clear or unchecked.
        </p>
      )}
    </div>
  );
}

function VerdictStrip({
  fresh,
  unconfirmed,
}: {
  fresh: number;
  unconfirmed: number;
}) {
  if (fresh > 0) {
    return (
      <p className="rounded-xl border border-accent-2 px-3 py-2 text-sm font-semibold text-accent-2">
        {fresh} {fresh === 1 ? "item" : "items"} the market may not have priced
        yet — check the gold tiles.
      </p>
    );
  }
  if (unconfirmed > 0) {
    return (
      <p className="rounded-xl border border-dashed px-3 py-2 text-sm">
        Nothing fresh — but {unconfirmed}{" "}
        {unconfirmed === 1 ? "instrument is" : "instruments are"} unchecked.
        Unverified is not benign.
      </p>
    );
  }
  return (
    <p className="rounded-xl border px-3 py-2 text-sm text-muted">
      Nothing here the market doesn&rsquo;t already know. That is a finding.
    </p>
  );
}

function StaffNoteCard({ note }: { note: ScoutStaffNote }) {
  return (
    <div className="rounded-xl border p-3">
      <div className="mb-2 flex items-center gap-2">
        <CrewAvatar kind="scout" className="h-6 w-6 shrink-0" />
        <span className="text-sm font-semibold">The {note.team} scout</span>
        <span className="text-xs text-muted">
          {note.role === "home" ? "home side, covers the venue" : "away side"}
        </span>
      </div>
      {note.report === null ? (
        <p className="text-sm text-muted">
          Filed nothing — the call failed. This side of the desk is dark, which
          is not the same as there being nothing to report.
        </p>
      ) : note.report.findings.length === 0 ? (
        <p className="text-sm text-muted">
          Looked and found nothing noteworthy. Searched:{" "}
          {note.report.searched_for.join(", ")}.
        </p>
      ) : (
        <ul className="space-y-2">
          {note.report.findings.map((finding, index) => (
            <li key={index} className="text-sm leading-relaxed">
              <span
                className={`mr-2 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                  finding.likely_already_priced
                    ? "bg-card text-muted"
                    : "bg-accent-2 text-white"
                }`}
              >
                {CATEGORY_LABELS[finding.category] ?? finding.category}
              </span>
              {finding.fact}
              <span className="ml-2 text-xs text-muted">
                {finding.source_url ? (
                  <a
                    href={finding.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    {finding.source}
                  </a>
                ) : (
                  finding.source
                )}
                {" · "}
                {finding.reported_when}
                {finding.likely_already_priced && (
                  <span className="ml-1 italic">— likely already priced in</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ScoutDesk({ ticker }: { ticker: string }) {
  const [state, setState] = useState<ScoutBriefingState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(() => {
    fetchScoutBriefing(ticker)
      .then((payload) => {
        setState(payload);
        setError(null);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "unavailable"),
      );
  }, [ticker]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll only while a convening is actually out. The backend's patience
  // window bounds how long that can be, so this cannot spin forever.
  const running =
    state?.state === "sent" && state.status === "running" && !state.gone_quiet;
  useEffect(() => {
    if (!running) return;
    pollRef.current = setInterval(load, POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [running, load]);

  const send = async () => {
    setSending(true);
    setSendError(null);
    const result = await sendScoutDesk(ticker);
    setSending(false);
    if (!result.accepted) {
      setSendError(result.detail);
      return;
    }
    load();
  };

  const sendButton = (label: string) => (
    <div>
      <button
        onClick={send}
        disabled={sending}
        className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
      >
        {sending ? "Sending…" : label}
      </button>
      <p className="mt-1.5 text-xs text-muted">
        Three metered calls from the fleet&rsquo;s shared daily budget. The
        desk reports facts with sources; it never prices anything.
      </p>
      {sendError && (
        <p className="mt-2 text-sm text-negative" role="alert">
          {sendError}
        </p>
      )}
    </div>
  );

  return (
    <section className="mt-6 rounded-2xl border bg-card p-4 sm:p-6">
      <div className="mb-3 flex items-center gap-2">
        <CrewAvatar kind="scout" className="h-7 w-7 shrink-0" />
        <h2 className="text-lg font-semibold">The scout desk</h2>
      </div>

      {error ? (
        <p className="text-sm text-muted">{error}</p>
      ) : state === null ? (
        <p className="text-sm text-muted">Checking the desk&hellip;</p>
      ) : state.state === "never_sent" ? (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-muted">
            The desk has not been sent on this game. Send it and two staff
            scouts — one per team — will file notes on player status, team
            status, and conditions at the venue, and the master scout will
            read their notes back as one board.
          </p>
          {sendButton("Send the scouts")}
        </div>
      ) : state.status === "running" && !state.gone_quiet ? (
        <p className="text-sm leading-relaxed text-muted">
          The desk is out on {state.event_title}: the {state.home_team} scout,
          the {state.away_team} scout, then the master. This takes a few
          minutes; the board appears here when they file.
        </p>
      ) : state.status === "running" && state.gone_quiet ? (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-muted">
            The desk went quiet — a convening started {when(state.requested_ms)}{" "}
            and never filed, which usually means the process restarted under
            it. Nothing more will arrive from that convening.
          </p>
          {sendButton("Send them again")}
        </div>
      ) : state.status === "refused" ? (
        <p className="text-sm leading-relaxed text-muted">
          The desk was refused by the day&rsquo;s budget:{" "}
          {state.refusal_reason ?? "the daily call ceiling"}. Nothing was
          spent. The day rolls over on its own.
        </p>
      ) : state.status === "failed" ? (
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-muted">
            The desk was sent {when(state.requested_ms)} and nothing came back
            — both scouts&rsquo; calls failed. The calls were still metered.
          </p>
          {sendButton("Send them again")}
        </div>
      ) : (
        <div className="space-y-4">
          <VerdictStrip
            fresh={freshFindings(state.staff)}
            unconfirmed={
              (state.briefing?.board ?? []).filter(
                (t) => t.state === "unconfirmed",
              ).length
            }
          />

          <Board
            tiles={
              state.briefing?.board?.length
                ? state.briefing.board
                : deriveBoard(state.staff)
            }
            derived={!state.briefing?.board?.length}
          />

          {state.briefing ? (
            <>
              <p className="text-sm font-semibold leading-snug">
                {state.briefing.headline}
              </p>
              <details className="rounded-xl border px-3 py-2">
                <summary className="cursor-pointer text-sm font-semibold">
                  The master&rsquo;s read
                </summary>
                <div className="mt-2 space-y-3">
                  <p className="text-sm leading-relaxed">
                    {state.briefing.assessment}
                  </p>
                  {state.briefing.what_matters.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                        What matters, in order
                      </h3>
                      <ol className="mt-1 list-decimal space-y-1 pl-5 text-sm leading-relaxed">
                        {state.briefing.what_matters.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ol>
                    </div>
                  )}
                  {state.briefing.conflicts.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                        Where the notes conflict or look thin
                      </h3>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                        {state.briefing.conflicts.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {state.briefing.unanswered.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                        What the desk could not confirm
                      </h3>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-relaxed">
                        {state.briefing.unanswered.map((item, index) => (
                          <li key={index}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              </details>
            </>
          ) : (
            <p className="text-sm leading-relaxed text-muted">
              The staff filed, but the master&rsquo;s synthesis is missing —
              the day&rsquo;s budget could not afford it, or his call failed.
              The raw notes below are still the desk&rsquo;s work.
            </p>
          )}

          {state.staff && (
            <details className="rounded-xl border px-3 py-2">
              <summary className="cursor-pointer text-sm font-semibold">
                The staff&rsquo;s notes, in full
              </summary>
              <div className="mt-2 space-y-3">
                {state.staff.map((note) => (
                  <StaffNoteCard key={note.role} note={note} />
                ))}
              </div>
            </details>
          )}

          <div className="border-t pt-3 text-xs text-muted">
            <p>
              Filed {state.completed_ms ? when(state.completed_ms) : "—"}
              {" · "}sent {when(state.requested_ms)}
              {" · "}facts with sources only; the desk never prices a bet.
            </p>
            <div className="mt-2">{sendButton("Send them again")}</div>
          </div>
        </div>
      )}
    </section>
  );
}
