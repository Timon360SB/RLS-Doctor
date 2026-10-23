import { readFile } from "node:fs/promises";
import { Ajv2020 } from "ajv/dist/2020.js";
import { fullFormats } from "ajv-formats/dist/formats.js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { createCaptureFetch } from "../src/index.js";
import type { CaptureOptions, DiagnosticEvent } from "../src/index.js";

const ORIGIN = "https://example.supabase.co";
const SECRET = "DO_NOT_PERSIST_SECRET_TOKEN";
const URL_VALUE = "DO_NOT_PERSIST_QUERY_VALUE";
const tick = async (): Promise<void> => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
const config = (events: DiagnosticEvent[], extra: Partial<CaptureOptions> = {}): CaptureOptions => ({
  enabled: true, allowedOrigin: ORIGIN, resources: ["documents"], sink: (event) => { events.push(event); }, ...extra,
});

afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

describe("transparent capture", () => {
  it("is disabled by default and retains original argument count, Promise, response, and this", async () => {
    const response = new Response("private response");
    const promise = Promise.resolve(response);
    const calls: unknown[][] = [];
    const receivers: unknown[] = [];
    const original = function(this: unknown, ...args: Parameters<typeof fetch>): ReturnType<typeof fetch> {
      receivers.push(this); calls.push(args); return promise;
    };
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(original, { sink: (event) => { events.push(event); } });
    const context = { app: true };
    const returned = wrapped.call(context, `${ORIGIN}/rest/v1/documents`);
    expect(returned).toBe(promise);
    expect(await returned).toBe(response);
    expect(calls).toEqual([[`${ORIGIN}/rest/v1/documents`]]);
    expect(receivers[0]).toBe(context);
    expect(events).toEqual([]);
    expect(await response.text()).toBe("private response");
  });

  it("passes original URL and init untouched, and never consumes or clones the response", async () => {
    const body = `[{"sensitive":"${SECRET}"}]`;
    const response = new Response(body, { headers: { "content-range": "0-0/100", "x-private": SECRET } });
    const text = vi.spyOn(response, "text");
    const json = vi.spyOn(response, "json");
    const clone = vi.spyOn(response, "clone");
    const original = vi.fn<typeof fetch>().mockResolvedValue(response);
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(original, config(events));
    const input = new URL(`${ORIGIN}/rest/v1/documents?owner_id=eq.${URL_VALUE}&select=*&order=title.desc&title=ilike.${SECRET}&bad%5Bname%5D=eq.${SECRET}`);
    const init = { headers: { Authorization: `Bearer ${SECRET}`, apikey: SECRET, Cookie: SECRET } };
    expect(await wrapped(input, init)).toBe(response);
    await tick();
    expect(original.mock.calls[0]?.[0]).toBe(input);
    expect(original.mock.calls[0]?.[1]).toBe(init);
    expect(response.bodyUsed).toBe(false);
    expect(text).not.toHaveBeenCalled();
    expect(json).not.toHaveBeenCalled();
    expect(clone).not.toHaveBeenCalled();
    expect(events).toHaveLength(1);
    expect(events[0]?.request.filters).toEqual([{ column: "owner_id", operator: "eq" }]);
    expect(events[0]?.context).toEqual({ authorization_present: true, apikey_present: true });
    expect(events[0]?.response).toEqual({ status: 200, row_count: 1, error_kind: null });
    const serialized = JSON.stringify(events);
    for (const value of [SECRET, URL_VALUE, ORIGIN, "Bearer", "Cookie", "x-private", "sensitive"]) expect(serialized).not.toContain(value);
  });

  it("honors Request method and complete init header replacement without touching the Request", async () => {
    const request = new Request(`${ORIGIN}/rest/v1/documents`, { method: "POST", headers: { Authorization: SECRET }, body: SECRET });
    const events: DiagnosticEvent[] = [];
    const original = vi.fn<typeof fetch>().mockResolvedValue(new Response("[]"));
    const wrapped = createCaptureFetch(original, config(events));
    const init = { method: "GET", headers: new Headers({ apikey: SECRET }) };
    await wrapped(request, init);
    await tick();
    expect(original.mock.calls[0]?.[0]).toBe(request);
    expect(original.mock.calls[0]?.[1]).toBe(init);
    expect(request.bodyUsed).toBe(false);
    expect(events[0]?.context).toEqual({ authorization_present: false, apikey_present: true });
    await wrapped(new Request(`${ORIGIN}/rest/v1/documents`, { headers: { Authorization: SECRET } }), { headers: [] });
    await tick();
    expect(events[1]?.context).toEqual({ authorization_present: false, apikey_present: false });
    await wrapped(new Request(`${ORIGIN}/rest/v1/documents`, { headers: { aPiKeY: SECRET } }));
    await tick();
    expect(events[2]?.context.apikey_present).toBe(true);
  });

  it("captures mixed-case header names and GET method without reading record values", async () => {
    const headers = Object.create(null) as Record<string, string>;
    Object.defineProperty(headers, "aUtHoRiZaTiOn", { enumerable: true, get: () => { throw new Error(SECRET); } });
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(new Response()), config(events));
    await wrapped(`${ORIGIN}/rest/v1/documents`, { method: "get", headers });
    await tick();
    expect(events[0]?.context.authorization_present).toBe(true);
  });

  it("preserves HTTP errors and network exception identity without capturing the message or error body", async () => {
    const events: DiagnosticEvent[] = [];
    const response = new Response(SECRET, { status: 403 });
    const error = new Error(`Fetch failed: ${ORIGIN}?token=${SECRET}`);
    const original = vi.fn<typeof fetch>().mockResolvedValueOnce(response).mockRejectedValueOnce(error);
    const wrapped = createCaptureFetch(original, config(events));
    expect(await wrapped(`${ORIGIN}/rest/v1/documents`)).toBe(response);
    await expect(wrapped(`${ORIGIN}/rest/v1/documents`)).rejects.toBe(error);
    await tick();
    expect(events.map((event) => event.response)).toEqual([
      { status: 403, row_count: null, error_kind: "http" },
      { status: null, row_count: null, error_kind: "network" },
    ]);
    expect(JSON.stringify(events)).not.toContain(SECRET);
    expect(response.bodyUsed).toBe(false);
  });

  it("preserves a custom fetch synchronous exception", () => {
    const error = new Error(SECRET);
    const original: typeof fetch = () => { throw error; };
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(original, config(events));
    expect(() => wrapped(`${ORIGIN}/rest/v1/documents`)).toThrow(error);
    expect(events[0]?.response.error_kind).toBe("network");
  });
});

