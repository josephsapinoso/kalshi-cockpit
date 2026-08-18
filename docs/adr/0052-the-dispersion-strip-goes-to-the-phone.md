# 0052 — The dispersion strip goes to the phone

Date: 2026-08-19
Status: accepted
Amends: ADR 0047 (the desktop tier is a reading surface)

## Context

ADR 0051 shipped the dispersion strip `xl:`-only, under ADR 0047's rule that
everything below 1280px stays byte-identical. That was the conservative reading
and it was stated as a decision with a cost, handed to Joe rather than taken
quietly.

He took it the same day: **put the strip on the phone too.**

He is right, and the reason is not a preference. Joe reads `/slate` on a phone —
it is the documented habit, and it is why the deep-link repair of 2026-08-18
mattered. An explanation of where a number came from that exists only on a
monitor explains nothing to the person who owns the account.

## Decision

The strip renders at **every width**. The wrapper is `w-full xl:col-span-full`;
no `hidden`.

**ADR 0047 is amended, not overturned.** Its rule was about *density* — not
adding rows of columns to a hand-held screen, which is what the Anchor and Width
cells are and why they stay `xl:`-only. The strip is not a column. It is the one
element on the row that says where the row's own number came from, and the
argument for keeping columns off a phone does not reach it.

## The cost, measured

The seeded `/slate` at 390px grew from **5,808px to 8,912px** of scroll — **+53%**
across eleven rows. `scripts/check_mobile.py` is clean at
390/768/1024/1440/1920/2560, so this is length, not overflow.

Nothing was trimmed to pay for it, and that was considered. The two candidates
were the `worst method each` label and the anchoring caveat, which together wrap
to three lines on a phone and are near-identical on ten of eleven rows. Both
were kept: they are the labels that stop the picture making a claim about the
market instead of about the statistic (ADR 0051), and dropping them to save
scroll would trade honesty for density on the smaller screen — exactly backwards.

If it proves too long in use, the next move is a per-row disclosure, not a
breakpoint and not a shorter caveat.

## The guard is inverted, not deleted

`tests/test_dispersion_strip.py` pinned `hidden` on the wrapper. That assertion
is now its exact inverse: `hidden` must **not** appear.

Deleting it instead would have left the visibility unrecorded, and a future
session tidying phone density would re-add `hidden` as an obvious improvement
with nothing to argue against. Inverted, it fails with the reason attached.
Verified by re-hiding the strip and watching it go red.

## What this does not change

Nothing about what the strip says, computes or claims — see ADR 0051's "what
this does not establish". Nothing about `/estimate`, which ADR 0047 excludes
from the desktop tier on anchoring grounds and which this does not touch.
