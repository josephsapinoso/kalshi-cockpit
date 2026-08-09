"""What rules were in force, and what the record says about each of them.

Every `recommendations` row carries `strategy_config_version`. That column is
the difference between "this tool has 400 observations" and "this tool has 400
observations *of a strategy that has been edited nine times*", and until now
nothing read it back. A config change silently splits the evidence into
incomparable halves, and the halves look identical to one continuous record.

So this module answers one question per version: **how much evidence exists
under these exact thresholds?** Not pooled, and never pooled — the CLAUDE.md
rule that a pooled number is not a finding until the parts agree applies to
this partition more sharply than to any other, because the parts are literally
different strategies.

Two distinctions this module refuses to collapse
------------------------------------------------
**"Nothing to report" is not "nobody has looked."** `lessons` has exactly one
writer — the Historian — and the Historian has never been called by anything
that runs. So an empty lessons list means the agent is unwired, not that the
record contains no lessons. Reported as `historian_has_run: false`, in the same
spirit as `analysis/marts.py` refusing to let a missing warehouse read as an
empty one. A screen showing "no lessons" over an agent that has never run is a
screen reporting a healthy silence over a disconnected wire.

**A proposal is inert until a human accepts it.** `accepted_by_user` is NULL on
every Historian proposal by construction. This module reports the count and the
diff; nothing here applies one, and no endpoint built on it should.

What this does not establish
----------------------------
That the per-version counts *support* anything. A version with nine
recommendations under it is a version with no evidence, and the counts are
returned precisely so that fact is visible rather than hidden inside a total.
Whether a version's CLV clears the noise bound is `gate.py`'s question, and it
is asked of the actionable population only.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Versions carrying fewer observations than this cannot say anything, and the
# payload says so per row rather than leaving a reader to notice. Not a filter:
# a starved version is itself a finding -- it usually means the config was
# edited more often than the slate produced games.
MIN_ROWS_TO_MEAN_ANYTHING = 100


def _loads(value: Any) -> Any:
    """Stored JSON -> object, or `None`. Never `{}` on unreadable.

    An empty config and an unparseable one would otherwise render the same, and
    only one of them means somebody should look.
    """
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        logger.warning("a strategy_configs row holds unparseable config_json")
        return None


def config_versions(conn) -> list[dict[str, Any]]:
    """Every strategy version, with the evidence recorded under each.

    The counts come from one grouped query rather than a query per version, and
    from a LEFT JOIN so a version with no rows appears with zeros instead of
    vanishing. A version that produced nothing is the most interesting row on
    this screen -- it is the one that shortened every other version's sample.
    """
    rows = conn.execute(
        """
        SELECT
            c.version,
            c.created_ms,
            c.effective_from_ms,
            c.effective_to_ms,
            c.config_json,
            c.rationale,
            c.approved_by_user,
            COUNT(r.id)                                      AS recommendations,
            COUNT(DISTINCT r.ticker)                         AS markets,
            SUM(CASE WHEN r.suppressed_reason IS NULL OR r.suppressed_reason = ''
                     THEN 1 ELSE 0 END)                      AS unsuppressed,
            SUM(CASE WHEN r.suggested_contracts > 0
                     THEN 1 ELSE 0 END)                      AS actionable,
            SUM(CASE WHEN r.clv_scored_ms IS NOT NULL
                     THEN 1 ELSE 0 END)                      AS clv_scored
        FROM strategy_configs c
        LEFT JOIN recommendations r
               ON r.strategy_config_version = c.version
        GROUP BY c.version
        ORDER BY c.version DESC
        """
    ).fetchall()

    out: list[dict[str, Any]] = []
    for row in rows:
        recommendations = int(row["recommendations"] or 0)
        out.append(
            {
                "version": int(row["version"]),
                "created_ms": int(row["created_ms"]),
                "effective_from_ms": int(row["effective_from_ms"]),
                "effective_to_ms": (
                    None if row["effective_to_ms"] is None
                    else int(row["effective_to_ms"])
                ),
                # Derived from the column, not from "is it the highest version":
                # a superseded row keeps its version number, so ordering cannot
                # answer this and would name the wrong one after a rollback.
                "is_current": row["effective_to_ms"] is None,
                "approved_by_user": bool(row["approved_by_user"]),
                "rationale": row["rationale"] or "",
                "config": _loads(row["config_json"]),
                "recommendations": recommendations,
                "markets": int(row["markets"] or 0),
                "unsuppressed": int(row["unsuppressed"] or 0),
                "actionable": int(row["actionable"] or 0),
                "clv_scored": int(row["clv_scored"] or 0),
                "has_enough_to_say_anything": (
                    recommendations >= MIN_ROWS_TO_MEAN_ANYTHING
                ),
            }
        )
    return out


def config_diff(
    older: Optional[dict[str, Any]], newer: Optional[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Which settings changed between two versions, and to what.

    Returned per key rather than as a rendered string so the caller decides how
    to show it, and so a test can assert on the change rather than on prose.
    A key present in one and absent in the other is a change too -- reported
    with `None` on the missing side rather than skipped, because a threshold
    that was deleted is exactly the kind of edit that needs to be visible.
    """
    older = older or {}
    newer = newer or {}
    changed: dict[str, dict[str, Any]] = {}
    for key in sorted(set(older) | set(newer)):
        before, after = older.get(key), newer.get(key)
        if before != after:
            changed[key] = {"from": before, "to": after}
    return changed


