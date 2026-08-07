"use client";

import { useState } from "react";
import { priceParlay, type ParlayLeg, type ParlayValuation } from "@/lib/api";

const DAY = 86_400_000;

/**
 * Parlay and teaser construction.
 *
 * The framing here is the opposite of every other screen: Kalshi has no parlay
 * product, so the fair-price engine is pointed *at the sportsbook* and the
 * output is the book's hold on that specific ticket. The honest answer is
 * almost always "don't", and saying so with the number attached is the useful
 * thing — a screen that only lit up on the rare good parlay would be silent
 * 99% of the time and teach nothing.
 *
 * The refusal is the feature. Two legs of the same fixture come back as a
 * refusal rather than a price, because same-game correlation is severe, its
 * sign depends on the specific pair, and multiplying the marginals overstates
 * the parlay in the direction that makes a bad bet look priceable.
 */
export default function BuilderPage() {
  const [legs, setLegs] = useState<ParlayLeg[]>([
    { label: "Chiefs ML", probability: 0.5, event_key: "E1", league: "americanfootball_nfl", commence_ms: Date.now() },
    { label: "Ravens ML", probability: 0.5, event_key: "E2", league: "americanfootball_nfl", commence_ms: Date.now() + 8 * DAY },
  ]);
  const [offered, setOffered] = useState(260);
  const [rho, setRho] = useState<string>("");
  const [result, setResult] = useState<ParlayValuation | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const update = (i: number, patch: Partial<ParlayLeg>) =>
    setLegs(legs.map((leg, j) => (j === i ? { ...leg, ...patch } : leg)));

  const addLeg = () =>
    setLegs([
      ...legs,
      {
        label: `Leg ${legs.length + 1}`,
        probability: 0.5,
        event_key: `E${legs.length + 1}`,
        league: "americanfootball_nfl",
        commence_ms: Date.now() + legs.length * 8 * DAY,
      },
    ]);

  const sameGame = new Set(legs.map((l) => l.event_key)).size < legs.length;

  async function price() {
    setBusy(true);
    setRefusal(null);
    setResult(null);
    const overrides =
      sameGame && rho.trim() !== "" && legs.length >= 2
        ? [{ a: legs[0].label, b: legs[1].label, rho: Number(rho) }]
        : [];
    const response = await priceParlay(legs, offered, overrides);
    if (response.ok) setResult(response.value);
    else setRefusal(response.refusal);
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12 sm:py-16">
      <header className="mb-8">
        <h1 className="display text-4xl sm:text-5xl">Builder</h1>
        <p className="mt-3 max-w-xl text-lg text-muted">
          Kalshi has no parlay product, so this points the fair-price engine at
          the sportsbook instead. The output is the book&rsquo;s hold on your
          specific ticket.
        </p>
      </header>

      <section className="mb-8 rounded-2xl border bg-card p-6">
        <div className="mb-4 flex items-baseline justify-between">
          <span className="text-xs font-semibold uppercase tracking-widest text-muted">
            Legs
          </span>
          <button
            onClick={addLeg}
            className="font-mono text-xs text-accent link-underline"
          >
            + add leg
          </button>
        </div>

        <div className="divide-y border-t">
          {legs.map((leg, i) => (
            <div key={i} className="flex flex-wrap items-center gap-3 py-3">
              <input
                value={leg.label}
                onChange={(e) => update(i, { label: e.target.value })}
                className="min-w-0 flex-1 rounded-xl border bg-background px-3 py-2 text-sm"
                aria-label={`Leg ${i + 1} name`}
              />
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="0.99"
                value={leg.probability}
                onChange={(e) => update(i, { probability: Number(e.target.value) })}
                className="w-24 rounded-xl border bg-background px-3 py-2 font-mono text-sm"
                aria-label={`Leg ${i + 1} devigged probability`}
              />
              <input
                value={leg.event_key}
                onChange={(e) => update(i, { event_key: e.target.value })}
                className="w-20 rounded-xl border bg-background px-3 py-2 font-mono text-sm"
                aria-label={`Leg ${i + 1} fixture`}
                title="Fixture key — two legs sharing one is a same-game parlay"
              />
              {legs.length > 2 && (
                <button
                  onClick={() => setLegs(legs.filter((_, j) => j !== i))}
                  className="font-mono text-xs text-muted link-underline"
                  aria-label={`Remove leg ${i + 1}`}
                >
                  remove
                </button>
              )}
            </div>
          ))}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-3">
          <label className="text-sm text-muted" htmlFor="offered">
            Book offers
          </label>
          <input
            id="offered"
            type="number"
            value={offered}
            onChange={(e) => setOffered(Number(e.target.value))}
            className="w-28 rounded-xl border bg-background px-3 py-2 font-mono text-sm"
          />
          <button
            onClick={price}
            disabled={busy}
            className="rounded-full bg-accent px-6 py-3 text-sm font-semibold text-white disabled:opacity-50"
          >
            {busy ? "Pricing…" : "Price it"}
          </button>
        </div>

        {sameGame && (
          <div className="mt-5 rounded-xl border bg-background p-4">
            <p className="text-sm">
              Two legs share a fixture. This will be refused unless you supply a{" "}
              <em>measured</em> correlation for that pair.
            </p>
            <div className="mt-3 flex items-center gap-3">
              <label className="text-sm text-muted" htmlFor="rho">
                ρ
              </label>
              <input
                id="rho"
                type="number"
                step="0.05"
                min="-1"
                max="1"
                value={rho}
                placeholder="unset"
                onChange={(e) => setRho(e.target.value)}
                className="w-28 rounded-xl border bg-card px-3 py-2 font-mono text-sm"
              />
              <span className="text-xs text-muted">
                leave empty to see the refusal
              </span>
            </div>
          </div>
        )}
      </section>

      {refusal && (
        <section className="mb-8 rounded-2xl border bg-card p-6">
          <p className="text-xs font-semibold uppercase tracking-widest text-negative">
            Refused
          </p>
          <p className="mt-3 leading-relaxed">{refusal}</p>
          <p className="mt-4 text-sm text-muted">
            This is the tool working. A same-game number produced from marginals
            alone would look exactly like a real one.
          </p>
        </section>
      )}

      {result && (
        <section className="mb-8 rounded-2xl border bg-card p-6">
          <p
            className={`text-3xl font-semibold tracking-tight ${
              result.is_positive_ev ? "text-positive" : "text-negative"
            }`}
          >
            {(result.hold * 100).toFixed(1)}% hold
          </p>
          <p className="mt-3 leading-relaxed">{result.verdict}</p>

          <div className="mt-6 divide-y border-t">
            <Row label="Fair price" value={signed(result.fair_american)} />
            <Row label="Book offers" value={signed(result.offered_american)} />
            <Row
              label="Fair probability"
              value={`${(result.fair_probability * 100).toFixed(2)}%`}
            />
            <Row
              label="Independence error"
              value={`${result.independence_error_points >= 0 ? "+" : ""}${result.independence_error_points.toFixed(2)} pts`}
              note="How much naive multiplication would have overstated it"
            />
            <Row
              label="Correlation"
              value={
                result.correlation_was_supplied
                  ? "measured, supplied"
                  : "modelled from timing and league"
              }
            />
          </div>

          <div className="mt-6 rounded-xl border bg-background p-4">
            <p className="text-xs font-semibold uppercase tracking-widest text-muted">
              Same combination on Kalshi
            </p>
            <p className="mt-2 font-mono text-sm">
              ${result.kalshi_alternative.total_cost_dollars.toFixed(2)} cost ·{" "}
              ${result.kalshi_alternative.total_fee_dollars.toFixed(2)} fees (
              {(result.kalshi_alternative.fee_share_of_stake * 100).toFixed(1)}%)
            </p>
            <p className="mt-3 text-sm text-muted">
              {result.kalshi_alternative.note}
            </p>
          </div>
        </section>
      )}

      <section className="rounded-2xl border bg-card p-6">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted">
          Teasers
        </p>
        <p className="mt-3 text-sm leading-relaxed">
          The Wong screen — NFL favourites of −7.5 to −8.5 and underdogs of +1.5
          to +2.5 on a six-point teaser — is live at{" "}
          <span className="font-mono text-xs">/api/builder/wong-screen</span>.
          Pricing one needs an empirical margin distribution fitted{" "}
          <em>per spread bucket</em>, and no historical results feed is connected
          yet, so the Builder refuses rather than guessing.
        </p>
        <p className="mt-3 text-sm text-muted">
          The refusal is deliberate. A league-wide distribution dragged onto an
          eight-point favourite moves the key numbers from 3 and 7 to 11 and 15,
          which prices the game worse than a plain normal curve while looking
          like data.
        </p>
      </section>
    </div>
  );
}

function Row({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 py-3">
      <span className="text-sm text-muted">
        {label}
        {note && <span className="ml-2 text-xs">— {note}</span>}
      </span>
      <span className="font-mono text-sm">{value}</span>
    </div>
  );
}

const signed = (american: number) =>
  `${american > 0 ? "+" : ""}${american}`;
