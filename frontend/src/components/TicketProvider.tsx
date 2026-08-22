"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";

import TicketSheet from "@/components/TicketSheet";
import type { Recommendation } from "@/lib/api";

/**
 * Owns the one open ticket, so every card on the Board opens the same sheet.
 *
 * A provider rather than local state in each list because the Board renders its
 * rows from three places -- the live ticker, the expired section, and whatever
 * comes next -- and a sheet per list would let two of them be open at once, on
 * a screen 320px wide, with a confirm button each.
 *
 * **The token lives here, in memory, for the life of the page.** Not in
 * `localStorage`, not in `sessionStorage`, not in a cookie. `APP_AUTH_TOKEN` is
 * the bearer that authorises the one route that can spend money, and the
 * session cookie is built specifically so that holding it does *not* give that
 * authority -- see `lib/session.ts`. Persisting the token in the browser would
 * quietly undo that: any XSS, any shared handset, any devtools screenshot would
 * hand over order authority, which is precisely the trade the cookie design
 * refused to make. Keeping it in a React state variable means it survives
 * closing and reopening the sheet, and dies on reload.
 */

type TicketState = {
  open: (rec: Recommendation) => void;
};

const TicketContext = createContext<TicketState | null>(null);

export function useTicket(): TicketState {
  const context = useContext(TicketContext);
  if (context === null) {
    // A card that could not find the provider would silently do nothing when
    // tapped, which is the worst available failure: it looks like the sheet is
    // not built yet.
    throw new Error("A ticket trigger was rendered outside <TicketProvider>.");
  }
  return context;
}

export function TicketProvider({
  instanceMode,
  quoteLimitMs,
  oddsLimitMs,
  children,
}: {
  instanceMode: string;
  quoteLimitMs: number;
  oddsLimitMs: number;
  children: React.ReactNode;
}) {
  const [ticket, setTicket] = useState<Recommendation | null>(null);
  const [token, setToken] = useState("");

  // Used to carry an `actionable` override the caller could narrow the row
  // to (never widen it). Removed 2026-08-22: `TicketTrigger` is this
  // provider's sole caller, passes no override, and every row it ever opens
  // already arrived actionable (`board.surfaced` is `routes.py`'s
  // actionable-only partition) -- the override existed for a state that
  // could never occur. See `TicketSheet`'s module docstring for the finding.
  const open = useCallback((rec: Recommendation) => {
    setTicket(rec);
  }, []);

  const value = useMemo(() => ({ open }), [open]);

  return (
    <TicketContext.Provider value={value}>
      {children}
      {ticket && (
        <TicketSheet
          // Keyed on the row so opening a second ticket resets the sheet's own
          // state rather than showing the previous bet's answer under a new
          // heading.
          key={ticket.id}
          rec={ticket}
          demo={instanceMode === "demo"}
          quoteLimitMs={quoteLimitMs}
          oddsLimitMs={oddsLimitMs}
          token={token}
          onToken={setToken}
          onClose={() => setTicket(null)}
        />
      )}
    </TicketContext.Provider>
  );
}

/**
 * Makes a card tappable.
 *
 * A real `<button>` rather than a click handler on a div: this has to work with
 * a keyboard and with a screen reader, and "the whole card is the target" is
 * the only hit area that works for a thumb at 320px. The card's own markup
 * stays inside it and is read out; the appended label says what tapping does,
 * which `aria-label` on the button would have replaced it with.
 */
export function TicketTrigger({
  rec,
  children,
}: {
  rec: Recommendation;
  children: React.ReactNode;
}) {
  const { open } = useTicket();
  return (
    <button
      type="button"
      onClick={() => open(rec)}
      className="block w-full min-w-0 text-left"
    >
      {children}
      <span className="sr-only">Open the ticket for this bet</span>
    </button>
  );
}
