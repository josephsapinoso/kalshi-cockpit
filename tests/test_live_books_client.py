"""The client half of the live book stream: `frontend/src/lib/liveBooks.ts`.

The shipped file is run by Node (`--experimental-strip-types`, as
`tests/test_bet_direction.py` does), so these are claims about the code the
browser runs, not a Python copy of it.

Claims:
- A book frame and a heartbeat that lists a ticker both confirm it current; a
  heartbeat that does not list it leaves its age growing.
- The feed reads silent after 25 s with no frame of any kind, and down when the
  server says so.
- `askMoved` reports a moved ask and nothing else, and never on unknowns.
- Combination tickers are not watched (their book is empty between RFQs).
- The page cap equals the server's per-client cap.

What this does not establish: the hook's `EventSource` handling, and the
screens. Neither was driven in a browser against a live feed.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.live import MAX_WATCHED_PER_CLIENT
from tests._node_driver import node_driver

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "frontend" / "src" / "lib"
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node is required")

DRIVER = """
import * as live from "./liveBooks.ts";
const steps = JSON.parse(process.argv[2]);
let state = live.EMPTY_STATE;
const out = [];
for (const step of steps) {
  if (step.frame) state = live.applyFrame(state, step.frame, step.at);
  if (step.read) {
    const r = step.read;
    out.push({
      status: live.feedStatus(state, r.now),
      age: r.ticker ? live.bookAgeMs(state, r.ticker, r.now) : null,
      ask: r.ticker ? live.liveAsk(state.books[r.ticker], r.side ?? "yes") : null,
      moved: r.ticker && "pinned" in r
        ? live.askMoved(r.pinned, live.liveAsk(state.books[r.ticker], r.side ?? "yes"))
        : null,
    });
  }
  if (step.watchable !== undefined) out.push(live.isWatchable(step.watchable));
}
console.log(JSON.stringify(out));
"""

T = "KXMLBGAME-26NOV131905NYYBOS-NYY"


def _book(**over):
    book = {
        "ticker": T,
        "yes_ask_tenths": 450, "yes_ask_display": "45c",
        "no_ask_tenths": 600, "no_ask_display": "60c",
        "yes_bid_tenths": 400, "yes_bid_display": "40c",
        "no_bid_tenths": 550, "no_bid_display": "55c",
        "yes_depth_at_ask": 200.0, "no_depth_at_ask": 300.0,
        "observed_ms": 1,
    }
    book.update(over)
    return book


def run(steps):
    with node_driver(LIB, DRIVER) as driver:
        done = subprocess.run(
            [NODE, "--experimental-strip-types", "--no-warnings", str(driver),
             json.dumps(steps)],
            capture_output=True, text=True, timeout=30,
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip())


@needs_node
class TestAges:
    def test_a_book_frame_confirms_and_its_age_counts_from_arrival(self):
        (r,) = run([
            {"frame": {"type": "book", **_book(), "at_ms": 9_999_999}, "at": 1_000},
            {"read": {"now": 4_000, "ticker": T}},
        ])
        # Local arrival (1_000), not the server's at_ms.
        assert r["age"] == 3_000
        assert r["ask"] == {"tenths": 450, "display": "45c"}

    def test_a_heartbeat_listing_the_ticker_refreshes_its_age(self):
        (r,) = run([
            {"frame": {"type": "book", **_book()}, "at": 1_000},
            {"frame": {"type": "heartbeat", "valid": [T], "down": None}, "at": 11_000},
            {"read": {"now": 12_000, "ticker": T}},
        ])
        assert r["age"] == 1_000

    def test_a_heartbeat_not_listing_it_leaves_the_age_growing(self):
        (r,) = run([
            {"frame": {"type": "book", **_book()}, "at": 1_000},
            {"frame": {"type": "heartbeat", "valid": [], "down": None}, "at": 11_000},
            {"read": {"now": 12_000, "ticker": T}},
        ])
        assert r["age"] == 11_000
        assert r["status"] == "live"


@needs_node
class TestTheFeedSaysWhenItIsNotLive:
    def test_no_frame_yet_is_connecting(self):
        (r,) = run([{"read": {"now": 5_000}}])
        assert r["status"] == "connecting"

    def test_silent_after_25_seconds_without_any_frame(self):
        reads = run([
            {"frame": {"type": "heartbeat", "valid": []}, "at": 0},
            {"read": {"now": 25_000}},
            {"read": {"now": 25_001}},
        ])
        assert [r["status"] for r in reads] == ["live", "silent"]

    def test_down_until_the_feed_is_up_again(self):
        reads = run([
            {"frame": {"type": "down", "reason": "x"}, "at": 0},
            {"read": {"now": 1}},
            {"frame": {"type": "up", "tickers": 1}, "at": 2},
            {"read": {"now": 3}},
        ])
        assert [r["status"] for r in reads] == ["down", "live"]


@needs_node
class TestAskMoved:
    def test_a_moved_ask_is_reported_with_both_prices(self):
        (r,) = run([
            {"frame": {"type": "book", **_book(yes_ask_tenths=470, yes_ask_display="47c")}, "at": 0},
            {"read": {"now": 1, "ticker": T, "pinned": 450}},
        ])
        assert r["moved"] == {"from": 450, "to": 470}

    def test_an_unmoved_ask_is_not_news(self):
        (r,) = run([
            {"frame": {"type": "book", **_book()}, "at": 0},
            {"read": {"now": 1, "ticker": T, "pinned": 450}},
        ])
        assert r["moved"] is None

    def test_unknown_on_either_side_says_nothing(self):
        reads = run([
            {"frame": {"type": "book", **_book(no_ask_tenths=None, no_ask_display=None)}, "at": 0},
            {"read": {"now": 1, "ticker": T, "side": "no", "pinned": 600}},
            {"read": {"now": 1, "ticker": T, "pinned": None}},
        ])
        assert [r["moved"] for r in reads] == [None, None]


@needs_node
class TestWhatIsWatched:
    def test_a_combination_is_not_watched(self):
        assert run([
            {"watchable": "KXMVESPORTSMULTIGAMEEXTENDED-S2026ABC"},
            {"watchable": T},
            {"watchable": ""},
        ]) == [False, True, False]


class TestTheCapsAgree:
    def test_the_page_cap_equals_the_servers_per_client_cap(self):
        text = (LIB / "liveBooks.ts").read_text(encoding="utf-8")
        (value,) = re.findall(r"export const MAX_WATCHED_PER_PAGE = (\d+);", text)
        assert int(value) == MAX_WATCHED_PER_CLIENT
