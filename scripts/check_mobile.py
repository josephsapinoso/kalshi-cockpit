"""Measure horizontal overflow at a real phone viewport.

Run:  python -m scripts.check_mobile [--width 390] [--base http://localhost:3000]

Why this exists rather than a screenshot
----------------------------------------
The cockpit is meant to be used from a phone. Checking that by resizing a
browser window does not work -- a window resize does not necessarily change the
*viewport*, so the `sm:` media queries never switch and every screenshot comes
back looking like a desktop. And a screenshot at the right width shows you that
something is clipped without telling you which element is doing it.

So this drives headless Chrome over the DevTools protocol, sets the viewport
explicitly via `Emulation.setDeviceMetricsOverride`, and asks the page which
elements are wider than the viewport. The answer is a list of culprits, not an
impression.

Exit code is 1 when any page overflows, so this can gate a release.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Optional

import websockets

CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
]

PAGES = ["/", "/builder", "/dashboards", "/ledger", "/gate"]

# The measurement, run inside the page. Reports every element whose right edge
# lands past the viewport, deepest-first, with enough identity to fix it.
PROBE = """
(() => {
  const vw = document.documentElement.clientWidth;
  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.width > vw + 1) {
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 90),
        width: Math.round(r.width),
        right: Math.round(r.right),
        text: (el.textContent || '').trim().slice(0, 45),
        children: el.children.length,
      });
    }
  }
  // Text painting outside its own box, which the check above cannot see.
  //
  // Tailwind's `grid-cols-N` is `repeat(N, minmax(0, 1fr))`. The `0` is
  // deliberate and it means a column may shrink *below its own content*, so a
  // label too long for its cell does not widen the grid, does not widen the
  // card, and does not widen the document -- it simply draws over its
  // neighbour. `scrollWidth` is therefore identical to a correct layout's, and
  // so is the screenshot's dimensions. Measured on the Board at 320px:
  // "CONSENSUS" wanted 86px in a 69px cell and rendered as "CONSENSUSKALSHI".
  //
  // Only leaves with visible overflow count. An ancestor that scrolls is doing
  // this on purpose, and `truncate` sets `overflow: hidden`, which is a
  // decision to clip rather than an accident.
  const overlaps = [];
  for (const el of document.querySelectorAll('body *')) {
    if (el.children.length > 0) continue;
    const text = (el.textContent || '').trim();
    if (!text) continue;
    const style = getComputedStyle(el);
    if (style.overflowX !== 'visible') continue;
    if (el.scrollWidth > el.clientWidth + 1 && el.clientWidth > 0) {
      overlaps.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 90),
        needs: el.scrollWidth,
        has: el.clientWidth,
        text: text.slice(0, 45),
      });
    }
  }

  return JSON.stringify({
    viewport: vw,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    offenders,
    overlaps,
  });
})()
"""


def find_chrome() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    which = shutil.which("chrome") or shutil.which("google-chrome") or shutil.which("chromium")
    if which:
        return Path(which)
    raise SystemExit("Chrome not found. Install it or edit CHROME_CANDIDATES.")


async def _call(ws, request_id: int, method: str, params: Optional[dict] = None) -> dict:
    await ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(await ws.recv())
        if message.get("id") == request_id:
            return message


async def measure(
    ws_url: str,
    base: str,
    width: int,
    height: int,
    shot_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Measure, and optionally capture, through one CDP session.

    Screenshots come from the same connection that set the viewport. Chrome's
    `--headless --screenshot --window-size=W,H` does *not* set the layout
    viewport -- it renders at the default width and crops to W, so a page that
    fits perfectly still comes back looking clipped. Capturing here removes the
    possibility of the image and the measurement disagreeing.
    """
    results: list[dict[str, Any]] = []
    async with websockets.connect(ws_url, max_size=None) as ws:
        request_id = 0

        def next_id() -> int:
            nonlocal request_id
            request_id += 1
            return request_id

        await _call(ws, next_id(), "Page.enable")
        await _call(ws, next_id(), "Runtime.enable")
        # The step a window resize cannot do: set the layout viewport itself,
        # so the CSS media queries actually switch.
        await _call(
            ws, next_id(), "Emulation.setDeviceMetricsOverride",
            {
                "width": width, "height": height,
                "deviceScaleFactor": 2, "mobile": True,
            },
        )

        for path in PAGES:
            await _call(ws, next_id(), "Page.navigate", {"url": f"{base}{path}"})
            # Server components render on request; give the load a moment rather
            # than racing it and measuring an empty page.
            await asyncio.sleep(2.5)
            response = await _call(
                ws, next_id(), "Runtime.evaluate",
                {"expression": PROBE, "returnByValue": True, "awaitPromise": True},
            )
            raw = response["result"]["result"].get("value")
            if raw is None:
                results.append({"path": path, "error": response["result"]})
                continue
            payload = json.loads(raw)
            payload["path"] = path

            if shot_dir is not None:
                shot = await _call(
                    ws, next_id(), "Page.captureScreenshot",
                    {"format": "png", "captureBeyondViewport": True},
                )
                name = (path.strip("/") or "board") + ".png"
                destination = shot_dir / name
                destination.write_bytes(
                    base64.b64decode(shot["result"]["data"])
                )
                payload["screenshot"] = str(destination)

            results.append(payload)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=390)
    parser.add_argument("--height", type=int, default=844)
    parser.add_argument("--base", default="http://localhost:3000")
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument(
        "--shots",
        default=None,
        help="Directory to write full-page screenshots at this viewport",
    )
    args = parser.parse_args()

    shot_dir = Path(args.shots) if args.shots else None
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    chrome = find_chrome()
    process = subprocess.Popen(
        [
            str(chrome), "--headless", "--disable-gpu", "--no-first-run",
            f"--remote-debugging-port={args.port}",
            f"--window-size={args.width},{args.height}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    try:
        ws_url = None
        for _ in range(40):
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{args.port}/json/list", timeout=1
                ) as response:
                    tabs = json.load(response)
                pages = [t for t in tabs if t.get("type") == "page"]
                if pages:
                    ws_url = pages[0]["webSocketDebuggerUrl"]
                    break
            except Exception:
                pass
            import time

            time.sleep(0.25)

        if not ws_url:
            raise SystemExit("Chrome did not expose a debugging endpoint.")

        results = asyncio.run(
            measure(ws_url, args.base, args.width, args.height, shot_dir)
        )
    finally:
        process.terminate()

    failed = False
    print(f"\nViewport {args.width}x{args.height}\n" + "=" * 72)
    for page in results:
        if "error" in page:
            print(f"\n{page['path']}: probe failed -- {page['error']}")
            failed = True
            continue

        overflow = page["scrollWidth"] - page["viewport"]
        status = "OK" if overflow <= 0 else f"OVERFLOWS by {overflow}px"
        print(f"\n{page['path'] or '/'}  scrollWidth={page['scrollWidth']}  {status}")

        # Reported even on a page that fits, because a page that fits is
        # exactly where this hides.
        for overlap in page.get("overlaps", []):
            failed = True
            print(
                f"    PAINTS OUTSIDE ITS BOX: {overlap['tag']} needs "
                f"{overlap['needs']}px in {overlap['has']}px -- "
                f"{overlap['text']!r}"
            )
            print(f"           cls={overlap['cls'][:58]!r}")

        if overflow <= 0:
            # Elements can legitimately extend past the viewport when an
            # ancestor scrolls them -- the nav link row is meant to do exactly
            # that at 320px. Listing those would train the reader to ignore
            # this output, so only a page that actually widens gets a report.
            continue

        failed = True
        # Only the widest few matter; the rest are usually their ancestors.
        worst = sorted(page["offenders"], key=lambda o: -o["width"])[:6]
        for offender in worst:
            print(
                f"    {offender['tag']:<6} w={offender['width']:<5} "
                f"right={offender['right']:<5} "
                f"cls={offender['cls'][:58]!r}"
            )
            if offender["text"]:
                print(f"           text={offender['text']!r}")

    print("\n" + "=" * 72)
    print("FAIL -- see above" if failed else "All pages fit the viewport.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
