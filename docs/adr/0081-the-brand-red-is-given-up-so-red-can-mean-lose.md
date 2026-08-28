# ADR 0081 — The brand red is given up so that red can mean lose

**Date:** 2026-08-28
**Status:** Accepted
**Decided by:** Joe, from a prototype, on decision-map ticket
[#10 "Brand red and loss red are the same colour"](https://github.com/josephsapinoso/kalshi-cockpit/issues/10).
**Supersedes nothing. Amends** ADR 0061 §3 (in place, at its own heading).

---

## 1. The defect

`--accent` and `--negative` were **byte-identical** in every theme block, and
had been since the palette was ported from `josephsapinoso/personal-website`:

```
light   --accent #aa0000    --negative #aa0000
dark    --accent #ef4444    --negative #ef4444
```

The source palette had no semantic loss colour because **a portfolio site has
no losses to paint**. A betting tool does, and the addition was made by
pointing `--negative` at the brand hue with a comment saying it "reads
naturally".

The consequence was structural rather than cosmetic: **every attempt to
emphasise anything read as "this is bad."** On the Games screen the single
loudest element was a refused row — the one row Joe must not bet. The eye was
pulled to the trap.

**One token carried three jobs**, not two, and the third is why this was not a
simple rename:

| role | example | what the record said |
|---|---|---|
| Identity | the nav logo tile, the focus ring, `.link-underline`, the ledger progress bar, the skip link | nothing — inherited |
| Commit money | the hand-bet confirm, the four ticket buttons, "Price on Kalshi", the login button | **ADR 0061 §3 by name** |
| Loss and refusal | the REJECTED chip, suppression reasons, unmet gate conditions, every negative number | `globals.css:29-31`, as a feature |

The cost had already been paid in comments rather than fixed: six components
gave up an emphasis they wanted rather than say *bad*
(`board/page.tsx:463`, `slate/page.tsx:920`, `FairValueSteps.tsx:32`,
`ParlayDifficulty.tsx:28`, `GoodChancePicks.tsx:28`, `slate/page.tsx:216`).

## 2. And a live accessibility failure that no test could see

Recomputing the ratios from scratch — rather than trusting the ticket's
arithmetic — turned up a defect that was **shipped and unguarded on live**:

```
white on --accent (dark)   3.76 : 1     floor for 14px semibold: 4.5 : 1
```

Every filled control in the app: `ManualTicket.tsx:563` (the **real-money**
confirm), `TicketSheet.tsx`'s four, `PriceOnKalshi.tsx:107`,
`market/[ticker]/page.tsx:351`, `login/page.tsx:66`, `Nav.tsx:202`.

`tests/test_palette_contrast.py` was green throughout, and it was not a bad
test — **it was checking a different pair.** It checked tokens *as ink on a
ground* and never *as a fill under white*. `--accent` cleared every ink check
in the file and failed as a fill, because in dark mode the shade that is
legible as ink is a light one, and white does not sit on a light shade.

**This is the generalisable finding of the whole ticket:** ink-on-ground and
white-on-fill are two different measurements of one token, and a palette guard
that takes only the first will pass a button nobody can read.

## 3. The decision — Split A

Chosen by Joe from a prototype drawing a real Games row and a real Picks block
four times (today plus three candidate splits), in both themes:
https://claude.ai/code/artifact/ddfe5cc4-c58c-43dd-b14e-c665050b81d4

**1. `--accent` becomes indigo and means identity + commit.** Two tokens, not
one, and that is the fix rather than an inconvenience:

```
light   --accent      #2f3d8f   9.61:1 on card,  9.21:1 on background
        --accent-fill #2f3d8f   white on it 9.61:1
        --accent-soft #e8eaf7   accent ink on it 8.03:1
dark    --accent      #8ea2ff   7.65:1 on card,  8.24:1 on background
        --accent-fill #3b4bb8   white on it 7.28:1
        --accent-soft #151a33   accent ink on it 7.14:1
```

The two are equal in light and **deliberately unequal in dark**. One token
doing both jobs is precisely how §2's defect got in.

**Indigo was chosen by arithmetic, not taste.** Petrol and teal were the
obvious "calm instrument" candidates and both were dropped on separation from
`--positive` green: Euclidean sRGB distance 43 (petrol, light) and 87 (petrol,
dark) against indigo's 92 and 156. Roughly one man in twelve cannot separate
red from green. Indigo-to-red separation survives simulation: **177 under
deuteranopia, 168 under protanopia**, and that floor is now a test.

**2. `--negative` keeps the red, unchanged, and nothing else may wear it.**
`#aa0000` / `#ef4444` are byte-identical to what they were. What changed is
exclusivity. The old red tint is not deleted — it is renamed `--negative-soft`
to the role it was actually serving.

**3. REJECTED moves to the warning ochre.** A refused row is not a loss —
nothing was spent. `--accent-2` on a new `--accent-2-soft` tint: light
`#7a5c14` on `#f7f0dd` (**5.48:1**), dark `#cbb279` on `#2a2313` (**7.55:1**).

This settles a contradiction nobody had noticed: on a REJECTED row the chip
was red while the edge number beside it was **already ochre**
(`EDGE_TONE_CLASS.refused`). Two tokens, one row, the same fact. Ochre wins
because the number got it right. The same reasoning moves every other refusal
— locked gate, unmet conditions, suppression reasons, the skeptic's refused
checks.

**4. Card panels take a new `--edge` token**, light `#cfc6bb` (1.69:1 on the
card), dark `#4a423b` (1.86:1). Joe was offered the strong option
(`--border-strong`, 2.68/3.04:1, no new token) and the soft one (deepen the
page ground) and took the middle. `--border` stays for row dividers.

**`suspicious_edge` keeps loss-red, deliberately.** CLAUDE.md rule 1 — a large
apparent edge is a bug until proven otherwise — is the one row on that screen
where the strongest available signal is correct. It keeps its ⚠ mark too.

## 4. What this achieves, and what it does not

**No split makes the refused row quieter, and none should.** The ticket's
framing — "the eye is pulled to the trap" — is answered not by dimming the
refusal but by making red **rare**. Under Split A the only red left on a normal
Games screen is the warning-marked suspicious-edge chip. The trap stops being
one loud thing among many and becomes the only one.

**The 1.04:1 surface is left alone.** The ticket called card-vs-page-background
`1.04:1` a border problem; it is not — the *border* is 1.30:1 against the card,
which `globals.css` already stated in its own comment. Both are invisible, so
the conclusion held, but they are two defects and this ADR fixes one. Joe took
the quiet-edge option over deepening the ground.

**Two decisions this opens and does not settle,** filed as tickets rather than
assumed:

- **[#32](https://github.com/josephsapinoso/kalshi-cockpit/issues/32) — the
  real-money warning strip.** `ManualTicket.tsx:476` was byte-identical to the
  REJECTED chip. The chip is now ochre and the button indigo; the strip was
  left on `--accent` and so is now indigo **by default, not by decision**. The
  prototype drew it red; that was an unreviewed call.
- **[#33](https://github.com/josephsapinoso/kalshi-cockpit/issues/33) — the six
  components that refused colour** are now free and nobody has said whether
  they take it. Their tests still forbid colour; only the stale *reason* in
  each docstring was rewritten.

## 5. Guards

`tests/test_palette_contrast.py` gains four assertions, and the first is the
one that would have prevented this ADR existing:

1. **`TestAFillIsCheckedAsAFill`** — white on every token used as a
   full-strength fill clears 4.5:1 in all three theme blocks, and every soft
   ground carries its paired ink. Mutation: restoring `--accent-fill: #ef4444`
   in dark turns it red at 3.76:1.
2. **`TestOneColourMeansOneThing`** — `--accent != --negative`, and they stay
   ≥60 apart under deuteranope and protanope simulation. Mutation: collapsing
   `--accent` back onto `#aa0000` turns both red, the second reporting a gap
   of 0.
3. **`TestTheNeutralCountIsNotPaintedAsAVerdict` was rewritten, not deleted.**
   Its premise was "`--accent` *is* `--negative`, so a Stat in it reads as a
   loss." That premise is now false and a Stat may lawfully wear indigo. What
   survives is the rule the two `Stat` comments were really about, and it is
   stronger: **a count is a fact, so no Stat wears the loss colour**, whatever
   the loss colour happens to be this month.
4. **Every `@theme inline` registration is pinned against the tokens.** A token
   defined in `:root` but not registered produces a Tailwind class that is
   **silently dropped** — no error, no build failure, the element simply
   renders with no colour. Four of this ADR's five new tokens are new classes,
   so the failure mode was one forgotten line away.

**Verified in the built CSS, not only in the source.** `bg-accent-fill`,
`bg-accent-2-soft`, `bg-negative-soft` and `border-edge` were each confirmed to
emit a rule pointing at the right custom property in
`.next/static/chunks/*.css` after `next build`. A green build proves nothing
here: Tailwind drops an unrecognised utility without complaint.

**One near-miss worth recording.** `border-edge` sets *colour* only; the
`border` class is what sets the 1px width. Rewriting `border bg-card` to
`border-edge bg-card` removed every panel's border entirely while typechecking
clean, building clean and passing every test. It was caught by reading the
diff, not by a guard, and no guard in this repo would have caught it.

## 6. What this does not establish

- Contrast is computed from the tokens in `globals.css`, not from rendered
  pixels. It cannot see opacity suffixes applied at the call site (`/50`,
  `/70`), text over images, or whether a component uses a token at all.
- The fill check knows which tokens are fills because the test file **names**
  them. A filled control built tomorrow on some other token is uncovered until
  it is added there.
- The colourblind simulation is a linear approximation, not a measurement of
  any real reader, and the 60 floor is a threshold this project chose rather
  than a published one. It catches a collapse; it does not certify a
  separation.
- **Nobody has looked at the result on a phone.** Every number here is
  arithmetic on hex values. Joe chose from a prototype rendered on a desktop
  browser, and the screens this paints are used one-handed on a handset.
