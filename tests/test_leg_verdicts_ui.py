"""The leg scout's TAKE/PASS frontend stays advisory (#151, ADR 0186).

Joe's ruling: "I just want to know if the scouts would make the bet or
not" -- an opinion to weigh beside the buy button, never a second gate. These
are source-text assertions, the same shape as `tests/test_token_proxy_routes.py`
and `tests/test_suppression_gloss.py`: this repo has no JS test runner
(`frontend/package.json` has `dev`, `build`, `start`, `lint`, no `test`), so
nothing here executes a component or proves it renders correctly -- only that
the source carries the properties an advisory-only, never-a-gate surface is
required to carry.

Four claims:

1. `LegVerdicts.tsx` disables nothing and imports no ticket or buy component.
2. `AskTheMarket.tsx` and `ManualTicket.tsx` -- explicitly NOT modified by
   this ticket -- do not mention leg verdicts at all.
3. `requestLegVerdicts` (the call that can make the seat actually RUN, and
   spend) is invoked only inside the two named trigger handlers; every other
   caller uses `fetchLegVerdicts` (a plain `GET`, spends nothing).
4. TAKE is never painted with the go/green token -- it is the absence of a
   named objection, not a prediction that the bet wins, and painting it green
   would claim more than the seat is allowed to say.

WHAT THIS DOES NOT ESTABLISH
-----------------------------
- That the component renders correctly, polls correctly, or stops polling
  after three minutes -- that needs a running browser this repo has none of.
- That the backend actually sends the frozen response shape this file
  assumes; that is `tests/test_leg_verdict_seat.py`'s job.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "frontend" / "src"

LEG_VERDICTS = SRC / "components" / "LegVerdicts.tsx"
PRICE_ON_KALSHI = SRC / "components" / "PriceOnKalshi.tsx"
PARLAY_CARDS = SRC / "components" / "ParlayCards.tsx"
ASK_THE_MARKET = SRC / "components" / "AskTheMarket.tsx"
MANUAL_TICKET = SRC / "components" / "ManualTicket.tsx"
API_TS = SRC / "lib" / "api.ts"

#: Every file `requestLegVerdicts` may be CALLED from (not merely imported
#: by -- `api.ts` defines it, which is not a call).
ALLOWED_REQUEST_CALLERS = {PRICE_ON_KALSHI, PARLAY_CARDS}

#: Every frontend source file under `src/`, so "everything else" in claim 3
#: has a concrete membership.
ALL_TSX = sorted(SRC.rglob("*.ts*"))


def _strip_comments(source: str) -> str:
    """Same rule as `test_glossary_coverage.py`: a docstring explaining why a
    forbidden name is absent must not itself trip the check for that name."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", source, flags=re.MULTILINE)


def _text(path: Path) -> str:
    return _strip_comments(path.read_text(encoding="utf-8"))


class TestLegVerdictsIsAdvisoryOnly:
    """Claim 1: the one renderer disables nothing and cannot reach a buy
    control. Mutation observed red: add `disabled` to the PASS line, or
    import ManualTicket into this file -- both must fail here."""

    def test_it_imports_no_ticket_or_buy_component(self):
        source = _text(LEG_VERDICTS)
        for forbidden in ("AskTheMarket", "ManualTicket", "TakeIt"):
            assert forbidden not in source, (
                f"LegVerdicts.tsx mentions {forbidden!r} -- it must not "
                f"import or reach a buy/ticket component"
            )

    def test_it_disables_nothing(self):
        assert "disabled" not in _text(LEG_VERDICTS)

    def test_it_takes_no_callback_prop(self):
        """No `on...` callback prop in its own type signature -- the module
        docstring's claim that it "takes no callbacks" would otherwise be
        unchecked prose."""
        source = _text(LEG_VERDICTS)
        assert not re.search(r"\bon[A-Z]\w*\s*:\s*\(", source), (
            "LegVerdicts.tsx declares a callback prop; the component is "
            "meant to be read-only and take no callbacks"
        )


class TestTheBuySurfacesStayUntouched:
    """Claim 2. These two files are explicitly `Must not touch` in #153, and
    the shortest proof that held is that neither one even mentions the
    feature this ticket added."""

    def test_ask_the_market_does_not_mention_leg_verdicts(self):
        source = _text(ASK_THE_MARKET)
        assert "LegVerdict" not in source
        assert "leg-verdict" not in source
        assert "leg_verdict" not in source

    def test_manual_ticket_does_not_mention_leg_verdicts(self):
        source = _text(MANUAL_TICKET)
        assert "LegVerdict" not in source
        assert "leg-verdict" not in source
        assert "leg_verdict" not in source


