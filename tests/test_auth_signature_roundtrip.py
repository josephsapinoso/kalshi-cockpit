"""Round-trip verification of the Kalshi request signer.

``KalshiAuth._sign`` produces the RSA-PSS signature that authenticates
real-money orders. Its only previous coverage asserted the signature header was
*truthy* (``tests/test_rest.py::test_auth_headers_are_present_on_every_request``),
and a base64 blob comes back whether the padding, the hash, the salt length and
the signed message are right or wrong. That test would have survived the
deletion of the thing it guards.

Here the signature is verified with the **public** half of a throwaway key,
using parameters written down from Kalshi's documented algorithm rather than
read back out of ``auth.py``:

    RSA-PSS, MGF1(SHA-256), salt = the maximum for the modulus, digest SHA-256
    message = {timestamp_ms}{HTTP_METHOD}{path}, concatenated, no separators
    signature base64-encoded

Sources for those parameters, both independent of the implementation:
``.claude/skills/kalshi-api/SKILL.md`` ("Authentication: RSA-PSS, not ED25519" —
algorithm, message layout, and the header table saying the timestamp is the same
**milliseconds** used in the message) and the empirical findings recorded in the
``auth.py`` module docstring. The salt length is computed here from RFC 8017
§9.1.1 (``sLen = emLen - hLen - 2``), not copied from the implementation's
``PSS.MAX_LENGTH`` constant, so that a change to the signer's salt length turns
these red instead of being fed straight back into the verifier.

A round-trip is the right shape because the expected value is fixed by
definition rather than by reasoning: either the counterpart key verifies the
bytes or it does not.

WHAT THIS HARNESS DOES NOT ESTABLISH

- **That Kalshi accepts the signature.** Only the exchange can say that. The
  live checks are ``scripts/verify_auth.py`` and a 200 on a signed request; a
  401 there is indistinguishable from bad credentials.
- **Anything about the production key.** Every key here is generated in-process
  and thrown away. The real key is a Fly secret and is never read, echoed or
  logged — by this file or anything it imports.
- **That the path handed to the signer is the right path.** ``signed_path``'s
  prefix derivation and the query-string rule are pinned in
  ``tests/test_rest.py::TestSigningContract``.
- **Anything about clock skew or replay.** How stale a timestamp may be before
  the venue rejects it is unmeasured, and nothing here rate-limits reuse.
- **That an ED25519 or non-RSA key is refused.** ``_load_private_key`` does not
  check the key type; that gap is reported, not fixed, by this file.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa

from backend.kalshi import auth as auth_module
from backend.kalshi.auth import KalshiAuth

KEY_SIZE_BITS = 2048
SHA256_DIGEST_BYTES = 32

API_KEY_ID = "test-key-id"
PATH = "/trade-api/v2/portfolio/balance"
OTHER_PATH = "/trade-api/v2/portfolio/orders"
WS_PATH = "/trade-api/ws/v2"

# A fixed wall clock, so the expected message can be written out in full.
# int(1756000000.123456 * 1000) == 1756000000123.
FIXED_EPOCH_SECONDS = 1_756_000_000.123456
FIXED_TIMESTAMP_MS = "1756000000123"


def _max_salt_bytes(key_size_bits: int, digest_bytes: int = SHA256_DIGEST_BYTES) -> int:
    """The largest PSS salt a modulus of this size admits, per RFC 8017 §9.1.1.

    ``emBits = modBits - 1``; ``emLen = ceil(emBits / 8)``; the salt may run to
    ``emLen - hLen - 2``. Written out here rather than passed through as
    ``PSS.MAX_LENGTH`` so the verifier does not inherit the signer's choice.
    """
    em_len = ((key_size_bits - 1) + 7) // 8
    return em_len - digest_bytes - 2


def _verify(public_key, signature_b64: str, message: str) -> None:
    """Verify under Kalshi's documented algorithm. Raises InvalidSignature."""
    public_key.verify(
        base64.b64decode(signature_b64),
        message.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=_max_salt_bytes(public_key.key_size),
        ),
        hashes.SHA256(),
    )


