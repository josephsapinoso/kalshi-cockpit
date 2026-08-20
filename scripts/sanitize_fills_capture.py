"""Derive the committed fills fixture from the private capture.

    .venv\\Scripts\\python.exe scripts\\sanitize_fills_capture.py

`tests/test_series_fee_multiplier.py` predicts the charged fee on real fills,
and until 2026-08-20 it read `data/captures/portfolio_fills.json` directly --
a file whose docstringed claim to be "tracked in git" was never true
(`data/` is gitignored, the force-add never happened, and `git ls-files
data/` is empty), so CI failed on every push from the moment the test
landed. The raw capture cannot simply be force-added: it carries
`order_id`, `trade_id`, `fill_id` and `subaccount_number`, account-linked
identifiers with no place in a public repo.

This script writes `tests/fixtures/portfolio_fills_sanitized.json` carrying
exactly the fields the test consumes and nothing else:

    ticker, is_taker, count_fp, yes_price_dollars, fee_cost, order_id

with `order_id` replaced by `order-NN` pseudonyms assigned in order of first
appearance -- distinctness is preserved (the test's multi-fill-order guard
needs it) and the real identifiers never leave the machine. Every retained
field's value for the attributed fills is already public row-by-row in
`docs/measurements/2026-08-14-fee-rate-attribution-round-three-result.md`
and the combo fee looks, so the fixture publishes no new fact about the
account, only a machine-readable copy of ones the record already states.

Wire-format rule (CLAUDE.md): tests load captured payloads, never
hand-constructed ones. This fixture is the captured payload minus named
fields -- a documented exception in the ADR 0035 family, where the reason
(here: account identifiers in a public repo; there: MLBAM terms) is the
decision.

What this does not establish: nothing about the capture's own accuracy, and
nothing about fills made after `captured_at` -- re-run
`scripts/capture_fills_fixture.py` and then this when the population moves.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "captures" / "portfolio_fills.json"
DEST = ROOT / "tests" / "fixtures" / "portfolio_fills_sanitized.json"

KEPT_FIELDS = ("ticker", "is_taker", "count_fp", "yes_price_dollars", "fee_cost")


def sanitize(raw: dict) -> dict:
    fills = raw["payload"]["fills"]
    pseudonyms: dict[str, str] = {}
    out_fills = []
    for fill in fills:
        real = fill["order_id"]
        if real not in pseudonyms:
            pseudonyms[real] = f"order-{len(pseudonyms) + 1:02d}"
        row = {k: fill[k] for k in KEPT_FIELDS}
        row["order_id"] = pseudonyms[real]
        out_fills.append(row)
    return {
        "note": (
            "Sanitized from data/captures/portfolio_fills.json by "
            "scripts/sanitize_fills_capture.py. order_id values are "
            "first-appearance pseudonyms; trade_id, fill_id, "
            "subaccount_number, timestamps and all other fields are dropped."
        ),
        "captured_at": raw["captured_at"],
        "endpoint": raw["endpoint"],
        "record_count": len(out_fills),
        "payload": {"fills": out_fills},
    }


def main() -> int:
    raw = json.loads(SOURCE.read_text(encoding="utf-8"))
    DEST.write_text(
        json.dumps(sanitize(raw), indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {DEST.relative_to(ROOT)}: {len(json.loads(DEST.read_text())['payload']['fills'])} fills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
