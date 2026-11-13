"use client";

import { useEffect, useMemo, useState } from "react";

import { fetchHealth, liveBooksUrl } from "@/lib/api";
import {
  EMPTY_STATE,
  MAX_WATCHED_PER_PAGE,
  applyFrame,
  feedStatus,
  isWatchable,
  type FeedStatus,
  type LiveState,
} from "@/lib/liveBooks";

export type LiveBooks = {
  state: LiveState;
  /** `off`: this instance has no feed (the demo, a keyless copy), or the
   *  server refused the request. Nothing live is shown. */
  status: FeedStatus | "off";
  /** This device's clock, advancing every second so ages tick. */
  now: number;
};

/**
 * Live top of book for `tickers`, or `off`.
 *
 * Opens the stream only when `/api/health` says the feed is running. A
 * browser's `EventSource` retries a failing endpoint on its own, forever and
 * silently, so pointing it at the demo would be a reconnect loop nobody sees.
 * A refused request (422, 429, 503) closes the source, and the hook says `off`
 * rather than retrying.
 */
export function useLiveBooks(tickers: (string | null | undefined)[]): LiveBooks {
  const key = useMemo(
    () =>
      Array.from(new Set(tickers.filter(isWatchable)))
        .sort()
        .slice(0, MAX_WATCHED_PER_PAGE)
        .join(","),
    [tickers],
  );
  const [state, setState] = useState<LiveState>(EMPTY_STATE);
  const [off, setOff] = useState(true);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    setState(EMPTY_STATE);
    setOff(true);
    if (key === "") return;
    let source: EventSource | null = null;
    let cancelled = false;
    fetchHealth()
      .then((health) => {
        if (cancelled || !health.live_quotes_available) return;
        source = new EventSource(liveBooksUrl(key.split(",")));
        setOff(false);
        source.onmessage = (event) => {
          let frame: unknown;
          try {
            frame = JSON.parse(event.data);
          } catch {
            return;
          }
          const received = Date.now();
          setState((s) => applyFrame(s, frame, received));
        };
        source.onerror = () => {
          // CLOSED means the server refused and the browser will not retry;
          // a transient drop leaves it CONNECTING and the silent rule speaks.
          if (source && source.readyState === EventSource.CLOSED) setOff(true);
        };
      })
      .catch(() => {
        if (!cancelled) setOff(true);
      });
    return () => {
      cancelled = true;
      source?.close();
    };
  }, [key]);

  useEffect(() => {
    if (off) return;
    const timer = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, [off]);

  return { state, status: off ? "off" : feedStatus(state, now), now };
}
