"""`fly.live.toml`'s stated per-call credit cost must equal what its own
`[env]` implies.

The cost of one `/odds` call moved twice in two days -- ADR 0152 added
`totals` and took it from 4 to 6, ADR 0155 named ten bookmakers in place of
regions and took it to 3 -- and the deploy file's comments did not follow
either time. The file ended up stating 2, 4 and 6 as the *current* cost in
different paragraphs, which is how someone asking "is there headroom for
another market key" gets a number that was never true.

So the arithmetic that describes TODAY is pinned here, derived from the
deployed `ODDS_MARKETS` and `ODDS_BOOKMAKERS` through `sweep_cost` itself.
Change either variable and this file goes red until the comments are
re-derived.

**What this does NOT establish:**

- It does not check the historical figures in that file. Those are meter
  readings at 2, 4, 6 and 20 credits a call, and re-deriving them at today's
  rate would falsify a measurement -- they are marked HISTORICAL in prose and
  are deliberately outside what any assertion here reads.
- It does not prove the vendor bills what `sweep_cost` computes. That is
  ADR 0155's measurement against `x-requests-last`, and
  `tests/test_named_bookmakers_billing.py` pins the formula.
- It reads four specific derivations, not every sentence. A new paragraph
  stating a stale cost in prose this file does not parse would still pass.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from backend.odds.budget import sweep_cost

_LIVE = Path(__file__).resolve().parents[1] / "fly.live.toml"


def _text() -> str:
    return _LIVE.read_text(encoding="utf-8")


def _env() -> dict[str, str]:
    return tomllib.loads(_text())["env"]


def _split(raw: str) -> list[str]:
    return [p.strip() for p in raw.split(",") if p.strip()]


@pytest.fixture(scope="module")
def deployed() -> dict[str, object]:
    env = _env()
    markets = _split(env["ODDS_MARKETS"])
    regions = _split(env.get("ODDS_REGIONS", ""))
    books = _split(env.get("ODDS_BOOKMAKERS", ""))
    return {
        "markets": markets,
        "regions": regions,
        "books": books,
        "cost": sweep_cost(markets, regions, books),
    }


class TestTheDeployFileStatesTheCostItsOwnEnvImplies:
    """Four derivations in `fly.live.toml` that describe the config as it is
    deployed today. Each is re-computed here rather than compared to a
    literal, so the test cannot go stale in the same way the comments did."""

    def test_the_today_line_names_the_markets_the_books_and_the_cost(
        self, deployed
    ):
        """The canonical line at the head of the ODDS_DAILY_CREDIT_BUDGET
        block. It is the one a reader is meant to quote, so all three of its
        numbers are pinned, not just the total."""
        m = re.search(
            r"TODAY\s+(\d+) markets x ceil\((\d+) books / 10\) = "
            r"\*\*(\d+) credits a call\*\*",
            _text(),
        )
        assert m, (
            "fly.live.toml no longer carries the canonical TODAY per-call "
            "derivation; it is the line every other figure is derived from"
        )
        assert int(m.group(1)) == len(deployed["markets"])
        assert int(m.group(2)) == len(deployed["books"])
        assert int(m.group(3)) == deployed["cost"]

    def test_the_idle_floor_row_is_the_product_it_prints(self, deployed):
        """`24h x 4 sports x N credits`, and the `~288/day` beside it must be
        that product. A row whose stated arithmetic and stated total disagree
        is worse than either alone."""
        m = re.search(
            r"idle floor, 4 sports\s+~([\d,]+)/day\s+"
            r"24h x 4 sports x (\d+) credits",
            _text(),
        )
        assert m, "the knowable-figures table lost its idle-floor row"
        per_call = int(m.group(2))
        total = int(m.group(1).replace(",", ""))
        assert per_call == deployed["cost"]
        assert total == 24 * 4 * per_call

    def test_the_kickoff_row_charges_the_same_call(self, deployed):
        """The largest of the three terms, gated by `credits_left` alone. It
        was the row that stayed at 4 while the call cost 6."""
        m = re.search(
            r"kickoff windows\s+UNCAPPED\s+clusters x 7 calls x (\d+) credits",
            _text(),
        )
        assert m, "the knowable-figures table lost its kickoff row"
        assert int(m.group(1)) == deployed["cost"]

    def test_the_open_tab_worst_case_is_recomputed_at_the_current_call(
        self, deployed
    ):
        """The reason ODDS_ATTENTION_DAILY_CREDITS exists. 24h at the 10-minute
        cadence is 6 calls an hour per sport; the figure quoted for two sports
        must be that, and the four-sport figure must be twice it."""
        m = re.search(
            r"open and visible for 24h is \*\*([\d,]+) credits/day at two "
            r"sports and ([\d,]+) at\s+#?\s*four\*\*",
            _text(),
        )
        assert m, "the attention cap's worst-case sentence changed shape"
        two = int(m.group(1).replace(",", ""))
        four = int(m.group(2).replace(",", ""))
        assert two == 24 * 6 * deployed["cost"] * 2
        assert four == two * 2

    def test_named_books_are_what_make_the_call_cheap(self, deployed):
        """The guard behind the other four: the cost above is only 3 because
        `bookmakers` replaces `regions`. If the books were ever dropped, the
        same three markets would bill `3 x len(regions)` and every derivation
        in that file would be wrong in the expensive direction."""
        assert deployed["books"], "ODDS_BOOKMAKERS is what halves the bill"
        assert deployed["cost"] < sweep_cost(
            deployed["markets"], deployed["regions"], ()
        )
