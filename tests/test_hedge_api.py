"""The four hedge routes (ADR 0077).

What these tests establish: `GET /api/hedge` serves held tickets with every
money string worded server-side and no edge-shaped key anywhere in the payload;
an instance with no Kalshi credentials still renders the record rather than
failing; recording converts cents to tenths once, at the boundary; a ticket
whose figures cannot carry the arithmetic is refused at entry with the reason in
words; a leg settles once and a second attempt is a 409; `resolved_source` is
fixed at `manual` by the route and cannot be claimed by a client; and every
mutating route requires auth.

What they do not establish: that any hedge is worth taking, or that a
hand-marked leg actually won.
"""

from __future__ import annotations

import httpx
import pytest

from backend import hedge
from backend.api.routes import create_app
from backend.config import AppConfig
from backend.store import db as store

#: The same stems `tests/test_parlays_api.py` forbids on the parlay desk.
#: `edge_tenths = 1000 * (fair - breakeven)`, so serving fair beside any of
#: these hands the reader the measured-negative edge by subtraction — and a
#: hedge surface has no business carrying either half.
FORBIDDEN_STEMS = ("breakeven", "edge", "kelly", "ev_", "suggested", "fair_")

CIN = "KXMLBGAME-26AUG26CINSF-CIN"
LAD = "KXMLBGAME-26AUG26LADSD-LAD"

TICKET = {
    "source": "sportsbook",
    "label": "Saturday six",
    "stake_cents": 500,
    "return_cents": 33_333,
    "legs": [
        {"ticker": CIN, "side": "yes", "label": "Cincinnati to win"},
        {"ticker": LAD, "side": "yes", "label": "Los Angeles to win"},
    ],
}


@pytest.fixture()
def app(tmp_path):
    path = tmp_path / "cockpit.db"
    store.init_db(path).close()
    return create_app(
        AppConfig(db_path=path, instance_mode="live", auth_token="secret-token")
    )


async def call(app, method, path, **kwargs):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.request(method, path, **kwargs)


AUTH = {"Authorization": "Bearer secret-token"}


class TestRecordingATicket:
    async def test_it_records_and_comes_back_on_the_screen(self, app):
        posted = await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        assert posted.status_code == 200, posted.text
        position_id = posted.json()["position_id"]

        screen = await call(app, "GET", "/api/hedge")
        assert screen.status_code == 200
        body = screen.json()
        assert [p["id"] for p in body["positions"]] == [position_id]

    async def test_cents_are_converted_to_tenths_once_at_the_boundary(self, app):
        await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        body = (await call(app, "GET", "/api/hedge")).json()
        position = body["positions"][0]
        # $5.00 in, $333.33 back — the slip that prompted the parlay desk.
        assert position["stake_display"] == "$5.00"
        assert position["return_display"] == "$333.33"

    async def test_a_misplaced_decimal_point_is_refused_in_words(self, app):
        # $5 to return $100,000 -- 20,000x, twice the ceiling. The first
        # version of this used $33,333, which is 6,666x and INSIDE the range;
        # it failed for the right reason and taught the wrong lesson.
        bad = dict(TICKET, return_cents=10_000_000)
        refused = await call(app, "POST", "/api/hedge/positions", json=bad, headers=AUTH)
        assert refused.status_code == 422
        assert "decimal point" in refused.json()["detail"]

    async def test_a_return_below_the_stake_is_refused(self, app):
        bad = dict(TICKET, stake_cents=1_000, return_cents=900)
        refused = await call(app, "POST", "/api/hedge/positions", json=bad, headers=AUTH)
        assert refused.status_code == 422

    async def test_an_unknown_source_never_reaches_the_database(self, app):
        bad = dict(TICKET, source="betfair")
        assert (
            await call(app, "POST", "/api/hedge/positions", json=bad, headers=AUTH)
        ).status_code == 422

    async def test_a_leg_may_have_no_ticker_because_a_slip_leg_has_none(self, app):
        slip = dict(
            TICKET,
            legs=[{"side": "yes", "label": "A leg Kalshi does not list"}],
        )
        posted = await call(app, "POST", "/api/hedge/positions", json=slip, headers=AUTH)
        assert posted.status_code == 200
        body = (await call(app, "GET", "/api/hedge")).json()
        leg = body["positions"][0]["legs"][0]
        assert leg["ticker"] is None
        assert leg["priceable"] is False


