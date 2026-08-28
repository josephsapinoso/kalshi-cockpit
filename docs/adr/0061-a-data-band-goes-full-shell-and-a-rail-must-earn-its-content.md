# 0061 — A data band goes full shell width, and a rail must earn its content

**Date:** 2026-08-21
**Status:** Accepted.
**Extends** [ADR 0047](0047-the-desktop-tier-is-a-reading-surface.md) (the
desktop tier is a reading tier) to pages it never covered; changes none of
its recorded decisions.
**Owns:** the market screen's desktop layout
(`frontend/src/app/market/[ticker]/page.tsx`, `ScoutDesk.tsx` at `xl:`), and
the pattern below for any future screen joining the shell.

## 1. What happened

Joe, looking at the market page on a ~2000px monitor: *"can we take up the
real estate of the site on desktop? it's so small. make it nicer."* A partner
convening (graphic-designer briefed first, then ui-designer and ux-designer;
report in the 2026-08-21 session record) found the root cause and a
disagreement worth recording.

**Root cause:** the page hardcoded `max-w-3xl` (768px) while the Nav and
Footer around it use `SHELL_WIDTH` (1024px → 84rem at xl). A page narrower
than its own chrome reads as a phone screen floating in a frame. It joined
the shell; `tests/test_desktop_tier.py` now bans `max-w-3xl` alongside
`max-w-5xl` in shell surfaces.

## 2. The decision: no rail on this page, and the general rule

All three design positions initially assumed a 24rem facts rail at xl. The
convening killed it on arithmetic: with the rail, the main column is 856px
and the six instrument tiles land at ~122px — barely above the 108px Joe
called "so small." The rail would have consumed exactly the pixels that
answer the complaint. And the only two candidates for its content were each
vetoed on their own grounds (the quote is a *precondition* that belongs
above the content it can invalidate; a ticker string is not context).

**The rule this establishes:** a *data band* (a board of tiles, a table, a
chart) goes full shell width, with its prose capped at ~65ch inside it. A
rail is only built where genuine standing context exists to fill it — never
to make a layout look like the Board's. Two shapes both citing ADR 0047 is
fine; a rail holding a button is not a shape.

Consequences applied the same day: tiles at ~193px in one six-across row
(pinned — one row of lamps is one glance), `xl:` type/padding steps,
prose caps guarded by `PROSE_FILES`, the chart widening to ~900px when
opened ("widen the data, never the prose").

## 3. A filled control is for money, at every width

> **Amended 2026-08-28 by ADR 0081.** This section was titled *"Red is for
> money, at every width"* and its body called `--accent` "the commit red".
> Both are now false as descriptions: `--accent` is indigo, and red
> (`--negative`) means loss and nothing else. **The rule is unchanged and was
> never about the hue** — it is about *weight*: a filled control claims the
> page. It survives in indigo exactly as written. The class name moved from
> `bg-accent` to `bg-accent-fill`; the guard
> `TestTheMarketScreenStaysOnItsInstruments` was repointed and its rule was
> not loosened.
>
> This paragraph exists because the next session to read §3 will find a rule
> stated in a colour that no longer does that job, and the obvious reading —
> "this was reverted" — is wrong. §3 is one of the three roles ADR 0081
> separates, and it is the one that was placed there deliberately.

The desk's re-send button wore `bg-accent` (the commit red). At desktop
scale it became one of the brightest things on the page — under a completed
board, an invitation to re-roll a metered request until it says something
different. Re-sends are bordered secondaries now; only the *first* send (and
real money controls elsewhere) wear the filled accent. Pinned by
`TestTheMarketScreenStaysOnItsInstruments`. Same reasoning ADR 0047 applied
to TicketSheet; recorded here because it now generalises: **a filled accent
control on a wide screen is a claim that pressing it is the point of the
page.**

## 4. Rejected, with reasons (so they are not re-proposed)

- **Container queries for the board's scaling.** `@[40rem]` fires inside the
  768px and 1024px shells too, breaking ADR 0047's below-xl byte-identity.
  `xl:` variants only.
- **Full-bleed / anything in the gutters** (logos, gradients, tickers,
  watermarks). The gutters are the bezel; ADR 0047's cap stands.
- **3×2 tile fold at desktop.** Two glances instead of one.
- **Auto-opening the price history at desktop.** Room is not a reason;
  desktop must not become a different page from the phone.

## What this does NOT establish

- That ~193px is the right tile size — Joe eyeballs that on his monitor,
  and six-across vs three-up is a look-at-it question he owns.
- That any other page should shed its rail; the Board's rail has real
  content and stands.
- Anything about what may appear on the market page — that is the
  2026-08-21 market-screen direction (venue's facts, never the tool's
  opinion), unchanged.
