/**
 * Where a Tab keypress inside the ticket's focus trap should send focus.
 *
 * **The defect this exists for.** The trap in `TicketSheet.tsx` wraps by
 * comparing `document.activeElement` against the first and last focusable
 * elements *inside* the panel. The panel itself is `tabIndex={-1}` and is never
 * in that list — `node.querySelectorAll` returns descendants only, and the
 * selector excludes `[tabindex="-1"]` besides. But the panel is exactly what
 * holds focus after `node.focus()`, which runs on open and again on every phase
 * change.
 *
 * So in that state the active element is neither `first` nor `last`, both
 * branches are false, nothing calls `preventDefault`, and the browser default
 * runs. Forward that is harmless by accident: the next focusable in DOM order is
 * inside the panel. **Backward it walks out** — onto the veil button, which
 * precedes the panel in the DOM, and from there into the page behind the modal.
 *
 * The trap is therefore open, in the backward direction, at the moment the sheet
 * opens and at the moment every answer renders.
 *
 * **Why a predicate.** This is a four-case mapping where the wrong answer is
 * another valid-looking answer, and there is no DOM test runner here. A source
 * substring assertion passes unchanged on a mapping with `first` and `last`
 * swapped. `tests/test_focus_wrap.py` executes it under node instead, and proves
 * each clause is load-bearing by disabling it. Same reasoning as `sweepTone.ts`.
 */

/** Where the active element sits relative to the trap's focusable list. */
export type TrapPosition =
  /** The first focusable element inside the panel. */
  | "first"
  /** The last focusable element inside the panel. */
  | "last"
  /**
   * The panel container itself — `tabIndex={-1}`, focused programmatically on
   * open and on every phase change, and in the focusable list of neither end.
   * This is the case the original trap had no branch for.
   */
  | "panel"
  /** Anywhere else inside the panel, where the browser default is correct. */
  | "inside";

/**
 * The element to focus, or `null` to let the browser's own Tab order run.
 *
 * `panel` wraps in **both** directions. Backward is the bug — without it focus
 * leaves the modal entirely. Forward already lands on `first` by browser
 * default, and is returned explicitly anyway so the correct behaviour is
 * guaranteed by this function rather than inherited from DOM ordering that a
 * later markup change could reorder.
 */
export function focusWrap(
  position: TrapPosition,
  shiftKey: boolean,
): "first" | "last" | null {
  if (shiftKey) return position === "first" || position === "panel" ? "last" : null;
  return position === "last" || position === "panel" ? "first" : null;
}
