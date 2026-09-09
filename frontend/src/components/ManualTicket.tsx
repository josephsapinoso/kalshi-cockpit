"use client";

/**
 * The manual ticket (ADR 0063): Joe's own hand bet, through the portal.
 *
 * **THE TICKET ASKS FOR NO PROBABILITY, AND NOTHING IS MASKED** — removed
 * 2026-09-09 on Joe's instruction, in his own words: "what is even the point
 * of the (p)yes score entry? I don't need it. it just gets in the way." See
 * `docs/adr/DRAFT-the-ticket-stops-asking-for-a-probability.md`, which
 * supersedes ADR 0065 §2.
 *
 * What used to be here: step 1 asked for P(YES) with the ask MASKED, on the
 * argument that the moment the ask is visible the typed number becomes the
 * ask's number (anchoring). That argument is sound and it was not what
 * failed. ADR 0065 shipped over a red-team objection — "an unscored form is
 * a speed bump a user learns to type through" — which lost on exactly one
 * premise: that `bets.bet_clv()` had just given a pre-bet P(YES) a consumer.
 * **That consumer was never built.** Nothing in the tree SELECTs `p_yes_bp`.
 * Anti-anchoring protects a number nobody scores, so it bought friction and
 * nothing else, and the red-team's description is what the desk actually was.
 *
 * Opening the control now goes straight to the live book. Removing the field
 * removes no risk control: the desk lockout, idempotency, the KXMVE
 * acknowledgement, the price ceiling, depth at the ask, the netting guard,
 * the shard collateral check and reserve-then-check are all server-side and
 * all untouched.
 *
 * ADR 0071 §2.2 makes price transparency the desk's job at the moment of a
 * bet, which is now the whole of what this control does.
 *
 * MORE PLACES TO START A BET IS NOT MORE BETS. This control is mounted
 * inline on the slate rows, the Picks cards and the parlay legs. What
 * bounds purchases is the ten-minute cool-off after every completed order
 * (`store/manual_orders.py`, no override) and the desk lockout — both
 * server-side, both indifferent to how many buttons exist.
 *
 * Every refusal renders the server's own sentence verbatim — the route has
 * a dozen distinct refusals and each explains itself better than a generic
 * message could. A 423 (lockout, cool-off) is a state, not an error, and
 * renders calm. The one state that must never look like success or retry
 * bait: `unrecognised_response`, whose note says to check the Kalshi app
 * before retrying — rendered loud, never a spinner.
 *
 * Both platforms: one-handed at 390px (large touch targets, stacked), and
 * keyboard on desktop — Escape closes the ticket, and the confirm is an
 * explicit button and never an implicit submit. (There is no form to advance
 * with Enter any more; the estimate step it belonged to is gone.)
 *
 * **The typed bearer token was REMOVED 2026-09-08 on Joe's instruction**
 * (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1, answer 3). This
 * block used to read: "a session cookie must never place a bet, and the typed
 * act is the strongest anti-impulse guard in the product." Both halves were
 * true, and he was shown the first one — that the 43 characters were the
 * credential and not merely friction, so that after this a person holding his
 * unlocked phone can bet his money — before he chose removal a second time.
 *
 * The order now posts to the same-origin `/manual-order` route handler, which
 * proves session by cookie and adds the bearer server-side. That is the
 * pattern `/parlay-bid` and `/refresh-odds` already used; the manual ticket
 * was the outlier, and the asymmetry was drift rather than a decision. Auth at
 * the API is unchanged — `require_auth` still guards every mutating route.
 */

import { useCallback, useEffect, useId, useState } from "react";

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

type Phase =
  | { name: "closed" }
  | { name: "loading" }
  | { name: "blocked"; words: string }
  | { name: "ticket"; market: ManualMarket }
  | { name: "sending"; market: ManualMarket }
  | { name: "placed"; placed: ManualOrderPlaced }
  | { name: "refused"; status: number; words: string; calm: boolean };

/** How the control sits on the page. `section` is its own card (the market
 *  screen); `inline` is a hairline-separated block inside somebody else's
 *  card — a slate row, a Picks card, a parlay leg. */
export type BuyVariant = "section" | "inline";

