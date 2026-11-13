"""`docker-compose.live-home.yml` is the whole live desk for the home desktop (#451).

Dormant until cutover day (epic #449). It must boot exactly what Fly's machine
boots, take every non-secret setting from the file generated off
`fly.live.toml` (#450), keep secrets in a gitignored file, and never be
confused with the serve-only rehearsal file.

What this does not establish
-----------------------------
- That the container boots or the recorder runs on the desktop. Docker is not
  run here; this reads the compose file and the entrypoint as text.
- That Docker applies `environment:` over `env_file:` (documented compose
  behaviour) or reads `env_file:` entries in order (likewise).
- That two recorders cannot run at once. That is #459's guard.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
LIVE = REPO / "docker-compose.live-home.yml"
REHEARSAL = REPO / "docker-compose.home.yml"
GENERATED = REPO / "deploy" / "home" / "live.env.example"
ENTRYPOINT = REPO / "docker" / "entrypoint.sh"


def _service(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["services"]["cockpit"]


def _generated() -> dict[str, str]:
    out = {}
    for line in GENERATED.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key] = value
    return out


class TestItIsTheWholeDesk:
    def test_serve_only_is_off(self):
        assert _service(LIVE)["environment"] == {"SERVE_ONLY": "0"}

    def test_the_generated_settings_say_live(self):
        assert _generated()["INSTANCE_MODE"] == "live"

    def test_the_entrypoint_starts_the_recorder_when_serve_only_is_off(self):
        text = ENTRYPOINT.read_text(encoding="utf-8")
        assert 'if [ "${SERVE_ONLY}" = "1" ]; then' in text
        assert "python scripts/run_loop.py" in text

    def test_no_credential_is_blanked(self):
        # The rehearsal file blanks every key; the live one must blank none,
        # or the desk would boot with no Kalshi key and refuse.
        env = _service(LIVE)["environment"]
        assert not any(v == "" for v in env.values())


class TestSettingsComeFromFly:
    def test_generated_file_first_then_secrets(self):
        assert _service(LIVE)["env_file"] == [
            "deploy/home/live.env.example",
            ".env.live-home",
        ]

    def test_nothing_the_generated_file_sets_is_overridden(self):
        overridden = set(_service(LIVE)["environment"]) & set(_generated())
        assert not overridden, overridden

    def test_the_secrets_file_is_gitignored(self):
        result = subprocess.run(
            ["git", "check-ignore", "-q", ".env.live-home"], cwd=REPO
        )
        assert result.returncode == 0


class TestItIsReachableOnlyOverTheTailnet:
    def test_bound_to_loopback(self):
        assert _service(LIVE)["ports"] == ["127.0.0.1:3000:3000"]

    def test_never_mentions_funnel(self):
        text = "\n".join(
            line for line in LIVE.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "funnel" not in text.lower()


class TestItCannotBeConfusedWithTheRehearsal:
    def test_its_own_volume(self):
        live = _service(LIVE)["volumes"][0].split(":")[0]
        rehearsal = _service(REHEARSAL)["volumes"][0].split(":")[0]
        assert live != rehearsal

    def test_its_own_image_tag(self):
        assert _service(LIVE)["image"] != _service(REHEARSAL)["image"]

    def test_the_rehearsal_still_serves_only(self):
        assert _service(REHEARSAL)["environment"]["SERVE_ONLY"] == "1"


class TestTheBuildNamesItsCommit:
    def test_git_sha_is_required_at_build(self):
        arg = _service(LIVE)["build"]["args"]["GIT_SHA"]
        assert arg.startswith("${GIT_SHA:?"), arg

    def test_restarts_itself(self):
        assert _service(LIVE)["restart"] == "unless-stopped"
