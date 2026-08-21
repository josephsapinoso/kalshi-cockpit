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
 * - FRESH is glyph-and-weight only (▲, strong border, full ink) — **no hue,
 *   since 2026-08-21**. It wore gold (accent-2) until the partner's
 *   betting-desk ruling neutralised it: `likely_already_priced` is the
 *   staff's own unfalsifiable guess about *pricing*, and lighting it in
 *   colour renders the tool's opinion of an edge — the exact thing ADR 0062
 *   demoted — in the palette slot every other screen reserves for "do not
 *   trust this" warnings (see test_palette_contrast.py). The fact still
 *   renders, in words and weight; it no longer glows.
 * - a dashed border and "?" is UNCHECKED — searched, could not verify.
 *   A gap must never render as calm; the first briefing's most useful fact
 *   was an unchecked weather instrument.
 * - muted is old news; `clear` is deliberately unlit — an annunciator panel
 *   is dark at rest, and green tiles above a price would argue with the
 *   tool's own measured no-edge conclusion.
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

/**
 * The glyph is the primary channel -- it survives greyscale and sunlight,
 * which a 6px coloured dot does not. `clear` is deliberately unlit (muted
 * ink, default border, blank glyph slot): an annunciator panel is dark at
 * rest, and that darkness is where a lit segment gets its authority. On a
 * quiet night six green tiles above a price would argue with the tool's own
 * measured conclusion that there is no edge. Only `fresh` carries hue.
 * `no_notes` (legacy derived boards only) renders exactly as `unconfirmed`:
 * two flavours of "we don't know" are the same fact for a decision.
 */
const TILE_STATES: Record<TileState, { glyph: string; className: string }> = {
  fresh: { glyph: "▲", className: "border-border-strong" },
  unconfirmed: { glyph: "?", className: "border-dashed border-border-strong" },
  stale_only: { glyph: "○", className: "text-muted" },
  clear: { glyph: "", className: "text-muted" },
  no_notes: { glyph: "?", className: "border-dashed border-border-strong" },
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
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-6 xl:gap-3">
        {CATEGORY_ORDER.map((category) => {
          const tile = byCategory.get(category);
          const state: TileState = tile ? tile.state : "no_notes";
          const style = TILE_STATES[state];
          return (
            <div
              key={category}
              className={`rounded-xl border p-2 xl:min-h-[132px] xl:p-4 ${style.className}`}
            >
              <p className="max-w-[65ch] text-[10px] font-semibold uppercase tracking-wide text-muted xl:text-xs">
                {CATEGORY_LABELS[category]}
              </p>
              {/* Label-and-caption (ADR 0050): the state renders verbatim,
                  the model's own note glosses it beneath. Never translated. */}
              <p className="mt-1 flex max-w-[65ch] items-center gap-1.5 font-mono text-xs font-semibold xl:text-base">
                <span className="inline-block w-3.5 shrink-0 text-sm leading-none xl:w-5 xl:text-lg">
                  {style.glyph}
                </span>
                {(tile ? tile.state : "no notes").replace("_", " ")}
              </p>
              {tile?.note && (
                <p className="mt-1 max-w-[65ch] line-clamp-2 text-[11px] leading-tight text-muted xl:line-clamp-3 xl:text-sm">
                  {tile.note}
                </p>
              )}
            </div>
          );
        })}
      </div>
      {derived && (
        <p className="mt-1.5 max-w-[65ch] text-[11px] text-muted">
          Board derived from the staff&rsquo;s filings — this briefing predates
          the master&rsquo;s own board, so &ldquo;no notes&rdquo; may mean
          clear or unchecked.
        </p>
      )}
    </div>
  );
}

/**
 * Binary on purpose -- no counts. The desk's schema structurally forbids any
 * number a forecast could hide in, and a "3 items" hero line manufactures the
 * one number the backend refuses to produce, in the slot where a magnitude
 * goes. Three stale-adjacent items are not more edge than one.
 */