export default function ManualTicket({
  ticker,
  variant = "section",
  openLabel,
  note,
}: {
  ticker: string;
  variant?: BuyVariant;
  /** Overrides the open affordance's words on a crowded surface. */
  openLabel?: string;
  /** An extra sentence this surface must say before a bet — the parlay
   *  desk's "buying a leg is not buying the parlay", for instance. */
  note?: string;
}) {
  const [phase, setPhase] = useState<Phase>({ name: "closed" });
  const [side, setSide] = useState<"yes" | "no">("yes");
  const [contracts, setContracts] = useState(1);
  const [maxPriceTenths, setMaxPriceTenths] = useState<number | null>(null);

  // ADR 0073's acknowledgement, per opened ticket. Cleared on close with
  // everything else: it is consent to one order, not a preference.
  const [comboOk, setComboOk] = useState(false);
  // One idempotency key per opened ticket: two taps are one order.
  const [intentKey, setIntentKey] = useState<string | null>(null);

  const close = useCallback(() => {
    setPhase({ name: "closed" });
    setComboOk(false);
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

  const openTicket = async () => {
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
        words: `You said not tonight. The desk unlocks at ${releaseClock(market.lockout_until_ms)} — there is no early unlock, and that is the point.`,
      });
      return;
    }
    // The cool-off gate was removed here 2026-09-08 along with the server's
    // (`docs/adr/0112-the-caps-come-off-the-hand-bet-path.md` §1, answer 3).
    // Both halves went in the same change deliberately: a screen still
    // enforcing a rule the route had dropped is the "one predicate with two
    // spellings" failure this repo has hit three times, and here it would have
    // been worse than usual, because the copy promised an unlock time that
    // nothing would ever produce. `/api/manual/market` now always answers
    // `cooloff_until_ms: null`, pinned by
    // `test_the_estimate_route_reports_no_cooloff_either`. The DESK LOCKOUT
    // above is untouched — Joe removed the cool-off, not the lockout.
    const defaultSide: "yes" | "no" =
      market.sides.yes.ask_tenths !== null ? "yes" : "no";
    setSide(defaultSide);
    setComboOk(false);
    // 0 until a dollar amount is typed: the confirm stays disabled, so an
    // untouched ticket cannot buy "1" by default.
    setContracts(0);
    setMaxPriceTenths(market.sides[defaultSide].ask_tenths);
    setPhase({ name: "ticket", market });
  };

  const confirm = async (market: ManualMarket) => {
    if (maxPriceTenths === null || intentKey === null) {
      return;
    }
    setPhase({ name: "sending", market });
    const result = await placeManualOrder(
      {
        ticker,
        side,
        contracts,
        max_price_tenths: maxPriceTenths,
        idempotency_key: intentKey,
        combo_acknowledged: market.is_combo ? comboOk : false,
      },
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

  const inline = variant === "inline";

  const body = (
    <>
      <div className="flex items-center justify-between gap-3">
        {phase.name === "closed" && inline ? null : inline ? (
          <h3 className="text-sm font-semibold">Place a bet</h3>
        ) : (
          <h2 className="text-lg font-semibold">Place a bet</h2>
        )}
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
        <div className={inline ? "" : "mt-3"}>
          <button
            onClick={() => void openTicket()}
            className="min-h-11 rounded-xl border border-border-strong px-4 py-2.5 text-sm font-semibold"
          >
            {openLabel ?? "Open the ticket"}
          </button>
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            The ticket reads Kalshi&rsquo;s live book and shows you the ask you
            would pay. Nothing is sent until you confirm.
          </p>
          {note && (
            <p className="mt-2 max-w-[65ch] text-xs text-muted">{note}</p>
          )}
        </div>
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
            setContracts(0);
            setMaxPriceTenths(phase.market.sides[s].ask_tenths);
          }}
          contracts={contracts}
          setContracts={setContracts}
          maxPriceTenths={maxPriceTenths}
          setMaxPriceTenths={setMaxPriceTenths}
          comboOk={comboOk}
          setComboOk={setComboOk}
          note={note}
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
    </>
  );

  return inline ? (
    <div className="mt-3 border-t pt-3">{body}</div>
  ) : (
    <section className="mt-6 rounded-2xl border border-edge bg-card p-4 sm:p-6">
      {body}
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
  comboOk,
  setComboOk,
  note,
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
  comboOk: boolean;
  setComboOk: (ok: boolean) => void;
  note?: string;
  sending: boolean;
  onConfirm: () => void;
}) {
  const facts = market.sides[side];
  // Two ceilings, and the smaller wins: what the server authorises for this
  // side, and what this path is armed for. The server serves the second so
  // the client cannot hold a stale copy of a constant that exists to be
  // raised.
  //
  // **`authorised_contracts` no longer carries a cap of ours** (ADR 0112
  // Amendment 1). Until 2026-09-08 it was `min($3.00 spend cap, 10% of the
  // observed balance)`, and this line disabled Confirm above it -- so a brake
  // Joe had removed by name went on being enforced on the button while the
  // route accepted two hundred times as much. It is now the structural
  // ceiling, the depth at the ask and the shard's collateral, which are the
  // three bounds the route itself applies.
  const ceiling =
    facts.authorised_contracts === null
      ? null
      : Math.min(facts.authorised_contracts, market.max_contracts);
  // Plain words for the bound that produced it. Joe has asked to be taught
  // the terms rather than handed them, so each says what to DO about it --
  // the remedies genuinely differ, and the old copy called every one of them
  // "your per-bet cap", which is now the one thing none of them is.
  const boundReason: Record<string, string> = {
    depth: "that is all that is resting at the ask right now",
    shard: "that is what this market's Kalshi wallet can pay for",
    structural: "that is this path's built-in ceiling, not a limit on the bet",
    price_grid: "the price grid will not express a larger order",
  };
  const boundWhy = boundReason[facts.authorised_binding] ?? null;
  const canConfirm =
    !sending &&
    facts.ask_tenths !== null &&
    maxPriceTenths !== null &&
    contracts >= 1 &&
    (ceiling === null || contracts <= ceiling) &&
    (!market.is_combo || comboOk);

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

      {facts.ask_tenths === null && (
        <p className="max-w-[65ch] text-xs text-muted">
          No resting bid on the other side of this book, so there is no{" "}
          <Term k="ask">ask</Term> — nothing to buy here right now, on either
          side that shows one.
        </p>
      )}

      <p className="max-w-[65ch] text-xs text-muted">
        <Term k="depth">Depth</Term>:{" "}
        {facts.depth_at_ask === null ? "—" : Math.round(facts.depth_at_ask)} at
        the <Term k="ask">ask</Term> · you can buy{" "}
        {ceiling === null
          ? facts.authorised_binding === "shard_unreadable"
            ? "— (your Kalshi wallet could not be read)"
            : "—"
          : `${ceiling}`}{" "}
        <Term k="contract">{ceiling === 1 ? "contract" : "contracts"}</Term>
        {ceiling !== null && boundWhy !== null && ` — ${boundWhy}`}
        {market.dry_run &&
          " · this path runs DRY — the order is recorded, not sent"}
      </p>

      {/* The one moment the reader has to know money moves, said BEFORE the
          confirm rather than in the receipt after it. The server's own
          `note` says it too, but by then the order has gone. Rendered only
          when the path is armed, so it cannot become wallpaper: while
          `dry_run` is true the line above says the opposite, and a screen
          that warns about both states warns about neither.

          It wears the warning ochre (`accent-2`), ticket #32. The strip IS a
          caution -- the same class as DRY RUN, EXPIRED and every other "be
          careful" string in the app -- not a refusal (nothing is stopped)
          and not a loss (nothing is spent yet). Until 2026-09-02 it wore
          `accent`, which since ticket #10 is indigo: the Confirm button's
          own colour directly below it, so the one sentence that says money
          moves carried no warning weight of its own. Do not repaint it from
          the palette comment in globals.css -- that comment cites this
          ticket for this element, not the other way round. */}
      {!market.dry_run && (
        <p className="max-w-[65ch] rounded-xl border border-accent-2/50 bg-accent-2-soft px-3 py-2 text-xs leading-relaxed text-accent-2">
          <span className="font-semibold">This spends real money.</span>{" "}
          Confirming sends the order to Kalshi immediately, at the live{" "}
          <Term k="ask">ask</Term>, and this tool has no way to cancel one —
          it fills or it is killed. All of it is lost if the market settles
          the other way.
        </p>
      )}

      {note && <p className="max-w-[65ch] text-xs text-muted">{note}</p>}

      <DollarAmount
        askTenths={facts.ask_tenths}
        askDisplay={facts.ask_display}
        ceiling={ceiling}
        contracts={contracts}
        setContracts={setContracts}
        disabled={sending}
      />

      <details className="max-w-[65ch]">
        <summary className="cursor-pointer text-xs font-semibold text-muted">
          Max price (set to the live ask)
        </summary>
        <div className="mt-2">
          <Stepper
            label="Max price (c)"
            value={
              maxPriceTenths === null ? 0 : Math.round(maxPriceTenths / 10)
            }
            onChange={(cents) => setMaxPriceTenths(cents * 10)}
            min={1}
            max={99}
            disabled={sending}
          />
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            The order goes out at the live ask, immediate-or-cancel, and is
            refused — never re-priced — if the ask has moved above this. The
            server prices the fee-inclusive worst case when you confirm and
            says &ldquo;at most&rdquo;, because the exact fee on this venue
            is still being measured.
          </p>
        </div>
      </details>

      {market.is_combo && (
        <div className="rounded-xl border border-negative/50 bg-negative/10 p-3">
          <p className="max-w-[65ch] text-xs leading-relaxed">
            {market.combo_note ??
              "This is a combination market. You can enter it and you cannot exit it."}
          </p>
          <label className="mt-2 flex items-start gap-2 text-xs font-semibold">
            <input
              type="checkbox"
              checked={comboOk}
              onChange={(event) => setComboOk(event.target.checked)}
              disabled={sending}
              className="mt-0.5 h-5 w-5 shrink-0"
            />
            <span>
              I understand there is no way out of this bet except the
              outcome.
            </span>
          </label>
          <p className="mt-2 max-w-[65ch] text-xs text-muted">
            The box is a courtesy; the server refuses without the
            acknowledgement whatever this screen renders.
          </p>
        </div>
      )}

      <button
        onClick={onConfirm}
        disabled={!canConfirm}
        className="min-h-12 w-full rounded-xl bg-accent-fill px-4 py-3 text-sm font-semibold text-white disabled:opacity-40 sm:w-auto sm:px-8"
      >
        {sending
          ? "Sending…"
          : contracts >= 1 && facts.ask_tenths !== null
            ? `Confirm — buy ${contracts} ${side.toUpperCase()} for ${dollars(
                contracts * facts.ask_tenths,
              )}`
            : `Confirm — buy ${side.toUpperCase()}`}
      </button>
    </div>
  );
}

