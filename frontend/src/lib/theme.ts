/**
 * The page ground, in both themes, defined once.
 *
 * These are `--background` from `globals.css` -- light `:root`, dark
 * `@media (prefers-color-scheme: dark)` / `[data-theme="dark"]`. They exist as
 * TypeScript because three consumers need the literal and CSS custom
 * properties are not readable from any of them:
 *
 *   - `app/manifest.ts`      `background_color` / `theme_color`
 *   - `app/layout.tsx`       the `themeColor` viewport entries, and the inline
 *                            pre-paint script that has to follow a forced theme
 *   - `components/ThemeToggle.tsx`   the same, on toggle
 *
 * Same argument as `lib/shell.ts`: before that constant the width rails agreed
 * by repetition, which held exactly as long as nobody edited one of them. A
 * status bar that disagrees with the page under it is the same defect one
 * layer up.
 *
 * **If you change `--background` in `globals.css`, change it here.** There is
 * no build step that can notice.
 */

export const THEME_COLOR = {
  light: "#fbfaf8",
  dark: "#0c0a09",
} as const;

/** The mark's ground: `--accent-fill`, light theme. Shared with `icon.svg` and
 *  `app/apple-icon.tsx`, which cannot import anything. */
export const BRAND_TILE = "#2f3d8f";

/**
 * Paint the status bar to match a FORCED theme.
 *
 * `app/layout.tsx` declares two `<meta name="theme-color">` tags, one per
 * `prefers-color-scheme`. Those are correct for a reader following the system
 * and they are all a reader without JavaScript gets -- but they cannot see
 * `localStorage.theme`, so someone forcing light on a dark handset would get a
 * black bar over a cream page. Overwriting BOTH tags rather than deleting one
 * means whichever the browser matches carries the same answer.
 *
 * The pre-paint script in `layout.tsx` repeats these three lines as a string,
 * because it has to run before React and cannot import. Change both.
 */
export function applyThemeColor(theme: "light" | "dark"): void {
  const tags = document.querySelectorAll('meta[name="theme-color"]');
  for (const tag of tags) tag.setAttribute("content", THEME_COLOR[theme]);
}
