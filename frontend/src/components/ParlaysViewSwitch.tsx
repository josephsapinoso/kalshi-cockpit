import Link from "next/link";

import {
  PARLAYS_VIEWS,
  parlaysViewHref,
  type ParlaysView,
} from "@/lib/parlaysView";

/**
 * The segmented switch under the `/parlays` header (#221): one section at a
 * time, chosen by `?view=`. Plain links, like `WindowPicker`, so a view is
 * linkable and survives a reload, and the league / kickoff / window cut in
 * the address is carried across every switch.
 *
 * `prefetch={false}` for the reason `FilterBar` gives: the page is
 * `force-dynamic` and each view is a full server render.
 *
 * Nothing here orders anything. The three sections are always in the same
 * order, and none is ranked above another.
 */
export default function ParlaysViewSwitch({
  view,
  params,
}: {
  view: ParlaysView;
  /** The address's own query, so the cut survives the switch. */
  params: { league?: string; within_hours?: string; horizon?: string };
}) {
  return (
    <nav aria-label="Parlay sections" className="mb-2">
      <div className="grid grid-cols-3 gap-1 rounded-lg border border-border p-1">
        {PARLAYS_VIEWS.map((choice) => {
          const active = choice.key === view;
          return (
            <Link
              key={choice.key}
              href={parlaysViewHref(choice.key, params)}
              prefetch={false}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-11 items-center justify-center rounded-md px-1 text-center text-sm leading-tight ${
                active
                  ? "bg-accent-soft font-semibold text-foreground"
                  : "text-muted"
              }`}
            >
              {choice.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
