"""The parlay ladder resolves team names with the league's own alias file.

**It never did.** `ladder_candidates` loaded aliases with `event_links.league`,
which holds Kalshi's `product_metadata.competition` verbatim -- measured on this
repo's own database as `'Pro Baseball'`, `'Pro Basketball (W)'`,
`'Pro Football'`. The alias files are named for The Odds API's sport keys
(`baseball_mlb.yaml`, `americanfootball_nfl.yaml`). `load_aliases` returns an
empty `TeamAliases` for a missing file rather than raising -- correctly, because
most leagues need no overrides -- so the lookup failed open and silent, and the
ladder ran with **zero** aliases from the day it was built.

Nothing caught it because the shared test seeder wrote `league = 'baseball_mlb'`
into `event_links`: the fixture encoded the same misconception as the code, so
the two agreed. The seeder now writes what production writes.

WHAT THIS DOES NOT ESTABLISH
----------------------------
- **That any leg on today's slate changes.** Measured, 2026-08-26: of the 13
  entries across `baseball_mlb.yaml` and `americanfootball_nfl.yaml`, **0
  require the alias** -- the token-prefix rule resolves every one on its own
  (both files say as much in their own comments). So on the leagues this
  instance currently carries, the bug was **real and inert**: the ladder ran
  alias-free and got the same answer anyway.

  That is the honest report, and it is not an argument that the fix does not
  matter. It matters the moment a league needs a genuine override, and the one
  arriving this weekend is exactly that league: `Ole Miss`/`Mississippi`,
  `USC`/`Southern California`, `Pitt`/`Pittsburgh` are none of them
  prefix-resolvable. A silent alias-free resolver would have dropped those
  fixtures with no counter and no error.
- **Anything about NCAAF**, whose alias file does not exist yet.

What DOES change today is the string on the card: the leg's `league` was
Kalshi's `'Pro Baseball'` and is now `'baseball_mlb'`, which
`frontend/src/lib/leagueLabel.ts` renders as `MLB` instead of verbatim.
"""

from __future__ import annotations

import pytest

from backend import parlays
from backend.match.linker import TeamAliases, normalise
from backend.store import db as store


def _seed(conn, *, kalshi_team: str, book_team: str, other: str) -> None:
    """One linked MLB game whose two ends spell the team differently.

    `event_links.league` gets the COMPETITION string, exactly as
    `runner.record_link` writes it, so the fixture cannot pass by accident.
    """
    now = store.now_ms()
    event_ticker = "KXMLBGAME-alias"
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_events (event_ticker, title, "
        "first_seen_ms, last_seen_ms) VALUES (?, ?, 0, 0)",
        (event_ticker, f"{other} at {kalshi_team}"),
    )
    conn.execute(
        "INSERT OR IGNORE INTO kalshi_markets (ticker, event_ticker, "
        "yes_side_team, market_type, status, first_seen_ms, last_seen_ms) "
        "VALUES (?, ?, ?, 'moneyline', 'active', 0, 0)",
        (f"{event_ticker}-T", event_ticker, kalshi_team),
    )
    conn.execute(
        "INSERT OR IGNORE INTO event_links (kalshi_event_ticker, odds_event_id, "
        "league, method, commence_skew_ms, linked_ms) "
        "VALUES (?, 'g1', 'Pro Baseball', 'exact_alias_pair', 0, 0)",
        (event_ticker,),
    )
    link_id = conn.execute(
        "SELECT id FROM event_links WHERE kalshi_event_ticker = ?",
        (event_ticker,),
    ).fetchone()["id"]
    conn.execute(
        "INSERT INTO odds_snapshots (fetched_ms, sport_key, odds_event_id, "
        "commence_ms, home_team, away_team, bookmaker, market, outcome_name, "
        "price_decimal) VALUES (?, 'baseball_mlb', 'g1', ?, ?, ?, 'pinnacle', "
        "'h2h', ?, 1.6)",
        (now - 30_000, now + 3_600_000, book_team, other, book_team),
    )
    for outcome, prob in ((book_team, 0.62), (other, 0.36)):
        conn.execute(
            "INSERT INTO fair_prices (computed_ms, link_id, market, "
            "outcome_name, p_multiplicative, p_additive, p_power, p_shin, "
            "p_conservative, book_count, books_used, anchored_on_sharp, "
            "oldest_book_age_ms) "
            "VALUES (?, ?, 'h2h', ?, ?, ?, ?, ?, ?, 3, '[]', 1, 5000)",
            (now - 30_000, link_id, outcome,
             prob + 0.02, prob + 0.01, prob + 0.015, prob + 0.005, prob),
        )
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    c = store.init_db(tmp_path / "aliases.db")
    yield c
    c.close()


