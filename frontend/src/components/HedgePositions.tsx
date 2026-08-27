"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  closeHeldPosition,
  resolveHeldLeg,
  type HedgeBlock,
  type HedgeRung,
  type HeldLeg,
  type HeldPosition,
} from "@/lib/api";
import { kalshiMarketUrl } from "@/lib/kalshiLink";
import Term from "@/components/Term";

/**
 * What Joe holds, and what hedging it would do (ADR 0077).
 *
 * Two states render completely differently and that is the whole design:
 *
 * **A lock** — one leg live, every other already won — carries a dollar figure
 * that is true whichever way the last leg goes. It is arithmetic on two
 * observed numbers, so it is stated plainly.
 *
 * **A de-risk** — several legs live — carries no such figure and never
 * pretends to. Both branches are shown so the shape of the choice is visible,
 * and the payload does not even have a `guaranteed` field to render as false.
 *
 * **There is no buy button, deliberately.** The manual door is capped at one
 * contract with a ten-minute cool-off (ADR 0073), so a thirty-contract hedge
 * cannot go through it — it would take five hours. The screen gives the size,
 * the price and a link into the Kalshi app, and Joe places it there. A control
 * that could only ever buy 1/30th of the hedge would be worse than none.
 *
 * **No ordering here is a judgement.** Positions come back in the order they
 * were recorded (ADR 0071 §2.5).
 */
export default function HedgePositions({
  positions,
  notes,
}: {
  positions: HeldPosition[];
  notes: Record<string, string>;
}) {
  if (positions.length === 0) {
    return (
      <p className="mt-6 text-sm text-muted">
        No tickets recorded. Add one below and the desk will watch its legs
        while the games run.
      </p>
    );
  }

  return (
    <div className="mt-6 flex flex-col gap-4">
      {positions.map((position) => (
        <Position key={position.id} position={position} notes={notes} />
      ))}
    </div>
  );
}

function Position({
  position,
  notes,
}: {
  position: HeldPosition;
  notes: Record<string, string>;
}) {
  return (
    <section
      aria-label={`${position.label} ticket`}
      className="flex flex-col rounded-lg border border-border p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest">
          {position.label}
        </h2>
        <span className="tabular text-sm text-muted">
          {position.stake_display} &rarr; {position.return_display}
        </span>
      </header>
      <p className="mt-1 text-xs leading-snug text-muted">
        {position.source === "kalshi_combo" ? "Kalshi combo" : "Sportsbook"}
        {position.book ? ` · ${position.book}` : ""} ·{" "}
        {position.state_detail}
      </p>

      <ol className="mt-3 divide-y divide-border">
        {position.legs.map((leg) => (
          <Leg key={leg.id} leg={leg} />
        ))}
      </ol>

      <Hedge block={position.hedge} position={position} notes={notes} />

      <Close position={position} />
    </section>
  );
}

/** One leg: what it is, what the venue says it is worth now, and how it settled. */
function Leg({ leg }: { leg: HeldLeg }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5">
      {/*
        One colour for every outcome, deliberately. Colour in this product
        makes claims — green is "we found something" — and "this leg lost" is
        a fact the WORD already carries. A red leg would read as an alarm on a
        screen whose whole job is to be calm about money already at risk.
      */}
      <span className="w-16 shrink-0 text-[11px] uppercase tracking-wide text-muted">
        {leg.outcome === "pending" ? "live" : leg.outcome}
      </span>
      <span className="flex-1 text-sm">
        {leg.label}
        {leg.is_hedge_leg && (
          <span className="ml-2 text-[11px] uppercase tracking-wide text-muted">
            hedge here
          </span>
        )}
      </span>
      {/*
        A percentage or "--". Never 0%: an absent bid and a leg nobody wants
        are different facts, and the payload keeps them apart.
      */}
      <span className="tabular text-sm">{leg.chance_display}</span>
      {leg.outcome === "pending" ? (
        <LegControls leg={leg} />
      ) : (
        <span className="w-full text-[11px] text-muted">
          {leg.resolved_source === "venue"
            ? "settled by the exchange"
            : "marked by you"}
        </span>
      )}
    </li>
  );
}

