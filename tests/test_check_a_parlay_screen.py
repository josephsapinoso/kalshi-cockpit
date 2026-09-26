"""The "check a parlay someone else built" box (issue #165, #167).

Source-reading tests, in the style of `tests/test_ask_the_market_screen.py`:
these pin what the screen renders and how it is wired, not what it looks
like at runtime -- there is no React test runner in this repo.

The hard rule this file exists to guard: 82 of Joe's 142 settled parlays were
never priced on this desk because they are a friend's parlays he tails, and
the fix is a box where a leg the desk has no consensus for renders as
"no desk reading for this leg" -- never `0`, never `0%`, never blank, because
`0` is itself a legitimate chance and indistinguishable from a silent
substitution once printed.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- Nothing about what the component renders at runtime.
- Nothing about whether `/api/parlays/check` (the backend route, built in a
  parallel lane) answers the contract this file assumes -- only that the
  frontend renders that contract correctly if it does.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).parent.parent / "frontend" / "src"
CHECK = FRONTEND / "components" / "CheckAParlay.tsx"
PAGE = FRONTEND / "app" / "parlays" / "page.tsx"
PROXY = FRONTEND / "app" / "parlay-check" / "route.ts"
MIDDLEWARE = FRONTEND / "middleware.ts"
API = FRONTEND / "lib" / "api.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestANullChanceIsNeverZero:
    def test_the_unknown_leg_sentence_is_present(self):
        source = _read(CHECK)
        assert "no desk reading for this leg" in source.lower()

    def test_the_unknown_leg_branch_is_keyed_on_chance_null(self):
        """Mutation observed red: change `=== null` to `!leg.chance` (or
        drop the branch), and a genuine 0% leg starts rendering as unknown,
        or a null chance stops being caught at all."""
        source = _read(CHECK)
        assert re.search(r"leg\.chance\s*===\s*null", source) or re.search(
            r"leg\.chance\s*==\s*null", source
        ), "the unknown-leg branch must test chance against null explicitly"

    def test_no_chance_value_is_defaulted_to_zero(self):
        """`?? 0` or `|| 0` near a chance field silently turns "no reading"
        into a real-looking 0% -- exactly the substitution CLAUDE.md's
        'unreadable resolves to None, never 0' rule forbids. `"0%"` as a
        literal is the same failure spelled a different way.

        Comments are stripped first: this guard's own explanation, quoted
        above, contains the literal string `?? 0` and would otherwise trip
        itself."""
        source = _strip_comments(_read(CHECK))
        for window in _windows_around(source, "chance"):
            assert "?? 0" not in window, "a chance field defaults to 0"
            assert "|| 0" not in window, "a chance field defaults to 0"
        assert '"0%"' not in source


class TestTheAskPanelIsWired:
    def test_ask_the_market_is_passed_the_minted_ticker(self):
        source = _read(CHECK)
        assert "<AskTheMarket" in source
        assert "marketTicker={value.minted_market_ticker}" in source

    def test_ask_the_market_is_imported(self):
        source = _read(CHECK)
        assert "AskTheMarket" in source.split("export default")[0]

    def test_ask_the_market_renders_only_where_asking_can_work(self):
        """#166 round 2: the RFQ path hard-codes shard 1, and an unsharded
        KXMVE market carries `exchange_index: 0`. A button that fires a
        create at the wrong shard 404s `not_found`, which reads as a
        permissions problem on the spending screen -- so the button is
        gated on the server's `rfq_available`, and the reason is shown."""
        source = _strip_comments(_read(CHECK))
        gate = source.index("value.rfq_available ?")
        assert gate < source.index("<AskTheMarket")
        assert "value.rfq_unavailable_reason" in source


class TestNoRankingOrVerdict:
    def test_the_component_never_sorts(self):
        """ADR 0071 s2.5: a per-row fact is transparency, an ordering is a
        claim. The legs and the joint render in the order the server sent
        them."""
        assert ".sort(" not in _read(CHECK)

    def test_no_verdict_words(self):
        source = _read(CHECK).lower()
        for forbidden in ("take", "good bet", "pass on this"):
            assert forbidden not in source


class TestThePageMountsIt:
    def test_the_page_imports_check_a_parlay(self):
        source = _read(PAGE)
        assert 'import CheckAParlay from "@/components/CheckAParlay";' in source

    def test_the_page_renders_it(self):
        assert "<CheckAParlay" in _read(PAGE)

    def test_it_sits_between_the_header_and_the_ladder(self):
        """Below the header, above the ladder -- the ticket's placement."""
        source = _read(PAGE)
        header_end = source.index("</header>")
        cards_start = source.index("<ParlayCards")
        mount = source.index("<CheckAParlay")
        assert header_end < mount < cards_start


class TestTheDoorIsRegistered:
    def test_the_proxy_forwards_to_the_backend_route(self):
        source = _read(PROXY)
        assert '"/api/parlays/check"' in source
        assert "backendToken" in source and "demoRefusal" in source

    def test_middleware_gives_an_unauthenticated_post_a_json_401(self):
        assert '"/parlay-check"' in _read(MIDDLEWARE)

    def test_the_proxy_says_nothing_was_checked_when_the_backend_is_silent(self):
        assert "Nothing was checked" in _read(PROXY)


class TestTheApiFunctionNeverThrows:
    def test_check_parlay_exists(self):
        assert "export async function checkParlay(" in _read(API)

    def test_it_returns_the_ok_refusal_shape(self):
        source = _read(API)
        fn = source[source.index("export async function checkParlay("):]
        assert "ok: true" in fn and "ok: false" in fn
        assert "refusal" in fn

    def test_it_posts_to_the_proxy_route(self):
        source = _read(API)
        fn = source[source.index("export async function checkParlay("):]
        assert '"/parlay-check"' in fn


def _strip_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", " ", source, flags=re.MULTILINE)


def _windows_around(source: str, needle: str, radius: int = 40) -> list[str]:
    """Every substring within `radius` characters of an occurrence of
    `needle`, so a stray `|| 0` elsewhere in the file (on an unrelated
    field) does not fail this test by accident."""
    windows = []
    for match in re.finditer(re.escape(needle), source):
        start = max(0, match.start() - radius)
        end = min(len(source), match.end() + radius)
        windows.append(source[start:end])
    return windows
