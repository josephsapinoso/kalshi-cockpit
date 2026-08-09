"""The evidence record has to be readable from a phone.

Every test here exists because a real reconnaissance pass over the live record
produced arithmetic that was invalid, and **every defect traced to a field the
API did not expose**:

- 743 scored rows were counted off `/api/ledger` against the 476 the gate
  reports at the primary horizon, because the payload carried `clv_tenths` and
  nothing saying which anchor produced it. The mixture is not neutral: a 1h line
  is a weaker benchmark than the close (`backend/analysis/clv.py`), so pooling
  biases the result in the flattering direction.
- Whether `reference_contracts > 0` had ever occurred was unanswerable from the
  API at all. `gate.population_counts` answers it and was emitted only into the
  log stream, i.e. reachable only through `flyctl`, i.e. from a laptop.
- `/api/ledger` returned no row total, so 1,000 rows and "the whole table" were
  indistinguishable in the payload.

**What these tests do not establish.** They assert that the numbers are
*reachable and correctly scoped*. They say nothing about whether the record
those numbers describe is any good, and nothing about what the gate decides --
`TestTheGateVerdictIsUnchanged` asserts precisely that this commit did not touch
that.
"""

from __future__ import annotations

import httpx
import pytest

from backend.analysis.clv import CONTROL_HORIZON_HOURS, DEFAULT_HORIZON_HOURS
from backend.api.routes import create_app
from backend.config import AppConfig, GateConfig
from backend.gate import evaluate_gate
from backend.store import db


async def get(app, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        return await c.get(path, **kwargs)


# One row per case, written by hand rather than seeded, because the states that
# matter here are exactly the ones a healthy seed does not produce: a legacy
# horizon, an unscored row, and a row whose two sizings disagree.
#
# `(horizon, suggested, reference, suppressed_reason)`
_ROWS = (
    # Scored at the current anchor, actionable, and the two sizings **differ** --
    # which is the state the $100 deployment writes and the backfilled record
    # cannot contain.
    (DEFAULT_HORIZON_HOURS, 1, 12, None),
    (DEFAULT_HORIZON_HOURS, 0, 9, None),
    # Scored at the legacy anchor. Permanently 1.0h observations: kept as record,
    # never as evidence, and never poolable with the two above.
    (CONTROL_HORIZON_HOURS, 3, 3, None),
    (CONTROL_HORIZON_HOURS, 0, 0, None),
    (CONTROL_HORIZON_HOURS, 0, 0, "suspicious_edge"),
    # Unscored. Distinct from every horizon, including 0.0.
    (None, 0, 0, "stale_odds"),
    (None, 4, 4, None),
)


@pytest.fixture
def mixed_db(tmp_path):
    """A record that is horizon-mixed and reference-divergent, on purpose."""
    path = tmp_path / "mixed.db"
    conn = db.init_db(path)
    conn.execute(
        "INSERT INTO strategy_configs (version, created_ms, effective_from_ms, "
        "config_json, rationale) VALUES (1, 0, 0, '{}', 'test')"
    )
    for i, (horizon, suggested, reference, suppressed) in enumerate(_ROWS):
        ticker = f"KXTEST-{i:02d}"
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, first_seen_ms, last_seen_ms) "
            "VALUES (?, ?, ?)",
            (ticker, 1000, 1000),
        )
        conn.execute(
            "INSERT INTO recommendations (created_ms, strategy_config_version, "
            "ticker, side, entry_ask_tenths, fair_probability, edge_tenths, "
            "fee_predicted, ev_net_dollars, kelly_fraction, suggested_contracts, "
            "reference_contracts, kalshi_quote_age_ms, odds_age_ms, "
            "suppressed_reason, reason_text, clv_tenths, clv_scored_ms, "
            "clv_horizon_hours) VALUES "
            "(?, 1, ?, 'yes', 500, 0.52, 5.0, 0.1, 0.2, 0.01, ?, ?, 1000, 2000, "
            " ?, 'test row', ?, ?, ?)",
            (
                1000 + i,
                ticker,
                suggested,
                reference,
                suppressed,
                None if horizon is None else 1.0,
                None if horizon is None else 9999,
                horizon,
            ),
        )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def mixed_app(mixed_db):
    return create_app(AppConfig(instance_mode="demo", db_path=mixed_db))


