"use client";

/**
 * The manual ticket (ADR 0063 + 0065): Joe's own hand bet, through the
 * portal, with his own number typed before the price is revealed.
 *
 * The ordering is the design, not a flourish. Step 1 asks for P(YES) with
 * the ask MASKED — the moment the ask is visible the typed number becomes
 * the ask's number (anchoring; the Playbook has taught this since it was
 * written). The reveal is the reward for the estimate. The server enforces
 * its half regardless (`p_yes_bp` is required at the route); this masking
 * is the client's half.
 *
 * Every refusal renders the server's own sentence verbatim — the route has
 * a dozen distinct refusals and each explains itself better than a generic
 * message could. A 423 (lockout, cool-off) is a state, not an error, and
 * renders calm. The one state that must never look like success or retry
 * bait: `unrecognised_response`, whose note says to check the Kalshi app
 * before retrying — rendered loud, never a spinner.
 *
 * Both platforms: one-handed at 390px (large touch targets, stacked), and
 * keyboard on desktop — Enter advances step 1's form, Escape closes the
 * ticket, the confirm is an explicit button and never an implicit submit.
 *
 * The bearer token lives in component state only — same rule as
 * `TicketProvider`: a session cookie must never place a bet, and the typed
 * act is the strongest anti-impulse guard in the product.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  DISPLAY_TIME_ZONE,
  fetchManualMarket,
  placeManualOrder,
  refusalText,
  type ManualMarket,
  type ManualOrderPlaced,
} from "@/lib/api";
import Term from "@/components/Term";

function releaseClock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    hour: "numeric",
    minute: "2-digit",
  });
}

/** "62.5" -> 6250 bp, or null when the text is not a probability. */
function percentToBp(text: string): number | null {
  const value = Number.parseFloat(text.replace(",", "."));
  if (!Number.isFinite(value)) return null;
  const bp = Math.round(value * 100);
  if (bp < 1 || bp > 9999) return null;
  return bp;
}

type Phase =
  | { name: "closed" }
  | { name: "estimate" }
  | { name: "loading" }
  | { name: "blocked"; words: string }
  | { name: "ticket"; market: ManualMarket }
  | { name: "sending"; market: ManualMarket }
  | { name: "placed"; placed: ManualOrderPlaced }
  | { name: "refused"; status: number; words: string; calm: boolean };

