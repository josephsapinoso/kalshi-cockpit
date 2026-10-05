"""#318: a create whose earlier attempt lost its answer is never "refused".

`KalshiRestClient.request` retries POSTs after a transport error, a 429 or a
5xx, so the status a caller finally sees describes only the LAST attempt. If
an earlier attempt created the RFQ and its answer was lost, the retry meets a
4xx (`already_exists`, or anything else) that proves nothing about the first.

What these tests establish: `request` marks a final error that followed a
lost answer (transport or 5xx) and does not mark one that followed only a
429; `create_rfq` turns every such error, and both `already_exists` branches
that cannot prove the open RFQ is someone else's, into `RfqOutcomeUnknown`.

What they do not establish
--------------------------
- **Nothing about a 429 body.** The 409 is real: `_ALREADY` is the body
  captured 2026-10-05 (`tests/fixtures/rfq_create_conflict_409.json`, n = 1).
  No RFQ-create 429 has been captured, and the detection is a substring
  match, so a change in the venue's wording would not be caught here.
- **Nothing about how often a create loses its answer.** These are
  constructed sequences, not observations.
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from backend.config import KalshiConfig
from backend.kalshi.rest import KalshiAPIError, KalshiRestClient
from backend.kalshi.rfq import RfqOutcomeUnknown, RfqRefused, create_rfq

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "rfq_create_conflict_409.json")
    .read_text(encoding="utf-8")
)
_ALREADY = _FIXTURE["body"]
_LEGS = [{"market_ticker": "L", "side": "yes"}]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A real `KalshiRestClient` over a scripted transport, no backoff wait."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = tmp_path / "key.pem"
    key.write_bytes(
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    async def _no_wait(_delay):
        return None

    monkeypatch.setattr("backend.kalshi.rest.asyncio.sleep", _no_wait)

    def _make(script):
        """`script` is a list: an exception to raise, or (status, body)."""
        steps = list(script)

        def handler(request):
            step = steps.pop(0)
            if isinstance(step, Exception):
                raise step
            status, body = step
            return httpx.Response(status, text=body)

        config = KalshiConfig(
            api_key="test-key",
            private_key_path=key,
            rest_url="https://api.elections.kalshi.com/trade-api/v2",
            ws_url="wss://example.invalid",
        )
        return KalshiRestClient(
            config,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    return _make


class TestTheClientRemembersALostAnswer:
    async def test_a_400_after_a_timeout_is_marked(self, client):
        api = client([httpx.ReadTimeout("lost"), (400, "bad")])
        with pytest.raises(KalshiAPIError) as got:
            await api.request("POST", "/communications/rfqs", json_body={})
        assert got.value.status_code == 400
        assert got.value.earlier_attempt_lost is True

    async def test_a_400_after_a_503_is_marked(self, client):
        api = client([(503, "down"), (400, "bad")])
        with pytest.raises(KalshiAPIError) as got:
            await api.request("POST", "/communications/rfqs", json_body={})
        assert got.value.earlier_attempt_lost is True

    async def test_a_400_after_only_a_429_is_not_marked(self, client):
        """Rate-limited means not processed: nothing was lost."""
        api = client([(429, "slow down"), (400, "bad")])
        with pytest.raises(KalshiAPIError) as got:
            await api.request("POST", "/communications/rfqs", json_body={})
        assert got.value.earlier_attempt_lost is False

    async def test_a_first_attempt_400_is_not_marked(self, client):
        api = client([(400, "bad")])
        with pytest.raises(KalshiAPIError) as got:
            await api.request("POST", "/communications/rfqs", json_body={})
        assert got.value.earlier_attempt_lost is False


class TestCreateAfterALostAnswer:
    async def test_a_plain_4xx_after_a_timeout_is_unknown(self, client):
        api = client([httpx.ReadTimeout("lost"), (400, "bad")])
        with pytest.raises(RfqOutcomeUnknown):
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                target_cost_dollars="5.0000",
            )

    async def test_a_first_attempt_4xx_is_still_a_refusal(self, client):
        api = client([(400, "bad")])
        with pytest.raises(RfqRefused) as got:
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                target_cost_dollars="5.0000",
            )
        assert not isinstance(got.value, RfqOutcomeUnknown)

    async def test_a_sized_ask_meeting_its_own_lost_create_is_unknown(
        self, client
    ):
        """The exit path: the open RFQ is most likely THIS ask, not another
        size -- so it must not say "Nothing was asked"."""
        api = client([httpx.ReadTimeout("lost"), (409, _ALREADY)])
        with pytest.raises(RfqOutcomeUnknown):
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                contracts_fp="2.01",
            )

    async def test_a_sized_ask_meeting_another_open_one_is_still_refused(
        self, client
    ):
        api = client([(409, _ALREADY)])
        with pytest.raises(RfqRefused, match="another size") as got:
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                contracts_fp="2.01",
            )
        assert not isinstance(got.value, RfqOutcomeUnknown)

    async def test_a_priced_ask_whose_open_rfq_cannot_be_proven_ours_is_unknown(
        self, client
    ):
        """`open_rfq_for` finds nothing of ours on the list (an empty list
        here), so the open RFQ cannot be named -- unknown after a lost
        attempt, a plain refusal without one."""
        api = client([
            httpx.ReadTimeout("lost"), (409, _ALREADY),
            (200, '{"rfqs": []}'),
        ])
        with pytest.raises(RfqOutcomeUnknown):
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                target_cost_dollars="5.0000",
            )


class TestTheCapturedConflict:
    """The venue's real reply to a second create, captured 2026-10-05."""

    def test_the_capture_is_a_409_naming_already_exists(self):
        assert _FIXTURE["status_code"] == 409
        assert json.loads(_ALREADY)["error"]["code"] == "already_exists"

    async def test_the_captured_reply_reaches_the_already_exists_branch(
        self, client
    ):
        """A first-attempt 409 on a sized ask is the refusal that names
        another size -- not the generic "would not create" text, which is
        what a body the substring missed would produce."""
        api = client([(_FIXTURE["status_code"], _ALREADY)])
        with pytest.raises(RfqRefused, match="already_exists") as got:
            await create_rfq(
                api, market_ticker="T", collection_ticker="C", legs=_LEGS,
                contracts_fp="2.01",
            )
        assert "would not create" not in str(got.value)
        assert not isinstance(got.value, RfqOutcomeUnknown)


def test_the_capture_script_never_reaches_the_accept_path():
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts" / "capture_rfq_create_conflict.py"
    ).read_text(encoding="utf-8")
    assert "accept_quote" not in source and "/accept" not in source
