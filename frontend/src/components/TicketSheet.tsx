"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  formatAge,
  formatKickoff,
  isLockedDetail,
  newIntentKey,
  placeOrder,
  refusalText,
  type LockedDetail,
  type OrderPlaced,
  type OrderResult,
  type Recommendation,
} from "@/lib/api";
import { betDirection } from "@/lib/betDirection";
import { focusWrap, type TrapPosition } from "@/lib/focusWrap";
import Term from "@/components/Term";

/**
 * The ticket: tap a card, see what the bet is, confirm it.
 *
 * Three rules shape everything below, and each of them is a thing this repo has
 * already been bitten by.
 *
 * **1. Nothing here does arithmetic on money.** Not the fee, not the edge, not
 * the cost, not the size. Every money figure on this sheet is a number the
 * server computed and sent, rendered as it arrived. The fee curve is an
 * unresolved hedge between two disagreeing sources (`core/fees.py`); shipping a
 * copy of it to the browser so this could multiply out a total would put two
 * implementations of a money calculation one refresh apart. Where a number is
 * genuinely absent the sheet says so rather than deriving it. The fee-inclusive
 * total used to be one of those; the read routes now send it, so it is
 * rendered rather than explained away. See `tasks/inbox/frontend.md`.
 *
 * **2. Everything above the button is a preview; everything below the answer is
 * authoritative.** The endpoint takes a recommendation id and a size and
 * re-derives the rest, including re-reading Kalshi and *clamping the size down*.
 * So the figures on the ticket are what the bet was recorded at, and the
 * response is what the server actually did. The two are labelled differently on
 * screen on purpose: presenting the preview as the price you will pay is how a
 * page comes to look like it is disagreeing with the server.
 *
 * **3. A disabled button is a hint to a human, not a control.** Every server
 * refusal is rendered anyway, because the server is the control and it refuses
 * for a dozen reasons this page cannot see.
 *
 * The realistic outcome of confirming today is **423, the locked gate**. That is
 * not an error path to be tucked into a toast -- it is the screen a person on a
 * phone will actually get, so it is the most carefully built state here.
 *
 * **There is no `!actionable` state on this sheet, and there never reachably
 * was one (found 2026-08-18, removed 2026-08-22).** `routes.py` sorts a row
 * into `board.surfaced` only when `item["actionable"]` is true; `LiveBoard`
 * renders `board.surfaced` only; and `TicketTrigger` -- this sheet's sole
 * opener -- passes no override. A row can only ever reach Confirm already
 * actionable, so the amber "aged out" note, the extra disabled term on the
 * stepper, and the "Off because..." caption branch were dead on arrival.
 */

type Phase = "ticket" | "sending" | "answered";

