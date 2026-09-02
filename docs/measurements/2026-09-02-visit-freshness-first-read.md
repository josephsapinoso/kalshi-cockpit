# Visit freshness, first read — the cold open meets the hourly floor, and the median-fixture figure is refused

**Instrument:** `scripts/inspect_live_db.py visit-freshness`, built 2026-09-02
(`7b64129`), run on live against build `f2cd34b` at ~2026-09-02T23:00Z.
Raw output preserved out of the repo at
`data/live-snapshots/visit-freshness-2026-09-02T23Z.txt` (gitignored;
operator data). Audited by `measurement-skeptic` before entry; two blockers
applied (below).

**The question.** Joe answered the batched interview's lead question — why
he stopped opening the desk — with *"the prices are stale when I look."*
The partner's hypothesis: attention buys fire only while a page is open, the
floor is hourly and only for a sport with a fixture inside 12 h, an unpaced
first buy waits for the full pass, so a cold open is *allowed by design* to
show books up to an hour old, and a once-a-day user meets that case every
time. This read joins `desk_attention` heartbeats (visits) to the consensus
age the screen would have shown at each visit's first stamp.

## 1. The reading

45 visits, 771 heartbeats, since 2026-08-26T22:39Z. Visit gap 300,000 ms
(`DEFAULT_ATTENTION_TTL_MS`); staleness limit 900,000 ms (`MAX_ODDS_AGE_S`
as deployed, `fly.live.toml`).

At the first stamp of each visit the **freshest** upcoming fixture had a
median consensus age of **837 s (14.0 min)** — just inside the 900 s limit —
with q75 40.8 min and q90 60.2 min. **On 21 of 45 opens (47%) not one
upcoming fixture was inside the limit**, which is the state `/board`'s
banner renders as `fixtures fresh 0/N`. Median time from the first
heartbeat to the first `trigger = 'attention'` credit was 3.3 s, with a
tail: 7 visits over 60 s and one at 64.7 min. 8 of 45 visits caused no
attention buy; 4 of those had a sport swept inside the ten-minute cadence
(nothing was due) and 4 did not — v3 (39.4 min), v6 (11.2), v8 (177.9,
the 2026-08-28T04:38Z night already in CLAUDE.md), v31 (20.8).

    visits                          45
    median freshest-fixture age     837 s   (14.0 min)   q75 40.8 min   q90 60.2 min
    opens with nothing fresh        21 / 45  (0.467)
    opens with a fresh fixture      24 / 45  — median freshest 14.0 min
    median attention latency        3.3 s   (tail: 7 over 60 s, max 64.7 min)
    visits with no attention buy    8 / 45  (4 nothing due, 4 unexplained)

## 2. What it supports

**The hypothesis is supported in direction, on the freshest-fixture
reading.** The freshest fixture's age at a cold open is bounded by the
hourly floor's own cadence in 41 of 45 visits (24 inside the limit, 17 more
between 15 and 65 min). The four exceptions — v8 (177.9 min), v32 (135.5),
v34 (68.8), v33 (65.8) — are all overnight, when the floor's 12 h horizon
also correctly declined. That is the shape the design predicts: a
once-a-day cold open meets the floor's hour, and worse when no fixture is
inside twelve hours.

**The attention slice is not the cause.** Sourced to the `credits-day`
reading by trigger — 5–10 attention rows a day against a 300-credit slice,
~7% used — and **not** to this table's `refused_sweeps` column, which cannot
see a slice refusal (`REFUSED` is written only by the daily cap,
`backend/odds/client.py:349,463`; a slice-spent sport is demoted to the
floor, and its refusal reaches the log only as `skipped`). The first draft
of this document cited the column; the skeptic's B1 removed it.

## 3. What is refused, and why

**`first_age_ms` — "the median fixture was 4.8 h old" — is not reported and
must not be.** Three demonstrations from the table itself:

1. `start_ms − first_age_ms` is one constant stamp (2026-08-30T01:56Z) on 17
   of 45 visits spanning 2.7 days; across them the column climbs from 3.3 h
   to 68.8 h with wall clock alone.
2. `last_age_ms − first_age_ms` equals the visit duration on 30 of 45
   visits, including v24: open 9,492 s with ten attention buys, median age
   up by 9,493 s. A number that does not move when the feed buys is not
   measuring the feed.
3. `_fixture_ages_at` applies no commence horizon, so the population is
   every not-yet-commenced fixture in the record, and an age is a book
   stamp: one bookmaker whose `last_update` has stopped advancing pins the
   median. The instrument records neither the contributing book nor a
   commence time, so the largest contributor's share cannot be read off
   the table — the pooled-number rule is unmet for that column.

The freshest-fixture figure and `first_fresh / first_fixtures` are the
columns that map to rendered numbers (`/board`'s banner; the Slate's
per-row age and its "any row past the limit" refresh promotion). Of the
five candidate statistics the instrument prints, the first draft led with
the one that read worst; this document leads with the one the screen
shows.

## 4. What this does not establish

- **n = 1 operator, and effective n is well below 45.** 17 visits share one
  frozen stamp, 15 are single-heartbeat (a bounce stamps like a look —
  `Nav.tsx` beats on mount), and visits 44–45 are this session's own
  browser during the deploy of the build under measurement (v45 is
  right-censored by the query instant). Excluding the single-heartbeat
  visits: nothing-fresh 13/30, median freshest 13.0 min. Excluding 44–45:
  21/43, 14.6 min. Immaterial either way, and stronger without them, so
  they are kept. No interval is attached; these are non-independent visits.
- **Direction is untested, and the mechanism the docstring first named is
  not the one the data show.** "Stale, so he stopped" and "stopped, so it
  is stale" are both consistent with the rows. But the longest inter-visit
  gaps did *not* produce the stalest opens (gap > 12 h: median freshest
  4.2 min, n = 3), because the floor runs whether or not anyone visits. The
  overnight exceptions are the 12 h horizon, not visit length.
- **No column here is what the Slate — the landing screen — shows.** The
  Slate prints a per-row `odds_age_now_ms` and promotes the refresh panel
  when any priced row is past the limit; that is a max over a smaller
  population. The cross-check against the Slate's own row ages at the visit
  instant is the measurement that would close the gap, and it is not taken.
- **The latency is attributed by window, not causally.** A buy already in
  flight when the page opened is credited to the visit; nine sub-second
  latencies are not the 5 s wake-poll mechanism.
- **Why the four unexplained no-buy visits bought nothing** is outside this
  instrument: `sports_open` is a freshness fact, and the floor's 12 h test
  needs a commence time the table does not carry.
- **Nothing about why a stamp is old**, inherited from `window-freshness`.

## 5. What it changes

Ticket #20 (the empty night) now has its spec: the state Joe meets most is
*a cold open with the freshest fixture just past the limit and the feed
about to buy within seconds*, and on half of opens *nothing fresh at all*.
The screen he lands on must say which of those it is, and that a buy is
seconds away, rather than rendering 0/N as a calm night. Whether the floor's
hour is the right cadence is a cost question the partner owns; this read
does not answer it.
