"""Every agent definition in `.claude/agents/` must actually parse.

**What this does not establish.** It does not check that the harness honours
any of these keys, that the named model exists, or that the agent gives good
answers. It checks one thing: that the YAML frontmatter is well-formed and
carries the fields an agent definition needs. That is worth a test because the
failure mode is silent -- a definition whose frontmatter does not parse does
not announce itself, it simply is not there when someone spawns it, which is
this repo's four-times-caught "built but never called" shape wearing a
different hat.

The specific defect that motivated this: an unquoted `: ` inside a
`description` value terminates the scalar and YAML rejects the mapping. It
looks completely normal to a reader and is invisible until the agent does not
load.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"

# `effort` is the frontmatter key that sets a subagent's reasoning effort,
# overriding the session level for that agent. The Agent tool has no
# spawn-time effort parameter, so this file is the only place it can be set.
VALID_EFFORT = {"low", "medium", "high", "xhigh", "max"}

REQUIRED_FIELDS = ("name", "description", "tools")


def _agent_files() -> list[Path]:
    return sorted(AGENTS_DIR.glob("*.md"))


def _frontmatter(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    assert raw.startswith("---\n"), f"{path.name} does not open with a frontmatter fence"
    parts = raw.split("---\n", 2)
    assert len(parts) >= 3, f"{path.name} has no closing frontmatter fence"
    return parts[1]


class TestEveryAgentDefinitionParses:
    def test_the_agents_directory_is_not_empty(self) -> None:
        # A passing suite over zero files would be decoration.
        assert _agent_files(), f"no agent definitions found under {AGENTS_DIR}"

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
    def test_frontmatter_is_well_formed_yaml(self, path: Path) -> None:
        try:
            parsed = yaml.safe_load(_frontmatter(path))
        except yaml.YAMLError as exc:  # pragma: no cover - message is the point
            pytest.fail(
                f"{path.name} frontmatter is not valid YAML, so this agent will "
                f"not load and nothing will say so:\n{exc}"
            )
        assert isinstance(parsed, dict), f"{path.name} frontmatter is not a mapping"

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
    def test_required_fields_are_present(self, path: Path) -> None:
        parsed = yaml.safe_load(_frontmatter(path))
        missing = [f for f in REQUIRED_FIELDS if not parsed.get(f)]
        assert not missing, f"{path.name} is missing {missing}"

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
    def test_name_matches_filename(self, path: Path) -> None:
        parsed = yaml.safe_load(_frontmatter(path))
        assert parsed["name"] == path.stem, (
            f"{path.name} declares name={parsed['name']!r}; the name is the "
            "address a spawn uses, so a mismatch is a spawn that finds nothing"
        )


class TestEffortIsSetDeliberately:
    """`effort` is optional to the harness and mandatory to us.

    Omitting it means the agent inherits the session level, which for a
    reviewer is fine and for a lookup agent silently spends opus-shaped effort
    on a grep. Requiring the key makes the choice visible in review.
    """

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
    def test_effort_is_declared_and_valid(self, path: Path) -> None:
        parsed = yaml.safe_load(_frontmatter(path))
        effort = parsed.get("effort")
        assert effort is not None, (
            f"{path.name} declares no effort level. Set one deliberately; "
            f"one of {sorted(VALID_EFFORT)}."
        )
        assert effort in VALID_EFFORT, (
            f"{path.name} declares effort={effort!r}, which is not one of "
            f"{sorted(VALID_EFFORT)}. An unrecognised value is ignored "
            "silently."
        )

    @pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
    def test_a_sonnet_agent_is_not_asking_for_high_effort(self, path: Path) -> None:
        """The cheap model paired with the expensive dial is a contradiction.

        Sonnet is chosen for lookup-shaped work whose answer a grep settles.
        If such an agent also asks for high effort, one of the two decisions
        was not made on purpose.
        """
        parsed = yaml.safe_load(_frontmatter(path))
        if parsed.get("model") != "sonnet":
            return
        assert parsed.get("effort") in {"low", "medium"}, (
            f"{path.name} runs on sonnet but asks for "
            f"effort={parsed.get('effort')!r}; pick one intent"
        )
