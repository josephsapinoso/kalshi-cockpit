"""`docker-compose.home.yml` serves a copy and can spend, place or push nothing.

The home rehearsal copy reads its env from a file Joe writes by hand, most
likely by copying the laptop's `.env`. Every credential in that file would
switch a spending path back on, so the compose file blanks each one under
`environment:`, which compose applies over `env_file:`.

The credential list is derived from `.env.example` (the config contract), so
a credential added there later fails this test until the compose file blanks
it too.

What this does not establish: that Docker applies `environment:` over
`env_file:` (documented compose behaviour, not tested here), or that the
container boots. The entrypoint's own refusals are in
`tests/test_serve_only_rehearsal_holds_no_key.py`.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
COMPOSE = REPO / "docker-compose.home.yml"
CONTRACT = REPO / ".env.example"

# Names that look like credentials but are budgets or the login token the
# copy needs to serve pages at all.
NOT_CREDENTIALS = {
    "APP_AUTH_TOKEN",
    "AGENT_MAX_TOKENS_PER_DAY",
    "SCOUT_AUTO_TAP_TOKEN_SHARE",
}
CREDENTIAL = re.compile(r"^([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|WEBHOOK_URL|CHANNEL_ID|B64|KEY_PATH))=",
                        re.MULTILINE)


def _service() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]["cockpit"]


def _credentials() -> set[str]:
    names = set(CREDENTIAL.findall(CONTRACT.read_text(encoding="utf-8")))
    names.add("KALSHI_PRIVATE_KEY_B64")  # Fly secret; not in the contract file
    return names - NOT_CREDENTIALS


class TestTheHomeCopyIsServeOnly:
    def test_serve_only_and_public_read_are_set(self):
        env = _service()["environment"]
        assert env["SERVE_ONLY"] == "1"
        assert env["KALSHI_PUBLIC_READ_ONLY"] == "true"

    def test_every_credential_in_the_contract_is_blanked(self):
        env = _service()["environment"]
        creds = _credentials()
        assert "ANTHROPIC_API_KEY" in creds and "ODDS_API_KEY" in creds
        unblanked = sorted(c for c in creds if env.get(c, None) != "")
        assert not unblanked, (
            f"{unblanked} would pass through from .env.home onto the copy"
        )

    def test_the_order_paths_are_switched_off(self):
        env = _service()["environment"]
        assert env["MANUAL_ORDERS_ENABLED"] == "false"
        assert env["LIVE_TRADING_ENABLED"] == "false"

    def test_the_port_is_bound_to_loopback_only(self):
        # tailscale serve on the host reaches it; the LAN does not.
        assert _service()["ports"] == ["127.0.0.1:3000:3000"]

    def test_the_database_is_on_a_named_volume_not_a_windows_folder(self):
        (mount,) = _service()["volumes"]
        source = mount.split(":", 1)[0]
        assert re.fullmatch(r"[a-z_]+", source), mount
