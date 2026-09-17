# ADR 0166 — The cockpit installs to the home screen as a shell, and nothing more

- **Status:** accepted
- **Date:** 2026-09-17
- **Decider:** Joe — asked whether the project could be a phone app "similar to
  how some websites on Safari allow you to make an app shortcut on an iPhone",
  and then chose between three scopes: **installable shell only**, iPhone only,
  and move the app icon off the retired brand crimson.
- **Amends** the `.sheet-safe-bottom` rationale in `globals.css` (corrected, not
  deleted) and finishes the palette migration ADR 0081 started.

## The decision

The web app becomes installable to an iPhone home screen — a manifest declaring
`display: "standalone"`, an apple-touch icon, and the Apple metadata — **and
takes on no new runtime behaviour at all.**

Specifically refused, in the same breath and for stated reasons:

| refused | why |
|---|---|
| a service worker | what it would cache is prices |
| any offline mode | same |
| web push | Discord already delivers; this is its precondition, not its start |
| `viewport-fit=cover` | it goes full-bleed in ordinary Safari too |
| Android/desktop icon sizes | one device installs this |

## Why an install is worth anything here

ADR 0071 settled that this is a personal betting desk operated from a phone and
a desk equally. On the phone it was a Safari tab: no icon, a tab-switch to
reach, and Safari's URL bar and toolbar taking roughly 110px of a 390px-wide
handset — on a screen whose most crowded element is the ticket sheet, whose
confirm button is the control that spends money.

An install changes the launch surface and nothing else. That is the whole
feature, and it is worth saying plainly because "make it an app" usually means
something larger.

## What it explicitly does not change

**It does not change how an alert reaches him.** `backend/notify/discord.py`
carries the reason it was chosen in its own first paragraph: *"Discord gets
native push to a phone with no app install and no PWA quirks."* That is still
true, and a link tapped in Discord opens Safari, **not** the installed app. The
installed app is a second surface beside Safari, with its own cookie jar — so
the first launch asks for the token again. `/login` sets
`autoComplete="current-password"`, so the iOS keychain fills it, and the cookie
is good for 30 days (`lib/session.ts:30`).

Anyone reading this later and expecting the icon to "fix" the notification path
should stop here: it does not touch it.

## Why there is no service worker, and why that is a refusal rather than a gap

A service worker is a cache that can get stuck, and the thing it would be
caching is prices. This repo's own words, from the notifier that exists because
of it: *"a broken feed makes the Board look calm — prices simply stop moving,
and stale numbers render exactly like fresh ones."* Rule 1 treats a number you
cannot date as a bug until proven otherwise.

An offline cockpit would be a screen that renders a price with no way to tell
whether it is thirty seconds or thirty minutes old, at a moment when the reader
is deciding whether to spend. The correct offline behaviour for this app is to
fail visibly, which is what Safari already does.

So: every price comes off the network, every time. `manifest.ts` says so in a
comment, and `tests/test_the_phone_app_installs.py::TestNothingCachesAPrice`
fails if a `serviceWorker`, `workbox` or `sw.js` ever appears under
`frontend/src` or `frontend/public`.

**Web push follows from the same place, differently.** iOS grants web push only
to an *installed* app, so this ADR is the precondition for it. It is not taken
because Discord already does the job and a second channel delivering the same
three message classes is two places for an alert to be missed. If it is ever
wanted, the thing to decide first is which channel *stops*.

## The one line the whole feature rests on

`frontend/src/middleware.ts` gates everything except an exact-match
`PUBLIC_PATHS` set. A web app manifest is fetched **with credentials omitted**
unless its link tag carries `crossorigin="use-credentials"` — and Next 16 emits
that attribute only on Vercel previews:

    // next/dist/lib/metadata/metadata.js, the manifest branch
    crossOrigin: !manifestOrigin && process.env.VERCEL_ENV === 'preview'
      ? 'use-credentials' : undefined