export default function ManualTicket({ ticker }: { ticker: string }) {
  const [phase, setPhase] = useState<Phase>({ name: "closed" });
  const [percent, setPercent] = useState("");
  const [pYesBp, setPYesBp] = useState<number | null>(null);
  const [side, setSide] = useState<"yes" | "no">("yes");
  const [contracts, setContracts] = useState(1);
  const [maxPriceTenths, setMaxPriceTenths] = useState<number | null>(null);
  const [token, setToken] = useState("");
  // One idempotency key per opened ticket: two taps are one order.
  const [intentKey, setIntentKey] = useState<string | null>(null);
  const estimateInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (phase.name === "estimate") estimateInput.current?.focus();
  }, [phase.name]);

  const close = useCallback(() => {
    setPhase({ name: "closed" });
    setPercent("");
    setPYesBp(null);
    setToken("");
    setIntentKey(null);
  }, []);

  useEffect(() => {
    if (phase.name === "closed") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [phase.name, close]);

  const revealMarket = async (bp: number) => {
    setPYesBp(bp);
    setPhase({ name: "loading" });
    setIntentKey(crypto.randomUUID());
    let market: ManualMarket;
    try {
      market = await fetchManualMarket(ticker);
    } catch (error) {
      setPhase({
        name: "blocked",
        words:
          error instanceof Error
            ? error.message
            : "the market could not be read.",
      });
      return;
    }
    if (!market.reachable) {
      setPhase({
        name: "blocked",
        words: market.unreachable_reason ?? "the manual path is not enabled.",
      });
      return;
    }
    const now = Date.now();
    if (market.lockout_until_ms !== null && market.lockout_until_ms > now) {
      setPhase({
        name: "blocked",
        words: `You said not tonight. The desk unlocks at ${releaseClock(market.lockout_until_ms)} — there is no early unlock, and that is the point. (Your number was still worth typing: it is yours, not the ask's.)`,
      });
      return;
    }
    if (market.cooloff_until_ms !== null && market.cooloff_until_ms > now) {
      setPhase({
        name: "blocked",
        words: `The buy control is resting after your last order and unlocks at ${releaseClock(market.cooloff_until_ms)}. No override.`,
      });
      return;
    }
    const defaultSide: "yes" | "no" =
      market.sides.yes.ask_tenths !== null ? "yes" : "no";
    setSide(defaultSide);
    setContracts(1);
    setMaxPriceTenths(market.sides[defaultSide].ask_tenths);
    setPhase({ name: "ticket", market });
  };

  const confirm = async (market: ManualMarket) => {
    if (
      pYesBp === null ||
      maxPriceTenths === null ||
      intentKey === null ||
      token.trim().length === 0
    ) {
      return;
    }
    setPhase({ name: "sending", market });
    const result = await placeManualOrder(
      {
        ticker,
        side,
        contracts,
        max_price_tenths: maxPriceTenths,
        p_yes_bp: pYesBp,
        idempotency_key: intentKey,
      },
      token.trim(),
    );
    if (result.ok) {
      setPhase({ name: "placed", placed: result.value });
    } else {
      setPhase({
        name: "refused",
        status: result.status,
        words: refusalText(result.detail),
        calm: result.status === 423,
      });
    }
  };

  return (
    <section className="mt-6 rounded-2xl border bg-card p-4 sm:p-6">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Place a bet</h2>
        {phase.name !== "closed" && (
          <button
            onClick={close}
            className="rounded-lg border px-3 py-1.5 text-xs text-muted"
          >
            Close
          </button>
        )}
      </div>

      {phase.name === "closed" && (
        <div className="mt-3">
          <button
            onClick={() => setPhase({ name: "estimate" })}
            className="min-h-11 rounded-xl border border-border-strong px-4 py-2.5 text-sm font-semibold"
          >
            Open the ticket
          </button>
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            The ticket asks for your own number first and shows the price
            after — a number typed after seeing the ask is just the ask
            wearing your handwriting.
          </p>
        </div>
      )}

      {phase.name === "estimate" && (
        <form
          className="mt-3"
          onSubmit={(event) => {
            event.preventDefault();
            const bp = percentToBp(percent);
            if (bp !== null) void revealMarket(bp);
          }}
        >
          <label
            htmlFor="manual-p-yes"
            className="text-xs font-semibold uppercase tracking-widest text-muted"
          >
            Your <Term k="p_yes">P(YES)</Term>, percent — before the price
          </label>
          <input
            id="manual-p-yes"
            ref={estimateInput}
            value={percent}
            onChange={(event) => setPercent(event.target.value)}
            inputMode="decimal"
            autoComplete="off"
            placeholder="62.5"
            className="mt-2 w-full max-w-xs rounded-xl border bg-background px-4 py-3 text-2xl font-semibold"
          />
          {percentToBp(percent) !== null && (
            <p className="mt-2 max-w-[65ch] text-xs text-muted">
              = a {(percentToBp(percent)! / 100).toFixed(2)}% chance this
              market ends YES — not your side, YES.
            </p>
          )}
          <button
            type="submit"
            disabled={percentToBp(percent) === null}
            className="mt-3 block min-h-11 rounded-xl border border-border-strong px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
          >
            Show me the price
          </button>
        </form>
      )}

      {phase.name === "loading" && (
        <p className="mt-3 max-w-[65ch] text-sm text-muted">
          Reading the live book&hellip;
        </p>
      )}

      {phase.name === "blocked" && (
        <p className="mt-3 max-w-[65ch] text-sm leading-relaxed text-muted">
          {phase.words}
        </p>
      )}

      {(phase.name === "ticket" || phase.name === "sending") && (
        <TicketBody
          market={phase.market}
          side={side}
          setSide={(s) => {
            setSide(s);
            setContracts(1);
            setMaxPriceTenths(phase.market.sides[s].ask_tenths);
          }}
          contracts={contracts}
          setContracts={setContracts}
          maxPriceTenths={maxPriceTenths}
          setMaxPriceTenths={setMaxPriceTenths}
          token={token}
          setToken={setToken}
          sending={phase.name === "sending"}
          onConfirm={() => void confirm(phase.market)}
        />
      )}

      {phase.name === "placed" && <Placed placed={phase.placed} close={close} />}

      {phase.name === "refused" && (
        <div
          className={`mt-3 rounded-xl border p-4 ${
            phase.calm ? "" : "border-negative/50 bg-negative/10"
          }`}
        >
          <p className="max-w-[65ch] text-sm leading-relaxed">
            {phase.words}
          </p>
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            Nothing was placed{phase.status === 0 ? " — the request never left" : ""}.
          </p>
        </div>
      )}
    </section>
  );
}

