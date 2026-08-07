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
      `KALSHI_PRIVATE_KEY_PATH` contents, `APP_AUTH_TOKEN`, `ODDS_API_KEY`,
      `DISCORD_WEBHOOK_URL`
- [ ] Actions → Deploy → instance `live` → type `kalshi-cockpit` into the
      confirm box → Run

The typed confirmation is deliberate. A dropdown mis-tap on a phone is a
plausible way to deploy the money instance by accident; typing its name is not.

---

## 4. Place the fee-calibration trades — in the Kalshi app

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

- **The first `git push`.** Creating the GitHub repo is a browser job, but
  pushing this working tree needs a machine once. After that, everything above
  works from the phone.
- **Editing code.** Obviously. That is what I am for — send me the change you
  want in chat.

---

## What needs nothing from you at all

I can keep working through `tasks/audit-2026-08-07.md` (~40 open findings,
triaged with file:line) and `tasks/NEXT.md` section 3 (Research screen,
Playbook screen, Ticket bottom sheet, README) without any input. Just say keep
going.
