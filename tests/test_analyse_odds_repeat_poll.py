"""The instrument that spends 24 credits had no test. This is that test.

`scripts/analyse_odds_repeat_poll.py` turns the repeat-poll capture into
CONFIRMED / REFUTED / UNRESOLVED. Until this file existed it was imported by
nothing and executed by nothing, which is failure mode #9/#10 verbatim:
`capture_fills_fixture.py` also had no test file, and its exit code turned out
to be **unreachable by construction** -- the settlements half had no `return` at
all, and the word a handoff quoted as its verdict was one a human had supplied,
not one the script ever printed. A verdict nobody has watched the code produce
is a verdict nobody has.

So the load-bearing property here is not "the arithmetic is right". It is
**every branch that can be printed has been printed at least once, from
artefacts, by the real `main()`, and read back off stdout with its exit code.**
Each of PC1-PC6 is driven to FAIL, and each of the three verdicts is driven to
be declared.

Fixture provenance
------------------
The four-poll artefacts are built from
`tests/fixtures/odds_mlb_h2h_spreads_totals.json` -- a **verbatim capture** of
`/v4/sports/baseball_mlb/odds` (us+eu, h2h+spreads+totals, decimal): 15 events,
30 bookmakers, 440 (book, event) pairs, and a real `h2h_lay` market the deployed
parser must drop. CLAUDE.md requires wire-format tests to load captured
payloads, and this is one; nothing here hand-rolls a bookmaker. What the tests
*do* hand-author is the **difference between polls** -- a shifted `last_update`,
a moved price, a moved hook -- which is unavoidable, because no repeat poll has
ever been captured by anyone. That is the whole reason the capture is being
paid for. The differences are the independent variable, and they are applied to
real rows.

The artefact envelope (`poll_index`, `payload`, `payload_raw_tokens`, ...) is
not hand-copied from memory: `TestTheCaptureAndAnalysisAgree` re-derives the key
set from the capture script's own AST, so a rename there fails here.

`payload` and `payload_raw_tokens` are produced the way the capture produces
them -- `json.loads(text)` and `json.loads(text, parse_float=str)` over **one**
serialised body -- so the TEXT_FLOAT_MISMATCH check is exercised through its
real mechanism rather than by writing the two halves separately.

What these tests do NOT establish
---------------------------------
- **Nothing about `last_update`.** Every stamp movement here was written by this
  file. These tests establish what the instrument *does with* an input, never
  what the aggregator does. The registration's question is untouched and stays
  untouched until the capture runs.
- **Not that the thresholds are right.** 0.90 / 0.20 / 20 / 5 / 0.80 / 0.05 / 5
  / 24 are quoted from the registration and are asserted to still equal those
  numbers; whether they are *good* numbers is a question the registration
  answered before any data existed, and is not re-opened here.
- **Not that the capture will succeed**, that the account has 24 credits, or
  that the slate rule holds. `tests/test_repeat_poll_preconditions.py` owns P1.
- **Not that a real payload cannot break the projection.** These artefacts share
  one captured slate; a book that emits a market key nobody has seen, or an
  `alternate_totals` block, would be new behaviour on the real wire and this
  file would not notice.
- **Not that the printed prose is correct English.** Assertions are on the
  verdict token, the PASS/FAIL flags and the exit code. Prose is read only where
  the registration mandates specific words (the CONFIRMED qualifier, QUIET
  SLATE).
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
FIXTURE = REPO / "tests" / "fixtures" / "odds_mlb_h2h_spreads_totals.json"
CAPTURE_SRC = SCRIPTS / "capture_odds_repeat_poll.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analyse = _load_module(SCRIPTS / "analyse_odds_repeat_poll.py", "analyse_repeat_poll")

T0_MS = 1_786_110_562_317
OFFSETS = (0, 60, 300, 900)

# A price that occurs nowhere else in the captured slate, so its JSON token can
# be rewritten by exact string match without touching any other row.
SENTINEL_PRICE = 1.9999937


# --------------------------------------------------------------------------
# Artefact construction, from the captured payload
# --------------------------------------------------------------------------

def _base_events() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["events"]


_BASE = _base_events()
ALL_BOOKS = sorted({b["key"] for e in _BASE for b in e["bookmakers"]})
N_EVENTS = len(_BASE)


def _iso_shift(value: str, seconds: int) -> str:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (dt + timedelta(seconds=seconds)).astimezone(
        timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def shift_stamps(
    events: list[dict], seconds: int, *, books: Optional[Iterable[str]] = None
) -> None:
    """Move `last_update` at BOTH levels; the parser prefers the market one."""
    keep = None if books is None else set(books)
    for event in events:
        for book in event["bookmakers"]:
            if keep is not None and book["key"] not in keep:
                continue
            book["last_update"] = _iso_shift(book["last_update"], seconds)
            for market in book["markets"]:
                if "last_update" in market:
                    market["last_update"] = _iso_shift(
                        market["last_update"], seconds
                    )


def change_prices(
    events: list[dict],
    *,
    books: Optional[Iterable[str]] = None,
    event_indices: Optional[Iterable[int]] = None,
    delta: float = 0.05,
) -> int:
    """Move one real h2h price per (book, event). Returns how many moved."""
    keep_books = None if books is None else set(books)
    keep_events = None if event_indices is None else set(event_indices)
    moved = 0
    for i, event in enumerate(events):
        if keep_events is not None and i not in keep_events:
            continue
        for book in event["bookmakers"]:
            if keep_books is not None and book["key"] not in keep_books:
                continue
            for market in book["markets"]:
                if market["key"] != "h2h":
                    continue
                outcome = market["outcomes"][0]
                outcome["price"] = round(float(outcome["price"]) + delta, 4)
                moved += 1
                break
    return moved


def set_sentinel_price(events: list[dict]) -> None:
    events[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = SENTINEL_PRICE


def move_total_hook(events: list[dict], event_index: int, book: str, delta: float) -> int:
    moved = 0
    for b in events[event_index]["bookmakers"]:
        if b["key"] != book:
            continue
        for market in b["markets"]:
            if market["key"] != "totals":
                continue
            for outcome in market["outcomes"]:
                outcome["point"] = round(float(outcome["point"]) + delta, 4)
                moved += 1
    return moved


def duplicate_outcome(events: list[dict], event_index: int, book: str) -> None:
    for b in events[event_index]["bookmakers"]:
        if b["key"] != book:
            continue
        market = b["markets"][0]
        market["outcomes"].append(copy.deepcopy(market["outcomes"][0]))


def drop_events(events: list[dict], keep: int) -> list[dict]:
    return events[:keep]


def keep_books(events: list[dict], books: Iterable[str]) -> None:
    keep = set(books)
    for event in events:
        event["bookmakers"] = [b for b in event["bookmakers"] if b["key"] in keep]


PRICEABLE = {"h2h", "spreads", "totals"}


def _count_quotes(payload: list[dict]) -> int:
    return sum(
        len(m["outcomes"])
        for e in payload
        for b in e["bookmakers"]
        for m in b["markets"]
        if m["key"] in PRICEABLE
    )


def artefact(
    index: int,
    events: list[dict],
    *,
    cost: int = 6,
    text_subs: tuple[tuple[str, str], ...] = (),
    n_quotes: Optional[int] = None,
) -> dict[str, Any]:
    """The capture's own envelope. One body, parsed twice -- as it writes it."""
    text = json.dumps(events)
    for old, new in text_subs:
        assert old in text, f"text substitution {old!r} matched nothing"
        text = text.replace(old, new, 1)
    payload = json.loads(text)
    raw = json.loads(text, parse_float=str)
    offset = OFFSETS[index - 1]
    return {
        "registration": (
            "docs/measurements/"
            "2026-08-10-preregistration-odds-last-update-repeat-poll.md"
        ),
        "poll_index": index,
        "nominal_offset_s": offset,
        "t0_ms": T0_MS,
        "fetched_ms": T0_MS + offset * 1000,
        "realised_offset_s": float(offset),
        "sport_key": "baseball_mlb",
        "markets": ["h2h", "spreads", "totals"],
        "regions": ["us", "eu"],
        "cost_credits": cost,
        "x_requests_remaining": "500",
        "x_requests_used": "100",
        "n_quotes_parsed": _count_quotes(payload) if n_quotes is None else n_quotes,
        "payload": payload,
        "payload_raw_tokens": raw,
    }