class TestResolvingALeg:
    async def _leg_id(self, app, index=0):
        await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        body = (await call(app, "GET", "/api/hedge")).json()
        return body["positions"][0]["legs"][index]["id"]

    async def test_a_leg_settles_once(self, app):
        leg_id = await self._leg_id(app)
        first = await call(
            app,
            "POST",
            f"/api/hedge/legs/{leg_id}/resolve",
            json={"outcome": "won"},
            headers=AUTH,
        )
        assert first.status_code == 200
        second = await call(
            app,
            "POST",
            f"/api/hedge/legs/{leg_id}/resolve",
            json={"outcome": "lost"},
            headers=AUTH,
        )
        assert second.status_code == 409

    async def test_the_route_fixes_the_source_and_a_client_cannot_claim_venue(
        self, app
    ):
        """The two sources are not equally good evidence.

        `venue` means `kalshi_markets.result` said so; `manual` means Joe did.
        A request that could set the column would erase that the first time
        somebody found it convenient, and every lock computed afterwards would
        be unauditable.
        """
        leg_id = await self._leg_id(app)
        answered = await call(
            app,
            "POST",
            f"/api/hedge/legs/{leg_id}/resolve",
            json={"outcome": "won", "source": "venue", "resolved_source": "venue"},
            headers=AUTH,
        )
        assert answered.status_code == 200
        assert answered.json()["source"] == "manual"

        body = (await call(app, "GET", "/api/hedge")).json()
        leg = body["positions"][0]["legs"][0]
        assert leg["resolved_source"] == "manual"

    async def test_a_leg_that_does_not_exist_is_a_409_and_not_a_500(self, app):
        answered = await call(
            app,
            "POST",
            "/api/hedge/legs/9999/resolve",
            json={"outcome": "won"},
            headers=AUTH,
        )
        assert answered.status_code == 409

    @pytest.mark.parametrize("bad", ["pending", "cancelled", "WON"])
    async def test_an_unknown_outcome_is_refused_by_the_model(self, app, bad):
        leg_id = await self._leg_id(app)
        answered = await call(
            app,
            "POST",
            f"/api/hedge/legs/{leg_id}/resolve",
            json={"outcome": bad},
            headers=AUTH,
        )
        assert answered.status_code == 422


class TestClosingATicket:
    async def test_a_closed_ticket_leaves_the_screen(self, app):
        posted = await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        position_id = posted.json()["position_id"]
        closed = await call(
            app,
            "POST",
            f"/api/hedge/positions/{position_id}/close",
            json={"status": "settled"},
            headers=AUTH,
        )
        assert closed.status_code == 200
        assert (await call(app, "GET", "/api/hedge")).json()["positions"] == []

    async def test_closing_twice_is_a_409(self, app):
        posted = await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        position_id = posted.json()["position_id"]
        for expected in (200, 409):
            answered = await call(
                app,
                "POST",
                f"/api/hedge/positions/{position_id}/close",
                json={"status": "settled"},
                headers=AUTH,
            )
            assert answered.status_code == expected


class TestThePayload:
    async def test_it_carries_no_edge_shaped_key_anywhere(self, app):
        await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        body = (await call(app, "GET", "/api/hedge")).json()

        seen: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    seen.append(key)
                    # "hedge" contains "edge", so the word this whole
                    # feature is named after is removed before the stems are
                    # applied. Without it `is_hedge_leg` trips a rule aimed at
                    # `edge_tenths`, and the only ways out are weakening the
                    # rule or renaming the domain.
                    lowered = key.lower().replace("hedge", "")
                    for stem in FORBIDDEN_STEMS:
                        assert stem not in lowered, key
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(body)
        # Vacuity guard: a walk over an empty payload would pass in silence.
        assert len(seen) > 25
        # And the stems must still bite after the "hedge" removal above.
        assert "edge_tenths" not in seen
        with pytest.raises(AssertionError):
            walk({"edge_tenths": 1})

    async def test_the_four_caveats_travel_with_it(self, app):
        body = (await call(app, "GET", "/api/hedge")).json()
        assert set(body["notes"]) == {
            "upper_bound",
            "not_advice",
            "no_button",
            "derisk",
        }
        # The sentence that keeps the figure honest is present, not merely a key.
        assert "ceiling" in body["notes"]["upper_bound"]

    async def test_no_credentials_still_renders_the_record(self, app):
        """The demo instance holds no Kalshi key and must not 500 on this.

        Every leg simply has no readable book, which the payload has words for.
        `create_app` runs on both deploys from one image.
        """
        await call(app, "POST", "/api/hedge/positions", json=TICKET, headers=AUTH)
        body = (await call(app, "GET", "/api/hedge")).json()
        position = body["positions"][0]
        assert position["state"] == hedge.STATE_NOT_HEDGEABLE
        assert all(leg["priceable"] is False for leg in position["legs"])
        assert position["hedge"] is None

    async def test_an_empty_screen_is_an_empty_list_and_not_an_error(self, app):
        body = (await call(app, "GET", "/api/hedge")).json()
        assert body["positions"] == []
        assert body["as_of_ms"] > 0


class TestEveryMutatingRouteNeedsAuth:
    """`CLAUDE.md`: every mutating route requires auth. Asserted per route
    rather than once, because the failure mode is a new route added without
    the dependency and a single spot-check cannot see it."""

    async def test_recording_needs_auth(self, app):
        assert (
            await call(app, "POST", "/api/hedge/positions", json=TICKET)
        ).status_code == 401

    async def test_resolving_needs_auth(self, app):
        assert (
            await call(
                app, "POST", "/api/hedge/legs/1/resolve", json={"outcome": "won"}
            )
        ).status_code == 401

    async def test_closing_needs_auth(self, app):
        assert (
            await call(
                app,
                "POST",
                "/api/hedge/positions/1/close",
                json={"status": "settled"},
            )
        ).status_code == 401

    async def test_reading_does_not(self, app):
        assert (await call(app, "GET", "/api/hedge")).status_code == 200

    def test_every_hedge_post_route_declares_the_dependency(self):
        """Read off the app itself, so a route added later is included.

        The population is enumerated rather than listed — the shape
        `tests/test_has_callers.py` calls "fails closed".
        """
        from backend.api.routes import create_app as factory

        application = factory(
            AppConfig(
                db_path=":memory:", instance_mode="live", auth_token="secret-token"
            )
        )
        checked = 0
        for route in application.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set()) or set()
            if not path.startswith("/api/hedge") or "POST" not in methods:
                continue
            checked += 1
            assert route.dependencies, path
        assert checked == 3
