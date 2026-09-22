#!/bin/sh
# scripts/measure_118_trip.sh -- #118's T1 / T2+T3 readings, taken unattended.
#
#     sh scripts/measure_118_trip.sh t1      # 2026-09-23 09:00-09:55Z window
#     sh scripts/measure_118_trip.sh t2      # 2026-09-23 10:30-14:00Z window
#
# Why this file exists
# --------------------
# The pre-registration at
# docs/measurements/2026-09-21-preregistration-unattended-scouting-first-reading.md
# fixes T1 as a 55-minute window (09:00-09:55Z on 2026-09-23, 02:00 PDT), n = 1,
# one slip permitted -- and the slip lands at 02:00 PDT again. No interactive
# session survives to that hour and nobody should have to. So the registered
# commands are run by two schedulers instead: a dated GitHub Actions workflow
# (.github/workflows/measure-118.yml) and a Windows scheduled task on the
# laptop, each calling THIS script by path. One source for the command strings,
# two callers with different failure modes (a runner that cannot open an ssh
# console; a laptop that went to sleep).
#
# Three properties the test pins (tests/test_118_trip_is_the_registered_command.py)
# ----------------------------------------------------------------------------
# **The commands are the registration's, byte for byte.** The four strings
# below are compared against the registration's section 2 by the test. This
# script chooses nothing about WHAT is read; it only chooses WHEN, and the
# schedulers choose that.
#
# **The clock is GitHub's, never the machine's.** The wall-clock instant of a
# read (`T1_ms` in the registration) is taken from the `Date` header of
# `https://api.github.com`. On 2026-09-22 the laptop printed local time
# labelled UTC and a whole session planned seven hours wrong on it
# (tasks/lessons.md, 2026-09-22 third). If the header cannot be read the read
# still happens and the stamp says UNAVAILABLE -- a reading with an uncertain
# clock is context; a missing reading is a slip.
#
# **Nothing here retries.** The schedulers fire several times inside each
# window on purpose; a retry loop here would turn one fire into several and
# hide which one was which. Amendment 1 of the registration says which of the
# several reads is T1.
#
# What this does not establish
# ----------------------------
# - Which read is T1. That is Amendment 1's rule, applied by the session that
#   writes the result doc over every read from both arms.
# - Anything about the public surface, freshness, or the data being right --
#   see the docstring of scripts/fetch_live_route.py, which this only invokes.
# - That the run happened inside the window. The stamp says when it ran; the
#   registration says whether that counts.
#
# Every venue-side command is a committed script invoked by path over
# `flyctl ssh console`, per the standing rule (scripts/fetch_live_route.py,
# scripts/inspect_live_db.py). `fetch_live_route.py` cannot express a write;
# the three QueryDefs are `cost=CHEAP` (scripts/inspect_live_db.py:790-850),
# so neither trip can perturb the day it reads.

set -u

APP=kalshi-cockpit

# The registered commands, section 2 of the registration. Do not edit these
# without amending the registration first; the test compares them.
T1_CMD='python /app/scripts/fetch_live_route.py /api/scout'
T2_WATCH_LOG_CMD='python /app/scripts/inspect_live_db.py scout-watch-log --days 3 --day-start-hour 10'
T2_BRIEFINGS_CMD='python /app/scripts/inspect_live_db.py scout-briefings --days 3 --day-start-hour 10'
T3_LADDER_CMD='python /app/scripts/inspect_live_db.py ladder-fixtures'

usage() {
    echo "usage: sh scripts/measure_118_trip.sh t1|t2" >&2
    exit 2
}

# Print one stamp line from GitHub's clock. Never `date -u` on its own.
stamp() {
    label="$1"
    header="$(curl -sI --max-time 15 https://api.github.com 2>/dev/null | tr -d '\r' | sed -n 's/^[Dd]ate: //p' | head -n 1)"
    if [ -z "$header" ]; then
        echo "STAMP ${label} clock_source=UNAVAILABLE github_date= epoch_ms="
        return 0
    fi
    secs="$(date -u -d "$header" +%s 2>/dev/null || echo "")"
    if [ -z "$secs" ]; then
        echo "STAMP ${label} clock_source=github github_date=${header} epoch_ms=UNPARSED"
        return 0
    fi
    echo "STAMP ${label} clock_source=github github_date=${header} epoch_ms=${secs}000"
}

# Run one registered command over ssh, print its output between markers, and
# report flyctl's exit code without acting on it: `flyctl ssh console` exits 1
# after a perfectly good read (memory: verification methods that lie), so the
# exit code is a fact to record, not a verdict.
run_venue() {
    name="$1"
    cmd="$2"
    echo "BEGIN ${name}: ${cmd}"
    flyctl ssh console -a "$APP" -C "$cmd"
    rc=$?
    echo "END ${name} flyctl_exit=${rc}"
}

trip="${1:-}"
case "$trip" in
    t1)
        stamp "t1 before"
        out="$(run_venue T1 "$T1_CMD" 2>&1)"
        echo "$out"
        stamp "t1 after"
        # A good T1 read carries the field the registration's pre-condition
        # reads first. Its absence is a failed read, said loudly so the
        # scheduler's step goes red and the next fire is the one that counts.
        case "$out" in
            *day_start_ms*) echo "RESULT t1 ok" ;;
            *) echo "RESULT t1 NO_READ (no day_start_ms in output)" >&2; exit 1 ;;
        esac
        ;;
    t2)
        stamp "t2 before"
        out_a="$(run_venue T2_WATCH_LOG "$T2_WATCH_LOG_CMD" 2>&1)"
        echo "$out_a"
        out_b="$(run_venue T2_BRIEFINGS "$T2_BRIEFINGS_CMD" 2>&1)"
        echo "$out_b"
        out_c="$(run_venue T3_LADDER "$T3_LADDER_CMD" 2>&1)"
        echo "$out_c"
        stamp "t2 after"
        # Every QueryDef ends each table with an "N row(s)" line (the shared
        # printer in inspect_live_db.py), so a read that reached the table
        # carries one. Three is a complete set; fewer is a partial one. The
        # "budget day starts 10:00Z" window header is printed by the two
        # scout QueryDefs only -- ladder-fixtures has no such header
        # (rehearsed 2026-09-22), so it is not the completeness marker.
        n=0
        for o in "$out_a" "$out_b" "$out_c"; do
            if printf '%s\n' "$o" | grep -Eq '^[0-9]+ rows?$'; then n=$((n + 1)); fi
        done
        if [ "$n" -eq 3 ]; then
            echo "RESULT t2 ok (3 of 3 reads)"
        else
            echo "RESULT t2 PARTIAL (${n} of 3 reads carried a row-count line)" >&2
            exit 1
        fi
        ;;
    *)
        usage
        ;;
esac
