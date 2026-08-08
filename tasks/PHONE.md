# What you can do from your phone

Everything currently blocked on you, in the order it unblocks the most. No
laptop needed for any of it.

---

## 1. Get an Odds API key — 2 minutes

The odds path has never run live, so every fair price so far comes from seeded
data. Nothing downstream is real until this exists.

- [ ] Browser → `the-odds-api.com` → sign up (free tier, 500 credits/month)
- [ ] Copy the key
- [ ] Send it to me, or put it in `.env` as `ODDS_API_KEY=...` when you're next
      at a machine

Free tier is ~16 calls/day, which is not "live" — the staleness gate will
refuse most bets on it, which is correct for an unvalidated strategy. The $59
tier is where live becomes honest, but there is no reason to pay for that until
the tool has shown it can find anything.

---

## 2. Answer two yes/no questions — 30 seconds

Both are one-word replies to me.

- [ ] **Combo price lookup?** Getting a real Kalshi combo quote needs one
      `POST .../lookup`, which *creates a market on the exchange* if that
      combination is new. No money moves — it is exactly what the app does when
      you tap a leg. I have it refusing by default because it is an
      outward-facing write on your account. Say the word and I'll run one, then
      invert the quote into an implied same-game correlation.
- [ ] **Fee-calibration trades?** See item 4 — but the decision is yours to
      make from anywhere.

---

## 3. Deploy — now phone-doable

`flyctl` has no mobile client, which made this the one blocker that genuinely
needed a laptop. It doesn't any more: `.github/workflows/deploy.yml` runs it
for you, and GitHub's mobile app has a **Run workflow** button.

One-time setup, all in a phone browser:

- [ ] Push this repo to GitHub (needs a laptop **once**, or create the repo on
      github.com and I can push it next session)
- [ ] `fly.io/dashboard` → Tokens → create a deploy token
- [ ] GitHub → repo → Settings → Secrets → Actions → new secret
      `FLY_API_TOKEN`

Then, from the GitHub mobile app:

- [ ] Actions → **Deploy** → Run workflow → instance `demo` → Run

The workflow creates the app if it doesn't exist, deploys, waits for
`/api/health`, checks the app reports the mode you asked for, and — for the
demo — asserts that `POST /api/orders` answers **403** even with a forged
bearer token. If the public instance ever had a reachable order path, the
deploy fails rather than succeeding quietly.

For the live instance later:

- [ ] Fly dashboard → your app → Secrets → set `KALSHI_API_KEY`,
      `KALSHI_PRIVATE_KEY_PATH` contents, `APP_AUTH_TOKEN`, `ODDS_API_KEY`
      **(already done)**. `DISCORD_WEBHOOK_URL` has its own workflow — see
      item 4; it deliberately cannot touch the four above, so that the vault
      holding your Kalshi key stays the only one that holds it.
- [ ] Actions → Deploy → instance `live` → type `kalshi-cockpit` into the
      confirm box → Run

The typed confirmation is deliberate. A dropdown mis-tap on a phone is a
plausible way to deploy the money instance by accident; typing its name is not.

---

## 4. Turn on Discord alerts — 5 minutes, all on the phone

Without this the tool cannot reach you, and the thing it needs to reach you
about lasts about thirty seconds. Everything below is phone-only.

**a. Make a webhook, in the Discord app itself** — no developer portal, no bot,
no Developer Mode toggle:

- [ ] Discord app → your server → the channel you want alerts in
- [ ] Long-press the channel → **Edit Channel** → **Integrations** → **Webhooks**
- [ ] **New Webhook** → name it something like `cockpit` → **Copy Webhook URL**

That URL *is* the credential — anyone holding it can post to that channel.
Nothing else, though: it cannot read messages and cannot act anywhere else in
the server, which is why it is used here instead of a bot token.

**b. Put it in GitHub** — the mobile *app* has no Settings screen, so use a
browser:

- [ ] Browser → `github.com/josephsapinoso/kalshi-cockpit/settings/secrets/actions`
- [ ] **New repository secret** → name `DISCORD_WEBHOOK_URL` → paste → Add

**c. Push it to Fly.** The GitHub mobile *app*'s Actions tab is unreliable for
workflows that take inputs — use the browser, or just tell me and I'll run it:

- [ ] Browser →
      `github.com/josephsapinoso/kalshi-cockpit/actions/workflows/secrets.yml`
- [ ] **Run workflow** → instance `live` → type `kalshi-cockpit` in the confirm
      box → **Run workflow**

The workflow refuses if no secret is set, sends the value over stdin rather
than as an argument, and echoes only the *names*. Then it checks two separate
things, because they fail differently:

- it polls `/api/health` until `notifications_configured: true`, so a green run
  means the *process* is seeing the secret, not merely that Fly accepted it;
- it **posts a real message to the channel**, because the first check only says
  the string is non-empty. A typo, a truncated copy, a revoked webhook and a
  deleted channel all look identical to it — and so does a working alerter on a
  quiet night. If Discord rejects the credential the run goes red and names
  which of those it was.

So: **the run going green and a message appearing in your channel are the same
event.** If you see "Alerts are wired up" in Discord, it is done.

**d. Check it yourself, any time:**

- [ ] `kalshi-cockpit.fly.dev/api/health` → look for
      `"notifications_configured":true`

The first alert you should see is **"Odds are fresh — the window is open"**,
after the budget day rolls at 10:00Z. A quiet channel before then is correct.

**Why not a bot token?** It also works — set `DISCORD_BOT_TOKEN` and
`DISCORD_CHANNEL_ID` as repo secrets instead and the same workflow handles them.
It just needs the developer portal, an application, an OAuth invite and
Developer Mode turned on to reveal a channel id, and it produces a *broader*
credential: a bot token works everywhere the bot was added, a webhook only in
the one channel.

---

## 5. Place the fee-calibration trades — in the Kalshi app

This is the one that closes a year-old open question, and it is *more*
convenient on a phone than on a laptop: place them in the Kalshi app directly.

The fee model is still a hedge between two sources that disagree with each
other — one says `0.07 × C × P × (1−P)` rounded up per order, the other a ~0.06
sports multiplier rounded to the nearest cent per contract. At 50c on 100
contracts they differ by 14%, and the ordering reverses at 20c. Until a real
fill says which is right, `core/fees.py` charges the more expensive one, which
suppresses essentially every longshot.

- [ ] Four minimum-size orders at spread-out prices — roughly **10c, 30c, 50c,
      80c** — on any liquid market
- [ ] Tell me when they fill

Total cost is a few dollars. Every fill reports the fee Kalshi actually
charged; `mart_fee_reconciliation` compares it against what we predicted, and
the answer retires the hedge. It also clears one of the five gate conditions —
"no fills yet" currently counts as **not verified**, deliberately, because
calling an absence a pass is the convenient reading.

---

## What is NOT phone-doable

Honestly, so you don't try:

- **The first `git push`.** Done — the repo is on GitHub and everything
  above works from the phone.
- **Setting the Kalshi private key, `APP_AUTH_TOKEN` or `ODDS_API_KEY`.**
  Deliberately not automated. Those live in Fly and nowhere else; a workflow
  that could write them would mean GitHub holds them too, doubling the number
  of places that can leak them to save a step taken once.
- **Editing code.** Obviously. That is what I am for — send me the change you
  want in chat.

---

## What needs nothing from you at all

I can keep working through `tasks/audit-2026-08-07.md` (~40 open findings,
triaged with file:line) and `tasks/NEXT.md` section 3 (Research screen,
Playbook screen, Ticket bottom sheet, README) without any input. Just say keep
going.
