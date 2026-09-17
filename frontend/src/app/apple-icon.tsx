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
 * **The typeface is not Georgia and the weight below does nothing.** Satori
 * (what `ImageResponse` draws with) has exactly one font, the Geist Regular
 * bundled with `next/og`, so `fontWeight: 700` has no heavier face to resolve
 * to and the rendered K is lighter than the favicon's bold serif. Confirmed by
 * looking at the PNG, not assumed. It is kept as the declared intent for the
 * day a face is supplied, and said aloud here so the next reader does not
 * believe a bold that is not there -- the same defect as the `env()` term in
 * `.sheet-safe-bottom`. Shipping a webfont to paint one letter is not worth
 * the bytes; the mark is the indigo tile.
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