class TestTheHorizonIsOnEveryRow:
    """Two regimes that must never be pooled, told apart from the payload alone."""

    async def test_the_row_carries_the_anchor_its_clv_was_measured_against(
        self, mixed_app
    ):
        rows = (await get(mixed_app, "/api/ledger")).json()["rows"]
        assert all("clv_horizon_hours" in r for r in rows)
        scored = [r for r in rows if r["clv_tenths"] is not None]
        assert scored, "fixture must contain scored rows or this proves nothing"
        assert {r["clv_horizon_hours"] for r in scored} == {
            DEFAULT_HORIZON_HOURS,
            CONTROL_HORIZON_HOURS,
        }

    async def test_a_consumer_can_reproduce_the_gates_count_from_the_payload(
        self, mixed_app
    ):
        """The defect, stated as its fix.

        Counting scored rows without filtering on the horizon gives 5 here and 2
        at the anchor the gate reads. That gap is the 743-against-476 defect in
        miniature, and it is now a filter a caller can apply rather than a
        mixture they cannot see.
        """
        body = (await get(mixed_app, "/api/ledger")).json()
        rows = body["rows"]
        pooled = [r for r in rows if r["clv_tenths"] is not None]
        at_anchor = [
            r
            for r in pooled
            if r["clv_horizon_hours"] == body["primary_horizon_hours"]
        ]
        assert len(pooled) == 5
        assert len(at_anchor) == 2
        assert body["clv_scored_rows"] == len(at_anchor)

    async def test_unscored_is_not_the_same_state_as_the_zero_hour_anchor(
        self, mixed_app
    ):
        """**0.0 is a legitimate horizon and it is falsy.**

        A row scored against the close and a row never scored at all must not
        collapse into one bucket, which is what any truthiness test on this
        field does.
        """
        rows = (await get(mixed_app, "/api/ledger")).json()["rows"]
        unscored = [r for r in rows if r["clv_horizon_hours"] is None]
        at_close = [r for r in rows if r["clv_horizon_hours"] == 0.0]
        assert len(unscored) == 2
        assert len(at_close) == 2
        assert all(r["clv_tenths"] is None for r in unscored)
        assert all(r["clv_tenths"] is not None for r in at_close)


class TestTheTwoSizingsAreSeparatelyVisible:
    """`suggested_contracts` is what you may buy; `reference_contracts` is what
    the record counts. The payload used to answer only the first, which made the
    gate's own admission criterion unreadable from anywhere but a log line."""

    async def test_the_counted_size_is_on_the_row(self, mixed_app):
        rows = (await get(mixed_app, "/api/ledger")).json()["rows"]
        assert all("reference_contracts" in r for r in rows)

    async def test_the_two_columns_are_not_the_same_field_twice(self, mixed_app):
        """If this ever passes only because the fixture makes them equal, it is
        testing nothing. The fixture writes rows where they differ on purpose."""
        rows = (await get(mixed_app, "/api/ledger")).json()["rows"]
        differing = [
            r for r in rows if r["reference_contracts"] != r["suggested_contracts"]
        ]
        assert len(differing) == 2
        # And the direction that matters: a row sized to zero at the deposit is
        # still evidence at the reference profile. Reading `suggested_contracts`
        # to judge the record would have discarded it.
        counted_but_unbuyable = [
            r
            for r in rows
            if r["suggested_contracts"] == 0 and (r["reference_contracts"] or 0) > 0
        ]
        assert len(counted_but_unbuyable) == 1

    async def test_the_board_and_the_ledger_carry_the_same_two_fields(
        self, mixed_app
    ):
        """One serialiser, so the screens cannot describe a row differently."""
        board = (await get(mixed_app, "/api/board?include_suppressed=true")).json()
        every = board["surfaced"] + board["expired"] + board["suppressed"] + board["no_edge"]
        assert every
        assert all("reference_contracts" in r for r in every)
        assert all("clv_horizon_hours" in r for r in every)


class TestASliceIsDistinguishableFromTheTable:
    async def test_the_total_counts_the_table_not_the_window(self, mixed_app):
        body = (await get(mixed_app, "/api/ledger?limit=2")).json()
        assert body["returned"] == 2
        assert body["limit"] == 2
        assert body["total"] == len(_ROWS)
        assert body["total"] > body["returned"], "the fixture must be truncated"

    async def test_an_untruncated_read_says_so(self, mixed_app):
        body = (await get(mixed_app, "/api/ledger")).json()
        assert body["returned"] == body["total"] == len(_ROWS)

    async def test_the_horizon_breakdown_is_over_the_table_not_the_window(
        self, mixed_app
    ):
        """The legacy rows are the **oldest**, and the window is newest-first.

        So a breakdown computed off `rows` is precisely the one that hides the
        contamination it exists to reveal. `limit=2` returns only the two
        newest rows; the breakdown must still see all seven.
        """
        body = (await get(mixed_app, "/api/ledger?limit=2")).json()
        assert body["horizons"] == {"0": 2, "1": 3, "unscored": 2}
        assert sum(body["horizons"].values()) == body["total"]

    async def test_the_breakdown_keeps_zero_and_unscored_apart(self, mixed_app):
        """Same falsy-zero trap as on the row, one level up."""
        horizons = (await get(mixed_app, "/api/ledger")).json()["horizons"]
        assert horizons["0"] == 2
        assert horizons["unscored"] == 2
        assert horizons["0"] != horizons["unscored"] + horizons["0"]

    async def test_it_names_the_anchor_the_gate_counts(self, mixed_app):
        body = (await get(mixed_app, "/api/ledger")).json()
        assert body["primary_horizon_hours"] == DEFAULT_HORIZON_HOURS


