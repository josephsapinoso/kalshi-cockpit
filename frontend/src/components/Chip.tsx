import Link from "next/link";

/**
 * The one chip (#414, town hall G finding #25). Before this the desk had three
 * styles: FilterBar's link chip, GameScriptCard's button chip and
 * WindowPicker's squared link. All three now render here, at a 44px tap height
 * (`min-h-11`) so a thumb hits them on the phone.
 *
 * A chip with `href` is a plain `Link` (state in the URL); a chip with
 * `onClick` is a toggle button (state on the client). `active` is the current
 * choice in both.
 */
const BASE =
  "inline-flex min-h-11 items-center rounded-full border px-3 text-sm transition-colors";

function tone(active: boolean): string {
  return active
    ? "border-foreground bg-foreground text-background"
    : "border-border text-muted hover:border-border-strong hover:text-foreground";
}

export default function Chip(
  props: { active: boolean; children: React.ReactNode } & (
    | { href: string; onClick?: undefined }
    | { href?: undefined; onClick: () => void }
  ),
) {
  const { active, children } = props;
  if (props.href !== undefined) {
    return (
      <Link
        href={props.href}
        prefetch={false}
        aria-current={active ? "true" : undefined}
        className={`${BASE} ${tone(active)}`}
      >
        {children}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={props.onClick}
      aria-pressed={active}
      className={`${BASE} ${tone(active)}`}
    >
      {children}
    </button>
  );
}
