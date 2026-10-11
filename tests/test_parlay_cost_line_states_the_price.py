"""The cost line states what the price means before Joe pays it (#354).

Joe's 2026-10-09 lesson (ADR 0195, sharp-bettor review): a $5 six-leg
cross-sport ticket at 5.5c was an 18%-of-bankroll bet he never read as "this
price says 5.5%, across three sports." `ParlayCostLine` (in
`AskTheMarket.tsx`) now states four facts beside the existing #328 clauses:
the price as an implied chance, the leg count, a flag when the legs span
more than one sport, and the server's own fair joint -- never recomputed
here, because a client-side product of leg fair chances is exactly the
same-game combined chance ADR 0189 refuses to compute.

**Why this renders the real component instead of reading its source.** The
other tests in `test_parlay_cost_line.py` read `AskTheMarket.tsx`'s source
with regexes, which proves the arithmetic exists but not that a real input
produces the right sentence -- a swapped operand or an off-by-one in the
JSX would still contain the right substrings elsewhere in the file. This
compiles the real `ParlayCostLine` (plus the real `parlayCost.ts`, `Term.tsx`
and `glossary.ts` it depends on) with the repo's own `tsc` and renders it
with `react-dom/server`, the same approach
`tests/test_open_positions_renders_every_refusal.py` uses and explains.

What this establishes: that `ParlayCostLine`, given a real captured RFQ
quote's price and the real leagues of that quote's own legs, states the
price as a chance and counts the sports correctly; that a synthetic
6-leg/3-sport/5.5c input (Joe's own recorded case, CLAUDE.md) renders all
four new facts and no combined-chance, ranking or verdict word; and that
each fact is independently absent when its own input is absent.

What this does not establish: that the four facts are wired correctly all
the way from `/api/parlays/rfq`, `/api/parlays/lookup` or
`/api/parlays/check` through `ParlayCards.tsx` / `PriceOnKalshi.tsx` /
`CheckAParlay.tsx` -- those screens are still read, not rendered, in
`test_parlay_cost_line.py`. Nor that the server's own fair-joint figure is
correct (ADR 0036/0037 and the signal-test record own that).
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
ASK_THE_MARKET = SRC / "components" / "AskTheMarket.tsx"
TERM = SRC / "components" / "Term.tsx"
PARLAY_COST = SRC / "lib" / "parlayCost.ts"
GLOSSARY = SRC / "lib" / "glossary.ts"
RFQ_FIXTURE = REPO / "tests" / "fixtures" / "combo_rfq_quotes.json"

NODE = shutil.which("node")
NPX = shutil.which("npx") or shutil.which("npx.cmd")

pytestmark = pytest.mark.skipif(
    NODE is None or NPX is None or not (FRONTEND / "node_modules").is_dir(),
    reason=(
        "node, npx and an installed frontend are required. Skipped rather "
        "than xfailed: the guard is real where they exist (CI and both dev "
        "machines) and a missing runtime is an environment fact."
    ),
)

# Permissive stand-ins for AskTheMarket.tsx's heavier dependencies. None of
# them is the code under test, and `ParlayCostLine` calls none of them --
# but `tsc` type-checks the whole file, including the default export and
# `TakeIt`, which do. `any` throughout keeps this file honest about that:
# it is scaffolding to make the real file compile, not a second copy of the
# real types.
_API_STUB = """
export function acceptComboQuote(..._args) { return Promise.resolve({}); }
export function askMarketToPrice(..._args) { return Promise.resolve({}); }
export function formatAge(..._args) { return ""; }
"""
_API_STUB_TYPES = """
export type ComboRfqAcceptResult = any;
export type ComboRfqResult = any;
"""
_SHEET_STUB = "export function useReportBusy(_busy) {}\n"
_UI_STUB = """
export function Button(props) {
  const { tone, ...rest } = props;
  return <button {...rest} />;
}
export function Stat({ label, value, sub }) {
  return <div><p>{label}</p><p>{value}</p>{sub ? <p>{sub}</p> : null}</div>;
}
"""
_HELD_CONFLICTS_STUB = "export default function HeldConflictsNote(_props) { return null; }\n"

_DRIVER = """
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ParlayCostLine } from "./AskTheMarket.js";
import { ParlayLegsContext } from "./lib/parlayCost.js";

