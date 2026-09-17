"""Add to Home Screen produces an app, not a bookmark.

The cockpit is operated from a phone as much as from a desk (ADR 0071). Until
2026-09-17 it was a Safari tab there: no icon, no launcher, and Safari's URL
bar and toolbar eating the vertical room the ticket sheet competes for. What
turns "Add to Home Screen" into an installed app is a web app manifest saying
`display: "standalone"` and a PNG touch icon -- neither of which this repo had.

**What this file is really guarding is the auth gate, and the reason is that
the failure is silent.** `frontend/src/middleware.ts` gates everything except
an exact-match allowlist, and a web app manifest is fetched with credentials
OMITTED unless its link tag carries `crossorigin="use-credentials"` -- which
Next emits only on Vercel previews. So the manifest and the icon arrive with no
cookie however signed in the reader is. Gated, they answer a 302 to `/login`,
and nothing looks broken: iOS quietly falls back to installing a bookmark and
screenshotting the page for the icon. Nobody would see a stack trace; they
would see a slightly wrong icon and assume that was the feature.

The pathnames are exact and Next chooses them: `/manifest.webmanifest` (it
special-cases the `manifest` route name) and `/apple-icon` -- no extension,
with the cache-busting hash in the QUERY, where an exact-match `Set` cannot see
it. `/apple-icon.png` in the allowlist would match nothing.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That the deployed instance serves any of it.** These read source. It was
  confirmed against a real build on 2026-09-17 --

      /manifest.webmanifest  200      /apple-icon  200
      /icon.svg              200      /  and  /picks  307 -> /login

  with `APP_AUTH_TOKEN` set and no cookie -- and the next session should redo
  that curl against live rather than trust this sentence.
- **That iOS accepts it.** Only a real Add to Home Screen on the handset shows
  whether the sheet offers the indigo tile or a screenshot of the page.
- **That the icon renders.** `apple-icon.tsx` is drawn by Satori, which has one
  bundled font and has never heard of Georgia. Whether the K is legible at
  180px is a thing to look at, not to assert.
- **Anything about offline behaviour**, because there is none: see
  `TestNothingCachesAPrice`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
APP = FRONTEND / "src" / "app"

MIDDLEWARE = FRONTEND / "src" / "middleware.ts"
MANIFEST = APP / "manifest.ts"
APPLE_ICON = APP / "apple-icon.tsx"
LAYOUT = APP / "layout.tsx"
ICON = APP / "icon.svg"
GLOBALS = APP / "globals.css"
THEME = FRONTEND / "src" / "lib" / "theme.ts"

#: The colour the brand gave up. ADR 0081 moved the palette off it so that red
#: could mean *lose*; `--negative` owns it now.
RETIRED_CRIMSON = "#aa0000"


def _stripped(path: Path) -> str:
    """The file with its COMMENTS STRIPPED.

    Same reason as `tests/test_frame_headers.py`: every comment added by this
    change names the thing it rejected -- `#aa0000`, `viewport-fit=cover`,
    "service worker" -- so a grep over the raw text would pass on the prose
    explaining why each was refused. A guard on the code must not be able to
    read the comment.

    **This was not hypothetical.** The first run of
    `test_the_favicon_is_not_crimson` failed on `icon.svg`'s own comment
    explaining that the fill used to be `#aa0000`, so the XML-comment pass is
    here because the SVG needed it, not for symmetry.
    """
    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.S)   # XML/SVG
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)    # block
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)     # line
    return raw


def _public_paths() -> set[str]:
    """The `PUBLIC_PATHS` literal out of the middleware, comments stripped."""
    source = _stripped(MIDDLEWARE)
    body = source[source.index("const PUBLIC_PATHS") :]
    body = body[: body.index("]")]
    return set(re.findall(r'"([^"]+)"', body))


def _css_background(selector: str) -> str:
    """`--background` under a given selector block in `globals.css`."""
    raw = GLOBALS.read_text(encoding="utf-8")
    block = raw[raw.index(selector) + len(selector) :]
    block = block[: block.index("}")]
    match = re.search(r"--background:\s*(#[0-9a-fA-F]{3,8});", block)
    assert match, f"no --background under {selector!r}"
    return match.group(1).lower()


class TestTheManifestSaysItIsAnApp:
    def test_the_manifest_route_exists(self):
        assert MANIFEST.exists(), (
            "`app/manifest.ts` is what Safari reads on Add to Home Screen. "
            "Without it the install is a bookmark."
        )

    def test_it_declares_standalone_display(self):
        """`display: "standalone"` is the whole feature -- it is what drops
        Safari's URL bar and toolbar on launch. `"browser"` installs a
        shortcut that opens a tab."""
        assert 'display: "standalone"' in _stripped(MANIFEST)

    @pytest.mark.parametrize("key", ["start_url", "scope", "id"])
    def test_it_pins_where_the_app_lives(self, key):
        """`start_url` is where the icon lands you; `scope` is what counts as
        inside the app rather than a hand-off to Safari; `id` keeps the
        install's identity if `start_url` ever moves, so a later edit updates
        the installed app instead of offering a second one beside it."""
        assert f'{key}: "/"' in _stripped(MANIFEST)


class TestTheGateLetsTheInstallThrough:
    """The silent-failure guard. See this module's docstring."""

    @pytest.mark.parametrize(
        "path,produced_by",
        [
            ("/manifest.webmanifest", MANIFEST),
            ("/apple-icon", APPLE_ICON),
        ],
    )
    def test_the_path_is_public(self, path, produced_by):
        assert produced_by.exists(), f"{produced_by.name} is what serves {path}"
        assert path in _public_paths(), (
            f"{path} is fetched without a cookie. Gated, it 302s to /login and "
            f"iOS installs a bookmark with a screenshot for an icon -- with no "
            f"error anywhere."
        )

    def test_the_allowlist_is_not_a_guess(self):
        """Next serves the generated icon at `/apple-icon`, extensionless,
        with its content hash in the query. An entry carrying `.png` matches
        nothing, and matching nothing is the failure that looks like success."""
        assert "/apple-icon.png" not in _public_paths()