@pytest.fixture(scope="module")
def keypair(tmp_path_factory):
    """A throwaway RSA key written to a temp file, plus its public half.

    Deliberately local rather than in the root ``conftest.py``: nothing outside
    this file uses it, and the repo's rule is about *shared* fixtures. 2048 bits
    because that is what a real Kalshi key is, and because the maximum salt
    length depends on the modulus size.
    """
    private = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE_BITS)
    path = tmp_path_factory.mktemp("signing") / "throwaway.pem"
    path.write_bytes(
        private.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return SimpleNamespace(path=path, public=private.public_key())


@pytest.fixture
def signer(keypair):
    return KalshiAuth(API_KEY_ID, keypair.path)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin the wall clock so the signed message is known exactly.

    Replaces the module's ``time`` reference rather than patching the stdlib
    module in place, so nothing else in the run sees a stopped clock.
    """
    monkeypatch.setattr(
        auth_module, "time", SimpleNamespace(time=lambda: FIXED_EPOCH_SECONDS)
    )


def _signature(headers: dict[str, str]) -> str:
    return headers["KALSHI-ACCESS-SIGNATURE"]


class TestTheSignatureIsAVerifiableRsaPssSignature:
    """The counterpart public key accepts it under the documented parameters.

    Every assertion here fails if the padding scheme, the MGF hash, the digest
    or the salt length moves — which "the header is truthy" could not see.
    """

    def test_a_rest_signature_verifies_under_the_documented_algorithm(
        self, signer, keypair, frozen_clock
    ):
        headers = signer.get_rest_headers("GET", PATH)
        _verify(
            keypair.public,
            _signature(headers),
            f"{FIXED_TIMESTAMP_MS}GET{PATH}",
        )

    def test_the_verifier_rejects_a_tampered_signature(
        self, signer, keypair, frozen_clock
    ):
        """The control. Without it the round-trip could be vacuously green."""
        raw = bytearray(base64.b64decode(_signature(signer.get_rest_headers("GET", PATH))))
        raw[-1] ^= 0x01
        with pytest.raises(InvalidSignature):
            _verify(
                keypair.public,
                base64.b64encode(bytes(raw)).decode("ascii"),
                f"{FIXED_TIMESTAMP_MS}GET{PATH}",
            )

    def test_the_salt_is_the_maximum_for_the_modulus_not_the_digest_length(
        self, signer, keypair, frozen_clock
    ):
        """PSS salt length is a free parameter and the two plausible choices —
        max, and the digest's 32 bytes — produce signatures that do not verify
        against each other. Kalshi's is the maximum."""
        signature = base64.b64decode(_signature(signer.get_rest_headers("GET", PATH)))
        message = f"{FIXED_TIMESTAMP_MS}GET{PATH}".encode("utf-8")
        with pytest.raises(InvalidSignature):
            keypair.public.verify(
                signature,
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=SHA256_DIGEST_BYTES,
                ),
                hashes.SHA256(),
            )

    def test_the_padding_is_pss_not_pkcs1v15(self, signer, keypair, frozen_clock):
        """The other RSA padding a signer could plausibly have been given."""
        signature = base64.b64decode(_signature(signer.get_rest_headers("GET", PATH)))
        with pytest.raises(InvalidSignature):
            keypair.public.verify(
                signature,
                f"{FIXED_TIMESTAMP_MS}GET{PATH}".encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )

    def test_two_signatures_of_the_same_message_differ(
        self, signer, keypair, frozen_clock
    ):
        """PSS salts randomly; PKCS1v15 is deterministic. Identical bytes twice
        over the same message would mean the padding is not PSS at all."""
        first = _signature(signer.get_rest_headers("GET", PATH))
        second = _signature(signer.get_rest_headers("GET", PATH))
        assert first != second

    def test_the_header_is_base64_of_exactly_one_modulus_of_bytes(
        self, signer, frozen_clock
    ):
        """An RSA signature is the size of the key. A truncated or re-encoded
        header would be a 401 at the venue and nothing else here would notice."""
        raw = base64.b64decode(_signature(signer.get_rest_headers("GET", PATH)), validate=True)
        assert len(raw) == KEY_SIZE_BITS // 8


