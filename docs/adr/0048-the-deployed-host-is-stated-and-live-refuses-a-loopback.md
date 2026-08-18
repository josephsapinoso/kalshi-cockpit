# ADR 0048 — The deployed host is stated in the deploy file, and live refuses to boot on a loopback

**Date:** 2026-08-18
**Status:** Accepted
**Supersedes:** nothing. **Extends:** the reasoning of
`tests/test_deployed_risk_caps_are_explicit.py` (2026-08-17) past money.

## The defect

Every Discord alert reaching Joe's phone carried a link to
`http://localhost:3000`. On a phone that is the phone, so the link was dead.

`COCKPIT_BASE_URL` was defaulted to `http://localhost:3000` in
`backend/config.py` and stated in **neither** `fly.live.toml` nor
`fly.demo.toml`, and set as no Fly secret on either app. Live therefore ran on
that default for the entire life of the alerter. `backend/notify/discord.py`
carried a *second, independent* copy of the same default with different
whitespace semantics.

Nothing was red. Nothing logged. `/api/health` reported
`notifications_configured: true`, which is a boolean about whether a string is
non-empty. The defect existed only at the boundary where the value left the
machine, and the machine cannot observe that boundary.

**The link was broken twice over**, and the second half is the more instructive
one. It was `/?focus=<ticker>`, and no file in the frontend reads a `focus`
param — `frontend/src/app/page.tsx` types its params as `{ rejected?: string }`.
Fixing the host alone yields a link that loads the Board and silently ignores
the ticker: a repair that looks complete and is not.

## The decision

Three parts, and each is load-bearing on its own.

**1. State the host in both deploy files.** `fly.live.toml` gets
`COCKPIT_BASE_URL = "https://kalshi-cockpit.fly.dev"`, `fly.demo.toml` gets
`"https://kalshi-cockpit-demo.fly.dev"`. This is `fly.live.toml`'s own rule
applied to a non-money setting: a value nobody chose is not a value.

**Be honest about the demo's reason.** `docker/entrypoint.sh:205-214` starts
`scripts/run_loop.py` only when `INSTANCE_MODE != "demo"`, so the demo never
constructs a notifier and never builds an embed. There, the variable is purely
`routes.py`'s CORS allow-list and parity. It is stated anyway because part 2
does not protect demo, so an omission there would be silent forever.

**2. A live instance refuses to boot on a loopback or absent host.** Same shape
as the existing `APP_AUTH_TOKEN` refusal, and effective container-wide:
`create_app` runs under uvicorn at boot and `entrypoint.sh` supervises it with
`wait -n`.

A *warning* was considered and rejected. The failure this guards is one nobody
sees from inside the system — a warning in a log Joe reads from a phone, if at
all, is how the defect survived in the first place.

**3. The link addresses `/market/<ticker>`.** That route is genuinely
ticker-addressable and **still renders after the opportunity expires**, which
the Board does not. An alert read twenty minutes late lands on the price history
rather than on a page that has forgotten the row. `?focus=` support was
explicitly **not** built: it is the plausible-looking fix for a page that
already exists elsewhere.

## What this does not establish

That either URL points at a machine that is up; that the webhook credential
works (`.github/workflows/secrets.yml` posts a synthetic embed for that); or
that any alert has ever been delivered. `notifications.delivered` is written by
`alerts.py:131-136` and read by nothing outside tests — a revoked webhook is
still indistinguishable from a quiet slate on `/api/health`. That is a separate
piece of work.

## The guard, and a pre-existing one it closes

`tests/test_deployed_urls_are_explicit.py`. It asserts the setting is present in
both `[env]` blocks as an absolute non-loopback `https://` URL, that live raises
`ConfigError` when it is absent or loopback, that demo does not, and — the
assertion that catches the class end-to-end — that a `DiscordNotifier` built
*from the environment* emits an embed whose link host and path match the
deployed config. All three guards were verified by disabling them and watching
the file go red.

Two further notes:

- **`tests/test_discord.py` could not have caught this.** Every test there
  constructs `DiscordConfig(cockpit_base_url="https://cockpit.example")`, so the
  `from_env` default path never executes. A test that supplies the value it is
  checking asserts nothing about production.
- **The refusal being copied had never been watched to fail.** Before this file,
  the whole repo contained no `AppConfig.load()` under `pytest.raises`, so the
  `APP_AUTH_TOKEN` live refusal — which has guarded the instance holding real
  credentials since it was written — was decoration. Closing it cost three
  lines and is included here.

## The generalisation, deliberately deferred

This guards one setting. The durable fix is the enumerate-and-classify
inversion `tests/test_has_callers.py` already argues for, applied to config:
AST-walk `backend/config.py` for every `_optional(NAME, default)` and require
each name to be either stated in both `[env]` blocks or listed in an explicit
`DEFAULT_IS_THE_DECISION` table with a reason. Unclassified fails.

`test_deployed_risk_caps_are_explicit.py` reached this reasoning on 2026-08-17
and applied it to the four dollar caps and nothing else. **The identical hole
was open on every other setting the whole time**, and this ADR is what walking
into it looks like. The walk needs its own ADR and is not taken here.