class TestTheAppleMetadataIsDeclared:
    def test_layout_declares_apple_web_app(self):
        source = _stripped(LAYOUT)
        assert "appleWebApp" in source
        assert "capable: true" in source

    def test_the_status_bar_is_opaque(self):
        """`black-translucent` would put the page under the status bar, which
        needs a top safe-area inset, which needs `viewport-fit=cover` -- and
        cover goes full-bleed in ordinary Safari too. See
        `TestTheSafeAreaIsNotTurnedOn`."""
        assert 'statusBarStyle: "default"' in _stripped(LAYOUT)

    def test_the_legacy_capable_tag_is_kept(self):
        """Next 16 spells the flag `mobile-web-app-capable`, having dropped
        the `apple-` prefix. An older iOS reads only the prefixed name and
        reads the manifest's `display` not at all, so both ship."""
        assert '"apple-mobile-web-app-capable": "yes"' in _stripped(LAYOUT)


class TestTheSafeAreaIsNotTurnedOn:
    def test_viewport_fit_is_declared_nowhere(self):
        """Considered and declined when the app was made installable.
        `viewport-fit=cover` applies in ordinary Safari as well as the
        installed app, and the element nearest the bottom edge is the ticket
        sheet's confirm button -- the control that spends real money. iOS
        already lays standalone content inside the safe area without it."""
        offenders = [
            p.relative_to(ROOT).as_posix()
            for p in (FRONTEND / "src").rglob("*.ts*")
            if "viewportFit" in _stripped(p)
        ]
        assert not offenders, (
            f"{offenders} turns on viewport-fit=cover. That is a deliberate "
            f"refusal, not an omission -- read the `.sheet-safe-bottom` "
            f"comment in globals.css before changing it."
        )


class TestNothingCachesAPrice:
    def test_there_is_no_service_worker(self):
        """A service worker is a cache that can get stuck, and what it would
        be caching is prices. A broken feed already makes the Board look
        *calm* -- stale numbers render exactly like fresh ones -- and rule 1
        treats a number you cannot date as a bug. Push is Discord's job
        (`backend/notify/discord.py`), which is also why nothing here needs
        one."""
        needles = ("serviceWorker", "workbox", "sw.js")
        offenders = sorted(
            f"{p.relative_to(ROOT).as_posix()}:{needle}"
            for p in list((FRONTEND / "src").rglob("*.ts*"))
            + list((FRONTEND / "public").rglob("*"))
            if p.is_file()
            for needle in needles
            if needle in p.read_text(encoding="utf-8", errors="ignore")
        )
        assert not offenders, offenders


class TestTheMarkIsNotTheColourThatMeansLose:
    """ADR 0081 retired the brand crimson so red could mean *lose*, and missed
    the one file outside `globals.css` with a hex in it. The favicon wore
    `--negative` for three weeks. A home-screen icon renders it at 180px."""

    def test_the_favicon_is_not_crimson(self):
        assert RETIRED_CRIMSON not in _stripped(ICON).lower()

    def test_the_favicon_wears_the_brand_tile(self):
        from_ts = re.search(
            r'BRAND_TILE = "(#[0-9a-fA-F]{6})"', THEME.read_text(encoding="utf-8")
        )
        assert from_ts, "lib/theme.ts no longer exports BRAND_TILE"
        assert from_ts.group(1).lower() in _stripped(ICON).lower()


class TestTheStatusBarMatchesThePage:
    """`theme-color` paints the status bar of an installed app. Three files
    need the literal and none of them can read a CSS custom property, so the
    one that can drift is the one nothing would notice: a status bar a shade
    off the page under it."""

    @pytest.mark.parametrize(
        "key,selector",
        [("light", ":root {"), ("dark", ':root[data-theme="dark"] {')],
    )
    def test_it_equals_the_page_ground(self, key, selector):
        declared = re.search(
            rf'{key}: "(#[0-9a-fA-F]{{6}})"', THEME.read_text(encoding="utf-8")
        )
        assert declared, f"lib/theme.ts no longer declares THEME_COLOR.{key}"
        assert declared.group(1).lower() == _css_background(selector)

    def test_the_manifest_uses_the_same_light_ground(self):
        source = _stripped(MANIFEST)
        assert "background_color: THEME_COLOR.light" in source
        assert "theme_color: THEME_COLOR.light" in source

    def test_a_forced_theme_repaints_it(self):
        """The two `theme-color` metas are keyed on `prefers-color-scheme`,
        which cannot see `localStorage.theme`. Without this the reader who
        forces light on a dark handset gets a black bar over a cream page."""
        assert "applyThemeColor" in _stripped(
            FRONTEND / "src" / "components" / "ThemeToggle.tsx"
        )
        assert 'meta[name="theme-color"]' in _stripped(LAYOUT)
