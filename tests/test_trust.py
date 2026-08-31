"""The sweet spot scores trust, and never edge.

Joe asked for a score that decides yes or no on a bet and chose, from three
options on 2026-08-31, **trust rather than edge**. This file guards the
properties that make that honest.

WHAT THIS ESTABLISHES
---------------------
That every threshold arrives from its existing owner rather than a literal;
that `unknown` is never folded into `pass`; that every failure is named rather
than one; and that no edge quantity reaches the module at all.

WHAT IT DOES NOT
----------------
That a high-trust row wins. Nothing here is scored against an outcome, and
doing so would need its own registration. The score is evidence quality.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.core import trust                                    # noqa: E402
from backend.core.ladder import AGREEMENT_SPREAD_POINTS           # noqa: E402

#: A row where every check passes, so each test can spoil exactly one thing.
GOOD = dict(
    max_odds_age_s=900,
    max_kalshi_quote_age_s=30,
    min_book_count=2,
    max_market_width=0.06,
    min_depth_contracts=10.0,
    odds_age_ms=120_000,
    quote_age_ms=20_000,
    book_count=9,
    market_width=0.012,
    method_spread_points=1.2,
    depth_at_ask=25.0,
    skeptic="checked",
    suppressed_reason=None,
    scout="filed_nothing",
    scout_flags=[],
)


def score(**over):
    return trust.score_trust(**{**GOOD, **over})


class TestTheScoreCountsWhatItCanSee:
    def test_a_clean_row_passes_every_check(self):
        s = score()
        assert s.passed == s.total == s.known
        assert s.failures == ()
        assert s.unknowns == ()

    def test_the_three_counts_are_reported_separately(self):
        """A caller may not reconstruct one from the others by assuming.

        `passed`, `known` and `total` are three different facts, and the gap
        between the last two is the number of things nobody looked at.
        """
        s = score(skeptic="absent", scout="absent")
        assert s.total == 8
        assert s.unknown == 2
        assert s.known == 6
        assert s.passed == 6


class TestUnknownIsNeverAPass:
    """The flattering direction, and the one most likely to be broken.

    Folding `unknown` into `pass` makes the LEAST-examined row score highest --
    the same failure `suppression.py` records for `market_width = 0.0`: *"the
    least-evidenced consensus in the system cleared this check most easily."*
    """

    @pytest.mark.parametrize(
        "over, name",
        [
            ({"skeptic": "not_on_this_path"}, "skeptic"),
            ({"skeptic": "absent"}, "skeptic"),
            ({"scout": "absent"}, "scout"),
            ({"scout": "refused"}, "scout"),
            ({"scout": "failed"}, "scout"),
            ({"scout": "briefing"}, "scout"),
            ({"odds_age_ms": None}, "consensus_fresh"),
            ({"quote_age_ms": None}, "quote_fresh"),
            ({"book_count": None}, "books"),
            ({"depth_at_ask": None}, "depth"),
            ({"method_spread_points": None}, "methods_agree"),
        ],
    )
    def test_an_absence_scores_unknown_not_pass(self, over, name):
        """Mutation observed red: score any of these as `pass`."""
        s = score(**over)
        check = next(c for c in s.checks if c.name == name)
        assert check.state == "unknown", (
            f"{name} scored {check.state} on {over}; an absence of a look is "
            f"not evidence of quality"
        )
        assert s.passed == s.total - 1

    def test_a_refused_scout_is_not_a_quiet_game(self):
        """A ceiling turning the desk away and a quiet game are opposite facts.

        Only one of them is information, and `filed_nothing` is the one that
        earns a pass.
        """
        refused = next(
            c for c in score(scout="refused").checks if c.name == "scout"
        )
        quiet = next(
            c for c in score(scout="filed_nothing").checks if c.name == "scout"
        )
        assert refused.state == "unknown"
        assert quiet.state == "pass"


class TestAnUnmeasurableWidthFailsRatherThanReadsUnknown:
    def test_no_second_book_is_a_measured_absence_of_evidence(self):
        """`suppression.py`'s own distinction, carried over deliberately.

        A `None` width means fewer than two books contributed -- there was no
        second book to disagree with. That is a fact the desk measured, not a
        measurement it failed to take, so it fails rather than reading unknown.
        """
        check = next(
            c for c in score(market_width=None).checks if c.name == "books_agree"
        )
        assert check.state == "fail"
        assert "no second book" in check.detail


class TestEveryThresholdComesFromItsOwner:
    """Mutate the limit, not the data, and the verdict must follow.

    A literal in this module would be a second definition of a limit that
    already lives in config, and `config.py` refuses to boot when two limits on
    one quantity disagree. These are the assertions that keep it honest.
    """

    def test_the_consensus_limit_is_the_one_passed_in(self):
        assert next(
            c for c in score(odds_age_ms=800_000).checks
            if c.name == "consensus_fresh"
        ).state == "pass"
        assert next(
            c for c in score(odds_age_ms=800_000, max_odds_age_s=60).checks
            if c.name == "consensus_fresh"
        ).state == "fail"

    def test_the_quote_limit_is_the_one_passed_in(self):
        assert next(
            c for c in score(quote_age_ms=25_000, max_kalshi_quote_age_s=10).checks
            if c.name == "quote_fresh"
        ).state == "fail"

    def test_the_book_floor_is_the_one_passed_in(self):
        assert next(
            c for c in score(book_count=3, min_book_count=9).checks
            if c.name == "books"
        ).state == "fail"

    def test_the_depth_floor_is_the_one_passed_in(self):
        assert next(
            c for c in score(depth_at_ask=5.0, min_depth_contracts=2.0).checks
            if c.name == "depth"
        ).state == "pass"

    def test_method_agreement_uses_the_ladders_own_constant(self):
        """`AGREEMENT_SPREAD_POINTS` exists already and carries its own
        reasoning: two points is where method choice stops being the biggest
        thing in the number. This module must not restate it."""
        just_over = AGREEMENT_SPREAD_POINTS + 0.1
        assert next(
            c for c in score(method_spread_points=just_over).checks
            if c.name == "methods_agree"
        ).state == "fail"
        assert next(
            c for c in score(method_spread_points=AGREEMENT_SPREAD_POINTS).checks
            if c.name == "methods_agree"
        ).state == "pass"


class TestEveryFailureIsNamed:
    def test_all_failures_are_reported_not_just_the_first(self):
        """`SuppressionResult.reason`'s reasoning, carried over.

        Naming one failure hides the one that mattered more -- and choosing
        WHICH to name would be the importance weight this module refuses to
        invent.
        """
        s = score(book_count=1, depth_at_ask=0.0, quote_age_ms=90_000)
        assert {c.name for c in s.failures} == {"books", "depth", "quote_fresh"}

    def test_a_scout_flag_names_its_categories(self):
        s = score(scout="briefed", scout_flags=[
            {"category": "lineup", "state": "fresh", "note": "scratched"},
            {"category": "weather", "state": "unconfirmed", "note": "roof?"},
        ])
        check = next(c for c in s.checks if c.name == "scout")
        assert check.state == "fail"
        assert "lineup" in check.detail and "weather" in check.detail

    def test_a_suppressed_row_carries_the_code_verbatim(self):
        """ADR 0050: the code is the fact; a translation is a second definition."""
        check = next(
            c for c in score(suppressed_reason="stale_odds").checks
            if c.name == "skeptic"
        )
        assert check.state == "fail"
        assert check.detail == "stale_odds"


class TestNoEdgeQuantityReachesThisModule:
    """ADR 0038 stays closed, structurally rather than by intention.

    The measured `beta = -0.141` means an edge term would rank the least
    trustworthy rows highest. The defence is that the function cannot receive
    one: no parameter carries a fair value, an ask, or a difference of them.
    """

    def test_the_signature_takes_no_price_or_edge(self):
        import inspect

        params = set(inspect.signature(trust.score_trust).parameters)
        for banned in (
            "edge", "edge_tenths", "fair", "fair_probability", "ask",
            "ask_tenths", "ask_probability", "p_conservative", "ev",
            "breakeven", "kelly",
        ):
            assert banned not in params, (
                f"`{banned}` reaches the trust score; edge is measured "
                f"negatively predictive and may not enter it"
            )

    def test_the_module_names_no_edge_symbol(self):
        source = (
            ROOT / "backend" / "core" / "trust.py"
        ).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in source.splitlines()
            if not line.strip().startswith("#")
        )
        # The docstring explains WHY edge is excluded, so the word appears
        # there legitimately; what must not appear is arithmetic on one.
        for banned in ("edge_tenths", "expected_value", "kelly"):
            assert banned not in code, banned


class TestTheInterlockCannotSeeIt:
    def test_gate_does_not_import_trust(self):
        """The boundary `manual_orders`, `combo_orders` and the hedge tables
        each have. A trust score is not evidence and may not move the
        live-trading interlock's counter."""
        gate = (ROOT / "backend" / "gate.py").read_text(encoding="utf-8")
        # The IMPORT, not the word. `gate.py` says "refusing to trust a
        # half-written confirmation" in prose, and a substring test on that
        # fails for a reason that has nothing to do with this boundary --
        # a guard whose first finding is a false one gets deleted.
        for form in (
            "import trust",
            "from .core.trust",
            "from backend.core.trust",
            "core.trust",
        ):
            assert form not in gate, (
                f"gate.py imports the trust score ({form}); a trust score is "
                f"not evidence and may not move the interlock's counter"
            )

    def test_the_module_writes_nothing(self):
        source = (
            ROOT / "backend" / "core" / "trust.py"
        ).read_text(encoding="utf-8")
        for banned in ("INSERT", "UPDATE", "DELETE", "conn", "sqlite3"):
            assert banned not in source, (
                f"{banned} appears in a module that must stay pure"
            )