/**
 * Marking a leg the exchange cannot settle.
 *
 * Required rather than convenient: a sportsbook leg has no Kalshi ticker, so
 * `kalshi_markets.result` can never reach it, and without this the lock case
 * is unreachable for exactly the slips this feature was asked for. The screen
 * says afterwards which source settled the leg, because the two are not
 * equally good evidence.
 */
function LegControls({ leg }: { leg: HeldLeg }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  async function mark(outcome: "won" | "lost" | "void") {
    setBusy(true);
    setRefused(null);
    const answer = await resolveHeldLeg(leg.id, outcome);
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    router.refresh();
  }

  return (
    <span className="flex w-full flex-wrap items-center gap-2 pt-1">
      {(["won", "lost", "void"] as const).map((outcome) => (
        <button
          key={outcome}
          type="button"
          disabled={busy}
          onClick={() => mark(outcome)}
          className="min-h-9 rounded border border-border px-3 text-[11px] uppercase tracking-wide disabled:opacity-50"
        >
          {outcome}
        </button>
      ))}
      {leg.ticker && (
        <a
          href={kalshiMarketUrl(leg.ticker)}
          target="_blank"
          rel="noreferrer"
          className="min-h-9 self-center text-[11px] underline decoration-dotted"
        >
          open on Kalshi
        </a>
      )}
      {refused && (
        <span className="w-full text-[11px] text-muted">{refused}</span>
      )}
    </span>
  );
}

function Hedge({
  block,
  position,
  notes,
}: {
  block: HedgeBlock | null;
  position: HeldPosition;
  notes: Record<string, string>;
}) {
  // `null` and a refusal are different answers. A ticket whose legs have all
  // won has nothing to hedge; a ticket whose hedge market has an empty book
  // has something we could not price. Collapsing them would make "nothing to
  // do" and "we could not look" the same empty card.
  if (block === null) return null;

  if (block.refusal) {
    return (
      <p className="mt-3 rounded border border-border p-3 text-sm text-muted">
        No hedge price: {block.refusal.detail}
      </p>
    );
  }

  if (block.kind === "derisk") {
    return (
      <div className="mt-3 rounded border border-border p-3">
        <h3 className="text-xs font-semibold uppercase tracking-widest">
          <Term k="derisk">de-risk</Term> only
        </h3>
        <p className="mt-1 text-xs leading-snug text-muted">{notes.derisk}</p>
        <p className="mt-2 text-sm">
          Venue&rsquo;s implied chance this ticket still wins:{" "}
          <span className="tabular">{block.chance_display}</span>
          {block.notional_value_display &&
            block.notional_value_display !== "--" && (
              <>
                {" "}
                &middot; worth about{" "}
                <span className="tabular">
                  {block.notional_value_display}
                </span>{" "}
                on paper
              </>
            )}
        </p>
        {block.chance_refusal && (
          <p className="mt-1 text-xs text-muted">
            {block.chance_refusal.detail}
          </p>
        )}
        <Ladder block={block} position={position} />
      </div>
    );
  }

  return (
    <div className="mt-3 rounded border border-border p-3">
      <h3 className="text-xs font-semibold uppercase tracking-widest">
        <Term k="lock">lock</Term> available
      </h3>
      {block.guaranteed && block.guaranteed_display ? (
        <p className="mt-1 text-lg font-semibold tabular">
          {block.guaranteed_display}{" "}
          <span className="text-xs font-normal text-muted">
            whichever way the last leg goes
          </span>
        </p>
      ) : (
        <p className="mt-1 text-sm text-muted">
          No size you could buy right now locks a gain.
        </p>
      )}
      {block.full_hedge_is_out_of_reach && block.equalising && (
        <p className="mt-1 text-xs text-muted">
          The full hedge is {block.equalising.contracts} contracts costing{" "}
          <span className="tabular">{block.equalising.cost_display}</span>
          {position.bankroll_known
            ? " — more than your balance covers."
            : " — and your balance could not be read, so nothing here is capped by it."}
        </p>
      )}
      <p className="mt-1 text-xs leading-snug text-muted">{notes.upper_bound}</p>
      <Ladder block={block} position={position} />
    </div>
  );
}