describe("capture boundaries", () => {
  it.each([
    ["https://other.supabase.co/rest/v1/documents", undefined],
    [`${ORIGIN}/rest/v1/other`, undefined],
    [`${ORIGIN}/rest/v1/rpc/procedure`, undefined],
    [`${ORIGIN}/auth/v1/user`, undefined],
    [`${ORIGIN}/rest/v1/documents/private`, undefined],
    [`${ORIGIN}/rest/v1/%64ocuments`, undefined],
    [`https://user:${SECRET}@example.supabase.co/rest/v1/documents`, undefined],
    ["/rest/v1/documents", undefined],
    [`${ORIGIN}/rest/v1/documents`, { method: "HEAD" }],
    [`${ORIGIN}/rest/v1/documents`, { method: "POST", body: SECRET }],
  ] as const)("does not capture unsupported request %s", async (input, init) => {
    const events: DiagnosticEvent[] = [];
    const original = vi.fn<typeof fetch>().mockResolvedValue(new Response());
    await createCaptureFetch(original, config(events))(input, init);
    await tick();
    expect(original).toHaveBeenCalledOnce();
    expect(events).toEqual([]);
  });

  it("does not consume a custom header iterable or capture malformed runtime methods", async () => {
    const iterate = vi.fn(function* () { yield ["Authorization", SECRET]; });
    const headers = { [Symbol.iterator]: iterate } as unknown as HeadersInit;
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(new Response()), config(events));
    await wrapped(`${ORIGIN}/rest/v1/documents`, { headers });
    await wrapped(`${ORIGIN}/rest/v1/documents`, { method: null } as unknown as RequestInit);
    await tick();
    expect(iterate).not.toHaveBeenCalled();
    expect(events).toEqual([]);
  });

  it("requires explicit valid origin/resources/sink and sanitizes configuration errors", () => {
    const original = vi.fn<typeof fetch>();
    for (const extra of [
      { allowedOrigin: undefined }, { allowedOrigin: `${ORIGIN}/path?token=${SECRET}` },
      { allowedOrigin: `https://u:${SECRET}@example.supabase.co` }, { allowedOrigin: "file:///tmp" },
      { resources: [] }, { resources: ["rpc"] }, { resources: [SECRET + ".table"] }, { sink: undefined },
      { maxEvents: 0 }, { maxEvents: Infinity }, { maxDurationMs: -1 },
    ]) {
      let message = "";
      try { createCaptureFetch(original, { ...config([]), ...extra } as CaptureOptions); }
      catch (error: unknown) { message = error instanceof Error ? error.message : ""; }
      expect(message.length).toBeGreaterThan(0);
      expect(message).not.toContain(SECRET);
    }
  });

  it("caps event admission including pending requests, expires pending captures, and supports stop", async () => {
    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    const events: DiagnosticEvent[] = [];
    let resolve: ((response: Response) => void) | undefined;
    const promise = new Promise<Response>((done) => { resolve = done; });
    const original = vi.fn<typeof fetch>().mockReturnValue(promise);
    const wrapped = createCaptureFetch(original, config(events, { maxEvents: 2, maxDurationMs: 10 }));
    const requests = Array.from({ length: 5 }, () => wrapped(`${ORIGIN}/rest/v1/documents`));
    resolve?.(new Response());
    await Promise.all(requests);
    await tick();
    expect(events).toHaveLength(2);
    expect(original).toHaveBeenCalledTimes(5);
    const expired = createCaptureFetch(original, config(events, { maxDurationMs: 10 }));
    now = 11;
    await expired(`${ORIGIN}/rest/v1/documents`);
    await tick();
    expect(events).toHaveLength(2);
    const stopped = createCaptureFetch(original, config(events));
    const result = stopped(`${ORIGIN}/rest/v1/documents`);
    stopped.stop();
    await result;
    await stopped(`${ORIGIN}/rest/v1/documents`);
    await tick();
    expect(events).toHaveLength(2);
  });

  it("drops an in-flight event completing after the time window", async () => {
    let now = 0;
    vi.spyOn(performance, "now").mockImplementation(() => now);
    let done: ((response: Response) => void) | undefined;
    const promise = new Promise<Response>((resolve) => { done = resolve; });
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(() => promise, config(events, { maxDurationMs: 10 }));
    const result = wrapped(`${ORIGIN}/rest/v1/documents`);
    now = 20;
    done?.(new Response());
    await result;
    await tick();
    expect(events).toEqual([]);
  });

  it("bounds normalized filters and rejects unsupported operators without recording values", async () => {
    const query = new URLSearchParams();
    for (let i = 0; i < 100; i++) query.append(`field_${i}`, `eq.${SECRET}`);
    query.append("field", `not.eq.${SECRET}`);
    const events: DiagnosticEvent[] = [];
    await createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(new Response()), config(events))(`${ORIGIN}/rest/v1/documents?${query}`);
    await tick();
    expect(events[0]?.request.filters).toHaveLength(64);
    expect(JSON.stringify(events)).not.toContain(SECRET);
  });

  it.each([
    ["0-9/100", 10], ["10-14/*", 5], ["*/0", 0], ["*/100", null], ["0-9/9", null],
    ["9-0/100", null], ["0-9007199254740992/*", null], ["0-9007199254740991/*", null], ["rows 0-1/3", null], ["secret", null],
  ])("infers returned range length only for valid Content-Range %s", async (range, expected) => {
    const events: DiagnosticEvent[] = [];
    await createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(new Response("[]", { headers: { "content-range": range } })), config(events))(`${ORIGIN}/rest/v1/documents`);
    await tick();
    expect(events[0]?.response.row_count).toBe(expected);
  });
});

