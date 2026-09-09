"""Put ONE orphaned combination under `/hedge`'s watch. Authorised, not general.

    .venv\\Scripts\\python.exe scripts\\backfill_orphan_combo_position.py --db /data/cockpit.db --dry-run
    .venv\\Scripts\\python.exe scripts\\backfill_orphan_combo_position.py --db /data/cockpit.db --commit

`manual_orders` id=4 filled at 2026-09-09T15:11:56.378Z with real money. ADR
0125's wiring -- which makes a filled combination write its own
`parlay_positions` row, so that `/hedge` can see the only exit an enter-only
combination has -- deployed at 15:56:45Z, forty-five minutes later. The fill
therefore never had a writer at all, and the position existed with the exit
screen never having heard of it.

**This script is the whole authorisation, and it is narrow.** It is Amendment 1
A1.2.3 of `docs/measurements/2026-09-08-parlay-positions-check-amendment-registration.md`,
which permits exactly this one row. It refuses any other target. It is
committed before it runs so that the exact arguments are in git rather than in
a transcript -- an authorisation living only in a transcript has not been
registered, which is §9.1's defect against the original check.

Why a script rather than a hand-written INSERT
-----------------------------------------------
A1.2.3: no figure may be hand-composed. Every value is derived by the same
functions ADR 0125's `_record_combo_position` would have used --
`parlays.priced_lookup_for`, `parlays.legs_for_position`,
`hedge.record_position` -- so the row is what the wiring would have written,
not what someone typed. `legs_for_position` returning `None` aborts the write
outright; a partial leg list is refused by ADR 0125 and this amendment does
not relax that.

The one field that is deliberately NOT the wiring's
----------------------------------------------------
`_record_combo_position` writes the note *"Recorded automatically from the
hand-bet path"*. For this row that sentence is false, and a false provenance
marker on a row inside an open observation window is exactly what the
amendment exists to prevent. `_NOTE` below replaces it and says who wrote the
row, when, under what authority, and that it is excluded from the statistic.

**Provenance here is a note, and prose is now the whole mechanism.** Amendment
1 A1.3.3 required provenance to become a *column* — a hand-written row can be
made byte-identical to a wired one, since `POST /api/hedge/positions` accepts
`note`, `combo_ticker` and `parlay_lookup_id` straight from the request.
**Joe withdrew that requirement on 2026-09-09 and Amendment 2 A2.7 records it
as dropped.** A1.3.3's argument was *forgeability*, which matters when a
statistic is being defended; the statistic was killed the same day, and what
is left is an honest reader who cannot tell — answered by a row id in a
committed file rather than by a column.

So printing the id, and appending it to the amendment, is **not optional and
is now the only mechanism there is**. A2.7.4 is the standing constraint:
authorship leaves no raw material, so a column added later recovers attribution
for nothing written before it. This is not a rule that can be broken and
written up afterwards as a deviation.

What this does not do
----------------------
- **It moves no money and reaches no venue.** It writes a table `gate.py` may
  never read (ADR 0063), so it cannot move the live-trading interlock.
- It does not decide whether the write is *permitted to execute*. That is a
  permission-system and operator question; this script does not answer it and
  is not a way around it.
- It does not backfill the two 2026-09-08 positions. They are settled, ADR 0125
  refused them deliberately, and a row for a closed position would be invented
  history rather than bookkeeping.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend import hedge as held_parlays  # noqa: E402
from backend import parlays  # noqa: E402

# The authorised target, spelled out. Anything else is refused rather than
# parameterised: a general backfill tool is not what was authorised, and the
# next orphan needs its own ruling, not a flag.
TICKER = "KXMVECROSSCATEGORY-SHARD1-S2026FAD1B866580-EE12A337E52"
MANUAL_ORDER_ID = 4
CONTRACTS = 4
FILL_PRICE_TENTHS = 410
PLACED_MS = 1788966716378

_NOTE = (
    "Recorded by hand on 2026-09-09 by an agent session under Amendment 1 of "
    "docs/measurements/2026-09-08-parlay-positions-check-amendment-"
    "registration.md, replaying ADR 0125's _record_combo_position against "
    "manual_orders id=4, which filled at 15:11:56Z -- 45 minutes before that "
    "wiring deployed at 15:56:45Z. This is NOT an act of recording by Joe. "
    "Excluded from R, and its sitting excluded from G, by that amendment."
)


def _check_target(conn: sqlite3.Connection) -> None:
    """Refuse unless the database really holds the row that was authorised.

    Guards against the two ways this runs somewhere it should not: a different
    database, and a `manual_orders` id=4 that is not the order the amendment
    describes. Both would produce a plausible row for a position nobody holds.
    """
    row = conn.execute(
        "SELECT ticker, status, dry_run, count FROM manual_orders WHERE id = ?",
        (MANUAL_ORDER_ID,),
    ).fetchone()
    if row is None:
        raise SystemExit(f"REFUSED: no manual_orders id={MANUAL_ORDER_ID}")
    ticker, status, dry_run, count = row
    if ticker != TICKER:
        raise SystemExit(f"REFUSED: id={MANUAL_ORDER_ID} is {ticker!r}")
    if status != "filled":
        raise SystemExit(f"REFUSED: status is {status!r}, not 'filled'")
    if dry_run != 0:
        raise SystemExit("REFUSED: that order was a dry run -- nothing was bought")
    if count != CONTRACTS:
        raise SystemExit(f"REFUSED: venue count {count} != {CONTRACTS}")

    existing = conn.execute(
        "SELECT id FROM parlay_positions WHERE combo_ticker = ?", (TICKER,)
    ).fetchone()
    if existing is not None:
        raise SystemExit(
            f"REFUSED: parlay_positions id={existing[0]} already watches this "
            "combination. A second row would be a second holding that does not "
            "exist, and /hedge would size against double the real exposure."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        _check_target(conn)

        lookup = parlays.priced_lookup_for(conn, TICKER)
        if lookup is None:
            raise SystemExit("REFUSED: no priced parlay_lookups row for it")
        parsed = parlays.legs_for_position(lookup["selected_legs"])
        if parsed is None:
            raise SystemExit("REFUSED: the leg list could not be parsed in full")

        stake_tenths = CONTRACTS * FILL_PRICE_TENTHS
        return_tenths = CONTRACTS * 1000
        label = lookup["card_key"] or TICKER

        print(f"lookup_id        {int(lookup['id'])}")
        print(f"label            {label!r}")
        print(f"stake_tenths     {stake_tenths}")
        print(f"return_tenths    {return_tenths}")
        print(f"legs             {len(parsed.legs)}")
        for leg in parsed.legs:
            print(f"  {leg}")

        if args.dry_run:
            print("DRY RUN -- nothing written")
            return 0

        position_id = held_parlays.record_position(
            conn,
            now_ms=int(time.time() * 1000),
            source="kalshi_combo",
            label=label,
            stake_tenths=stake_tenths,
            return_tenths=return_tenths,
            legs=parsed.legs,
            placed_ms=PLACED_MS,
            combo_ticker=TICKER,
            parlay_lookup_id=int(lookup["id"]),
            note=_NOTE,
        )
        conn.commit()
        written = conn.execute(
            "SELECT id, created_ms FROM parlay_positions WHERE id = ?",
            (position_id,),
        ).fetchone()
        # Printed because A1.2.3 requires the id and created_ms to be appended
        # to the amendment: until that line exists the row is identified only
        # by description.
        print(f"WROTE parlay_positions id={written['id']} "
              f"created_ms={written['created_ms']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
