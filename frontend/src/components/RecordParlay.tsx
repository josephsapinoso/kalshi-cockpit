"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { recordHeldPosition, type HeldLegInput } from "@/lib/api";
import Term from "@/components/Term";

/**
 * Telling the desk about a ticket you already hold (ADR 0078).
 *
 * Nothing in this project has ever recorded a bet Joe placed: `parlay_lookups`
 * records that a card was *priced*, `manual_orders` records that a ticker was
 * *sent*, and a sportsbook slip is not on this venue at all. A hedge needs the
 * stake, the payout and which legs are still alive, and only the operator knows
 * all three — so this form is the input the arithmetic cannot do without.
 *
 * **The money fields say what they mean.** "Returns" is the TOTAL that lands in
 * the account on a win, stake included — not "to win". The equalising hedge is
 * exactly that many dollars of contracts, so the ambiguity would land straight
 * in the size, and the label carries the example rather than assuming.
 *
 * **The ticker is optional and that is the sportsbook case.** A leg Kalshi does
 * not list can still be recorded; the screen then says it cannot be priced,
 * rather than treating an absent quote as a bad one.
 *
 * No validation of the figures happens here. The server owns the
 * cents-to-tenths conversion and the odds-range refusal, and it returns its own
 * sentence, which this renders verbatim — one implementation of a money rule,
 * on the side that has to be right.
 *
 * **It renders on four screens now, not one, and `prefill` is why (2026-09-06).**
 * Joe asked to be able to pay for a combination at a sportsbook "from the
 * betting and parlay pages", having just had the exchange's offer-making
 * controls removed. A sportsbook bet is placed at the book, so what the desk
 * can offer is the record of it — and a record that has to be re-typed from a
 * card already on screen is one nobody keeps. On the parlay desk the legs, the
 * name and the source arrive filled in from the card he was looking at; on the
 * other screens the form opens empty, which is what it always did.
 *
 * **Prefilled is not submitted.** Every field stays editable and nothing is
 * sent until he taps. The stake and the return are deliberately NOT guessed
 * from the card: the desk does not know what his book paid him, and a wrong
 * return lands directly in the size of a hedge (see the label note above).
 */

export type RecordParlayPrefill = {
  source?: "sportsbook" | "kalshi_combo";
  label?: string;
  book?: string;
  legs?: { label: string; ticker: string }[];
};

const BLANK_LEGS = [
  { label: "", ticker: "" },
  { label: "", ticker: "" },
];

