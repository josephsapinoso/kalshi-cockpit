# Archive - the split log that used to head `tasks/NEXT.md`

**Verbatim.** Moved out of the header of `tasks/NEXT.md` on 2026-09-08
(ADR 0116). Seven paragraphs, one per split, each recording the size at
which it was taken and what it taught. The rule they converge on stays in
the header: split at ~90%, checked before writing, on a date boundary,
index lines in the same edit, verbatim into a file named for the split date.

---

The split happened because this file had reached **456,641 bytes / 8,145
lines**, past the 262,144-byte ceiling at which the Read tool refuses a file
outright. `tests/test_session_files_are_readable.py` now fails if it or
`tasks/lessons.md` crosses back over. When you add an entry and the file grows,
move the older ones into the dated archive file — do not shorten them.

**Split again 2026-08-25, at 243,486 bytes — 93% of the ceiling, not past it.**
The 08-19 and 08-17 entries moved to `archive/next-2026-08-25.md`, verbatim,
leaving ~146KB here. Waiting for the test to go red is the wrong trigger: the
test guards the *file*, and what actually breaks first is the instruction at the
top of it — a session that cannot read the whole file reads the head and
silently believes it has the state. **Split at ~90%, not at 100%.**

**Split again 2026-08-29, at 225,270 bytes — 86%, before writing anything.**
The 2026-08-26 and 2026-08-25 entries (9 of them) moved to
`archive/next-2026-08-29.md`, verbatim, leaving ~148KB here. This is the first
split taken on the rule rather than on the alarm: `wc -c` was read before the
session's entry existed, and the entries moved out before it was added.

**Split again 2026-09-05, at 224,305 bytes — 85.6%, checked before writing.**
The five 2026-08-30 and two 2026-08-29 entries moved to
`archive/next-2026-09-05.md`, verbatim, leaving ~166KB — 63.6%. Taken under
the trigger rather than at it, because the entry about to be written was a
long one and the size that matters is the size *after*. The index section
went in the same edit; a split that moves entries without moving their index
lines is a data loss with a table of contents.

**Split again 2026-09-06, at 223,790 bytes — 85.4%, checked before writing.**
The three 2026-09-02, two 2026-09-01 and four 2026-08-31 entries moved to
`archive/next-2026-09-06.md`, verbatim, leaving 117KB — **44.7%**. Cut deeper
than the trigger required, on the reasoning `archive/lessons-2026-08-31.md`
records: clearing to well under the line buys one more split rather than
several. The cut falls on a **date boundary** — everything 2026-09-02 and
earlier moved — so no single day is split across two files, which the previous
splits did not always manage and which makes the index harder to read than it
needs to be. The move was verified by md5: the archived bytes below its header
hash identically to the bytes removed. Index lines moved in the same edit.

**Split again 2026-09-08, at 205,381 bytes — 78.3%, well under the
trigger and on Joe's instruction rather than on the rule.** The six
2026-09-06, one 2026-09-05, one 2026-09-04 and two 2026-09-03 entries
moved to `archive/next-2026-09-08.md`, verbatim, leaving **58KB — 22.3%**.
The deepest cut this file has taken, and deliberately so: it was asked for
before a fresh session opened, which is the one moment the cost of cutting
too much is zero and the cost of cutting too little is a split mid-session.
Date boundary as always; md5 verified; index lines written in the same
edit.

**Split again 2026-08-27, at 259,407 bytes — 98.9%, and that is a miss.** The
2026-08-24 through 2026-08-20 entries (27 of them) moved to
`archive/next-2026-08-27.md`, verbatim, leaving ~140KB here. The rule above says
90% and it was not followed, because the entry that crossed the line was the one
being written and nobody checks the size before adding. **Check `wc -c` BEFORE
writing an entry, not after** — at 98.9% the margin was 2,737 bytes, roughly one
paragraph, and the failure mode is silent.

**Split again 2026-09-11, at 200,701 bytes — 76.6%, checked before
writing.** The five 2026-09-09 and two 2026-09-08 entries moved to
`archive/next-2026-09-11.md`, verbatim, leaving **97KB — 37.2%**. The
lowest percentage any split has been taken at. Cut on the partner’s
reading that the file had two entries of headroom left: the trigger is a
ceiling, not a target, and a split is cheapest at the start of a session
and most expensive in the middle of one. Date boundary — everything
2026-09-09 and earlier moved, so the five 2026-09-10 entries stayed
together. md5 verified against the bytes removed
(`67e5e15a0c37d328786b10aa08b8e223`); index lines written in the same
edit.

**What this one taught, and it is about the script rather than the rule:**
do the move in **binary**. A text-mode round trip on Windows rewrites every
line ending in the file, so a seven-entry move renders as a whole-file diff
and the one thing a reviewer needs to see — that nothing outside the moved
range changed — becomes invisible. Read bytes, slice bytes, write bytes,
and hash the slice.
