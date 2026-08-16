/**
 * Inline SVG caricatures for the desk crew.
 *
 * **Inline, not an asset.** No image file, no CDN, no `next/image` pipeline,
 * and nothing to 404 on a phone with a bad connection. Each face is a handful
 * of paths drawn in `currentColor`, so it inherits the theme the same way the
 * text beside it does and needs no light/dark variant.
 *
 * **Caricature, not likeness.** These are house characters. None of them is a
 * portrait of a living person, and the one who has a real-world echo -- Willy
 * Balters -- is deliberately a fiction with a fiction's name. See
 * `CrewBubble.tsx` for why that rule exists and where it came from.
 *
 * Joe called these a placeholder ("caricatures for now, I'll think of a
 * different style later"), so the component takes the whole face as a `kind`
 * rather than spreading paths through the bubble: restyling means editing one
 * file, not hunting inline `<svg>` blocks.
 */

export type CrewFace = "skeptic" | "willy" | "scout";

/**
 * One 24x24 face. `aria-hidden` on every one of them: the name and role are
 * already text beside the avatar, so announcing the drawing would read the
 * same person twice.
 */
export default function CrewAvatar({
  kind,
  className = "",
}: {
  kind: CrewFace;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      className={className}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {kind === "skeptic" && (
        <>
          {/* Head, one eye narrowed to a line, a flat mouth: the face of
              somebody about to tell you why it will not work. */}
          <circle cx="12" cy="12" r="9" />
          <path d="M7.5 10.2h3" />
          <circle cx="15.2" cy="10.4" r="1.1" fill="currentColor" stroke="none" />
          <path d="M6.6 8.1c1-.9 2.4-1.1 3.6-.6" />
          <path d="M17.6 7.6c-1-.7-2.3-.7-3.3-.1" />
          <path d="M9 16.2c1.6-.7 3.4-.7 5 0" />
        </>
      )}

      {kind === "willy" && (
        <>
          {/* Brimmed hat and a grin. The hat is the whole character: somebody
              who has been at the counter a long time and is not startled. */}
          <circle cx="12" cy="13.2" r="7.4" />
          <path d="M3.4 7.6h17.2" />
          <path d="M6.6 7.6c.6-3 2.7-4.4 5.4-4.4s4.8 1.4 5.4 4.4" />
          <circle cx="9.4" cy="12.4" r="1" fill="currentColor" stroke="none" />
          <circle cx="14.6" cy="12.4" r="1" fill="currentColor" stroke="none" />
          <path d="M8.9 16c1.9 1.5 4.3 1.5 6.2 0" />
        </>
      )}

      {kind === "scout" && (
        <>
          {/* Cap and binoculars, both lowered. He is not looking at anything,
              which is exactly what his line says. */}
          <circle cx="12" cy="13" r="7.6" />
          <path d="M4.6 8.6h14.8" />
          <path d="M5.8 8.6c.9-2.7 3.2-4.2 6.2-4.2 1.7 0 3.2.5 4.3 1.4" />
          <path d="M16.3 5.8 21 7.2" />
          <circle cx="9.2" cy="13.6" r="2.1" />
          <circle cx="15" cy="13.6" r="2.1" />
          <path d="M11.3 13.6h1.6" />
        </>
      )}
    </svg>
  );
}
