"""`game-script-card-stamps`, `parlay-lookup-errors`, `own-open-rfqs` (#286).

Three CHEAP reads from the 2026-10-02 parlay town hall.

What these tests establish
---------------------------
- Each QueryDef is CHEAP, its SQL scans a LIMIT-bounded subquery (never the
  table), and its docstring carries a "does not establish" section.
- With more rows than the window, the window binds: `rows_scanned` equals the
  cap and older rows are not counted.
- The counts mean what the docstrings say, against the real schema.
- The copied venue cap equals `backend.kalshi.rfq.MAX_OPEN_RFQS`.

What these tests do NOT establish
----------------------------------
- **Nothing about live.** Every row is seeded here.
- **That the plans are good on a 10M-row table.** The bound is the subquery's
  LIMIT, asserted on the SQL text and on behaviour, not timed.
"""

from __future__ import annotations

import inspect

from scripts.inspect_live_db import CHEAP, QUERIES  # noqa: I001 (sets sys.path)
import inspect_live_db_parlays as parlays
from backend.store import db

NEW = (
    "game-script-card-stamps",
    "game-script-card-rechecks",
    "game-script-card-refusals",
    "parlay-lookup-errors",
    "own-open-rfqs",
)
SQLS = {
    "game-script-card-stamps": (
        parlays._SQL_GAME_SCRIPT_CARD_STAMPS,
        parlays._SQL_GAME_SCRIPT_CARD_WINDOW,
    ),
    "game-script-card-rechecks": (parlays._SQL_GAME_SCRIPT_CARD_RECHECKS,),
    "game-script-card-refusals": (parlays._SQL_GAME_SCRIPT_CARD_REFUSALS,),
    "parlay-lookup-errors": (
        parlays._SQL_PARLAY_LOOKUP_ERRORS,
        parlays._SQL_PARLAY_LOOKUP_WINDOW,
    ),
    "own-open-rfqs": (parlays._SQL_OWN_OPEN_RFQS,),
}


def _args(**kw):
    class A:
        limit = 2000
        tail = 5

    a = A()
    for k, v in kw.items():
        setattr(a, k, v)
    return a


def _conn(tmp_path):
    return db.init_db(tmp_path / "townhall.db")


def _run(conn, name, **kw):
    return QUERIES[name].run(conn, _args(**kw))


def _rows(section):
    return [dict(zip(section.columns, r)) for r in section.rows]


def _card(conn, status, combo=None, built_ms=1000):
    story = "s" if status == "built" else None
    legs = "[]" if status == "built" else None
    reason = None if status == "built" else "why"
    conn.execute(
        "INSERT INTO game_script_cards (game_event_ticker, sport_key,"
        " kickoff_ms, built_ms, status, story, legs_json, reason, combo_ticker)"
        " VALUES ('KX-G', 'nba', 5000, ?, ?, ?, ?, ?, ?)",
        (built_ms, status, story, legs, reason, combo),
    )


def _recheck_card(
    conn, recheck_status, kickoff_ms, drop_if="d", status="built", combo=None
):
    conn.execute(
        "INSERT INTO game_script_cards (game_event_ticker, sport_key,"
        " kickoff_ms, built_ms, status, story, legs_json, drop_if,"
        " recheck_status, combo_ticker)"
        " VALUES ('KX-G', 'nba', ?, 1000, ?, 's', '[]', ?, ?, ?)",
        (kickoff_ms, status, drop_if, recheck_status, combo),
    )


_FAR_FUTURE_MS = 4_102_444_800_000  # 2100-01-01


def _lookup(conn, status, error, ms=1000):
    conn.execute(
        "INSERT INTO parlay_lookups (requested_ms, card_key, stake_cents,"
        " selected_legs, status, error) VALUES (?, 'safe', 100, '[]', ?, ?)",
        (ms, status, error),
    )


_N = [0]


def _rfq(conn, status="quoted", deleted_ms=None, ms=1000, error_text=None):
    _N[0] += 1
    conn.execute(
        "INSERT INTO combo_rfqs (rfq_id, requested_ms, ticker,"
        " collection_ticker, selected_legs, exchange_index, status, deleted_ms,"
        " error_text)"
        " VALUES (?, ?, 'KXMVE-T', 'KXMVE-C', '[]', 1, ?, ?, ?)",
        (f"rfq-{_N[0]}", ms, status, deleted_ms, error_text),
    )