class TestTheAliasLookupUsesTheSportKey:
    def test_load_aliases_is_called_with_a_key_that_names_a_file_on_disk(
        self, conn, monkeypatch
    ):
        """The failure was silent because a missing file is a legal answer.

        So the assertion is not "aliases were loaded" -- they always were, and
        they were always empty. It is that the KEY names a file that exists.
        """
        from backend.match import linker

        seen: list[str] = []
        real = parlays.load_aliases

        def spy(key, *a, **kw):
            seen.append(key)
            return real(key, *a, **kw)

        monkeypatch.setattr(parlays, "load_aliases", spy)
        _seed(conn, kalshi_team="Houston", book_team="Houston Astros",
              other="Seattle Mariners")
        parlays.ladder_candidates(conn, now_ms=store.now_ms())

        assert seen, "ladder_candidates loaded no aliases at all"
        for key in seen:
            assert (linker.ALIAS_DIR / f"{key}.yaml").exists(), (
                f"`load_aliases({key!r})` names no file on disk. That returns "
                f"an empty mapping and the ladder runs alias-free, which is "
                f"exactly the bug this test exists for."
            )

    def test_a_leg_needing_a_genuine_override_is_found(self, conn, monkeypatch):
        """Proves the loaded object is USED, not merely fetched.

        `Athletics` is not a token-prefix of `Oakland Athletics` -- the tokens
        are `[athletics]` against `[oakland, athletics]` -- so the
        deterministic rule cannot resolve it and only an alias can. With the
        old lookup this leg is dropped as `no_kalshi_market`.

        **The stub is deliberately key-sensitive, and the first version of this
        test was not.** A stub that returns the override for ANY key passes
        whichever vocabulary the code hands it, so it stayed green when the bug
        was put back -- a guard that could not see the thing it existed to pin.
        It now behaves the way `load_aliases` really behaves: the file exists
        for the sport key and does not exist for the competition string, and a
        missing file is an EMPTY mapping rather than an error.
        """
        real_keys = {"baseball_mlb"}

        def stub(key, *a, **kw):
            if key not in real_keys:
                return TeamAliases(sport_key=key)      # missing file, silently
            return TeamAliases(
                sport_key=key,
                mapping={normalise("Athletics"): normalise("Oakland Athletics")},
            )

        monkeypatch.setattr(parlays, "load_aliases", stub)
        _seed(conn, kalshi_team="Athletics", book_team="Oakland Athletics",
              other="Seattle Mariners")
        legs, excluded = parlays.ladder_candidates(conn, now_ms=store.now_ms())

        assert [leg.team for leg in legs] == ["Oakland Athletics"], (
            f"the override did not reach the resolver; excluded={excluded}"
        )

    def test_the_serialised_league_is_the_sport_key_the_client_can_render(
        self, conn
    ):
        """`leagueLabel` keys on sport keys and renders an unknown key verbatim.

        Serving `'Pro Baseball'` therefore put Kalshi's internal competition
        string on a card where every other screen says `MLB`.
        """
        _seed(conn, kalshi_team="Houston", book_team="Houston Astros",
              other="Seattle Mariners")
        legs, _ = parlays.ladder_candidates(conn, now_ms=store.now_ms())

        assert legs, "fixture produced no candidate leg"
        assert {leg.league for leg in legs} == {"baseball_mlb"}
