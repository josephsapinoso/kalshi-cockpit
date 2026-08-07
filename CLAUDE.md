# CLAUDE.md

Spine for this repo. Deliberately short — detail lives in `.claude/skills/`,
loaded only when working in that area. Read `tasks/todo.md` and
`tasks/lessons.md` at session start.

## What this is

A cockpit for betting sports on Kalshi. It compares Kalshi's prices against
devigged sportsbook consensus and an in-house power-ratings model, surfaces
opportunities where both agree Kalshi is mispriced by more than the fee, and
records everything so the edge can be *measured* rather than assumed.

It runs hosted on Fly.io (not a laptop), is used from a phone, and is intended
to become a public portfolio repo.

**The premise, stated honestly:** Kalshi's advantage is cost, not information.
Prices are accurate to ~2c and sports is the most bot-contested corner of the
venue. The venue lowers the break-even bar from 52.38% to 51.75% (taker) or
50.44% (maker). It does not clear that bar. This tool exists to find out
whether an edge is there — not to assume one.

## The three rules everything else follows from

1. **A large apparent edge is a bug until proven otherwise.** Big numbers get
   suppressed and investigated, never surfaced. The devig-method spread alone
   (1–2 percentage points) exceeds the fee advantage being hunted.
2. **Use the worst of four devig methods** for any money decision, so no edge
   survives that is an artifact of method choice.
3. **Validate against Kalshi's own closing line.** The question is whether you
   beat *Kalshi*; only Kalshi's close answers it.

## Measurement rules

These are not style preferences. Every one of them exists because an earlier
measurement was wrong in a way that flattered the result.

- **Read `n` before the effect size.** Require ≥5 expected outcomes on each
  side before a normal approximation is allowed to speak. The biggest gaps come
  from the smallest cells.
- **A pooled number is not a finding until the parts agree.** Always print the
  per-group view and the largest contributor's share beside any aggregate.
- **Bucket by the price you would actually pay** — the derived ask, never the
  mid. One bucket in the previous project showed a +25.4 point edge *and lost
  money* because it was bucketed on the mid but transacted at the ask.
- **The convenient column is usually contaminated.** `last_price` on a settled
  market has already converged on the outcome. State when a price was observed
  relative to when the outcome became known, and re-run at a second horizon.
- **Count your tests.** 1,190 category cells produce dozens of "significant"
  results by chance.
- **Every harness states what it does not establish**, in its module docstring.

## Conventions

- **Money is integer tenths of a cent** (`core/prices.py`), never float
  dollars, everywhere in the risk path. ~25% of Kalshi markets tick in
  deci-cents; whole cents misprice them by up to half a cent against a 4c edge.
- **Unreadable resolves to `None`, never `0`.** Callers refuse rather than
  substitute. See `tasks/lessons.md`.
- **Clamp what you trust; refuse what you're validating.**
- **Config via `.env`**, never hardcoded. `.env.example` is the contract.
- **Async** for all I/O. One shared `httpx.AsyncClient`, not one per call.
- **Wire-format tests load captured payloads** from `tests/fixtures/`, never
  hand-constructed ones.

## Testing

```
.venv\Scripts\python.exe -m pytest -q
```

`asyncio_mode = auto`, so async tests need no marker. Shared fixtures are in
`conftest.py` at the repo root (not `tests/`) because `backend` is imported as
a package from the root. Group with `class Test<Behaviour>`, and name tests
after the claim they make (`test_maker_is_one_quarter_of_taker`).

**Every guard is verified by disabling it and watching the test fail.** If it
stays green, it's decoration. Never weaken an assertion to make a test pass.

## Security

This repo is intended to go public and the live instance holds real money.

- The Kalshi private key is a Fly secret. Never read, echo, log, or commit it.
  If it ever appears in a transcript, it is compromised — rotate it.
- `.env`, `*.pem`, `*.key` are gitignored from the first commit.
- Every mutating route requires auth. The order endpoint re-validates staleness
  and risk caps **server-side** — never trust that the UI disabled a button.
- Demo and live run as separate deploys from one image. A public URL must not
  be one config bug away from the order path.

## Do not read these

They will burn a context window and tell you nothing you need:

- `../kalshi_orderbook_monitor/orderbook_data/**` — ~400MB of JSONL recordings.
- `../kalshi_orderbook_monitor/static/app.js` — 100KB vanilla JS, superseded.
- `../kalshi_orderbook_monitor/auto_trader.py`, `trading_server.py` — 86KB and
  90KB. Skim structure only; the strategies in them were measured and failed.
- `.venv/`, `node_modules/`, `warehouse/target/`.

To reference the previous project, read `.claude/skills/kalshi-api/SKILL.md`
first — it carries what was learned without the bulk.

## Do not rebuild these

Measured and refuted in the previous project. Re-litigating them costs days.

| Idea | Result |
|---|---|
| Stale-quote detection / picking off | Edge lives at ~400ms; a 60–180s detector is far too slow |
| "The NO side is systematically cheap" | Refuted on 66,686 settled markets — every price bucket negative |
| Kalshi↔Polymarket arbitrage | Text matching gives 0.56% match rate, and the matches are *wrong* |

## Do not repeat this inference

`/markets` is ~99.8% `KXMVE` with no volume. That is a fact about **discovery
hygiene** — never paginate `/markets` — and it does **not** mean Kalshi has no
combo product. `KXMVE` is Multi-Variate Event: 1,389 collections and 13,806
legs, same-game and cross-game. This project asserted the opposite for eleven
build steps. See `backend/kalshi/combos.py` and `tasks/lessons.md`.

## Workflow

1. **Plan first** for anything non-trivial (3+ steps or an architectural
   choice). If something goes sideways, stop and re-plan rather than pushing.
2. **Vertical slices, not horizontal layers.** Each step ends demoable and
   verifiable, so a session can end anywhere without leaving a half-built
   layer.
3. **Offload research to subagents** to keep the main context clean. One task
   per subagent.
4. **Verify before done.** Never mark a task complete without proving it works.
   Would a staff engineer approve this?
5. **Capture lessons.** After any correction, write the *pattern* to
   `tasks/lessons.md` — not the incident.
6. **Record decisions** in `docs/adr/` so no future session re-derives them.
