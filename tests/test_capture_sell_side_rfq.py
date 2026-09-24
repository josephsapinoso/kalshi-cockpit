"""`scripts/capture_sell_side_rfq.py` -- one sell-side ask, raw payloads kept (#129).

What these establish: the script never touches the accept path; the size it
asks for is floored from `position_fp`, never rounded; the capture is on disk
BEFORE the RFQ is withdrawn; an existing capture path, an unheld ticker and an
already-open RFQ each refuse before any venue write; and the redaction keeps
prices verbatim while replacing every identity.

What they do not establish: that a maker will bid, what the venue's real
`/markets/{ticker}` envelope looks like today (the fake mirrors the shape
`backend/kalshi/combos.py` reads), or anything about the accept path -- which
is the point.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "capture_sell_side_rfq.py"

TICKER = "KXMVECROSSCATEGORY-S2026TEST-ABC"
COLLECTION = "KXMVECROSSCATEGORY-R"
LEGS = [
    {"event_ticker": "KXNCAAFGAME-26SEP17SYRPITT", "market_ticker": "KXNCAAFGAME-26SEP17SYRPITT-PITT", "side": "yes"},
    {"event_ticker": "KXWNBAGAME-26SEP17CONNATL", "market_ticker": "KXWNBAGAME-26SEP17CONNATL-ATL", "side": "yes"},
]


def _load():
    spec = importlib.util.spec_from_file_location("capture_sell_side_rfq", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():
    return _load()


def _quote(quote_id: str, *, yes_bid: str, no_bid: str = "0.4070", rfq_id: str = "rfq-1") -> dict:
    return {
        "id": quote_id,
        "rfq_id": rfq_id,
        "creator_id": f"maker-{quote_id}",
        "rfq_creator_id": "joe-account",
        "rfq_creator_user_id": "joe-user",
        "market_ticker": TICKER,
        "yes_bid_dollars": yes_bid,
        "no_bid_dollars": no_bid,
        "no_contracts_fp": "8.00",
        "contracts_fp": "8.00",
        "status": "open",
        "created_ts": "2026-09-22T04:00:00.000000Z",
        "updated_ts": "2026-09-22T04:00:00.000000Z",
    }


class FakeVenue:
    """Records every call in order; on DELETE, records whether the capture
    file already existed -- the one ordering the instrument exists to keep."""

    def __init__(self, *, held: dict[str, str], open_rfqs=(), quotes=(), out_path: Path,
                 ours_already_open: bool = False):
        self.held = held
        self.open_rfqs = list(open_rfqs)
        #: The venue's one-live-RFQ-per-requester rule: the create answers 409.
        self.ours_already_open = ours_already_open
        self.quotes = list(quotes)
        self.out_path = out_path
        self.calls: list[tuple] = []
        self.capture_existed_at_delete: bool | None = None

    async def positions(self):
        self.calls.append(("positions",))
        return [{"ticker": t, "position_fp": fp} for t, fp in self.held.items()]

    async def get(self, path, **params):
        self.calls.append(("GET", path, params))
        assert path == f"/markets/{TICKER}", path
        return {"market": {"ticker": TICKER, "mve_collection_ticker": COLLECTION, "mve_selected_legs": LEGS}}

    async def request(self, method, path, *, params=None, json_body=None):
        self.calls.append((method, path, params, json_body))
        if method == "GET" and path == "/communications/rfqs":
            return {"rfqs": self.open_rfqs}
        if method == "GET" and path == "/communications/rfqs/rfq-1":
            return {"rfq": {"id": "rfq-1", "market_ticker": TICKER, "status": "open"}}
        if method == "POST" and path == "/communications/rfqs":
            if self.ours_already_open:
                raise RuntimeError('HTTP 409 {"error":{"code":"already_exists"}}')
            return {"rfq": {"id": "rfq-1"}}
        if method == "GET" and path == "/communications/quotes":
            return {"quotes": list(self.quotes)}
        if method == "DELETE":
            self.capture_existed_at_delete = self.out_path.exists()
            self.quotes = []
            return {}
        raise AssertionError(f"unexpected call {method} {path}")


async def _no_sleep(_s):
    return None


def _clock(ticks):
    it = iter(ticks)

    def clock():
        return next(it)

    return clock


class TestTheScriptNeverReachesTheAcceptPath:
    def test_source_never_names_accept_quote_or_the_accept_endpoint(self):
        source = SCRIPT.read_text(encoding="utf-8")
        body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert "accept_quote" not in body, "the capture instrument imported or named the spend"
        assert "/accept" not in body
        assert "accepted_side" not in body

    def test_the_only_venue_writes_are_one_create_and_one_delete(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={TICKER: "8.226"}, quotes=[_quote("q1", yes_bid="0.0760")], out_path=out)
        import asyncio

        asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep, clock=_clock([0, 0, 10])))
        writes = [c for c in venue.calls if c[0] in ("POST", "DELETE", "PUT", "PATCH")]
        assert [(c[0], c[1]) for c in writes] == [
            ("POST", "/communications/rfqs"),
            ("DELETE", "/communications/rfqs/rfq-1"),
        ], writes


class TestTheSizeIsFlooredFromTheHolding:
    @pytest.mark.parametrize("fp,expected", [("8.226", 8), ("8.999", 8), ("60.97", 60), ("9.21", 9), ("1.00", 1)])
    def test_position_fp_floors(self, mod, fp, expected):
        assert mod.floor_contracts(fp) == expected

    def test_the_create_body_carries_the_floored_count_and_no_dollar_target(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={TICKER: "8.226"}, quotes=[], out_path=out)
        import asyncio

        asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep, clock=_clock([0, 10])))
        post = next(c for c in venue.calls if c[0] == "POST")
        body = post[3]
        assert body["contracts"] == 8, body
        assert "target_cost_dollars" not in body, body
        assert body["rest_remainder"] is False
        assert body["mve_collection_ticker"] == COLLECTION
        assert body["mve_selected_legs"] == LEGS
        assert post[2] == {"exchange_index": 1}, "every RFQ write names the combinations shard"

    def test_a_holding_under_one_contract_refuses_before_any_write(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={TICKER: "0.27"}, out_path=out)
        import asyncio

        with pytest.raises(mod.Refused, match="floors to 0"):
            asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep))
        assert not any(c[0] == "POST" for c in venue.calls)
        assert not out.exists()

    def test_unreadable_position_fp_refuses_rather_than_reading_zero(self, mod):
        with pytest.raises(mod.Refused):
            mod.floor_contracts("eight")


class TestTheCaptureIsOnDiskBeforeTheDelete:
    def test_delete_sees_the_file_already_written(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={TICKER: "8.226"}, quotes=[_quote("q1", yes_bid="0.0760"), _quote("q2", yes_bid="0.0000")], out_path=out)
        import asyncio

        capture = asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep, clock=_clock([0, 0, 0, 10])))
        assert venue.capture_existed_at_delete is True, venue.calls
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        assert on_disk["deleted"] is True
        assert on_disk["accepted"] is False
        assert len(on_disk["quote_reads"]) == 2
        # Every raw payload is kept verbatim, including the field the buy
        # path parses and discards.
        assert on_disk["quote_reads"][0]["payload"]["quotes"][0]["yes_bid_dollars"] == "0.0760"
        assert capture["summary"] == {
            "quotes_seen": 2,
            "quotes_with_yes_bid": 1,
            "best_yes_bid_tenths": 76,
            "refused_finer_than_tenths": 0,
            "refused_unreadable": 0,
            "reads": 2,
        }

    def test_the_delete_still_happens_when_a_read_raises(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={TICKER: "8.226"}, out_path=out)
        original = venue.request

        async def flaky(method, path, *, params=None, json_body=None):
            if method == "GET" and path == "/communications/quotes":
                venue.calls.append((method, path, params, json_body))
                raise RuntimeError("socket")
            return await original(method, path, params=params, json_body=json_body)

        venue.request = flaky
        import asyncio

        asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep, clock=_clock([0, 0, 10])))
        assert venue.capture_existed_at_delete is True
        on_disk = json.loads(out.read_text(encoding="utf-8"))
        assert "error" in on_disk["quote_reads"][0]
        assert on_disk["summary"]["reads"] == 0


class TestRefusalsHappenBeforeAnyVenueCall:
    def test_an_existing_capture_path_refuses_before_positions_are_read(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        out.write_text("{}", encoding="utf-8")
        venue = FakeVenue(held={TICKER: "8.226"}, out_path=out)
        import asyncio

        with pytest.raises(mod.Refused, match="refusing to overwrite"):
            asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep))
        assert venue.calls == []
        assert out.read_text(encoding="utf-8") == "{}"

    def test_an_unheld_ticker_refuses_before_create(self, mod, tmp_path):
        out = tmp_path / "cap.json"
        venue = FakeVenue(held={"KXMVE-OTHER": "5.00"}, out_path=out)
        import asyncio

        with pytest.raises(mod.Refused, match="not among the account's open positions"):
            asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep))
        assert not any(c[0] == "POST" for c in venue.calls)
        assert not out.exists()

    def test_an_already_open_rfq_of_ours_refuses_and_is_not_deleted(self, mod, tmp_path):
        """`create_rfq` would silently reuse it (#96 defect 4); this instrument
        must neither read quotes priced for another ask nor destroy quotes a
        tab may be holding open. "Ours" is the venue's 409, not the list."""
        out = tmp_path / "cap.json"
        venue = FakeVenue(
            held={TICKER: "8.226"},
            open_rfqs=[{"id": "rfq-old", "market_ticker": TICKER, "status": "open", "target_cost_dollars": "5.0000"}],
            out_path=out,
            ours_already_open=True,
        )
        import asyncio

        with pytest.raises(mod.Refused, match="already open"):
            asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep))
        assert not any(c[0] == "DELETE" for c in venue.calls), venue.calls
        assert not any(c[1:2] == ("/communications/quotes",) for c in venue.calls), venue.calls
        assert not out.exists()


