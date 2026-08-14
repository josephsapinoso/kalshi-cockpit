"""`scripts/analyse_qw_result.py`: the numbers behind the Q-W verdict.

Every claim here was observed red under a named mutation, written beside the
test. The instrument this file pins re-derives figures that have already been
published, so its failure mode is quiet by construction: a wrong number here
does not crash anything, it just disagrees with a document nobody re-checks.

WHAT THESE TESTS DO NOT ESTABLISH
---------------------------------
- **Nothing about the live database.** Every payload below is built in this
  file. The analyser reads one JSON artefact and cannot tell whether that
  artefact came from the machine it claims to.
- **Nothing about whether `W` should have activated.** The registered rule fired
  in `kalshi-quotes-band`. This script is descriptive, and a test that let it
  reverse a verdict would be testing the wrong thing.
"""

from __future__ import annotations

import json

import pytest

from scripts.analyse_qw_result import (
    _MAX_HONEST_GAP_MIN,
    analyse,
    main,
    render,
)

OFFSET_MS = 3 * 60 * 60 * 1000
DAY0 = 1_786_060_800_000  # 2026-08-07T00:00:00Z
WINDOW_END = 1_786_406_400_000  # 2026-08-11T00:00:00Z
MIN = 60_000


def _payload(instants, events, verdict=None, event_columns=None):
    """Build an artefact of the shape `kalshi-quotes-band --json` emits.

    `instants` is a list of `(observed_ms, qualifying_markets)`.
    `events` is a list of `(event_ticker, qualifying_quotes, start_ms, nlc)`.
    """
    cols = event_columns or (
        "event_ticker",
        "qualifying_quotes",
        "true_start_ms",
        "non_linear_cent_quotes",
    )
    return {
        "sections": [
            {
                "title": "Q-W window (registered)",
                "columns": ("start_ms", "end_ms"),
                "rows": [(DAY0, WINDOW_END)],
            },
            {
                "title": "Q-W verdict: W ACTIVATES (bars: >= 80% of pre-game "
                "instants, >= 8 distinct events)",
                "columns": (
                    "series_ticker",
                    "pregame_instants",
                    "qualifying_instants",
                    "instant_pct",
                    "qualifying_events",
                    "activates",
                    "note",
                ),
                "rows": [
                    verdict
                    or (
                        "KXWNBAGAME",
                        len(instants),
                        sum(1 for _, n in instants if n > 0),
                        97.99,
                        len(events),
                        1,
                        "ACTIVATES",
                    )
                ],
            },
            {
                "title": "KXWNBAGAME: every pre-game polling instant, and how "
                "many markets in band with depth at each",
                "columns": ("observed_ms", "qualifying_markets"),
                "rows": list(instants),
            },
            {
                "title": "KXWNBAGAME: distinct events contributing a "
                "qualifying market",
                "columns": cols,
                "rows": list(events),
            },
        ]
    }


def _run(instants, events, gap=5.0, **kw):
    return analyse(_payload(instants, events, **kw), gap, OFFSET_MS)


EV = [("E1", 10, DAY0 + MIN, 0)]


class TestTheSectionLookupRefusesAnAmbiguousMatch:
    """"distinct events" appears in the VERDICT title too.

    A first-match lookup returned the verdict while re-deriving the event
    table. It happened to fail loudly because the columns did not exist -- luck,
    not design, and the same slip against a section with overlapping column
    names would have returned wrong numbers silently.

    Mutation seen red: the `len(matches) != 1` guard replaced by `matches[0]`.
    """

    def test_the_event_table_is_not_confused_with_the_verdict(self):
        a = _run([(DAY0, 1)], EV)
        assert a["events_total"] == 1
        assert a["verdict"]["series_ticker"] == "KXWNBAGAME"

    def test_two_sections_matching_one_fragment_is_refused(self):
        p = _payload([(DAY0, 1)], EV)
        p["sections"].append(dict(p["sections"][-1]))
        with pytest.raises(SystemExit):
            analyse(p, 5.0, OFFSET_MS)

    def test_a_missing_section_is_refused_rather_than_skipped(self):
        p = _payload([(DAY0, 1)], EV)
        p["sections"] = [s for s in p["sections"] if "verdict" not in s["title"]]
        with pytest.raises(SystemExit):
            analyse(p, 5.0, OFFSET_MS)


