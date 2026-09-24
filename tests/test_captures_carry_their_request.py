"""A captured payload without its request cannot make an ABSENCE readable.

The defect, and the finding it killed -- ADR 0157
-------------------------------------------------
`tests/fixtures/odds_mlb_h2h_spreads_totals.json` carries

    "params": {"regions": ["us", "eu"], "markets": ["h2h", "spreads", "totals"]}

and its sibling `tests/fixtures/odds_mlb_player_props.json` carries no such
envelope at all. That asymmetry killed a real finding on 2026-09-15. The claim
was *no sharp book quotes player props, so four of the ten named bookmakers are
dead weight on the prop endpoint*. The prop capture returned nine books, every
one of them a US book, and not one of `pinnacle`, `matchbook` or
`betfair_ex_eu`.

Nine US books and no EU book is **exactly what `regions=us` returns**. So

    "EU books do not quote player props"      -- a fact about the world
    "that capture never asked for EU"         -- a fact about the request

produce the byte-identical file. The parameter that decides between them is the
one the capture did not record, and no amount of re-reading the payload recovers
it. `test_the_prop_fixture_cannot_tell_an_unquoted_book_from_an_unasked_one`
below pins that confound so the exception cannot quietly stop being one.

Why this is a rule and not a note about the odds feed
-----------------------------------------------------
**A present thing is evidence on its own. An absent thing is evidence only
against the question that was asked.** This repo reasons from absences
constantly: which book is missing from a devig, which market key came back
empty, which series returned no events, whether a combo leg had no resting bid
(`tests/test_combo_book_depth_claims.py` rests an entire ADR on *zero* resting
YES bids over 36 levels). Every one of those readings is unavailable on a
payload whose request is unknown -- and unavailable *silently*, because the file
looks complete either way.

So a capture is not the response. It is the **pair** (request, response).
Storing half of it stores something that reads as whole and is not.

The required shape
------------------
A fixture records its request when the document names, at top level:

1. **the parameters that shaped the response** -- `params_in` below names the
   keys, and `param_names` names parameters that must be findable inside them.
   `odds_nfl_h2h_spreads.json` uses a `params` mapping; `events_nfl_preseason.json`
   spells the same thing as a query string inside `endpoint`; `markets_settled.json`
   uses a `queries` list, one entry per call. All three are accepted, because the
   rule is about the information being present, not about a house style.
2. **the endpoint it was sent to** -- `endpoint_in` names the keys, and the value
   must read as a path or a URL.

New captures write the canonical form through `scripts/capture_envelope.py`,
which refuses a document with no `request` block and refuses a
credential-shaped parameter inside one. The shapes above are what is already on
disk, and re-capturing to normalise them is not free (see the cost column).

Why an opt-out table rather than a bare rule
--------------------------------------------
Nineteen of the thirty-six fixtures in this repo predate the rule. A rule that
fails on nineteen files gets deleted; a rule with nineteen unexplained
exceptions is not a rule. So `DISPOSITIONS` classifies **every** file, the test
enumerates the directory rather than the table, and an unclassified fixture
fails. That is the shape `tests/test_has_callers.py` arrived at for the same
reason and after the same failure: an allowlist cannot report what is missing
from it, so the population is computed and the *classification* is what a human
supplies.

`RequestUnrecorded` entries name a cost, because the cost is the decision. A
Kalshi `/events` re-capture is a free unauthenticated read; an Odds API
re-capture spends credits against a 700/day cap and is the operator's call, not
a test's.

What this file does NOT establish
---------------------------------
- **Nothing about whether any sharp book quotes player props.** It pins that the
  prop fixture cannot answer the question, which is the opposite claim. ADR 0157
  answers it from live `odds_snapshots` for zero credits instead.
- **Nothing about whether a recorded request is TRUE.** A fixture says what its
  author said was sent. `capture_nfl_odds_fixture.py` builds the envelope and
  the call from the same module constants so the two cannot drift, but this test
  cannot check a claim about a request nobody can replay.
- **Nothing about payload correctness.** Whether the events parse, whether the
  prices are sane, whether a book is spelled right -- all of that lives in the
  wire-format tests. This one asks a single question: can a reader tell what was
  asked for?
- **Nothing about fixtures that do not exist.** MLBAM (`statsapi.mlb.com`)
  payloads are never committed -- this repo is public and their terms permit
  "only individual, non-commercial, non-bulk use" (ADR 0035, CLAUDE.md). MLB
  tests use synthetic payloads with a shape assertion, and that inconsistency is
  the decision, not a bug. `test_no_fixture_carries_an_mlbam_payload` keeps the
  ratchet from ever demanding an envelope on a payload that may not be here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from scripts.capture_envelope import (
    CaptureEnvelopeError,
    assert_records_its_request,
    request_envelope,
    write_capture,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
SCRIPTS = ROOT / "scripts"


# --------------------------------------------------------------------------
# The three classifications
# --------------------------------------------------------------------------
class RecordsItsRequest:
    """The document says what was asked for, and the test checks that it does.

    `params_in` and `endpoint_in` are top-level keys; `param_names` are
    parameter names that must be findable inside the `params_in` subtree,
    either as a key or inside a string value (which is how a query string
    spelled into an `endpoint` field is accepted).

    This is a *checked* claim, not prose. An entry that names a key the fixture
    does not have fails, so the table cannot drift away from the files.
    """

    kind = "RECORDED"

    def __init__(
        self,
        *,
        params_in: tuple[str, ...],
        param_names: tuple[str, ...],
        endpoint_in: tuple[str, ...],
        how: str,
    ) -> None:
        self.params_in = params_in
        self.param_names = param_names
        self.endpoint_in = endpoint_in
        self.how = how


class NotACapture:
    """No third-party response body is stored here, so there is no request.

    Derived tables, synthetic payloads and counts. The distinction matters:
    demanding an envelope on a hand-written payload would invent a request that
    was never made, which is a worse lie than the missing one.
    """

    kind = "NOT_A_CAPTURE"

    def __init__(self, reason: str) -> None:
        self.reason = reason


class RequestUnrecorded:
    """A real capture whose request is not recorded. A named, costed exception.

    `cost` is what getting the record back would take, and it is the whole
    decision. `writer` is the script that produced the file, or the words that
    say there is not one -- a fixture with no writer cannot be re-captured by
    running anything, which is a different and worse position than an expensive
    one.
    """

    kind = "UNRECORDED"

    def __init__(self, *, reason: str, cost: str, writer: str) -> None:
        self.reason = reason
        self.cost = cost
        self.writer = writer


# --------------------------------------------------------------------------
# Every file in tests/fixtures/, classified. An unclassified file fails.
# --------------------------------------------------------------------------
DISPOSITIONS: dict[str, RecordsItsRequest | NotACapture | RequestUnrecorded] = {
    # -- Records its request -------------------------------------------------
    # ADR 0164 -- the first capture of a Kalshi COMBINATION's real price. It
    # records the read AND the write that produced it, because the quotes
    # cannot be re-fetched: withdrawing the RFQ destroys the venue's copy, so
    # an unrecorded request here could never be reconstructed by asking again.
    "board_issues.json": RecordsItsRequest(
        params_in=("params",),
        param_names=("roots", "paginate"),
        endpoint_in=("endpoint",),
        how="A real `gh api` capture of the sub-issue trees under map #3 and "
            "backlog root #80 (2026-09-19), trimmed of URL and avatar noise; "
            "every field `scripts/board.py` reads is verbatim. A `synthetic` "
            "key holds hand-built nodes for tree shapes the live tree did not "
            "contain that day, labelled as such inside the file.",
    ),
    "combo_rfq_quotes.json": RecordsItsRequest(
        params_in=("params",),
        param_names=("rfq_user_filter", "limit", "exchange_index"),
        endpoint_in=("endpoint",),
        how="A `params` mapping carrying the quote read, plus the full body of "
            "the `POST /communications/rfqs` that drew these quotes -- the "
            "write matters as much as the read, since `exchange_index=1` is "
            "what makes the create succeed at all. Account identifiers are "
            "replaced by documented placeholders: this repo is public and "
            "operator data never enters it. Prices and structure are verbatim.",
    ),
    # #96 / #129 -- the first committed SELL-side quote: an RFQ asked about a
    # combination held at the venue, sized in contracts from the holding.
    # Written by `scripts/capture_sell_side_rfq.py --fixture`, which carries
    # the create's URL (with `exchange_index=1`) and its full body.
    "combo_rfq_quotes_sell_side.json": RecordsItsRequest(
        params_in=("params",),
        param_names=("rfq_user_filter", "limit", "exchange_index"),
        endpoint_in=("endpoint",),
        how="A `params` mapping carrying the quote read, the create's URL "
            "(`exchange_index=1` in it) and the full `POST /communications/rfqs` "
            "body, sized in `contracts` from the venue's own positions read. "
            "Quote, maker and requester ids are documented placeholders; "
            "prices, sizes and timestamps are verbatim.",
    ),
    # #147 -- the RFQ LIST is market-wide: every requester's rows, and the
    # discriminator the fix keeps as a second guard. Written by
    # `scripts/capture_rfq_list.py` on a combination the account does NOT hold.
    "combo_rfq_list_market_wide.json": RecordsItsRequest(
        params_in=("endpoint",),
        param_names=("market_ticker", "limit"),
        endpoint_in=("endpoint",),
        how="An `endpoint` string spelling the read with its query "
            "(`market_ticker`, `limit`). Every ticker is a TICKER_N_REDACTED "
            "placeholder and every non-empty `creator_user_id` / `creator_id` "
            "is replaced; which rows carried the field survives redaction.",
    ),
    # #107 -- a real combination book with a resting YES bid. Captured on a
    # HELD combination on Joe's word (2026-09-24), ticker redacted; the
    # response body carries no identifying field.
    "combo_orderbook_with_yes_bid.json": RecordsItsRequest(
        params_in=("request",),
        param_names=("ticker", "depth"),
        endpoint_in=("endpoint",),
        how="A `request` block written through `capture_envelope.write_capture`: "
            "the orderbook URL template and `ticker` (a redacted placeholder). "
            "The response is verbatim.",
    ),
    "odds_mlb_h2h_spreads_totals.json": RecordsItsRequest(
        params_in=("params",),
        param_names=("regions", "markets", "oddsFormat"),
        endpoint_in=("note",),
        how="A `params` mapping. The fixture ADR 0157 contrasts its silent "
            "sibling against: under us+eu all four sharp books appear on team "
            "markets, and this file can say so because it records the regions.",
    ),
    "odds_nfl_h2h_spreads.json": RecordsItsRequest(
        params_in=("params",),
        param_names=("regions", "markets", "oddsFormat"),
        endpoint_in=("note",),
        how="A `params` mapping plus the vendor's credit headers. Written by "
            "capture_nfl_odds_fixture.py, which since ADR 0157 also emits the "
            "canonical `request` block -- absent from the file on disk because "
            "re-capturing costs credits.",
    ),
    "events_nfl_preseason.json": RecordsItsRequest(
        params_in=("endpoint", "series_ticker"),
        param_names=("series_ticker", "status", "with_nested_markets"),
        endpoint_in=("endpoint",),
        how="The query string is spelled into `endpoint`, so every gate the "
            "capture passed through is readable: this fixture exists because "
            "the league classifier was untested on preseason, and `status=open` "
            "is what decides which events could have been in it.",
    ),
    "events_mlb_props_nested.json": RecordsItsRequest(
        params_in=("endpoint", "series"),
        param_names=("series_ticker", "status", "with_nested_markets"),
        endpoint_in=("endpoint",),
        how="`endpoint` carries the query template and `series` names the two "
            "substituted into it. It also records `truncation` -- the list is "
            "cut to 4 events per series -- which is the same class of fact: an "
            "absence here can be truncation rather than the API.",
    ),
    "events_nfl_props_nested.json": RecordsItsRequest(
        params_in=("source",),
        param_names=("with_nested_markets", "status"),
        endpoint_in=("source",),
        how="A full URL with its query string under `source`, plus "
            "`keep_events_per_series` for the truncation.",
    ),
    "events_nfl_spread.json": RecordsItsRequest(
        params_in=("series_ticker", "endpoint"),
        param_names=("series_ticker",),
        endpoint_in=("endpoint",),
        how="`endpoint` is the bare URL and `series_ticker` is the one "
            "parameter that mattered -- this capture exists to pin _KNOWN_UNITS "
            "against a real NFL spread subtitle, so which series was asked for "
            "is the whole point of the file.",
    ),
    "markets_settled.json": RecordsItsRequest(
        params_in=("queries",),
        param_names=("series", "status"),
        endpoint_in=("note",),
        how="A `queries` LIST, one entry per call, each with its series, its "
            "status and how many rows came back -- including the one that "
            "returned HTTP 400. The strongest envelope in the repo: it records "
            "a request that FAILED, which is the only way `status=finalized` "
            "being rejected is readable at all.",
    ),
    "series_fee_fields.json": RecordsItsRequest(
        params_in=("payloads", "endpoint"),
        param_names=("ticker",),
        endpoint_in=("endpoint",),
        how="`endpoint` is the `/series/{ticker}` template and `payloads` is "
            "keyed by the tickers substituted into it, so the four series asked "
            "for are exactly the four keys.",
    ),
    "market_single.json": RecordsItsRequest(
        params_in=("ticker", "event_ticker"),
        param_names=("ticker",),
        endpoint_in=("note",),
        how="`note` names all three endpoints the document holds side by side "
            "and `ticker` is the parameter common to them. The point of the "
            "fixture is that /events and /markets/{t} agree field for field, "
            "which needs the reader to know they were asked about one market.",
    ),
    "candlesticks_mlb.json": RecordsItsRequest(
        params_in=("markets",),
        param_names=("series_ticker", "period_interval", "start_ts", "end_ts"),
        endpoint_in=("note",),
        how="The request is per market and stored beside each response: the "
            "series, the interval and the window. A candlestick series is "
            "meaningless without its window -- a missing bar is a bar outside "
            "start_ts..end_ts until proven otherwise.",
    ),

    # -- Not a capture: nothing third-party is stored verbatim ----------------
    "portfolio_balance_shape.json": NotACapture(
        reason="SYNTHETIC, and deliberately so. A real /portfolio/balance "
               "body is Joe's account balance -- operator data, which never "
               "enters this public repo even sanitized -- so this follows "
               "ADR 0035's precedent: a synthetic payload plus a shape "
               "assertion. There is no request because no call was made to "
               "produce it. The SHAPE it asserts is not invented: it was "
               "read off 72 real payloads held outside the repo under "
               "data/ (gitignored), which returned exactly one shape. "
               "docs/measurements/2026-09-18-the-shard-balance-is-dollars.md.",
    ),
    "create_order_responses.json": NotACapture(
        reason="Hand-written SYNTHETIC payloads. Its own `_provenance` says so "
               "and names the runbook and the SHA-256 of the real C0 probe "
               "capture, which is operator data and is deliberately not "
               "committed. There is no request because no call was made here.",
    ),
    "anthropic_scout_report.json": NotACapture(
        reason="SDK-DERIVED, not captured: built by "
               "scripts/build_agent_wire_fixture.py and validated against the "
               "installed SDK's own pydantic models. No Anthropic call is made "
               "to produce it and no key is needed. Its docstring states the "
               "weaker claim plainly, which is why this is a classification "
               "rather than a violation.",
    ),
    "anthropic_scout_refusal.json": NotACapture(
        reason="Same as anthropic_scout_report.json -- SDK-derived by "
               "scripts/build_agent_wire_fixture.py, no call made.",
    ),
    "combo_collections_summary.json": NotACapture(
        reason="Derived counts over the collections walk (1,389 collections, "
               "13,986 legs, 0 with active quoters), not a stored response.",
    ),
    "sports_coverage.json": NotACapture(
        reason="Derived counts and a series list computed from the "
               "events_sports_nested.json walk. No response body.",
    ),
    "price_grids.json": NotACapture(
        reason="One entry per DISTINCT price grid across 1,426 game markets -- "
               "a de-duplicated derivation, not a payload. `note` names the "
               "endpoint the values were read out of.",
    ),
    "occurrence_datetime_probe.json": NotACapture(
        reason="A probe's derived tables -- period pairs, settlement lag "
               "medians, expiration disagreements -- computed across many "
               "calls. Individual field values are verbatim; no response body "
               "is stored, so there is no single request to record.",
    ),

    # -- Real captures with no request record. Named, costed exceptions. ------
    "odds_mlb_player_props.json": RequestUnrecorded(
        reason="**The fixture this whole file exists for.** The bare per-event "
               "Odds API response object: no params, no endpoint, no regions. "
               "Its nine books are all US books, which is what BOTH 'EU books "
               "quote no props' and 'this capture never asked for EU' predict. "
               "ADR 0157 records the finding as unverified on exactly this "
               "ground and answers the question from live odds_snapshots "
               "instead, for zero credits.",
        cost="Odds API credits, against a 700/day cap on a four-sport weekend. "
             "The operator's call, not a test's, and not this lane's.",
        writer="none -- no script in scripts/ writes this file. Captured by "
               "hand for commit fa18077 (props slice 1, 2026-08-14).",
    ),
    "anthropic_scout_captured.json": RequestUnrecorded(
        reason="A real Anthropic Messages response, stored as the bare message "
               "object. The request -- model, tools, system prompt, the "
               "messages themselves -- is nowhere in it, so what the Scout was "
               "ASKED cannot be read off what it answered.",
        cost="Anthropic tokens. Cheap in money; the fleet is retired "
             "(review_retired refuses every row), so nothing routine "
             "re-captures it.",
        writer="none -- captured by hand for commit c2976ec. "
               "scripts/build_agent_wire_fixture.py writes the two SDK-derived "
               "siblings, not this one.",
    ),
    "candlesticks_pregame_mlb.json": RequestUnrecorded(
        reason="Carries series_ticker and event_ticker but NOT the candlestick "
               "window -- no period_interval, no start_ts, no end_ts. So an "
               "absent bar cannot be told from a bar outside the window, which "
               "is the same shape of confound as the prop fixture. Its sibling "
               "candlesticks_mlb.json records all three.",
        cost="Free. Unauthenticated Kalshi read -- but the pregame window it "
             "was captured in has passed, so a re-capture is a different "
             "observation, not the same one.",
        writer="none -- no script in scripts/ writes this file.",
    ),
    "combo_collections.json": RequestUnrecorded(
        reason="Keyed by series ticker, which reads like a parameter and is "
               "not: the walk asks for everything and groups the answer. "
               "Neither the endpoint nor the page/limit walk is recorded, and "
               "the entries are truncated to 12 associated events "
               "(`_truncated_from` is kept per entry, which is the one absence "
               "this file can explain).",
        cost="Free. Read-only GET, no credentials, no credits -- "
             "scripts/capture_combo_fixtures.py.",
        writer="scripts/capture_combo_fixtures.py",
    ),
    "combo_priced_markets.json": RequestUnrecorded(
        reason="Combination markets minted by Kalshi's own users, read while "
               "still quoted, with each referenced leg read at the same time. "
               "Which pages of /markets were sampled is not recorded -- and "
               "sampling is exactly what went wrong here before: the docstring "
               "of its writer records that sampling the wrong pages says 'no "
               "combo is ever priced' with complete conviction.",
        cost="Free GET, but the quote decays within a couple of minutes of "
             "creation, so a re-capture samples a different population.",
        writer="scripts/capture_combo_fixtures.py",
    ),
    "combo_lookup_response.json": RequestUnrecorded(
        reason="The verbatim POST .../lookup response. The lookup's request -- "
               "the collection and the legs selected -- is only readable as the "
               "response's own `custom_strike` echo, which is the venue's "
               "account of the request, not ours.",
        cost="Free in money and NOT free in effect: a lookup MINTS a market on "
             "Kalshi. That is a side effect on a live venue, which is a reason "
             "to re-run it deliberately or not at all.",
        writer="scripts/capture_combo_lookup.py",
    ),
    "combo_lookup_orderbook.json": RequestUnrecorded(
        reason="Two empty arrays under `orderbook_fp` and nothing else -- 76 "
               "bytes. The single most absence-shaped fixture in the repo: it "
               "IS an absence, and it does not say which market's book was "
               "read or when. It is readable only because its sibling "
               "combo_lookup_response.json sits beside it in one commit.",
        cost="Free GET, but only against a market a lookup has already minted.",
        writer="scripts/capture_combo_lookup.py",
    ),
    "combo_lookup_repeat.json": RequestUnrecorded(
        reason="Records the collection ticker, the scope and the selected "
               "markets -- genuinely most of the request -- but no endpoint and "
               "no method, and the question it answers ('does a second "
               "identical lookup return the same ticker?') is entirely about "
               "the request being identical.",
        cost="Free in money; mints markets on the live venue, twice by design.",
        writer="scripts/capture_combo_repeat_lookup.py",
    ),
    "combo_orderbooks.json": RequestUnrecorded(
        reason="A bare list of {ticker, orderbook_fp}. The tickers are the "
               "request, so this is closer than most -- but there is no "
               "endpoint, no timestamp, and no record of how the twenty were "
               "chosen out of the population, which is the selection question "
               "ADR 0012 section 5 turns on.",
        cost="Free unauthenticated GET, one call per ticker.",
        writer="none -- no script in scripts/ writes this file.",
    ),
    "espn_scoreboard_mlb_20260809.json": RequestUnrecorded(
        reason="A verbatim ESPN scoreboard body with no envelope at all. The "
               "date is in the FILENAME, which is the weakest possible place "
               "for a request parameter: a rename loses it and nothing notices.",
        cost="Free unauthenticated read -- but 2026-08-09 is past, and ESPN's "
               "scoreboard for a past date is not guaranteed to return what it "
               "returned on the day.",
        writer="none -- no script in scripts/ writes this file.",
    ),
    "espn_scoreboard_wnba_20260809.json": RequestUnrecorded(
        reason="Same as the MLB scoreboard: verbatim body, no envelope, league "
               "and date carried only by the filename.",
        cost="Free unauthenticated read; the date has passed.",
        writer="none -- no script in scripts/ writes this file.",
    ),
    "events_sports_nested.json": RequestUnrecorded(
        reason="A bare LIST of 32 event objects -- there is no top-level object "
               "for an envelope to live in. The most-loaded fixture in the "
               "repo: thirteen modules and scripts read it. Two other captures "
               "exist ONLY because of what it does not contain (no preseason "
               "event, no prop ladder), and both of those had to be argued "
               "from the shape of the data rather than read off the request.",
        cost="Free unauthenticated Kalshi read. Cheap in credits and NOT cheap "
             "in blast radius -- re-capturing changes the input of every test "
             "that loads it, so it is a deliberate change, not a refresh.",
        writer="scripts/capture_fixtures.py",
    ),
    "nfl_names_kalshi.json": RequestUnrecorded(
        reason="A reduced capture -- team names and kickoff only. A reduction "
               "drops more than a full capture does, so its request matters "
               "MORE: `--league` picks the series and `--limit` truncates the "
               "page walk, so a team absent here could be a team Kalshi does "
               "not list, a team past the limit, or a league nobody asked for. "
               "FIXED IN THE WRITER: scripts/capture_team_names.py now writes "
               "a `request` block; this file predates that and stays as it is.",
        cost="Free unauthenticated Kalshi read, but the same run also spends "
             "Odds API credits for the _books half, so the pair is not free.",
        writer="scripts/capture_team_names.py",
    ),
    "nfl_names_books.json": RequestUnrecorded(
        reason="The Odds API half of the same run: fixture id, kickoff and the "
               "two team names, no odds. Records neither the sport key nor the "
               "endpoint. FIXED IN THE WRITER -- see nfl_names_kalshi.json.",
        cost="Odds API credits.",
        writer="scripts/capture_team_names.py",
    ),
    "ncaaf_names_kalshi.json": RequestUnrecorded(
        reason="Same reduced Kalshi capture, --league ncaaf. FIXED IN THE "
               "WRITER -- see nfl_names_kalshi.json.",
        cost="Free unauthenticated Kalshi read.",
        writer="scripts/capture_team_names.py",
    ),
    "ncaaf_names_books.json": RequestUnrecorded(
        reason="Same reduced Odds API capture, --league ncaaf. FIXED IN THE "
               "WRITER -- see nfl_names_kalshi.json.",
        cost="Odds API credits.",
        writer="scripts/capture_team_names.py",
    ),
    "portfolio_fills_redacted.json": RequestUnrecorded(
        reason="Names its `endpoint` (/portfolio/fills) and not its parameters "
               "-- no limit, no cursor, no window. So the set of fills in it "
               "cannot be told from the set of fills in the account.",
        cost="Cannot be re-captured from this repo at all. It is redacted from "
             "a gitignored capture of a real account (operator data never "
             "enters the repo), so restoring the envelope means re-running the "
             "redactor against a capture only the operator holds.",
        writer="scripts/redact_captures.py",
    ),
    "portfolio_settlements_redacted.json": RequestUnrecorded(
        reason="Same as portfolio_fills_redacted.json: endpoint recorded, "
               "parameters not.",
        cost="Cannot be re-captured from this repo -- operator data.",
        writer="scripts/redact_captures.py",
    ),
    "ws_orderbook_stream.json": RequestUnrecorded(
        reason="A WebSocket recording, where the 'request' is the subscribe "
               "command. Only the server's `subscribed` ACK is stored, not the "
               "command sent -- and `tickers` lists what was subscribed without "
               "saying which channels were asked for. A frame type absent from "
               "`counts` is therefore unreadable: never sent, or never "
               "subscribed to.",
        cost="Free, and only live -- a stream cannot be re-captured for a past "
             "moment at all.",
        writer="scripts/capture_ws_fixture.py",
    ),
}


#: The ratchet. Equality, not containment: a new envelope-less capture fails,
#: and so does removing one without deleting its row here, which is how a fix
#: gets noticed instead of quietly leaving the table stale.
#:
#: Nineteen entries on 2026-09-15. This number may go DOWN when a fixture is
#: re-captured with its request recorded. It may not go up.
UNRECORDED_ON_2026_09_15 = frozenset(
    {
        "anthropic_scout_captured.json",
        "candlesticks_pregame_mlb.json",
        "combo_collections.json",
        "combo_lookup_orderbook.json",
        "combo_lookup_repeat.json",
        "combo_lookup_response.json",
        "combo_orderbooks.json",
        "combo_priced_markets.json",
        "espn_scoreboard_mlb_20260809.json",
        "espn_scoreboard_wnba_20260809.json",
        "events_sports_nested.json",
        "ncaaf_names_books.json",
        "ncaaf_names_kalshi.json",
        "nfl_names_books.json",
        "nfl_names_kalshi.json",
        "odds_mlb_player_props.json",
        "portfolio_fills_redacted.json",
        "portfolio_settlements_redacted.json",
        "ws_orderbook_stream.json",
    }
)


#: Capture scripts that predate `scripts/capture_envelope.py`. Each names the
#: fixtures it writes, and those must be classified above -- so the writer half
#: and the fixture half of this file cannot drift apart.
#:
#: A script that writes into `tests/fixtures/` and is neither here nor an
#: importer of the helper fails `test_every_script_that_writes_a_fixture_-
#: records_its_request`. That is the fail-closed half: the population is
#: enumerated from the directory, not remembered.
LEGACY_WRITERS: dict[str, tuple[str, ...]] = {
    "build_agent_wire_fixture.py": (
        "anthropic_scout_report.json",
        "anthropic_scout_refusal.json",
    ),
    "capture_combo_fixtures.py": (
        "combo_collections.json",
        "combo_collections_summary.json",
        "combo_priced_markets.json",
    ),
    "capture_combo_lookup.py": (
        "combo_lookup_response.json",
        "combo_lookup_orderbook.json",
    ),
    "capture_combo_repeat_lookup.py": ("combo_lookup_repeat.json",),
    "capture_fixtures.py": (
        "events_sports_nested.json",
        "sports_coverage.json",
    ),
    "capture_market_fixture.py": ("market_single.json",),
    "capture_nfl_prop_fixture.py": ("events_nfl_props_nested.json",),
    "capture_nfl_spread_subtitles.py": ("events_nfl_spread.json",),
    "capture_preseason_fixture.py": ("events_nfl_preseason.json",),
    "capture_price_grids.py": ("price_grids.json",),
    "capture_prop_fixture.py": ("events_mlb_props_nested.json",),
    "capture_series_fixture.py": ("series_fee_fields.json",),
    "capture_settled_markets.py": ("markets_settled.json",),
    "capture_ws_fixture.py": ("ws_orderbook_stream.json",),
    "measure_occurrence_datetime.py": ("occurrence_datetime_probe.json",),
    "redact_captures.py": (
        "portfolio_fills_redacted.json",
        "portfolio_settlements_redacted.json",
    ),
}

#: Capture scripts that write through `scripts/capture_envelope.py`. Their next
#: capture cannot be written without a `request` block, because `write_capture`
#: refuses one. Rewired for ADR 0157, in this commit:
#:
#:   capture_nfl_odds_fixture.py  writes the odds fixture whose silent sibling
#:                               started this. Emits the canonical `request`
#:                               block alongside the legacy `params` key, both
#:                               built from the same module constants so they
#:                               cannot drift.
#:   capture_team_names.py       writes FOUR of the nineteen envelope-less
#:                               fixtures. A reduced capture drops more than a
#:                               full one, so `--league` and `--limit` are the
#:                               difference between "Kalshi does not list this
#:                               team" and "this team was past the limit".
#:
#: The files already on disk still have no envelope: re-capturing them costs
#: Odds API credits and is the operator's call. This fixes the NEXT one.
UPGRADED_WRITERS: dict[str, tuple[str, ...]] = {
    "capture_nfl_odds_fixture.py": ("odds_nfl_h2h_spreads.json",),
    "capture_team_names.py": (
        "nfl_names_kalshi.json",
        "nfl_names_books.json",
        "ncaaf_names_kalshi.json",
        "ncaaf_names_books.json",
    ),
}

#: Every fixture some script in `scripts/` produces. Derived, so it cannot drift
#: from the two tables above. A `RequestUnrecorded` row claiming no writer is
#: checked against this -- a fixture with a writer can be re-captured by running
#: something, and one without cannot, which is a real difference in what the
#: exception costs to lift.
WRITTEN_BY_A_SCRIPT = frozenset(
    name
    for written in list(LEGACY_WRITERS.values()) + list(UPGRADED_WRITERS.values())
    for name in written
)

#: A script counts as a fixture writer when it names the fixtures directory as a
#: path and writes. Both halves matter: a script that only READS a fixture
#: (`census_odds_stamps.py`, `demo_combos.py`) is not a writer, and a script
#: that writes elsewhere (`capture_fills_fixture.py` -> `data/captures/`,
#: gitignored) is not one either.
_FIXTURES_PATH_EXPRESSION = re.compile(r'"tests"\s*/\s*"fixtures"')
_WRITE_CALL = ("write_text", "write_capture")

#: The three sharp books this repo buys. A sharp anchor selects at most three
#: (`backend/core/devig.py`), and all three are EU-region -- dropping "eu"
#: zeroes the anchor. Their absence from a props capture is the observation ADR
#: 0157's dead finding rested on.
SHARP_BOOKS = ("pinnacle", "matchbook", "betfair_ex_eu")

#: MLBAM markers. Committing any of these breaks ADR 0035 and CLAUDE.md.
MLBAM_MARKERS = ("statsapi.mlb.com", "gdx.mlb.com", "MLBAM", "mlbam")


def _fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURES.glob("*.json"))


def _load(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _fixture_writers() -> dict[str, str]:
    """{script name: source}, for every script that writes into tests/fixtures/."""
    found: dict[str, str] = {}
    for path in sorted(SCRIPTS.glob("*.py")):
        source = path.read_text(encoding="utf-8", errors="replace")
        if not _FIXTURES_PATH_EXPRESSION.search(source):
            continue
        if not any(call in source for call in _WRITE_CALL):
            continue
        found[path.name] = source
    return found


def _mentions_a_param(node: Any, name: str) -> bool:
    """Is `name` a key anywhere under `node`, or inside any string value?

    The string arm is what accepts a query string spelled into an `endpoint`
    field. It is deliberately scoped to the subtree the table names, never to
    the whole document -- a search over the whole file would match the payload
    and pass on anything.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key) == name or _mentions_a_param(value, name):
                return True
        return False
    if isinstance(node, list):
        return any(_mentions_a_param(item, name) for item in node)
    if isinstance(node, str):
        return name in node
    return False


