export type FilterOperator = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "is";

/** Only metadata allowed by schemas/diagnostic-event-v1.schema.json. */
export interface DiagnosticEvent {
  readonly schema_version: "1.0" | "1.1";
  readonly event_id: string;
  readonly timestamp: string;
  readonly duration_ms: number;
  readonly binding?: { readonly project_id: string; readonly origin_sha256: string };
  readonly auth_check?: "not_checked" | "no_authorization" | "verified_user" | "rejected" | "unavailable";
  readonly request: {
    readonly method: "GET";
    readonly api: "rest";
    readonly resource: string;
    readonly schema?: string;
    readonly columns?: readonly string[] | null;
    readonly filters: readonly { readonly column: string; readonly operator: FilterOperator }[];
  };
  readonly response: {
    readonly status: number | null;
    readonly row_count: number | null;
    readonly error_kind: "http" | "network" | null;
  };
  readonly context: {
    readonly authorization_present: boolean;
    readonly apikey_present: boolean;
  };
}

export type CaptureSink = (event: DiagnosticEvent) => void | Promise<void>;
export type DiagnosticErrorCode = "metadata_failed" | "sink_failed";

export interface CaptureOptions {
  /** Non-secret UUID copied from a saved database profile. Enables schema 1.1. */
  readonly projectId?: string;
  /** Explicit extra Auth GET with the same request headers; never persists tokens or user IDs. */
  readonly verifyAuth?: boolean;
  /** Capture is disabled unless explicitly true. */
  readonly enabled?: boolean;
  /** Exact HTTP(S) origin; paths, credentials, query strings and fragments are rejected. */
  readonly allowedOrigin?: string;
  /** Exact simple table/view names. RPC and nested paths are always unsupported. */
  readonly resources?: readonly string[];
  /** A local callback. Nothing is sent anywhere unless this callback does so. */
  readonly sink?: CaptureSink;
  /** Receives only fixed codes, never request data or exception messages. */
  readonly onDiagnosticError?: (code: DiagnosticErrorCode) => void | Promise<void>;
  /** Maximum capture attempts, including in-flight requests. Default 100, at most 10000. */
  readonly maxEvents?: number;
  /** Capture window, including request completion, in milliseconds. Default 300000, at most 86400000. */
  readonly maxDurationMs?: number;
}

export type CaptureFetch = typeof fetch & {
  /** Permanently stop new captures and discard pending capture results. Requests continue normally. */
  stop(): void;
};

export interface JsonFileSinkOptions {
  /** A dedicated local directory. Existing files count toward both limits. */
  readonly directory: string;
  readonly maxEvents?: number;
  readonly maxBytes?: number;
}
