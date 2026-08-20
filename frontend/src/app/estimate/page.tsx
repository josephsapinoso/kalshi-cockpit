"use client";

/**
 * The calibration bet log's entry form. One ticker tap and one number,
 * budgeted at ~12 seconds on a phone (registration §9.4).
 *
 * Three rules are load-bearing and none is decoration:
 *
 * - **No price appears on this screen, ever.** The backend captures the
 *   market's book at estimate time for the anchoring tripwires and embargoes
 *   it until the study stops. The search payload carries no quote fields, so
 *   this page cannot leak what it never receives.
 * - **The "had you already opened Kalshi?" tap comes BEFORE the probability
 *   input enables** (§9.2). It is the one recorded signal about the hole the
 *   two clocks cannot close, and asking it after the number would let the
 *   number contaminate the answer.
 * - **P(YES), always** -- never "probability my side wins". The estimate can
 *   be formed before choosing a side, which is a strictly more pre-price act;
 *   the venue reports which side was actually taken.
 */

import { useEffect, useRef, useState } from "react";

import Term from "@/components/Term";

import {
  DISPLAY_TIME_ZONE,
  engageLockout,
  fetchRecentEstimates,
  fetchStudyStop,
  logEstimate,
  reviseEstimate,
  searchEstimateMarkets,
  type EstimateLogged,
  type EstimateMarket,
  type RecentEstimate,
  type StudyStop,
} from "@/lib/api";

/** 6250 bp -> "62.50%". Rendering only; the record keeps the integer. */
function bpToPercent(bp: number): string {
  return `${(bp / 100).toFixed(2)}%`;
}

/** "62.5" -> 6250, or null when the text is not a probability. */
function percentToBp(text: string): number | null {
  const value = Number.parseFloat(text.replace(",", "."));
  if (!Number.isFinite(value)) return null;
  const bp = Math.round(value * 100);
  if (bp < 1 || bp > 9999) return null;
  return bp;
}

