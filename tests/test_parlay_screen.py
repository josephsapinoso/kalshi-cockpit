"""Two dead ends the 2026-08-24 code review found on the parlay desk's one
money-adjacent control (findings 1 and 2 of that review).

1. **A dropped connection froze the card forever.** `lookupParlay` had no
   `try`/`catch` around its `fetch` and called `response.json()` unguarded, so
   a network failure rejected the promise; `PriceOnKalshi`'s `tap()` did not
   catch either, leaving the component in `working` — which renders "Asking
   Kalshi…" and unmounts the only button on the card. The sibling
   `refreshOdds` had the pattern already.
2. **There was no transition back to `idle`.** The state machine went
   `idle → working → done | refused` and stopped. But `book_empty` is the
   *expected* first answer on a freshly minted combo (the 2026-08-23 capture),
   and its own server-worded copy says "Try again shortly" — an instruction the
   screen made impossible to follow without a page reload. Same dead end after
   a 409 drift refusal.

**What this does not establish.** The assertions are over **source text**,
because this repo has no JS test runner (`frontend/package.json` has `dev`,
`build`, `start`, `lint` and no test script). They prove the guard and the
transition are written; they do not render anything, so they cannot prove the
button reaches the DOM, that it is reachable with a thumb at 390px, or that
the refusal words are legible. Only opening the page does that. Nor do they
say anything about whether a retry is the *right* action against the exchange
— that is finding 7's open question about the repeat-call wire shape.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend" / "src"
API_TS = FRONTEND / "lib" / "api.ts"
PRICE_ON_KALSHI = FRONTEND / "components" / "PriceOnKalshi.tsx"


def _lookup_parlay_source() -> str:
    """Just `lookupParlay`'s body — so a `try` elsewhere in the 2,000-line
    module cannot satisfy an assertion about this function."""
    source = API_TS.read_text(encoding="utf-8")
    start = source.index("export async function lookupParlay(")
    # The next top-level `export` after it bounds the function.
    end = source.index("\nexport ", start + 1)
    return source[start:end]


class TestTheLookupNeverStrandsTheCard:
    def test_the_fetch_itself_is_guarded(self):
        body = _lookup_parlay_source()
        assert "try {" in body and "} catch (error) {" in body, (
            "lookupParlay must not let a transport failure reject: its caller "
            "renders one button and unmounts it while the request is in "
            "flight, so a rejection freezes the card at 'Asking Kalshi…'."
        )

    def test_the_body_parse_cannot_throw(self):
        body = _lookup_parlay_source()
        # Every `.json()` in this function must be followed by a `.catch`.
        assert ".json().catch(" in body
        assert "await response.json()) as ParlayLookupResult" not in body, (
            "an unguarded response.json() on the ok path throws on a proxy "
            "page served with a 200"
        )

    def test_a_transport_failure_says_the_market_may_exist(self):
        body = _lookup_parlay_source()
        assert "did not reach the cockpit" in body
        assert "may already have" in body, (
            "a dropped connection is not the same as nothing happening -- the "
            "POST may have reached Kalshi and minted the market, and the "
            "words must not invite a blind retry"
        )

    def test_the_component_catches_too(self):
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        tap = source[source.index("const tap = async ()") :]
        tap = tap[: tap.index("\n  const ")]
        assert "try {" in tap and "catch (error)" in tap


class TestEveryNonFinalStateOffersAWayBack:
    def test_there_is_a_transition_back_to_idle(self):
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        assert 'setState({ kind: "idle" })' in source, (
            "book_empty is the expected first answer on a fresh combo and its "
            "own copy says 'Try again shortly'; without a transition back to "
            "idle that instruction needs a page reload"
        )

    def test_the_retry_covers_refusals_and_unpriced_answers(self):
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        assert 'state.kind === "refused"' in source
        assert 'state.value.status !== "priced"' in source, (
            "the retry must cover book_empty and no_collection (both are "
            "'done'), not only the refused branch"
        )

    def test_a_priced_answer_is_final(self):
        """No retry on a priced answer: re-asking a question already answered
        is how a screen invites tapping for a better number."""
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        assert 'status !== "priced"' in source

    def test_the_retry_is_not_the_money_coloured_control(self):
        """`bg-accent` is the red money slot, and this screen spends it on the
        first tap only (ADR 0070). A second control wearing it would make the
        card read as two actions of equal weight."""
        source = PRICE_ON_KALSHI.read_text(encoding="utf-8")
        # Only actual class strings -- the module's docstring and the comment
        # beside the retry both name `bg-accent` to explain the rule.
        wearing_it = [
            line for line in source.splitlines()
            if "className=" in line and "bg-accent" in line
        ]
        assert len(wearing_it) == 1, wearing_it
