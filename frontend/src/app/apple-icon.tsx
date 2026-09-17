/**
 * The home-screen icon, for an iPhone that has installed this desk.
 *
 * Safari will not use an SVG here -- `icon.svg` is the favicon and the
 * add-to-home-screen sheet ignores it -- so this renders the same tile to a
 * 180x180 PNG at build time. Generated rather than committed because the repo
 * is public and a binary that drifts from `icon.svg` cannot be diffed. The
 * colours come from `lib/theme.ts`; `icon.svg` repeats them as literals
 * because an SVG cannot import.
 *
 * **No rounded corner, deliberately.** iOS masks the icon with its own
 * squircle. `icon.svg` carries `rx="7"` because a browser tab does not mask;
 * repeating it here would round an already-rounded corner and leave four
 * white notches on the home screen.
 *
 * The typeface is not Georgia. Satori (what `ImageResponse` draws with) has
 * only the font it bundles, and shipping a Georgia-metric webfont to paint one
 * letter at 180px is not worth the bytes. The mark is the indigo tile.
 */

import { ImageResponse } from "next/og";

import { BRAND_TILE, THEME_COLOR } from "@/lib/theme";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: BRAND_TILE,
          color: THEME_COLOR.light,
          fontSize: 116,
          fontWeight: 700,
        }}
      >
        K
      </div>
    ),
    size,
  );
}
