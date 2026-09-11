"""The exposure line on the buy ticket: what it says, and what it may not do.

ADR 0112 removed all five brakes from the hand-bet path. Those caps were the
only thing in the product that read Joe's exposure before a bet, so after they
went, nothing on any screen carried it -- and `/parlays`, the screen all four
real combination fills were placed on, fetched no position data at all. The
line goes INSIDE `ManualTicket.tsx` because that is the one edit that reaches
all seven surfaces a bet can start from.

Two halves, tested two ways.

**The words**, under node. `lib/exposureLine.ts` is React-free and pure for
exactly this reason: the property is a branch table over the server payload,
and the failure mode is a branch that substitutes `$0.00` for a refusal. The
module runs against the payload `backend/bets.open_positions` really produces,
off a real database -- the same shape `tests/test_open_positions_stamp.py`
takes, and for the same reason a substring assertion over the component would
not have answered it.

**The posture**, over `ManualTicket.tsx`'s source with comments stripped
(`code_only`, the `test_crew_bubble` lesson): the exposure state must not
reach `canConfirm`, `disabled`, or any early return. A gate here would be a
sixth ceiling on a hand bet, which is a reversal of ADR 0112 and not a
feature. The component reads `QuoteAge`'s posture in `PriceOnKalshi.tsx`:
relabel, never block.

What this establishes
---------------------
- Every refusing payload produces the SERVER's sentence and no dollar sign.
- A readable payload produces the server's display string, the count, and the
  clock of the read that produced it -- the COUNT's clock, never the value's.
- A fresh venue holding nothing says so in words rather than printing $0.00.
- The buy button's `canConfirm` does not read the exposure state, and no
  branch of the ticket returns early on it.
- All seven mount points still mount `<ManualTicket`, so "one edit reaches
  seven surfaces" stays true rather than becoming a comment.

What it does NOT establish
--------------------------
That the served figure is right (`tests/test_exposure_route.py` and
`tests/test_venue_positions.py` own that), that the line is legible, or that
the fetch is wired correctly in the browser -- `next build` and a browser say
that.

The mutation table is in `tests/test_exposure_route.py`'s docstring, not
repeated here: the nine mutations were run against both files together,
because a screen guard and a server guard on the same figure are worth
nothing separately, and two copies of one table is one copy that goes stale.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend import bets
from backend.store import db

sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_desk_panels import code_only  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
LIB = REPO / "frontend" / "src" / "lib"
MODULE = LIB / "exposureLine.ts"
TICKET = REPO / "frontend" / "src" / "components" / "ManualTicket.tsx"

NODE = shutil.which("node")

TZ = "America/Los_Angeles"

nodeless = pytest.mark.skipif(
    NODE is None,
    reason=(
        "node is not on PATH. Skipped rather than xfailed: the guard is real "
        "where node exists (CI and both dev machines)."
    ),
)

_DRIVER = """
import { exposureUnreadable, exposureWords } from "./_exposure_under_test.ts";
const [block, timeZone] = [JSON.parse(process.argv[2]), process.argv[3]];
console.log(JSON.stringify({
  words: exposureWords(block, timeZone),
  unreadable: exposureUnreadable("the request never left."),
}));
"""


def words(block: dict) -> dict:
    """Run the SHIPPED module under node over a real server payload.

    The module is copied beside itself with its one relative specifier given
    an extension, because node resolves ESM specifiers literally while the
    bundler does not. Nothing else about it is changed, and the copy is
    removed whatever happens -- a stray `.ts` in `lib/` would be compiled by
    `next build`.
    """
    source = MODULE.read_text(encoding="utf-8").replace(
        'from "./openPositionsStamps"', 'from "./openPositionsStamps.ts"'
    )
    under_test = LIB / "_exposure_under_test.ts"
    driver = LIB / "_exposure_driver.mjs"
    under_test.write_text(source, encoding="utf-8")
    driver.write_text(_DRIVER, encoding="utf-8")
    try:
        out = subprocess.run(
            [
                NODE,
                "--experimental-strip-types",
                str(driver),
                json.dumps(block),
                TZ,
            ],
            capture_output=True,
            text=True,
            # Node writes UTF-8; without this Windows decodes with the ANSI
            # code page and an em dash comes back as U+FFFD.
            encoding="utf-8",
            timeout=60,
            cwd=str(LIB),
        )
    finally:
        under_test.unlink(missing_ok=True)
        driver.unlink(missing_ok=True)
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip())


def served(
    tmp_path,
    *,
    positions_ms=None,
    row_count=0,
    exposures=(),
    balance_ms=None,
    now_ms=1_757_000_000_000,
) -> dict:
    """The payload `/api/exposure` really serves, off a real database."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    conn = db.init_db(tmp_path / "e.db")
    if positions_ms is not None:
        cur = conn.execute(
            "INSERT INTO poll_log (polled_ms, endpoint, ok, row_count, mirrored) "
            "VALUES (?, 'positions', 1, ?, 1)",
            (positions_ms, row_count),
        )
        for i, tenths in enumerate(exposures):
            conn.execute(
                "INSERT INTO venue_positions "
                "(poll_log_id, polled_ms, ticker, exposure_tenths) "
                "VALUES (?, ?, ?, ?)",
                (cur.lastrowid, positions_ms, f"KXTEST-{i}", tenths),
            )
    if balance_ms is not None:
        conn.execute(
            "INSERT INTO venue_balance_snapshots "
            "(observed_ms, balance_tenths, portfolio_value_tenths) "
            "VALUES (?, 2560, 0)",
            (balance_ms,),
        )
    conn.commit()
    return bets.open_positions(conn, now_ms=now_ms)