def test_new_querydefs_are_bounded_and_state_what_they_do_not_establish():
    for name in NEW:
        qd = QUERIES[name]
        assert qd.cost is CHEAP, name
        doc = inspect.getdoc(qd.run)
        assert "What this does not establish" in doc, name
        for sql in SQLS[name]:
            # The table is only ever read through a LIMIT-bounded subquery.
            assert "ORDER BY" in sql and sql.count("LIMIT ?") == 1, (name, sql)
            sub = sql[sql.index("(SELECT"):]
            assert "LIMIT ?" in sub, (name, sql)
            assert sql.index("LIMIT ?") < sql.rindex(")") + 1, (name, sql)


def test_the_window_binds_on_every_table(tmp_path):
    conn = _conn(tmp_path)
    for i in range(6):
        _card(conn, "built", built_ms=1000 + i)
        _lookup(conn, "error", "boom", ms=1000 + i)
        _rfq(conn, ms=1000 + i)
    conn.commit()
    _, w = _run(conn, "game-script-card-stamps", limit=4)
    assert _rows(w)[0]["rows_scanned"] == 4
    assert _rows(w)[0]["oldest_built_ms"] == 1002
    _, w = _run(conn, "parlay-lookup-errors", limit=4)
    assert _rows(w)[0]["rows_scanned"] == 4
    (o,) = _run(conn, "own-open-rfqs", limit=4)
    assert _rows(o)[0]["rows_scanned"] == 4
    assert _rows(o)[0]["open_rows"] == 4


def test_cards_built_versus_combo_stamped(tmp_path):
    conn = _conn(tmp_path)
    _card(conn, "built", combo="KXMVE-A")
    _card(conn, "built")
    _card(conn, "built")
    _card(conn, "skipped", combo=None)
    conn.commit()
    stamps, _ = _run(conn, "game-script-card-stamps")
    by = {r["status"]: r for r in _rows(stamps)}
    assert by["built"]["cards"] == 3 and by["built"]["combo_stamped"] == 1
    assert by["skipped"]["cards"] == 1 and by["skipped"]["combo_stamped"] == 0


def test_lookup_errors_by_count_and_n_bounds_the_groups(tmp_path):
    conn = _conn(tmp_path)
    for _ in range(3):
        _lookup(conn, "error", "venue 404")
    _lookup(conn, "refused", "drifted leg")
    _lookup(conn, "priced", None)
    conn.commit()
    top, window = _run(conn, "parlay-lookup-errors")
    rows = _rows(top)
    assert [(r["error"], r["lookups"]) for r in rows] == [
        ("venue 404", 3), ("drifted leg", 1)]
    assert _rows(window)[0]["rows_scanned"] == 5
    assert _rows(window)[0]["with_error"] == 4
    top, _ = _run(conn, "parlay-lookup-errors", tail=1)
    assert len(top.rows) == 1 and _rows(top)[0]["error"] == "venue 404"


def test_open_rfqs_against_the_cap(tmp_path):
    conn = _conn(tmp_path)
    _rfq(conn, "quoted", ms=1000)
    _rfq(conn, "asked", ms=2000)
    _rfq(conn, "quoted", deleted_ms=5, ms=3000)  # withdrawn
    _rfq(conn, "error", ms=4000)  # never stood
    conn.commit()
    (s,) = _run(conn, "own-open-rfqs")
    (r,) = _rows(s)
    assert r["open_rows"] == 2
    assert r["venue_cap"] == 100 and r["headroom"] == 98
    assert (r["oldest_open_ms"], r["newest_open_ms"]) == (1000, 2000)
    assert r["possibly_open"] == 0


def test_an_unknown_create_is_possibly_open_and_never_open(tmp_path):
    """#318: a create whose answer was lost is counted apart, not as closed."""
    conn = _conn(tmp_path)
    _rfq(conn, "quoted", ms=1000)
    _rfq(conn, "error", ms=2000, error_text="unknown: timed out")
    _rfq(conn, "error", ms=3000, error_text="HTTP 400 refused")
    conn.commit()
    (s,) = _run(conn, "own-open-rfqs")
    (r,) = _rows(s)
    assert r["open_rows"] == 1
    assert r["possibly_open"] == 1


def test_the_copied_unknown_prefix_matches_the_backend_constant():
    from backend.combo_rfq import UNKNOWN_CREATE_PREFIX

    assert parlays._UNKNOWN_CREATE_PREFIX == UNKNOWN_CREATE_PREFIX


