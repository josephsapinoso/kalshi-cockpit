# Rotating `ODDS_API_KEY` — phone sheet

**Five minutes. On your phone. No laptop.** This is the Odds API key, **not** the
Kalshi one. No money moves and no order path is touched.

---

## Why

A subagent read `.env` and the plaintext key landed in its transcript on disk.
This repo's own standing rule says that counts as compromised, so it gets
rotated. Nothing suggests it was *used* by anyone — this is hygiene, not an
incident response.

**Rotating is also what makes the leak moot.** The leaked value is in a
transcript file we cannot un-write. Once the key is replaced, that value is
dead text. That is the remediation; there is no second step chasing the file.

---

## The blocker in the handoff was wrong

The 2026-08-17 handoff said this needs `flyctl secrets set` from a laptop.

`.github/workflows/secrets.yml` genuinely **cannot** do it, and that exclusion is
deliberate and stays — verbatim from its own header (lines 15-18):

> *"**Notification secrets only.** This cannot touch KALSHI_PRIVATE_KEY,
> KALSHI_API_KEY, APP_AUTH_TOKEN or ODDS_API_KEY. Those live in Fly and nowhere
> else; routing them through GitHub would double the number of vaults that can
> leak them, to save a step nobody takes twice."*

It manages `DISCORD_WEBHOOK_URL`, `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID`, and
nothing else. **Do not widen it.**

**But `flyctl` is not the only way.** Fly's secrets can be set from the **web
dashboard**, which is a website and works on a handset. So there is no laptop
step and no ADR is needed — the exclusion is untouched and the rotation happens
in the vault the exclusion says it should happen in.

---

## Do not send the key to the agent

Not in a message, not in a file, not in a command. The agent never needs it and
will refuse it. Generating and installing the key are **your** actions; the agent
verifies afterwards from behaviour.

---

## The steps

**1. Make the new key.**
Sign in at **the-odds-api.com** → your account page → regenerate / issue a new
key. Keep the old one alive if the site lets you; you can revoke it after step 4
passes.

**2. Open the Fly dashboard.**
`https://fly.io/apps/kalshi-cockpit/secrets`

**3. Update `ODDS_API_KEY`.**
Set it to the new value and save. The current secrets on this app are:

```
KALSHI_API_KEY   ODDS_API_KEY   KALSHI_PRIVATE_KEY_B64
APP_AUTH_TOKEN   DISCORD_WEBHOOK_URL   ANTHROPIC_API_KEY
```

Only `ODDS_API_KEY` changes. **Do not touch the other five.**

**4. THE DASHBOARD ONLY STAGES IT. THIS IS THE STEP THAT BITES.**

Saving in the web UI does **not** restart anything. The secret sits as
**`Staged`** and the running loop keeps using the **old key** — indefinitely.
Confirmed live on 2026-08-17: after a dashboard save, `flyctl secrets list`
showed

```
* ODDS_API_KEY   c62a5156744f4b7a   Staged
```

— new digest, old key still in the process.

**Why this is the dangerous step and not a footnote:** the loop keeps sweeping
successfully on the old key, so *every* check below passes while nothing has
been rotated. A verification that cannot fail is worse than none, because it
retires the task. **Check for `Deployed`, never just for a working sweep.**

Apply it one of two ways:

- **In the dashboard, click "Deploy secrets".** That is the literal button
  name, confirmed by Joe on 2026-08-17. It applies the staged value *and*
  restarts the machine in one action. Saving the field does not do this;
  saving only stages.
- Or ask the agent, which runs `flyctl secrets deploy -a kalshi-cockpit`.

Then confirm the status word has changed:

```
flyctl secrets list -a kalshi-cockpit
```

`ODDS_API_KEY` must read **`Deployed`**, not `Staged`. The machine restarts on
apply, which is what restarts the odds loop (`docker/entrypoint.sh` →
`scripts/run_loop.py`). There is **no `.env` in the image** — the Fly secret is
the only source, so nothing else needs editing.

