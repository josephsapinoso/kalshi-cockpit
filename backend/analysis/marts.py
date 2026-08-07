"""Reading the dbt marts for the Dashboards screen.

The marts already contain the measurement discipline -- every one of them emits
a `verdict` string rather than only a number, precisely so a dashboard cannot
plot a noise-level result as though it were a finding. This module's job is to
carry those verdicts to the UI without softening them, and to be loud about the
one thing SQL cannot express: **whether the warehouse was built at all.**

Why that matters more than it sounds
------------------------------------
A missing warehouse and a warehouse containing no findings look identical
downstream -- both produce empty arrays. Rendered on a dashboard, an empty table
reads as "nothing to worry about". So `read_dashboards` distinguishes them:

- warehouse file absent      -> `WarehouseMissing`, with the command to fix it
- mart absent from the file  -> that panel reports `unavailable`, not `empty`
- mart present but empty     -> `empty`, which is a real and reportable state

The staleness of the warehouse is reported alongside every panel, because these
marts are built from a Parquet snapshot rather than live SQLite. A calibration
plot from last Tuesday is not wrong, but reading it as current is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import duckdb

logger = logging.getLogger(__name__)

# Every mart the Dashboards screen reads, and whether the screen can function
# without it. `mart_multiple_comparisons` is required because it is the panel
# that qualifies all the others -- rendering per-bucket findings without the
# count of tests behind them is the exact error it exists to prevent.
MARTS: dict[str, bool] = {
    "mart_multiple_comparisons": True,
    "mart_clv_by_bucket": True,
    "mart_calibration": True,
    "mart_suppression_audit": False,
    "mart_fee_reconciliation": False,
}


class WarehouseMissing(RuntimeError):
    """Raised when the DuckDB file does not exist.

    Distinct from an empty mart, and deliberately not caught and rendered as
    "no data": an unbuilt warehouse is an operational problem, not a finding.
    """


@dataclass
class Panel:
    """One mart, plus the state it is in."""

    name: str
    status: str                      # "ok" | "empty" | "unavailable"
    rows: list[dict[str, Any]] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "rows": self.rows,
            "note": self.note,
        }


def _read_mart(conn: duckdb.DuckDBPyConnection, name: str) -> Panel:
    try:
        cursor = conn.execute(f"select * from {name}")  # noqa: S608 - fixed names
    except duckdb.CatalogException:
        return Panel(
            name=name,
            status="unavailable",
            note=(
                f"{name} is not in the warehouse. Run `dbt build` in warehouse/. "
                f"Until then this panel is unknown, not empty."
            ),
        )

    columns = [description[0] for description in cursor.description]
    rows = [dict(zip(columns, record)) for record in cursor.fetchall()]

    if not rows:
        return Panel(
            name=name,
            status="empty",
            note=f"{name} built successfully and produced no rows.",
        )
    return Panel(name=name, status="ok", rows=rows)


def read_dashboards(warehouse_path: Path | str) -> dict[str, Any]:
    """Read every dashboard mart, with the warehouse's own freshness attached.

    Raises `WarehouseMissing` rather than returning empty panels, because an
    empty dashboard is indistinguishable from a healthy one with nothing to
    report -- and only one of those needs someone to do something.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise WarehouseMissing(
            f"No warehouse at {path}. The Dashboards screen reads dbt marts "
            f"built over the Parquet lake, so it needs both steps: "
            f"`python -m backend.store.publish` to snapshot SQLite to Parquet, "
            f"then `dbt build` in warehouse/. Showing an empty dashboard instead "
            f"would read as 'nothing to report', which is not what this is."
        )

    # Read-only: the API process must never be able to mutate the warehouse,
    # and a second writer would fail on DuckDB's single-writer lock anyway.
    conn = duckdb.connect(str(path), read_only=True)
    try:
        panels = {name: _read_mart(conn, name) for name in MARTS}
    finally:
        conn.close()

    missing_required = [
        name for name, required in MARTS.items()
        if required and panels[name].status == "unavailable"
    ]
    if missing_required:
        logger.warning(
            "dashboards: required marts missing from the warehouse: %s",
            ", ".join(missing_required),
        )

    built_ms = int(path.stat().st_mtime * 1000)
    return {
        "warehouse_built_ms": built_ms,
        # Named rather than implied. These marts are built from a Parquet
        # snapshot, so they lag live SQLite by however long since `publish` ran.
        "freshness_note": (
            "Built from the Parquet snapshot, not live SQLite. Numbers here lag "
            "the Board by however long since the last publish."
        ),
        "missing_required_marts": missing_required,
        "panels": {name: panel.to_dict() for name, panel in panels.items()},
    }


def headline_verdicts(dashboards: dict[str, Any]) -> list[str]:
    """The verdict strings, in the order they should be read.

    `mart_multiple_comparisons` comes first and is not optional. It is the
    single row that says how many tests produced the findings below it, and
    reading any per-bucket result without it is how ten cells and one
    two-sigma hit becomes "we found something".
    """
    ordered: list[str] = []
    for name in MARTS:
        panel = dashboards["panels"].get(name, {})
        if panel.get("status") != "ok":
            continue
        for row in panel["rows"]:
            verdict = row.get("verdict")
            if verdict:
                ordered.append(f"{name}: {verdict}")
    return ordered