class TestAStrangersOpenRfqDoesNotBlockTheAsk:
    def test_open_rfqs_in_the_market_list_are_not_read_as_ours(self, mod, tmp_path):
        """Measured 2026-09-24: `GET /communications/rfqs?market_ticker=` lists
        EVERY requester's RFQs, `creator_id` blank on all, and a pre-check on
        it refused all three held combinations. Only the create's 409 means
        ours -- so a list full of strangers' open RFQs must not stop the ask."""
        out = tmp_path / "cap.json"
        strangers = [
            {"id": f"rfq-stranger-{i}", "market_ticker": TICKER, "status": "open",
             "creator_id": "", "target_cost_dollars": "10.0000"}
            for i in range(3)
        ]
        venue = FakeVenue(held={TICKER: "8.226"}, open_rfqs=strangers,
                          quotes=[_quote("q1", yes_bid="0.0760")], out_path=out)
        import asyncio

        capture = asyncio.run(mod.capture_one(venue, TICKER, out, now_ms=1, sleep=_no_sleep, clock=_clock([0, 0, 10])))
        assert capture["rfq"] == {"id": "rfq-1", "reused": False, "target_cost_dollars": None}
        assert capture["rfq_row"]["rfq"]["id"] == "rfq-1"
        assert capture["summary"]["quotes_with_yes_bid"] == 1
        assert venue.capture_existed_at_delete is True