export default function RecordParlay({
  prefill,
  summary = "Record a ticket you hold",
  blurb,
}: {
  prefill?: RecordParlayPrefill;
  summary?: string;
  blurb?: string;
} = {}) {
  const router = useRouter();
  const [source, setSource] = useState<"sportsbook" | "kalshi_combo">(
    prefill?.source ?? "sportsbook",
  );
  const [label, setLabel] = useState(prefill?.label ?? "");
  const [book, setBook] = useState(prefill?.book ?? "");
  const [stake, setStake] = useState("");
  const [payout, setPayout] = useState("");
  const [legs, setLegs] = useState<{ label: string; ticker: string }[]>(
    prefill?.legs && prefill.legs.length > 0 ? prefill.legs : BLANK_LEGS,
  );
  const [busy, setBusy] = useState(false);
  const [refused, setRefused] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  function setLeg(index: number, field: "label" | "ticker", value: string) {
    setLegs((current) =>
      current.map((leg, i) => (i === index ? { ...leg, [field]: value } : leg)),
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setRefused(null);

    const named: HeldLegInput[] = legs
      .filter((leg) => leg.label.trim().length > 0)
      .map((leg) => ({
        label: leg.label.trim(),
        // Every recorded leg is the side that has to WIN for the ticket to
        // pay, which is the YES side of its own market. The hedge is the
        // other one, and the server picks it.
        side: "yes",
        ticker: leg.ticker.trim().toUpperCase() || null,
      }));

    // Dollars in the form, cents on the wire, tenths in the database. The
    // conversion happens once at each boundary and never twice at one.
    const answer = await recordHeldPosition({
      source,
      label: label.trim(),
      stake_cents: Math.round(Number(stake) * 100),
      return_cents: Math.round(Number(payout) * 100),
      legs: named,
      book: book.trim() || null,
    });

    setBusy(false);
    if (!answer.ok) {
      setRefused(answer.detail);
      return;
    }
    setStake("");
    setPayout("");
    // **The prefilled fields go back to the prefill, not to blank.** On a
    // parlay card this form belongs to one card and will still be sitting
    // under it after the tap; clearing the legs there would leave an empty
    // form attached to a named card, which reads as if the record failed.
    setLabel(prefill?.label ?? "");
    setBook(prefill?.book ?? "");
    setLegs(prefill?.legs && prefill.legs.length > 0 ? prefill.legs : BLANK_LEGS);
    setDone(true);
    router.refresh();
  }

  return (
    <details className="mt-4 rounded-lg border border-border p-4">
      <summary className="cursor-pointer text-sm font-semibold uppercase tracking-widest">
        {summary}
      </summary>
      <p className="mt-2 text-xs leading-snug text-muted">
        {blurb ??
          "The desk cannot see a bet you placed somewhere else."}{" "}
        Tell it the stake, the total return and the <Term k="leg">legs</Term>,
        and it will watch them while the games run.
      </p>

      <form onSubmit={submit} className="mt-3 flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted">Where is it</span>
          <select
            value={source}
            onChange={(e) =>
              setSource(e.target.value as "sportsbook" | "kalshi_combo")
            }
            className="min-h-9 rounded border border-border bg-transparent px-2 text-sm"
          >
            <option value="sportsbook">A sportsbook slip</option>
            <option value="kalshi_combo">A Kalshi combo</option>
          </select>
        </label>

        <label className="flex flex-col gap-1 text-xs">
          <span className="text-muted">What to call it</span>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Saturday six"
            className="min-h-9 rounded border border-border bg-transparent px-2 text-sm"
          />
        </label>

        {source === "sportsbook" && (
          <label className="flex flex-col gap-1 text-xs">
            <span className="text-muted">Which book (optional)</span>
            <input
              value={book}
              onChange={(e) => setBook(e.target.value)}
              className="min-h-9 rounded border border-border bg-transparent px-2 text-sm"
            />
          </label>
        )}

        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1 text-xs">
            <span className="text-muted">Stake ($)</span>
            <input
              inputMode="decimal"
              value={stake}
              onChange={(e) => setStake(e.target.value)}
              placeholder="5.00"
              className="tabular min-h-9 rounded border border-border bg-transparent px-2 text-sm"
            />
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs">
            {/*
              TOTAL back, not "to win". The equalising hedge is exactly this
              many dollars of contracts, so the ambiguity would land in the
              size rather than in the wording.
            */}
            <span className="text-muted">Returns in total ($)</span>
            <input
              inputMode="decimal"
              value={payout}
              onChange={(e) => setPayout(e.target.value)}
              placeholder="333.33"
              className="tabular min-h-9 rounded border border-border bg-transparent px-2 text-sm"
            />
          </label>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-xs text-muted">
            Legs — the Kalshi ticker is optional, and a leg without one simply
            cannot be priced or hedged
          </legend>
          {legs.map((leg, index) => (
            <div key={index} className="flex gap-2">
              <input
                value={leg.label}
                onChange={(e) => setLeg(index, "label", e.target.value)}
                placeholder="Cincinnati to win"
                className="min-h-9 flex-1 rounded border border-border bg-transparent px-2 text-sm"
              />
              <input
                value={leg.ticker}
                onChange={(e) => setLeg(index, "ticker", e.target.value)}
                placeholder="KXMLBGAME-…-CIN"
                className="min-h-9 flex-1 rounded border border-border bg-transparent px-2 font-mono text-[11px]"
              />
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setLegs((current) => [...current, { label: "", ticker: "" }])
            }
            className="min-h-9 self-start rounded border border-border px-3 text-[11px] uppercase tracking-wide"
          >
            another leg
          </button>
        </fieldset>

        <button
          type="submit"
          disabled={busy}
          className="min-h-11 rounded border border-border px-4 text-sm font-semibold uppercase tracking-wide disabled:opacity-50"
        >
          {busy ? "recording…" : "record it"}
        </button>

        {/* The server's own sentence, verbatim. */}
        {refused && <p className="text-xs text-muted">{refused}</p>}

        {/*
          **Says where it went.** This form used to render only on /hedge, so
          a successful record was self-evident: the position appeared above it
          on the same screen. On the parlay desk and the slate there is
          nothing to see, and a form that empties its money fields and says
          nothing is indistinguishable from one that failed quietly.
        */}
        {done && !refused && (
          <p className="text-xs text-muted">
            Recorded.{" "}
            <a href="/hedge" className="underline">
              Watch it on the Hedging screen
            </a>{" "}
            while the games run.
          </p>
        )}
      </form>
    </details>
  );
}