class TestRequestLegVerdictsOnlyFiresFromTheTwoTriggers:
    """Claim 3. `requestLegVerdicts` is the one call that can make the seat
    spend; `fetchLegVerdicts` only reads. A mount effect or a stray render
    calling the spending function is exactly the defect this pins against.
    Mutation observed red: add a bare `requestLegVerdicts(...)` call inside
    `LegVerdicts.tsx` -- it is not one of the two allowed callers."""

    def test_price_on_kalshi_calls_it_inside_tap(self):
        source = _text(PRICE_ON_KALSHI)
        assert "requestLegVerdicts(legInputs, \"price_tap\"" in source

    def test_parlay_cards_calls_it_inside_the_toggle(self):
        source = _text(PARLAY_CARDS)
        assert 'requestLegVerdicts(legInputs, "leg_buys_open"' in source

    def test_no_other_frontend_file_calls_it(self):
        offenders = []
        for path in ALL_TSX:
            if path == API_TS or path in ALLOWED_REQUEST_CALLERS:
                continue
            source = _text(path)
            if re.search(r"(?<!function )requestLegVerdicts\s*\(", source):
                offenders.append(path.relative_to(SRC).as_posix())
        assert not offenders, (
            f"requestLegVerdicts is called from {offenders}, outside the two "
            f"trigger handlers -- everything else must call fetchLegVerdicts"
        )

    def test_leg_verdicts_component_only_calls_the_read(self):
        source = _text(LEG_VERDICTS)
        assert "fetchLegVerdicts" in source
        assert "requestLegVerdicts" not in source

    def test_every_other_file_that_mentions_the_feature_reads_rather_than_asks(self):
        """The inverse of claim 3: any file touching leg verdicts at all,
        outside the two trigger handlers, must use the non-spending read."""
        for path in ALL_TSX:
            if path in (API_TS, PRICE_ON_KALSHI, PARLAY_CARDS, LEG_VERDICTS):
                continue
            source = _text(path)
            if "LegVerdict" not in source and "leg-verdict" not in source:
                continue
            assert "requestLegVerdicts" not in source, (
                f"{path.relative_to(SRC).as_posix()} mentions leg verdicts "
                f"and calls requestLegVerdicts -- only PriceOnKalshi.tsx and "
                f"ParlayCards.tsx may"
            )


class TestTakeIsNeverPaintedGo:
    """Claim 4. `text-positive` / `bg-positive` is this repo's go/green
    token (`OpportunityCard.tsx`, `TicketSheet.tsx`, `PriceChart.tsx`).
    TAKE is the absence of a named objection, not a prediction the bet wins,
    and this repo's own rule (ADR 0071 s2.5) is that a per-row fact may be
    shown and never dressed as a claim stronger than it is.

    Mutation observed red: change the TAKE span's className to
    `"font-semibold text-positive"` -- this test then fails."""

    def test_the_go_token_never_appears_in_the_file(self):
        source = _text(LEG_VERDICTS)
        assert "text-positive" not in source
        assert "bg-positive" not in source

    def test_pass_and_take_are_rendered_as_literal_words(self):
        source = _text(LEG_VERDICTS)
        assert '"PASS"' in source
        assert '"TAKE"' in source


class TestTheFilesInThisScanExist:
    """The anchor. Without it a path typo makes every claim above vacuously
    pass against a file that was never read."""

    def test_every_named_file_exists(self):
        for path in (
            LEG_VERDICTS,
            PRICE_ON_KALSHI,
            PARLAY_CARDS,
            ASK_THE_MARKET,
            MANUAL_TICKET,
            API_TS,
        ):
            assert path.exists(), f"{path} does not exist"


class TestAVerdictRequestedAfterMountStillArrives:
    """Review fix, 2026-09-25. Before it, `<LegVerdicts>` inside the closed
    'Bet these legs one by one' panel mounted on page load, read `none`, and
    stopped polling for good. Opening the panel fired the request, but the
    line never re-read, so Joe would never have seen the verdict. The fix:
    each trigger stamps a request time, and a change of it restarts the
    poll."""

    def test_the_poll_restarts_when_a_request_is_stamped(self):
        src = LEG_VERDICTS.read_text(encoding="utf-8")
        assert "}, [legsKey, requestedAtMs]);" in src

    def test_the_poll_waits_through_none_just_after_a_request(self):
        src = LEG_VERDICTS.read_text(encoding="utf-8")
        assert 'justAsked && leg.state === "none"' in src

    def test_both_triggers_stamp_and_pass_the_request_time(self):
        for name in ("ParlayCards.tsx", "PriceOnKalshi.tsx"):
            src = (SRC / "components" / name).read_text(encoding="utf-8")
            assert "setRequestedAtMs(Date.now());" in src, name
            assert "requestedAtMs={requestedAtMs}" in src, name


class TestEveryCardHasAVisibleWayIn:
    """v58, Joe 2026-09-25: 'i dont see any take or pass here.' The scouts
    were live but invisible until a buy step. Each built card now carries a
    button, and before any tap only legs with a read are shown."""

    def test_each_card_renders_the_ask_the_scouts_button(self):
        src = (SRC / "components" / "ParlayCards.tsx").read_text(encoding="utf-8")
        assert "<AskTheScouts card={card} />" in src
        assert "Ask the scouts about these legs" in src
        assert 'requestLegVerdicts(legInputs, "card_button", card.key)' in src

    def test_the_card_view_hides_unasked_legs_until_a_tap(self):
        src = LEG_VERDICTS.read_text(encoding="utf-8")
        assert 'rows.filter((row) => row.state !== "none")' in src
