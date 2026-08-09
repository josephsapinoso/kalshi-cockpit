"""The §S1 population predicate, pinned against the reasons the code can emit.

`docs/measurements/2026-08-09-preregistration-clv-signal-test.md` §2 excludes
two suppression codes -- `stale_odds` and `stale_kalshi_quote` -- because each
contaminates the regressor. §S1 implemented that exclusion as

    suppressed_reason NOT IN ('stale_odds', 'stale_kalshi_quote')

and `SuppressionResult.reason` is a **comma-joined composite** of every check
that failed, not a single code. `evaluate_suppression` deliberately runs all
checks rather than short-circuiting, so co-occurrence is the normal case, not
an edge case: a stale quote is exactly the condition under which a book also
goes wide and depth also thins. A row reading `stale_odds,wide_market` is equal
to neither literal, so `NOT IN` **retained** it -- the precise population the
exclusion existed to remove.

Amendment 1 replaces the predicate with a delimited substring test. These tests
pin that replacement against composites produced by running the real
`evaluate_suppression`, never by writing the strings out by hand, and they
assert the defect in the superseded predicate directly so the correction cannot
silently regress into it.

What this does not establish
----------------------------
That the live record contains any of these composites, or in what proportion --
no data was read to write this. It establishes only that the amended predicate
classifies every reason string the code *can* produce the way §2 says it must.
It says nothing about the other exclusions in §2, nothing about the half-spread
join, and nothing about `beta`.
"""

from __future__ import annotations

import pytest

from backend.agents.skeptic import apply_verdict
from backend.core.suppression import SuppressionConfig, evaluate_suppression
from backend.store import db

CONFIG = SuppressionConfig()

# The two codes §2 excludes, and the reason each is excluded is a function of
# input timestamps alone -- never of `clv_tenths`.
EXCLUDED_CODES = ("stale_odds", "stale_kalshi_quote")

# What §S1 registered. Superseded by Amendment 1; kept here as the thing the
# amended predicate is measured against, because "the new one passes" says
# nothing unless the old one is shown to fail on the same input.
REGISTERED_PREDICATE = (
    "(suppressed_reason IS NULL "
    " OR suppressed_reason NOT IN ('stale_odds', 'stale_kalshi_quote'))"
)

# Amendment 1. `instr` rather than `LIKE`, because `_` is a single-character
# wildcard in `LIKE` and every code in this vocabulary contains underscores --
# `LIKE '%,stale_odds,%'` also matches `,staleXodds,`. That over-exclusion is
# not reachable from today's code, but a predicate that is only correct because
# no one has added a colliding code name is a predicate with a trap in it.
# `instr` is a plain substring search with no metacharacters at all.
AMENDED_PREDICATE = (
    "(suppressed_reason IS NULL "
    " OR (instr(',' || suppressed_reason || ',', ',stale_odds,') = 0 "
    "     AND instr(',' || suppressed_reason || ',', ',stale_kalshi_quote,') = 0))"
)


def reason_for(**overrides) -> str:
    """A composite reason string, produced by the code that writes them.

    The baseline passes every check, so each override breaks exactly the checks
    it names and the returned string is the real wire format -- ordering,
    separator and vocabulary included.
    """
    args = dict(
        config=CONFIG,
        kalshi_quote_age_ms=5_000,
        odds_age_ms=120_000,
        commence_skew_ms=60_000,
        depth_at_ask=200.0,
        contracts=25,
        market_width=0.01,
        book_count=4,
        edge_tenths=20.0,
        method_spread_probability=0.002,
    )
    args.update(overrides)
    result = evaluate_suppression(**args)
    assert result.reason is not None, "override did not suppress anything"
    return result.reason


