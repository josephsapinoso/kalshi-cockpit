"""#242: a leg verdict's TAKE is SHOWN as "No red flag"; the wire value stays take."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEG_VERDICTS = ROOT / "frontend/src/components/LegVerdicts.tsx"
PARLAY_CARDS = ROOT / "frontend/src/components/ParlayCards.tsx"
BACKEND = ROOT / "backend/agents/leg_verdict.py"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _jsx_strings(source: str) -> list[str]:
    """Quoted string literals and JSX text lines -- comments stripped."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    source = re.sub(r"(?m)^\s*//.*$", "", source)
    return re.findall(r'"[^"\n]*"|>[^<>{}\n]*<|^\s+[A-Za-z][^<>{}\n]*$', source, flags=re.M)


def test_take_renders_as_no_red_flag():
    assert '{isPass ? "PASS" : "No red flag"}' in _text(LEG_VERDICTS)


def test_no_user_facing_string_renders_bare_take():
    for path in (LEG_VERDICTS, PARLAY_CARDS):
        for s in _jsx_strings(_text(path)):
            assert not re.search(r"\bTAKE\b", s), (path.name, s)


def test_wire_enum_still_contains_take():
    assert re.search(r'["\']take["\']', _text(BACKEND), re.I)
    assert '"take"' in _text(ROOT / "frontend/src/lib/types/parlays.ts")