/** Tenths of a cent -> "$4.73". Display only: the money path stays integer
 *  tenths end to end (`core/prices.py`), and the server re-derives every
 *  figure from the ask it actually gets. */
function dollars(tenths: number): string {
  return (tenths / 1000).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

/** The amount control, in dollars, because that is how Joe thinks about a
 *  bet ("about five bucks on this"), while the venue transacts in contracts
 *  that each cost the ask. The conversion is shown, never hidden: the point
 *  is to teach the mapping, not to abstract it away. Rounds DOWN — the tool
 *  must never spend more than the number typed. */
function DollarAmount({
  askTenths,
  askDisplay,
  ceiling,
  contracts,
  setContracts,
  disabled,
}: {
  askTenths: number | null;
  askDisplay: string | null;
  ceiling: number | null;
  contracts: number;
  setContracts: (n: number) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");
  const uid = useId();
  const amountId = `manual-dollars-${uid}`;

  const parsed = Number.parseFloat(text.replace(",", "."));
  const amountTenths =
    Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed * 1000) : null;

  // Derived here AND pushed up: the parent owns what is sent, this control
  // owns how it was arrived at. Recomputed when the side (and so the ask)
  // changes, keeping the typed dollars.
  useEffect(() => {
    if (askTenths === null || amountTenths === null) {
      setContracts(0);
      return;
    }
    const affordable = Math.floor(amountTenths / askTenths);
    setContracts(Math.min(affordable, ceiling ?? affordable));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [amountTenths, askTenths, ceiling]);

  const affordable =
    askTenths === null || amountTenths === null
      ? null
      : Math.floor(amountTenths / askTenths);
  const capped =
    affordable !== null && ceiling !== null && affordable > ceiling;

  return (
    <div>
      <label
        htmlFor={amountId}
        className="text-xs font-semibold uppercase tracking-widest text-muted"
      >
        Amount, in dollars
      </label>
      <div className="mt-1 flex items-center gap-2">
        <span className="text-lg font-semibold text-muted">$</span>
        <input
          id={amountId}
          value={text}
          onChange={(event) => setText(event.target.value)}
          inputMode="decimal"
          autoComplete="off"
          placeholder="5"
          disabled={disabled || askTenths === null}
          className="w-28 rounded-xl border bg-background px-3 py-2.5 text-lg font-semibold disabled:opacity-40"
        />
      </div>
      {askTenths !== null && amountTenths !== null && (
        <p className="mt-2 max-w-[65ch] text-xs text-muted">
          {contracts >= 1 ? (
            <>
              Buys{" "}
              <span className="font-semibold text-foreground">
                {contracts}{" "}
                <Term k="contract">
                  {contracts === 1 ? "contract" : "contracts"}
                </Term>
              </span>{" "}
              at {askDisplay} each = {dollars(contracts * askTenths)}, plus
              the fee. Whole contracts only, rounded down — the rest of your{" "}
              {dollars(amountTenths)} stays in your pocket.
            </>
          ) : (
            <>
              Not enough: one contract costs {askDisplay}, so the smallest
              bet here is {dollars(askTenths)}.
            </>
          )}
          {capped && ceiling !== null && (
            <>
              {" "}
              Trimmed to {ceiling} — the book or your Kalshi wallet, not your
              typed amount, set the size. No cap of the desk's is involved.
            </>
          )}
        </p>
      )}
      {askTenths !== null && amountTenths === null && text.trim() !== "" && (
        <p className="mt-2 max-w-[65ch] text-xs text-muted">
          Type a dollar amount, like 5 or 2.50.
        </p>
      )}
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
        {placed.worst_case_cost_display}.
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