class TestAWiderCutIsRefused:
    """The dedup share is monotone increasing in gap width by construction.

    A burst qualifies if ANY instant in it qualifies, so widening the cut can
    only ever raise the number. That makes a wide cut a way to manufacture a
    better result, which is why the ceiling is enforced rather than advised.

    Mutation seen red: the `> _MAX_HONEST_GAP_MIN` check deleted.
    """

    def test_a_gap_above_the_ceiling_exits_2(self, tmp_path, capsys):
        path = tmp_path / "a.json"
        path.write_text(json.dumps(_payload([(DAY0, 1)], EV)), encoding="utf-8")
        rc = main([str(path), "--burst-gap-min", str(_MAX_HONEST_GAP_MIN + 0.1)])
        assert rc == 2
        assert "measures the cut, not the book" in capsys.readouterr().err

    def test_the_ceiling_itself_is_allowed(self, tmp_path):
        path = tmp_path / "a.json"
        path.write_text(json.dumps(_payload([(DAY0, 1)], EV)), encoding="utf-8")
        assert main([str(path), "--burst-gap-min", str(_MAX_HONEST_GAP_MIN)]) == 0

    def test_widening_the_cut_never_lowers_the_share(self):
        # The property the ceiling exists because of. Two instants 8 min apart,
        # the second a miss: at 5 min they are two looks (50%), at 10 min one
        # look that qualifies (100%).
        instants = [(DAY0, 1), (DAY0 + 8 * MIN, 0)]
        assert _run(instants, EV, gap=5.0)["burst_pct"] == 50.0
        assert _run(instants, EV, gap=10.0)["burst_pct"] == 100.0


class TestTheBurstDedupCountsLooksNotRows:
    """`pregame_instants` is poller uptime, not clock.

    Mutations seen red: `>` widened to `>=` at the gap boundary; the burst
    "qualifies if any member qualifies" rule changed to "if all members do".
    """

    def test_a_tight_burst_of_hits_is_one_look(self):
        instants = [(DAY0 + i * 10_000, 1) for i in range(40)]
        a = _run(instants, EV)
        assert a["verdict"]["pregame_instants"] == 40
        assert a["bursts"] == 1
        assert a["burst_pct"] == 100.0

    def test_a_burst_containing_one_hit_counts_as_a_hit(self):
        instants = [(DAY0, 0), (DAY0 + 10_000, 1), (DAY0 + 20_000, 0)]
        a = _run(instants, EV)
        assert a["bursts"] == 1 and a["bursts_ok"] == 1

    def test_a_gap_exactly_at_the_cut_does_not_split(self):
        instants = [(DAY0, 1), (DAY0 + 5 * MIN, 1)]
        assert _run(instants, EV, gap=5.0)["bursts"] == 1

    def test_a_gap_one_ms_over_the_cut_splits(self):
        instants = [(DAY0, 1), (DAY0 + 5 * MIN + 1, 1)]
        assert _run(instants, EV, gap=5.0)["bursts"] == 2

    def test_dedup_can_lower_the_raw_share(self):
        # 39 clustered hits and one isolated miss: raw 97.5%, deduped 50%.
        instants = [(DAY0 + i * 10_000, 1) for i in range(39)]
        instants.append((DAY0 + 60 * MIN, 0))
        a = _run(instants, EV)
        assert a["bursts"] == 2 and a["burst_pct"] == 50.0


class TestTheTimeWeightedCheckIsIndependent:
    """A second count of the same rows is not a second denominator.

    Mutation seen red: `outage_h` computed from the miss COUNT rather than the
    span they cover, which makes it a restatement of the raw share.
    """

    def test_a_contiguous_outage_is_measured_as_a_span(self):
        instants = [(DAY0 + i * MIN, 1) for i in range(60)]
        for i in range(10, 20):
            instants[i] = (instants[i][0], 0)
        a = _run(instants, EV)
        assert a["outage_h"] == pytest.approx(9 / 60, abs=1e-6)

    def test_a_single_miss_has_no_span(self):
        instants = [(DAY0, 1), (DAY0 + MIN, 0), (DAY0 + 2 * MIN, 1)]
        assert _run(instants, EV)["outage_h"] == 0.0

    def test_no_misses_gives_a_hundred_percent(self):
        instants = [(DAY0 + i * MIN, 1) for i in range(10)]
        assert _run(instants, EV)["time_weighted_pct"] == 100.0


