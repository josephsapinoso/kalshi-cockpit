/**
 * Live top of book for the tickers on one screen, from `/api/stream/books`.
 *
 * Pure functions only: no React and no imports, so Node can run the shipped
 * file directly in `tests/test_live_books_client.py`. The hook that drives
 * them is `useLiveBooks.ts`.
 *
 * **No money figure is computed here.** A frame carries the venue's bid, ask
 * and depth and nothing else. The ticket's max price, fee and break-even stay
 * the preflight the server computed; `askMoved` only says that the ask on the
 * book is no longer the one the ticket was priced at (Joe, 2026-11-13).
 *
 * **Every age is measured on this device's clock.** A frame's arrival time,
 * not the server's `at_ms`, is what each age counts from, so a phone whose
 * clock is a minute off cannot print a fresh price as stale or a stale one as
 * fresh.
 */

/** One market's top of book, as the server sent it. */
export interface LiveBook {
  ticker: string;
  yes_ask_tenths: number | null;
  yes_ask_display: string | null;
  no_ask_tenths: number | null;
  no_ask_display: string | null;
  yes_bid_tenths: number | null;
  yes_bid_display: string | null;
  no_bid_tenths: number | null;
  no_bid_display: string | null;
  yes_depth_at_ask: number | null;
  no_depth_at_ask: number | null;
  /** True when that price is `null` because a level rests there at a price
   *  finer than a tenth of a cent, which the desk will not round (review
   *  D7). `null` with this false means nothing rests there. */
  yes_bid_unpriced?: boolean;
  no_bid_unpriced?: boolean;
  yes_ask_unpriced?: boolean;
  no_ask_unpriced?: boolean;
  observed_ms: number | null;
}

export interface LiveState {
  books: Record<string, LiveBook>;
  /** When each book was last confirmed current: a `book` frame, or a
   *  heartbeat that listed it as valid. Local clock. */
  confirmedMs: Record<string, number>;
  /** When any frame at all last arrived. Local clock. */
  lastFrameMs: number | null;
  /** The server's reason the feed is down, or `null`. */
  down: string | null;
}

export type FeedStatus = "connecting" | "live" | "silent" | "down";

/** No frame of any kind for this long means the feed is silent: treat every
 *  price as frozen. The server heartbeats every 10 s, so 25 s is two missed
 *  beats and a margin — the rule ADR 0119 records for the Board. */
export const SILENT_MS = 25_000;

/** One page may watch at most this many markets: `MAX_WATCHED_PER_CLIENT` in
 *  `backend/live.py`, pinned equal by `tests/test_live_books_client.py`. Past
 *  it the server refuses the whole request, so the hook watches the first
 *  this-many tickers (sorted) and the rest show no live line. */
export const MAX_WATCHED_PER_PAGE = 40;

export const EMPTY_STATE: LiveState = {
  books: {},
  confirmedMs: {},
  lastFrameMs: null,
  down: null,
};

type Frame = {
  type?: unknown;
  books?: unknown;
  valid?: unknown;
  down?: unknown;
  reason?: unknown;
  ticker?: unknown;
};

function confirm(
  confirmed: Record<string, number>,
  tickers: unknown,
  at: number,
): Record<string, number> {
  if (!Array.isArray(tickers)) return confirmed;
  const next = { ...confirmed };
  for (const t of tickers) if (typeof t === "string") next[t] = at;
  return next;
}

function asBook(raw: unknown): LiveBook | null {
  if (!raw || typeof raw !== "object") return null;
  const b = raw as Record<string, unknown>;
  return typeof b.ticker === "string" ? (b as unknown as LiveBook) : null;
}

/** Fold one server frame into the state. `receivedMs` is this device's clock. */
export function applyFrame(
  state: LiveState,
  frame: unknown,
  receivedMs: number,
): LiveState {
  if (!frame || typeof frame !== "object") return state;
  const f = frame as Frame;
  const base = { ...state, lastFrameMs: receivedMs };
  switch (f.type) {
    case "books_snapshot": {
      const books = { ...state.books };
      if (Array.isArray(f.books)) {
        for (const raw of f.books) {
          const book = asBook(raw);
          if (book) books[book.ticker] = book;
        }
      }
      return {
        ...base,
        books,
        confirmedMs: confirm(state.confirmedMs, f.valid, receivedMs),
        down: typeof f.down === "string" ? f.down : null,
      };
    }
    case "book": {
      const book = asBook(frame);
      if (!book) return base;
      return {
        ...base,
        books: { ...state.books, [book.ticker]: book },
        confirmedMs: { ...state.confirmedMs, [book.ticker]: receivedMs },
      };
    }
    case "heartbeat":
      return {
        ...base,
        confirmedMs: confirm(state.confirmedMs, f.valid, receivedMs),
        down: typeof f.down === "string" ? f.down : null,
      };
    case "up":
      return { ...base, down: null };
    case "down":
      return { ...base, down: typeof f.reason === "string" ? f.reason : "the feed is down" };
    default:
      return base;
  }
}

export function feedStatus(state: LiveState, nowMs: number): FeedStatus {
  if (state.lastFrameMs === null) return "connecting";
  if (state.down !== null) return "down";
  if (nowMs - state.lastFrameMs > SILENT_MS) return "silent";
  return "live";
}

/** Milliseconds since `ticker`'s book was last confirmed current, or `null`
 *  when it never has been. Clamped at zero. */
export function bookAgeMs(
  state: LiveState,
  ticker: string,
  nowMs: number,
): number | null {
  const at = state.confirmedMs[ticker];
  return at === undefined ? null : Math.max(0, nowMs - at);
}

/** The live ask for one side, or `null`. */
export function liveAsk(
  book: LiveBook | undefined,
  side: "yes" | "no",
): { tenths: number; display: string } | null {
  if (!book) return null;
  const tenths = side === "yes" ? book.yes_ask_tenths : book.no_ask_tenths;
  const display = side === "yes" ? book.yes_ask_display : book.no_ask_display;
  return tenths === null || display === null ? null : { tenths, display };
}

/** Whether the book's ask has moved away from the one the ticket was priced
 *  at. `null` when either is unknown or they agree. */
export function askMoved(
  pinnedTenths: number | null,
  live: { tenths: number } | null,
): { from: number; to: number } | null {
  if (pinnedTenths === null || live === null) return null;
  return live.tenths === pinnedTenths ? null : { from: pinnedTenths, to: live.tenths };
}

/** Combination (KXMVE) books are empty between RFQs by design (ADR 0164), so
 *  a live book for one would only ever say "no ask". They are not watched. */
export function isWatchable(ticker: string | null | undefined): ticker is string {
  return typeof ticker === "string" && ticker.length > 0 && !ticker.startsWith("KXMVE");
}