/**
 * The sizes, with both branches beside each.
 *
 * A partial hedge is the realistic move on a small bankroll, so "all or
 * nothing" would hide the choice actually available. Every figure is a string
 * the server rendered; this component does no money arithmetic.
 */
function Ladder({
  block,
  position,
}: {
  block: HedgeBlock;
  position: HeldPosition;
}) {
  const ladder = block.ladder ?? [];
  if (ladder.length === 0) return null;

  return (
    <>
      <p className="mt-3 text-xs text-muted">
        Buy {block.side?.toUpperCase()} at{" "}
        <span className="tabular">{block.ask_display}</span>
        {block.depth_at_ask !== null && block.depth_at_ask !== undefined && (
          <> &middot; {Math.floor(block.depth_at_ask)} resting</>
        )}
      </p>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-muted">
            <tr className="text-left">
              <th className="py-1 pr-3 font-normal">contracts</th>
              <th className="py-1 pr-3 font-normal">costs</th>
              <th className="py-1 pr-3 font-normal">if the leg wins</th>
              <th className="py-1 pr-3 font-normal">if it loses</th>
              <th className="py-1 font-normal">worst case</th>
            </tr>
          </thead>
          <tbody>
            {ladder.map((rung) => (
              <Rung key={rung.contracts} rung={rung} position={position} />
            ))}
          </tbody>
        </table>
      </div>
      {block.ticker && (
        <p className="mt-2 text-xs text-muted">
          {/* No buy control: see this component's docstring. */}
          <a
            href={kalshiMarketUrl(block.ticker)}
            target="_blank"
            rel="noreferrer"
            className="underline decoration-dotted"
          >
            Place it on Kalshi
          </a>
        </p>
      )}
    </>
  );
}

function Rung({
  rung,
  position,
}: {
  rung: HedgeRung;
  position: HeldPosition;
}) {
  // A rung you cannot fill or cannot pay for is shown rather than hidden --
  // "the full hedge is 100 contracts and 40 are resting" is the useful
  // sentence -- but it is dimmed so it does not read as available.
  const reachable = rung.fillable && rung.affordable;
  return (
    <tr className={reachable ? "" : "text-muted opacity-60"}>
      <td className="tabular py-1 pr-3">{rung.contracts}</td>
      <td className="tabular py-1 pr-3">{rung.cost_display}</td>
      <td className="tabular py-1 pr-3">{rung.if_leg_wins_display}</td>
      <td className="tabular py-1 pr-3">{rung.if_leg_loses_display}</td>
      <td className="tabular py-1">
        {rung.floor_display}
        {!rung.fillable && (
          <span className="ml-1 text-[10px] uppercase">not resting</span>
        )}
        {rung.fillable && !rung.affordable && position.bankroll_known && (
          <span className="ml-1 text-[10px] uppercase">over balance</span>
        )}
      </td>
    </tr>
  );
}

function Close({ position }: { position: HeldPosition }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);

  async function close() {
    setBusy(true);
    setRefused(null);
    const answer = await closeHeldPosition(position.id, "settled");
    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    router.refresh();
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={close}
        className="min-h-9 rounded border border-border px-3 text-[11px] uppercase tracking-wide disabled:opacity-50"
      >
        done with this ticket
      </button>
      <span className="text-[11px] text-muted">
        Stops watching it. Nothing is deleted.
      </span>
      {refused && <span className="w-full text-[11px] text-muted">{refused}</span>}
    </div>
  );
}
