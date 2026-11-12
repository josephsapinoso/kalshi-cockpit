import type { BetsRecord } from "@/lib/api";
import type { BetsPopulation, SameGameSplit } from "@/lib/types/bets";
import Term from "@/components/Term";

/**
 * #397: where the money went, by price paid and by number of legs.
 *
 * Combinations only. Every figure is the server's: rows come in its FIXED
 * order (price bands low to high, leg counts ascending) and are never
 * re-ordered by what happened. No colour by sign, nothing divided here, no
 * range on a cell that is too small to carry one. A combination with no
 * recorded leg list is COUNTED on its own row, never dropped.
 */

/**
 * Types are local because `lib/types/bets.ts` is outside this ticket's lane
 * and `api.ts` declares none (test_no_type_alias_or_interface_is_declared_in_api_ts).
 */
export type ShapeCell = {
  n: number;
  won: number;
  expected: number;
  too_few: boolean;
  range_low: number | null;
  range_high: number | null;
  staked_tenths: number;
  net_tenths: number;
};
type LegViews = {
  leg_counts: (ShapeCell & { legs: number })[];
  same_game_split: SameGameSplit;
  no_leg_list: { n: number; staked_tenths: number; net_tenths: number };
};
export type ByShape = LegViews & {
  price_bands: (ShapeCell & { label: string })[];
  unbanded: { n: number; staked_tenths: number; net_tenths: number };
  uncomputable: number;
  staked_tenths: number;
  net_tenths: number;
  /** #423: the three leg views again, over the combinations bought off the
   *  desk only. */
  off_desk?: LegViews;
};

function dollars(tenths: number, signed: boolean): string {
  const sign = tenths < 0 ? "-" : signed ? "+" : "";
  return `${sign}$${(Math.abs(tenths) / 1000).toFixed(2)}`;
}

function CellText({ cell, noun }: { cell: ShapeCell; noun: string }) {
  return (
    <>
      {cell.n} {noun} · {cell.won} won ·{" "}
      {cell.too_few ? (
        <Term k="too_few">too few to judge</Term>
      ) : (
        <>
          about {cell.expected} expected to win (range {cell.range_low} to{" "}
          {cell.range_high})
        </>
      )}{" "}
      · staked {dollars(cell.staked_tenths, false)} · net{" "}
      {dollars(cell.net_tenths, true)}
    </>
  );
}

export default function ShapeStrip({
  record,
  population = "all",
}: {
  record: BetsRecord;
  population?: BetsPopulation;
}) {
  const data = (record as BetsRecord & { by_shape?: ByShape }).by_shape;
  if (!data) return null;
  // #423: the leg views for the chosen population; the price bands stay the
  // whole record's. The rows, their order and the wording do not change.
  const view: LegViews =
    population === "off_desk" && data.off_desk ? data.off_desk : data;
  const nothing =
    data.price_bands.every((b) => b.n === 0) &&
    data.leg_counts.length === 0 &&
    data.no_leg_list.n === 0 &&
    (data.off_desk?.leg_counts.length ?? 0) === 0 &&
    data.unbanded.n === 0;
  if (nothing) return null;
  return (
    <details open className="mt-1 max-w-[65ch] text-xs text-muted">
      <summary className="cursor-pointer">
        <Term k="stake_weighted">Where the money went</Term>
      </summary>
      <p className="mt-1 max-w-prose">
        Combinations only. Settled bets, whole record.
      </p>
      <p className="mt-1 font-medium">By price paid</p>
      <ul className="mt-1 space-y-1 font-mono">
        {data.price_bands.map((band) => (
          <li key={band.label}>
            {band.label === "under 10c" ? (
              <Term k="longshot">under 10c</Term>
            ) : (
              band.label
            )}
            : <CellText cell={band} noun="combos" />
          </li>
        ))}
        {data.unbanded.n > 0 && (
          <li>
            price not on the grid: {data.unbanded.n} combos · staked{" "}
            {dollars(data.unbanded.staked_tenths, false)} · net{" "}
            {dollars(data.unbanded.net_tenths, true)}
          </li>
        )}
      </ul>
      <p className="mt-2 font-medium">By number of legs</p>
      <ul className="mt-1 space-y-1 font-mono">
        {view.leg_counts.map((row) => (
          <li key={row.legs}>
            {row.legs} legs: <CellText cell={row} noun="combos" />
          </li>
        ))}
        <li>
          no leg list: {view.no_leg_list.n} combos · staked{" "}
          {dollars(view.no_leg_list.staked_tenths, false)} · net{" "}
          {dollars(view.no_leg_list.net_tenths, true)}
        </li>
      </ul>
      <p className="mt-2 font-medium">
        <Term k="same_game">Same-game</Term> or{" "}
        <Term k="cross_game">cross-game</Term>
      </p>
      <ul className="mt-1 space-y-1 font-mono">
        {view.same_game_split.cells.map((cell) => (
          <li key={cell.split}>
            {cell.split === "same_game" ? (
              <Term k="same_game">same-game</Term>
            ) : (
              <Term k="cross_game">cross-game</Term>
            )}
            : <CellText cell={cell} noun="combos" />
          </li>
        ))}
        {view.same_game_split.unclassified.n > 0 && (
          <li>
            games not readable: {view.same_game_split.unclassified.n} combos ·
            staked {dollars(view.same_game_split.unclassified.staked_tenths, false)}{" "}
            · net {dollars(view.same_game_split.unclassified.net_tenths, true)}
          </li>
        )}
      </ul>
      {data.uncomputable > 0 && (
        <p className="mt-1">
          {data.uncomputable} combos left out because their result or price
          could not be read.
        </p>
      )}
    </details>
  );
}
