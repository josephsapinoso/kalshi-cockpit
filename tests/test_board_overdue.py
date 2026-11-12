"""A frontier ticket naming an ISO date that has passed is marked OVERDUE (#433).

Does not establish that the date is a deadline: a body citing a past
measurement and no later date is flagged too.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import board  # noqa: E402

TODAY = dt.date(2026, 11, 12)


def _node(number: int, title: str, body: str = "", state: str = "open") -> dict:
    return {
        "number": number, "title": title, "body": body, "state": state,
        "ready": True, "owner": "joe", "model": None,
    }


def _frontier_text(*nodes: dict) -> str:
    text = board.render([], list(nodes), [], [], today=TODAY)
    return text.split("WARNINGS")[0]


def _line(text: str, number: int) -> str:
    return next(ln for ln in text.splitlines() if ln.strip().startswith(f"#{number} "))


class TestOverdue:
    def test_past_date_in_title_is_marked(self):
        assert "OVERDUE" in _line(_frontier_text(_node(1, "look due 2026-11-03")), 1)

    def test_past_date_in_body_is_marked(self):
        assert "OVERDUE" in _line(_frontier_text(_node(2, "x", "revisit 2026-11-08")), 2)

    def test_future_date_is_not_marked(self):
        assert "OVERDUE" not in _line(_frontier_text(_node(3, "due 2027-01-15")), 3)

    def test_no_date_is_not_marked(self):
        assert "OVERDUE" not in _line(_frontier_text(_node(4, "no date here")), 4)

    def test_latest_date_wins(self):
        n = _node(5, "x", "measured 2026-09-01, next look 2027-01-15")
        assert "OVERDUE" not in _line(_frontier_text(n), 5)

    def test_today_itself_is_not_overdue(self):
        assert "OVERDUE" not in _line(_frontier_text(_node(6, "due 2026-11-12")), 6)

    def test_invalid_date_is_ignored(self):
        assert "OVERDUE" not in _line(_frontier_text(_node(7, "id 2026-13-40")), 7)
