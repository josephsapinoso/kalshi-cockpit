import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Footer from "@/components/Footer";
import Nav from "@/components/Nav";
import { THEME_COLOR } from "@/lib/theme";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Kalshi Cockpit",
  description:
    "Compares Kalshi prices against devigged sportsbook consensus. Surfaces a bet only when the edge survives fees, freshness, depth and the suspicion checks.",

  // Installed to an iPhone home screen, this launches without Safari's URL bar
  // or toolbar. `title` is what sits under the icon -- shorter than the tab
  // title, which would be truncated. See `app/manifest.ts` for the rest, and
  // for why there is no service worker.
  //
  // `statusBarStyle: "default"` and NOT "black-translucent": translucent puts
  // the page under the status bar, which only looks right with
  // `viewport-fit=cover`, and cover would make the app full-bleed in ordinary
  // Safari too -- where the element nearest the bottom edge is the ticket
  // sheet's confirm button. Not a trade worth 34 pixels.
  appleWebApp: { capable: true, title: "Cockpit", statusBarStyle: "default" },

  // The belt to `appleWebApp.capable`'s braces. Next 16 spells that flag
  // `<meta name="mobile-web-app-capable">`, having dropped the `apple-`
  // prefix; iOS honours the unprefixed name only recently, and reads the
  // manifest's `display` only from 17.4. The legacy tag is what makes an older
  // handset launch this without Safari's chrome, and it costs one line.
  // (`apple-touch-fullscreen` and `-precomposed` are deprecated here and warn;
  // this one does not.)
  other: { "apple-mobile-web-app-capable": "yes" },
};

export const viewport: Viewport = {
  // Next's own default, restated because declaring `viewport` at all replaces
  // it. Dropping either half makes every `sm:` breakpoint misfire on a phone.
  width: "device-width",
  initialScale: 1,

  // The colour behind the status bar on an installed app, and the browser
  // chrome tint elsewhere. Two entries because the theme follows the system by
  // default; `THEME_SCRIPT` below overwrites both when the reader has forced
  // one, which a media query cannot see.
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: THEME_COLOR.light },
    { media: "(prefers-color-scheme: dark)", color: THEME_COLOR.dark },
  ],
};

// The theme is applied before first paint. Without this the page renders light
// and then flips, which is worse than either theme on its own.
//
// It also repaints the `theme-color` metas, and that is why the work is done
// twice: this script runs in `<head>` and Next may not have streamed those tags
// yet, so the first pass is for the case where they are already there and the
// `DOMContentLoaded` pass is for the case where they are not. Setting a meta
// late costs a status-bar repaint, not a content flash. `lib/theme.ts`
// `applyThemeColor` is the same three lines for code that can import.
const THEME_SCRIPT = `
(function () {
  try {
    var stored = localStorage.getItem("theme");
    if (stored !== "dark" && stored !== "light") return;
    document.documentElement.dataset.theme = stored;
    var colour = stored === "dark" ? ${JSON.stringify(THEME_COLOR.dark)} : ${JSON.stringify(THEME_COLOR.light)};
    var paint = function () {
      var tags = document.querySelectorAll('meta[name="theme-color"]');
      for (var i = 0; i < tags.length; i++) tags[i].setAttribute("content", colour);
    };
    paint();
    document.addEventListener("DOMContentLoaded", paint);
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[100] focus:rounded-lg focus:bg-accent-fill focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-white"
        >
          Skip to content
        </a>
        <Nav />
        <main id="main">{children}</main>
        {/* Below the content, not in the nav row: `Nav.tsx` spends its four
            links deliberately (six until decision-map #18, 2026-09-02, when
            the six were measured already scrolling at 390px). The pages here
            were traded away on their merits and were once reachable only by
            typing a URL, which on a phone is not a route anyone takes. */}
        <Footer />
      </body>
    </html>
  );
}