STALE_ODDS_ONLY = {"odds_age_ms": 1_000_000}
STALE_QUOTE_ONLY = {"kalshi_quote_age_ms": 120_000}
# Staleness beside another failure. This is the shape `NOT IN` let through.
STALE_ODDS_AND_WIDE = {"odds_age_ms": 1_000_000, "market_width": 0.20}
# Both stale codes plus most of the rest, which is what a genuinely broken
# upstream pass produces -- one dead feed fails several checks at once.
NEARLY_EVERYTHING = {
    "kalshi_quote_age_ms": 120_000,
    "odds_age_ms": 1_000_000,
    "commence_skew_ms": None,
    "depth_at_ask": None,
    "book_count": 1,
    "market_width": None,
    "edge_tenths": 400.0,
}
# No staleness anywhere: §2 retains all of these.
WIDE_ONLY = {"market_width": 0.20}
NO_CONSENSUS = {"book_count": 1, "market_width": None}
SUSPICIOUS_ONLY = {"edge_tenths": 400.0}
METHOD_NOISE_ONLY = {"edge_tenths": 1.0, "method_spread_probability": 0.002}


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "prereg.db")
    c.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    c.execute(
        "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
        "VALUES ('MKT', 0, 0)"
    )
    c.commit()
    yield c
    c.close()


def add_row(conn, suppressed_reason):
    cursor = conn.execute(
        "INSERT INTO recommendations (created_ms, strategy_config_version, "
        "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
        "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
        "kalshi_quote_age_ms, odds_age_ms, suppressed_reason, reason_text) "
        "VALUES (?, 1, 'MKT', 'yes', 480, 0.5, 10.0, 0.1, 0.5, 0.02, 0, "
        "1000, 1000, ?, 'x')",
        (1_754_800_000_000, suppressed_reason),
    )
    conn.commit()
    return cursor.lastrowid


def retained(conn, predicate: str, row_id: int) -> bool:
    """Whether the population predicate keeps this row."""
    found = conn.execute(
        f"SELECT id FROM recommendations WHERE id = ? AND {predicate}",
        (row_id,),
    ).fetchone()
    return found is not None


class TestTheCompositeFormatIsWhatTheDocumentAssumed:
    """If this changes, the predicate below is answering the wrong question."""

    def test_a_multi_failure_row_joins_its_codes_with_commas(self):
        assert reason_for(**STALE_ODDS_AND_WIDE) == "stale_odds,wide_market"

    def test_a_single_failure_row_is_a_bare_code(self):
        assert reason_for(**STALE_ODDS_ONLY) == "stale_odds"

    def test_staleness_is_not_rare_beside_other_failures(self):
        """One dead feed trips several checks, which is why `NOT IN` was wrong.

        `evaluate_suppression` runs every check rather than short-circuiting, on
        purpose -- so a stale row *always* also reports whatever else was
        broken, and the composite is the normal output rather than the unusual
        one.
        """
        codes = reason_for(**NEARLY_EVERYTHING).split(",")
        assert "stale_odds" in codes
        assert "stale_kalshi_quote" in codes
        assert len(codes) > 2, codes

    def test_the_skeptic_appends_to_an_existing_reason_with_a_comma(self):
        """A twelfth code family the audit's list of eleven did not carry.

        `skeptic_defect` / `skeptic_suspicious` are appended by `apply_verdict`
        in the same comma-joined format, so the predicate has to survive them
        too.
        """
        assert apply_verdict(_Blocking("defect"), None) == "skeptic_defect"
        assert (
            apply_verdict(_Blocking("suspicious"), "sizing:refused")
            == "sizing:refused,skeptic_suspicious"
        )


class _Blocking:
    """The two fields `apply_verdict` reads, without an API round trip."""

    def __init__(self, verdict: str):
        self.verdict = verdict
        self.blocks_bet = True