# --------------------------------------------------------------------------
# The fixture half
# --------------------------------------------------------------------------
class TestEveryFixtureIsClassified:
    def test_no_fixture_is_missing_from_the_table(self) -> None:
        unclassified = [n for n in _fixture_names() if n not in DISPOSITIONS]
        assert not unclassified, (
            f"{len(unclassified)} fixture(s) are not classified in "
            f"DISPOSITIONS: {unclassified}. Classify each one: "
            "RecordsItsRequest if the document says what was asked for, "
            "NotACapture if no third-party response body is stored, or "
            "RequestUnrecorded (and add it to UNRECORDED_ON_2026_09_15) if it "
            "is a real capture with no request record -- naming the reason, "
            "the cost of getting one, and the writer. A new capture should "
            "write through scripts/capture_envelope.write_capture instead, "
            "which makes the first option the default."
        )

    def test_no_table_row_names_a_fixture_that_is_gone(self) -> None:
        present = set(_fixture_names())
        stale = sorted(n for n in DISPOSITIONS if n not in present)
        assert not stale, (
            f"DISPOSITIONS names fixture(s) that no longer exist: {stale}. "
            "Delete the rows -- a table that outlives its files stops being "
            "read as a description of the directory."
        )


class TestARecordedRequestIsCheckedNotAsserted:
    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "RECORDED"),
    )
    def test_a_fixture_that_claims_to_record_its_request_actually_does(
        self, name: str
    ) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, RecordsItsRequest)
        document = _load(name)
        assert isinstance(document, dict), (
            f"{name} claims to record its request but is a "
            f"{type(document).__name__} at top level, so there is nowhere for "
            "an envelope to live."
        )
        for key in entry.params_in:
            assert key in document, (
                f"{name}: DISPOSITIONS says the request parameters live under "
                f"{key!r} and the fixture has no such key. The table drifted "
                "from the file -- fix whichever one is wrong."
            )
            assert document[key], f"{name}: {key!r} is present but empty."

        subtree = {key: document[key] for key in entry.params_in}
        for param in entry.param_names:
            assert _mentions_a_param(subtree, param), (
                f"{name}: the parameter {param!r} is not findable under "
                f"{list(entry.params_in)}. Either it was not recorded after "
                "all, or the table names the wrong keys."
            )

    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "RECORDED"),
    )
    def test_a_recorded_request_names_the_endpoint_it_was_sent_to(
        self, name: str
    ) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, RecordsItsRequest)
        document = _load(name)
        for key in entry.endpoint_in:
            assert key in document, f"{name}: no {key!r} key to read an endpoint from."
            value = document[key]
            assert isinstance(value, str) and value.strip(), (
                f"{name}: {key!r} should be a non-empty string naming the "
                f"endpoint, got {value!r}."
            )
            assert "/" in value, (
                f"{name}: {key!r} is {value!r}, which does not read as a path "
                "or a URL. Parameters without an endpoint are half a request: "
                "us+eu on WHICH endpoint is the question ADR 0157 turns on."
            )

    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "RECORDED"),
    )
    def test_a_recorded_fixture_explains_how_it_records_it(self, name: str) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, RecordsItsRequest)
        assert len(entry.how.strip()) > 40, (
            f"{name}: `how` is the sentence a later reader uses to decide "
            "whether this shape is worth copying. One word is not one."
        )


