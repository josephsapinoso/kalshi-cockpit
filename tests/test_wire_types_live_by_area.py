"""The backend wire types live one file per area under `lib/types/` (#262,
ADR 0191 section 2.5), and `api.ts` only re-exports them.

Why: 62 of api.ts's 68 commits since 2026-09-01 also touched `backend/`. A
payload change should edit one small types file, not the hottest file in the
repo, while every `import { X } from "@/lib/api"` keeps working.

Establishes: api.ts declares no type itself, still exports every name it
exported before the move, every name is declared in exactly one `lib/types/`
file, and those files carry no runtime import. Does not establish that a type
matches the backend payload (the reasons test does that for `HeldPosition`).
"""

from __future__ import annotations

import re
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "frontend" / "src" / "lib"
API_TS = LIB / "api.ts"
TYPES = LIB / "types"

# Generated from `export type X` in api.ts at main d9b98c6, before the move,
# plus the `WriteResult` re-export from `./transport`.
PRE_MOVE_EXPORTS = [
    "ActionableWindow",
    "BetKind",
    "BetsKindSummary",
    "BetsRecord",
    "BetsSection",
    "ExpectedBlock",
    "BySourceBlock",
    "PickSourceKey",
    "PickSourcesBlock",
    "Board",
    "BoardTile",
    "BookDistribution",
    "ChartCandle",
    "CheckedParlayLeg",
    "CheckedParlayResult",
    "ComboBid",
    "ComboBidResult",
    "ComboRfqAcceptResult",
    "ComboRfqQuote",
    "ComboRfqResult",
    "ConfigVersion",
    "ConsensusProvenance",
    "Dashboards",
    "DeskBriefing",
    "DevigMethods",
    "EdgeTone",
    "EstimateLogged",
    "EstimateMarket",
    "Exposure",
    "GameLeg",
    "GameLegGroup",
    "GameLegSide",
    "GameLegs",
    "GameMintResult",
    "GameScriptCard",
    "GameScriptCards",
    "GameScriptLeg",
    "Gate",
    "GateCondition",
    "Gauntlet",
    "HedgeBlock",
    "HedgeRefusal",
    "HedgeRung",
    "HedgeScreen",
    "HedgeSellQuote",
    "HeldLeg",
    "HeldLegInput",
    "HeldPosition",
    "HeldConflict",
    "HeldConflicts",
    "HeldPositionInput",
    "Ledger",
    "LegRest",
    "LegVerdict",
    "LegVerdictInput",
    "LegVerdictState",
    "LegVerdictTrigger",
    "LegVerdictsResult",
    "Lesson",
    "LineShopData",
    "LineShopLeg",
    "ListFilter",
    "ListFilterEcho",
    "LockedDetail",
    "ManualMarket",
    "ManualMarketSide",
    "ManualOrderPlaced",
    "ManualOrderResult",
    "MarketCandles",
    "MarketDetail",
    "OddsRefreshResult",
    "OpenPositionsBlock",
    "OrderPlaced",
    "OrderQuote",
    "OrderResult",
    "Panel",
    "ParlayCardData",
    "ParlayCardJoint",
    "ParlayCardLeg",
    "ParlayCardScouting",
    "ParlayHorizon",
    "ParlayLadder",
    "ParlayLeg",
    "ParlayLookupResult",
    "ParlayPrefix",
    "ParlayStake",
    "ParlayValuation",
    "ParlayWindow",
    "PlannedSlot",
    "Playbook",
    "RecentEstimate",
    "Recommendation",
    "RecordPassResult",
    "Refreshable",
    "RefreshableBeyondHorizon",
    "RefreshableFixture",
    "RefreshableSport",
    "ScoutBriefingState",
    "ScoutFinding",
    "ScoutOverview",
    "ScoutOverviewRow",
    "ScoutSpend",
    "ScoutStaffNote",
    "ScoutStaffReport",
    "SendDeskResult",
    "SettledBet",
    "SharpTake",
    "Signal",
    "Slate",
    "SlatePick",
    "SlatePicks",
    "SlateRowData",
    "StudyStop",
    "Suppression",
    "TeamRest",
    "TonightActivity",
    "TrustScore",
    "UnrecordedAtVenue",
    "VenueSettlement",
    "WriteResult",
]


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def _api() -> str:
    return _strip_comments(API_TS.read_text(encoding="utf-8"))


def _reexported(text: str) -> set[str]:
    names: set[str] = set()
    for block in re.findall(r"export type \{([^}]*)\}", text):
        names.update(n.strip() for n in block.split(",") if n.strip())
    return names


class TestApiDeclaresNoTypes:
    def test_no_type_alias_or_interface_is_declared_in_api_ts(self):
        text = _api()
        assert not re.search(r"^export type \w+\s*=", text, flags=re.MULTILINE)
        assert not re.search(r"^export interface\b", text, flags=re.MULTILINE)
        assert not re.search(r"^(type|interface)\s+\w+", text, flags=re.MULTILINE)

    def test_there_is_no_lib_api_folder_beside_api_ts(self):
        assert not (LIB / "api").exists()


class TestEveryNameIsStillExported:
    def test_every_pre_move_name_is_reexported_from_api_ts(self):
        missing = sorted(set(PRE_MOVE_EXPORTS) - _reexported(_api()))
        assert not missing, f"api.ts no longer exports: {missing}"

    def test_every_moved_name_is_declared_in_exactly_one_types_file(self):
        declared: dict[str, list[str]] = {}
        for path in sorted(TYPES.glob("*.ts")):
            for name in re.findall(
                r"^export type (\w+)\s*=", _strip_comments(path.read_text("utf-8")),
                flags=re.MULTILINE,
            ):
                declared.setdefault(name, []).append(path.name)
        expected = set(PRE_MOVE_EXPORTS) - {"WriteResult"}
        assert set(declared) == expected
        assert {n: f for n, f in declared.items() if len(f) != 1} == {}


class TestTypesFilesAreTypesOnly:
    def test_no_types_file_has_a_runtime_import_or_imports_api(self):
        files = sorted(TYPES.glob("*.ts"))
        assert files, "lib/types/ is empty"
        for path in files:
            text = _strip_comments(path.read_text(encoding="utf-8"))
            for stmt in re.findall(r"^\s*import\b[^;]*;", text, flags=re.MULTILINE):
                assert re.match(r"\s*import type\b", stmt), f"{path.name}: {stmt!r}"
                assert not re.search(r'from\s+"(\.\./|\./)api"', stmt), path.name
            assert not re.search(r"^export (const|function|async|let|enum)\b", text,
                                 flags=re.MULTILINE), path.name
            assert not re.search(r"^\s*import\s+\"", text, flags=re.MULTILINE), path.name