class TestTheAmendedPredicateExcludesEveryStaleRow:
    @pytest.mark.parametrize(
        "overrides",
        [STALE_ODDS_ONLY, STALE_QUOTE_ONLY, STALE_ODDS_AND_WIDE, NEARLY_EVERYTHING],
        ids=["stale_odds", "stale_quote", "stale_and_wide", "nearly_everything"],
    )
    def test_a_stale_row_is_excluded_however_many_codes_it_carries(
        self, conn, overrides
    ):
        reason = reason_for(**overrides)
        row_id = add_row(conn, reason)
        assert not retained(conn, AMENDED_PREDICATE, row_id), (
            f"{reason!r} carries an excluded staleness code and reached the "
            f"regression population. §2 excludes it because the price behind "
            f"`edge_tenths` had already moved."
        )

    def test_the_superseded_predicate_let_the_multi_reason_row_through(self, conn):
        """The defect Amendment 1 exists to fix, asserted rather than described.

        Written first and run against `AMENDED_PREDICATE` in place of the
        registered one, where it fails -- which is what makes the test above a
        guard rather than decoration.
        """
        row_id = add_row(conn, reason_for(**STALE_ODDS_AND_WIDE))
        assert retained(conn, REGISTERED_PREDICATE, row_id), (
            "the registered `NOT IN` predicate no longer has the defect "
            "Amendment 1 was written for -- if the composite format changed, "
            "re-derive the amendment rather than deleting this test"
        )
        assert not retained(conn, AMENDED_PREDICATE, row_id)

    def test_both_predicates_agree_on_a_row_carrying_only_one_code(self, conn):
        """`NOT IN` was not wrong everywhere, which is why it survived review."""
        row_id = add_row(conn, reason_for(**STALE_ODDS_ONLY))
        assert not retained(conn, REGISTERED_PREDICATE, row_id)
        assert not retained(conn, AMENDED_PREDICATE, row_id)


class TestTheAmendedPredicateRetainsWhatSectionTwoRetains:
    """Over-exclusion is the other failure, and it is the invisible one.

    An exclusion that quietly removes `wide_market` would truncate the
    regressor's noisy end and inflate `beta` -- the flattering direction, with
    nothing on any screen to say it happened.
    """

    @pytest.mark.parametrize(
        "overrides",
        [WIDE_ONLY, NO_CONSENSUS, SUSPICIOUS_ONLY, METHOD_NOISE_ONLY],
        ids=["wide_market", "no_consensus", "suspicious_edge", "method_noise"],
    )
    def test_a_non_stale_suppression_is_retained(self, conn, overrides):
        reason = reason_for(**overrides)
        assert not any(code in reason.split(",") for code in EXCLUDED_CODES)
        row_id = add_row(conn, reason)
        assert retained(conn, AMENDED_PREDICATE, row_id), reason

    def test_an_unsuppressed_row_is_retained(self, conn):
        row_id = add_row(conn, None)
        assert retained(conn, AMENDED_PREDICATE, row_id)

    @pytest.mark.parametrize(
        "reason",
        ["sizing:refused", "skeptic_defect", "sizing:refused,skeptic_suspicious"],
    )
    def test_the_sizing_and_skeptic_codes_are_retained(self, conn, reason):
        row_id = add_row(conn, reason)
        assert retained(conn, AMENDED_PREDICATE, row_id)


class TestTheDelimitersAreLoadBearing:
    """The guard on the guard.

    A bare `instr(suppressed_reason, 'stale_odds')` would look identical on
    every row above and would also strike any future code whose name contains
    one of these as a substring. The leading and trailing commas are what make
    the match a whole-field match, and nothing else in the suite would notice
    if they were dropped.
    """

    def test_a_code_containing_an_excluded_name_is_not_excluded(self, conn):
        """Not producible today. That is the point: the predicate must not
        depend on nobody ever adding `stale_odds_upstream`."""
        row_id = add_row(conn, "stale_odds_upstream,wide_market")
        assert retained(conn, AMENDED_PREDICATE, row_id)

        undelimited = "(instr(suppressed_reason, 'stale_odds') = 0)"
        assert not retained(conn, undelimited, row_id), (
            "the undelimited form no longer over-excludes, so the commas in "
            "AMENDED_PREDICATE are no longer doing anything and this test has "
            "stopped testing them"
        )

    def test_like_would_treat_the_underscores_as_wildcards(self, conn):
        """Why `instr` and not `LIKE`, asserted on the operators themselves.

        Every code in this vocabulary contains `_`, which `LIKE` reads as
        "any single character". The delimited `LIKE` form is therefore correct
        only by the accident that no code name collides.
        """
        row_id = add_row(conn, "staleXodds")
        like_form = (
            "(',' || suppressed_reason || ',' NOT LIKE '%,stale_odds,%')"
        )
        assert not retained(conn, like_form, row_id), (
            "`LIKE` stopped treating `_` as a wildcard, so `instr` is no "
            "longer buying anything and the choice can be revisited"
        )
        assert retained(conn, AMENDED_PREDICATE, row_id)