class TestAnExceptionIsADecisionSomeoneWroteDown:
    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "UNRECORDED"),
    )
    def test_every_unrecorded_capture_names_a_reason_a_cost_and_a_writer(
        self, name: str
    ) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, RequestUnrecorded)
        assert len(entry.reason.strip()) > 40, (
            f"{name}: an exception without a reason is a gap wearing a table's "
            "clothes."
        )
        assert len(entry.cost.strip()) > 10, (
            f"{name}: name the cost of getting the request record back. It is "
            "the whole decision -- a free Kalshi read and an Odds API "
            "re-capture against a 700/day cap are not the same exception."
        )
        assert entry.writer.strip(), f"{name}: name the writer, or say there is none."

    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "UNRECORDED"),
    )
    def test_a_named_writer_is_a_script_that_exists(self, name: str) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, RequestUnrecorded)
        if entry.writer.startswith("none"):
            assert name not in WRITTEN_BY_A_SCRIPT, (
                f"{name}: the table says no script writes it, but a writer in "
                "LEGACY_WRITERS or UPGRADED_WRITERS claims it. A fixture with "
                "a writer can be re-captured by running something and one "
                "without cannot, so the exception costs a different thing to "
                "lift."
            )
            return
        assert (ROOT / entry.writer).exists(), (
            f"{name}: DISPOSITIONS names {entry.writer} as its writer and that "
            "file does not exist."
        )
        assert name in WRITTEN_BY_A_SCRIPT, (
            f"{name}: DISPOSITIONS names {entry.writer} as its writer, but that "
            "script's row does not list this fixture among what it writes."
        )

    @pytest.mark.parametrize(
        "name",
        sorted(n for n, d in DISPOSITIONS.items() if d.kind == "NOT_A_CAPTURE"),
    )
    def test_a_non_capture_says_why_it_is_not_one(self, name: str) -> None:
        entry = DISPOSITIONS[name]
        assert isinstance(entry, NotACapture)
        assert len(entry.reason.strip()) > 40, (
            f"{name}: 'not a capture' is the one classification that EXEMPTS a "
            "file rather than checking it, so it is the one that has to argue."
        )


