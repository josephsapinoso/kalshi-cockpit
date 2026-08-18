/**
 * The width rails, defined once.
 *
 * The Board's shell, the nav and the footer must agree on where the content
 * column sits: a board widened without its chrome hangs cards outside the nav
 * rails, which reads as a bug at every width. Before this constant the three
 * agreed by repetition (`max-w-5xl` written three times), which held only as
 * long as nobody edited one of them.
 *
 * The tiers (ADR 0047 — the desktop tier is a reading surface):
 *
 *   base–lg   `max-w-5xl` (1024px) — exactly the old layout. Everything below
 *             1280px renders byte-identically to the phone-first design.
 *   xl        84rem (1344px) — room for the Board's context rail.
 *   2xl       96rem (1536px) — the terminal cap. Deliberately not full-bleed:
 *             the page is majority prose-with-reasons, and past this width a
 *             flex row's `ml-auto` puts ~700px between a team name and the
 *             suppression code that is the row's content.
 *
 * One complete string, appended to rather than assembled: Tailwind v4 finds
 * class names by scanning source for complete literals, so a class built by
 * concatenating fragments ("max-w-" + size) would silently compile to nothing.
 */
export const SHELL_WIDTH =
  "mx-auto w-full max-w-5xl xl:max-w-[84rem] 2xl:max-w-[96rem]";
