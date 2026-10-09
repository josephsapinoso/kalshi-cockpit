"""`combo-markup` -- the registered markup-by-leg-count instrument (#327).

Spec: `docs/measurements/2026-10-08-preregistration-combo-markup-by-leg-count.md`.

What these tests establish
---------------------------
- The QueryDef is whitelisted, `cost=CHEAP`, and refuses a malformed
  `--cutoff` rather than ignoring it.
- On a fixture database built here (`db.init_db`, rows inserted by hand) the
  funnel counts, the cell medians / quartiles and the dispersion table equal
  values worked out by hand in this file's comments.
- Leg counts are never pooled
a cell below the floor prints no interval and
  a P1 whose floor is missed prints no test.
- A re-asked RFQ (stored quotes captured after `requested_ms`) is removed by
  rule 6 and counted, not silently averaged in.
- `g` is rebuilt through the ladder's own mapping, as of the lookup: a
  `fair_prices` row computed after the lookup is not used, a reproduction
  failure and a leg with no row are counted, not guessed.
- The as-of `fair_prices` read plans onto `idx_fair_link` with BOTH time
  bounds and never scans (the pin the lessons file asks for).
- The t quantile and the CR1 standard error agree with an independent
  computation in this file and with the two values the registration quotes.

What these tests do NOT establish
----------------------------------
- Nothing about live data: no row here is real, and the script was not run
  against the live account.
- That the ladder mapping used for `g` agrees with the one the desk showed on
  the day of an ask: it is the CURRENT code mapping, applied as of a past time.
- That any outcome word is warranted on live data
the fixture is built so a
  word can be checked, not so that one is true.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import pytest

from backend.store import db
from scripts.inspect_live_db import CHEAP, QUERIES, main
import inspect_live_db_parlays as P  # noqa: E402 -- on sys.path via the line above

_BASE_MS = int(datetime(2026, 9, 20, 16, 0, tzinfo=timezone.utc).timestamp() * 1000)
_DAY = 86_400_000
_CUTOFF_MS = int(datetime(2026, 10, 8, tzinfo=timezone.utc).timestamp() * 1000)


class _Args:
    limit = 2000
    cutoff = None


def _args(**kw):
    a = _Args()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _run(path, **kw):
    conn = db.connect(path)
    try:
        return QUERIES["combo-markup"].run(conn, _args(**kw))
    finally:
        conn.close()


def _section(sections, contains):
    for s in sections:
        if contains in s.title:
            return s
    raise AssertionError(f"no section like {contains!r}: {[s.title for s in sections]}")


def _rows(section):
    return [dict(zip(section.columns, r)) for r in section.rows]


def _add_ask(
    conn, n, *, day, legs, f, quotes, status="quoted", purpose=None,
    single=True, lookup=True, lookup_age_ms=60_000, card="safe",
    legs_json=None, ticker=None, lookup_fair=None,
):
    """One `combo_rfqs` row, its quotes, and the lookup that minted it."""
    req = _BASE_MS + day * _DAY + n * 1000
    ticker = ticker or f"KXMVE-T{n}"
    if legs_json is None:
        legs_json = json.dumps([
            {"event_ticker": f"EV{n}-{j}", "market_ticker": f"M{n}-{j}", "side": "yes"}
            for j in range(legs)
        ])
    conn.execute(
        "INSERT INTO combo_rfqs (rfq_id, requested_ms, card_key, ticker, "
        "collection_ticker, selected_legs, exchange_index, target_cost_dollars, "
        "fair_joint, quote_count, status, purpose) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"rfq-{n}", req, card, ticker, "KXMVE-COLL", legs_json, 1, "1.00", f,
         len(quotes), status, purpose),
    )
    for i, q in enumerate(quotes):
        conn.execute(
            "INSERT INTO combo_rfq_quotes (rfq_id, quote_id, captured_ms, "
            "yes_ask_tenths) VALUES (?,?,?,?)",
            (f"rfq-{n}", f"q{n}-{i}", req if single else req + 5000, q),
        )
    if lookup:
        conn.execute(
            "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents, "
            "selected_legs, status, minted_market_ticker, fair_joint_conservative) "
            "VALUES (?,?,?,?,?,?,?)",
            (req - lookup_age_ms, card, 100, legs_json, "priced", ticker,
             f if lookup_fair is None else lookup_fair),
        )
    return req


def _fixture(tmp_path):
    """Level 2: 20 asks on 10 days. Level 3: 20 asks on 10 days. Level 6+:
    5 asks. Plus eight asks, each removed at a different registered step."""
    path = tmp_path / "markup.db"
    conn = db.init_db(path)
    n = 0
    points = []  # (day, L, r) of the primary population, for the reference fit
    for i in range(20):  # level 2, f = 0.5 (500 tenths)
        n += 1
        best = 550 + (i % 2) * 10 + (i // 2)  # 550/560 + a day-varying drift
        _add_ask(conn, n, day=i // 2, legs=2, f=0.5, quotes=[best, 600])
        points.append((i // 2, 2, math.log(best / 500.0)))
    for i in range(20):  # level 3, f = 0.25 (250 tenths)
        n += 1
        best = 300 + (i // 2)
        _add_ask(conn, n, day=i // 2, legs=3, f=0.25, quotes=[best, 330])
        points.append((i // 2, 3, math.log(best / 250.0)))
    for i in range(3):  # seven legs, coded 6
        n += 1
        _add_ask(conn, n, day=i, legs=7, f=0.1, quotes=[150])
        points.append((i, 6, math.log(150 / 100.0)))
    for i in range(2):  # six legs
        n += 1
        _add_ask(conn, n, day=i, legs=6, f=0.1, quotes=[160])
        points.append((i, 6, math.log(160 / 100.0)))
    # The eight removed asks, one per registered step.
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[550], purpose="exit")
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[], status="no_quotes")
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=None, quotes=[400, 500], lookup=False)
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=1.2, quotes=[550], lookup=False)
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[550, 600], single=False)
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[550], lookup=False)
    n += 1
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[550], lookup_age_ms=31 * 60_000)
    n += 1
    # A lookup exists but copied a DIFFERENT fair: provenance cannot be shown.
    _add_ask(conn, n, day=1, legs=2, f=0.5, quotes=[550], lookup_fair=0.4)
    conn.commit()
    conn.close()
    return path, points


@pytest.fixture()
def fx(tmp_path):
    path, points = _fixture(tmp_path)
    return path, points


class TestComboMarkup:
    def test_is_whitelisted_cheap_and_cites_its_registration(self):
        q = QUERIES["combo-markup"]
        assert q.cost == CHEAP
        assert "preregistration" in q.run.__doc__ or "pre-registration" in q.run.__doc__.lower() or "preregistration" in q.run.__doc__.replace("-", "")
        assert "Row bound" in q.run.__doc__

    def test_malformed_cutoff_is_refused_not_ignored(self, fx):
        path, _ = fx
        with pytest.raises(ValueError):
            _run(path, cutoff="not-a-date")
        # and through main: exit 2, no output
        assert main(["combo-markup", "--db", str(path), "--cutoff", "nope"]) == 2

    def test_funnel_counts_equal_the_hand_count(self, fx):
        path, _ = fx
        rows = {r["step"]: r for r in _rows(_section(_run(path), "Exclusion funnel"))}
        assert rows["1 requested_ms before cutoff"]["remaining"] == 53
        assert rows["2 purpose"]["removed"] == 1
        assert rows["3 status"]["removed"] == 1
        assert rows["4 fair NULL"]["removed"] == 1
        assert rows["5 fair outside (0,1)"]["removed"] == 1
        assert rows["6 single-read"]["removed"] == 1
        assert rows["7 provenance"]["removed"] == 2
        assert rows["8 fair age"]["removed"] == 1
        assert rows["8 fair age"]["remaining"] == 45

    def test_cutoff_excludes_later_rows(self, fx):
        path, _ = fx
        # Cutoff before every fixture row: nothing scanned.
        sec = _section(_run(path, cutoff=str(_BASE_MS - 1)), "window")
        assert _rows(sec)[0]["asks_scanned"] == 0

    def test_limit_bounds_the_ask_walk_and_reports_truncation(self, fx):
        path, _ = fx
        sec = _section(_run(path, limit=10), "window")
        row = _rows(sec)[0]
        assert row["asks_scanned"] == 10 and row["truncated_at_limit"] is True

    def test_rule_6_removes_a_re_asked_rfq_and_prints_the_share(self, fx):
        path, _ = fx
        row = _rows(_section(_run(path), "Rule 6"))[0]
        assert row["re_asked_removed"] == 1
        # passed rules 1-5: 45 primary + no-lookup(1) + wrong-fair lookup(1) + stale(1) + re-asked(1)
        assert row["passed_rules_1_to_5"] == 49

    def test_cells_equal_hand_computed_values_and_never_pool_leg_counts(self, fx):
        path, _ = fx
        cells = {(r["leg_count"], r["price_band"]): r
                 for r in _rows(_section(_run(path), "Cells"))}
        # Level 2: best = 550/560 + (i//2), f = 500. The hand values below
        # are the median/quartiles of 100*(b-500)/500 over those 20 asks.
        bests = [550 + (i % 2) * 10 + (i // 2) for i in range(20)]
        pcts = sorted(100.0 * (b - 500) / 500 for b in bests)
        c2 = cells[(2, "[500,1000]")]
        assert c2["n"] == 20 and c2["days"] == 10
        assert c2["median_pct_f"] == round((pcts[9] + pcts[10]) / 2, 2)
        pos = 0.25 * 19
        q1 = pcts[int(pos)] + (pcts[int(pos) + 1] - pcts[int(pos)]) * (pos - int(pos))
        assert c2["q1_pct_f"] == round(q1, 2)
        assert c2["median_markup_tenths"] == round(
            sorted(b - 500 for b in bests)[9] / 2 + sorted(b - 500 for b in bests)[10] / 2, 2)
        # Level 3: best = 300 + i//2, f = 250 -> cell [250,500) up to best 309.
        c3 = cells[(3, "[250,500)")]
        assert c3["n"] == 20 and c3["days"] == 10
        # The other cells of those two levels are empty: nothing pooled.
        assert cells[(2, "[250,500)")]["n"] == 0
        assert cells[(3, "[500,1000]")]["n"] == 0
        # 6+ pools seven- and six-leg asks (registration: "6 or more"), 5 asks.
        c6 = cells[(6, "[100,250)")]
        assert c6["n"] == 5 and c6["days"] == 3
        assert c6["median_pct_f"] == 50.0 and c6["q3_pct_f"] == 60.0

    def test_a_cell_below_the_floor_prints_no_interval(self, fx):
        path, _ = fx
        cells = {(r["leg_count"], r["price_band"]): r
                 for r in _rows(_section(_run(path), "Cells"))}
        small = cells[(6, "[100,250)")]  # 5 asks on 3 days
        assert small["ci_lo_pct_f"] == "below floor"
        assert small["ci_hi_pct_f"] == "below floor"
        full = cells[(2, "[500,1000]")]  # 20 asks on 10 days
        assert isinstance(full["ci_lo_pct_f"], float)
        assert full["ci_lo_pct_f"] <= full["median_pct_f"] <= full["ci_hi_pct_f"]

    def test_p1_floor_met_prints_the_fit_and_it_matches_an_independent_ols(self, fx):
        path, points = fx
        secs = _run(path)
        p1 = {(r["fit"], r["against"]): r
              for r in _rows(_section(secs, "P1: OLS slope"))}
        prim = p1[("P1 primary", "f")]
        beta, se, g_days = _ref_cr1(points)
        assert prim["n"] == len(points) and prim["G_days"] == g_days
        assert prim["beta"] == pytest.approx(beta, abs=1e-5)
        assert prim["se_cr1"] == pytest.approx(se, abs=1e-5)
        outcome = _rows(_section(secs, "P1 outcome"))[0]
        # Floors hold (levels 2 and 3 each meet 20 asks / 10 days) but g could
        # not be rebuilt (no event links in this fixture), so MORE PER LEG is
        # unreachable: the word is GROWTH or UNRESOLVED, by beta_c's own t.
        t_c = P._cm_t_crit(g_days)
        expected = ("GROWTH NOT SEPARATED FROM THE DESK'S OWN FAIR"
                    if beta / se >= t_c else "REVERSED" if beta / se <= -t_c
                    else "UNRESOLVED")
        assert outcome["outcome"] == expected
        assert outcome["outcome"] != "MAKERS CHARGE MORE PER LEG"

    def test_p1_with_one_level_above_the_floor_runs_no_test(self, tmp_path):
        path = tmp_path / "thin.db"
        conn = db.init_db(path)
        for i in range(25):  # one level only, 25 asks on 12 days
            _add_ask(conn, i + 1, day=i // 2, legs=2, f=0.5, quotes=[550 + i])
        for i in range(3):
            _add_ask(conn, 100 + i, day=i, legs=3, f=0.25, quotes=[300])
        conn.commit()
        conn.close()
        secs = _run(path)
        out = _rows(_section(secs, "P1 outcome"))[0]
        assert out["outcome"].startswith("FLOOR NOT MET")
        tests = _section(secs, "four registered one-sided tests")
        assert tests.rows == []

    def test_p2_is_not_evaluable_without_start_times(self, fx):
        path, _ = fx
        out = _rows(_section(_run(path), "P2 outcome"))[0]
        assert out["outcome"].startswith("FLOOR NOT MET")

    def test_dispersion_counts_and_values(self, fx):
        path, _ = fx
        secs = _run(path)
        counts = {r["stored_quotes"]: r["asks"]
                  for r in _rows(_section(secs, "Dispersion population"))}
        # Two-quote asks passing rules 1,2,3,6: 20 (L2) + 20 (L3) + the
        # fair-NULL ask = 41; the re-asked two-quote ask is out by rule 6.
        assert counts["2"] == 41
        assert counts["0"] == 0 + 0  # no_quotes status is out at rule 3
        disp = {r["group"]: r for r in _rows(_section(secs, "Dispersion, worst"))}
        assert disp["all"]["asks"] == 41
        assert disp["no fair (same-game or unpriceable)"]["asks"] == 1
        assert disp["no fair (same-game or unpriceable)"]["median_tenths"] == 100.0
        assert disp["leg_count 3"]["asks"] == 20
        # L3: quotes [300 + i//2, 330] -> spreads 30,30,29,29,...,21,21.
        spreads = sorted(330 - (300 + i // 2) for i in range(20))
        assert disp["leg_count 3"]["median_tenths"] == (spreads[9] + spreads[10]) / 2

    def test_t_quantile_matches_the_registrations_two_values(self):
        assert P._cm_t_crit(10) == pytest.approx(2.685, abs=5e-4)
        assert P._cm_t_crit(21) == pytest.approx(2.423, abs=5e-4)
        assert P._cm_t_crit(1) is None

    def test_eastern_day_handles_dst_and_the_late_evening_boundary(self):
        # 2026-10-08T03:30Z is 23:30 on the 7th in EDT; in Dec it is the 7th 22:30 EST
        assert P._cm_eastern_day(int(datetime(2026, 10, 8, 3, 30, tzinfo=timezone.utc).timestamp() * 1000)) == "2026-10-07"
        assert P._cm_eastern_day(int(datetime(2026, 12, 8, 4, 30, tzinfo=timezone.utc).timestamp() * 1000)) == "2026-12-07"
        # DST boundary: 2026-11-01 06:30Z is 01:30 EST (after fall back) -> 1st
        assert P._cm_eastern_day(int(datetime(2026, 11, 1, 5, 30, tzinfo=timezone.utc).timestamp() * 1000)) == "2026-11-01"


# --- the generous fair g, through the ladder's own mapping -------------------


def _g_fixture(tmp_path):
    path = tmp_path / "g.db"
    conn = db.init_db(path)
    conn.execute("INSERT INTO kalshi_series (series_ticker, league, first_seen_ms, last_seen_ms) VALUES ('SER','MLB',0,0)")
    for i, (team, mt) in enumerate((("Houston Astros", "M1"), ("Boston Red Sox", "M2")), start=1):
        conn.execute(
            "INSERT INTO kalshi_events (event_ticker, series_ticker, title, commence_ms, first_seen_ms, last_seen_ms) "
            "VALUES (?,?,?,?,0,0)", (f"EV{i}", "SER", f"game {i}", _BASE_MS + 5 * 3600 * 1000, ))
        conn.execute(
            "INSERT INTO kalshi_markets (ticker, event_ticker, title, yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
            "VALUES (?,?,?,?,?,?,0,0)", (mt, f"EV{i}", f"{team} to win", team, "moneyline", "open"))
        conn.execute(
            "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, commence_ms, home_team, away_team, bookmaker, market, outcome_name, price_decimal) "
            "VALUES (0,'baseball_mlb',?,?,?,?,'b','h2h',?,2.0)", (f"O{i}", _BASE_MS, team, "Other", team))
        conn.execute(
            "INSERT INTO event_links (id, kalshi_event_ticker, odds_event_id, league, method, commence_skew_ms, linked_ms) "
            "VALUES (?,?,?,?,?,0,0)", (i, f"EV{i}", f"O{i}", "baseball_mlb", "exact_alias_pair"))
    return path, conn


def _fair(conn, link, team, computed_ms, p_cons, mult, add, pw, shin):
    conn.execute(
        "INSERT INTO fair_prices (computed_ms, link_id, market, outcome_name, "
        "p_multiplicative, p_additive, p_power, p_shin, p_conservative, "
        "book_count, books_used, oldest_book_age_ms) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (computed_ms, link, "h2h", team, mult, add, pw, shin, p_cons, 3, "[]", 1000))


def _legs(*pairs):
    return json.dumps([{"event_ticker": e, "market_ticker": m, "side": "yes"} for e, m in pairs])


class TestGeneratedFairIsRebuiltAsOfTheLookup:
    def _build(self, tmp_path):
        path, conn = _g_fixture(tmp_path)
        lookup_ms = _BASE_MS
        # In force at the lookup:
        _fair(conn, 1, "Houston Astros", lookup_ms - 3_600_000, 0.50, 0.52, 0.51, 0.53, 0.505)
        _fair(conn, 2, "Boston Red Sox", lookup_ms - 3_600_000, 0.40, 0.41, 0.42, 0.44, 0.43)
        # Computed AFTER the lookup: must never be used (the as-of bound).
        _fair(conn, 1, "Houston Astros", lookup_ms + 600_000, 0.30, 0.70, 0.70, 0.70, 0.70)
        legs = _legs(("EV1", "M1"), ("EV2", "M2"))
        # Good ask: f = 0.5 * 0.4 = 0.2 reproduces; best 250.
        _add_ask(conn, 1, day=0, legs=2, f=0.2, quotes=[250], legs_json=legs,
                 lookup_age_ms=0)
        # Reproduction fails: stored fair 0.3 vs product 0.2 (ln 1.5 > 0.05).
        _add_ask(conn, 2, day=0, legs=2, f=0.3, quotes=[350], legs_json=legs,
                 lookup_age_ms=0)
        # A leg with no fair row (an alternate-line leg looks the same).
        _add_ask(conn, 3, day=0, legs=2, f=0.2, quotes=[250],
                 legs_json=_legs(("EV1", "M1"), ("EV2", "M-ALT")), lookup_age_ms=0)
        conn.execute("UPDATE combo_rfqs SET requested_ms = ?", (lookup_ms,))
        conn.execute("UPDATE combo_rfq_quotes SET captured_ms = ?", (lookup_ms,))
        conn.execute("UPDATE parlay_lookups SET requested_ms = ?", (lookup_ms,))
        conn.commit()
        conn.close()
        return path

    def test_g_is_the_product_of_each_legs_most_generous_method(self, tmp_path):
        path = self._build(tmp_path)
        secs = _run(path, cutoff=str(_BASE_MS + _DAY))
        cell = {(r["leg_count"], r["price_band"]): r
                for r in _rows(_section(secs, "Cells"))}[(2, "[250,500)")]
        # asks 1,2,3 all land in band [250,500)? best 250/350/250 -> yes.
        assert cell["n"] == 3
        # Only ask 1 reconstructs: g = 0.2 * (0.53/0.50) * (0.44/0.40) = 0.2332
        assert cell["n_g"] == 1
        assert cell["median_pct_g"] == round(100 * (250 - 233.2) / 233.2, 2)

    def test_failures_are_counted_by_reason_not_guessed(self, tmp_path):
        path = self._build(tmp_path)
        secs = _run(path, cutoff=str(_BASE_MS + _DAY))
        why = {r["reason"]: r["asks"]
               for r in _rows(_section(secs, "Why asks were not reconstructed"))}
        assert why == {"reproduction_failed": 1, "leg_has_no_fair_row": 1}
        share = {r["leg_count"]: r for r in _rows(_section(secs, "g reconstructed from"))}
        assert share["all"]["reconstructed"] == 1 and share["all"]["asks"] == 3

    def test_a_row_computed_after_the_lookup_is_never_used(self, tmp_path):
        # Same fixture: the post-lookup Houston row has p_hi 0.70 and p_cons
        # 0.30. If it leaked in, ask 1 would fail the reproduction check
        # (0.3 * 0.4 = 0.12 vs f 0.2) and n_g would be 0.
        path = self._build(tmp_path)
        secs = _run(path, cutoff=str(_BASE_MS + _DAY))
        row = {r["leg_count"]: r for r in _rows(_section(secs, "g reconstructed from"))}["all"]
        assert row["reconstructed"] == 1


class TestTheAsOfFairReadPlansOntoAnIndex:
    def _plan(self, tmp_path):
        path = tmp_path / "plan.db"
        conn = db.init_db(path)
        sql = P._SQL_CM_FAIR_ASOF
        params = (1,) * sql.count("?")
        rows = conn.execute("EXPLAIN QUERY PLAN " + sql, params).fetchall()
        conn.close()
        return " | ".join(str(r[3]) for r in rows)

    def test_fair_prices_is_searched_by_link_and_both_time_bounds(self, tmp_path):
        plan = self._plan(tmp_path)
        assert "idx_fair_link" in plan
        # The as-of bound and the lookback floor are both in the seek.
        assert "link_id=? AND computed_ms>? AND computed_ms<?" in plan
        assert "SCAN fair_prices" not in plan and "SCAN f" not in plan

    def test_the_market_list_is_a_copy_of_the_candidate_scans(self):
        assert P._CM_POOL_MARKETS_SQL in P._SQL_PARLAY_CANDIDATES

    def test_the_ask_lookup_and_quote_reads_use_their_indexes(self, tmp_path):
        path = tmp_path / "plan2.db"
        conn = db.init_db(path)
        for name, sql in (
            ("asks", P._SQL_CM_ASKS), ("quotes", P._SQL_CM_QUOTES),
            ("lookup", P._SQL_CM_LOOKUP),
        ):
            params = (1,) * sql.count("?")
            plan = " | ".join(str(r[3]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params))
            assert "SCAN combo" not in plan and "SCAN parlay_lookups" not in plan, (name, plan)
        conn.close()


# --- independent reference: simple regression with CR1 by cluster -------------


def _ref_cr1(points):
    """beta, se (CR1) of y ~ 1 + L, clustered by day, closed-form 2x2."""
    n = len(points)
    sx = sum(p[1] for p in points)
    sxx = sum(p[1] ** 2 for p in points)
    sy = sum(p[2] for p in points)
    sxy = sum(p[1] * p[2] for p in points)
    det = n * sxx - sx * sx
    b1 = (n * sxy - sx * sy) / det
    b0 = (sy - b1 * sx) / n
    # (X'X)^-1 second row: [-sx, n] / det
    clusters = {}
    for day, L, y in points:
        u = y - b0 - b1 * L
        s = clusters.setdefault(day, [0.0, 0.0])
        s[0] += u
        s[1] += u * L
    meat = [[0.0, 0.0], [0.0, 0.0]]
    for s in clusters.values():
        for a in range(2):
            for b in range(2):
                meat[a][b] += s[a] * s[b]
    inv = [[sxx / det, -sx / det], [-sx / det, n / det]]
    # V[1][1] = row1(inv) . meat . col1(inv)
    row = inv[1]
    v = sum(row[a] * meat[a][b] * inv[b][1] for a in range(2) for b in range(2))
    g = len(clusters)
    v *= (g / (g - 1)) * ((n - 1) / (n - 2))
    return b1, math.sqrt(v), g
