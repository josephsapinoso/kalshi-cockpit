"""`/api/scout`: the scout desk (ADR 0060) -- convene, overview, briefing.

Moved verbatim from `backend/api/routes.py` on 2026-09-04; see
`backend/api/routers/__init__.py` for the `register()` shape and why. The two
helpers at the top (`_resolve_scout_fixture`, `_run_scout_desk`) were closure
locals beside the handlers and travel with them.

This is the API's one caller of the billed path: `send_scout_desk` re-checks
`AgentBudget.refusal_reason` before accepting a request, and `build_client` is
referenced only inside the background task `convene_desk` consumes.
`tests/test_has_callers.py`'s `BILLED_PATH_CALL_SITES` names this module for
that reason, and a second module that references `build_client` fails there.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException

from ...agents import scout_desk
from ...agents.base import AgentConfig, build_client
from ...agents.budget import AgentBudget
from ...config import AppConfig
from ...store import db

logger = logging.getLogger(__name__)


def register(
    app: FastAPI, *, app_config: AppConfig, get_conn, require_auth
) -> None:
    """Attach the three scout handlers to `app`, in their original order."""

    def _resolve_scout_fixture(conn, ticker: str) -> Optional[dict]:
        """Who plays whom, from the linked sportsbook fixture. `None` if unlinked.

        Teams, league and start come from `odds_snapshots`, never from Kalshi:
        `kalshi_events.commence_ms` is the raw `occurrence_datetime`, ~3 hours
        late on game series (ADR 0006), and Kalshi titles do not carry a
        home/away split at all. A ticker with no linked fixture cannot be
        scouted -- the desk would not know which two clubs to cover -- and that
        refusal is honest rather than a guess from parsing a ticker string.
        """
        link = conn.execute(
            "SELECT l.odds_event_id, e.title AS event_title "
            "FROM recommendations r "
            "JOIN event_links l ON l.id = r.link_id "
            "LEFT JOIN kalshi_markets m ON m.ticker = r.ticker "
            "LEFT JOIN kalshi_events e ON e.event_ticker = m.event_ticker "
            "WHERE r.ticker = ? "
            "ORDER BY r.created_ms DESC, r.id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not link:
            return None
        # SQLite's bare-column rule: with a lone MIN() aggregate, the bare
        # columns come from the row that achieved the minimum -- the earliest
        # snapshot, whose team names are as good as any (they never change
        # within one fixture).
        fixture = conn.execute(
            "SELECT home_team, away_team, sport_key, "
            "       MIN(commence_ms) AS commence_ms "
            "FROM odds_snapshots WHERE odds_event_id = ?",
            (link["odds_event_id"],),
        ).fetchone()
        if not fixture or fixture["home_team"] is None:
            return None
        title = link["event_title"] or (
            f"{fixture['away_team']} at {fixture['home_team']}"
        )
        return {
            "event_title": title,
            "league": fixture["sport_key"],
            "home_team": fixture["home_team"],
            "away_team": fixture["away_team"],
            "commence_ms": fixture["commence_ms"],
        }

    # A `running` row older than this is reported as gone quiet: the process
    # that owned it cannot come back to finish it after a restart, and a row
    # that looks alive forever would pin the button in its spinner state.
    SCOUT_DESK_PATIENCE_MS = 15 * 60 * 1000

    async def _run_scout_desk(row_id: int, config: AgentConfig, fixture: dict,
                              ticker: str) -> None:
        """The background half of one convening. Owns its own connection.

        Runs on the API process's event loop after the POST has already
        returned 202, so nothing here may raise out: every failure ends in the
        row being marked `failed`, because a briefing that dies silently is
        indistinguishable from one still running.
        """
        conn = db.open_db(app_config.db_path)
        try:
            budget = AgentBudget.from_config(conn, config)
            client = build_client(config)
            commence_iso = (
                datetime.fromtimestamp(
                    fixture["commence_ms"] / 1000, tz=timezone.utc
                ).isoformat()
                if fixture["commence_ms"] is not None
                else None
            )
            result = await asyncio.wait_for(
                scout_desk.convene_desk(
                    client,
                    config,
                    budget,
                    ticker=ticker,
                    event_title=fixture["event_title"],
                    league=fixture["league"],
                    commence_iso=commence_iso,
                    home_team=fixture["home_team"],
                    away_team=fixture["away_team"],
                    now_ms=db.now_ms(),
                ),
                # The desk is three web-searching calls; the longest plausible
                # convening is minutes. Ten is a backstop, not a target.
                timeout=600,
            )
            staff_json = json.dumps(
                [
                    {
                        "role": note.role,
                        "team": note.team,
                        "report": (
                            None
                            if note.report is None
                            else note.report.model_dump()
                        ),
                    }
                    for note in result.staff
                ]
            ) if result.staff else None
            briefing_json = (
                result.briefing.model_dump_json()
                if result.briefing is not None
                else None
            )
            # NULL when the seat filed nothing — never `{}`. The absence
            # reason is logged at convening time and not stored: on read,
            # "predates the seat" and "filed nothing" render the same
            # honest words, and a stored reason would age into a claim
            # about a budget day long over. See ADR 0069.
            sharp_json = (
                result.sharp.model_dump_json()
                if result.sharp is not None
                else None
            )
            conn.execute(
                "UPDATE scout_briefings SET status = ?, completed_ms = ?, "
                "staff_json = ?, briefing_json = ?, sharp_json = ?, "
                "refusal_reason = ? WHERE id = ?",
                (
                    result.status,
                    db.now_ms(),
                    staff_json,
                    briefing_json,
                    sharp_json,
                    result.refusal_reason,
                    row_id,
                ),
            )
            conn.commit()
        except Exception:
            logger.exception("scout desk convening %d died", row_id)
            conn.execute(
                "UPDATE scout_briefings SET status = 'failed', "
                "completed_ms = ? WHERE id = ?",
                (db.now_ms(), row_id),
            )
            conn.commit()
        finally:
            conn.close()

    @app.post(
        "/api/scout/{ticker}",
        dependencies=[Depends(require_auth)],
        status_code=202,
    )
    async def send_scout_desk(ticker: str) -> dict:
        """Send the scout desk on one game. Four metered Anthropic calls.

        202 with a row id, never the briefing: the desk takes minutes and a
        phone must not hold a request open that long. The caller polls the GET.
        The answer is `accepted`, not `briefed` -- the same honesty rule as
        `/api/odds/refresh`.

        Auth is required because this route spends money (ADR 0060). The spend
        itself is bounded server-side by `AgentBudget` against the same
        `agent_calls` day the Skeptic draws from, so the cookie-holding client
        cannot raise the ceiling however many times it taps.
        """
        config = AgentConfig.from_env()
        if config is None:
            raise HTTPException(
                status_code=503,
                detail="No ANTHROPIC_API_KEY configured, so the desk cannot "
                       "be paid. This is a configuration state, not a refusal.",
            )
        write_conn = db.open_db(app_config.db_path)
        try:
            fixture = _resolve_scout_fixture(write_conn, ticker)
            if fixture is None:
                raise HTTPException(
                    status_code=422,
                    detail=f"{ticker} has no linked sportsbook fixture, so the "
                           f"desk cannot tell which two clubs to cover. Only "
                           f"games the matcher linked can be scouted.",
                )
            now = db.now_ms()
            running = write_conn.execute(
                "SELECT id FROM scout_briefings WHERE ticker = ? "
                "AND status = 'running' AND requested_ms > ? LIMIT 1",
                (ticker, now - SCOUT_DESK_PATIENCE_MS),
            ).fetchone()
            if running:
                raise HTTPException(
                    status_code=409,
                    detail="The desk is already out on this game. One "
                           "convening at a time; poll for its briefing.",
                )
            # Refuse before writing anything, so a tap against an exhausted
            # day answers immediately and spends nothing -- the same check the
            # desk itself makes (searches worst case included, v17), done
            # early where the phone can see it.
            budget = AgentBudget.from_config(write_conn, config)
            reason = budget.refusal_reason(
                2,
                now,
                searches_worst_case=scout_desk.STAFF_PAIR_SEARCHES_WORST_CASE,
            )
            if reason is not None:
                raise HTTPException(status_code=429, detail=reason)
            cursor = write_conn.execute(
                "INSERT INTO scout_briefings (ticker, event_title, league, "
                "home_team, away_team, commence_ms, requested_ms, status, "
                "model) VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?)",
                (
                    ticker,
                    fixture["event_title"],
                    fixture["league"],
                    fixture["home_team"],
                    fixture["away_team"],
                    fixture["commence_ms"],
                    now,
                    config.model,
                ),
            )
            write_conn.commit()
            row_id = int(cursor.lastrowid)
        finally:
            write_conn.close()
        asyncio.create_task(_run_scout_desk(row_id, config, fixture, ticker))
        return {"accepted": True, "id": row_id}

    @app.get("/api/scout")
    def scout_desk_overview(conn=Depends(get_conn)) -> dict:
        """The desk's own screen: recent briefings, and today's metered spend.

        The spend block is the v17 token meter made phone-readable -- the one
        place Joe can see what the desk has cost TODAY before sending it
        again, in the three units that actually bill: calls, web searches,
        tokens. Counts, never dollars (`AgentSpendSummary` has the argument:
        the per-token rate in this repo is assumed, not invoiced).
        `calls_unmetered` is the number of today's calls whose usage never
        came back -- the sums do not cover them, and saying so beats a
        confident undercount. `spend` is None when no ANTHROPIC_API_KEY is
        configured (the demo): the desk does not exist there, and a row of
        zeroes would claim a meter where there is no account to meter.

        Briefing rows are summaries only -- status and identity, no
        `staff_json`/`briefing_json` -- because this screen answers "what has
        the desk done and what did it cost", and the briefing itself is read
        on the game's own screen via `GET /api/scout/{ticker}`.
        """
        rows = conn.execute(
            "SELECT id, ticker, event_title, league, home_team, away_team, "
            "commence_ms, requested_ms, completed_ms, status, refusal_reason, "
            "model, briefing_json IS NOT NULL AS has_briefing "
            "FROM scout_briefings ORDER BY requested_ms DESC, id DESC LIMIT 50"
        ).fetchall()
        now = db.now_ms()
        briefings = []
        for row in rows:
            gone_quiet = (
                row["status"] == "running"
                and now - row["requested_ms"] > SCOUT_DESK_PATIENCE_MS
            )
            briefings.append(
                {
                    "id": row["id"],
                    "ticker": row["ticker"],
                    "event_title": row["event_title"],
                    "league": row["league"],
                    "home_team": row["home_team"],
                    "away_team": row["away_team"],
                    "commence_ms": row["commence_ms"],
                    "requested_ms": row["requested_ms"],
                    "completed_ms": row["completed_ms"],
                    "status": row["status"],
                    "gone_quiet": gone_quiet,
                    "refusal_reason": row["refusal_reason"],
                    "has_briefing": bool(row["has_briefing"]),
                }
            )
        config = AgentConfig.from_env()
        spend = None
        if config is not None:
            summary = AgentBudget.from_config(conn, config).today_summary(now)
            spend = {
                "calls_today": summary.calls_today,
                "calls_daily_budget": summary.daily_budget,
                "searches_today": summary.searches_today,
                "searches_daily_budget": summary.searches_daily_budget,
                "tokens_today": summary.tokens_today,
                "tokens_daily_budget": summary.tokens_daily_budget,
                "calls_unmetered_today": summary.calls_unmetered_today,
                "day_start_ms": summary.day_start_ms,
            }
        return {"briefings": briefings, "spend": spend}

    @app.get("/api/scout/{ticker}")
    def scout_briefing(ticker: str, conn=Depends(get_conn)) -> dict:
        """The latest briefing for one game, or the honest absence of one.

        Public read: a briefing is sourced sports news, not operator data.
        `state: "never_sent"` and a `running` row are different facts; a
        `running` row past the patience window gains `gone_quiet: true`
        because the process that owned it cannot finish it after a restart.
        """
        row = conn.execute(
            "SELECT * FROM scout_briefings WHERE ticker = ? "
            "ORDER BY requested_ms DESC, id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        if not row:
            return {"state": "never_sent"}
        gone_quiet = (
            row["status"] == "running"
            and db.now_ms() - row["requested_ms"] > SCOUT_DESK_PATIENCE_MS
        )
        return {
            "state": "sent",
            "id": row["id"],
            "status": row["status"],
            "gone_quiet": gone_quiet,
            "ticker": row["ticker"],
            "event_title": row["event_title"],
            "league": row["league"],
            "home_team": row["home_team"],
            "away_team": row["away_team"],
            "commence_ms": row["commence_ms"],
            "requested_ms": row["requested_ms"],
            "completed_ms": row["completed_ms"],
            "refusal_reason": row["refusal_reason"],
            "staff": json.loads(row["staff_json"]) if row["staff_json"] else None,
            "briefing": (
                json.loads(row["briefing_json"]) if row["briefing_json"] else None
            ),
            # Willy Balters' take (ADR 0069). `null` on a briefing that
            # predates the seat or where the seat filed nothing — the
            # screen renders the absence in words, never an empty card.
            "sharp": (
                json.loads(row["sharp_json"]) if row["sharp_json"] else None
            ),
            "model": row["model"],
        }