def test_the_copied_venue_cap_matches_the_backend_constant():
    from backend.kalshi.rfq import MAX_OPEN_RFQS

    assert parlays._VENUE_MAX_OPEN_RFQS == MAX_OPEN_RFQS


def test_rechecks_name_the_null_group_and_exclude_future_kickoffs(tmp_path):
    conn = _conn(tmp_path)
    _recheck_card(conn, None, 5000, combo="KXMVE-A")  # minted, never re-checked
    _recheck_card(conn, None, 5000, drop_if="")
    _recheck_card(conn, "unknown", 5000, combo="KXMVE-B")
    _recheck_card(conn, "triggered", 5000, drop_if=None)
    _recheck_card(conn, None, _FAR_FUTURE_MS)  # not yet kicked off
    conn.commit()
    (sec,) = _run(conn, "game-script-card-rechecks")
    by = {(r["status"], r["recheck_status"]): r for r in _rows(sec)}
    assert set(by) == {
        ("built", "(NULL)"), ("built", "unknown"), ("built", "triggered")}
    # NULL is its own group: two past cards, one with an empty drop_if.
    assert by[("built", "(NULL)")]["cards"] == 2
    assert by[("built", "(NULL)")]["with_drop_if"] == 1
    # A minted card the re-check never reached is visible as such.
    assert by[("built", "(NULL)")]["combo_stamped"] == 1
    assert by[("built", "unknown")]["combo_stamped"] == 1
    assert by[("built", "triggered")]["combo_stamped"] == 0
    assert by[("built", "unknown")]["cards"] == 1
    assert by[("built", "triggered")]["with_drop_if"] == 0


def test_rechecks_window_binds_on_newest_past_rows(tmp_path):
    conn = _conn(tmp_path)
    for _ in range(3):
        _recheck_card(conn, "unknown", 5000)
    _recheck_card(conn, None, 5000)
    conn.commit()
    (sec,) = _run(conn, "game-script-card-rechecks", limit=1)
    assert [(r["recheck_status"], r["cards"]) for r in _rows(sec)] == [
        ("(NULL)", 1)]


def _refused(conn, status, reason, built_ms=1000):
    conn.execute(
        "INSERT INTO game_script_cards (game_event_ticker, sport_key,"
        " kickoff_ms, built_ms, status, reason)"
        " VALUES ('KX-G', 'nba', 5000, ?, ?, ?)",
        (built_ms, status, reason),
    )


def test_refusals_group_by_reason_and_leave_built_cards_out(tmp_path):
    conn = _conn(tmp_path)
    for _ in range(3):
        _refused(conn, "refused_invalid", "the card has 4 legs; it needs 2 to 3")
    _refused(conn, "refused_budget", "100 of 100 calls already made today")
    _card(conn, "built")
    _card(conn, "skipped")  # reason 'why', but not a refusal
    conn.commit()
    (top,) = _run(conn, "game-script-card-refusals")
    assert [(r["status"], r["reason"], r["cards"]) for r in _rows(top)] == [
        ("refused_invalid", "the card has 4 legs; it needs 2 to 3", 3),
        ("refused_budget", "100 of 100 calls already made today", 1),
    ]
    (top,) = _run(conn, "game-script-card-refusals", tail=1)
    assert len(top.rows) == 1 and _rows(top)[0]["cards"] == 3


def test_latest_prompt_reads_only_the_newest_version(tmp_path):
    conn = _conn(tmp_path)
    for version, drop_if in (("3", "old"), ("4", "Swayman scratched"), ("4", "X out")):
        conn.execute(
            "INSERT INTO game_script_cards (game_event_ticker, sport_key,"
            " kickoff_ms, built_ms, status, story, legs_json, drop_if,"
            " prompt_version) VALUES ('KX-G', 'nhl', 5000, 1000, 'built',"
            " 's', '[]', ?, ?)",
            (drop_if, version),
        )
    _card(conn, "refused_budget")  # no prompt_version: not the newest version
    conn.commit()
    (section,) = _run(conn, "game-script-latest-prompt")
    assert [r["drop_if"] for r in _rows(section)] == ["X out", "Swayman scratched"]
    assert "LIMIT ?" in parlays._SQL_GAME_SCRIPT_LATEST_PROMPT
    assert QUERIES["game-script-latest-prompt"].cost == CHEAP
