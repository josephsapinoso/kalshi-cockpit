"""Coloured border utilities must render their own colour (#231).

`* { border-color: var(--border) }` in globals.css was unlayered. Under
Tailwind v4 an unlayered rule beats anything in `@layer utilities`
regardless of specificity, so `border-negative` and friends computed to
--border. This test compiles the real globals.css with the repo's own
PostCSS/Tailwind, loads it in headless Chromium and reads computed styles.

Does not establish: pixel appearance, or any page other than a probe. It skips
when node_modules or Chromium is missing, so a skip is not a pass.
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
CHROME = Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"

COMPILE = """
import postcss from 'postcss';
import tw from '@tailwindcss/postcss';
import fs from 'node:fs';
const f = 'src/app/globals.css';
const r = await postcss([tw()]).process(fs.readFileSync(f, 'utf8')
  + '\\n@source inline("border border-negative border-positive border-accent border-warn text-warn rounded-2xl");', { from: f });
process.stdout.write(r.css);
"""

PROBE = """<!doctype html><html data-theme="{theme}"><head><style>{css}</style></head>
<body>
<div id="neg" class="border border-negative">x</div>
<div id="pos" class="border border-positive">x</div>
<div id="acc" class="border border-accent">x</div>
<div id="plain" class="border">x</div>
<div id="hud" class="hud rounded-2xl border">x</div>
<div id="warn" class="border border-warn text-warn">x</div>
<div id="t-acc2" style="color:var(--accent-2)">x</div>
<div id="t-neg" style="color:var(--negative)">x</div>
<div id="t-pos" style="color:var(--positive)">x</div>
<div id="t-acc" style="color:var(--accent)">x</div>
<div id="t-bor" style="color:var(--border)">x</div>
<pre id="out"></pre>
<script>
const c = (id, p) => getComputedStyle(document.getElementById(id))[p];
document.getElementById('out').textContent = JSON.stringify({{
  neg: c('neg','borderTopColor'), pos: c('pos','borderTopColor'),
  acc: c('acc','borderTopColor'), plain: c('plain','borderTopColor'),
  negT: c('t-neg','color'), posT: c('t-pos','color'),
  accT: c('t-acc','color'), borT: c('t-bor','color'),
  hud: c('hud','borderTopLeftRadius'), warn: c('warn','borderTopColor'),
  warnT: c('warn','color'), acc2: c('t-acc2','color'),
}});
</script></body></html>"""


def _chrome():
    hits = sorted(CHROME.glob("chromium-*/chrome-win64/chrome.exe")) if CHROME.exists() else []
    return hits[-1] if hits else None


@pytest.fixture(scope="module")
def computed(tmp_path_factory):
    return _render(tmp_path_factory, "dark")


@pytest.fixture(scope="module")
def computed_light(tmp_path_factory):
    return _render(tmp_path_factory, "light")


def _render(tmp_path_factory, theme):
    if not (FRONTEND / "node_modules").exists():
        pytest.skip("frontend/node_modules missing")
    chrome = _chrome()
    if chrome is None:
        pytest.skip("no Playwright Chromium installed")
    css = subprocess.run(
        [shutil.which("node"), "--input-type=module", "-e", COMPILE],
        cwd=FRONTEND, capture_output=True, text=True, check=True,
    ).stdout
    page = tmp_path_factory.mktemp("border231" + theme) / "probe.html"
    page.write_text(PROBE.format(css=css, theme=theme), encoding="utf-8")
    dom = subprocess.run(
        [str(chrome), "--headless", "--disable-gpu", "--dump-dom", page.as_uri()],
        capture_output=True, text=True, timeout=60,
    ).stdout
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)
    assert m, dom[:500]
    return json.loads(m.group(1).replace("&quot;", '"'))


class TestBorderColourUtilities:
    def test_border_negative_computes_to_negative_not_border(self, computed):
        assert computed["neg"] == computed["negT"]
        assert computed["neg"] != computed["borT"]

    def test_the_other_coloured_utilities_render_their_own_colour(self, computed):
        assert computed["pos"] == computed["posT"]
        assert computed["acc"] == computed["accT"]

    def test_a_bare_border_still_takes_the_themed_colour(self, computed):
        assert computed["plain"] == computed["borT"]


class TestHudRadiusAndWarnToken:
    def test_a_hud_panel_computes_2px_even_with_rounded_2xl(self, computed):
        assert computed["hud"] == "2px"

    def test_border_warn_is_the_ochre_in_dark(self, computed):
        assert computed["warn"] == computed["acc2"]
        assert computed["warn"] not in ("rgba(0, 0, 0, 0)", computed["borT"])
        assert computed["warnT"] == computed["acc2"]

    def test_border_warn_is_the_ochre_in_light(self, computed_light):
        assert computed_light["warn"] == computed_light["acc2"]
        assert computed_light["warn"] not in ("rgba(0, 0, 0, 0)", computed_light["borT"])
        assert computed_light["warnT"] == computed_light["acc2"]