class TestTheRedactionKeepsTheWireAndDropsTheIdentities:
    def _capture(self, quotes, *, reused=False):
        return {
            "rfq": {"id": "rfq-1", "reused": reused, "target_cost_dollars": None},
            "rfq_created_by": "POST /trade-api/v2/communications/rfqs?exchange_index=1",
            "rfq_request_body": {"market_ticker": TICKER, "contracts": 8},
            "quotes_endpoint": "GET /trade-api/v2/communications/quotes?rfq_user_filter=self&limit=500",
            "quote_reads": [
                {"read_ms": 1, "payload": {"quotes": quotes[:1]}},
                {"read_ms": 2, "payload": {"quotes": quotes}},
            ],
        }

    def test_prices_and_timestamps_are_verbatim_and_every_id_is_a_placeholder(self, mod):
        raw = [_quote("q1", yes_bid="0.0760"), _quote("q2", yes_bid="0.0470"), _quote("q3", yes_bid="0.0000", rfq_id="someone-elses")]
        fixture = mod.redact_to_fixture(self._capture(raw), note="test")
        assert [q["yes_bid_dollars"] for q in fixture["quotes"]] == ["0.0760", "0.0470"]
        assert fixture["quotes"][0]["created_ts"] == "2026-09-22T04:00:00.000000Z"
        for q in fixture["quotes"]:
            assert q["id"].endswith("_REDACTED")
            assert q["creator_id"].startswith("MAKER_")
            assert q["rfq_id"] == "RFQ_REDACTED"
            assert q["rfq_creator_id"] == "REQUESTER_REDACTED"
            assert q["rfq_creator_user_id"] == "REQUESTER_USER_REDACTED"
        assert fixture["sell_side"] is True
        assert fixture["redaction"] == mod.REDACTION_NOTE
        assert fixture["params"]["rfq_request_body"]["contracts"] == 8
        dumped = json.dumps(fixture)
        assert "joe-account" not in dumped and "joe-user" not in dumped and "maker-q1" not in dumped

    def test_the_same_maker_keeps_one_placeholder(self, mod):
        a = _quote("q1", yes_bid="0.0760")
        b = _quote("q2", yes_bid="0.0470")
        b["creator_id"] = a["creator_id"]
        fixture = mod.redact_to_fixture(self._capture([a, b]), note="test")
        assert fixture["quotes"][0]["creator_id"] == fixture["quotes"][1]["creator_id"]

    def test_a_reused_rfq_is_refused_as_fixture_material(self, mod):
        with pytest.raises(mod.Refused, match="reused"):
            mod.redact_to_fixture(self._capture([_quote("q1", yes_bid="0.0760")], reused=True), note="test")

    def test_a_capture_with_no_quotes_on_its_rfq_is_refused(self, mod):
        with pytest.raises(mod.Refused, match="no quotes"):
            mod.redact_to_fixture(self._capture([_quote("q9", yes_bid="0.01", rfq_id="other")]), note="test")


class TestTheCliRefusesBeforeTheVenue:
    def test_dry_run_names_the_path_and_touches_nothing(self, mod, tmp_path, capsys):
        code = mod.main(["--ticker", TICKER, "--capture", str(tmp_path), "--dry-run"])
        assert code == 0
        out = capsys.readouterr().out
        assert TICKER in out and "would ask" in out
        assert list(tmp_path.iterdir()) == []

    def test_fixture_mode_refuses_to_overwrite(self, mod, tmp_path):
        cap = tmp_path / "cap.json"
        cap.write_text(json.dumps({"rfq": {"id": "rfq-1"}, "quote_reads": []}), encoding="utf-8")
        out = tmp_path / "fixture.json"
        out.write_text("keep", encoding="utf-8")
        with pytest.raises(mod.Refused, match="refusing to overwrite"):
            mod.main(["--fixture", str(cap), str(out), "--note", "n"])
        assert out.read_text(encoding="utf-8") == "keep"