def lessons(conn, *, limit: int = 50) -> list[dict[str, Any]]:
    """What the Historian concluded, newest first.

    `sample_size` travels with every row because a lesson without one is an
    anecdote, and it is the number `validate_proposals` refuses on.
    """
    rows = conn.execute(
        """
        SELECT id, created_ms, title, body, evidence_json, sample_size,
               proposed_config_diff, accepted_by_user
        FROM lessons
        ORDER BY created_ms DESC, id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()

    return [
        {
            "id": int(row["id"]),
            "created_ms": int(row["created_ms"]),
            "title": row["title"],
            "body": row["body"],
            "evidence": _loads(row["evidence_json"]),
            "sample_size": (
                None if row["sample_size"] is None else int(row["sample_size"])
            ),
            "proposed_config_diff": _loads(row["proposed_config_diff"]),
            # Three states, not two. NULL is "nobody has decided", 0 is
            # "rejected", 1 is "accepted" -- and collapsing NULL into 0 would
            # turn every proposal awaiting a human into one a human refused.
            "accepted_by_user": (
                None if row["accepted_by_user"] is None
                else bool(row["accepted_by_user"])
            ),
        }
        for row in rows
    ]


def read_playbook(conn, *, limit: int = 50) -> dict[str, Any]:
    """The whole screen, in one read."""
    versions = config_versions(conn)
    entries = lessons(conn, limit=limit)

    for index, version in enumerate(versions):
        # Versions come back newest-first, so the predecessor is the *next*
        # element. Diffing against the previous element would describe every
        # change backwards, which is a sign error that renders perfectly.
        predecessor = versions[index + 1] if index + 1 < len(versions) else None
        version["changed_from_previous"] = (
            config_diff(predecessor["config"], version["config"])
            if predecessor else {}
        )

    awaiting = [
        entry for entry in entries
        if entry["proposed_config_diff"] and entry["accepted_by_user"] is None
    ]

    return {
        "config_versions": versions,
        "current_version": next(
            (v["version"] for v in versions if v["is_current"]), None
        ),
        "lessons": entries,
        "proposals_awaiting_approval": awaiting,
        # The distinction the screen must not collapse. `lessons` has one
        # writer and it has never been called by anything that runs, so an
        # empty list here is a fact about wiring, not about the record.
        "historian_has_run": bool(entries),
        "note": (
            "Every recommendation carries the version it was made under. A "
            "config change splits the evidence into halves that cannot be "
            "compared, and this is where that split is visible."
            if len(versions) > 1
            else "One config version, so the whole record is comparable."
        ),
        "min_rows_to_mean_anything": MIN_ROWS_TO_MEAN_ANYTHING,
    }
