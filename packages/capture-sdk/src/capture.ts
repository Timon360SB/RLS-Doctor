import { createHash, randomUUID } from "node:crypto";
import { checkAuth } from "./auth.js";
import { boundedInteger, eventSnapshot, IDENTIFIER, OPERATORS } from "./event.js";
import type { CaptureFetch, CaptureOptions, DiagnosticErrorCode, DiagnosticEvent, FilterOperator } from "./types.js";

const RESERVED_QUERY_KEYS = new Set(["select", "order", "limit", "offset", "and", "or", "on_conflict"]);

interface PendingCapture {
  readonly started: number;
  readonly timestamp: string;
  readonly resource: string;
  readonly filters: DiagnosticEvent["request"]["filters"];
  readonly context: DiagnosticEvent["context"];
  readonly schema?: string;
  readonly columns?: readonly string[] | null;
  readonly authHeaders?: Headers;
}

function originOption(value: string | undefined): string {
  try {
    if (value === undefined) throw new Error();
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        url.pathname !== "/" || url.search || url.hash) throw new Error();
    return url.origin;
  } catch { throw new TypeError("Enabled capture requires a valid exact HTTP(S) origin."); }
}

/** Inspect names only. Do not read header values or consume custom iterables. */
function headerPresence(headers: HeadersInit | undefined): DiagnosticEvent["context"] | null {
  if (headers === undefined || headers === null) return { authorization_present: false, apikey_present: false };
  if (headers instanceof Headers) return {
    authorization_present: headers.has("authorization"), apikey_present: headers.has("apikey"),
  };
  let names: string[];
  if (Array.isArray(headers)) {
    names = [];
    for (const pair of headers) {
      if (!Array.isArray(pair) || typeof pair[0] !== "string") return null;
      names.push(pair[0].toLowerCase());
    }
  } else {
    if (Symbol.iterator in headers) return null;
    const prototype: unknown = Object.getPrototypeOf(headers);
    if (prototype !== Object.prototype && prototype !== null) return null;
    names = Object.keys(headers).map((name) => name.toLowerCase());
  }
  return { authorization_present: names.includes("authorization"), apikey_present: names.includes("apikey") };
}

function metadata(args: Parameters<typeof fetch>, origin: string, resources: ReadonlySet<string>, bound: boolean, verifyAuth: boolean): PendingCapture | null {
  const [input, init] = args;
  const request = input instanceof Request ? input : null;
  const overrideMethod = init?.method;
  const method = overrideMethod !== undefined ? overrideMethod : request?.method ?? "GET";
  if (typeof method !== "string" || method.toUpperCase() !== "GET") return null;
  const raw = request?.url ?? (typeof input === "string" ? input : input instanceof URL ? input.href : null);
  if (raw === null || raw.length > 16_384) return null;
  const url = new URL(raw);
  if (url.origin !== origin || url.username || url.password) return null;
  const match = /^\/rest\/v1\/([a-zA-Z_][a-zA-Z0-9_]{0,62})\/?$/.exec(url.pathname);
  const resource = match?.[1];
  if (resource === undefined || resource === "rpc" || !resources.has(resource)) return null;
  const overrideHeaders = init?.headers;
  const headers = overrideHeaders === undefined ? request?.headers : overrideHeaders;
  const context = headerPresence(headers);
  if (context === null) return null;
  const filters: { column: string; operator: FilterOperator }[] = [];
  let inspected = 0;
  for (const [column, value] of url.searchParams) {
    if (++inspected > 256 || filters.length === 64) break;
    if (!IDENTIFIER.test(column) || RESERVED_QUERY_KEYS.has(column)) continue;
    const separator = value.indexOf(".");
    if (separator < 0) continue;
    const operator = value.slice(0, separator);
    if (OPERATORS.has(operator)) filters.push({ column, operator: operator as FilterOperator });
  }
  let schema: string | undefined;
  let columns: readonly string[] | null | undefined;
  let authHeaders: Headers | undefined;
  if (bound) {
    const normalized = new Headers(headers);
    schema = normalized.get("accept-profile") ?? "public";
    if (!IDENTIFIER.test(schema)) return null;
    const projection = url.searchParams.get("select");
    const parts = projection?.split(",");
    columns = parts && parts.length <= 64 && parts.every(c => IDENTIFIER.test(c)) ? [...new Set(parts)] : null;
    if (verifyAuth) authHeaders = normalized;
  }
  return { started: performance.now(), timestamp: new Date().toISOString(), resource, filters, context,
    ...(schema === undefined ? {} : { schema, columns: columns ?? null }),
    ...(authHeaders === undefined ? {} : { authHeaders }) };

}