class TestTheSignedMessageIsTimestampThenMethodThenPath:
    """Composition, which is the property an attacker-facing signer needs.

    A signature that verifies is worth nothing if it verifies for a request the
    caller did not make. Each test below moves exactly one component.
    """

    def test_the_three_parts_are_joined_with_no_separators(
        self, signer, keypair, frozen_clock
    ):
        headers = signer.get_rest_headers("POST", PATH)
        with pytest.raises(InvalidSignature):
            _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS} POST {PATH}")
        _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}POST{PATH}")

    def test_a_signature_for_one_path_does_not_verify_for_another(
        self, signer, keypair, frozen_clock
    ):
        """Otherwise a signature captured off a balance read authenticates an
        order.

        Paired: the negative half alone is a tautology no signer mutation can
        falsify, because a wrong message never verifies either. The positive
        half is what makes this test able to go red.
        """
        headers = signer.get_rest_headers("GET", PATH)
        _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}GET{PATH}")
        with pytest.raises(InvalidSignature):
            _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}GET{OTHER_PATH}")

    def test_a_signature_for_one_method_does_not_verify_for_another(
        self, signer, keypair, frozen_clock
    ):
        """GET and POST on the same path must not share a signature. Paired
        with the positive for the same reason as the path test above."""
        headers = signer.get_rest_headers("GET", PATH)
        _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}GET{PATH}")
        with pytest.raises(InvalidSignature):
            _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}POST{PATH}")

    def test_a_signature_made_at_one_timestamp_does_not_verify_at_another(
        self, signer, keypair, frozen_clock
    ):
        """The timestamp is inside the signed bytes, which is what stops an old
        header being replayed with a fresh clock. Paired with the positive for
        the same reason as the path test above."""
        headers = signer.get_rest_headers("GET", PATH)
        _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}GET{PATH}")
        later = str(int(FIXED_TIMESTAMP_MS) + 1)
        with pytest.raises(InvalidSignature):
            _verify(keypair.public, _signature(headers), f"{later}GET{PATH}")

    @pytest.mark.parametrize(
        "dropped, message",
        [
            ("timestamp", f"GET{PATH}"),
            ("method", f"{FIXED_TIMESTAMP_MS}{PATH}"),
            ("path", f"{FIXED_TIMESTAMP_MS}GET"),
        ],
    )
    def test_no_component_may_be_missing_from_the_signed_message(
        self, signer, keypair, frozen_clock, dropped, message
    ):
        assert dropped in ("timestamp", "method", "path")  # names it in the test id
        headers = signer.get_rest_headers("GET", PATH)
        with pytest.raises(InvalidSignature):
            _verify(keypair.public, _signature(headers), message)

    def test_the_websocket_message_is_get_and_the_websocket_path(
        self, signer, keypair, frozen_clock
    ):
        """The WS handshake signs a literal GET against the ws path — there is
        no request method to read off, so a wrong literal here is a connection
        that never opens."""
        headers = signer.get_ws_headers()
        _verify(keypair.public, _signature(headers), f"{FIXED_TIMESTAMP_MS}GET{WS_PATH}")

    def test_the_websocket_path_is_signed_as_given(self, signer, keypair, frozen_clock):
        """The argument is honoured rather than a hardcoded default winning."""
        headers = signer.get_ws_headers("/trade-api/ws/v3")
        _verify(
            keypair.public,
            _signature(headers),
            f"{FIXED_TIMESTAMP_MS}GET/trade-api/ws/v3",
        )


