import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { Ajv2020 } from "ajv/dist/2020.js";
import { fullFormats } from "ajv-formats/dist/formats.js";
import { describe, expect, it, vi } from "vitest";
import { createCaptureFetch } from "../src/index.js";
import type { DiagnosticEvent } from "../src/index.js";

const origin = "https://app.example.com";
const projectId = "00000000-0000-4000-8000-000000000001";
const secret = "PRIVATE_BEARER_NOT_IN_EVENT";

async function capture(authStatus = 200, userBody: unknown = { id: projectId }): Promise<DiagnosticEvent> {
  let done!: (event: DiagnosticEvent) => void;
  const event = new Promise<DiagnosticEvent>(resolve => { done = resolve; });
  const application = new Response("PRIVATE_ROWS", { headers: { "content-range": "*/0" } });
  const original = vi.fn<typeof fetch>().mockImplementation(async input => {
    if (String(input).endsWith("/auth/v1/user")) return new Response(JSON.stringify(userBody), { status: authStatus });
    return application;
  });
  const wrapper = createCaptureFetch(original, { enabled: true, projectId, allowedOrigin: origin,
    resources: ["documents"], verifyAuth: true, sink: done });
  const promise = wrapper(`${origin}/rest/v1/documents?select=id,owner_id&owner_id=eq.PRIVATE_FILTER`, {
    headers: { Authorization: `Bearer ${secret}`, apikey: "PRIVATE_API_KEY", "Accept-Profile": "private" },
  });
  expect(await promise).toBe(application);
  expect(application.bodyUsed).toBe(false);
  const result = await event;
  expect(original).toHaveBeenCalledTimes(2);
  const auth = original.mock.calls[1];
  expect(auth?.[0]).toBe(`${origin}/auth/v1/user`);
  expect(auth?.[1]?.redirect).toBe("error");
  expect(auth?.[1]?.signal).toBeInstanceOf(AbortSignal);
  for (const value of [secret, "PRIVATE_API_KEY", "PRIVATE_FILTER", "PRIVATE_ROWS"]) {
    expect(JSON.stringify(result)).not.toContain(value);
  }
  return result;
}

describe("bound application capture", () => {
  it("binds API/schema/projection, validates schema 1.1 and checks Auth separately", async () => {
    const event = await capture();
    expect(event.schema_version).toBe("1.1");
    expect(event.binding).toEqual({ project_id: projectId, origin_sha256: createHash("sha256").update(origin).digest("hex") });
    expect(event.request.schema).toBe("private");
    expect(event.request.columns).toEqual(["id", "owner_id"]);
    expect(event.auth_check).toBe("verified_user");
    const schema: unknown = JSON.parse(await readFile(new URL("../../../schemas/diagnostic-event-v1.1.schema.json", import.meta.url), "utf8"));
    const validate = new Ajv2020({ strict: true, allErrors: true, formats: fullFormats }).compile(schema as object);
    expect(validate(event)).toBe(true);
    expect(validate({ ...event, binding: { ...event.binding, token: secret } })).toBe(false);
  });
  it("records rejected sessions without inventing an executed role", async () => {
    expect((await capture(401)).auth_check).toBe("rejected");
  });
  it("does not treat an arbitrary JSON body as verified identity", async () => {
    expect((await capture(200, { message: secret })).auth_check).toBe("unavailable");
  });
  it("bounds Auth response reads", async () => {
    expect((await capture(200, { id: projectId, oversized: "x".repeat(40000) })).auth_check).toBe("unavailable");
  });
  it("does not add an Auth request when verification is disabled", async () => {
    const events: DiagnosticEvent[] = [];
    const original = vi.fn<typeof fetch>().mockResolvedValue(new Response("[]"));
    const wrapper = createCaptureFetch(original, { enabled: true, projectId, allowedOrigin: origin,
      resources: ["documents"], sink: event => { events.push(event); } });
    await wrapper(`${origin}/rest/v1/documents`);
    expect(events[0]?.auth_check).toBe("not_checked");
    expect(events[0]?.request.columns).toBeNull();
    expect(original).toHaveBeenCalledTimes(1);
  });
  it("isolates failed Auth checks from the original Promise and response", async () => {
    let done!: (event: DiagnosticEvent) => void;
    const event = new Promise<DiagnosticEvent>(resolve => { done = resolve; });
    const response = new Response("PRIVATE_ROWS");
    const promise = Promise.resolve(response);
    const original: typeof fetch = input => String(input).endsWith("/auth/v1/user") ? Promise.reject(new Error(secret)) : promise;
    const wrapper = createCaptureFetch(original, { enabled: true, projectId, allowedOrigin: origin,
      resources: ["documents"], verifyAuth: true, sink: done });
    const returned = wrapper(`${origin}/rest/v1/documents`, { headers: { authorization: `Bearer ${secret}`, apikey: "private" } });
    expect(returned).toBe(promise);
    expect(await returned).toBe(response);
    expect((await event).auth_check).toBe("unavailable");
    expect(response.bodyUsed).toBe(false);
    expect(JSON.stringify(await event)).not.toContain(secret);
  });
  it("does not contact Auth without an authorization header", async () => {
    const events: DiagnosticEvent[] = [];
    const original = vi.fn<typeof fetch>().mockResolvedValue(new Response("[]"));
    const wrapper = createCaptureFetch(original, { enabled: true, projectId, allowedOrigin: origin,
      resources: ["documents"], verifyAuth: true, sink: e => { events.push(e); } });
    await wrapper(`${origin}/rest/v1/documents`);
    await vi.waitFor(() => expect(events).toHaveLength(1));
    expect(events[0]?.auth_check).toBe("no_authorization");
    expect(original).toHaveBeenCalledTimes(1);
  });
  it("rejects insecure Auth destinations and invalid project IDs before capture", () => {
    const base = { enabled: true, projectId, allowedOrigin: "http://example.com", resources: ["documents"], sink: () => undefined };
    expect(() => createCaptureFetch(fetch, { ...base, verifyAuth: true })).toThrow();
    expect(() => createCaptureFetch(fetch, { ...base, projectId: secret })).toThrow();
  });
});
