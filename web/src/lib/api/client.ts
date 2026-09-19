/**
 * Typed fetch wrapper for the DyPol backend.
 *
 * - Always sends the session cookie (`credentials: "include"`).
 * - Throws `ApiError` on non-2xx so callers can branch on `.status`.
 * - Reads `NEXT_PUBLIC_API_BASE_URL` from `.env.local`.
 */
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// Module-level "active org" — set by <OrgProvider> on mount and on switch.
// Endpoints that don't take an explicit `org` query param fall back to this.
let _defaultOrg: string | null = null;
export function setDefaultOrg(login: string | null): void {
  _defaultOrg = login;
}
function getDefaultOrg(): string | null {
  return _defaultOrg;
}

export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

interface ApiOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
}

function buildUrl(path: string, query?: ApiOptions["query"]): string {
  const url = new URL(path, API_BASE_URL);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
  }
  // Auto-attach the active org if the caller didn't already supply one.
  // Auth endpoints (/auth/*) skip this — they're org-agnostic.
  if (!url.searchParams.has("org") && !url.pathname.startsWith("/auth")) {
    const fallback = getDefaultOrg();
    if (fallback) url.searchParams.set("org", fallback);
  }
  return url.toString();
}

export async function api<T>(path: string, opts: ApiOptions = {}): Promise<T> {
  const { body, query, headers, ...rest } = opts;
  const init: RequestInit = {
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string> | undefined),
    },
    ...rest,
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  const res = await fetch(buildUrl(path, query), init);
  const text = await res.text();
  const data = text ? safeJson(text) : null;

  if (!res.ok) {
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : undefined) ?? res.statusText;
    throw new ApiError(res.status, detail, data);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

export const apiUrl = (path: string) => buildUrl(path);

/** A parsed Server-Sent Events frame: an `event:` name and its raw `data:` payload. */
export interface SseFrame {
  event: string;
  data: string;
}

interface SseStreamOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  query?: ApiOptions["query"];
}

/**
 * POSTs to an SSE endpoint and yields parsed `{ event, data }` frames as they
 * arrive, reading the raw `ReadableStream` (works with POST, unlike EventSource).
 *
 * Throws `ApiError` on a non-2xx response *before* streaming begins, so callers
 * can branch on `.status` (e.g. fall back to a non-streaming endpoint on 404).
 * Partial frames split across network chunks are buffered until a blank-line
 * frame separator is seen.
 */
export async function* sseStream(
  path: string,
  opts: SseStreamOptions = {},
): AsyncGenerator<SseFrame, void, unknown> {
  const { body, query, headers, signal, ...rest } = opts;
  const init: RequestInit = {
    method: "POST",
    credentials: "include",
    signal,
    headers: {
      Accept: "text/event-stream",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(headers as Record<string, string> | undefined),
    },
    ...rest,
  };
  if (body !== undefined) init.body = JSON.stringify(body);

  const res = await fetch(buildUrl(path, query), init);

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    const data = text ? safeJson(text) : null;
    const detail =
      (data && typeof data === "object" && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : undefined) ?? res.statusText;
    throw new ApiError(res.status, detail, data);
  }
  if (!res.body) {
    throw new ApiError(res.status, "Streaming response had no body", null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // Frames are separated by a blank line. Normalise CRLF first.
      let sep: number;
      while ((sep = indexOfFrameBoundary(buffer)) !== -1) {
        const raw = buffer.slice(0, sep);
        // Advance past the boundary (handles "\n\n" and "\r\n\r\n").
        buffer = buffer.slice(sep).replace(/^(\r?\n){2}/, "");
        const frame = parseSseFrame(raw);
        if (frame) yield frame;
      }
    }
    // Flush any trailing frame that wasn't terminated by a blank line.
    const tail = parseSseFrame(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

/** Index of the first blank-line frame boundary (`\n\n` or `\r\n\r\n`), or -1. */
function indexOfFrameBoundary(buffer: string): number {
  const lf = buffer.indexOf("\n\n");
  const crlf = buffer.indexOf("\r\n\r\n");
  if (lf === -1) return crlf;
  if (crlf === -1) return lf;
  return Math.min(lf, crlf);
}

/** Parse a single SSE frame block into `{ event, data }`, or null if empty. */
function parseSseFrame(block: string): SseFrame | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) continue; // blank or comment
    const idx = line.indexOf(":");
    const field = idx === -1 ? line : line.slice(0, idx);
    // Per spec, strip a single leading space after the colon.
    let val = idx === -1 ? "" : line.slice(idx + 1);
    if (val.startsWith(" ")) val = val.slice(1);
    if (field === "event") event = val;
    else if (field === "data") dataLines.push(val);
  }
  if (dataLines.length === 0 && event === "message") return null;
  return { event, data: dataLines.join("\n") };
}
