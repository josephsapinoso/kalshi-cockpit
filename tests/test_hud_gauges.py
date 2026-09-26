"""The HUD's two spend gauges, executed rather than read (#172).

Same lane as `tests/test_window_chip.py`: the two predicates live in a
React-free module (`frontend/src/lib/gauges.ts`) so the real shipped
functions can be run by node, because a substring assertion passes unchanged
on a predicate that picked the wrong cap or divided by the wrong budget.

What this establishes: that `scoutGauge` names whichever of the three
metered caps (tokens, searches, calls) is closest to used up, that
`oddsGauge` measures against the 700-credit daily cap and not the 300-credit
attention slice, and that an unreadable input renders no number rather than
a fabricated 0%. It also establishes that `Nav.tsx` and `ParlayCards.tsx`
import the gauge helper rather than re-deriving a fraction locally. What it
does **not** establish: that the gauges are legible, or that `/api/scout`
and `/api/window` compute the underlying numbers correctly -- those are the
scout-desk and timing tests' claims.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
GAUGES_TS = REPO / "frontend" / "src" / "lib" / "gauges.ts"
NAV_TSX = REPO / "frontend" / "src" / "components" / "Nav.tsx"
PARLAY_CARDS_TSX = REPO / "frontend" / "src" / "components" / "ParlayCards.tsx"

NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)

_DRIVER = """
import { scoutGauge, oddsGauge } from "./gauges.ts";
const [kind, facts] = JSON.parse(process.argv[2]);
const parsed = JSON.parse(facts);
const gauge = kind === "scout" ? scoutGauge(parsed) : oddsGauge(parsed);
console.log(JSON.stringify(gauge));
"""


def gauge_of(kind: str, facts) -> dict:
    driver = GAUGES_TS.parent / "_gauges_driver.mjs"
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps([kind, json.dumps(facts)]),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=str(GAUGES_TS.parent),
        )
    finally:
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def scout_gauge(facts) -> dict:
    return gauge_of("scout", facts)


def odds_gauge(facts) -> dict:
    return gauge_of("odds", facts)


class TestTheScoutGaugeNamesTheCapClosestToUsedUp:
    def test_the_scout_gauge_shows_the_cap_closest_to_used_up(self):
        # Tokens at 40%, calls at 50%, searches at 90% -- searches binds.
        searches_bind = scout_gauge(
            {
                "tokens_today": 400_000,
                "tokens_daily_budget": 1_000_000,
                "searches_today": 90,
                "searches_daily_budget": 100,
                "calls_today": 20,
                "calls_daily_budget": 40,
            }
        )
        assert searches_bind == {"fraction": 0.9, "label": "searches 90%"}

        # Tokens at 90%, calls and searches low -- tokens binds this time,
        # so the function is picking the max each call, not always the same
        # field.
        tokens_bind = scout_gauge(
            {
                "tokens_today": 900_000,
                "tokens_daily_budget": 1_000_000,
                "searches_today": 5,
                "searches_daily_budget": 100,
                "calls_today": 2,
                "calls_daily_budget": 40,
            }
        )
        assert tokens_bind == {"fraction": 0.9, "label": "tokens 90%"}

    def test_the_scout_gauge_matches_the_2026_09_26_reading(self):
        # 1,033,348 / 1,500,000 tokens (69%), 57 / 100 searches (57%),
        # 21 / 40 calls (52.5%) -- the ticket's own motivating numbers.
        # Tokens bind here, at 69% -- the three sit within the ~15% spread
        # the ticket describes, and which one binds depends on the day's
        # actual numbers, not a fixed cap.
        gauge = scout_gauge(
            {
                "tokens_today": 1_033_348,
                "tokens_daily_budget": 1_500_000,
                "searches_today": 57,
                "searches_daily_budget": 100,
                "calls_today": 21,
                "calls_daily_budget": 40,
            }
        )
        assert gauge["label"] == "tokens 69%"


class TestUnreadableInputsShowNoNumber:
    def test_a_null_spend_shows_no_number(self):
        assert scout_gauge(None) == {"fraction": None, "label": "—"}

    def test_a_missing_field_shows_no_number(self):
        gauge = scout_gauge(
            {
                "tokens_today": 400_000,
                "tokens_daily_budget": 1_000_000,
                "searches_today": 10,
                # searches_daily_budget missing entirely
                "calls_today": 5,
                "calls_daily_budget": 40,
            }
        )
        assert gauge == {"fraction": None, "label": "—"}

    def test_a_non_finite_field_shows_no_number(self):
        gauge = scout_gauge(
            {
                "tokens_today": None,
                "tokens_daily_budget": 1_000_000,
                "searches_today": 10,
                "searches_daily_budget": 100,
                "calls_today": 5,
                "calls_daily_budget": 40,
            }
        )
        assert gauge == {"fraction": None, "label": "—"}

    def test_a_zero_budget_shows_no_number_not_a_full_bar(self):
        gauge = scout_gauge(
            {
                "tokens_today": 0,
                "tokens_daily_budget": 0,
                "searches_today": 10,
                "searches_daily_budget": 100,
                "calls_today": 5,
                "calls_daily_budget": 40,
            }
        )
        assert gauge == {"fraction": None, "label": "—"}

    def test_an_unreadable_odds_window_shows_no_number(self):
        assert odds_gauge(None) == {"fraction": None, "label": "—"}
        assert odds_gauge({"spent_today": 40, "daily_budget": 0}) == {
            "fraction": None,
            "label": "—",
        }


class TestTheOddsGaugeMeasuresAgainstTheDailyCap:
    def test_the_odds_gauge_measures_against_the_daily_cap_not_the_attention_slice(
        self,
    ):
        # 300 spent of the 300-credit attention slice would be 100% if the
        # gauge mistakenly measured against that slice; against the real
        # 700-credit daily cap it is well under half.
        gauge = odds_gauge(
            {
                "spent_today": 300,
                "daily_budget": 700,
                # An attention-slice field, if the payload carried one,
                # must never be read by this function -- it is not even in
                # `OddsSpendFacts`, so passing it here is inert on purpose.
                "attention_daily_credits": 300,
            }
        )
        assert gauge["fraction"] == pytest.approx(300 / 700)
        assert gauge["label"] == "odds 43%"

    def test_a_fully_spent_day_reads_100_percent_against_the_700_cap(self):
        gauge = odds_gauge({"spent_today": 700, "daily_budget": 700})
        assert gauge == {"fraction": 1.0, "label": "odds 100%"}


class TestTheWiring:
    def test_nav_imports_the_gauge_helper_rather_than_re_deriving_it(self):
        nav = NAV_TSX.read_text(encoding="utf-8")
        assert "from \"@/lib/gauges\"" in nav or "from '@/lib/gauges'" in nav
        assert "scoutGauge" in nav and "oddsGauge" in nav
        # A local re-derivation would divide `_today` by `_daily_budget`
        # inline instead of calling into the module.
        assert "tokens_today /" not in nav
        assert "spent_today /" not in nav

    def test_parlay_cards_imports_the_gauge_helper_rather_than_re_deriving_it(self):
        parlay_cards = PARLAY_CARDS_TSX.read_text(encoding="utf-8")
        assert (
            "from \"@/lib/gauges\"" in parlay_cards
            or "from '@/lib/gauges'" in parlay_cards
        )
        assert "scoutGauge" in parlay_cards
        assert "tokens_today /" not in parlay_cards
        assert "searches_today /" not in parlay_cards