class TestTheRatchet:
    def test_the_set_of_captures_without_a_request_record_does_not_grow(self) -> None:
        today = frozenset(
            n for n, d in DISPOSITIONS.items() if d.kind == "UNRECORDED"
        )
        added = sorted(today - UNRECORDED_ON_2026_09_15)
        assert not added, (
            f"New capture(s) with no request record: {added}. This is the "
            "defect ADR 0157 named, arriving again. Write the capture through "
            "scripts/capture_envelope.write_capture, which refuses a document "
            "with no `request` block -- do not add a row here to make this "
            "pass."
        )
        removed = sorted(UNRECORDED_ON_2026_09_15 - today)
        assert not removed, (
            f"{removed} no longer needs an exception -- good. Delete the "
            "entries from UNRECORDED_ON_2026_09_15 so the frozen set keeps "
            "meaning what it says."
        )


class TestThePropFixtureIsTheWorkedExample:
    """The confound, pinned. This is the finding ADR 0157 refused to publish."""

    def test_the_prop_fixture_cannot_tell_an_unquoted_book_from_an_unasked_one(
        self,
    ) -> None:
        document = _load("odds_mlb_player_props.json")

        # 1. It records nothing about the request.
        for key in ("params", "request", "regions", "endpoint", "source"):
            assert key not in document, (
                f"odds_mlb_player_props.json now carries {key!r}. If the "
                "request was recovered, ADR 0157's confound is resolved: move "
                "this fixture to RecordsItsRequest, drop it from "
                "UNRECORDED_ON_2026_09_15, and rewrite this test to assert "
                "what the request actually was."
            )

        # 2. Not one sharp book is in it.
        books = [b["key"] for b in document["bookmakers"]]
        present_sharps = sorted(set(books) & set(SHARP_BOOKS))
        assert not present_sharps, (
            f"A sharp book appears in the prop fixture: {present_sharps}. That "
            "would settle ADR 0157's question in the affirmative from the "
            "fixture alone -- re-read the ADR before changing anything."
        )

        # 3. And that is exactly what regions=us returns, so the file is
        #    consistent with both hypotheses and separates neither.
        assert len(books) == 9, (
            f"The prop fixture returned {len(books)} books, not the nine ADR "
            "0157 reasons about. The ADR's arithmetic was done on nine."
        )
        assert len(set(books)) == len(books), "A book appears twice; re-read the file."

    def test_its_sibling_records_the_regions_that_make_the_same_absence_readable(
        self,
    ) -> None:
        """The contrast is the argument: one file can answer, the other cannot."""
        sibling = _load("odds_mlb_h2h_spreads_totals.json")
        regions = sibling["params"]["regions"]
        assert "eu" in regions, (
            "The team fixture no longer records asking for EU, which is the "
            "only reason its book list can be read as evidence about EU books."
        )
        books = {
            b["key"] for e in sibling["events"] for b in e.get("bookmakers", [])
        }
        found = sorted(books & set(SHARP_BOOKS))
        assert found, (
            "No sharp book in the team fixture either. ADR 0157's contrast "
            "rests on all four sharps appearing on team markets under us+eu; "
            "if that is no longer true the ADR needs re-reading, not this test "
            "relaxing."
        )


