"""The home desk's non-secret settings are generated from fly.live.toml and never drift.

Does not establish that the secrets file is complete.
"""
from __future__ import annotations

import importlib.util
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOML = ROOT / "fly.live.toml"
COMMITTED = ROOT / "deploy" / "home" / "live.env.example"

_spec = importlib.util.spec_from_file_location(
    "home_env_from_fly", ROOT / "scripts" / "home_env_from_fly.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def _parse(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        k, _, v = line.partition("=")
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1]
        out[k] = v
    return out


def _scratch(tmp_path: Path, env_lines: str) -> Path:
    p = tmp_path / "fly.toml"
    p.write_text('app = "x"\n[env]\n' + env_lines, encoding="utf-8")
    return p


class TestHomeEnvMatchesFlyLive:
    def test_committed_file_equals_fresh_generation(self):
        assert COMMITTED.read_bytes().decode() == gen.generate(TOML)

    def test_every_env_key_present_with_same_value(self):
        env = tomllib.loads(TOML.read_text(encoding="utf-8"))["env"]
        have = _parse(COMMITTED.read_text(encoding="utf-8"))
        assert have == env

    def test_generator_refuses_a_secret_shaped_key(self, tmp_path, capsys):
        for key in ("ODDS_API_KEY", "FOO_TOKEN", "X_SECRET", "Y_B64",
                    "DB_PASSWORD", "DISCORD_WEBHOOK_URL", "APP_AUTH_TOKEN"):
            toml = _scratch(tmp_path, f'{key} = "v"\n')
            out = tmp_path / "out.env"
            assert gen.main(["--toml", str(toml), "--out", str(out)]) != 0
            assert key in capsys.readouterr().err
            assert not out.exists()

    def test_check_fails_when_a_value_changes(self, tmp_path):
        scratch_out = tmp_path / "live.env.example"
        shutil.copy(COMMITTED, scratch_out)
        argv = ["--check", "--out", str(scratch_out)]
        assert gen.main([*argv, "--toml", str(TOML)]) == 0
        text = TOML.read_text(encoding="utf-8").replace(
            'PORT = "3000"', 'PORT = "3001"', 1
        )
        assert 'PORT = "3001"' in text
        changed = tmp_path / "fly.live.toml"
        changed.write_text(text, encoding="utf-8")
        assert gen.main([*argv, "--toml", str(changed)]) == 1

    def test_values_with_spaces_or_hash_are_single_quoted(self, tmp_path):
        toml = _scratch(tmp_path, 'A = "x y"\nB = "p#q"\nC = "plain"\n')
        text = gen.generate(toml)
        assert "A='x y'\n" in text
        assert "B='p#q'\n" in text
        assert "C=plain\n" in text