class TestLeadTimeUsesTheTrueStartNotTheStoredStamp:
    """The stored stamp is expected EXPIRATION and runs 3h late (ADR 0006).

    The first artefact emitted it under the name `commence_ms`. Reading that
    column without correcting it moves every fixture three hours later, which
    pushes fixtures across the window boundary in the flattering direction --
    fewer events look like they had not tipped.

    Mutations seen red: the correction dropped for the `commence_ms` shape; the
    correction also applied to the already-corrected `true_start_ms` shape.
    """

    def _events(self, start_ms, column):
        cols = (
            "event_ticker",
            "qualifying_quotes",
            column,
            "non_linear_cent_quotes",
        )
        return [("E1", 10, start_ms, 0)], cols

    def test_the_two_artefact_shapes_agree_on_the_same_fixture(self):
        true_start = WINDOW_END - MIN
        new_rows, new_cols = self._events(true_start, "true_start_ms")
        old_rows, old_cols = self._events(true_start + OFFSET_MS, "commence_ms")
        new = _run([(DAY0, 1)], new_rows, event_columns=new_cols)
        old = _run([(DAY0, 1)], old_rows, event_columns=old_cols)
        assert new["events_in_window"] == old["events_in_window"] == 1
        assert new["not_tipped"] == old["not_tipped"] == []

    def test_a_fixture_tipping_after_the_window_is_counted(self):
        rows, cols = self._events(WINDOW_END + MIN, "true_start_ms")
        a = _run([(DAY0, 1)], rows, event_columns=cols)
        assert len(a["not_tipped"]) == 1
        assert a["events_in_window"] == 0

    def test_a_fixture_tipping_exactly_at_the_window_end_is_counted_out(self):
        rows, cols = self._events(WINDOW_END, "true_start_ms")
        assert len(_run([(DAY0, 1)], rows, event_columns=cols)["not_tipped"]) == 1

    def test_an_artefact_with_neither_column_is_refused(self):
        rows, cols = self._events(WINDOW_END, "something_else_ms")
        with pytest.raises(SystemExit):
            _run([(DAY0, 1)], rows, event_columns=cols)


class TestThePartsArePrintedBesideTheAggregate:
    """A pooled share is not a finding until the per-group view agrees.

    Mutation seen red: the per-day split dropped from `render`.
    """

    def test_each_utc_day_is_its_own_row(self):
        instants = [(DAY0 + 12 * 3_600_000, 1), (DAY0 + 36 * 3_600_000, 0)]
        a = _run(instants, EV)
        assert sorted(a["per_day"]) == ["2026-08-07", "2026-08-08"]
        assert a["per_day"]["2026-08-07"] == [1, 1]
        assert a["per_day"]["2026-08-08"] == [1, 0]

    def test_the_render_names_every_day_and_the_restricted_count(self):
        rows, cols = [("E1", 10, WINDOW_END + MIN, 0)], None
        a = _run([(DAY0, 1)], rows, event_columns=cols)
        text = render(a)
        assert "2026-08-07" in text
        assert "BELOW THE BAR" in text
        assert "UNREGISTERED" in text

    def test_the_restricted_count_is_not_flagged_when_it_clears(self):
        rows = [(f"E{i}", 10, DAY0 + MIN, 0) for i in range(8)]
        assert "BELOW THE BAR" not in render(_run([(DAY0, 1)], rows))


class TestHalfCentContaminationIsCarriedThrough:
    """`non_linear_cent_quotes` is the column that closes the rounding hazard.

    Mutation seen red: the sum replaced by a constant 0, which is the value it
    is expected to have and therefore the mutation most likely to survive.
    """

    def test_a_nonzero_count_is_reported(self):
        assert _run([(DAY0, 1)], [("E1", 10, DAY0, 3)])["non_linear_cent_quotes"] == 3

    def test_it_sums_across_events(self):
        rows = [("E1", 10, DAY0, 2), ("E2", 10, DAY0, 5)]
        assert _run([(DAY0, 1)], rows)["non_linear_cent_quotes"] == 7


class TestAnEmptyInstantSectionIsRefused:
    """Zero rows must not render as a clean 100%.

    Mutation seen red: the `if not rows` guard deleted, which crashes on an
    IndexError deep in the burst loop instead of saying what is wrong.
    """

    def test_it_exits_rather_than_dividing_by_zero(self):
        with pytest.raises(SystemExit):
            _run([], EV)


class TestAnUncomputableFigureSaysSoRatherThanSubstituting:
    """Unreadable resolves to `None`, and the renderer must print that.

    A zero-length observation has no time-weighted share. Rendering it as 100%
    would report perfect availability from an artefact containing one look --
    an absence borrowing a present value's representation, which is the failure
    this repo's `_iso(None)` rule already exists for.

    Mutations seen red: `time_weighted_pct` defaulted to `100.0` when `span_h`
    is 0; the `None` branch in `render` replaced by a bare format.
    """

    def test_a_single_look_has_no_time_weighted_share(self):
        assert _run([(DAY0, 1)], EV)["time_weighted_pct"] is None

    def test_the_render_says_not_computable_rather_than_a_number(self):
        text = render(_run([(DAY0, 1)], EV))
        assert "not computable (no span)" in text
        assert "-> 100.0%" not in text

    def test_no_qualifying_quotes_gives_no_concentration_figure(self):
        a = _run([(DAY0, 0)], [("E1", 0, DAY0, 0)])
        assert a["top4_share"] is None
        assert "not computable (no qualifying quotes)" in render(a)
