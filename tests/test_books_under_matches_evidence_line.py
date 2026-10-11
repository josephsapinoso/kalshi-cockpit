"""A Games row's "x/N books under" must count the books its evidence line counts.

Ticket #353. The Games row printed "0/5 books under" (the `Books` helper:
`row.books.book_count`, every book that quoted the outcome) beside "1 book(s),
need 2" (`TrustNote`, printing `core/trust.py`'s `books` check, which is fed
`fair_prices.book_count`, the books that survived anchoring). Two populations,
one noun. `books_below` exists only for the first, and the payload carries no
per-book list to recompute it for the second, so the decision (partner, on the
ticket) is: print the figure only when both denominators are the same number,
otherwise print none.

**The payload is real route output, not a hand-built dict.** No captured
`/api/slate` response exists under `tests/fixtures/`, so the rows come from the
repo's own `/api/slate` over the seeded demo database -- the same route code
the browser calls. Its seed carries the disagreeing case (5 usable books, 1
anchored). The seed is synthetic data, not a live capture; that is the one
thing this does not establish.

The shipped `booksUnderFigure` is lifted out of `slate/page.tsx` by its marker
comments and executed under node, so the assertion is on what it returns for
each real row, and a copy of the old behaviour (no comparison) is run through
the same driver to show the test goes red on it.

Establishes: on every seeded row whose evidence line says "N book(s)", the
figure is either absent or has denominator N; at least one seeded row
disagrees and prints nothing; an agreeing pair still prints. Does not
establish: how the replacement cell lays out at 390px.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from tests._node_driver import node_driver

from backend.api.routes import create_app
from backend.config import AppConfig
from backend.seed_demo import seed_all

REPO = Path(__file__).resolve().parents[1]
PAGE = REPO / "frontend" / "src" / "app" / "slate" / "page.tsx"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is not on PATH; skipped, not xfailed"
)

START = "// BOOKS-UNDER-FIGURE-START"
END = "// BOOKS-UNDER-FIGURE-END"


def shipped_helper_source() -> str:
    text = PAGE.read_text(encoding="utf-8")
    assert START in text and END in text, "marker comments missing from page.tsx"
    body = text.split(START, 1)[1].split(END, 1)[0]
    # The START line is a comment that continues on the next line; drop it.
    return body.split("\n", 2)[2]


# The behaviour #353 removed: print books_below/book_count unconditionally.
OLD_HELPER = """
function booksUnderFigure(
  books: { book_count: number; books_below: number } | null | undefined,
  anchoredBookCount: number | null | undefined,
): string | null {
  if (!books || books.book_count === 0) return null;
  return `${books.books_below}/${books.book_count} books under`;
}
"""

_DRIVER = """
import { booksUnderFigure } from "./helper.ts";
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(([b, a]) => booksUnderFigure(b, a))));
"""


def run_helper(source: str, cases: list, tmp_path: Path) -> list:
    (tmp_path / "helper.ts").write_text(
        source + "\nexport { booksUnderFigure };\n", encoding="utf-8"
    )
    with node_driver(tmp_path, _DRIVER) as driver:
        out = subprocess.run(
            [NODE, "--experimental-strip-types", str(driver), json.dumps(cases)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            cwd=str(tmp_path),
        )
    assert out.returncode == 0, f"node failed:\n{out.stdout}\n{out.stderr}"
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.fixture(scope="module")
def seeded_rows(tmp_path_factory):
    import asyncio

    path = tmp_path_factory.mktemp("books353") / "demo.db"
    seed_all(path)
    app = create_app(AppConfig(instance_mode="demo", db_path=path))

    async def fetch():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return (await c.get("/api/slate")).json()["rows"]

    return asyncio.run(fetch())


def evidence_book_count(row: dict) -> int | None:
    """The N in the evidence line's "N book(s), need M" -- the trust check's
    own detail string, which `TrustNote` prints verbatim."""
    for check in (row.get("trust") or {}).get("checks", []):
        m = re.match(r"(\d+) book\(s\), need \d+", check.get("detail") or "")
        if m:
            return int(m.group(1))
    return None


def figure_cases(rows: list) -> list:
    return [[r.get("books"), r.get("book_count")] for r in rows]


class TestFigureAgreesWithEvidenceLine:
    def test_the_seed_carries_the_disagreeing_case(self, seeded_rows):
        """Else the test below is vacuous."""
        disagree = [
            r
            for r in seeded_rows
            if r.get("books")
            and evidence_book_count(r) is not None
            and r["books"]["book_count"] != evidence_book_count(r)
        ]
        assert disagree, "no seeded row has usable books != evidence-line books"

    def test_no_figure_has_a_denominator_the_evidence_line_contradicts(
        self, seeded_rows, tmp_path
    ):
        figures = run_helper(shipped_helper_source(), figure_cases(seeded_rows), tmp_path)
        checked = 0
        for row, fig in zip(seeded_rows, figures):
            n = evidence_book_count(row)
            if n is None or fig is None:
                continue
            checked += 1
            assert fig.split("/")[1].split(" ")[0] == str(n), (
                f"{row['ticker']}: evidence line says {n} book(s) but the row "
                f"prints {fig!r}"
            )
        assert checked, "no row printed a figure to compare; seed has no agreeing row"

    def test_a_disagreeing_row_prints_no_figure(self, seeded_rows, tmp_path):
        figures = run_helper(shipped_helper_source(), figure_cases(seeded_rows), tmp_path)
        for row, fig in zip(seeded_rows, figures):
            n = evidence_book_count(row)
            if row.get("books") and n is not None and row["books"]["book_count"] != n:
                assert fig is None, f"{row['ticker']} printed {fig!r} beside {n} book(s)"

    def test_agreeing_counts_still_print_and_unreadable_counts_do_not(self, tmp_path):
        b = {"book_count": 1, "books_below": 0}
        got = run_helper(
            shipped_helper_source(),
            [[b, 1], [b, None], [{"book_count": 0, "books_below": 0}, 0], [None, 1]],
            tmp_path,
        )
        assert got == ["0/1 books under", None, None, None]


class TestTheComparisonIsLoadBearing:
    def test_the_old_helper_fails_the_agreement_check(self, seeded_rows, tmp_path):
        """The mutation, run through the same driver: without the comparison a
        disagreeing row prints a figure, which is what the checks above refuse."""
        figures = run_helper(OLD_HELPER, figure_cases(seeded_rows), tmp_path)
        printed_wrong = [
            r["ticker"]
            for r, fig in zip(seeded_rows, figures)
            if fig is not None
            and evidence_book_count(r) is not None
            and fig.split("/")[1].split(" ")[0] != str(evidence_book_count(r))
        ]
        assert printed_wrong, "the old helper agrees with the evidence line; test is decoration"


class TestTheRowCallsIt:
    def test_books_renders_the_helper_result_not_its_own_counts(self):
        text = PAGE.read_text(encoding="utf-8")
        assert "booksUnderFigure(books, row.book_count)" in text
        assert "{books.books_below}/{books.book_count} books under" not in text
