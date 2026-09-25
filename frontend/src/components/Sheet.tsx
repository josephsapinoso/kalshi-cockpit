"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { focusWrap, type TrapPosition } from "@/lib/focusWrap";

/**
 * A slide-over panel: a bottom sheet on a phone, a panel docked to the right
 * edge from `lg` (#158, Joe's choice 2026-09-25).
 *
 * Built for the parlay desk's buy flow, which used to unfold three levels deep
 * inside a card about 277px wide. `TicketSheet.tsx` is the older sheet on
 * the Picks path and is left alone. It owns an order lifecycle, and this owns
 * none.
 *
 * **It never unmounts what it holds.** A closed sheet is `hidden`, not gone.
 * The flows inside it keep state that must survive a close: a maker's quote,
 * an order receipt, and above all an UNKNOWN acceptance, which has no retry
 * and no second chance to be read. The `<details>` this replaced kept its
 * children mounted when collapsed, and so does this.
 *
 * **It will not close while money is in flight.** Any control inside that
 * spends reports `useReportBusy(true)` while its request is out. Until the
 * answer lands, Escape and the backdrop do nothing. That is TicketSheet's
 * rule 2 applied here: closing mid-send throws away the only report of what
 * the venue did. The Close button is disabled for the same window.
 *
 * Focus is trapped with the same `focusWrap` predicate TicketSheet uses
 * (`tests/test_focus_wrap.py`), and returns to the opener on close.
 */

type BusyReporter = (id: string, busy: boolean) => void;

const BusyContext = createContext<BusyReporter | null>(null);

/**
 * Tell the enclosing sheet, if there is one, that a request that spends is
 * in flight. A no-op outside a sheet, so a component can call it on every
 * surface it is mounted on.
 */
export function useReportBusy(busy: boolean): void {
  const report = useContext(BusyContext);
  const id = useId();
  useEffect(() => {
    if (report === null) return;
    report(id, busy);
    return () => report(id, false);
  }, [report, id, busy]);
}

export default function Sheet({
  open,
  onClose,
  title,
  subtitle,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const headingId = useId();
  // Which children are mid-request. A Set in a ref plus a counter in state:
  // the ref is what the key handler reads, and the state re-renders the
  // Close button's disabled look.
  const inFlight = useRef<Set<string>>(new Set());
  const [busyCount, setBusyCount] = useState(0);
  const report = useCallback<BusyReporter>((id, busy) => {
    if (busy) inFlight.current.add(id);
    else inFlight.current.delete(id);
    setBusyCount(inFlight.current.size);
  }, []);
  const close = useRef(onClose);
  close.current = onClose;

  const tryClose = () => {
    if (inFlight.current.size > 0) return;
    close.current();
  };

  useEffect(() => {
    if (!open) return;
    const node = panel.current;
    if (!node) return;
    const opener = document.activeElement as HTMLElement | null;
    node.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        // Not while a request that spends is out; see the module docstring.
        if (inFlight.current.size > 0) return;
        event.preventDefault();
        close.current();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        node.querySelectorAll<HTMLElement>(
          'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),summary,[tabindex]:not([tabindex="-1"])',
        ),
        // Hidden tabs stay mounted; they must not be tab stops.
      ).filter((el) => el.offsetParent !== null);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const position: TrapPosition =
        active === node
          ? "panel"
          : active === first
            ? "first"
            : active === last
              ? "last"
              : "inside";
      const wrap = focusWrap(position, event.shiftKey);
      if (wrap === null) return;
      event.preventDefault();
      (wrap === "first" ? first : last).focus();
    };

    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      opener?.focus?.();
    };
  }, [open]);

  return (
    <BusyContext.Provider value={report}>
      <div
        hidden={!open}
        className={
          open
            ? "fixed inset-0 z-50 flex flex-col justify-end lg:flex-row lg:justify-end"
            : "hidden"
        }
      >
        <button
          type="button"
          aria-label="Close"
          tabIndex={-1}
          className="veil-in absolute inset-0 h-full w-full cursor-default bg-black/50"
          onClick={tryClose}
        />
        <div
          ref={panel}
          role="dialog"
          aria-modal="true"
          aria-labelledby={headingId}
          tabIndex={-1}
          className="sheet-rise relative flex h-[88dvh] w-full flex-col rounded-t-2xl border-t bg-card shadow-2xl outline-none lg:h-full lg:max-h-none lg:w-[32rem] lg:rounded-none lg:border-l lg:border-t-0"
        >
          <div className="flex items-start justify-between gap-3 border-b px-4 pb-3 pt-2 sm:px-6 lg:pt-5">
            <div className="min-w-0">
              <div
                aria-hidden
                className="mx-auto mb-3 h-1 w-10 rounded-full bg-[var(--border)] lg:hidden"
              />
              <h2
                id={headingId}
                className="truncate text-lg font-bold tracking-tight"
              >
                {title}
              </h2>
              {subtitle && (
                <p className="mt-0.5 text-sm text-muted">{subtitle}</p>
              )}
            </div>
            <button
              type="button"
              onClick={tryClose}
              disabled={busyCount > 0}
              className="mt-2 shrink-0 rounded-lg border px-3 py-1.5 text-xs text-muted disabled:opacity-50 lg:mt-0"
            >
              Close
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 sm:px-6">
            {children}
          </div>
        </div>
      </div>
    </BusyContext.Provider>
  );
}