class TestTheRuleDoesNotDemandAPayloadThatMayNotExist:
    def test_no_fixture_carries_an_mlbam_payload(self) -> None:
        """CLAUDE.md and ADR 0035: MLBAM Materials never enter this public repo.

        This is here so the ratchet above can never be read as 'every source
        needs a committed capture with an envelope'. MLB is the deliberate
        exception -- synthetic payloads with a shape assertion -- and the
        inconsistency is the decision.
        """
        offenders: list[str] = []
        for name in _fixture_names():
            text = (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
            if any(marker in text for marker in MLBAM_MARKERS):
                offenders.append(name)
        assert not offenders, (
            f"MLBAM payload markers found in {offenders}. This repo is public "
            "and MLBAM's terms permit 'only individual, non-commercial, "
            "non-bulk use'. See ADR 0035: MLB tests use synthetic payloads "
            "with a shape assertion, and no envelope rule overrides that."
        )

    def test_no_mlbam_source_is_listed_in_the_table(self) -> None:
        assert not [n for n in DISPOSITIONS if "mlbam" in n.lower()], (
            "DISPOSITIONS names an MLBAM fixture. There must not be one to "
            "classify."
        )


class TestRecordingAParameterMustNotRecordACredential:
    def test_no_fixture_carries_the_odds_api_credential_marker(self) -> None:
        """The hazard this rule creates, closed on the files already on disk.

        The Odds API takes its key as a query parameter, so 'write down every
        parameter you sent' is exactly the instruction that leaked it once
        (`backend/logging_setup.py` exists because of that). `apiKey` catches a
        serialised request URL even after a rotation.
        """
        offenders = [
            name
            for name in _fixture_names()
            if "apiKey" in (FIXTURES / name).read_text(encoding="utf-8", errors="replace")
        ]
        assert not offenders, (
            f"{offenders} contain the string 'apiKey', which means a request "
            "URL carrying the Odds API credential has been serialised into a "
            "public repo. Rotate the key."
        )


# --------------------------------------------------------------------------
# The writer half -- fail-closed over a population the test enumerates
# --------------------------------------------------------------------------
class TestANewCaptureCannotBeWrittenWithoutItsRequest:
    def test_every_script_that_writes_a_fixture_is_classified(self) -> None:
        """Fail-closed over a population the test enumerates, not a memory.

        The directory decides who is in scope. A new capture script is found by
        the walk and fails for not being in either table -- which is the point,
        because the defect ADR 0157 named arrived as a capture nobody thought
        to check.
        """
        unclassified = sorted(
            name
            for name in _fixture_writers()
            if name not in LEGACY_WRITERS and name not in UPGRADED_WRITERS
        )
        assert not unclassified, (
            f"Script(s) write into tests/fixtures/ and are in neither table: "
            f"{unclassified}. A NEW script goes through "
            "scripts/capture_envelope.write_capture, which refuses a document "
            "with no `request` block, and gets a UPGRADED_WRITERS row. "
            "LEGACY_WRITERS is for scripts that predate the helper -- adding a "
            "new one there re-introduces the defect."
        )

    def test_no_script_is_in_both_tables(self) -> None:
        overlap = sorted(set(LEGACY_WRITERS) & set(UPGRADED_WRITERS))
        assert not overlap, f"{overlap} is listed as both legacy and upgraded."

    @pytest.mark.parametrize(
        "script", sorted(set(LEGACY_WRITERS) | set(UPGRADED_WRITERS))
    )
    def test_a_writer_row_names_fixtures_that_are_classified(self, script: str) -> None:
        written = LEGACY_WRITERS.get(script) or UPGRADED_WRITERS[script]
        assert (SCRIPTS / script).exists(), f"{script} is gone; drop its row."
        assert written, f"{script}: name the fixtures it writes."
        for fixture in written:
            assert fixture in DISPOSITIONS, (
                f"{script} writes {fixture}, which is not classified in "
                "DISPOSITIONS. The writer half and the fixture half have "
                "drifted apart."
            )

    @pytest.mark.parametrize("script", sorted(UPGRADED_WRITERS))
    def test_an_upgraded_writer_still_goes_through_the_helper(
        self, script: str
    ) -> None:
        """Pins the fix, not the intention.

        A refactor that drops the `write_capture` call would restore the defect
        with every other test in this file still green.
        """
        sources = _fixture_writers()
        assert script in sources, (
            f"{script} is no longer detected as a fixture writer. Either it "
            "stopped writing fixtures or _fixture_writers() stopped seeing it "
            "-- the second would make the whole writer half vacuous."
        )
        assert "write_capture(" in sources[script], (
            f"{script} no longer calls write_capture, so nothing stops its next "
            "capture being written without a request record."
        )
        assert "request_envelope(" in sources[script], (
            f"{script} calls write_capture without building a request_envelope; "
            "a hand-assembled block is re-validated but is one edit from being "
            "wrong."
        )

    def test_no_legacy_writer_row_survives_its_upgrade(self) -> None:
        sources = _fixture_writers()
        upgraded = sorted(
            name
            for name in LEGACY_WRITERS
            if "capture_envelope" in sources.get(name, "")
        )
        assert not upgraded, (
            f"{upgraded} now use scripts/capture_envelope. Move the row to "
            "UPGRADED_WRITERS -- a legacy list nobody prunes stops reading as a "
            "backlog."
        )


class TestTheHelperIsTheGate:
    def test_it_refuses_a_document_with_no_request_block(self) -> None:
        with pytest.raises(CaptureEnvelopeError, match="carries no 'request'"):
            assert_records_its_request({"events": [1, 2, 3]}, what="a capture")

    def test_it_refuses_an_empty_parameter_map(self) -> None:
        """An empty dict reads exactly like a forgotten one."""
        with pytest.raises(CaptureEnvelopeError, match="non-empty `params`"):
            request_envelope(endpoint="/v4/sports/x/odds", params={})

    def test_it_refuses_an_empty_endpoint(self) -> None:
        with pytest.raises(CaptureEnvelopeError, match="non-empty `endpoint`"):
            request_envelope(endpoint="  ", params={"regions": "us"})

    def test_it_refuses_a_credential_shaped_parameter_name(self) -> None:
        with pytest.raises(CaptureEnvelopeError, match="credential-shaped"):
            request_envelope(
                endpoint="/v4/sports/baseball_mlb/odds",
                params={"regions": "us", "apiKey": "abc123"},
            )

    def test_it_refuses_a_live_credential_hiding_under_an_innocent_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Refusing by NAME alone would miss `{"q": "<the key>"}`."""
        monkeypatch.setenv("ODDS_API_KEY", "s3cr3t-live-key")
        with pytest.raises(CaptureEnvelopeError, match="ODDS_API_KEY"):
            request_envelope(
                endpoint="/v4/sports/baseball_mlb/odds",
                params={"regions": "us", "q": "s3cr3t-live-key"},
            )

    def test_it_accepts_a_request_that_says_what_was_asked_for(self) -> None:
        envelope = request_envelope(
            endpoint="/v4/sports/baseball_mlb/odds",
            params={"regions": "us,eu", "markets": "h2h"},
        )
        assert envelope["method"] == "GET"
        assert envelope["params"]["regions"] == "us,eu"
        assert_records_its_request({"request": envelope, "events": []}, what="ok")

    def test_it_revalidates_a_hand_assembled_request_block(self) -> None:
        """A check that only runs on the happy path is not a check."""
        with pytest.raises(CaptureEnvelopeError):
            assert_records_its_request(
                {"request": {"method": "GET", "endpoint": "", "params": {"a": 1}}},
                what="a hand-assembled document",
            )

    def test_write_capture_writes_nothing_when_it_refuses(self, tmp_path: Path) -> None:
        """The refusal has to happen BEFORE the file exists, or it is advice."""
        target = tmp_path / "capture.json"
        with pytest.raises(CaptureEnvelopeError):
            write_capture(target, {"events": []})
        assert not target.exists()

    def test_write_capture_runs_the_callers_guard_on_the_exact_text(
        self, tmp_path: Path
    ) -> None:
        """`capture_nfl_odds_fixture.py` scans for its credential this way."""
        seen: list[str] = []
        target = tmp_path / "capture.json"
        write_capture(
            target,
            {
                "request": request_envelope(
                    endpoint="/events", params={"series_ticker": "KXMLBGAME"}
                ),
                "events": [],
            },
            before_write=seen.append,
        )
        assert seen and seen[0] == target.read_text(encoding="utf-8")
        assert "KXMLBGAME" in seen[0]