def base_polls() -> dict[int, list[dict]]:
    """Four polls off the captured slate, stamps advancing, prices frozen.

    Deliberately the *quiet slate*: this is the configuration that produces
    S = 1.0 with `movers = 0`, i.e. the confound PC5 exists to catch. Every
    other scenario is this one plus a named difference.
    """
    polls: dict[int, list[dict]] = {}
    for index, offset in enumerate(OFFSETS, start=1):
        events = copy.deepcopy(_BASE)
        shift_stamps(events, offset)
        polls[index] = events
    return polls


def make_control_reachable(
    polls: dict[int, list[dict]], books: Iterable[str], *, event_index: int = 0
) -> None:
    """Move a price for `books` at poll 4 only, so `movers` can reach 5.

    Poll 4 alone, so the deciding 1 -> 3 pair is untouched.
    """
    change_prices(polls[4], books=books, event_indices=[event_index])


def run(
    tmp_path: Path,
    polls: dict[int, list[dict]],
    *,
    costs: Optional[dict[int, int]] = None,
    text_subs: Optional[dict[int, tuple[tuple[str, str], ...]]] = None,
    n_quotes: Optional[dict[int, int]] = None,
    indices: Optional[dict[int, int]] = None,
    reverse: bool = False,
    capsys=None,
) -> tuple[int, str]:
    paths: list[str] = []
    for index in sorted(polls):
        art = artefact(
            index,
            polls[index],
            cost=(costs or {}).get(index, 6),
            text_subs=(text_subs or {}).get(index, ()),
            n_quotes=(n_quotes or {}).get(index),
        )
        if indices and index in indices:
            art["poll_index"] = indices[index]
        path = tmp_path / f"p{index}.json"
        path.write_text(json.dumps(art), encoding="utf-8")
        paths.append(str(path))
    if reverse:
        paths.reverse()
    code = analyse.main(paths)
    out = capsys.readouterr().out
    return code, out


