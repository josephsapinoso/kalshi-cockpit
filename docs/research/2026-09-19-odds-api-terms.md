# The Odds API — Terms and Conditions, as fetched

**Fact-finding only. No verdict, no legal conclusion.** Written for ticket
#98 (part of #84), feeding #99. This document quotes the terms verbatim on
four points and places two lines of ADR 0035 beside them so the reader can
see the contradiction #98 was opened to resolve. It does not decide it.

## Source

- **URL fetched:** `https://the-odds-api.com/terms-and-conditions.html`
  (the footer link on `the-odds-api.com` is `/terms-and-conditions.html`;
  `https://www.the-odds-api.com/terms-and-conditions.html` 301-redirects to
  this same canonical URL — both checked).
- **Page's own "Last updated" date:** 31 August 2026.
- **Date fetched:** 2026-09-19 (`curl`, HTTP 200, `Content-Length: 19347`).
- **Method:** `WebFetch` on this page returned a summary/paraphrase on two
  attempts, including one explicit request for verbatim text — the tool's
  own summarizing model would not stop condensing. Per CLAUDE.md's
  wire-format rule (verbatim over reconstructed), the raw HTML was instead
  fetched directly (`curl`, from this repo's own network, no API key used
  or needed — this page is public marketing/legal content, not an API
  endpoint) and converted to plain text mechanically (tag-stripping only,
  no rewriting). The full extracted text is reproduced in section order
  below; nothing between the quoted passages was altered.

## (a) Redistribution / sharing of API-derived data

Under the heading **"Restrictions"**:

> Do not resell, repackage, or redistribute our data as a standalone data
> product. This includes, but is not limited to, offering our data through
> your own API, data feed, downloadable files, or any other format intended
> to serve as a source of raw data for others.

> We support and encourage the use of our data in websites, mobile apps,
> dashboards, analytical tools, and other user-facing applications,
> including commercial use, provided our data is not the primary product
> being sold or redistributed.

> We mainly prohibit reselling the data as a raw data feed, i.e. a
> competing product. In other words, don't resell our data as your own API
> or data source.

> If we reasonably suspect a violation of these terms, including the resale
> or redistribution of our data as a data service, we reserve the right to
> revoke your API key and block future access.

## (b) Retention / storage / archival — any limit on how long fetched data may be retained

Also under **"Restrictions"**, in the list of "Permitted uses" (the terms
give no separate "Retention" or "Storage" heading — this is the only
passage on the page that speaks to it):

> Permitted uses include, but are not limited to:
> Storing our data and retaining it indefinitely
> Displaying our data in a UI, website, or mobile app, including for
> commercial use
> Using our data in research papers and analytical dashboards
> Calculating and displaying values you derive from our data
> Using our data to train statistical and machine learning models

No clause anywhere on the page states or implies a maximum retention
period, an expiry, or a duty to delete. "Retaining it indefinitely" is
listed as a **permitted** use, not merely a tolerated one.

## (c) Any "individual, non-commercial, non-bulk"-style restriction

**None found.** The page contains no clause resembling MLBAM's
"individual, non-commercial, non-bulk use" notice (quoted for comparison
only, per the ticket — that restriction is MLBAM's, not asserted here to
apply to The Odds API). The closest passages are the same ones quoted under
(a):

> We support and encourage the use of our data in websites, mobile apps,
> dashboards, analytical tools, and other user-facing applications,
> **including commercial use**, provided our data is not the primary
> product being sold or redistributed.

> Displaying our data in a UI, website, or mobile app, **including for
> commercial use**

Both explicitly permit commercial use, which is the opposite shape of a
non-commercial restriction. No "bulk" or "individual-use" language appears
on the page at all.

## (d) Any distinction between live/real-time data and historical/archived data

**None found on this page.** No section title, clause, or sentence
distinguishes "live" from "historical" or "archived" data with respect to
permitted use, retention, or redistribution. The "Permitted uses" list
(quoted in (b)) covers storage/retention without qualifying it by data age
or by whether the odds are still live. (The Odds API separately advertises
a paid "historical odds" API product elsewhere on the site, per general
awareness of the vendor's product lineup — but this Terms and Conditions
page itself draws no legal distinction between the two, and that separate
product page was not fetched for this ticket, which is scoped to the terms
document.)

## The rest of the page

The whole page was fetched and read (raw HTML via `curl`, tags stripped
mechanically, nothing rewritten); only the clauses bearing on the four
questions above are reproduced here. This repository is public, and a
vendor's terms page is theirs to publish — the URL and the page's own
"Last updated" date above are the citation, and the four sections quote
verbatim what was read.

## Beside ADR 0035's contradiction

`docs/adr/0035-mlb-stat-data-is-split-across-two-sources-on-licence-grounds.md`
makes two claims about The Odds API's terms that the ticket flagged as
contradictory. Both line ranges were re-verified by direct `Read` at the
exact offsets in this session and match the ticket's citation exactly.

**Lines 122–123** (section "3. No MLBAM payload is ever committed to this
repository"):

> it was written for Kalshi and The Odds API, whose data we are not
> prohibited from
> redistributing.

**Lines 186–187** (section "What this ADR does not establish"):

> - **It says nothing about Kalshi's or The Odds API's terms**, which are
>   separate
>   agreements and are unexamined here.

Read against the terms quoted in (a) above: the terms do contain a
redistribution clause, and it is narrower than an unqualified "not
prohibited from redistributing" — it permits use of the data in
user-facing products (explicitly including commercial ones) while
prohibiting resale/repackaging of the data itself "as a standalone data
product" or "raw data feed... for others." Whether that clause makes ADR
0035:122–123's claim true, false, or true-with-caveats for this repo's
specific use is not decided here — that is #99's and Joe's, per the ticket.

## What this does not establish

- **No legal conclusion.** This document is a verbatim transcription of one
  public terms page, not legal advice, and (per ADR 0035's own framing,
  which this document adopts) "I am not a lawyer and this is not legal
  advice."
- **No recommendation.** It does not say whether this repo's current
  architecture — raw storage in `odds_snapshots` with no retention cap
  (`schema.sql:210-213`'s stated reason for storing raw, per the ticket) —
  complies with these terms. That judgement belongs to #99/#10 and,
  ultimately, to whoever signs the resulting ADR.
- **No resolution of the ADR 0035 contradiction.** This document supplies
  the evidence; it does not pick which of the two existing ADR 0035
  sentences to keep, amend, or discard.
- **Does not cover Kalshi's terms.** Ticket #98 and this document are
  scoped to The Odds API only. ADR 0035:186–187 makes a claim about
  Kalshi's terms too, which remains unexamined by this document.
- **Does not cover The Odds API's separate historical-odds product page,
  privacy policy, or API documentation** — only the Terms and Conditions
  page at the URL above was fetched and quoted. If a future decision turns
  on the historical-odds product specifically, that page has not been read
  here and should be fetched separately.
- **Single fetch, single point in time.** The page states "We may update
  these Terms and Conditions from time to time" with only email notice for
  material changes and no version history shown on the page itself. This
  document reflects the text as it read on 2026-09-19; a stale re-read risk
  applies the same way it does to any other terms-of-service snapshot in
  this repo.