const input = JSON.parse(process.argv[2]);
const element = createElement(
  ParlayLegsContext.Provider,
  { value: input.legsInfo },
  createElement(ParlayCostLine, {
    priceTenths: input.priceTenths,
    coefficient: input.coefficient ?? null,
    lead: input.lead,
  }),
);
const html = renderToStaticMarkup(element);
console.log(JSON.stringify({ html }));
"""

# Node's ESM loader resolves bare specifiers (`react`, `react/jsx-runtime`)
# from the importing FILE, not `cwd` -- unreachable from a temp out dir
# however the subprocess is launched. This resolves exactly those two
# against the repo's own `frontend/` install and leaves everything else to
# fail exactly as node would, same as `test_open_positions_renders_every_refusal.py`.
_HOOK = """
import {{ registerHooks }} from "node:module";
const MAP = {map};
registerHooks({{
  resolve(specifier, context, nextResolve) {{
    if (Object.hasOwn(MAP, specifier)) {{
      return {{ url: MAP[specifier], shortCircuit: true }};
    }}
    try {{
      return nextResolve(specifier, context);
    }} catch (e) {{
      const relative = specifier.startsWith("./") || specifier.startsWith("../");
      const bare = !/\\.[cm]?jsx?$/.test(specifier);
      if (e && e.code === "ERR_MODULE_NOT_FOUND" && relative && bare) {{
        return nextResolve(specifier + ".js", context);
      }}
      throw e;
    }}
  }},
}});
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
    out = subprocess.run(
        [NODE, "-e", script], capture_output=True, text=True, timeout=60
    )
    assert out.returncode == 0, f"could not resolve react: {out.stderr}"
    return json.loads(out.stdout.strip())


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    """`ParlayCostLine`, compiled once, with its real dependencies and
    permissive stubs for the ones this test never calls."""
    work = tmp_path_factory.mktemp("cost_line") / "rt"
    (work / "lib").mkdir(parents=True)

    ask = ASK_THE_MARKET.read_text(encoding="utf-8")
    ask = (
        ask.replace('"@/lib/api"', '"./lib/api"')
        .replace('"@/components/Term"', '"./Term"')
        .replace('"@/components/Sheet"', '"./Sheet"')
        .replace('"@/components/ui"', '"./ui"')
        .replace('"@/components/HeldConflictsNote"', '"./HeldConflictsNote"')
        .replace('"@/lib/parlayCost"', '"./lib/parlayCost"')
    )
    (work / "AskTheMarket.tsx").write_text(ask, encoding="utf-8")

    term = TERM.read_text(encoding="utf-8").replace(
        '"@/lib/glossary"', '"./lib/glossary"'
    )
    (work / "Term.tsx").write_text(term, encoding="utf-8")
    (work / "lib" / "glossary.ts").write_text(
        GLOSSARY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (work / "lib" / "parlayCost.ts").write_text(
        PARLAY_COST.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (work / "lib" / "api.ts").write_text(
        _API_STUB + _API_STUB_TYPES, encoding="utf-8"
    )
    (work / "Sheet.tsx").write_text(_SHEET_STUB, encoding="utf-8")
    (work / "ui.tsx").write_text(_UI_STUB, encoding="utf-8")
    (work / "HeldConflictsNote.tsx").write_text(
        _HELD_CONFLICTS_STUB, encoding="utf-8"
    )

    out = work / "out"
    compile_result = subprocess.run(
        [
            NPX, "tsc",
            str(work / "AskTheMarket.tsx"),
            str(work / "Term.tsx"),
            str(work / "Sheet.tsx"),
            str(work / "ui.tsx"),
            str(work / "HeldConflictsNote.tsx"),
            str(work / "lib" / "api.ts"),
            str(work / "lib" / "parlayCost.ts"),
            str(work / "lib" / "glossary.ts"),
            "--jsx", "react-jsx",
            "--module", "esnext",
            "--target", "es2022",
            "--moduleResolution", "bundler",
            "--skipLibCheck",
            "--outDir", str(out),
        ],
        capture_output=True, text=True, timeout=300, cwd=str(FRONTEND),
    )
    assert (out / "AskTheMarket.js").is_file(), (
        "tsc emitted no AskTheMarket.js:\n"
        f"{compile_result.stdout}\n{compile_result.stderr}"
    )
    (out / "render.mjs").write_text(_DRIVER, encoding="utf-8")
    (out / "hook.mjs").write_text(
        _HOOK.format(map=json.dumps(_module_map())), encoding="utf-8"
    )
    return out


def render(legs_info: dict | None, price_tenths, out: Path, **extra) -> str:
    """Render `<ParlayCostLine>` under a `ParlayLegsContext.Provider` set to
    `legs_info`; return its text content."""
    payload = {"legsInfo": legs_info, "priceTenths": price_tenths, **extra}
    driver = out / "render.mjs"
    hook = out / "hook.mjs"
    result = subprocess.run(
        [
            NODE,
            "--import", hook.resolve().as_uri(),
            str(driver),
            json.dumps(payload),
        ],
        capture_output=True, text=True, timeout=120, cwd=str(FRONTEND),
    )
    assert result.returncode == 0, (
        f"node failed rendering:\n{result.stdout}\n{result.stderr}"
    )
    html = json.loads(result.stdout.strip())["html"]
    # `<Term k="leg">legs</Term>` wraps "legs" in a tappable span, so "6
    # legs" only appears as a text substring once tags are stripped -- the
    # same reason `test_open_positions_renders_every_refusal.py` strips them.
    return re.sub(r"<[^>]+>", "", html)


# Joe's own recorded case (CLAUDE.md, ADR 0195): a six-leg cross-sport ticket
# at 5.5c, across NCAA football, NHL and WNBA.
SIX_LEG_CROSS_SPORT = {
    "legCount": 6,
    "legAsksTenths": None,
    "legLeagues": [
        "americanfootball_ncaaf",
        "americanfootball_ncaaf",
        "icehockey_nhl",
        "icehockey_nhl",
        "basketball_wnba",
        "basketball_wnba",
    ],
    "fairJointPercentDisplay": "4.1%",
}


class TestTheFourFactsOnJoesOwnCase:
    """6 legs, 3 sports, 5.5c -- the exact ticket this fixed (#354)."""

    def test_the_price_the_leg_count_and_the_sport_count_all_render(self, built):
        html = render(SIX_LEG_CROSS_SPORT, 55, built)
        assert "says 5.5%" in html
        assert "6 legs" in html
        assert "3 sports" in html

    def test_the_servers_own_fair_joint_renders_beside_the_quote(self, built):
        html = render(SIX_LEG_CROSS_SPORT, 55, built)
        assert "4.1%" in html

    def test_no_combined_chance_ranking_or_verdict_word_appears(self, built):
        html = render(SIX_LEG_CROSS_SPORT, 55, built).lower()
        for word in (
            "combined",
            "verdict",
            "rank",
            "cheap",
            "good",
            "edge",
            "best",
            "better",
            "worth",
            "predict",
        ):
            assert word not in html, word


class TestOnARealCapturedQuote:
    """`tests/fixtures/combo_rfq_quotes.json` (#354's own `never hand-built`
    line): a real maker quote on a real 3-leg NCAAF/WNBA combination,
    captured 2026-09-17. The price below is read from it, not invented --
    `yes_ask_tenths` is the server's own complement of the maker's NO bid
    (`ComboRfqQuote.yes_ask_tenths`'s own rule), and the two WNBA legs make
    this a real (if 2-sport, not 3-sport) cross-sport example."""

    def test_the_implied_chance_and_sport_count_come_from_the_real_quote(self, built):
        fixture = json.loads(RFQ_FIXTURE.read_text(encoding="utf-8"))
        quotes = fixture["quotes"]
        legs = fixture["params"]["rfq_request_body"]["mve_selected_legs"]
        assert len(legs) == 3, "fixture's leg count moved -- recompute below"
        # The cheapest YES ask is the quote with the larger NO bid, since
        # yes_ask = 1 - no_bid (ComboRfqQuote's own derivation).
        best_no_bid = max(float(q["no_bid_dollars"]) for q in quotes)
        yes_ask_tenths = round((1 - best_no_bid) * 1000)
        assert yes_ask_tenths == 593
        legs_info = {
            "legCount": len(legs),
            "legAsksTenths": None,
            # KXNCAAFGAME -> americanfootball_ncaaf, KXWNBAGAME ->
            # basketball_wnba (backend/kalshi/discovery.py's own map).
            "legLeagues": [
                "americanfootball_ncaaf",
                "basketball_wnba",
                "basketball_wnba",
            ],
            "fairJointPercentDisplay": None,
        }
        html = render(legs_info, yes_ask_tenths, built)
        assert "says 59.3%" in html
        assert "3 legs" in html
        assert "2 sports" in html


class TestEachFactIsIndependentlyAbsent:
    def test_no_sport_flag_on_a_single_sport_card(self, built):
        legs_info = dict(SIX_LEG_CROSS_SPORT, legLeagues=["baseball_mlb"] * 6)
        html = render(legs_info, 55, built)
        assert "sports" not in html

    def test_no_sport_flag_with_no_league_data(self, built):
        legs_info = dict(SIX_LEG_CROSS_SPORT, legLeagues=None)
        html = render(legs_info, 55, built)
        assert "sports" not in html

    def test_no_fair_joint_clause_when_the_server_served_none(self, built):
        legs_info = dict(SIX_LEG_CROSS_SPORT, fairJointPercentDisplay=None)
        html = render(legs_info, 55, built)
        assert "multiply" not in html

    def test_no_implied_chance_on_a_null_price(self, built):
        html = render(SIX_LEG_CROSS_SPORT, None, built)
        assert html == ""


class TestAFreshPriceNeverCarriesAnOlderJoint:
    """#354 review: `PriceOnKalshi` builds the context from the FRESH lookup.
    A null fresh joint (same-game set, unknown leg) must give no "multiply"
    clause -- not the ladder card's older joint beside a fresh price, which
    puts two observation times on one line."""

    def test_a_null_fresh_joint_renders_no_clause(self, built):
        legs_info = dict(SIX_LEG_CROSS_SPORT, fairJointPercentDisplay=None)
        html = render(legs_info, 55, built)
        assert "multiply" not in html
        assert "4.1%" not in html

    def test_price_on_kalshi_does_not_fall_back_to_the_outer_joint(self):
        src = (SRC / "components" / "PriceOnKalshi.tsx").read_text(
            encoding="utf-8"
        )
        m = re.search(r"fairJointPercentDisplay:([^;]*?),\s*\n\s*\};", src, re.S)
        assert m, "legsInfo no longer ends with fairJointPercentDisplay"
        expr = m.group(1)
        assert "conservative_percent_display" in expr
        assert "outer" not in expr, (
            "the fresh lookup's joint must not fall back to the ladder card's"
        )

    def test_the_books_clause_wraps_books_in_a_glossary_term(self):
        src = ASK_THE_MARKET.read_text(encoding="utf-8")
        assert '<Term k="books">books</Term> multiply' in src
        gloss = GLOSSARY.read_text(encoding="utf-8")
        assert re.search(r"^\s*books:\s*\{", gloss, re.M)