def pc_flags(out: str) -> dict[str, str]:
    flags: dict[str, str] = {}
    for line in out.splitlines():
        stripped = line.strip()
        if stripped.startswith("[PASS] PC") or stripped.startswith("[FAIL] PC"):
            flags[stripped[7:10]] = stripped[1:5]
    return flags


def s_value(out: str) -> float:
    return float(out.split("  S            ")[1].split()[0])


def verdict_line(out: str) -> str:
    lines = [line for line in out.splitlines() if line.startswith("VERDICT:")]
    assert lines, f"no VERDICT line printed:\n{out}"
    return lines[-1]


# --------------------------------------------------------------------------


class TestTheFixtureIsTheCapturedSlate:
    """If the fixture is not the real capture, every number below is theatre."""

    def test_fixture_is_a_verbatim_capture(self):
        raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
        assert "Verbatim" in raw["note"]
        assert raw["params"]["oddsFormat"] == "decimal"
        assert raw["params"]["regions"] == ["us", "eu"]

    def test_shape_matches_the_registrations_counts(self):
        assert N_EVENTS == 15
        assert len(ALL_BOOKS) == 30
        assert sum(len(e["bookmakers"]) for e in _BASE) == 440

    def test_the_slate_contains_a_market_the_parser_must_drop(self):
        # §5.2 of the client: h2h_lay beside h2h. If this stopped being true the
        # projection would no longer be exercised against the exclusion path.
        keys = {m["key"] for e in _BASE for b in e["bookmakers"] for m in b["markets"]}
        assert "h2h_lay" in keys


