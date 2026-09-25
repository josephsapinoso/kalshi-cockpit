import type { ButtonHTMLAttributes, ReactNode } from "react";

/**
 * The few shapes the parlay desk repeats, written once (#158).
 *
 * Before this file every block on a parlay card hand-rolled its own Tailwind:
 * four corner radii, eight text sizes, and a filled button in three places on
 * one card. That is what made an expanded card read as a pile rather than a
 * page. These are deliberately dumb -- no state, no data, no arithmetic -- so
 * that moving a block onto them changes how it looks and nothing it says.
 *
 * **`primary` is for money only** (ADR 0061 section 3): a filled accent
 * control is a claim that pressing it is the point of the screen. Opening a
 * panel, asking a question and retrying are `secondary` or `quiet`.
 */

type Tone = "primary" | "secondary" | "quiet";

const BUTTON: Record<Tone, string> = {
  primary:
    "rounded-lg bg-accent-fill px-4 py-2 text-sm font-semibold text-white disabled:opacity-60",
  secondary:
    "rounded-lg border border-border-strong px-4 py-2 text-sm font-semibold hover:bg-accent-soft disabled:opacity-60",
  quiet:
    "rounded-lg px-2 py-1 text-sm font-semibold text-accent underline-offset-4 hover:underline disabled:opacity-60",
};

export function Button({
  tone = "secondary",
  className = "",
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button type={type} className={`${BUTTON[tone]} ${className}`} {...rest} />
  );
}

/** The small caps label that heads a block. */
export function SectionLabel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      className={`font-mono text-[0.65rem] uppercase tracking-widest text-muted ${className}`}
    >
      {children}
    </p>
  );
}

/**
 * A label over one big number. The number is always a server-rendered
 * string; this draws it and never computes it.
 */
export function Stat({
  label,
  value,
  sub,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted">{label}</p>
      <p className="tabular text-2xl font-semibold leading-tight">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

/**
 * The ochre strip: a warning, a refusal, something to read before tapping.
 * Never red -- red means lose (ADR 0081).
 */
export function Notice({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-accent-2/50 bg-accent-2-soft px-3 py-2 text-xs leading-snug ${className}`}
    >
      {children}
    </div>
  );
}
