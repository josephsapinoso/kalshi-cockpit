# Archive - the split log that used to head `tasks/lessons.md`

**Verbatim.** Moved out of the preamble and the index intro of
`tasks/lessons.md` on 2026-09-08 (ADR 0116). The rule they converge on
stays in the file: split at ~90%, checked before writing, on a date
boundary, index lines in the same edit, verbatim into a file named for the
split date, and regenerate the index from the headings.

---

**Split 2026-09-11, at 180,535 bytes — 68.9%, well under the trigger.**
Taken on a direct request to bring the file down toward 40–45% rather than
on the alarm. The nine 2026-09-08, five 2026-09-07, eight 2026-09-06 and ten
2026-09-05 entries — 32 in all — moved to `archive/lessons-2026-09-11.md`,
verbatim, leaving **118,685 bytes — 45.3%**. Date boundary as always: only a
whole-date cut was available near the target — the next one in (everything
2026-09-09 and earlier) would have left 78,149 bytes, **29.8%**, undershooting
the band by more than this split overshoots it, so the shallower cut was
taken. Verified by md5 against the exact bytes removed
(`895c39ab148bc6d2b3d6b63dbb03249f`); the only lines added to `lessons.md`
itself were the four moved dates' index pointers, repointed from "in this
file, above" to the new archive link, in the same edit. Done in **binary**,
per the lesson two splits above: `git diff --stat` came back 4 insertions,
1062 deletions — a pure deletion plus the four pointer lines, nothing else
touched.

**Split 2026-09-08, at 209,373 bytes — 79.9%, under the trigger and on
Joe's instruction rather than on the rule.** Everything 2026-09-04 and
earlier — 77 lessons across eight dates — moved to
`archive/lessons-2026-09-08.md`, verbatim, leaving **98KB, 37.5%**. Their
index headers were repointed from "in this file, above" to the archive
link in the same edit, because an index that still claims a moved lesson
is here is worse than no index.

**The same pass found the index was already 8 lessons short** — all four
2026-09-08 entries and four of the five 2026-09-07 ones had bodies and no
index lines. 2026-09-06 and 2026-09-05 were complete, so the gap is recent
and came from prepending a lesson without touching the index. **Writing
the lesson is half the work; the index is what makes it findable after the
next split**, and a lesson nobody can find gets learned twice.

**Split 2026-08-29, at 243,030 bytes — 92.7% of the ceiling, not past it.**
The nine 2026-08-17 entries still living here moved to
`archive/lessons-2026-08-29.md`, verbatim, leaving ~214KB — under 82%. That
file is named for the day of the split rather than the day of the lessons,
because `archive/lessons-2026-08-17.md` already exists and holds four *other*
entries from that date; one name must not point at two files. The index below
therefore carries two 2026-08-17 sections, one per file.

**Split 2026-09-05, at 229,412 bytes — 87.5%.** Every 2026-08-27 and
2026-08-26 lesson moved to `archive/lessons-2026-09-05.md`, verbatim, leaving
161KB — **61.5%**. Taken at 87.5% rather than at the 90% trigger, and on the
same reasoning the 2026-08-31 split records: clearing to just-under-the-line
buys one more split rather than several, and this file gained three lessons in
one session.

**The split was proved rather than assumed.** The archive's content was
reassembled with the two index lines restored and the result measured at
**229,412 bytes — the pre-split size exactly**. A split is a claim that
nothing was lost, and that claim is cheap to check and expensive to be wrong
about; the index lines moved in the same edit, because moving entries without
moving their index is a data loss with a table of contents.


**Split 2026-08-31, at 230,266 bytes — 87.8%.** The **fifty** lessons from
2026-08-25 back to 2026-08-18 moved to `archive/lessons-2026-08-31.md`,
verbatim, leaving 136KB — **52%**. A deeper cut than the last one on purpose:
this file was split twice in three days, and clearing to just-under-the-line
buys one more split rather than several.

**The index was updated in the same edit, and that is the load-bearing half.**
Seven `### DATE — in this file, above` markers became links to the new archive.
The header below this one already records why: an index that says "every lesson
ever written" while pointing at the wrong place makes the file lie about
itself, and a session scanning it for something relevant misses exactly the
lessons it was looking for. **Moving entries without moving their index lines
is not a split, it is a data loss with a table of contents.**

**This split was taken on the rule, not on the alarm.** Waiting for
`tests/test_session_files_are_readable.py` to go red is the wrong trigger: the
test guards the *file*, and what breaks first is the instruction at the top of
it — a session that cannot read the whole file reads the head and silently
believes it has the state. **Split at ~90%, not at 100%.** Read `wc -c` before
writing an entry, not after.

---

**Regenerated again 2026-08-31, and the same way for the same reason.** The
newest section here was 2026-08-26 listing eight lines, while the file above it
held **64** unarchived lessons across six dates -- so "every lesson ever
written" was false of its own file for the second time, and a session scanning
for something relevant would have missed everything written in the last five
days. **An index that is not regenerated in the same edit as the entry is stale
by one entry immediately and by dozens within a week.** Regenerate it from the
headings rather than appending by hand; the headings are the source.

**Regenerated 2026-08-26.** This index had listed the five entries of
2026-08-17 as "in this file, above" and stopped there, while 61 later lessons
sat unindexed above it — so the line "every lesson ever written" was false of
its own file, and a session scanning the index for something relevant would
have missed every lesson written in the last nine days. The titles below are
the lessons' own headings, taken verbatim; keep it that way, so regenerating it
is a script and not a judgement.
