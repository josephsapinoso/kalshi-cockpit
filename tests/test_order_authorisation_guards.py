"""The two order-endpoint refusals `test_quote_refresh.py` never reaches.

`_place_order` (`backend/api/routes.py`) runs a numbered sequence of refusal
steps before it will spend a Kalshi request or a dollar. Steps 2 (suppressed),
5 (gate) and 6 (game started) already have end-to-end coverage in
`test_quote_refresh.py`, `test_order_record.py` and `test_order_idempotency.py`.
Two did not:

- **Step 1** -- the recommendation id has to resolve to a row at all.
- **Step 3** -- a row with no suppression reason is not automatically a row
  worth betting. `suggested_contracts <= 0` means the engine looked and found
  no edge, and that state has to refuse exactly like a suppressed one does.
  The comment at `backend/api/routes.py:2106-2126` names the defect this
  guards against: on the seeded demo, three rows the engine scored at -6.0c,
  -3.5c and -1.2c per contract were orderable at maximum size because only
  `suppressed_reason` was being checked.

Both tests assert the status code **and** a substring of the refusal text
that is unique to that guard, per the shape every other guard test in this
suite uses (`test_a_suppressed_row_is_refused_before_any_request` and
neighbours in `test_quote_refresh.py`). A status code alone cannot say which
of a dozen 422s fired; the earlier failure mode in this repo is exactly a
green test whose asserted copy had gone stale.

What these tests do not establish
----------------------------------
- **That these are the only ways to trip steps 1 or 3.** Step 1 is exercised
  with an id that was simply never inserted; a row that existed and was later
  deleted, or one from a different (foreign-key-orphaned) table state, is not
  covered. Step 3 is exercised only at `suggested_contracts == 0`; a negative
  value is not, though the guard reads `<= 0` and nothing here would catch a
  regression that special-cased zero and let negative values through.
- **Ordering relative to steps 4, 5, 6, 7.** Both cases are constructed so the
  refusing check is the first one that *could* fire (no suppression reason, a
  live gate, a linked pre-game fixture with readable ages), which is what
  makes `quotes.calls == []` meaningful -- but it also means these tests say
  nothing about what happens when an unknown id or a no-edge row is combined
  with, say, an already-started game. That combination is untested.
"""

from __future__ import annotations

import pytest

from .test_quote_refresh import FakeQuotes, _live_pick, _order, _app, build_armed_db


@pytest.fixture
def armed_db(tmp_path):
    """Built, not imported -- see `test_order_idempotency.py` for why: a
    re-exported fixture shadows itself in every signature that takes it."""
    return build_armed_db(tmp_path)


class TestTheRecommendationMustExist:
    async def test_an_unknown_recommendation_is_refused_not_invented(
        self, armed_db
    ):
        """Step 1, `backend/api/routes.py:2085-2092`.

        No row with this id was ever inserted -- `armed_db` seeds 400 rows
        with autoincrement ids well below this one, so it collides with
        nothing. The refusal has to name the id and say it does not exist,
        not fall through to whatever a later step would say about a `None`.
        """
        path, conn, now = armed_db
        quotes = FakeQuotes()
        unknown_id = 999_999_999

        response = await _order(_app(path, quotes), unknown_id)

        assert response.status_code == 404
        body = response.json()
        assert "does not exist" in body["detail"]
        assert str(unknown_id) in body["detail"]
        # Nothing about a made-up id should ever cost a Kalshi request.
        assert quotes.calls == []


class TestTheEngineMustHaveAuthorisedABet:
    async def test_a_row_with_no_edge_is_refused_not_offered_at_size(
        self, armed_db
    ):
        """Step 3, `backend/api/routes.py:2106-2126`.

        `suppressed_reason` is NULL (the default `_live_pick` writes) and
        `suggested_contracts` is 0 -- the engine's own "no edge" state, which
        this repo has previously (wrongly) treated as identical to a
        suppressed row's absence of a reason. It is not: a suppressed row was
        rejected for a reason, a zero-contract row was evaluated and found
        wanting, and both must refuse, but this is the guard that was
        missing when three -6.0c/-3.5c/-1.2c rows were orderable at maximum
        size on the seeded demo.
        """
        path, conn, now = armed_db
        rec = _live_pick(conn, now, suggested_contracts=0, suppressed=None)
        quotes = FakeQuotes()

        response = await _order(_app(path, quotes), rec)

        assert response.status_code == 422
        body = response.json()
        assert "found no edge worth betting after fees" in body["detail"]
        assert "was sized at 0 contracts" in body["detail"]
        # Fires before the gate check and before any Kalshi request -- a
        # no-edge row should never reach either.
        assert quotes.calls == []
