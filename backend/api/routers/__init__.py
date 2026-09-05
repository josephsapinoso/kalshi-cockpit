"""Route handlers moved out of `backend/api/routes.py`, one module per desk.

**Why this shape and not `APIRouter`.** `routes.py` was 333,958 bytes on
2026-09-04 -- past the 262,144-byte ceiling at which the Read tool refuses a
file, so no session could open it (`tests/test_session_files_are_readable.py`;
the plan is `docs/decisions/2026-09-04-routes-split-map.md`). Every handler
was a closure inside `create_app`, drawing on locals defined there --
`app_config`, `gate`, `risk`, `staleness`, `odds`, `thresholds`, the shared
`live_quotes()` and `combo_api()` factories, `require_auth`, `get_conn`. An
`APIRouter` rewrite would have meant re-plumbing every one of those through
`Depends` or `app.state`, and a rewrite of a 40 KB order path is not a move.

So each module here exposes one plain function:

    def register(app, *, app_config, ..., get_conn, require_auth) -> None:
        @app.get("/api/...")
        def handler(...):
            ...

`create_app` calls each `register()` in the order the handlers used to appear,
passing exactly the closure locals that module's handlers read, by keyword.
The handler bodies moved **byte-identical** -- same indentation depth, same
decorators, same docstrings -- and the move was proved by tokenising each
definition on both sides (`tokenize`, ignoring only NL/NEWLINE/INDENT/DEDENT/
COMMENT positions). No `Depends` was rewired, no prefix added, no `app.state`
introduced, no `nonlocal` needed.

Two properties every module here keeps:

- **Mutable closure state is passed as the same object, never copied.**
  `live_quotes` closes over `create_app`'s `quotes` dict; `combo_api` over
  `combo_clients`. The lifespan closes what those dicts hold, so a router
  that built its own would leak a socket per app.
- **Monkeypatch seams stay where the tests pin them.** `KalshiRestClient`,
  `OrderPlacer`, `reserve_order` and `record_outcome` are resolved from
  `backend.api.routes`'s namespace at call time (`combo_api` and the writers
  live there), so a test that patches `backend.api.routes.KalshiRestClient`
  still reaches the client a moved handler uses.

What stays in `routes.py`, deliberately: `/api/health` and the quote stream,
`/api/board`, `/api/slate`, `/api/window`, `/api/market/{ticker}` and its
candles, `/api/orders`, and the manual order path. `test_board_sized_to_zero`
needs the board and slate decorators adjacent in one file, and the two
`OrderPlacer(` constructions are a counted guard on the live order path.
"""