NOW = 1_757_000_000_000
POSITIONS_MS = NOW - 4 * 60 * 1000        # fresh; the count's own read
BALANCE_MS = NOW - 90_000                 # fresh; a DIFFERENT read
STALE_MS = NOW - 6 * 3600 * 1000          # past the 30-minute bound


class TestAReadableFigureIsShownWithItsOwnClock:
    @nodeless
    def test_the_servers_display_string_and_the_count_are_both_said(
        self, tmp_path
    ):
        """Two positions, $22.00 in. The string is the server's; nothing here
        divides money by a thousand."""
        block = served(
            tmp_path, positions_ms=POSITIONS_MS, row_count=2,
            exposures=(12_340, 9_660), now_ms=NOW,
        )
        assert block["staked_display"] == "$22.00"
        out = words(block)["words"]
        assert out["refused"] is False
        assert "$22.00" in out["headline"]
        # What the money is ON travels inside the emphasised string, never in
        # the muted qualifier beside it: `/slate` printed a bold "$X staked"
        # twice for two different numbers, and the muted words that told them
        # apart were not what the eye took (`OpenPositions.tsx`).
        assert "2 open positions" in out["headline"]
        assert out["qualifier"] is not None
        assert "$" not in out["qualifier"]

    @nodeless
    def test_one_position_is_singular(self, tmp_path):
        block = served(
            tmp_path, positions_ms=POSITIONS_MS, row_count=1,
            exposures=(5_000,), now_ms=NOW,
        )
        out = words(block)["words"]
        assert "1 open position" in out["headline"]
        assert "positions" not in out["headline"]

    @nodeless
    def test_the_stamp_is_the_positions_read_and_never_the_balance_read(
        self, tmp_path
    ):
        """The two figures ride one cadence and are two reads. The staked
        figure is selected by the very poll whose `row_count` is the count,
        so the count's clock is its own -- and borrowing the balance's is the
        defect `openPositionsStamps.ts` exists to have made impossible."""
        block = served(
            tmp_path, positions_ms=POSITIONS_MS, row_count=1,
            exposures=(5_000,), balance_ms=BALANCE_MS, now_ms=NOW,
        )
        assert block["count_as_of_ms"] != block["value_as_of_ms"]
        out = words(block)["words"]
        assert out["stamp"] is not None
        # 4 minutes for the positions poll, 1 minute for the balance. The
        # stamp must carry the former.
        assert "4m ago" in out["stamp"]
        assert "1m ago" not in out["stamp"]
        assert out["stamp"].startswith("counted ")

    @nodeless
    def test_a_fresh_empty_venue_says_nothing_open_rather_than_zero_dollars(
        self, tmp_path
    ):
        """Count 0 and $0.00 from the same successful read is knowledge, not a
        refusal -- but two spellings of nothing on one line is noise, so it is
        said once, in words."""
        block = served(
            tmp_path, positions_ms=POSITIONS_MS, row_count=0, now_ms=NOW
        )
        assert block["staked_display"] == "$0.00"
        out = words(block)["words"]
        assert out["refused"] is False
        assert "$" not in out["headline"]
        assert "nothing open" in out["headline"].lower()


