# ADR 0171 — The Parlays lede states what an exit costs, and the login renews as it is used

Date: 2026-09-18
Status: Accepted
Issues: #64 (answered A), #65 (answered A). #64 completes the copy rule set in
#60; #65 follows ADR 0166's installable app.

Two unrelated decisions Joe answered in the same line. They share a commit
because each is small and neither blocks the other.

---

## #64 — the Parlays lede

### Context

The lede ended *"…once you own one hardly anyone is bidding to buy it back."*
That clause asserted a **frequency**, and every version of it has been
falsified:

| version | ratified | died | on what |
|---|---|---|---|
| "nobody is bidding to buy it back" | 2026-08-27 (#9) | 2026-09-10 | two `KXMVECROSSCATEGORY-SHARD1` books carrying resting YES bids |
| "hardly anyone is bidding to buy it back" | 2026-09-10 (re-ratified by Joe, given the counterexample and two alternatives) | 2026-09-17 | sell-side RFQs drew a bid on **3 of 3** held combinations — 16 of 44 quotes, every one at the full size asked — and two carried public-book bids **38,709** and **24,900** contracts deep |

It was the fourth false-availability sentence on the desk. #60 fixed the other
three on 2026-09-17 with Joe's answer (a).

### Decision

His rule, now settled twice: **say what an exit costs, not how often it
exists.**

> …a card pays only if every pick on it wins, and selling one back before the
> outcome usually costs more than holding it.

The frequency has been wrong three times. **Every measured best bid sitting
below what had been paid has been true every time** — 7.60 vs 10.20, 4.70 vs
5.70, 0.14 vs 0.38. So the replacement asserts no rate and the next reading
cannot falsify it. That property, not the wording, is what was bought.

`tests/test_tab_ledes.py` pins it verbatim, as it pinned the last two, so
changing it again is Joe's call rather than a side effect of shipping a
feature. The card's own sentence was already corrected under #60 and is
untouched here.

---

## #65 — the session slides

### Context

`issueSession` was called only at login and the cookie carried a hard thirty
days. The installed home-screen app has **its own cookie jar** (observed
2026-09-17, which is why the first launch after installing asked for the token
again), so it had its own clock running out around 2026-10-17 — regardless of
how often Joe opened it.

### Decision

Any authenticated request inside the window re-issues the cookie for another
thirty days. Daily use never expires; thirty days of silence does.

**Renewed once a day, not once a request**, and that is the whole reason
`SESSION_RENEW_AFTER_S` exists. A `Set-Cookie` on every response is an HMAC
per request and a header on every page, image and API call — on a box whose
page-cache behaviour was the subject of ADR 0167 the day before. Once a day
buys exactly the property Joe asked for at one extra signature per device.

The cost of the cheaper rule is that the real window is **29 to 30 days** of
silence rather than exactly 30. Stated on the constant rather than hidden.

Three things the shape is chosen for:

- **One set of cookie attributes.** `sessionCookie()` is shared by the login
  exchange and the renewal. Two literals would be two places for `httpOnly` to
  drift, and a renewal that quietly dropped it would downgrade a session's
  security *by keeping it alive*.
- **A failed renewal cannot cost him the request.** The cookie he already
  holds is still valid; the worst case of doing nothing is signing in a day
  later than he would have, and the worst case of raising is that a
  bookkeeping convenience takes down the page he asked for.
- **`renewalDue` is separate from `verifySession`.** That function answers one
  question — may this request through — and a renewal decision riding inside
  an auth check is how the two start being changed together by accident. It
  returns false on anything unreadable, so a cookie whose age cannot be
  determined is left exactly as it was.

The renewal sits on the verified branch only, after `PUBLIC_PATHS` has
returned, so `/api/health` and the manifest never touch it.

### What this does not establish

- **Nothing at runtime.** There is no Edge-runtime test runner here; the tests
  read source. They pin that the renewal is called, is conditional, shares its
  attributes with the login, and cannot take a request down.
- **Nothing about iOS.** That the installed app keeps a separate cookie jar —
  the reason this matters — was observed, not tested.
- **Nothing about the arithmetic.** The 29-to-30-day window is documented on
  the constant and is not executed by any test.

---

## A stale claim fixed on the way past

`middleware.ts` said `/parlay-rfq` was listed *"because no accept route
exists"* — three lines above the accept route's own entry. It has existed
since ADR 0165. Same decay pattern this session has now corrected six times on
the RFQ path.

## Mutations

Eight run, **eight red**.

| # | mutation | result |
|---|---|---|
| M1 | put the frequency claim back on the lede | RED |
| M2 | reword the lede without asking him | RED |
| M3 | stop renewing the session entirely | RED |
| M4 | renew on every single request | RED |
| M5 | renew on a path let through as public | RED |
| M6 | let the login keep its own copy of the cookie attributes | RED |
| M7 | let a failed renewal take the request down with it | RED |
| M8 | guess at an unreadable cookie instead of leaving it alone | RED |

---

## Post-deploy verification — 2026-09-18, live box on `ffa0bcb`

The #65 section above says the tests establish **nothing at runtime**, because
there is no Edge-runtime test runner here. That gap was closed against the
live instance instead, with GETs only and a cookie minted from `.env` the way
`scripts/time_live_routes.py` does it:

| check | result |
|---|---|
| unauthenticated `/picks` | `307` → `/login` |
| valid session `/picks` | `200` |
| **fresh** cookie re-issued? | **no** — the renewal is once a day, not once a request |
| **two-day-old** cookie | `200`, and re-issued |
| the replacement keeps `httpOnly` / `secure` / `SameSite=lax` / `Path=/` | all four |

The third and fourth rows together are the claim that mattered and the one
source-reading could not make: the renewal **fires on an aged cookie and only
on an aged cookie**. The fifth is the one a renewal could silently get wrong —
a session kept alive on weaker terms than it was issued on.

And the #64 lede was read back off the live page: the new sentence is there
and `"hardly anyone is bidding"` returns no match anywhere in the document.

This does not establish anything about iOS, or about the 29-to-30-day window
at its boundary; both remain as stated above.
