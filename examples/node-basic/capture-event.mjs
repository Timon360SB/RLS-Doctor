import { createCaptureFetch } from "../../packages/capture-sdk/dist/index.js";

// Offline producer/consumer contract example: no HTTP request and no credentials.
const events = [];
const captureFetch = createCaptureFetch(
  async () => new Response("[]", { headers: { "Content-Range": "*/0" } }),
  {
    enabled: true,
    allowedOrigin: "http://127.0.0.1:54321",
    resources: ["documents"],
    sink: (event) => { events.push(event); },
    maxEvents: 1,
  },
);
await captureFetch("http://127.0.0.1:54321/rest/v1/documents?owner_id=eq.synthetic-fixture-value");
// The SDK's completion observer was registered before this await continuation.
if (events.length !== 1) throw new Error("Expected exactly one sanitized producer event.");
process.stdout.write(`${JSON.stringify(events[0], null, 2)}\n`);