class TestEveryRefusalIsTheServersWordsAndNeverADollarSign:
    @nodeless
    def test_a_never_polled_record_refuses_and_carries_no_clock(self, tmp_path):
        block = served(tmp_path, now_ms=NOW)
        out = words(block)["words"]
        assert out["refused"] is True
        assert "$" not in out["headline"]
        assert block["staked_refusal"] in out["headline"]
        assert out["stamp"] is None

    @nodeless
    def test_a_stale_read_refuses_in_words_and_keeps_its_clock(self, tmp_path):
        """"Not read since" is the sentence a dead poller must produce. A
        `$0.00` here would report nothing at risk off an unread mirror, which
        is the false negative in the flattering direction."""
        block = served(
            tmp_path, positions_ms=STALE_MS, row_count=2,
            exposures=(4_000, 6_000), now_ms=NOW,
        )
        out = words(block)["words"]
        assert out["refused"] is True
        assert "$" not in out["headline"]
        assert block["staked_refusal"] in out["headline"]
        assert out["stamp"] is not None and "6h ago" in out["stamp"]

    @nodeless
    def test_a_mirror_mismatch_refuses_the_money_and_still_reports_the_count(
        self, tmp_path
    ):
        """An integrity failure: the poll counted two rows and one was kept.
        The count is readable and the money is not, and the line must not
        round that to either extreme."""
        block = served(
            tmp_path, positions_ms=POSITIONS_MS, row_count=2,
            exposures=(4_000,), now_ms=NOW,
        )
        assert block["count"] == 2 and block["staked_display"] is None
        out = words(block)["words"]
        assert out["refused"] is True
        assert "$" not in out["headline"]
        assert "2 positions are open" in out["headline"]
        assert block["staked_refusal"] in out["headline"]

    @nodeless
    def test_a_backend_one_version_behind_refuses_rather_than_saying_nothing(
        self, tmp_path
    ):
        """Silence at a buy button reads as "nothing", and nothing is the one
        thing an absent field has not established."""
        out = words({
            "count": None,
            "count_as_of_ms": None,
            "count_age_ms": None,
            "value_tenths": None,
            "value_display": None,
            "value_as_of_ms": None,
            "value_age_ms": None,
            "value_refusal": None,
        })["words"]
        assert out["refused"] is True
        assert "$" not in out["headline"]
        assert out["stamp"] is None

    @nodeless
    def test_an_unreachable_route_refuses_in_the_same_shape(self, tmp_path):
        """A thrown fetch is a connection report, not a figure. It ends with
        the same sentence every other refusal does."""
        out = words(served(tmp_path, now_ms=NOW))["unreadable"]
        assert out["refused"] is True
        assert "$" not in out["headline"]
        assert out["headline"].endswith(
            "That is not the same as nothing at risk."
        )

    @nodeless
    def test_every_refusal_ends_by_saying_it_is_not_nothing(self, tmp_path):
        """The one sentence that turns a technicality into a fact about the
        tap about to happen."""
        for block in (
            served(tmp_path / "a", now_ms=NOW),
            served(tmp_path / "b", positions_ms=STALE_MS, row_count=1,
                   exposures=(1_000,), now_ms=NOW),
            served(tmp_path / "c", positions_ms=POSITIONS_MS, row_count=2,
                   exposures=(1_000,), now_ms=NOW),
        ):
            out = words(block)["words"]
            assert out["refused"] is True
            assert out["headline"].endswith(
                "That is not the same as nothing at risk."
            )
            # A refusal carries no muted aside: the whole of it is the fact.
            assert out["qualifier"] is None


