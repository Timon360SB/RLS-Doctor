# RLS Doctor Capture SDK

Node.js 22.12+/24 SDK for opt-in Supabase REST GET metadata. Capture is disabled by
default. There is no telemetry service, global patch, token decoding, request
retransmission, or implicit network destination.

```ts
import { createCaptureFetch, createJsonFileSink } from '@rls-doctor/capture-sdk';
import { createClient } from '@supabase/supabase-js';

const captureFetch = createCaptureFetch(fetch, {
  enabled: true,
  allowedOrigin: new URL(localUrl).origin,
  resources: ['documents'],
  maxEvents: 100,
  maxDurationMs: 300_000,
  sink: createJsonFileSink({ directory: '.rls-doctor/captures' }),
  onDiagnosticError: code => console.error(code),
});
const client = createClient(localUrl, localAnonKey, {
  global: { fetch: captureFetch },
});
// Run your normal application request through this client.
// Handle its result/errors as usual; capture does not change them.
await client.from('documents').select('id', { count: 'exact' });
```

When the diagnostic window is finished, explicitly stop capture:

```ts
captureFetch.stop(); // also disables metadata for still-pending results
```

Supply application credentials from your local environment; never put them in
diagnostic files. The example identifiers `localUrl` and `localAnonKey` refer to
your own application configuration.

## Public API

`createCaptureFetch(fetchImpl, options?) -> CaptureFetch` wraps the user-supplied
Fetch implementation. `CaptureFetch` has the standard Fetch signature plus
`stop(): void`. It passes the original arguments, argument count, and receiver
to Fetch and returns its original Promise. It returns the original Response
without reading or cloning its body. Original thrown/rejected errors retain
their identity. The wrapper does not change request headers, URLs, methods,
bodies, auth, status, or retry behavior.

`CaptureOptions`:

| Field | Behavior |
| --- | --- |
| `enabled` | Defaults to `false`. Set explicitly to `true` to capture. |
| `allowedOrigin` | Required when enabled; exact HTTP(S) origin, with no credentials, path, query or fragment. |
| `resources` | Required nonempty allowlist of simple table/view names (ASCII identifiers, at most 63 characters). |
| `sink` | Required when enabled; `(event: DiagnosticEvent) => void \| Promise<void>`. |
| `onDiagnosticError` | Optional callback receiving only `metadata_failed` or `sink_failed`. Synchronous throws and Promise rejections are isolated. |
| `maxEvents` | Default 100; positive integer at most 10000. Includes admitted in-flight captures and failed sink attempts. |
| `maxDurationMs` | Default 300000; positive integer at most 86400000. Both admission and response completion must be within the window. |

Invalid explicit configuration throws a fixed, sanitized `TypeError` when the
wrapper is created. Runtime diagnostic errors never reject the application's
Fetch Promise. Async sinks are observed but never awaited; a sink that never
settles does not delay the original request. As with any in-process callback,
a sink doing synchronous expensive work or blocking the event loop can delay
other JavaScript execution. Keep sinks small and asynchronous.

Only exact `/rest/v1/<allowed resource>` paths (optionally ending with `/`) and
effective method GET are eligible. An `init.method` or `init.headers` replacement
overrides the corresponding Request input field. RPC, nested paths, encoded
resource names, URL credentials, other origins, relative URLs, and unsupported
methods are not captured. Custom header iterables are not consumed for
diagnostics. URLs over 16384 characters are skipped; at most 256 query
parameters are inspected and at most 64 filters are recorded.

## Event contract and limits

`DiagnosticEvent` follows the canonical schema in
`schemas/diagnostic-event-v1.schema.json`. Events contain a random local UUID,
timestamp, duration, method/API/resource, safe filter column names and supported
operator names (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `is`), response status,
optional inferred returned-range length, fixed error kind, and boolean header
presence. Events are frozen before passing to a sink.

Query values, full URLs, request/response bodies, SQL, header values, cookies,
tokens, raw errors, and decoded JWT claims are never included. Unsupported
operators and unsafe column names are omitted. Filters are a partial metadata
description, so events cannot faithfully replay their source request.

`row_count` is inferred only from a syntactically valid Content-Range header:
`0-9/100` indicates 10 returned rows, not 100. `*/0` indicates zero; ambiguous,
missing or invalid ranges yield `null`. The body is never checked against the
header. Empty results do not prove that RLS filtered a row. Header presence
does not prove authentication, identity, role, or token validity. HTTP errors
have `error_kind: 'http'`; rejected Fetch calls have `'network'`, without the
exception text.

`createJsonFileSink({ directory, maxEvents?, maxBytes? }) -> CaptureSink` writes
one `<event UUID>.json` per event. Defaults are 100 files and 1048576 bytes;
maximum configurable limits are 10000 files and 104857600 bytes. Existing
directory entries count toward the limits. Calls are serialized and admitted
within bounded per-instance reservations; failed attempts are not retried.
The sink rebuilds schema fields before writing, discarding extra properties.
Duplicate filenames are refused. Error strings are fixed and do not echo paths
or event data. Await the returned Promise if your application needs to confirm
that a file was persisted.

New POSIX directories use 0700 and files 0600. Existing POSIX sink directories
with group/other permissions are refused. Windows users must place captures
under an appropriately private directory ACL. Symlink/junction directory
components and symlink entries are refused; files use exclusive creation, so
they are never overwritten. These checks do not protect against a hostile
process concurrently replacing filesystem components. Use a private, dedicated
directory, not a shared directory. Multiple concurrent sink instances have
separate limits and are not a filesystem quota.

Browser support and arbitrary writes are outside v0.1. A custom sink is user
code: review it before sending even sanitized metadata anywhere.


Schema 1.0 records the REST resource, not `Accept-Profile` or a verified database
schema/identity. A custom-schema application still configures `db.schema` in
supabase-js; a diagnostic replay must declare its schema and synthetic values
separately. See the [installed-package task-board example](../../examples/task-board/README.md).


## Bound project events and explicit Auth verification

Copy the non-secret project UUID and API origin from `rls-doctor connect`:

```ts
const captureFetch = createCaptureFetch(fetch, {
  enabled: true, projectId: 'UUID_FROM_CONNECT',
  allowedOrigin: 'https://YOUR_PROJECT.supabase.co', resources: ['orders'],
  verifyAuth: true,
  sink: createJsonFileSink({ directory: '.rls-doctor/captures' }),
});
```

`projectId?: string` opts into event 1.1, retaining 1.0 as the default. It adds a
project UUID, SHA-256 of the API origin (not a token), Accept-Profile schema and
simple projection-column names. Complex projection metadata is null. Schemas 1.0
and 1.1 are separate strict contracts; new Python readers accept both, old readers
reject 1.1. Shared-contract changes need review by both workstreams before merging.

`verifyAuth?: boolean` defaults false. It requires projectId and HTTPS (numeric
loopback HTTP excepted). It explicitly allows one additional GET /auth/v1/user
through the supplied Fetch, with only authorization/apikey headers of that capture.
The check starts after the original response; its result is a later observation.
It uses redirect:error, an AbortSignal, a 3-second limit and a 32-KiB response cap.
Transient Auth data is discarded; only verified_user/rejected/unavailable/
no_authorization/not_checked is serialized. No token, user ID, email or Auth body
is persisted. The original application Response is neither read nor cloned.

A verified user session does not prove the executed database role or auth.uid value
in the original query. A bound event establishes a configuration match, not trusted
server routing or tamper-proof event authenticity. Review your supplied Fetch and
local sink as trusted code. --event diagnosis never repeats the application GET.
