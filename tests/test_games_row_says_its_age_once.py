"""A stale Games row says its age once (#353, second half).

The red age chip and the TrustNote failure list both printed
"Kalshi quote 357s old, limit 30s". `TrustNote` takes an opt-in
`hideAgeChecks` that drops the `consensus_fresh` / `quote_fresh` details from
the printed failure list; only the Games row (`slate/page.tsx`) passes it.

Renders the real `TrustNote.tsx` (compiled with the repo's `tsc`, rendered with
`react-dom/server`, same approach as `test_parlay_cost_line_states_the_price.py`).

Establishes: with the prop, age details are absent and other failures remain;
without it (every other caller) the age details print; an age-only failure
renders no failure line and never the all-passed sentence. Does not establish
that the Games row's chip itself renders (read, not rendered).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRONTEND = REPO / "frontend"
SRC = FRONTEND / "src"
TRUST_NOTE = SRC / "components" / "TrustNote.tsx"
SLATE = SRC / "app" / "slate" / "page.tsx"

NODE = shutil.which("node")
NPX = shutil.which("npx") or shutil.which("npx.cmd")

needs_node = pytest.mark.skipif(
    NODE is None or NPX is None or not (FRONTEND / "node_modules").is_dir(),
    reason="node, npx and an installed frontend are required",
)

AGE_Q = {"name": "quote_fresh", "state": "fail",
         "detail": "Kalshi quote 357s old, limit 30s"}
AGE_C = {"name": "consensus_fresh", "state": "fail",
         "detail": "sportsbook consensus 400s old, limit 120s"}
BOOKS = {"name": "books", "state": "fail", "detail": "2 book(s), need 3"}
OK = {"name": "width", "state": "pass", "detail": "ok"}


def _trust(*checks):
    return {"passed": sum(c["state"] == "pass" for c in checks),
            "known": len(checks), "total": len(checks), "checks": list(checks)}


_DRIVER = """
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import TrustNote from "./TrustNote.js";
const input = JSON.parse(process.argv[2]);
console.log(JSON.stringify({ html: renderToStaticMarkup(
  createElement(TrustNote, input)) }));
"""

_HOOK = """
import {{ registerHooks }} from "node:module";
const MAP = {map};
registerHooks({{ resolve(s, c, next) {{
  if (Object.hasOwn(MAP, s)) return {{ url: MAP[s], shortCircuit: true }};
  try {{ return next(s, c); }} catch (e) {{
    if (e && e.code === "ERR_MODULE_NOT_FOUND" && s.startsWith("./") && !/\\.[cm]?jsx?$/.test(s))
      return next(s + ".js", c);
    throw e;
  }}
}} }});
"""


def _module_map() -> dict[str, str]:
    script = (
        "const {createRequire}=require('module');"
        f"const r=createRequire({json.dumps(str(FRONTEND / 'package.json'))});"
        "const {pathToFileURL}=require('url');"
        "console.log(JSON.stringify({"
        "'react': pathToFileURL(r.resolve('react')).href,"
        "'react-dom/server': pathToFileURL(r.resolve('react-dom/server')).href,"
        "'react/jsx-runtime': pathToFileURL(r.resolve('react/jsx-runtime')).href"
        "}));"
    )
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def _build(work: Path, source: str) -> Path:
    work.mkdir(parents=True)
    (work / "TrustNote.tsx").write_text(
        source.replace('"@/lib/api"', '"./api"'), encoding="utf-8")
    (work / "api.ts").write_text(
        "export type TrustScore = {passed:number;known:number;total:number;"
        "checks:{name:string;state:'pass'|'fail'|'unknown';detail:string}[]};\n",
        encoding="utf-8")
    out = work / "out"
    r = subprocess.run(
        [NPX, "tsc", str(work / "TrustNote.tsx"), str(work / "api.ts"),
         "--jsx", "react-jsx", "--module", "esnext", "--target", "es2022",
         "--moduleResolution", "bundler", "--skipLibCheck", "--outDir", str(out)],
        capture_output=True, text=True, timeout=300, cwd=str(FRONTEND))
    assert (out / "TrustNote.js").is_file(), f"{r.stdout}\n{r.stderr}"
    (out / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    (out / "hook.mjs").write_text(
        _HOOK.format(map=json.dumps(_module_map())), encoding="utf-8")
    return out


def _render(out: Path, trust, **props) -> str:
    r = subprocess.run(
        [NODE, "--import", (out / "hook.mjs").resolve().as_uri(),
         str(out / "render.mjs"), json.dumps({"trust": trust, **props})],
        capture_output=True, text=True, timeout=120, cwd=str(FRONTEND))
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    return re.sub(r"<[^>]+>", "", json.loads(r.stdout.strip())["html"])


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    return _build(tmp_path_factory.mktemp("trustnote") / "rt",
                  TRUST_NOTE.read_text(encoding="utf-8"))


@needs_node
class TestGamesRowSaysItsAgeOnce:
    def test_stale_games_row_omits_the_age_detail(self, built):
        text = _render(built, _trust(AGE_Q, AGE_C, BOOKS, OK), hideAgeChecks=True)
        assert "old, limit" not in text
        assert "357s" not in text
        assert "2 book(s), need 3." in text

    def test_other_callers_still_print_the_age_checks(self, built):
        # Positive control: the default (no prop) is unchanged.
        text = _render(built, _trust(AGE_Q, AGE_C, BOOKS, OK))
        # TrustNote prints ages in minutes since town hall #411.
        assert "Kalshi quote 6 min old, limit 30s" in text
        assert "sportsbook consensus 7 min old, limit 120s" in text

    def test_age_only_failure_renders_no_empty_or_misleading_line(self, built):
        text = _render(built, _trust(AGE_Q, OK), hideAgeChecks=True)
        assert "evidence 1/2 checks" in text
        assert text.strip().endswith("checks")  # nothing after the score
        assert "Every check" not in text

    def test_age_only_failure_without_the_prop_still_prints(self, built):
        assert "6 min old" in _render(built, _trust(AGE_Q, OK))

    def test_clean_row_still_says_everything_passed(self, built):
        assert "Every check" in _render(built, _trust(OK), hideAgeChecks=True)


class TestOnlyTheGamesRowPassesIt:
    def test_slate_passes_it(self):
        assert re.search(r"<TrustNote[^>]*hideAgeChecks", SLATE.read_text(encoding="utf-8"))

    def test_no_other_caller_passes_it(self):
        for p in SRC.rglob("*.tsx"):
            if p in (SLATE, TRUST_NOTE):
                continue
            assert "hideAgeChecks" not in p.read_text(encoding="utf-8"), p
