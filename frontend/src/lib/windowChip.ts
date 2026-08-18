/**
 * The nav's window chip: one line of *state*, never navigation and never
 * permission.
 *
 * The xl shell leaves dead air between the brand and the links, and the one
 * fact worth that space is the thing a person otherwise scrolls back up to
 * check: is the sweep window open right now. The chip renders in muted ink at
 * every state on purpose — "open" here means *the recorder's window is open*
 * (prices are being kept fresh), which is a statement about freshness and
 * never about there being anything to bet. A green chip would read as
 * permission, and `is_open` has opened onto an empty board on almost every
 * window this instance has recorded.
 *
 * Like `sweepTone.ts`, this is plain TypeScript with no React import so the
 * real function can be executed by `node` from a pytest
 * (`tests/test_window_chip.py`) rather than substring-read. The copy lives
 * here rather than in the component for the same reason: the label *is* the
 * behaviour.
 */

/**
 * Exactly the fields the chip depends on — a deliberate subset of
 * `ActionableWindow`, so a test states a whole world in four values and the
 * function cannot quietly start reading something else.
 */
export type ChipFacts = {
  now_ms: number;
  is_open: boolean;
  open_until_ms: number | null;
  next_sweep_ms: number | null;
};

export type Chip = {
  state: "open" | "closed";
  label: string;
};

/** "3h 12m" / "42m" / "under a minute" — coarse on purpose; the chip is a
    glance, and a seconds counter in the nav would be motion that means
    nothing. */
function coarse(ms: number): string {
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "under a minute";
  if (minutes < 60) return `${minutes}m`;
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

export function windowChip(w: ChipFacts): Chip {
  if (w.is_open) {
    // "priceable", never "bettable": the words must survive being read alone,
    // away from the banner that explains them.
    if (w.open_until_ms !== null && w.open_until_ms > w.now_ms) {
      return {
        state: "open",
        label: `window open · fresh for ${coarse(w.open_until_ms - w.now_ms)}`,
      };
    }
    return { state: "open", label: "window open" };
  }
  if (w.next_sweep_ms !== null && w.next_sweep_ms > w.now_ms) {
    return {
      state: "closed",
      label: `window closed · next sweep in ${coarse(w.next_sweep_ms - w.now_ms)}`,
    };
  }
  // No sweep scheduled is a different quiet from "one is coming". Saying
  // nothing more is the honest version: the Board's banner carries the why.
  return { state: "closed", label: "window closed" };
}
