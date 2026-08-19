"""Poll live /api/health and record every latency, so a slow one is caught.

Deliberately not a summary: the failure being chased is intermittent, so the
mean is the least interesting number here. One line per probe, appended and
flushed immediately, because the process may be killed mid-run.

`machine_id` and `machine_version` come back in the `build` block, so a restart
is visible in the record without needing flyctl -- a changed `machine_version`
between two probes IS a restart, which is the thing this cannot otherwise see.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

URL = "https://kalshi-cockpit.fly.dev/api/health"
OUT = sys.argv[1]
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 900
EVERY = 5.0

end = time.time() + SECONDS
with open(OUT, "a", encoding="utf-8", buffering=1) as fh:
    while time.time() < end:
        started = time.time()
        row = {"t": time.strftime("%H:%M:%SZ", time.gmtime())}
        try:
            # 30s: longer than the heartbeat's 25s cutoff on purpose. If a slow
            # response is the cause, the interesting question is *how* slow --
            # a probe that gives up at 25s can only ever report ">25".
            with urllib.request.urlopen(URL, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            row["ms"] = round((time.time() - started) * 1000)
            row["code"] = resp.status
            row["status"] = body.get("status")
            build = body.get("build") or {}
            row["machine_version"] = build.get("machine_version")
            rec = body.get("recorder") or {}
            row["recorder_age_ms"] = rec.get("age_ms")
        except urllib.error.HTTPError as exc:
            row["ms"] = round((time.time() - started) * 1000)
            row["code"] = exc.code
        except Exception as exc:                               # noqa: BLE001
            row["ms"] = round((time.time() - started) * 1000)
            row["error"] = type(exc).__name__
        fh.write(json.dumps(row) + "\n")
        slept = EVERY - (time.time() - started)
        if slept > 0:
            time.sleep(slept)
