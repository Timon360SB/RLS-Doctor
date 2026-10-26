import type { DiagnosticEvent } from "./types.js";

/** Additional opt-in Auth request. Original application response/body is never touched. */
export async function checkAuth(fetchImpl: typeof fetch, origin: string, headers: Headers): Promise<NonNullable<DiagnosticEvent["auth_check"]>> {
  const authorization = headers.get("authorization");
  const apikey = headers.get("apikey");
  if (!authorization) return "no_authorization";
  if (!/^Bearer [^\s]+$/i.test(authorization) || authorization.length > 16384 ||
      !apikey || apikey.length > 16384 || apikey.startsWith("sb_secret_")) return "unavailable";
  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const work = async (): Promise<NonNullable<DiagnosticEvent["auth_check"]>> => {
    const response = await fetchImpl(`${origin}/auth/v1/user`, {
      method: "GET", headers: { authorization, apikey }, redirect: "error", signal: controller.signal,
    });
    if (response.status === 401 || response.status === 403) { await response.body?.cancel(); return "rejected"; }
    if (response.status !== 200 || !response.body) { await response.body?.cancel(); return "unavailable"; }
    const reader = response.body.getReader();
    const cancel = (): void => { void reader.cancel().catch(() => undefined); };
    controller.signal.addEventListener("abort", cancel, { once: true });
    try {
      const chunks: Uint8Array[] = [];
      let size = 0;
      while (true) {
        const next = await reader.read();
        if (next.done) break;
        size += next.value.byteLength;
        if (size > 32768) return "unavailable";
        chunks.push(next.value);
      }
      const data: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (!data || typeof data !== "object" || !("id" in data) || typeof data.id !== "string" ||
          !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.id)) return "unavailable";
      return "verified_user";
    } finally { controller.signal.removeEventListener("abort", cancel); await reader.cancel().catch(() => undefined); reader.releaseLock(); }
  };
  try {
    return await Promise.race([work(), new Promise<"unavailable">(resolve => {
      timer = setTimeout(() => { controller.abort(); resolve("unavailable"); }, 3000);
    })]);
  } catch { return "unavailable"; }
  finally { if (timer !== undefined) clearTimeout(timer); }
}