class TestTheHeadersCarryWhatTheApiNeeds:
    """Three headers, and the timestamp in the units Kalshi reads."""

    def test_the_timestamp_header_is_milliseconds_not_seconds(
        self, signer, frozen_clock
    ):
        """Milliseconds, established two ways: the skill file's header table
        says "the same milliseconds used in the message", and the source builds
        it as ``int(time.time() * 1000)``. Seconds would be a 10-digit number
        roughly 1000x too small, which is what this pins."""
        stamp = signer.get_rest_headers("GET", PATH)["KALSHI-ACCESS-TIMESTAMP"]
        assert stamp == FIXED_TIMESTAMP_MS
        assert len(stamp) == 13
        assert int(stamp) // 1000 == int(FIXED_EPOCH_SECONDS)

    def test_the_timestamp_sent_is_the_timestamp_that_was_signed(
        self, signer, keypair
    ):
        """No frozen clock: the header and the signed message must agree even
        when the clock is read live. If the signer read the clock twice, this is
        the only test in the repo that would catch it — and the venue would
        answer 401 with no other clue."""
        headers = signer.get_rest_headers("DELETE", OTHER_PATH)
        stamp = headers["KALSHI-ACCESS-TIMESTAMP"]
        _verify(keypair.public, _signature(headers), f"{stamp}DELETE{OTHER_PATH}")

    def test_the_key_id_is_sent_verbatim_as_the_access_key(self, signer, frozen_clock):
        assert signer.get_rest_headers("GET", PATH)["KALSHI-ACCESS-KEY"] == API_KEY_ID

    def test_rest_requests_declare_a_json_body_and_websocket_ones_do_not(
        self, signer, frozen_clock
    ):
        rest = signer.get_rest_headers("GET", PATH)
        assert rest["Content-Type"] == "application/json"
        assert set(signer.get_ws_headers()) == {
            "KALSHI-ACCESS-KEY",
            "KALSHI-ACCESS-SIGNATURE",
            "KALSHI-ACCESS-TIMESTAMP",
        }


class TestTheKeyMustBeRsaAtLoadTime:
    """The refusal that turns an afternoon into one line.

    `backend/kalshi/auth.py`'s module docstring names this as the expensive
    failure: "It is RSA-PSS, not ED25519 [...] Anyone who generates an ED25519
    key will fail to authenticate with errors that look like bad credentials."
    The old repo's README claimed ED25519 for most of its life while the code
    did RSA-PSS, so this is a mistake someone has actually made.

    `_load_private_key` is annotated `-> rsa.RSAPrivateKey`, and an annotation
    is a claim rather than a check: before 2026-09-09 an ED25519 key loaded
    without complaint and died much later inside `.sign()` with a padding
    `TypeError`, at a call site with nothing to do with key material.

    Not established here: that Kalshi accepts any key this class loads. Only
    the exchange can say that.
    """

    def _write(self, tmp_path, key):
        path = tmp_path / "wrong_type.pem"
        path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return path

    def test_an_ed25519_key_is_refused_at_load_rather_than_at_sign(self, tmp_path):
        path = self._write(tmp_path, ed25519.Ed25519PrivateKey.generate())
        with pytest.raises(TypeError) as exc:
            KalshiAuth(API_KEY_ID, path)
        assert "not an RSA key" in str(exc.value)

    def test_an_ec_key_is_refused_too(self, tmp_path):
        """The guard is about the algorithm family, not about ED25519 alone."""
        path = self._write(tmp_path, ec.generate_private_key(ec.SECP256R1()))
        with pytest.raises(TypeError):
            KalshiAuth(API_KEY_ID, path)

    def test_the_refusal_names_the_file_and_the_type_it_found(self, tmp_path):
        """A message saying only "wrong key type" sends the reader to the code.

        Naming the path and the actual class sends them to the key instead,
        which is where the mistake is.
        """
        path = self._write(tmp_path, ed25519.Ed25519PrivateKey.generate())
        with pytest.raises(TypeError) as exc:
            KalshiAuth(API_KEY_ID, path)
        message = str(exc.value)
        assert str(path) in message
        assert "Ed25519" in message

    def test_a_real_rsa_key_still_loads(self, keypair):
        """Otherwise the guard above could pass by refusing everything."""
        assert KalshiAuth(API_KEY_ID, keypair.path).private_key is not None