function VerdictStrip({
  fresh,
  unconfirmed,
}: {
  fresh: boolean;
  unconfirmed: boolean;
}) {
  if (fresh) {
    return (
      <div className="rounded-xl border border-border-strong px-3 py-2 text-sm font-semibold xl:px-4 xl:py-3">
        <p className="max-w-[65ch]">
          The desk filed something recent — read the marked tiles, then judge
          it yourself. Recent is not the same as unpriced.
        </p>
      </div>
    );
  }
  if (unconfirmed) {
    return (
      <div className="rounded-xl border border-dashed border-border-strong px-3 py-2 text-sm xl:px-4 xl:py-3">
        <p className="max-w-[65ch]">
          Nothing fresh — but some instruments went unchecked. Unverified is
          not benign.
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border px-3 py-2 text-sm text-muted xl:px-4 xl:py-3">
      <p className="max-w-[65ch]">
        Nothing here the market doesn&rsquo;t already know. That is a finding.
      </p>
    </div>
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
        <p className="max-w-[65ch] text-sm text-muted">
          Filed nothing — the call failed. This side of the desk is dark, which
          is not the same as there being nothing to report.
        </p>
      ) : note.report.findings.length === 0 ? (
        <p className="max-w-[65ch] text-sm text-muted">
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
                    : "border border-border-strong"
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

  /**
   * Only the FIRST send wears the filled accent; every re-send is a bordered
   * secondary. ADR 0047 made the same call for TicketSheet: a filled accent
   * control must not be the brightest thing on a wide screen unless it spends
   * money it has not spent before -- and a red button under a completed board
   * invites re-rolling the desk until it says something.
   */
  const sendButton = (label: string, again = false) => (
    <div>
      <button
        onClick={send}
        disabled={sending}
        className={
          again
            ? "rounded-lg border border-border-strong px-4 py-2 text-sm font-semibold text-muted disabled:opacity-50"
            : "rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        }
      >
        {sending ? "Sending…" : label}
      </button>
      <p className="mt-1.5 max-w-[65ch] text-xs text-muted">
        {again
          ? "Three more metered calls, up to a dozen web searches. The board above stays until they file."
          : "Three metered calls and up to a dozen web searches, from the fleet’s shared daily budget — the Scout screen shows today’s running total. The desk reports facts with sources; it never prices anything."}
      </p>
      {sendError && (
        <p className="mt-2 max-w-[65ch] text-sm text-negative" role="alert">
          {sendError}
        </p>
      )}
    </div>
  );

  return (
    <section className="mt-6 rounded-2xl border bg-card p-4 sm:p-6 xl:p-8">
      <div className="mb-3 flex items-center gap-2">
        <CrewAvatar kind="scout" className="h-7 w-7 shrink-0" />
        <h2 className="text-lg font-semibold xl:text-xl">The scout desk</h2>
      </div>

      {error ? (
        <p className="max-w-[65ch] text-sm text-muted">{error}</p>
      ) : state === null ? (
        <p className="max-w-[65ch] text-sm text-muted">Checking the desk&hellip;</p>
      ) : state.state === "never_sent" ? (
        <div className="space-y-3">
          <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
            The desk has not been sent on this game. Send it and two staff
            scouts — one per team — will file notes on player status, team
            status, and conditions at the venue, and the master scout will
            read their notes back as one board.
          </p>
          {sendButton("Send the scouts")}
        </div>
      ) : state.status === "running" && !state.gone_quiet ? (
        <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
          The desk is out on {state.event_title}: the {state.home_team} scout,
          the {state.away_team} scout, then the master. This takes a few
          minutes; the board appears here when they file.
        </p>
      ) : state.status === "running" && state.gone_quiet ? (
        <div className="space-y-3">
          <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
            The desk went quiet — a convening started {when(state.requested_ms)}{" "}
            and never filed, which usually means the process restarted under
            it. Nothing more will arrive from that convening.
          </p>
          {sendButton("Send them again", true)}
        </div>
      ) : state.status === "refused" ? (
        <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
          The desk was refused by the day&rsquo;s budget:{" "}
          {state.refusal_reason ?? "the daily call ceiling"}. Nothing was
          spent. The day rolls over on its own.
        </p>
      ) : state.status === "failed" ? (
        <div className="space-y-3">
          <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
            The desk was sent {when(state.requested_ms)} and nothing came back
            — both scouts&rsquo; calls failed. The calls were still metered.
          </p>
          {sendButton("Send them again", true)}
        </div>
      ) : (
        (() => {
          const derived = !state.briefing?.board?.length;
          const tiles = derived
            ? deriveBoard(state.staff)
            : state.briefing!.board!;
          return (
        <div className="space-y-4">
          <VerdictStrip
            fresh={tiles.some((t) => t.state === "fresh")}
            unconfirmed={
              tiles.some((t) => t.state === "unconfirmed") ||
              tiles.length < CATEGORY_ORDER.length
            }
          />

          <Board tiles={tiles} derived={derived} />

          {state.briefing ? (
            <>
              <p className="max-w-[65ch] text-sm font-semibold leading-snug xl:text-base">
                {state.briefing.headline}
              </p>
              <details className="rounded-xl border px-3 py-2">
                <summary className="cursor-pointer text-sm font-semibold">
                  The master&rsquo;s read
                </summary>
                <div className="mt-2 space-y-3">
                  <p className="max-w-[65ch] text-sm leading-relaxed xl:text-[15px]">
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
            <p className="max-w-[65ch] text-sm leading-relaxed text-muted">
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
            <div className="mt-2">{sendButton("Send them again", true)}</div>
          </div>
        </div>
          );
        })()
      )}
    </section>
  );
}