class TestPopulationCountsAreReachableWithoutAnLaptop:
    async def test_the_gate_endpoint_publishes_them(self, mixed_app):
        body = (await get(mixed_app, "/api/gate")).json()
        assert set(body["populations"]["counts"]) == {
            "actionable",
            "no_edge",
            "suppressed",
        }

    async def test_they_count_the_whole_table_not_a_recent_window(self, mixed_app):
        """`log_gate_progress` asks "is this producing anything today". This is
        asked "has it ever", and the fixture's rows are all at epoch+1s -- so a
        24h window would report zeros for a record that is not empty."""
        counts = (await get(mixed_app, "/api/gate")).json()["populations"]["counts"]
        assert counts["actionable"] == 4
        assert counts["no_edge"] == 1
        assert counts["suppressed"] == 2
        assert sum(counts.values()) == len(_ROWS)

    async def test_they_count_rows_written_not_rows_scored(self, mixed_app):
        """The distinction that makes this worth exposing separately.

        The gate's conditions read the scored-at-the-anchor subset (2 rows
        here). The populations read every row ever written (7). A zero in the
        first is a statement about scoring; a zero in the second is a statement
        about whether the strategy has ever had a bet at all.
        """
        body = (await get(mixed_app, "/api/gate")).json()
        assert sum(body["populations"]["counts"].values()) == len(_ROWS)
        assert body["populations"]["since_ms"] == 0

    async def test_it_is_openable_in_a_browser_without_a_bearer_token(
        self, mixed_db
    ):
        """The whole defect is that the number was laptop-only.

        A bearer token cannot be typed into a phone's address bar, and the Next
        layer that proxies `/api/*` sends no `Authorization` header -- so
        putting this behind `require_auth` would move it from one unreachable
        place to another. It is not unauthenticated on live: the Next
        middleware 401s every `/api/*` path without a session cookie, which is
        the one credential a phone browser can carry.

        Asserted on the **live** instance, where `auth_token` exists and is
        deliberately not required for this read.
        """
        live = create_app(
            AppConfig(
                instance_mode="live", auth_token="secret-token", db_path=mixed_db
            )
        )
        response = await get(live, "/api/gate")
        assert response.status_code == 200
        assert response.json()["populations"]["counts"]["actionable"] == 4

    async def test_the_predicates_are_published_beside_the_numbers(self, mixed_app):
        """`no_edge` reading as a rejection is a misreading this repo has
        already had to correct once."""
        predicates = (await get(mixed_app, "/api/gate")).json()["populations"][
            "predicates"
        ]
        assert "reference_contracts" in predicates["actionable"]
        assert "suppressed_reason IS NULL" in predicates["no_edge"]


class TestTheGateVerdictIsUnchanged:
    """This commit adds fields an operator can read. It must not move a threshold,
    a predicate, or a decision -- and "must not" is only worth writing down if
    something fails when it does."""

    async def test_the_endpoint_reports_exactly_what_evaluate_gate_decides(
        self, mixed_app, mixed_db
    ):
        conn = db.open_db(mixed_db, read_only=True)
        try:
            decided = evaluate_gate(conn, GateConfig()).to_dict()
        finally:
            conn.close()
        served = (await get(mixed_app, "/api/gate")).json()
        for key, value in decided.items():
            assert served[key] == value

    async def test_the_added_keys_are_purely_additive(self, mixed_app):
        """Nothing that existed was renamed or removed. The frontend reads this."""
        body = (await get(mixed_app, "/api/gate")).json()
        assert {"open", "conditions", "reason", "bankroll_dollars", "note"} <= set(body)
        assert set(body) - {"populations"} == {
            "open",
            "conditions",
            "reason",
            "bankroll_dollars",
            "note",
        }

    async def test_the_ledger_keeps_every_field_it_had(self, mixed_app):
        body = (await get(mixed_app, "/api/ledger")).json()
        assert {
            "rows",
            "clv_scored",
            "clv_scored_rows",
            "clv_required",
            "gate_open",
        } <= set(body)

    async def test_the_verdict_is_pinned(self, mixed_app):
        """A golden pin on the decision itself, so a future change to a
        threshold or a population predicate reddens here rather than being
        discovered on the live record."""
        body = (await get(mixed_app, "/api/gate")).json()
        assert body["open"] is False
        assert [(c["name"], c["met"]) for c in body["conditions"]] == [
            ("scored_recommendations", False),
            ("clv_survives_noise_guard", False),
            ("fee_model_verified", False),
            ("config_enabled", False),
        ]

    async def test_reading_the_populations_does_not_move_the_decision(
        self, mixed_app
    ):
        """The new query is a read. Two consecutive fetches of a static database
        must agree, including after the populations block has been computed."""
        first = (await get(mixed_app, "/api/gate")).json()
        second = (await get(mixed_app, "/api/gate")).json()
        assert first["conditions"] == second["conditions"]
        assert first["open"] is second["open"] is False
