"use client";

/**
 * The scout desk on one game's screen (ADR 0060).
 *
 * Joe's design: a master scout with a staff -- one specialist per club, each
 * covering their own team's player status, team status, and (for the host's
 * scout) the weather at their park -- and the master collecting their notes
 * into the read that greets him at the desk.
 *
 * Three honesty rules, all load-bearing:
 * - **No number ever renders here that could feed a bet.** The desk's schema
 *   has no field for one; this component adds none.
 * - **"Filed nothing" is not "found nothing".** A dead scout renders as a
 *   dark side of the desk, an empty filing as "looked, nothing noteworthy".
 * - **A convening that went quiet says so.** The POST answers `accepted`,
 *   never `briefed`; a `running` row past the backend's patience window is
 *   rendered as gone quiet rather than spinning forever.
 *
 * Sending costs three metered Anthropic calls from the same 24-call day the
 * Skeptic draws on, and the button says so before it is tapped.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DISPLAY_TIME_ZONE,
  fetchScoutBriefing,
  sendScoutDesk,
  type ScoutBriefingState,
  type ScoutStaffNote,
} from "@/lib/api";
import CrewAvatar from "@/components/CrewAvatar";

const POLL_MS = 5_000;

const CATEGORY_LABELS: Record<string, string> = {
  injury: "injury",
  lineup: "lineup",
  weather: "weather",
  rest_travel: "rest & travel",
  venue: "venue",
  other: "note",
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

function StaffNoteCard({ note }: { note: ScoutStaffNote }) {
  return (
    <div className="rounded-xl border p-3">
      <div className="mb-2 flex items-center gap-2">
        <CrewAvatar kind="scout" className="h-6 w-6 shrink-0" />
        <span className="text-sm font-semibold">The {note.team} scout</span>
        <span className="text-xs text-muted">
          {note.role === "home" ? "home side, covers the park" : "away side"}
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
              <span className="mr-2 rounded bg-card px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
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
                  <span className="ml-1 italic">
                    — old enough that every venue has likely priced it in
                  </span>
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
            scouts — one per club — will file notes on player status, team
            status, and conditions at the park, and the master scout will read
            their notes back as one briefing.
          </p>
          {sendButton("Send the scouts")}
        </div>
      ) : state.status === "running" && !state.gone_quiet ? (
        <p className="text-sm leading-relaxed text-muted">
          The desk is out on {state.event_title}: the {state.home_team} scout,
          the {state.away_team} scout, then the master. This takes a few
          minutes; the briefing appears here when they file.
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
        <div className="space-y-3">
          <p className="text-sm leading-relaxed text-muted">
            The desk was refused by the day&rsquo;s budget:{" "}
            {state.refusal_reason ?? "the daily call ceiling"}. Nothing was
            spent. The day rolls over on its own.
          </p>
        </div>
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
          {state.briefing ? (
            <div>
              <p className="text-base font-semibold leading-snug">
                {state.briefing.headline}
              </p>
              <p className="mt-2 text-sm leading-relaxed">
                {state.briefing.assessment}
              </p>
              {state.briefing.what_matters.length > 0 && (
                <div className="mt-3">
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
                <div className="mt-3">
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
                <div className="mt-3">
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
          ) : (
            <p className="text-sm leading-relaxed text-muted">
              The staff filed, but the master&rsquo;s synthesis is missing —
              the day&rsquo;s budget could not afford it, or his call failed.
              The raw notes below are still the desk&rsquo;s work.
            </p>
          )}

          {state.staff && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                The staff&rsquo;s notes
              </h3>
              {state.staff.map((note) => (
                <StaffNoteCard key={note.role} note={note} />
              ))}
            </div>
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
