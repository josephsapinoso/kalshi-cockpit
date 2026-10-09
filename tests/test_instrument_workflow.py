"""`.github/workflows/instrument.yml` runs only fixed, counts-only commands,
each naming a script the image ships.

What this establishes: every `python /app/scripts/<name>.py` in the workflow
is allowlisted in `.dockerignore` (so it exists on the box), the command set
is exactly the one agreed, the write needs the typed app name, and the file
takes no free-text command input.
What it does not establish: that the Fly token in the repository's secrets
may open an ssh console (the first `health` run on live answers that).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "instrument.yml"
DOCKERIGNORE = ROOT / ".dockerignore"

AGREED = {
    "health": "python /app/scripts/fetch_live_route.py /api/health",
    "bets-summary": "python /app/scripts/fetch_live_bets_summary.py",
    "backfill-leg-prices-dry-run": (
        "python /app/scripts/backfill_leg_prices.py --db /data/cockpit.db --dry-run --limit 400"
    ),
    "backfill-leg-prices-commit": (
        "python /app/scripts/backfill_leg_prices.py --db /data/cockpit.db --commit --limit 400"
    ),
}


def _text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _commands() -> dict[str, str]:
    found = {}
    for match in re.finditer(r"^\s+([a-z-]+)\)\n\s+cmd=\"([^\"]+)\"", _text(), re.M):
        found[match.group(1)] = match.group(2)
    return found


class TestTheCommandsAreFixed:
    def test_the_command_set_is_exactly_the_agreed_one(self):
        assert _commands() == AGREED

    def test_every_script_named_is_shipped_by_the_image(self):
        allow = {
            line.strip()[len("!scripts/"):]
            for line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("!scripts/")
        }
        for cmd in AGREED.values():
            script = re.search(r"/app/scripts/([a-z_]+\.py)", cmd).group(1)
            assert script in allow or any(
                a.endswith("*.py") and script.startswith(a[:-4]) for a in allow
            ), f"{script} is not in .dockerignore's allowlist"

    def test_the_choice_list_matches_the_commands(self):
        options = re.search(r"options:\n((?:\s+- [a-z-]+\n)+)", _text()).group(1)
        listed = set(re.findall(r"- ([a-z-]+)", options)) - {"choose-one"}
        assert listed == set(AGREED)

    def test_no_free_text_command_input_exists(self):
        text = _text()
        assert "type: string" in text  # confirm_live only
        assert text.count("type: string") == 1
        assert "inputs.command" not in text and "inputs.script" not in text


class TestTheWriteIsGuarded:
    def test_the_commit_instrument_needs_the_typed_app_name(self):
        text = _text()
        guard = text.index("Guard the write")
        assert "inputs.instrument == 'backfill-leg-prices-commit'" in text[guard:guard + 400]
        assert "!= \"kalshi-cockpit\"" in text[guard:guard + 700]

    def test_only_the_commit_instrument_writes(self):
        for name, cmd in AGREED.items():
            if name == "backfill-leg-prices-commit":
                assert "--commit" in cmd
            else:
                assert "--commit" not in cmd