So on this deployment the manifest and the icon arrive with no cookie however
signed in the reader is. Gated, they answer a 302 to `/login` — **and nothing
looks broken.** iOS does not report an error; it silently degrades to
installing a bookmark and screenshotting the page for the icon. The reader
would see a slightly wrong icon and assume that was the feature.

Both pathnames are chosen by Next, and both are exact:

| route file | served at |
|---|---|
| `app/manifest.ts` | `/manifest.webmanifest` |
| `app/apple-icon.tsx` | `/apple-icon` — no extension, hash in the **query** |

`/apple-icon.png` in the allowlist would match nothing, and matching nothing is
the failure that looks like success. Measured against a real build with
`APP_AUTH_TOKEN` set and no cookie: both 200, `/icon.svg` 200, `/` and `/picks`
307 to `/login`.

Neither file carries anything private — a name, a colour, a start URL, and a
letter on a square. `/icon.svg` has been in that same allowlist since the gate
was built.

## `viewport-fit=cover`: considered, declined, and a comment corrected

`globals.css` has defined `.sheet-safe-bottom` as
`padding-bottom: max(0.75rem, env(safe-area-inset-bottom))` since the ticket
sheet was built, commented *"keeps the action bar clear of the home indicator
on a notched handset"*.

**`env(safe-area-inset-*)` resolves to 0 unless the viewport declares
`viewport-fit=cover`**, and nothing here ever did. The class has always
computed to a flat `0.75rem`; the comment described a value that was never
non-zero.

Nothing is broken by that — without `cover`, iOS lays a standalone web app's
content *inside* the safe area on its own, so the bar was never under the home
indicator. Turning `cover` on would buy about 34 pixels and would apply in
**ordinary Safari too**, where the element nearest the bottom edge is
`TicketSheet.tsx`'s confirm button. That is a real regression risk on the path
Joe uses today, for a cosmetic gain.

So `cover` stays off, the `max()` stays as the expression that will be correct
the day someone turns it on, and the comment is rewritten to say what is
actually true. This is the pattern `tasks/lessons.md` already names: a comment
explaining why something is safe goes stale silently, because nothing executes
it.

`tests/..._installs.py::TestTheSafeAreaIsNotTurnedOn` refuses `viewportFit`
anywhere under `frontend/src`, so turning it on is a decision someone has to
make deliberately rather than an edit that slips in.

## The favicon stops wearing the colour that means *lose*

ADR 0081 gave up the brand crimson so red could mean a loss: `--negative` is
`#aa0000` now, and the nav's logo tile went indigo (`--accent-fill`,
`#2f3d8f`). It missed `frontend/src/app/icon.svg` — the one file outside
`globals.css` with a palette hex in it — whose comment still described itself
as "the nav logo tile, at favicon size: accent crimson". For three weeks the
tab badge wore the colour that means money was lost, next to a nav tile that
did not.

A home-screen icon renders that mark at 180px on the handset, so it is
corrected here rather than institutionalised at eight times the size. The hexes
now live once in `frontend/src/lib/theme.ts`, and a test pins them against
`--background` in `globals.css` in both themes — `icon.svg` repeats them as
literals only because an SVG cannot import.

## What this does not establish

- **That iOS accepts any of it.** The tests read source; the curls read a local
  build. Only a real Add to Home Screen on the handset shows whether the sheet
  offers the indigo tile or a screenshot of the page.
- **That the generated PNG is legible.** `apple-icon.tsx` is drawn by Satori,
  which has one bundled font and has never heard of Georgia. The "K" is set in
  whatever face `next/og` ships. If it reads badly, the fallback is a committed
  180×180 PNG in `frontend/public` — which would be this repo's first binary.
- **That the container serves the icon.** `next build` reports `/apple-icon` as
  prerendered static content, so the runtime should never invoke Satori, but
  the `@vercel/og` wasm tracing into `.next/standalone` was not tested inside a
  built image. First curl after deploy answers it.
- **Anything about Android or desktop install.** They will offer one; nobody
  checked what it looks like, because nobody uses it.