export default function EstimatePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<EstimateMarket[]>([]);
  const [searching, setSearching] = useState(false);
  const [market, setMarket] = useState<EstimateMarket | null>(null);
  const [opened, setOpened] = useState<0 | 1 | null>(null);
  const [percent, setPercent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [saved, setSaved] = useState<EstimateLogged | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentEstimate[]>([]);
  const [revising, setRevising] = useState<number | null>(null);
  const [reason, setReason] = useState("");
  const [stop, setStop] = useState<StudyStop | null>(null);
  // Set the instant the tap lands, so the lock is visible without a refetch.
  const [localLockout, setLocalLockout] = useState<number | null>(null);
  const [lockingOut, setLockingOut] = useState(false);
  const [extremeConfirmed, setExtremeConfirmed] = useState(false);
  const probabilityInput = useRef<HTMLInputElement>(null);

  const loadRecent = () =>
    fetchRecentEstimates()
      .then((payload) => setRecent(payload.estimates))
      .catch(() => setRecent([]));

  useEffect(() => {
    loadRecent();
    // The money arm's strip. Over the venue's settlement record, never the
    // estimate log — A7 rules that embargo-safe. The server enforces the
    // stop regardless (423); this is the honest dashboard, not the control.
    fetchStudyStop()
      .then(setStop)
      .catch(() => setStop(null));
  }, []);

  // Debounced search. Two characters before the first request, so a single
  // tapped letter does not sweep the whole market table.
  useEffect(() => {
    if (market) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const timer = setTimeout(() => {
      searchEstimateMarkets(trimmed)
        .then((payload) => setResults(payload.markets))
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, market]);

  const bp = percentToBp(percent);
  // The extreme-value confirm: below 3% or above 97%, one extra tap. The
  // plain-sentence echo below the input catches "0.6"-for-60% on read; this
  // catches it on ACTION, because the write-once trigger makes the mistyped
  // row permanent and the revision path is the only undo. Symmetric tails,
  // deliberately: both are where a dropped decimal lands (0.6, 99.5) and
  // where a genuine estimate is rare.
  const isExtreme = bp !== null && (bp < 300 || bp > 9700);

  const reset = () => {
    setQuery("");
    setResults([]);
    setMarket(null);
    setOpened(null);
    setPercent("");
    setSaved(null);
    setError(null);
    setExtremeConfirmed(false);
  };

  const submit = async () => {
    if (!market || opened === null || bp === null || submitting) return;
    if (isExtreme && !extremeConfirmed) {
      // First tap arms the confirm; the button re-labels with the sentence.
      setExtremeConfirmed(true);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const logged = await logEstimate({
        ticker: market.ticker,
        stated_probability_bp: bp,
        had_already_opened_kalshi: opened,
        estimate_client_ms: Date.now(),
      });
      setSaved(logged);
      loadRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Logging failed.");
    } finally {
      setSubmitting(false);
    }
  };

  // Active lockout: the tap's own answer wins over the fetched strip, and an
  // expired release renders nothing — "you said not tonight, and tonight
  // ended" must not become a nag.
  const lockedUntil =
    localLockout !== null && localLockout > Date.now()
      ? localLockout
      : stop?.lockout_until_ms != null && stop.lockout_until_ms > Date.now()
        ? stop.lockout_until_ms
        : null;

  const notTonight = async () => {
    if (lockingOut) return;
    setLockingOut(true);
    setError(null);
    try {
      const { until_ms } = await engageLockout();
      setLocalLockout(until_ms);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lockout failed.");
    } finally {
      setLockingOut(false);
    }
  };

  const flagRevised = async (id: number) => {
    const text = reason.trim();
    if (!text) return;
    try {
      await reviseEstimate(id, text);
      setRevising(null);
      setReason("");
      loadRecent();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Revision failed.");
    }
  };

  return (
    <main className="mx-auto w-full max-w-xl px-4 py-8">
      <header className="mb-6">
        <h1 className="display text-4xl">Log an estimate</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Your <Term k="p_yes">P(YES)</Term>, recorded before the bet. Type it{" "}
          <strong>before opening Kalshi</strong> &mdash; the record is only
          worth keeping if the number came first.
        </p>
      </header>

      {/* The money arm, always in view. "$X of $100" is summed over the
          venue's own settlements — Joe's wallet, which he sees in the Kalshi
          app anyway — never over the estimate log, which is why A7 rules it
          embargo-safe. No win rate, no per-bet attribution, no study-scoped
          P&L: those ARE the estimate log and stay embargoed until the stop. */}
      {stop !== null &&
        (stop.study_state === "stopped_without_result" ? (
          <section className="mb-6 rounded-2xl border bg-card p-5">
            <div className="text-xs font-semibold uppercase tracking-widest text-muted">
              Study stopped
            </div>
            <p className="mt-2 text-sm leading-relaxed text-muted">
              You closed the calibration study on{" "}
              {new Date(stop.stopped_by_owner_ms).toLocaleDateString("en-US", {
                timeZone: DISPLAY_TIME_ZONE,
                month: "long",
                day: "numeric",
              })}
              , without a result. Nothing was scored then, and nothing entered
              here is scored now &mdash; the $100 stop never fired. Starting
              again would be a fresh study, not a resume.
            </p>
          </section>
        ) : stop.stopped === true ? (
          <section className="mb-6 rounded-2xl border border-negative/50 bg-negative/10 p-5">
            <div className="text-xs font-semibold uppercase tracking-widest text-negative">
              Study stopped
            </div>
            <p className="mt-2 text-sm leading-relaxed">
              The $100 stop has fired:{" "}
              <Term k="realised_loss">realised loss</Term> since the study
              opened reached ${stop.loss_dollars?.toFixed(2)}. Logging is
              closed, permanently.
            </p>
          </section>
        ) : stop.stopped === null ? (
          <p className="mb-6 rounded-xl border bg-card px-4 py-3 text-xs text-muted">
            The $100 stop: the record can&rsquo;t be read right now, so the
            loss figure is unknown. Logging still works.
          </p>
        ) : (
          <p className="mb-6 rounded-xl border bg-card px-4 py-3 text-sm">
            <span className="font-semibold">
              ${Math.max(stop.loss_dollars ?? 0, 0).toFixed(2)}
            </span>{" "}
            of the ${stop.ceiling_dollars.toFixed(0)} stop used &mdash;{" "}
            <Term k="realised_loss">realised loss</Term> since the study
            opened.
            {/* The "(you're net up $X)" parenthetical was deleted here on
                2026-08-20 (fleet convening item 5). A signed running P&L on
                the screen where bets begin is the chase trigger the tilt
                review refused — winning reads as licence exactly the way
                losing reads as a hole to fill. The stop line above is a cap,
                not a score. */}
          </p>
        ))}

      {/* One tap of "not tonight" (fleet convening item 10). Rendered only
          while it would do something: not during a lockout, not after the
          permanent stop. No confirm step — the whole point is that the
          moment of clarity is brief, and a dialog gives the impulse a veto. */}
      {stop?.stopped !== true && lockedUntil === null && (
        <button
          onClick={notTonight}
          disabled={lockingOut}
          className="mb-6 w-full rounded-xl border border-border px-4 py-3 text-sm text-muted transition-colors hover:border-accent-2/60 hover:text-accent-2"
        >
          {lockingOut
            ? "Locking…"
            : "Not tonight — lock the log until the day rolls over"}
        </button>
      )}

      {stop?.stopped === true ? null : lockedUntil !== null ? (
        <section className="rounded-2xl border bg-card p-5">
          <div className="text-xs font-semibold uppercase tracking-widest text-muted">
            Locked, at your request
          </div>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            You said not tonight. Logging opens again at{" "}
            {new Date(lockedUntil).toLocaleTimeString("en-US", {
              timeZone: DISPLAY_TIME_ZONE,
              hour: "numeric",
              minute: "2-digit",
            })}
            . There is no early unlock — that is the point. The server
            enforces this too; hiding the form is a courtesy, not the control.
          </p>
        </section>
      ) : saved ? (
        <section className="rounded-2xl border bg-card p-6">
          <div className="text-xs font-semibold uppercase tracking-widest text-accent">
            Logged
          </div>
          <p className="mt-3 font-mono text-sm">{saved.ticker}</p>
          <p className="mt-1 text-3xl font-semibold">
            {bpToPercent(saved.stated_probability_bp)}
          </p>
          <p className="mt-1 text-xs text-muted">
            P(YES), stamped{" "}
            {new Date(saved.estimate_server_ms).toLocaleTimeString("en-US", {
              timeZone: DISPLAY_TIME_ZONE,
            })}{" "}
            by the server. It cannot be edited &mdash; mistyped it? Flag it
            below and log a fresh one.
          </p>
          <button
            onClick={reset}
            className="mt-5 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white"
          >
            Log another
          </button>
        </section>
      ) : (
        <section className="rounded-2xl border bg-card p-6">
          {/* Step 1: the market, one tap. */}
          {market === null ? (
            <>
              <label
                htmlFor="market-search"
                className="text-xs font-semibold uppercase tracking-widest text-muted"
              >
                1 &middot; Market
              </label>
              <input
                id="market-search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Team, player or ticker&hellip;"
                autoComplete="off"
                className="mt-2 w-full rounded-xl border bg-background px-4 py-3 text-base"
              />
              {searching && (
                <p className="mt-3 text-sm text-muted">Searching&hellip;</p>
              )}
              <ul className="mt-3 space-y-2">
                {results.map((item) => (
                  <li key={item.ticker}>
                    <button
                      onClick={() => setMarket(item)}
                      className="w-full rounded-xl border px-4 py-3 text-left"
                    >
                      <span className="block text-sm font-medium">
                        {item.title ?? item.ticker}
                        {item.player_name ? ` — ${item.player_name}` : ""}
                      </span>
                      <span className="mt-0.5 block font-mono text-xs text-muted">
                        {item.ticker}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {query.trim().length >= 2 && !searching && results.length === 0 && (
                <div className="mt-3 text-sm text-muted">
                  <p>
                    Nothing discovered by that name. If you know the exact
                    ticker, use it directly:
                  </p>
                  <button
                    onClick={() =>
                      setMarket({
                        ticker: query.trim().toUpperCase(),
                        title: null,
                        player_name: null,
                        event_ticker: null,
                        event_title: null,
                        close_ms: null,
                      })
                    }
                    className="mt-2 w-full rounded-xl border px-4 py-3 text-left font-mono text-sm"
                  >
                    Use &ldquo;{query.trim().toUpperCase()}&rdquo;
                  </button>
                </div>
              )}
            </>
          ) : (
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-xs font-semibold uppercase tracking-widest text-muted">
                  Market
                </div>
                <p className="mt-1 text-sm font-medium">
                  {market.title ?? market.ticker}
                  {market.player_name ? ` — ${market.player_name}` : ""}
                </p>
                <p className="font-mono text-xs text-muted">{market.ticker}</p>
              </div>
              <button
                onClick={() => {
                  setMarket(null);
                  setOpened(null);
                  setPercent("");
                }}
                className="rounded-lg border px-3 py-1.5 text-xs text-muted"
              >
                Change
              </button>
            </div>
          )}

          {/* Step 2: the honesty tap, BEFORE the number input enables (§9.2). */}
          {market !== null && (
            <div className="mt-6">
              <div className="text-xs font-semibold uppercase tracking-widest text-muted">
                2 &middot; Have you already opened Kalshi and seen this
                market&rsquo;s price?
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2">
                {([0, 1] as const).map((value) => (
                  <button
                    key={value}
                    onClick={() => {
                      setOpened(value);
                      // The number field enables now; put the cursor in it so
                      // the whole flow stays inside the 12-second budget.
                      setTimeout(() => probabilityInput.current?.focus(), 0);
                    }}
                    className={`rounded-xl border px-4 py-3 text-sm font-semibold ${
                      opened === value
                        ? "border-accent bg-accent/10 text-accent"
                        : ""
                    }`}
                  >
                    {value === 0 ? "No" : "Yes"}
                  </button>
                ))}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted">
                Answer honestly &mdash; it is recorded, not judged. A
                &ldquo;yes&rdquo; still counts; it is just labelled.
              </p>
            </div>
          )}

          {/* Step 3: the measurement itself. */}
          {market !== null && (
            <div className="mt-6">
              <label
                htmlFor="p-yes"
                className="text-xs font-semibold uppercase tracking-widest text-muted"
              >
                3 &middot; Your <Term k="p_yes">P(YES)</Term>, percent
              </label>
              <input
                id="p-yes"
                ref={probabilityInput}
                value={percent}
                onChange={(event) => {
                  setPercent(event.target.value);
                  setExtremeConfirmed(false);
                }}
                disabled={opened === null}
                inputMode="decimal"
                placeholder={opened === null ? "answer step 2 first" : "62.5"}
                autoComplete="off"
                className="mt-2 w-full rounded-xl border bg-background px-4 py-3 text-2xl font-semibold disabled:opacity-40"
              />
              {/* A plain sentence, not a bp echo. "0.6" meaning 0.60% passed
                  every check and rendered as "60 bp" -- a fat-finger the
                  write-once trigger makes permanent. "a 0.60% chance the
                  market ends YES" is the echo a tired thumb actually reads. */}
              <p className="mt-2 text-xs text-muted">
                Probability the market resolves <strong>YES</strong> &mdash;
                not your side. 0.01 to 99.99.
                {bp !== null && (
                  <span className="ml-2 font-semibold text-foreground">
                    = a {bpToPercent(bp)} chance the market ends YES
                  </span>
                )}
              </p>
              <button
                onClick={submit}
                disabled={opened === null || bp === null || submitting}
                className={`mt-4 w-full rounded-xl px-4 py-3 text-sm font-semibold text-white disabled:opacity-40 ${
                  isExtreme && extremeConfirmed ? "bg-negative" : "bg-accent"
                }`}
              >
                {submitting
                  ? "Logging…"
                  : isExtreme && extremeConfirmed && bp !== null
                    ? `Yes — a ${bpToPercent(bp)} chance of YES. Log it.`
                    : isExtreme
                      ? "Log it (extreme — will ask once)"
                      : "Log it"}
              </button>
              {isExtreme && extremeConfirmed && bp !== null && (
                <p className="mt-2 text-xs leading-relaxed text-negative">
                  {bpToPercent(bp)} is a near-{bp < 300 ? "certain NO" : "certain YES"}.
                  If you meant {bp < 300 ? "a percent like 60, not 0.60" : "something lower"},
                  fix the number &mdash; once logged it cannot be edited.
                </p>
              )}
            </div>
          )}

        </section>
      )}

      {/* Outside the saved/form ternary on purpose: a failed REVISION sets
          this state while the "Logged" card is showing, and an error block
          scoped to the form branch rendered that failure as silence -- on the
          one recovery path a write-once record has. */}
      {error && (
        <p className="mt-4 rounded-xl border border-negative/50 bg-negative/10 px-4 py-3 text-sm text-negative">
          {error}
        </p>
      )}

      {/* The record so far -- what was typed, never what the server captured. */}
      {recent.length > 0 && (
        <section className="mt-8">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Recent entries
          </h2>
          <ul className="mt-3 space-y-2">
            {recent.map((entry) => (
              <li key={entry.id} className="rounded-xl border bg-card px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="min-w-0 flex-1 truncate font-mono text-xs text-muted">
                    {entry.ticker}
                  </span>
                  <span className="text-sm font-semibold">
                    {bpToPercent(entry.stated_probability_bp)}
                  </span>
                </div>
                <div className="mt-1 flex items-center justify-between gap-3">
                  <span className="text-xs text-muted">
                    {new Date(entry.estimate_server_ms).toLocaleString("en-US", {
                      timeZone: DISPLAY_TIME_ZONE,
                    })}
                    {entry.stated_probability_is_revised === 1 && (
                      <span className="ml-2 font-semibold text-negative">
                        revised &mdash; excluded
                      </span>
                    )}
                  </span>
                  {entry.stated_probability_is_revised === 0 &&
                    (revising === entry.id ? (
                      <span className="flex items-center gap-2">
                        <input
                          value={reason}
                          onChange={(event) => setReason(event.target.value)}
                          placeholder="why?"
                          autoComplete="off"
                          className="w-28 rounded-lg border bg-background px-2 py-1 text-xs"
                        />
                        <button
                          onClick={() => flagRevised(entry.id)}
                          disabled={reason.trim().length === 0}
                          className="text-xs font-semibold text-negative disabled:opacity-40"
                        >
                          Flag
                        </button>
                        <button
                          onClick={() => {
                            setRevising(null);
                            setReason("");
                          }}
                          className="text-xs text-muted"
                        >
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <button
                        onClick={() => setRevising(entry.id)}
                        className="text-xs text-muted underline"
                      >
                        Mistyped?
                      </button>
                    ))}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
