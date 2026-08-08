"""Open the ticket sheet on a real viewport, tap Confirm, and measure both.

Run:  python -m scripts.check_ticket_sheet --width 390 --token <APP_AUTH_TOKEN>

Why this exists rather than `check_mobile.py`
---------------------------------------------
`check_mobile.py` measures the five pages as they *load*. The ticket sheet is
not on any of them: it exists only after a tap, it is `position: fixed`, and
that combination defeats both halves of that script.

- **A tap is required.** A page-load measurement cannot see a component that
  only mounts on an interaction, so the sheet could overflow at 320px on every
  handset and every existing check would stay green.
- **`scrollWidth` cannot see it.** A fixed-position element is laid out against
  the viewport, not the document, so an over-wide sheet does **not** widen
  `document.documentElement.scrollWidth`. The offender list is the measurement
  here and the document width is not evidence of anything.

So this drives the same CDP session `check_mobile.py` does -- real layout
viewport via `Emulation.setDeviceMetricsOverride`, screenshots captured through
the connection that set it -- and then dispatches real mouse events to open the
sheet and to press Confirm.

**The answer state is the point.** With no evidence in the record the gate is
locked, so a tap on Confirm returns 423 with the unmet conditions, and that
screen -- not the ticket above it -- is what a person on a phone actually gets
today. It renders four conditions with prose, which is the tallest and
widest thing this component ever draws. Measuring the ticket and not the
refusal would be measuring the state that does not happen.

What it does not establish
--------------------------
Chrome's device emulation is not a handset. It reflows correctly, which is the
thing screenshots and window resizes get wrong, but it does not reproduce iOS
Safari's dynamic viewport, a notch, or a real thumb. `dvh` and
`env(safe-area-inset-bottom)` are asserted to be *present* in the stylesheet by
this script; whether they behave is a claim about Safari that only Safari can
settle.
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

# Minimum comfortable touch target. 44px is Apple's figure and the one the
# stepper (`h-11 w-11`) was built against; anything the reader must hit to get
# out of this sheet is checked against it.
MIN_TAP_PX = 44

# The measurement, run inside the page.
#
# `offenders` deliberately excludes anything inside an element that scrolls
# horizontally on purpose -- the nav link row and the `<pre>` holding the
# request body both do, and reporting them would train the reader to skim past
# this output. Everything else wider than the viewport is clipping.
PROBE = """
(() => {
  const vw = document.documentElement.clientWidth;
  const vh = document.documentElement.clientHeight;

  const scrollsHorizontally = (el) => {
    const style = getComputedStyle(el);
    return style.overflowX === 'auto' || style.overflowX === 'scroll';
  };
  const insideAScroller = (el) => {
    for (let p = el.parentElement; p; p = p.parentElement) {
      if (scrollsHorizontally(p) && p.getBoundingClientRect().width <= vw + 1) {
        return true;
      }
    }
    return false;
  };

  const offenders = [];
  for (const el of document.querySelectorAll('body *')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right > vw + 1 || r.width > vw + 1) {
      if (insideAScroller(el)) continue;
      offenders.push({
        tag: el.tagName.toLowerCase(),
        cls: (el.getAttribute('class') || '').slice(0, 90),
        width: Math.round(r.width),
        right: Math.round(r.right),
        text: (el.textContent || '').trim().slice(0, 45),
      });
    }
  }

  const dialog = document.querySelector('[role="dialog"]');
  const rect = (el) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      top: Math.round(r.top), bottom: Math.round(r.bottom),
      left: Math.round(r.left), right: Math.round(r.right),
      width: Math.round(r.width), height: Math.round(r.height),
    };
  };

  // Every button the sheet offers, with the geometry that decides whether a
  // thumb can hit it and whether it is on screen at all.
  const buttons = dialog
    ? [...dialog.querySelectorAll('button')].map((b) => ({
        label: (b.getAttribute('aria-label') || b.textContent || '').trim().slice(0, 40),
        disabled: b.disabled,
        ...rect(b),
      }))
    : [];

  return JSON.stringify({
    viewport: vw,
    viewportHeight: vh,
    scrollWidth: document.documentElement.scrollWidth,
    offenders,
    dialogPresent: dialog !== null,
    // The sheet slides up over 0.26s. Measured mid-flight it reports itself
    // 6% of its own height below where it lands -- 45px at 320, which reads
    // exactly like a sheet that overflows the bottom of the screen. Nothing is
    // measured until this is false.
    animating: dialog
      ? dialog.getAnimations().some((a) => a.playState === 'running')
      : false,
    dialogModal: dialog ? dialog.getAttribute('aria-modal') : null,
    dialogFocused: dialog ? dialog.contains(document.activeElement) : false,
    focusedElement: (() => {
      const a = document.activeElement;
      if (!a) return null;
      return (
        a.tagName.toLowerCase() +
        (a.id ? '#' + a.id : '') +
        ((a.textContent || '').trim() ? ' ' + (a.textContent || '').trim().slice(0, 24) : '')
      );
    })(),
    bodyLocked: getComputedStyle(document.body).overflow === 'hidden',
    dialog: rect(dialog),
    buttons,
    // The verdict heading, when the sheet is showing an answer.
    verdictCode: (() => {
      const h = dialog && dialog.querySelector('h3.display');
      if (!h) return null;
      const code = h.previousElementSibling;
      return {
        code: code ? code.textContent.trim() : null,
        heading: h.textContent.trim(),
      };
    })(),
    conditionCount: dialog ? dialog.querySelectorAll('ul > li').length : 0,
    text: dialog ? dialog.innerText.replace(/\\n{2,}/g, '\\n').slice(0, 2200) : null,
  });
})()
"""

# Board cards are wrapped in the ticket trigger; the first one is the tap.
#
# Scrolled into view before its coordinates are read, and read *after* the
# scroll. A card on the Board sits below a demo banner, a header, the window
# banner and a stats row, so on a 320x844 screen the first one starts below the
# fold -- and a mouse event dispatched at a point outside the viewport is
# silently dropped by the browser, which presents as "the sheet does not open"
# rather than as a bad coordinate.
SCROLL_TO_TRIGGER = """
(() => {
  const trigger = document.querySelector('button.block.w-full');
  if (!trigger) return JSON.stringify({found: false});
  trigger.scrollIntoView({block: 'center'});
  return JSON.stringify({found: true});
})()
"""

FIND_TRIGGER = """
(() => {
  const trigger = document.querySelector('button.block.w-full');
  if (!trigger) return JSON.stringify({found: false});
  const r = trigger.getBoundingClientRect();
  return JSON.stringify({
    found: true,
    x: Math.round(r.left + r.width / 2),
    y: Math.round(r.top + Math.min(r.height / 2, 60)),
    top: Math.round(r.top),
    height: Math.round(r.height),
    text: (trigger.textContent || '').trim().slice(0, 60),
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
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            return message


class Session:
    """One CDP connection, one viewport, one page."""

    def __init__(self, ws, base: str, shot_dir: Optional[Path]):
        self.ws = ws
        self.base = base
        self.shot_dir = shot_dir
        self._id = 0

    def _next(self) -> int:
        self._id += 1
        return self._id

    async def call(self, method: str, params: Optional[dict] = None) -> dict:
        return await _call(self.ws, self._next(), method, params)

    async def evaluate(self, expression: str) -> Any:
        response = await self.call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        value = response["result"]["result"].get("value")
        return None if value is None else json.loads(value)

    async def probe(self) -> dict:
        return await self.evaluate(PROBE)

    async def tap(self, x: int, y: int) -> None:
        """A real input event, not `element.click()`.

        `.click()` runs the handler without the browser deciding whether the
        point is hittable, so it would report success on a button covered by
        the veil or pushed off the bottom of the screen -- the two failures a
        bottom sheet on a phone actually has.
        """
        for kind in ("mousePressed", "mouseReleased"):
            await self.call(
                "Input.dispatchMouseEvent",
                {
                    "type": kind, "x": x, "y": y,
                    "button": "left", "clickCount": 1, "buttons": 1,
                },
            )
            await asyncio.sleep(0.05)

    async def screenshot(self, name: str) -> Optional[str]:
        if self.shot_dir is None:
            return None
        shot = await self.call(
            "Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}
        )
        destination = self.shot_dir / name
        destination.write_bytes(base64.b64decode(shot["result"]["data"]))
        return str(destination)


async def sign_in(session: Session, token: str) -> str:
    """Log in through the page, the way a phone does.

    Setting the cookie over CDP would be faster and would skip the one screen
    every live session starts on. This types the token into the form instead,
    so a login page that does not fit 320px fails here rather than in someone's
    hand.
    """
    await session.call("Page.navigate", {"url": f"{session.base}/login"})
    await asyncio.sleep(1.5)
    filled = await session.evaluate(
        """
        (() => {
          const input = document.querySelector('input[name="token"], input[type="password"]');
          const form = document.querySelector('form');
          if (!input || !form) return JSON.stringify({ok: false});
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
          setter.call(input, TOKEN);
          input.dispatchEvent(new Event('input', {bubbles: true}));
          form.submit();
          return JSON.stringify({ok: true});
        })()
        """.replace("TOKEN", json.dumps(token))
    )
    await asyncio.sleep(2.0)
    landed = await session.evaluate("JSON.stringify(location.pathname)")
    if not filled or not filled.get("ok"):
        return "no login form on the page"
    return f"signed in, landed on {landed}"


async def wait_for(session: Session, predicate, attempts: int = 30) -> dict:
    for _ in range(attempts):
        state = await session.probe()
        if predicate(state):
            return state
        await asyncio.sleep(0.35)
    return await session.probe()


async def run(ws_url: str, base: str, token: str, width: int, height: int,
              shot_dir: Optional[Path], fail_order: bool = False) -> dict:
    async with websockets.connect(ws_url, max_size=None) as ws:
        session = Session(ws, base, shot_dir)
        await session.call("Page.enable")
        await session.call("Runtime.enable")
        await session.call("Network.enable")
        await session.call(
            "Emulation.setDeviceMetricsOverride",
            {"width": width, "height": height, "deviceScaleFactor": 2, "mobile": True},
        )

        report: dict[str, Any] = {"width": width, "steps": []}

        if token:
            report["login"] = await sign_in(session, token)

        await session.call("Page.navigate", {"url": f"{base}/"})
        await asyncio.sleep(2.5)

        scrolled = await session.evaluate(SCROLL_TO_TRIGGER)
        if not scrolled or not scrolled.get("found"):
            report["error"] = (
                "no tappable card on the Board. The sheet cannot be measured "
                "without one -- seed a database with a surfaced row."
            )
            return report
        await asyncio.sleep(0.4)
        trigger = await session.evaluate(FIND_TRIGGER)

        report["card"] = trigger["text"]
        report["card_at"] = f"y={trigger['y']} (top {trigger['top']}, {trigger['height']}px tall)"
        await session.tap(trigger["x"], trigger["y"])
        opened = await wait_for(
            session, lambda s: s.get("dialogPresent") and not s.get("animating")
        )
        opened["shot"] = await session.screenshot(f"ticket-{width}.png")
        report["steps"].append(("ticket", opened))
        if not opened.get("dialogPresent"):
            report["error"] = "tapping the card did not open the sheet."
            return report

        # The token, typed into the sheet. On a live instance the session
        # cookie deliberately does *not* carry order authority, so Confirm
        # stays disabled until `APP_AUTH_TOKEN` is in this field -- meaning a
        # run that skipped it would report "disabled" and never reach the
        # refusal this script exists to measure.
        if token:
            report["token_field"] = await session.evaluate(
                """
                (() => {
                  const input = document.getElementById('ticket-token');
                  if (!input) return JSON.stringify({present: false});
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(input, TOKEN);
                  input.dispatchEvent(new Event('input', {bubbles: true}));
                  return JSON.stringify({present: true});
                })()
                """.replace("TOKEN", json.dumps(token))
            )
            await asyncio.sleep(0.3)
            opened = await session.probe()

        # Press Confirm. Named rather than positional: the action bar holds one
        # button before the answer and up to two after it.
        confirm = next(
            (b for b in opened["buttons"] if b["label"].lower().startswith("confirm")),
            None,
        )
        if confirm is None:
            report["error"] = "no Confirm button in the sheet."
            return report
        report["confirm"] = confirm
        if confirm["disabled"]:
            report["steps"].append(("confirm-disabled", confirm))
            return report

        # Block the order request so the sheet renders its offline answer.
        #
        # This is the one branch that cannot be produced by any database state:
        # `status: 0` means the request never left the handset, which on a real
        # phone is a tunnel or a dead cell and here is the only way to see the
        # two-button action bar at all. The bar's own comment records that
        # three buttons "turned into a three-line stack of wrapped labels at
        # 320" -- a claim about a layout that, until this flag existed, had
        # never been rendered.
        if fail_order:
            await session.call(
                "Network.setBlockedURLs", {"urls": ["*/api/orders"]}
            )

        await session.tap(
            (confirm["left"] + confirm["right"]) // 2,
            (confirm["top"] + confirm["bottom"]) // 2,
        )
        answered = await wait_for(
            session, lambda s: (s.get("verdictCode") or {}).get("code") not in (None, "")
        )
        answered["shot"] = await session.screenshot(f"answer-{width}.png")
        report["steps"].append(("answer", answered))
        return report


def describe(report: dict, show_text: bool = False) -> bool:
    """Print the report. Returns True if anything failed."""
    width = report["width"]
    failed = False
    print(f"\n{'=' * 72}\nViewport {width}px")
    if "login" in report:
        print(f"  login: {report['login']}")
    if "error" in report:
        print(f"  FAIL: {report['error']}")
        return True
    print(f"  card:  {report['card'][:60]!r}  {report.get('card_at', '')}")

    for name, state in report["steps"]:
        print(f"\n  -- {name} " + "-" * (66 - len(name)))
        if name == "confirm-disabled":
            print(f"     Confirm is disabled: {state}")
            continue

        dialog = state.get("dialog") or {}
        vh = state.get("viewportHeight", 0)
        verdict = state.get("verdictCode") or {}
        if verdict.get("code"):
            print(f"     verdict:   {verdict['code']} -- {verdict['heading']}")
        if state.get("conditionCount"):
            print(f"     conditions rendered: {state['conditionCount']}")
        print(
            f"     dialog:    {dialog.get('width')}x{dialog.get('height')} "
            f"top={dialog.get('top')} bottom={dialog.get('bottom')} (viewport {vh})"
        )
        print(
            f"     modal:     aria-modal={state.get('dialogModal')} "
            f"focus-inside={state.get('dialogFocused')} "
            f"body-locked={state.get('bodyLocked')}"
        )

        # A modal that does not hold focus is not modal. The Tab handler only
        # wraps when focus is already on the first or last control inside the
        # sheet, so focus resting on `<body>` walks straight out into the page
        # behind the veil -- and it lands there the moment Confirm unmounts,
        # which is exactly when the reader is being shown the answer.
        if not state.get("dialogFocused"):
            failed = True
            print(
                f"     FOCUS ESCAPED: focus is on "
                f"{state.get('focusedElement')!r}, outside the sheet"
            )

        # Every offender is a clip, since the probe already excluded anything
        # inside something built to scroll.
        offenders = state.get("offenders", [])
        if offenders:
            failed = True
            print(f"     OVERFLOWS: {len(offenders)} element(s) wider than {width}px")
            for offender in sorted(offenders, key=lambda o: -o["width"])[:6]:
                print(
                    f"        {offender['tag']:<6} w={offender['width']:<5} "
                    f"right={offender['right']:<5} cls={offender['cls'][:52]!r}"
                )
                if offender["text"]:
                    print(f"            text={offender['text']!r}")
        else:
            print(f"     width:     OK -- nothing wider than {width}px")

        # The sheet must not extend past the bottom of the screen: that is
        # where every button on it lives.
        if dialog and dialog.get("bottom", 0) > vh + 1:
            failed = True
            print(
                f"     OFF-SCREEN: the sheet ends at {dialog['bottom']}px, "
                f"{dialog['bottom'] - vh}px below the {vh}px viewport"
            )

        for button in state.get("buttons", []):
            if button["bottom"] > vh + 1 or button["top"] < -1:
                failed = True
                print(
                    f"     UNREACHABLE: {button['label']!r} at "
                    f"top={button['top']} bottom={button['bottom']} (viewport {vh})"
                )
            # Disabled buttons are excluded: they cannot be pressed, so their
            # size is not a claim about anything. Everything else on a sheet
            # built to be used one-handed has to be hittable.
            if not button["disabled"] and (
                button["height"] < MIN_TAP_PX or button["width"] < MIN_TAP_PX
            ):
                failed = True
                print(
                    f"     TAP TARGET: {button['label']!r} is "
                    f"{button['width']}x{button['height']}, under {MIN_TAP_PX}px"
                )
        # A disabled button must name the reason it is disabled, and only a
        # reason the reader can act on should read like an instruction.
        #
        # Coupled to the copy on purpose. The failure this catches is not a
        # layout fault and no geometry can see it: the sheet said "The token
        # above is required before this can be sent." on a row whose consensus
        # had aged out, three paragraphs below its own note saying the Confirm
        # button was off for a completely different reason. Both sentences were
        # correct; the one under the button was the useless one.
        text = state.get("text") or ""
        if "until the next sweep runs" in text and "token above is required" in text:
            failed = True
            print(
                "     CONTRADICTORY: the sheet says the consensus aged out, "
                "and the line under the button asks for a token instead"
            )

        if state.get("shot"):
            print(f"     shot:      {state['shot']}")
        # The sheet's own words. Layout is measured above; whether the sentence
        # on screen names the actual reason is a thing only reading it settles.
        if show_text and state.get("text"):
            print("     text:")
            for line in state["text"].splitlines():
                print(f"       | {line}")

    return failed


def main() -> int:
    # The sheet is full of typographic characters -- a real minus sign in the
    # stepper, em dashes in the button labels -- and a Windows console defaults
    # to cp1252, where printing them raises. Reporting a layout failure that is
    # really an encoding failure would send the next reader after the wrong
    # thing entirely.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--width", type=int, action="append",
        help="Repeatable. Defaults to 320, 390 and 430.",
    )
    parser.add_argument("--height", type=int, default=844)
    parser.add_argument("--base", default="http://127.0.0.1:3000")
    parser.add_argument("--port", type=int, default=9334)
    parser.add_argument(
        "--token", default="",
        help="APP_AUTH_TOKEN, for a live-mode instance behind the login.",
    )
    parser.add_argument("--shots", default=None)
    parser.add_argument(
        "--fail-order", action="store_true",
        help="Block POST /api/orders in the browser, so the sheet renders the "
             "answer it gives when the request never reaches the cockpit.",
    )
    parser.add_argument(
        "--text", action="store_true",
        help="Print the sheet's rendered text. The layout check cannot "
             "tell you whether the sentence names the right reason.",
    )
    args = parser.parse_args()

    widths = args.width or [320, 390, 430]
    shot_dir = Path(args.shots) if args.shots else None
    if shot_dir:
        shot_dir.mkdir(parents=True, exist_ok=True)

    chrome = find_chrome()
    process = subprocess.Popen(
        [
            str(chrome), "--headless", "--disable-gpu", "--no-first-run",
            f"--remote-debugging-port={args.port}",
            f"--window-size={max(widths)},{args.height}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    failed = False
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

        for width in widths:
            report = asyncio.run(
                run(
                    ws_url, args.base, args.token, width, args.height,
                    shot_dir, fail_order=args.fail_order,
                )
            )
            failed = describe(report, show_text=args.text) or failed
    finally:
        process.terminate()

    print("\n" + "=" * 72)
    print("FAIL -- see above" if failed else "The ticket sheet fits every viewport.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