class TestTheLineInformsAndNeverBlocks:
    def test_the_confirm_predicate_does_not_read_the_exposure_state(self):
        """ADR 0112 removed all five ceilings on a hand bet. A gate here would
        be the sixth, under a new name."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        predicate = text.split("const canConfirm =")[1].split(";")[0]
        assert "exposure" not in predicate
        assert "words" not in predicate

    def test_nothing_disabled_on_the_ticket_reads_the_exposure_state(self):
        """Every `disabled=` on the ticket, checked one by one: the side
        buttons, the steppers, the acknowledgement and the confirm."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        for match in re.findall(r"disabled=\{([^}]*)\}", text):
            assert "exposure" not in match, match
            assert "refused" not in match, match

    def test_no_branch_of_the_ticket_returns_early_on_the_exposure_read(self):
        """A `blocked` phase or an early `return null` on a failed exposure
        read would hide the whole ticket behind a read that is allowed to
        fail. The state is rendered by one component and consulted nowhere
        else."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        uses = [
            line for line in text.splitlines()
            if re.search(r"\bexposure\b", line)
        ]
        assert uses, "the exposure state is gone from the ticket"
        for line in uses:
            assert "return" not in line or "Exposure" in line, line
            assert "setPhase" not in line, line

    def test_the_read_is_not_awaited_inside_the_book_read(self):
        """`openTicket` must not wait on `/api/exposure`: a slow or dead
        record has no business delaying the live ask by a millisecond."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        open_ticket = text.split("const openTicket =")[1].split(
            "const confirm ="
        )[0]
        assert "fetchExposure" not in open_ticket

    def test_the_ticket_renders_the_line_and_its_clock(self):
        """The figure and the stamp both reach the screen. A stale exposure
        number that does not say it is stale is worse than none."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        assert "<Exposure words={exposure} />" in text
        assert "{words.headline}" in text
        assert "{words.stamp}" in text
        assert "{words.qualifier}" in text

    def test_the_term_is_taught_rather_than_assumed(self):
        """Joe asked to be educated, not shielded: every betting term is
        defined at first use through the glossary."""
        text = code_only(TICKET.read_text(encoding="utf-8"))
        assert 'Term k="exposure"' in text
        glossary = (LIB / "glossary.ts").read_text(encoding="utf-8")
        assert "exposure: {" in glossary


class TestOneEditReachesSevenSurfaces:
    def test_every_mount_point_still_mounts_the_ticket(self):
        """The claim that justifies putting the line inside the component
        rather than on each screen. If a surface stops mounting
        `<ManualTicket`, it silently stops showing exposure too."""
        mounts = [
            "components/LiveBoard.tsx",
            "components/MarketSearch.tsx",
            "components/ParlayCards.tsx",
            "components/PriceOnKalshi.tsx",
            "components/SlateRow.tsx",
            "app/market/[ticker]/page.tsx",
            "app/slate/page.tsx",
        ]
        for rel in mounts:
            text = (REPO / "frontend" / "src" / rel).read_text(encoding="utf-8")
            assert "<ManualTicket" in code_only(text), rel
        assert len(mounts) == 7


#: The `exposure` gloss, ratified by Joe 2026-09-11.
#:
#: **It replaced a false reassurance, which is why it is pinned in words.**
#: The definition used to end "The exposure cap bounds that total, so one bad
#: night cannot take the whole bankroll." ADR 0112 removed all five brakes from
#: the hand-bet path on Joe's own instruction, so that sentence has been false
#: on the path he actually uses since 2026-09-08 -- and this gloss renders AT
#: THE BUY BUTTON, which makes it the worst place in the product to carry a
#: comforting untruth. Corrected 2026-09-11, put to Joe with the alternative,
#: and kept on his answer.
#:
#: A future session looking at "nothing caps it" will read it as alarming copy
#: and be tempted to soften it. It is not alarming; it is the fact, and the
#: softer version is the one that was wrong.
RATIFIED_EXPOSURE_GLOSS = (
    "The total you could lose if every bet you have open lost, fees "
    "included. Hold two $20 bets and you are $40 exposed. Nothing caps "
    "it on a bet you place by hand \u2014 that is why the ticket shows it."
)

#: The claim ADR 0112 falsified. It may not come back in any spelling.
KILLED_EXPOSURE_CLAIMS = (
    "exposure cap bounds",
    "cannot take the whole bankroll",
)


class TestTheExposureGlossIsJoesRatifiedCopy:
    """Ratified 2026-09-11. Same force as the #9 tab ledes: the words are
    his, and a correctness patch is not a licence to reword them."""

    def _gloss(self) -> str:
        text = (LIB / "glossary.ts").read_text(encoding="utf-8")
        start = text.index("exposure: {")
        block = text[start : text.index("},", start)]
        # The definition only -- the sibling `label` is also a quoted string.
        return block[block.index("definition:") :]

    def test_the_ratified_sentence_is_on_the_ticket_verbatim(self):
        """Verbatim after the string concatenation the file is written in."""
        joined = "".join(re.findall(r'"([^"]*)"', self._gloss()))
        assert joined == RATIFIED_EXPOSURE_GLOSS, (
            "the exposure gloss changed. It is Joe's ratified copy "
            "(2026-09-11) and renders at the buy button; changing it is his "
            "call, not a passing edit.\n"
            f"  found:  {joined!r}\n"
            f"  wanted: {RATIFIED_EXPOSURE_GLOSS!r}"
        )

    def test_the_falsified_cap_claim_cannot_return(self):
        """The half that makes this a guard rather than a snapshot. ADR 0112
        removed the caps; copy that promises one is false on the hand-bet
        path, and false in the flattering direction."""
        gloss = self._gloss()
        for claim in KILLED_EXPOSURE_CLAIMS:
            assert claim not in gloss, (
                f"the exposure gloss says {claim!r} again. ADR 0112 removed "
                "all five brakes from the hand-bet path -- there is no cap to "
                "promise, and this string renders at the buy button."
            )

    def test_the_gloss_teaches_with_a_worked_example(self):
        """Joe is a beginner and asked to be educated, not shielded: a
        definition without a number is a definition he has to translate."""
        gloss = self._gloss()
        assert "$20" in gloss and "$40" in gloss, (
            "the worked example is gone; a bare definition is what the "
            "glossary exists to avoid"
        )
