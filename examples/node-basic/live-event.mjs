// Real local Supabase request for scripts/e2e.py; never print rows or credentials.
import { createClient } from "@supabase/supabase-js";
import { createCaptureFetch } from "../../packages/capture-sdk/dist/index.js";

const origin = process.env.RLS_DOCTOR_LOCAL_API_URL;
const key = process.env.RLS_DOCTOR_LOCAL_ANON_KEY;
const token = process.env.RLS_DOCTOR_TEST_TOKEN;
if (!origin || !key || !token) throw new Error("Local test environment missing.");
const events = [];
const capturedFetch = createCaptureFetch(globalThis.fetch, {
  enabled: true, allowedOrigin: origin, resources: ["documents"],
  sink: (event) => { events.push(event); }, maxEvents: 1,
});
const client = createClient(origin, key, {
  global: { fetch: capturedFetch, headers: { Authorization: `Bearer ${token}` } },
  auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
});
const result = await client.from("documents").select("id", { count: "exact" });
if (result.error || events.length !== 1) throw new Error("Local capture failed.");
process.stdout.write(JSON.stringify(events[0]));