function rowCount(response: Response): number | null {
  const range = response.headers.get("content-range");
  if (range === null) return null;
  if (range === "*/0") return 0;
  const match = /^(\d+)-(\d+)\/(\d+|\*)$/.exec(range);
  if (!match) return null;
  const start = Number(match[1]);
  const end = Number(match[2]);
  const total = match[3] === "*" ? null : Number(match[3]);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end < start ||
      (total !== null && (!Number.isSafeInteger(total) || total <= end))) return null;
  const count = end - start + 1;
  return Number.isSafeInteger(count) ? count : null;
}

/** Wrap a supplied fetch without changing its arguments, returned Promise, response, or failure. */
export function createCaptureFetch(fetchImpl: typeof fetch, options: CaptureOptions = {}): CaptureFetch {
  if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required.");
  const enabled = options.enabled === true;
  const origin = enabled ? originOption(options.allowedOrigin) : "";
  const bound = enabled && options.projectId !== undefined;
  if (bound && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(options.projectId ?? "")) {
    throw new TypeError("Project binding requires a non-secret UUID.");
  }
  if (enabled && options.verifyAuth && (!bound || !(origin.startsWith("https://") || /^http:\/\/(127(?:\.\d{1,3}){3}|\[::1\])(?::\d+)?$/.test(origin)))) {
    throw new TypeError("Auth verification requires a project binding and HTTPS (numeric loopback excepted).");
  }
  const resources = new Set(options.resources ?? []);
  if (enabled && (resources.size === 0 || [...resources].some((name) => !IDENTIFIER.test(name) || name === "rpc") ||
      typeof options.sink !== "function")) {
    throw new TypeError("Enabled capture requires simple resource names and a sink.");
  }
  const maxEvents = boundedInteger(options.maxEvents, 100, 10_000);
  const maxDuration = boundedInteger(options.maxDurationMs, 300_000, 86_400_000);
  const deadline = performance.now() + maxDuration;
  let stopped = !enabled;
  let accepted = 0;

  const diagnosticError = (code: DiagnosticErrorCode): void => {
    try { void Promise.resolve(options.onDiagnosticError?.(code)).catch(() => undefined); } catch { /* Never affect the application. */ }
  };
  const emit = (pending: PendingCapture, response: Response | null, authCheck: DiagnosticEvent["auth_check"], elapsed: number): void => {
    if (stopped || performance.now() > deadline) return;
    let event: DiagnosticEvent;
    try {
      const status = response !== null && response.status >= 100 && response.status <= 599 ? response.status : null;
      event = eventSnapshot({
        schema_version: bound ? "1.1" : "1.0",
        ...(bound ? { binding: { project_id: options.projectId!, origin_sha256: createHash("sha256").update(origin).digest("hex") }, auth_check: authCheck ?? "not_checked" } : {}),
        event_id: randomUUID(), timestamp: pending.timestamp,
        duration_ms: elapsed,
        request: { method: "GET", api: "rest", resource: pending.resource, filters: pending.filters, ...(bound ? { schema: pending.schema!, columns: pending.columns ?? null } : {}) },
        response: { status, row_count: response === null ? null : rowCount(response), error_kind: response === null ? "network" : status !== null && status >= 400 ? "http" : null },
        context: pending.context,
      });
    } catch { diagnosticError("metadata_failed"); return; }
    try { void Promise.resolve(options.sink?.(event)).catch(() => diagnosticError("sink_failed")); }
    catch { diagnosticError("sink_failed"); }
  };
  const complete = (pending: PendingCapture, response: Response | null): void => {
    const elapsed = Math.min(86_400_000, Math.max(0, Math.round(performance.now() - pending.started)));
    if (options.verifyAuth && pending.authHeaders && !stopped && performance.now() <= deadline) {
      void checkAuth(fetchImpl, origin, pending.authHeaders).then(result => emit(pending, response, result, elapsed)).catch(() => emit(pending, response, "unavailable", elapsed));
    } else { emit(pending, response, "not_checked", elapsed); }
  };
  const wrapped = function(this: unknown, ...args: Parameters<typeof fetch>): ReturnType<typeof fetch> {
    let pending: PendingCapture | null = null;
    if (!stopped && accepted < maxEvents && performance.now() <= deadline) {
      try { pending = metadata(args, origin, resources, bound, options.verifyAuth === true); } catch { diagnosticError("metadata_failed"); }
      if (pending !== null) accepted += 1;
    }
    let result: ReturnType<typeof fetch>;
    try { result = Reflect.apply(fetchImpl, this, args) as ReturnType<typeof fetch>; }
    catch (error: unknown) { if (pending !== null) complete(pending, null); throw error; }
    if (pending !== null) {
      const captured = pending;
      try { void result.then((response) => complete(captured, response), () => complete(captured, null)).catch(() => diagnosticError("metadata_failed")); }
      catch { diagnosticError("metadata_failed"); }
    }
    return result;
  } as CaptureFetch;
  wrapped.stop = (): void => { stopped = true; };
  return wrapped;
}
