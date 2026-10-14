import type { BetsRecord } from "@/lib/api";

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
export type ByShape = {
  price_bands: (ShapeCell & { label: string })[];
  unbanded: { n: number; staked_tenths: number; net_tenths: number };
  leg_counts: (ShapeCell & { legs: number })[];
  no_leg_list: { n: number; staked_tenths: number; net_tenths: number };
  uncomputable: number;
  staked_tenths: number;
  net_tenths: number;
};

function dollars(tenths: number, signed: boolean): string {
  const sign = tenths < 0 ? "-" : signed ? "+" : "";
  return `${sign}$${(Math.abs(tenths) / 1000).toFixed(2)}`;
}

function cellText(cell: ShapeCell, noun: string): string {
  const head = `${cell.n} ${noun} · ${cell.won} won`;
  const expected = cell.too_few
    ? " · too few to judge"
    : ` · about ${cell.expected} expected to win (range ${cell.range_low} to ${cell.range_high})`;
  return `${head}${expected} · staked ${dollars(cell.staked_tenths, false)} · net ${dollars(cell.net_tenths, true)}`;
}

export default function ShapeStrip({ record }: { record: BetsRecord }) {
  const data = (record as BetsRecord & { by_shape?: ByShape }).by_shape;
  if (!data) return null;
  const nothing =
    data.price_bands.every((b) => b.n === 0) &&
    data.leg_counts.length === 0 &&
    data.no_leg_list.n === 0 &&
    data.unbanded.n === 0;
  if (nothing) return null;
  return (
    <details className="mt-1 max-w-[65ch] text-xs text-muted">
      <summary className="cursor-pointer">Where the money went</summary>
      <p className="mt-1 max-w-prose">
        Combinations only. Settled bets, whole record.
      </p>
      <p className="mt-1 font-medium">By price paid</p>
      <ul className="mt-1 space-y-1 font-mono">
        {data.price_bands.map((band) => (
          <li key={band.label}>
            {band.label}: {cellText(band, "combos")}
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
        {data.leg_counts.map((row) => (
          <li key={row.legs}>
            {row.legs} legs: {cellText(row, "combos")}
          </li>
        ))}
        <li>
          no leg list: {data.no_leg_list.n} combos · staked{" "}
          {dollars(data.no_leg_list.staked_tenths, false)} · net{" "}
          {dollars(data.no_leg_list.net_tenths, true)}
        </li>
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