class TestTheCaptureAndAnalysisAgree:
    """`poll_index` is 1-based on both sides, re-derived rather than recalled."""

    @staticmethod
    def _capture_tree() -> ast.Module:
        return ast.parse(CAPTURE_SRC.read_text(encoding="utf-8"))

    def test_capture_enumerates_polls_from_one(self):
        starts = [
            kw.value.value
            for node in ast.walk(self._capture_tree())
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "enumerate"
            and any(
                isinstance(a, ast.Name) and a.id == "POLL_OFFSETS_S"
                for a in node.args
            )
            for kw in node.keywords
            if kw.arg == "start" and isinstance(kw.value, ast.Constant)
        ]
        assert starts == [1], (
            "capture_odds_repeat_poll.py:588 must enumerate POLL_OFFSETS_S with "
            f"start=1; found {starts}. The analysis indexes polls 1..4."
        )

    def test_analysis_reads_the_same_base(self):
        used = set(analyse.PRIMARY_PAIR) | set(analyse.FALLBACK_PAIR)
        assert min(used) == 1
        assert max(used) <= analyse.N_POLLS
        assert analyse.N_POLLS == 4

    def test_the_artefact_envelope_is_the_captures_own(self):
        keys: set[str] = set()
        for node in ast.walk(self._capture_tree()):
            if (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "artefact"
                and isinstance(node.value, ast.Dict)
            ):
                keys = {
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
        assert keys, "no `artefact = {...}` literal found in the capture script"
        assert set(analyse.REQUIRED_FIELDS) <= keys, (
            "the analysis requires fields the capture does not write: "
            f"{set(analyse.REQUIRED_FIELDS) - keys}"
        )
        built = set(artefact(1, copy.deepcopy(_BASE)))
        assert built == keys, (
            "the test builder and the capture disagree on the artefact envelope: "
            f"only-in-test {built - keys}, only-in-capture {keys - built}"
        )

    def test_offsets_are_the_registered_schedule(self):
        capture = _load_module(CAPTURE_SRC, "capture_repeat_poll_for_test")
        assert tuple(capture.POLL_OFFSETS_S) == OFFSETS
        assert len(capture.POLL_OFFSETS_S) == analyse.N_POLLS


class TestTheThresholdsAreStillTheRegisteredOnes:
    """A threshold that drifts after a capture voids the registration (§P0)."""

    def test_every_constant(self):
        assert analyse.CONFIRM_AT == 0.90
        assert analyse.REFUTE_AT == 0.20
        assert analyse.PC1_MIN_BOOKS == 20
        assert analyse.PC2_MIN_ADV_BOOKS == 5
        assert analyse.PC3_MIN_ATTRITION == 0.80
        assert analyse.PC4_MAX_DEFECT_RATE == 0.05
        assert analyse.PC5_MIN_MOVERS == 5
        assert analyse.EXPECTED_TOTAL_CREDITS == 24
        assert analyse.PRIMARY_PAIR == (1, 3)
        assert analyse.FALLBACK_PAIR == (1, 4)


class TestTheThreeVerdicts:
    """Each of CONFIRMED / REFUTED / UNRESOLVED, produced by the real main()."""

    def test_confirmed_with_the_mandatory_qualifier(self, tmp_path, capsys):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        assert "VERDICT: CONFIRMED" in verdict_line(out)
        assert "S = 1.0000 >= 0.9" in out
        # The five control books moved a price over the span, so S_strict cannot
        # reach 0.90 and §7's qualifier is mandatory.
        assert "MANDATORY QUALIFIER" in out
        assert "not a" in out and "per-line" in out
        # The other leg's licensed paragraph must NOT appear here.
        assert "PERMITTED WORDING" not in out

    def test_confirmed_with_the_strong_wording(self, tmp_path, capsys):
        # The books that supply `movers` are NOT the books that advance, so
        # S_strict reaches 1.0 while PC5 still passes. §7 says the write-up may
        # then use the strong wording; this proves that branch is reachable.
        control = set(ALL_BOOKS[:5])
        advancing = [b for b in ALL_BOOKS if b not in control]
        polls: dict[int, list[dict]] = {}
        for index, offset in enumerate(OFFSETS, start=1):
            events = copy.deepcopy(_BASE)
            shift_stamps(events, offset, books=advancing if index < 4 else None)
            polls[index] = events
        make_control_reachable(polls, control)

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        assert "VERDICT: CONFIRMED" in verdict_line(out)
        assert "N_adv = 25" in out
        assert "S_strict = 1.0000" in out
        assert "MANDATORY QUALIFIER" not in out
        # Amendment B §B1 retired the phrase "the strong wording" and fixed the
        # permitted sentence in advance. The script must print that sentence,
        # not a phrase defined nowhere.
        assert "strong wording" not in out.replace(
            "'The strong wording' is not a term of this", ""
        )
        assert "PERMITTED WORDING (Amendment B sec B1)" in out
        assert "No price change" in out
        assert "for the bookmakers whose stamps advanced" in out
        assert "moved and moved back" in out
        assert "NOT licensed:" in out

    def test_s_strict_prints_the_span_it_was_earned_on(self, tmp_path, capsys):
        # Amendment B §B2: `s_strict` is ALWAYS computed over poll 1 -> poll 4,
        # a registered deviation from §6's natural reading, and the result must
        # print the span beside the value.
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        _, out = run(tmp_path, polls, capsys=capsys)
        assert "span: poll 1 -> poll 4 (nominal 900s), always" in out
        assert "Amendment B sec B2" in out

    def test_refuted(self, tmp_path, capsys):
        polls = base_polls()
        # Every book moves a price on every event between poll 1 and poll 3:
        # every advancing pair lands in the refuting cell.
        for index in (3, 4):
            change_prices(polls[index])
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        assert "VERDICT: REFUTED" in verdict_line(out)
        assert s_value(out) <= analyse.REFUTE_AT
        assert "425   <- refuting" in out

    def test_unresolved_mid_band(self, tmp_path, capsys):
        polls = base_polls()
        half = list(range(N_EVENTS // 2))
        for index in (3, 4):
            change_prices(polls[index], event_indices=half)
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        line = verdict_line(out)
        assert "VERDICT: UNRESOLVED" in line
        assert "lies between" in line
        assert analyse.REFUTE_AT < s_value(out) < analyse.CONFIRM_AT

    def test_unresolved_just_above_the_refutation_threshold(self, tmp_path, capsys):
        # The band immediately above 0.20, pinned with the literal rather than
        # the constant: a test that reads `analyse.REFUTE_AT` moves its own
        # goalposts when the constant is edited, and this is the region where
        # UNRESOLVED and REFUTED are one threshold apart.
        polls = base_polls()
        for index in (3, 4):
            change_prices(polls[index], event_indices=range(11))
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        assert 0.20 < s_value(out) < 0.50
        assert "VERDICT: UNRESOLVED" in verdict_line(out)
        assert "lies between" in verdict_line(out)


class TestEveryPreconditionCanFail:
    """PC1-PC6, each driven to FAIL. A guard never seen failing is decoration."""

    def test_pc1_book_coverage(self, tmp_path, capsys):
        nineteen = ALL_BOOKS[:19]
        polls = base_polls()
        for events in polls.values():
            keep_books(events, nineteen)
        make_control_reachable(polls, nineteen[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert pc_flags(out)["PC1"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC1"]
        assert "VERDICT: UNRESOLVED" in verdict_line(out)
        assert "PC1" in verdict_line(out)
        assert "19 books" in out

    def test_pc2_confirming_cell_unreachable_even_after_the_fallback(
        self, tmp_path, capsys
    ):
        # No stamp advances anywhere, so 1->3 fails PC2, the registered 1->4
        # substitution is applied, and it fails too. Five books still move a
        # price at poll 4 so PC5 passes and PC2 fails alone.
        polls = {index: copy.deepcopy(_BASE) for index in range(1, 5)}
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert "(PC2 FALLBACK APPLIED)" in out
        assert pc_flags(out)["PC2"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC2"]
        assert "N_adv = 0" in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc3_attrition(self, tmp_path, capsys):
        polls = base_polls()
        polls[3] = drop_events(polls[3], 7)   # 205 of 440 pairs survive
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert pc_flags(out)["PC3"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC3"]
        assert "BOTH 205 vs 80% of 440" in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc4_text_float_mismatch(self, tmp_path, capsys):
        # Same float, different JSON token: `1.9999937` vs `1.99999370`. This is
        # the "byte-identical" claim of §5.3 made literally, and it can only be
        # caught through `payload_raw_tokens`.
        polls = base_polls()
        for events in polls.values():
            set_sentinel_price(events)
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(
            tmp_path, polls,
            text_subs={3: (("1.9999937", "1.99999370"),)},
            capsys=capsys,
        )
        assert code == 0
        assert "TEXT_FLOAT_MISMATCH 1" in out
        assert pc_flags(out)["PC4"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC4"]
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc4_key_degenerate(self, tmp_path, capsys):
        polls = base_polls()
        duplicate_outcome(polls[3], 0, ALL_BOOKS[0])
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert "KEY-DEGENERATE 1" in out
        assert pc_flags(out)["PC4"] == "FAIL"
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc4_regressed_stamps(self, tmp_path, capsys):
        # Eight books' stamps go backwards at poll 3 -- cached or sharded
        # responses. 22 books still advance, so PC2 passes on the primary pair
        # and no substitution masks the defect.
        backwards = ALL_BOOKS[:8]
        polls = base_polls()
        shift_stamps(polls[3], -3600, books=backwards)
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert pc_flags(out)["PC4"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC4"]
        assert "regressed 0 " not in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc5_quiet_slate_is_this_repos_scar(self, tmp_path, capsys):
        # Stamps advance everywhere, not one price moves anywhere: S = 1.0 on
        # data that could not have produced any other answer.
        code, out = run(tmp_path, base_polls(), capsys=capsys)

        assert code == 0
        assert "S            1.0000" in out
        assert pc_flags(out)["PC5"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC5"]
        assert "QUIET SLATE" in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)
        assert "CONFIRMED" not in verdict_line(out)

    def test_pc6_credits_do_not_total_24(self, tmp_path, capsys):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        code, out = run(tmp_path, polls, costs={4: 5}, capsys=capsys)

        assert code == 0
        assert pc_flags(out)["PC6"] == "FAIL"
        assert [k for k, v in pc_flags(out).items() if v == "FAIL"] == ["PC6"]
        assert "23 credits" in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_pc6_an_empty_poll_is_a_refusal_not_a_slate(self, tmp_path, capsys):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        code, out = run(tmp_path, polls, n_quotes={2: 0}, capsys=capsys)

        assert code == 0
        assert pc_flags(out)["PC6"] == "FAIL"
        assert "all non-empty: False" in out
        assert "VERDICT: UNRESOLVED" in verdict_line(out)


class TestThePreconditionsPrintBeforeS:
    """§7: a statistic read before its preconditions is one quoted without them."""

    def test_ordering(self, tmp_path, capsys):
        _, out = run(tmp_path, base_polls(), capsys=capsys)
        assert out.index("PRECONDITIONS") < out.index(
            "S -- bookmaker-clustered MEAN"
        )
        assert out.index("R -- the advance rate") < out.index("PRECONDITIONS")

    def test_s_is_still_printed_when_a_precondition_fails(self, tmp_path, capsys):
        _, out = run(tmp_path, base_polls(), capsys=capsys)
        assert "S            1.0000" in out
        assert "UNRESOLVED -- DOES NOT DECIDE" in out


class TestThePC2Fallback:
    """The one registered substitution, and it happens at most once."""

    def test_fallback_is_applied_and_can_still_decide(self, tmp_path, capsys):
        # Nothing advances by poll 3; everything advances by poll 4. PC2 fails
        # on 1->3, the registered 1->4 substitution takes over, and it resolves.
        polls: dict[int, list[dict]] = {}
        for index in range(1, 5):
            events = copy.deepcopy(_BASE)
            if index == 4:
                shift_stamps(events, 900)
            polls[index] = events
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert "deciding pair: poll 1 -> 4" in out
        assert "(PC2 FALLBACK APPLIED)" in out
        assert "substitution reason: N_adv = 0 < 5 on the primary pair" in out
        assert pc_flags(out) == {f"PC{i}": "PASS" for i in range(1, 7)}
        assert "VERDICT: CONFIRMED" in verdict_line(out)

    def test_the_primary_pair_is_chosen_by_index_not_by_realised_interval(
        self, tmp_path, capsys
    ):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        _, out = run(tmp_path, polls, capsys=capsys)
        assert "deciding pair: poll 1 -> 3   (PRIMARY)" in out


class TestTheEqualityPredicate:
    """§5.3, where a wrong key would remove real reprices from the denominator."""

    def test_a_moved_hook_is_a_change_not_an_absence(self, tmp_path, capsys):
        polls = base_polls()
        for index in (3, 4):
            move_total_hook(polls[index], 0, ALL_BOOKS[0], 0.5)
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        # Exactly one (book, event) pair changed, and it is in the REFUTING
        # cell. If `outcome_point` were in the row key it would instead vanish
        # from the compared set and be reported as ROWSET-CHANGED.
        assert "B advanced & changed        1" in out
        assert "ROWSET-CHANGED 0" in out

    def test_no_stamp_pairs_are_excluded_not_counted_as_static(
        self, tmp_path, capsys
    ):
        # A book that reports no `last_update` at all is UNREADABLE, not
        # static. It must not be able to hide a reprice in the uninformative
        # cell: §S2 lists it under exclusions, counted.
        polls = base_polls()
        for index in (1, 3):
            for book in polls[index][0]["bookmakers"][:2]:
                book.pop("last_update", None)
                for market in book["markets"]:
                    market.pop("last_update", None)
        change_prices(polls[3], books=[polls[3][0]["bookmakers"][0]["key"]],
                      event_indices=[0])
        make_control_reachable(polls, ALL_BOOKS[:5])

        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert "NO-STAMP 2" in out
        assert "C static   & identical      0" in out


class TestThePartialCaptureRule:
    """§8, resolved rather than left ambiguous. See the script's docstring."""

    def test_polls_1_and_3_alone_yield_a_verdict(self, tmp_path, capsys):
        polls = base_polls()
        del polls[2]
        del polls[4]
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert "PARTIAL CAPTURE" in out
        assert "deciding pair: poll 1 -> 3   (PRIMARY)" in out
        # The control cannot be measured without poll 4, so it FAILS. It does
        # not default to 0 and it does not quietly pass.
        assert pc_flags(out)["PC5"] == "FAIL"
        assert "NOT EVALUABLE" in out
        assert pc_flags(out)["PC6"] == "FAIL"
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_polls_1_and_4_alone_go_through_the_pc2_fallback(self, tmp_path, capsys):
        polls = base_polls()
        del polls[2]
        del polls[3]
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert "deciding pair: poll 1 -> 4" in out
        assert "(PC2 FALLBACK APPLIED)" in out
        assert "poll 3 absent" in out
        assert pc_flags(out)["PC6"] == "FAIL"
        assert "VERDICT: UNRESOLVED" in verdict_line(out)

    def test_any_other_partial_capture_is_incomplete_and_exits_2(
        self, tmp_path, capsys
    ):
        polls = base_polls()
        del polls[3]
        del polls[4]
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 2
        assert "VERDICT: UNRESOLVED -- INCOMPLETE" in out
        assert "sec 8 requires 1 and 3" in out

    def test_a_partial_capture_can_never_be_confirmed(self, tmp_path, capsys):
        # The loosened gate must not become a route to a verdict on 12 credits.
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        del polls[2]
        code, out = run(tmp_path, polls, capsys=capsys)

        assert code == 0
        assert "S            1.0000" in out
        assert "CONFIRMED" not in verdict_line(out)
        assert "VERDICT: UNRESOLVED" in verdict_line(out)


class TestTheRefusals:
    """Exit 2 -- no verdict issued. Read the exit code, not the prose."""

    def test_a_repeated_poll_index_is_refused(self, tmp_path, capsys):
        polls = base_polls()
        code, out = run(tmp_path, polls, indices={2: 1}, capsys=capsys)

        assert code == 2
        assert "REFUSED" in out
        assert "repeated poll_index" in out
        assert "VERDICT" not in out

    def test_a_zero_based_poll_index_is_refused(self, tmp_path, capsys):
        # If the capture ever loses `start=1`, PRIMARY_PAIR = (1, 3) would
        # silently compare polls 2 and 4 -- a 600 s pair reported as 300 s.
        polls = base_polls()
        code, out = run(
            tmp_path, polls, indices={1: 0, 2: 1, 3: 2, 4: 3}, capsys=capsys
        )
        assert code == 2
        assert "REFUSED" in out
        assert "1-based" in out

    def test_a_missing_field_names_the_file(self, tmp_path):
        art = artefact(1, copy.deepcopy(_BASE))
        del art["realised_offset_s"]
        path = tmp_path / "broken.json"
        path.write_text(json.dumps(art), encoding="utf-8")
        with pytest.raises(SystemExit) as excinfo:
            analyse.main([str(path)])
        assert "broken.json" in str(excinfo.value)
        assert "realised_offset_s" in str(excinfo.value)


class TestOrderIndependence:
    def test_file_order_does_not_change_the_verdict(self, tmp_path, capsys):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        forward_code, forward = run(tmp_path, polls, capsys=capsys)
        reverse_code, reverse = run(tmp_path, polls, reverse=True, capsys=capsys)

        assert forward_code == reverse_code == 0
        assert verdict_line(forward) == verdict_line(reverse)
        assert pc_flags(forward) == pc_flags(reverse)


class TestTheRivalIsPricedBeforeTheNumber:
    """ADR 0026: name what else could produce the branch, before the data."""

    def test_the_rival_block_is_printed_on_every_verdict(self, tmp_path, capsys):
        # Printed on a CONFIRMED run, not only when REFUTED is declared --
        # otherwise it is a judgement made after the number, which is the thing
        # ADR 0026 forbids.
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        _, confirmed = run(tmp_path, polls, capsys=capsys)

        refuting = base_polls()
        for index in (3, 4):
            change_prices(refuting[index])
        _, refuted = run(tmp_path, refuting, capsys=capsys)

        for out in (confirmed, refuted):
            assert "RIVAL HYPOTHESIS, PRICED BEFORE THE NUMBER (ADR 0026)" in out
            assert "REFUTED is CONDITIONAL" in out
            assert out.index("RIVAL HYPOTHESIS") < out.index("VERDICT:")
            assert out.index("RIVAL HYPOTHESIS") < out.index(
                "S -- bookmaker-clustered MEAN"
            )
        assert "VERDICT: CONFIRMED" in verdict_line(confirmed)
        assert "VERDICT: REFUTED" in verdict_line(refuted)

    def test_the_separating_observable_is_printed(self, tmp_path, capsys):
        refuting = base_polls()
        for index in (3, 4):
            change_prices(refuting[index])
        _, out = run(tmp_path, refuting, capsys=capsys)
        # 425 of 440 pairs repriced inside the 300 s primary interval, which is
        # the rival's own signature. The instrument prints the rate; it does not
        # adjudicate it, and no threshold is attached.
        assert "(B + D) / BOTH = 425 / 440 = 0.9659" in out


class TestMoversIsPrintedOnBothWindows:
    """PC5 spans 900 s; the verdict is decided at 300 s. Print both."""

    def test_the_two_windows_can_disagree_and_both_are_shown(
        self, tmp_path, capsys
    ):
        # All movement is confined to the 3 -> 4 leg: PC5 passes on 5 books
        # while nothing at all moved at the deciding 1 -> 3 pair.
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        _, out = run(tmp_path, polls, capsys=capsys)

        assert "MOVERS -- the control" in out
        assert "full span poll 1 -> 4       5 books" in out
        assert "deciding pair 1 -> 3       0 books" in out
        assert "REPORTED, NOT GATING" in out
        assert pc_flags(out)["PC5"] == "PASS"
        assert out.index("MOVERS") < out.index("S -- bookmaker-clustered MEAN")

    def test_the_restricted_count_gates_nothing(self, tmp_path, capsys):
        # Same run as above: zero movers at the deciding pair, and the verdict
        # is still CONFIRMED. If the restricted count ever starts gating, this
        # goes red -- which is the point of asserting it.
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        code, out = run(tmp_path, polls, capsys=capsys)
        assert code == 0
        assert "deciding pair 1 -> 3       0 books" in out
        assert "VERDICT: CONFIRMED" in verdict_line(out)


class TestTheOperationalCorollary:
    """§7: a count. It may never raise, lower, or create the verdict."""

    def test_it_is_printed_after_the_verdict(self, tmp_path, capsys):
        polls = base_polls()
        make_control_reachable(polls, ALL_BOOKS[:5])
        _, out = run(tmp_path, polls, capsys=capsys)
        assert out.index("VERDICT:") < out.index("OPERATIONAL COROLLARY")
        assert "carries no alpha" in out
        assert "30/30" in out

    def test_it_is_not_printed_when_a_precondition_failed(self, tmp_path, capsys):
        _, out = run(tmp_path, base_polls(), capsys=capsys)
        assert "OPERATIONAL COROLLARY" not in out
