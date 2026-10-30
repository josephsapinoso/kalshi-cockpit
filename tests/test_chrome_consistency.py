"""#414 (town hall G): one Chip, Nav lights Games on /game, shell widths, copy.

Source-reading pins. Each guard is mutation-checked: disabling it must turn
its test red.
"""

from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"


def read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


class TestOneChip:
    def test_chip_component_is_44px_tall(self):
        src = read("components/Chip.tsx")
        assert '"inline-flex min-h-11 items-center' in src

    def test_three_callers_use_the_shared_chip(self):
        for rel in (
            "components/FilterBar.tsx",
            "components/GameScriptCard.tsx",
            "components/WindowPicker.tsx",
        ):
            src = read(rel)
            assert 'import Chip from "@/components/Chip";' in src, rel
            assert "<Chip" in src, rel

    def test_no_local_chip_definitions_remain(self):
        assert "function Chip(" not in read("components/FilterBar.tsx")
        assert "function FilterChip(" not in read("components/GameScriptCard.tsx")
        # WindowPicker's old squared link style is gone.
        assert "rounded border px-3 py-2" not in read("components/WindowPicker.tsx")


class TestNavLightsGamesOnGame:
    def test_game_path_lights_games(self):
        assert 'pathname.startsWith("/game/")' in read("components/Nav.tsx")


class TestShellWidth:
    def test_gate_and_playbook_use_shell_width(self):
        for rel in ("app/gate/page.tsx", "app/playbook/page.tsx"):
            src = read(rel)
            assert "SHELL_WIDTH" in src, rel
            assert "max-w-3xl" not in src, rel


class TestCopy:
    def test_card_lede_names_the_real_sizes(self):
        src = read("components/GameScriptCard.tsx")
        assert "two or three" not in src
        assert "3, 5 or 8" in src

    def test_gate_says_300_is_a_floor_not_proof(self):
        src = read("app/gate/page.tsx")
        assert "300 is a floor, not proof" in src
        assert "needed at least 861" in src
        assert "still ended unresolved at 1,000" in src

    def test_playbook_says_actionable_rows(self):
        src = read("app/playbook/page.tsx")
        assert 'label="Actionable rows"' in src
        assert 'label="Actionable"' not in src

    def test_playbook_diffs_are_not_red_green(self):
        src = read("app/playbook/page.tsx")
        assert 'text-negative">{render(change.from)}' not in src
        assert 'text-positive">{render(change.to)}' not in src
        assert "{render(change.from)}" in src and "{render(change.to)}" in src
