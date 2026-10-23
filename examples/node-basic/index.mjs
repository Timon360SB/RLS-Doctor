import { createClient } from "@supabase/supabase-js";
import { resolve } from "node:path";
import { createCaptureFetch, createJsonFileSink } from "../../packages/capture-sdk/dist/index.js";

const localOrigin = "http://127.0.0.1:54321";
const apikey = process.env.RLS_DOCTOR_LOCAL_ANON_KEY;
if (!apikey || process.env.RLS_DOCTOR_APPROVE_LOCAL_TEST !== "true") {
  process.stderr.write("Set RLS_DOCTOR_LOCAL_ANON_KEY and RLS_DOCTOR_APPROVE_LOCAL_TEST=true for a disposable local Supabase stack.\n");
  process.exitCode = 1;
} else {
  const writes = [];
  const fileSink = createJsonFileSink({ directory: resolve(".rls-doctor/captures"), maxEvents: 5 });
  const captureFetch = createCaptureFetch(fetch, {
    enabled: true,
    allowedOrigin: localOrigin,
    resources: ["documents"],
    maxEvents: 5,
    maxDurationMs: 30_000,
    sink: (event) => {
      const writing = Promise.resolve(fileSink(event));
      writes.push(writing);
      return writing;
    },
    onDiagnosticError: (code) => { process.stderr.write(`Capture diagnostic: ${code}\n`); },
  });
  const client = createClient(localOrigin, apikey, {
    global: { fetch: captureFetch },
    auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
  });
  try {
    const { status, error } = await client.from("documents").select("id", { count: "exact" }).limit(5).abortSignal(AbortSignal.timeout(10_000));
    // Do not print rows, headers, credentials or the raw Supabase error object.
    process.stdout.write(`Local synthetic request finished: HTTP ${status}; application error present: ${error !== null}.\n`);
    const persisted = await Promise.allSettled(writes);
    if (persisted.some((result) => result.status === "rejected")) process.exitCode = 1;
    process.stdout.write(`Sanitized capture files written: ${persisted.filter((result) => result.status === "fulfilled").length}.\n`);
  } catch {
    process.stderr.write("The local synthetic request could not complete. Check the disposable fixture stack.\n");
    process.exitCode = 1;
  } finally { captureFetch.stop(); }
}
