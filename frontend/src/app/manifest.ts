/**
 * What makes this a home-screen app rather than a bookmark.
 *
 * Served at `/manifest.webmanifest` (Next special-cases the `manifest` route
 * name). Safari reads it when you tap Share -> Add to Home Screen: `name` and
 * `short_name` fill the sheet, `display: "standalone"` is what drops the URL
 * bar and the toolbar on launch, and `start_url` is where the icon lands you.
 *
 * **It must be in `middleware.ts`'s PUBLIC_PATHS and this is not optional.**
 * A manifest is fetched with credentials OMITTED unless the link tag carries
 * `crossorigin="use-credentials"`, and Next only emits that on Vercel previews
 * (`next/dist/lib/metadata/metadata.js`, the manifest branch). Behind the
 * cookie gate it would answer a 302 to `/login`, and the failure is silent:
 * iOS falls back to a screenshot of the page as the icon and treats the whole
 * thing as a bookmark. There is nothing here that is not already public.
 *
 * **There is no service worker and no offline entry, and that is a decision.**
 * A service worker is a cache that can get stuck, and the thing it would be
 * caching is prices. `backend/notify/discord.py` says it plainly: a broken
 * feed makes the Board look calm, because stale numbers render exactly like
 * fresh ones. Rule 1 of this repo treats a number you cannot date as a bug.
 * So every price comes off the network every time, and an offline cockpit is
 * refused rather than unbuilt.
 *
 * **No web push either**, for a smaller reason: `notify/discord.py` already
 * delivers native phone push and was chosen for it. iOS only allows web push
 * to an INSTALLED app, so this file is the precondition if that ever changes
 * -- it is not the start of it.
 *
 * Android/desktop install is not targeted: no 192/512 or maskable PNG icons,
 * because the operator carries an iPhone. Chrome will still offer an install
 * and will scale the SVG; if a second platform ever matters, that is the line
 * to add.
 */

import type { MetadataRoute } from "next";

import { THEME_COLOR } from "@/lib/theme";

export default function manifest(): MetadataRoute.Manifest {
  return {
    // The full name is the install sheet's heading; `short_name` is what fits
    // under a home-screen icon before iOS truncates it (~12 characters).
    name: "Kalshi Cockpit",
    short_name: "Cockpit",
    // No `description`. iOS never shows it, and every string in
    // `frontend/src` is scanned by `tests/test_glossary_coverage.py` -- which
    // already exempts `layout.tsx` for the word "devigged" in its meta
    // description. A second copy of that sentence would buy a second
    // exemption for text nobody reads.
    // `id` pins the app's identity across a change of `start_url`, so a later
    // edit to the landing screen updates the installed app instead of offering
    // a second one beside it.
    id: "/",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    // The page ground, not the brand indigo: this paints the area behind the
    // status bar and the launch screen, and a full-bleed accent there would be
    // a colour the app never otherwise shows.
    background_color: THEME_COLOR.light,
    theme_color: THEME_COLOR.light,
    icons: [
      // The favicon tile, which every install surface except Apple's will
      // accept and scale. Apple's comes from `app/apple-icon.tsx`, which is
      // declared by a `<link rel="apple-touch-icon">` rather than from here --
      // Safari does not read manifest icons for the home screen.
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
    ],
  };
}
