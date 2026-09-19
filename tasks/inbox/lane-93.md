# Lane 93 handoff

Ticket #93: extend `scripts/inspect_live_disk.py` with a `reserved` section
(reserved-for-root bytes) beside `unaccounted_bytes`.

Done. `capacity()` now returns `reserved_bytes = (f_bfree - f_bavail) *
f_frsize` from the same `os.statvfs` call it already made. `report()` adds a
`reserved` dict carrying `total_bytes`, `reserved_bytes`, and
`unaccounted_bytes` restated; `render_text()` prints both figures side by
side with an explicit "a match is not proof" caveat. Module docstring's
"What this does not establish" gained a bullet for the new section, and
`capacity()`'s own docstring explains the field. No subprocess, no file
opens, no change to what the script deletes (nothing).

Nothing here needs main-session follow-up beyond #94 (main) running the
script live and reading whether `reserved_bytes` is close to the historical
~882 MB `unaccounted_bytes` figure — that comparison is exactly what this
ticket built the capability for, but running it on the live box is #94's
job, not this lane's.