describe("diagnostic failure isolation and schema contract", () => {
  it.each(["throw", "reject", "never"] as const)("isolates a sink that can %s", async (kind) => {
    const callback = vi.fn((code: string) => { expect(code).toBe("sink_failed"); throw new Error(SECRET); });
    const response = new Response();
    const sink = (): Promise<void> => {
      if (kind === "throw") throw new Error(SECRET);
      if (kind === "reject") return Promise.reject(new Error(SECRET));
      return new Promise<void>(() => undefined);
    };
    const wrapped = createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(response), config([], { sink, onDiagnosticError: callback }));
    expect(await wrapped(`${ORIGIN}/rest/v1/documents`)).toBe(response);
    await tick();
    expect(callback).toHaveBeenCalledTimes(kind === "never" ? 0 : 1);
  });

  it("handles rejecting error callbacks and metadata errors without exposing the raw exception", async () => {
    const response = new Response();
    vi.spyOn(response.headers, "get").mockImplementation(() => { throw new Error(SECRET); });
    const callback = vi.fn(() => Promise.reject(new Error(SECRET)));
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(response), config(events, { onDiagnosticError: callback }));
    expect(await wrapped(`${ORIGIN}/rest/v1/documents`)).toBe(response);
    await tick();
    expect(callback).toHaveBeenCalledWith("metadata_failed");
    expect(events).toEqual([]);
  });

  it("validates a real producer event against canonical JSON Schema draft 2020-12", async () => {
    const events: DiagnosticEvent[] = [];
    const wrapped = createCaptureFetch(vi.fn<typeof fetch>().mockResolvedValue(new Response("[]", { headers: { "content-range": "*/0" } })), config(events));
    await wrapped(`${ORIGIN}/rest/v1/documents?id=eq.${URL_VALUE}`, { headers: [["Authorization", SECRET]] });
    await tick();
    const schema: unknown = JSON.parse(await readFile(new URL("../../../schemas/diagnostic-event-v1.schema.json", import.meta.url), "utf8"));
    const ajv = new Ajv2020({ strict: true, allErrors: true, formats: fullFormats });
    const validate = ajv.compile(schema as object);
    expect(validate(events[0]), JSON.stringify(validate.errors)).toBe(true);
    expect(validate({ ...events[0], schema_version: "2.0" })).toBe(false);
    expect(validate({ ...events[0], body: SECRET })).toBe(false);
    expect(Object.isFrozen(events[0])).toBe(true);
    expect(Object.isFrozen(events[0]?.request.filters)).toBe(true);
  });
});
