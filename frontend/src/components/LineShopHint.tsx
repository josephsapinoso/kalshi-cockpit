/**
 * The line-shopping hint on a Games row (#245).
 *
 * On a two-outcome game, YES on one team and NO on the other are the same
 * opinion bought through two different books. When the other way is cheaper
 * after fees the server says so; this component only prints what it sent.
 *
 * **The sentence is the server's (`backend/line_shop.py`), not retyped here**,
 * so the one line that says "it cuts what you pay, it does not create an edge"
 * exists once. The two prices and the depth at each ask are shown beside it as
 * figures, so the reader sees what was compared, not just a verdict.
 *
 * No colour tone: a cheaper route is a fact about cost, and green would read as
 * a claim that the bet is good. No link, no sort, no count: nothing in the list
 * is ordered or filtered by this (ADR 0071 §2.5).
 */

import type { LineShopData, LineShopLeg } from "@/lib/api";

function Leg({ label, leg }: { label: string; leg: LineShopLeg }) {
  return (
    <span className="tabular">
      {label}: {leg.side.toUpperCase()}
      {leg.team ? ` ${leg.team}` : ""} at {leg.ask_display}
      <span className="text-muted"> · {leg.depth.toLocaleString("en-US")} at that ask</span>
    </span>
  );
}

export default function LineShopHint({
  hint,
}: {
  hint: LineShopData | null | undefined;
}) {
  if (!hint) return null;
  return (
    <div
      className="w-full break-words text-xs leading-snug text-muted xl:col-span-full"
      data-line-shop
    >
      <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-foreground">
        <Leg label="Cheaper" leg={hint.cheaper} />
        <Leg label="This row" leg={hint.current} />
      </div>
      <div>{hint.copy}</div>
    </div>
  );
}
