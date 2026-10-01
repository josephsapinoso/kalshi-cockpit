/**
 * The one place the browser sends a write to the cockpit (ADR 0191).
 *
 * React-free, and imported from `api.ts` by relative path so a node-run test
 * can load it. Reads are out of scope: `get<T>` in `api.ts` is already one
 * helper.
 *
 * **Two sentences are REQUIRED parameters and have no default:** what to say
 * when no reply arrives (`noReply`) and what to say when a reply arrives that
 * cannot be read (`unreadable`). A call that can spend must say the state is
 * unknown; a default would let the next call that forgets to override it tell
 * Joe something false (ADR 0191 §2.3).
 *
 * **No retries, ever.** Nothing here sends a second request (ADR 0164/0165).
 */

/** What every write hands back. `refusal` always comes from `refusalText`. */
export type WriteResult<T> =
  | { ok: true; status: number; value: T }
  | { ok: false; status: number; refusal: string; detail: unknown };

export type WriteOptions<T> = {
  path: string;
  /** Omitted: no body and no Content-Type are sent (`/lockout`). */
  body?: unknown;
  signal?: AbortSignal;
  /**
   * Extra request headers, merged over the JSON Content-Type. Only the engine
   * order path uses it, for its optional bearer (`placeOrder`).
   */
  headers?: Record<string, string>;
  /** The sentence when the request got no reply. REQUIRED, no default. */
  noReply: (error: unknown) => string;
  /** The sentence when a reply cannot be read. REQUIRED, no default. */
  unreadable: (status: number) => string;
  /**
   * The caller's existing success-shape check, kept exactly. A success body
   * that fails it is `unreadable`. Optional: calls that never checked do not
   * start now.
   */
  shape?: (body: unknown) => boolean;
  /** A 2xx whose body is not JSON is a success with `value: null`. */
  tolerateEmptyBody?: boolean;
  /** The words for a JSON refusal that carries no `detail`. */
  noDetail?: (status: number) => string;
};

/** A thrown fetch's own message, for the sentence that wraps it. */
export function networkMessage(error: unknown): string {
  return error instanceof Error ? error.message : "network error";
}

/**
 * A refusal body as text, whatever shape it arrived in.
 *
 * Three shapes reach here and all three are real: FastAPI's plain string, the
 * list of dicts pydantic produces when the request body itself is invalid, and
 * an object. The endpoint's plain-language strings are the useful output and
 * are passed through untouched -- there are a dozen distinct refusals and each
 * one explains itself better than a generic sentence could.
 */
export function refusalText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((entry) => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const item = entry as { loc?: unknown[]; msg?: string };
          const field = Array.isArray(item.loc)
            ? item.loc.filter((p) => p !== "body").join(".")
            : "";
          return field && item.msg ? `${field}: ${item.msg}` : (item.msg ?? "");
        }
        return String(entry);
      })
      .filter(Boolean)
      .join("\n");
  }
  if (detail && typeof detail === "object") {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string") return message;
    return JSON.stringify(detail);
  }
  return "The server refused and gave no reason, which is itself a defect.";
}

export async function postJson<T>(options: WriteOptions<T>): Promise<WriteResult<T>> {
  const {
    path,
    body,
    signal,
    headers,
    noReply,
    unreadable,
    shape,
    tolerateEmptyBody,
    noDetail,
  } = options;
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      ...(body === undefined
        ? headers
          ? { headers }
          : {}
        : {
            headers: { "Content-Type": "application/json", ...(headers ?? {}) },
            body: JSON.stringify(body),
          }),
      cache: "no-store",
      ...(signal ? { signal } : {}),
    });
  } catch (error) {
    return { ok: false, status: 0, refusal: noReply(error), detail: null };
  }

  const parsed: unknown = await response.json().catch(() => null);
  const status = response.status;

  if (response.ok) {
    if (parsed === null && tolerateEmptyBody) {
      return { ok: true, status, value: null as T };
    }
    if (parsed === null || (shape && !shape(parsed))) {
      return { ok: false, status, refusal: unreadable(status), detail: parsed };
    }
    return { ok: true, status, value: parsed as T };
  }

  if (parsed === null) {
    return { ok: false, status, refusal: unreadable(status), detail: null };
  }
  if (typeof parsed === "object" && "detail" in parsed) {
    const detail = (parsed as { detail: unknown }).detail;
    return { ok: false, status, refusal: refusalText(detail), detail };
  }
  return {
    ok: false,
    status,
    refusal: noDetail ? noDetail(status) : `HTTP ${status}`,
    detail: parsed,
  };
}
