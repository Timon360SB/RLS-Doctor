import type { DiagnosticEvent, FilterOperator } from "./types.js";

export const IDENTIFIER = /^[a-zA-Z_][a-zA-Z0-9_]{0,62}$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
export const OPERATORS = new Set<string>(["eq", "neq", "gt", "gte", "lt", "lte", "is"]);

export function boundedInteger(value: number | undefined, fallback: number, maximum: number): number {
  const result = value ?? fallback;
  if (!Number.isSafeInteger(result) || result < 1 || result > maximum) {
    throw new TypeError("Capture limit must be a positive integer within the documented range.");
  }
  return result;
}

/** Rebuild an allowlisted event before disk serialization, excluding arbitrary extra properties. */
export function eventSnapshot(event: DiagnosticEvent): DiagnosticEvent {
  const fail = (): never => { throw new TypeError("Capture event does not match schema v1."); };
  if (!["1.0", "1.1"].includes(event.schema_version) || typeof event.event_id !== "string" || !UUID.test(event.event_id) ||
      typeof event.timestamp !== "string" || !ISO_DATE.test(event.timestamp) || !Number.isFinite(Date.parse(event.timestamp)) ||
      new Date(event.timestamp).toISOString() !== event.timestamp ||
      !Number.isInteger(event.duration_ms) || event.duration_ms < 0 || event.duration_ms > 86_400_000 ||
      event.request.method !== "GET" || event.request.api !== "rest" || typeof event.request.resource !== "string" || !IDENTIFIER.test(event.request.resource) ||
      !Array.isArray(event.request.filters) || event.request.filters.length > 64 ||
      typeof event.context.authorization_present !== "boolean" || typeof event.context.apikey_present !== "boolean") fail();
  const status = event.response.status;
  const count = event.response.row_count;
  const kind = event.response.error_kind;
  if ((status !== null && (!Number.isInteger(status) || status < 100 || status > 599)) ||
      (count !== null && (!Number.isSafeInteger(count) || count < 0)) ||
      (kind !== null && kind !== "http" && kind !== "network")) fail();
  const filters = event.request.filters.map((filter) => {
    if (typeof filter.column !== "string" || !IDENTIFIER.test(filter.column) || !OPERATORS.has(filter.operator)) fail();
    return Object.freeze({ column: filter.column, operator: filter.operator as FilterOperator });
  });
  let bound: Pick<DiagnosticEvent, "binding" | "auth_check"> = {};
  let requestFields: Pick<DiagnosticEvent["request"], "schema" | "columns"> = {};
  if (event.schema_version === "1.1") {
    const b = event.binding;
    const schema = event.request.schema;
    const columns = event.request.columns;
    if (!b || !UUID.test(b.project_id) || !/^[0-9a-f]{64}$/.test(b.origin_sha256) ||
        typeof schema !== "string" || !IDENTIFIER.test(schema) ||
        !(columns === null || Array.isArray(columns) && columns.length <= 64 &&
          new Set(columns).size === columns.length && columns.every(c => typeof c === "string" && IDENTIFIER.test(c))) ||
        !["not_checked", "no_authorization", "verified_user", "rejected", "unavailable"].includes(event.auth_check ?? "")) fail();
    bound = { binding: Object.freeze({ project_id: b!.project_id, origin_sha256: b!.origin_sha256 }), auth_check: event.auth_check! };
    requestFields = { schema: schema!, columns: columns === null ? null : Object.freeze([...columns!]) };
  }
  return Object.freeze({
    ...bound,
    schema_version: event.schema_version,
    event_id: event.event_id,
    timestamp: event.timestamp,
    duration_ms: event.duration_ms,
    request: Object.freeze({ method: "GET", api: "rest", resource: event.request.resource, ...requestFields, filters: Object.freeze(filters) }),
    response: Object.freeze({ status, row_count: count, error_kind: kind }),
    context: Object.freeze({ authorization_present: event.context.authorization_present, apikey_present: event.context.apikey_present }),
  });
}