function TicketBody({
  market,
  side,
  setSide,
  contracts,
  setContracts,
  maxPriceTenths,
  setMaxPriceTenths,
  token,
  setToken,
  sending,
  onConfirm,
}: {
  market: ManualMarket;
  side: "yes" | "no";
  setSide: (s: "yes" | "no") => void;
  contracts: number;
  setContracts: (n: number) => void;
  maxPriceTenths: number | null;
  setMaxPriceTenths: (n: number | null) => void;
  token: string;
  setToken: (t: string) => void;
  sending: boolean;
  onConfirm: () => void;
}) {
  const facts = market.sides[side];
  const ceiling = facts.authorised_contracts;
  const canConfirm =
    !sending &&
    facts.ask_tenths !== null &&
    maxPriceTenths !== null &&
    contracts >= 1 &&
    (ceiling === null || contracts <= ceiling) &&
    token.trim().length > 0;

  return (
    <div className="mt-3 space-y-4">
      <div className="grid grid-cols-2 gap-2">
        {(["yes", "no"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSide(s)}
            disabled={sending || market.sides[s].ask_tenths === null}
            className={`min-h-11 rounded-xl border px-4 py-3 text-sm font-semibold disabled:opacity-40 ${
              side === s ? "border-border-strong bg-background" : ""
            }`}
          >
            {s.toUpperCase()}
            <span className="ml-2 font-mono">
              {market.sides[s].ask_display ?? "no ask"}
            </span>
          </button>
        ))}
      </div>

      <p className="max-w-[65ch] text-xs text-muted">
        <Term k="depth">Depth</Term>:{" "}
        {facts.depth_at_ask === null ? "—" : Math.round(facts.depth_at_ask)} at
        the <Term k="ask">ask</Term> · your per-bet cap authorises{" "}
        {ceiling === null ? "— (cap underivable)" : `${ceiling}`}{" "}
        <Term k="contract">{ceiling === 1 ? "contract" : "contracts"}</Term>
        {market.dry_run &&
          " · this path runs DRY — the order is recorded, not sent"}
      </p>

      <div className="flex flex-wrap items-center gap-4">
        <Stepper
          label="Contracts"
          value={contracts}
          onChange={setContracts}
          min={1}
          max={ceiling ?? 1}
          disabled={sending}
        />
        <Stepper
          label="Max price (c)"
          value={maxPriceTenths === null ? 0 : Math.round(maxPriceTenths / 10)}
          onChange={(cents) => setMaxPriceTenths(cents * 10)}
          min={1}
          max={99}
          disabled={sending}
        />
      </div>
      <p className="max-w-[65ch] text-xs text-muted">
        The order goes out at the live ask, immediate-or-cancel, and is
        refused — never re-priced — if the ask has moved above your max. The
        server prices the fee-inclusive worst case when you confirm and says
        &ldquo;at most&rdquo;, because the exact fee on this venue is still
        being measured.
      </p>

      <div>
        <label
          htmlFor="manual-token"
          className="text-xs font-semibold uppercase tracking-widest text-muted"
        >
          Order token
        </label>
        <input
          id="manual-token"
          type="password"
          value={token}
          onChange={(event) => setToken(event.target.value)}
          autoComplete="off"
          className="mt-1 w-full max-w-xs rounded-xl border bg-background px-3 py-2 text-sm"
        />
        <p className="mt-1 max-w-[65ch] text-xs text-muted">
          Typed each time, held in memory only. The session cookie can read
          this cockpit; it can never place a bet.
        </p>
      </div>

      <button
        onClick={onConfirm}
        disabled={!canConfirm}
        className="min-h-12 w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white disabled:opacity-40 sm:w-auto sm:px-8"
      >
        {sending ? "Sending…" : `Confirm — buy ${contracts} ${side.toUpperCase()}`}
      </button>
    </div>
  );
}

function Stepper({
  label,
  value,
  onChange,
  min,
  max,
  disabled,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min: number;
  max: number;
  disabled: boolean;
}) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {label}
      </div>
      <div className="mt-1 flex items-center gap-2">
        <button
          onClick={() => onChange(Math.max(min, value - 1))}
          disabled={disabled || value <= min}
          aria-label={`${label} down`}
          className="grid h-11 w-11 place-items-center rounded-xl border text-lg disabled:opacity-40"
        >
          −
        </button>
        <span className="tabular w-10 text-center font-mono text-lg font-semibold">
          {value}
        </span>
        <button
          onClick={() => onChange(Math.min(max, value + 1))}
          disabled={disabled || value >= max}
          aria-label={`${label} up`}
          className="grid h-11 w-11 place-items-center rounded-xl border text-lg disabled:opacity-40"
        >
          +
        </button>
      </div>
    </div>
  );
}

function Placed({
  placed,
  close,
}: {
  placed: ManualOrderPlaced;
  close: () => void;
}) {
  const unrecognised = placed.status === "unrecognised_response";
  return (
    <div
      className={`mt-3 rounded-xl border p-4 ${
        unrecognised ? "border-negative/50 bg-negative/10" : ""
      }`}
    >
      <div className="text-xs font-semibold uppercase tracking-widest text-muted">
        {placed.dry_run ? "Recorded — dry run" : placed.status.replace("_", " ")}
      </div>
      <p className="mt-2 max-w-[65ch] text-sm">
        {placed.contracts} × {placed.side.toUpperCase()} on{" "}
        <span className="font-mono text-xs">{placed.ticker}</span> at{" "}
        {placed.limit_price_display}, costs at most{" "}
        {placed.worst_case_cost_display}. Your P(YES):{" "}
        {(placed.p_yes_bp / 100).toFixed(2)}%.
      </p>
      <p className="mt-2 max-w-[65ch] text-xs leading-relaxed text-muted">
        {placed.note}
      </p>
      {placed.error_text && (
        <p className="mt-2 max-w-[65ch] text-xs leading-relaxed text-negative">
          {placed.error_text}
        </p>
      )}
      <button
        onClick={close}
        className="mt-3 min-h-11 rounded-xl border px-4 py-2 text-sm font-semibold"
      >
        Done — the control now rests
      </button>
    </div>
  );
}