export default function TicketSheet({
  rec,
  demo,
  quoteLimitMs,
  oddsLimitMs,
  token,
  onToken,
  onClose,
}: {
  rec: Recommendation;
  /** Demo instances hold no credentials; the order route answers 403. */
  demo: boolean;
  quoteLimitMs: number;
  oddsLimitMs: number;
  token: string;
  onToken: (value: string) => void;
  onClose: () => void;
}) {
  const authorised = rec.suggested_contracts;
  const [contracts, setContracts] = useState(authorised);
  const [phase, setPhase] = useState<Phase>("ticket");
  const [result, setResult] = useState<OrderResult | null>(null);

  const sheet = useRef<HTMLDivElement>(null);
  // Held in refs so the modal effect below can keep empty deps. With `phase` in
  // the dependency list the effect tore down and re-ran on every send, which
  // yanked focus back to the top of the sheet mid-request and, on close,
  // restored focus to whatever had been active at that moment rather than to
  // the card that was tapped.
  const busy = useRef(false);
  const close = useRef(onClose);
  busy.current = phase === "sending";
  close.current = onClose;

  useEffect(() => {
    const node = sheet.current;
    if (!node) return;
    const opener = document.activeElement as HTMLElement | null;
    node.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Not while a request is in flight: the order may already have been
        // decided, and closing the sheet would discard the only report of it.
        if (busy.current) return;
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = node.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),summary,[tabindex]:not([tabindex="-1"])',
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      // `panel` is a real case and it used to have no branch. `node` is
      // `tabIndex={-1}` and `querySelectorAll` returns descendants only, so the
      // panel is in neither end of that list -- while being exactly what holds
      // focus after `node.focus()`, which runs on open and on every phase
      // change. Both comparisons were therefore false, nothing prevented the
      // default, and Shift+Tab walked backwards onto the veil and out of the
      // modal. `focusWrap` has the branch; see its module docstring.
      const active = document.activeElement;
      const position: TrapPosition =
        active === node
          ? "panel"
          : active === first
            ? "first"
            : active === last
              ? "last"
              : "inside";
      const wrap = focusWrap(position, event.shiftKey);
      if (wrap === null) return;
      event.preventDefault();
      (wrap === "first" ? first : last).focus();
    };

    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      opener?.focus?.();
    };
  }, []);

  // Focus follows the content, and this effect is separate from the one above
  // on purpose: that one installs listeners and must keep empty deps, this one
  // must run on every phase change.
  //
  // Confirm, Back, and the disabling of Confirm while a request is in flight
  // all remove the element that currently holds focus. The browser then drops
  // focus onto `<body>` -- outside the sheet, where the Tab handler's
  // wrap-around cannot fire, because it only acts when focus is already on the
  // first or last control *inside* the panel. So the trap silently opens at
  // the exact moment the answer appears, and the next Tab walks into the page
  // behind the veil. Measured: after Confirm, `document.activeElement` was
  // `<body>` at 320, 390 and 430px.
  useEffect(() => {
    const node = sheet.current;
    if (node && !node.contains(document.activeElement)) node.focus();
  }, [phase]);

  // One key per *intent*, minted when the sheet opens and stable for as long as
  // it stays open. That is the whole mechanism: both halves of a double-tap,
  // and a retry after a dropped connection, carry the same key, so the server
  // answers the second one with the first one's order instead of placing a
  // second. A key minted inside `confirm` would be a fresh one per tap and
  // would protect nothing at all.
  //
  // `useRef` rather than `useState` because it must not be a render input --
  // and `useRef(crypto.randomUUID())` would re-evaluate the argument on every
  // render, discarding the value but doing the work. The lazy form is the one
  // that actually holds still.
  const intentKey = useRef<string>("");
  if (!intentKey.current) intentKey.current = newIntentKey();

  const confirm = useCallback(async () => {
    setPhase("sending");
    setResult(null);
    const outcome = await placeOrder(
      rec.id,
      contracts,
      intentKey.current,
      token || undefined,
    );
    setResult(outcome);
    setPhase("answered");
    // The answer is the point of the interaction and it renders where the
    // ticket was, so put the reader at the top of it rather than wherever they
    // had scrolled to reach the button.
    sheet.current?.scrollTo?.({ top: 0, behavior: "smooth" });
  }, [rec.id, contracts, token]);

  const quoteAge = rec.quote_age_now_ms ?? rec.kalshi_quote_age_ms;
  // The heading below is `rec.team`, which is the YES-side team on every row
  // including the ones that buy NO. This is the sentence that says which way
  // round the bet actually goes; see `lib/betDirection.ts`.
  const direction = betDirection(rec);
  const priceStale = rec.price_is_current === false;
  const resized = contracts !== authorised;
  const needsToken = !demo && token.trim().length === 0;

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end lg:items-center lg:justify-center lg:p-6">
      {/* Bottom sheet on a phone; centred dialog from `lg`. Unconstrained,
          the sheet's `w-full` panel put a monitor-wide filled Confirm on the
          order path at 2560px — the largest, brightest control this app had
          ever drawn, on the one screen that spends money. */}
      <button
        type="button"
        aria-label="Close the ticket"
        className="veil-in absolute inset-0 h-full w-full cursor-default bg-black/50"
        onClick={() => {
          if (phase !== "sending") onClose();
        }}
      />

      <div
        ref={sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ticket-heading"
        tabIndex={-1}
        className="sheet-panel sheet-rise relative flex w-full flex-col overflow-y-auto rounded-t-2xl border-t bg-card shadow-2xl outline-none lg:max-w-xl lg:rounded-2xl lg:border"
      >
        <div className="sticky top-0 z-10 border-b bg-card px-4 pb-3 pt-2 sm:px-6">
          {/* The drag affordance is a phone gesture; on a pointer it is a
              decoration that promises a drag that does nothing. */}
          <div
            aria-hidden
            className="mx-auto mb-3 h-1 w-10 rounded-full bg-[var(--border)] lg:hidden"
          />
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <h2
                id="ticket-heading"
                className="truncate text-lg font-bold tracking-tight"
              >
                {rec.team ?? rec.ticker}
              </h2>
              {/* The heading above names the YES-side team on every row, so on
                  a NO row it is the team this bet pays out *against*. The `NO`
                  pill in the meta row is the only other correction on screen
                  and a pill reads as a tag, not as a negation.

                  Deliberately not truncated: the team name is the payload here,
                  and "betting against New Yor..." would be a worse failure than
                  a second line. It wraps instead.

                  No colour. `against` is not a warning -- it is which bet this
                  is -- and the accent is spoken for. The preposition carries
                  the meaning, so the preposition is the emphasis. */}
              {direction && (
                <p className="mt-1 text-sm leading-snug">
                  You are betting{" "}
                  <strong className="font-bold">{direction.preposition}</strong>{" "}
                  {direction.team}.
                </p>
              )}
              <p className="mt-0.5 truncate text-sm text-muted">
                {rec.event_title ?? rec.ticker}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={phase === "sending"}
              // 44px tall, which is taller than it looks: it is the width of a
              // thumb, and this is one of the three ways out of a sheet that
              // covers the whole screen. It measured 59x26 before, which is a
              // target you aim at rather than press.
              className="-mr-1 inline-flex min-h-11 shrink-0 items-center rounded-full border px-4 text-xs font-semibold disabled:opacity-40"
            >
              Close
            </button>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-xs text-muted">
            <span className="rounded bg-accent-soft px-1.5 py-0.5 uppercase text-accent">
              {rec.side}
            </span>
            <span className="break-all">{rec.ticker}</span>
            {rec.commence_ms && <span>{formatKickoff(rec.commence_ms)}</span>}
          </div>
        </div>

        <div className="min-w-0 flex-1 px-4 py-4 sm:px-6">
          {phase === "answered" && result ? (
            <Answer result={result} />
          ) : (
            <>
              <Section
                label="The ticket"
                note={
                  "The bet as it was recorded. Confirming reads Kalshi again " +
                  "and prices and sizes against what it says then."
                }
              >
                <div className="grid grid-cols-2 gap-x-4 gap-y-4">
                  {/* A percentage. The `c` form of this number sat beside the
                      ask at the same size and read as a second price. */}
                  {/* Terms on the money screen (2026-08-22 review, A4): the
                      one place a novice is a tap from an order had zero
                      self-teaching words. Labels stay identical; each now
                      opens its definition. */}
                  <Figure
                    label={<Term k="consensus">Consensus fair</Term>}
                    value={rec.fair_percent_display}
                  />
                  <Figure
                    label={<Term k="ask">Kalshi asks</Term>}
                    value={rec.ask_display}
                  />
                  <Figure
                    label={<Term k="edge">Edge, net of fees</Term>}
                    value={`${rec.edge_cents > 0 ? "+" : ""}${rec.edge_cents.toFixed(1)}c`}
                    tone={rec.edge_cents > 0 ? "positive" : "negative"}
                  />
                  <Figure
                    label="Engine authorised"
                    value={`${authorised}`}
                    unit={<Term k="contract">contracts</Term>}
                  />
                </div>

                {/* Fee and expected value were computed by the server for the
                    authorised size. Re-scaling them here for a smaller order
                    would be the browser doing fee arithmetic -- the one thing
                    this sheet may not do -- and the fee does not scale
                    linearly anyway: it rounds up on the whole order. So at any
                    other size they are withdrawn rather than adjusted. */}
                <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 border-t pt-4">
                  <Figure
                    label={<Term k="fee">Predicted fee</Term>}
                    value={resized ? "—" : dollars(rec.fee_predicted)}
                    muted={resized}
                  />
                  {/* The fee-inclusive figure the server now sends for the
                      authorised size. It replaces the sentence that used to
                      sit at the bottom of this section saying there was no
                      total -- which was true only because the payload did not
                      carry one, never because a total was unwanted. */}
                  <Figure
                    label="Total cost"
                    value={resized ? "—" : dollars(rec.total_cost_dollars)}
                    muted={resized}
                  />
                  <Figure
                    label={<Term k="ev">Expected, net</Term>}
                    value={resized ? "—" : signedDollars(rec.ev_net_dollars)}
                    tone={
                      resized
                        ? undefined
                        : rec.ev_net_dollars >= 0
                          ? "positive"
                          : "negative"
                    }
                    muted={resized}
                  />
                  {/* Not the fee, and not scaled by anything here. The one
                      number on this sheet that says what being wrong costs. */}
                  <Figure
                    label={<Term k="sd">Swing, 1 SD</Term>}
                    value={resized ? "—" : dollars(rec.sd_dollars)}
                    muted={resized}
                  />
                </div>
                {resized && (
                  <p className="mt-3 text-xs leading-relaxed text-muted">
                    The fee and the expected value the server sent describe{" "}
                    {authorised} contracts. The fee rounds up on the whole
                    order rather than per contract, so they cannot be scaled to{" "}
                    {contracts} on this page. The response will carry the real
                    numbers for the size that is actually sent.
                  </p>
                )}

                {/* The total is now the server's, for the size on record, and
                    it is still a preview. Both halves are said: the number
                    exists, and the order re-prices. */}
                <p className="mt-4 border-t pt-3 text-xs leading-relaxed text-muted">
                  {resized ? (
                    <>
                      Every figure above describes {authorised} contracts. The
                      order re-prices at whatever Kalshi says when you confirm,
                      and the worst-case cost comes back with the answer.
                    </>
                  ) : (
                    <>
                      The total is the stake plus the predicted fee, for this
                      size at the recorded price. The order re-prices at
                      whatever Kalshi says when you confirm, and the worst-case
                      cost comes back with the answer.
                    </>
                  )}
                </p>
              </Section>

              <Section label="Size">
                {/* Frozen while a request is in flight. `confirm` closes over
                    `contracts`, so the size that was *sent* is always right --
                    but the screen was not: tapping `-` mid-send re-rendered the
                    sheet at the new number, withdrew four money figures to "—",
                    and could show or hide the depth Note, while a request for
                    the old size was still out. The answer then came back naming
                    a size the ticket had stopped displaying.

                    Confirm has carried `phase === "sending"` in its disabled set
                    all along (below); these two were simply left out of it. */}
                <Stepper
                  value={contracts}
                  max={authorised}
                  disabled={phase === "sending"}
                  onChange={setContracts}
                />
                <p className="mt-3 text-xs leading-relaxed text-muted">
                  You propose a size; the server decides one. It re-derives the
                  size at the live price and takes the smaller of the two, so
                  the order can come back smaller than this and never larger.
                </p>
              </Section>

              {priceStale && (
                <Note>
                  The price on this ticket was read{" "}
                  <span className="font-mono">{formatAge(quoteAge)}</span>.
                  Still bettable — confirming reads Kalshi again and prices and
                  sizes against what comes back, so expect the ask, the size and
                  the cost to move.
                </Note>
              )}

              {rec.depth_at_ask !== null && rec.depth_at_ask < contracts && (
                <Note tone="warn">
                  The book showed{" "}
                  <span className="font-mono">
                    {rec.depth_at_ask.toFixed(0)}
                  </span>{" "}
                  resting at this price when the row was written and this order
                  is {contracts}. The server checks the book again and will
                  refuse rather than leave a remainder resting.
                </Note>
              )}

              {demo ? (
                <Note>
                  This is the demo instance. It holds no credentials and has no
                  execution path — confirming will come back refused, which is
                  the point of showing the button at all.
                </Note>
              ) : (
                <Section label="Authorisation">
                  <label
                    htmlFor="ticket-token"
                    className="block text-xs leading-relaxed text-muted"
                  >
                    Signing in gave this browser read access. Placing an order
                    needs the token itself — the session cookie is built so it
                    cannot stand in for one. Held in memory for this page only,
                    never stored.
                  </label>
                  <input
                    id="ticket-token"
                    type="password"
                    autoComplete="off"
                    spellCheck={false}
                    value={token}
                    onChange={(event) => onToken(event.target.value)}
                    disabled={phase === "sending"}
                    placeholder="APP_AUTH_TOKEN"
                    className="mt-2 w-full rounded-lg border bg-transparent px-3 py-2 font-mono text-sm disabled:opacity-40"
                  />
                </Section>
              )}
            </>
          )}
        </div>

        <div className="sheet-safe-bottom sticky bottom-0 z-10 border-t bg-card px-4 pt-3 sm:px-6">
          {phase === "answered" && result ? (
            /* Two buttons at most, and one of them is always Close.
               Three fitted at 390px and turned into a three-line stack of
               wrapped labels at 320 -- which is the width that decides, and the
               one a thumb is worst at. So the secondary action is whichever one
               is actually useful for this refusal, and there is only ever one:
               a retry when the exchange could not be read, a way back to the
               size control when the bet itself was refused, and neither when
               the gate is locked, because nothing on this sheet moves it. */
            <div className="flex gap-3">
              {secondaryAction(result) === "retry" && (
                <button
                  type="button"
                  onClick={confirm}
                  className="flex-1 rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white"
                >
                  Try again
                </button>
              )}
              {secondaryAction(result) === "back" && (
                <button
                  type="button"
                  onClick={() => {
                    setPhase("ticket");
                    setResult(null);
                  }}
                  className="flex-1 rounded-lg bg-accent px-4 py-3 text-sm font-semibold text-white"
                >
                  Back
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                className={`flex-1 rounded-lg px-4 py-3 text-sm font-semibold ${
                  secondaryAction(result) === null
                    ? "bg-accent text-white"
                    : "border"
                }`}
              >
                {result.ok ? "Done" : "Close"}
              </button>
            </div>
          ) : (
            <>
              <button
                type="button"
                onClick={confirm}
                disabled={phase === "sending" || contracts < 1 || needsToken}
                aria-busy={phase === "sending"}
                className="w-full rounded-lg bg-accent px-4 py-3.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                {phase === "sending"
                  ? "Asking the server…"
                  : `Confirm — buy ${contracts}`}
              </button>
              <p className="mt-2 text-center text-xs text-muted">
                {needsToken
                  ? "The token above is required before this can be sent."
                  : "Priced and sized by the server at the moment you tap."}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Which second button, if any, this answer deserves.
 *
 * `retry` only where retrying can change the answer: the exchange could not be
 * read (5xx) or the request never left the handset (0). Every other refusal is
 * a fact about this bet at this price and would answer the same way a thousand
 * times — offering a retry there would be inviting someone to hammer a decision
 * that has already been made.
 *
 * `back` returns to the ticket, which holds the only two things on this sheet a
 * person can change -- the size and the token. Pointless for a locked gate
 * (nothing here moves it), for a 404 (the row is gone), and for a 403 (the
 * instance itself has no execution path, and no size and no token change that),
 * so all three get Close alone. 401 keeps it, because the token field is behind
 * that button and a mistyped token is the likeliest cause.
 */
function secondaryAction(result: OrderResult): "retry" | "back" | null {
  if (result.ok) return null;
  if (result.status === 0 || result.status >= 500) return "retry";
  if (result.status === 423 || result.status === 404 || result.status === 403) {
    return null;
  }
  return "back";
}

/* -------------------------------------------------------------------------
   The answer. Everything below this point is the server's, rendered as it
   arrived.
------------------------------------------------------------------------- */

function Answer({ result }: { result: OrderResult }) {
  if (result.ok) return <Placed order={result.value} />;
  if (result.status === 423 && isLockedDetail(result.detail)) {
    return <GateLocked detail={result.detail} />;
  }
  return <Refused status={result.status} detail={result.detail} />;
}

/**
 * The locked gate. The state a tap on Confirm actually produces today.
 *
 * The 423 body carries both a `reason` -- the unmet conditions joined into one
 * pipe-separated line -- and the conditions themselves. Only the structured
 * list is rendered: the flat string is the same text again, and printing both
 * would put four long paragraphs on a 320px screen twice.
 */
function GateLocked({ detail }: { detail: LockedDetail }) {
  const conditions = detail.conditions ?? [];
  const unmet = conditions.filter((c) => !c.met);

  return (
    <div>
      <Verdict tone="refused" code="423">
        {detail.message ?? "The live gate is locked."}
      </Verdict>

      <p className="mt-3 text-sm leading-relaxed text-muted">
        Nothing was sent to the exchange and nothing was recorded.{" "}
        {conditions.length > 0 ? (
          <>
            {unmet.length} of {conditions.length}{" "}
            {conditions.length === 1 ? "condition is" : "conditions are"} unmet.
            All of them have to be met before an order can leave this machine,
            and they are met by the record accumulating rather than by anything
            on this screen.
          </>
        ) : (
          "The gate reported no conditions with the refusal, which is itself worth reporting."
        )}
      </p>

      {conditions.length > 0 && (
        <ul className="mt-5 divide-y border-t">
          {conditions.map((condition, index) => (
            <li
              key={condition.name ?? index}
              className="flex items-start gap-3 py-4"
            >
              {/* The glyph and the word both. Colour alone is not a channel --
                  the Gate screen uses the same pair for the same reason. */}
              <span
                className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                  condition.met
                    ? "bg-positive/15 text-positive"
                    : "bg-accent-soft text-accent"
                }`}
              >
                {condition.met ? "✓" : "—"}
              </span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="break-all font-mono text-sm font-semibold">
                    {condition.name}
                  </span>
                  <span
                    className={`text-[0.65rem] font-bold uppercase tracking-widest ${
                      condition.met ? "text-positive" : "text-accent"
                    }`}
                  >
                    {condition.met ? "met" : "not met"}
                  </span>
                </div>
                <p className="mt-1 break-words text-sm leading-relaxed text-muted">
                  {condition.detail}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-5 border-t pt-4 text-xs leading-relaxed text-muted">
        This is the expected answer. The gate is locked by default and stays
        locked until the paper record earns it; the Gate screen shows the same
        conditions with the reasoning behind each one.
      </p>
    </div>
  );
}

/**
 * Every other refusal.
 *
 * The endpoint's own sentence is rendered verbatim and is not summarised,
 * re-worded or replaced. There are a dozen distinct refusals on that path and
 * each one names the specific thing that is wrong -- which price moved and by
 * how much, how many contracts rest at the ask, which minimum was missed. A
 * generic "the order was refused" here would throw away the only part of the
 * response worth reading.
 */
function Refused({ status, detail }: { status: number; detail: unknown }) {
  const text = refusalText(detail);
  const retryable = status >= 500;
  const unreachable = status === 0;

  return (
    <div>
      <Verdict tone="refused" code={unreachable ? "no reply" : String(status)}>
        {unreachable
          ? "The cockpit did not answer"
          : status === 401 || status === 403
            ? "Not authorised"
            : status === 404
              ? "That row is gone"
              : retryable
                ? "The exchange could not be read"
                : "The server refused this bet"}
      </Verdict>

      <p className="mt-4 whitespace-pre-line break-words text-sm leading-relaxed">
        {text}
      </p>

      <p className="mt-4 border-t pt-4 text-xs leading-relaxed text-muted">
        {unreachable
          ? "Nothing reached the server, so nothing was decided. Worth trying again once the connection is back."
          : retryable
            ? "This one is worth tapping again — the price could not be read, which is a condition that passes. A refusal about the bet itself would answer the same way however many times you asked."
            : status === 401 || status === 403
              ? "Retrying will not change this. Check the token, or the instance you are on."
              : status === 404
                ? "The Board is showing a row the record no longer has. Reload the Board."
                : "Retrying will not change this: it is a fact about this bet at this price, not a transient. Nothing was sent to the exchange."}
      </p>
    </div>
  );
}

/**
 * The server accepted. **Every number here is the server's**, including ones
 * that contradict the ticket -- especially those.
 *
 * Unknown keys are rendered rather than dropped. The response is being extended
 * by other work in flight, and a panel that showed only the fields it was built
 * against would silently hide the first thing a new field was added to say.
 */
const RENDERED_KEYS = new Set([
  "status",
  "dry_run",
  "client_order_id",
  "order_id",
  "ticker",
  "side",
  "book_side",
  "contracts",
  "limit_price_dollars",
  "limit_price_cents",
  "fill_price_tenths",
  "fill_price_display",
  "price_grid",
  "worst_case_cost_dollars",
  "resulting_exposure_dollars",
  "quote",
  "request_body",
  "note",
]);

function Placed({ order }: { order: OrderPlaced }) {
  const quote = order.quote ?? {};
  const extras = Object.entries(order).filter(
    ([key, value]) =>
      !RENDERED_KEYS.has(key) && (value === null || typeof value !== "object"),
  );

  return (
    <div>
      <Verdict tone={order.dry_run ? "dry" : "placed"} code={order.status}>
        {order.dry_run ? "Dry run — nothing was sent" : "Order placed"}
      </Verdict>

      <p className="mt-3 text-sm leading-relaxed text-muted">
        These are the server&apos;s numbers, not the ticket&apos;s. Where they
        differ from the figures you tapped Confirm on, these are the ones that
        happened.
      </p>

      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 border-t pt-4">
        {order.contracts !== undefined && (
          <Figure
            label="Contracts"
            value={`${order.contracts}`}
            unit="filled size"
          />
        )}
        {/* Two units, never converted. `limit_price_dollars` and
            `limit_price_cents` are the extended and the current shape of the
            same field; turning one into the other here would be the browser
            doing money arithmetic to paper over a rename. */}
        {order.limit_price_dollars !== undefined ? (
          <Figure label="Limit" value={dollars(order.limit_price_dollars)} />
        ) : order.limit_price_cents !== undefined ? (
          <Figure label="Limit" value={`${order.limit_price_cents}c`} />
        ) : null}
        {order.fill_price_display !== undefined && (
          <Figure
            label={<Term k="fill">Fill</Term>}
            value={String(order.fill_price_display)}
          />
        )}
        {order.worst_case_cost_dollars !== undefined && (
          <Figure
            label="Worst-case cost"
            value={dollars(order.worst_case_cost_dollars)}
          />
        )}
        {/* Rendered when the response carries it and absent when it does not.
            Written this way on purpose: the field is being added by other work
            in flight, and an "exposure: $0.00" printed from a missing key would
            be a claim about the portfolio that nothing measured. */}
        {order.resulting_exposure_dollars !== undefined && (
          <Figure
            label={<Term k="exposure">Exposure after this</Term>}
            value={dollars(order.resulting_exposure_dollars)}
          />
        )}
      </div>

      <dl className="mt-5 space-y-2 border-t pt-4 text-xs">
        <Row label="Ticker" value={order.ticker} mono />
        <Row label="Side" value={order.side} mono />
        <Row label="Book side" value={order.book_side} mono />
        <Row label="Price grid" value={order.price_grid} mono />
        <Row label="Order id" value={order.order_id} mono />
        <Row label="Client order id" value={order.client_order_id} mono />
        {extras.map(([key, value]) => (
          <Row key={key} label={key} value={String(value)} mono />
        ))}
      </dl>

      {Object.keys(quote).length > 0 && (
        <div className="mt-5 border-t pt-4">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
            The price it was read at
          </h3>
          <dl className="mt-3 space-y-2 text-xs">
            <Row label="Recorded ask" value={quote.recorded_ask_display} mono />
            <Row label="Live ask" value={quote.live_ask_display} mono />
            <Row
              label="Moved"
              value={
                quote.moved_tenths === undefined
                  ? undefined
                  : `${quote.moved_tenths > 0 ? "+" : ""}${quote.moved_tenths} tenths`
              }
              mono
            />
            <Row
              label="Read"
              value={
                quote.age_ms === undefined ? undefined : formatAge(quote.age_ms)
              }
              mono
            />
            <Row
              label={<Term k="depth">Depth at ask</Term>}
              value={
                quote.depth_at_ask === undefined || quote.depth_at_ask === null
                  ? undefined
                  : quote.depth_at_ask.toFixed(0)
              }
              mono
            />
            <Row
              label="Authorised"
              value={
                quote.authorised_contracts === undefined
                  ? undefined
                  : `${quote.authorised_contracts}`
              }
              mono
            />
            <Row
              label="Re-sized to"
              value={
                quote.resized_contracts === undefined
                  ? undefined
                  : `${quote.resized_contracts}`
              }
              mono
            />
            <Row label="Bound by" value={quote.binding_constraint} mono />
          </dl>
          {quote.note && (
            <p className="mt-3 text-xs leading-relaxed text-muted">
              {quote.note}
            </p>
          )}
        </div>
      )}

      {order.note && (
        <p className="mt-5 rounded-lg border border-accent/40 bg-accent-soft px-3 py-2 text-xs leading-relaxed">
          {order.note}
        </p>
      )}

      {order.request_body && (
        <details className="mt-5 border-t pt-4">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-widest text-muted">
            The exact bytes
          </summary>
          <pre className="mt-3 max-w-full overflow-x-auto rounded-lg border p-3 font-mono text-[0.7rem] leading-relaxed">
            {JSON.stringify(order.request_body, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ atoms */

function Verdict({
  tone,
  code,
  children,
}: {
  tone: "refused" | "dry" | "placed";
  code?: string;
  children: React.ReactNode;
}) {
  const colour =
    tone === "placed"
      ? "text-positive"
      : tone === "dry"
        ? "text-accent-2"
        : "text-accent";
  return (
    <div>
      {code && (
        <div
          className={`font-mono text-xs font-bold uppercase tracking-widest ${colour}`}
        >
          {code}
        </div>
      )}
      <h3 className={`display mt-1 text-2xl ${colour}`}>{children}</h3>
    </div>
  );
}

function Section({
  label,
  note,
  children,
}: {
  label: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </h3>
      {note && (
        <p className="mt-2 text-xs leading-relaxed text-muted">{note}</p>
      )}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Note({
  tone,
  children,
}: {
  tone?: "warn";
  children: React.ReactNode;
}) {
  return (
    <p
      className={`mb-6 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${
        tone === "warn"
          ? "border-accent/40 bg-accent-soft"
          : "text-muted"
      }`}
    >
      {children}
    </p>
  );
}

function Figure({
  label,
  value,
  unit,
  tone,
  muted,
}: {
  /** ReactNode so a label can be a <Term> (2026-08-22, A4). */
  label: React.ReactNode;
  value: string;
  unit?: React.ReactNode;
  tone?: "positive" | "negative";
  muted?: boolean;
}) {
  const colour = muted
    ? "text-muted"
    : tone === "positive"
      ? "text-positive"
      : tone === "negative"
        ? "text-negative"
        : "text-foreground";
  return (
    <div className="min-w-0">
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className={`tabular mt-1 truncate text-xl font-bold ${colour}`}>
        {value}
      </div>
      {unit && <div className="text-xs text-muted">{unit}</div>}
    </div>
  );
}

function Row({
  label,
  value,
  mono,
}: {
  /** ReactNode so a label can be a <Term> (2026-08-22, A4). */
  label: React.ReactNode;
  value?: string | number | null;
  mono?: boolean;
}) {
  if (value === undefined || value === null || value === "") return null;
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
      <dt className="text-muted">{label}</dt>
      <dd className={`min-w-0 break-all text-right ${mono ? "font-mono" : ""}`}>
        {value}
      </dd>
    </div>
  );
}

/**
 * Size. An integer the human chooses, sent to a server that will only ever
 * reduce it -- not a derived quantity, which is why it is allowed to exist on
 * this side of the wire at all.
 */
function Stepper({
  value,
  max,
  disabled,
  onChange,
}: {
  value: number;
  max: number;
  disabled: boolean;
  onChange: (next: number) => void;
}) {
  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        aria-label="One contract fewer"
        disabled={disabled || value <= 1}
        onClick={() => onChange(Math.max(1, value - 1))}
        className="h-11 w-11 shrink-0 rounded-lg border text-lg font-bold disabled:opacity-30"
      >
        −
      </button>
      <div className="min-w-0 flex-1 text-center">
        <div className="tabular text-3xl font-extrabold">{value}</div>
        <div className="text-xs text-muted">of {max} authorised</div>
      </div>
      <button
        type="button"
        aria-label="One contract more"
        disabled={disabled || value >= max}
        onClick={() => onChange(Math.min(max, value + 1))}
        className="h-11 w-11 shrink-0 rounded-lg border text-lg font-bold disabled:opacity-30"
      >
        +
      </button>
    </div>
  );
}

/* ---------------------------------------------------------------- currency

   Rendering, not arithmetic. `toFixed` chooses how many digits to print; it
   does not decide what the number is. Nothing in this file adds, multiplies or
   converts a money value.
--------------------------------------------------------------------------- */

function dollars(value: number): string {
  return `${value < 0 ? "−" : ""}$${Math.abs(value).toFixed(2)}`;
}

function signedDollars(value: number): string {
  return `${value >= 0 ? "+" : "−"}$${Math.abs(value).toFixed(2)}`;
}