**5. Tell the agent you've done it.** Do not say what the value is.

---

## How it gets verified — and what does NOT count

**A 200 from `/api/health` proves nothing here.** The deployed API process never
reads this key at all: it takes `OddsConfig.load_without_credentials()`
(`backend/api/routes.py:263`), and the only live reader is
`backend/config.py:251`, reached only by the runner
(`scripts/run_loop.py:277` ← `docker/entrypoint.sh`), and only on the live
instance. Demo never reads it.

**The proof is a served sweep row**, written after the restart:

```
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py credits-tail"
```

Pass = a new `api_credits` row with a `called_ms` **after** the restart. A 401
from the provider would instead show up as a `refused`/error row in
`odds_sweep_log` and **no** new credit row.

**Timing matters.** Sweep windows open 75 minutes before a cluster's first pitch,
not on a clock — so a quiet hour after the rotation is not a failure. Check
`odds_sweep_log` for the next slot before worrying:

```
flyctl ssh console -a kalshi-cockpit -C "python /app/scripts/inspect_live_db.py sweep-log -n 5"
```

If you'd rather not wait, the phone UI's per-fixture **Refresh odds** button
forces a real call — but it spends credits (22 for a prop tap), so the free
answer is to wait for the next window.

---

## What the 2026-08-17 rotation actually cost, so the next one is cheaper

Three things went wrong and none of them were the paste.

**1. The dashboard staged instead of applying.** Covered in step 4 above. The
running loop kept the old key and kept succeeding, so every "is it working"
check passed while nothing had rotated.

**2. A rejected call still writes an `api_credits` row, so a row is not proof.**
The 401 at 2026-08-17T21:06:48Z produced a credit row at 21:06:40 with
`cost = 2` — because `client.py` records before raising, deliberately, since
some error classes do consume credits. **The tell is that
`remaining_reported` and `used_reported` are `NULL`**: the provider sends those
headers on success, and "unreadable resolves to `None`, never `0`" is what makes
the failure visible instead of silently zero. **Verify on a non-NULL
`remaining_reported`, not on the existence of a row.**

A rejected call also **resets the odds-freshness clock** — immediately after the
401 the scheduler reported *"odds are 0.4min old"* and deferred its retry a full
ten minutes. So a bad key makes the system believe it has fresh odds. That is a
defect in its own right and is listed in `tasks/NEXT.md`, not fixed here.

**3. A restart mid-window costs up to 15 minutes.** `backend/scheduler.py:182`
returns `fast_interval_s if self.window_open else self.slow_interval_s`, and a
fresh process starts with `window_open` false — so after the restart the loop
slept **900s** instead of 15s, inside an open window. Ten minutes of apparent
silence that looked exactly like a hung process. It is not hung; check
`sweep-log`'s newest row against the restart time before concluding anything.

**The digest is a fingerprint and it is the cheapest diagnostic here.**
`flyctl secrets list` prints a digest per secret without ever revealing the
value. If the digest is unchanged after a re-paste, Fly holds byte-for-byte what
was pasted and the problem is not local. That is how the 2026-08-17 incident was
narrowed to the provider without anyone handling the key.

## One thing that breaks and is not on the machine

`scripts/probe_prop_dispersion.py` and the other operator CLI scripts read
`ODDS_API_KEY` from a **local** `.env` on whatever laptop runs them. Those keep
using the old key until that file is updated. They are not on the Fly box, they
write no `api_credits` rows, and nothing scheduled calls them — so this does not
affect the live loop. Update the local `.env` next time you're at a laptop.

---

## Not done, and deliberately

- **`secrets.yml` is not widened.** The exclusion is reasoned and holds.
- **No ADR.** Nothing is decided here that wasn't already decided; the dashboard
  route uses the vault the existing decision names.
- **The old value is not hunted through transcripts.** Rotation kills it. `.env`
  is gitignored and untracked, verified.
