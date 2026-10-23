# RLS Doctor

**Request replay and authorization diagnostics for Supabase.**

RLS Doctor combines opt-in Node.js request metadata with an explicit synthetic
GET scenario, read-only PostgreSQL catalog inspection, and an evidence-based
console or JSON report. It does not copy production requests or collect rows,
JWTs, cookies, passwords or response bodies in diagnostic events.

Status: initial 0.1.0 implementation, **not a published release**. See
[verification](docs/verification.md) for exactly which checks have run. Full
Supabase E2E needs Docker and an approved disposable local stack.

## Start with the contract (no database needed)

Prerequisites: Node.js 22.12+/24, pnpm 11.25.0, Python 3.12+ and uv 0.13.5.

```sh
pnpm install --frozen-lockfile
uv sync --project python --frozen --group dev
pnpm build
node examples/node-basic/capture-event.mjs > event.json
uv run --project python rls-doctor validate event.json --format json
```

The offline producer executes the actual SDK around a supplied in-memory Fetch
implementation. It proves the TypeScript-to-Python contract; it does not prove
Supabase, PostgreSQL or network behavior. The real stack check is separate below.

## Capture an application request

```ts
import { createClient } from '@supabase/supabase-js';
import { createCaptureFetch, createJsonFileSink } from '@rls-doctor/capture-sdk';

const fetchWithCapture = createCaptureFetch(fetch, {
  enabled: true,
  allowedOrigin: 'http://127.0.0.1:54321',
  resources: ['documents'],
  maxEvents: 10,
  maxDurationMs: 30_000,
  sink: createJsonFileSink({ directory: '.rls-doctor/captures' }),
});
const client = createClient(localUrl, localAnonKey, {
  global: { fetch: fetchWithCapture },
});
```

SDK packages are currently workspace packages, not claimed npm publications.
Build and use the relative import shown in [the runnable example](examples/node-basic).
Capture is disabled unless explicitly enabled. A diagnostic sink failure cannot
replace the application's response or request error. SDK v1 records a row count
only from a valid Content-Range header and never parses response bodies.

## Explicit local replay

```sh
uv run --project python rls-doctor init
uv run --project python rls-doctor doctor
uv run --project python rls-doctor inspect public.documents
uv run --project python rls-doctor replay documents.yaml --inspect --format json
```

`init` creates a disabled configuration. Review local fixtures, approve the
numeric loopback origin/ports/resources and set local-test environment credentials
before `doctor` or `replay`. See [getting started](docs/getting-started.md).
Replay cannot reconstruct redacted production values: scenario filters and test
expectations are explicit. Only GET table resources are accepted; arbitrary RPCs,
SQL, remote hosts and redirects are rejected. The built-in fixture identity probe
is the sole hard-coded GET RPC exception.

Every finding uses OBSERVED, INFERRED or UNVERIFIED. Assertion results are PASS,
FAIL, UNKNOWN or ERROR. Exit codes are 0, 1, 2 and 3 respectively. For example,
200 with zero rows cannot establish that RLS filtered a row. Catalog inspection
alone returns UNKNOWN about actual request behavior.

## Check the real disposable stack

With Docker running and Supabase CLI 2.121.0 installed:

```sh
supabase start --workdir fixtures
# Set RLS_DOCTOR_ALLOW_FIXTURE_SETUP=1 in your shell first.
supabase status --workdir fixtures --output json | uv run --project python python scripts/e2e.py --status-stdin
supabase stop --workdir fixtures
```

Run in a private terminal: Supabase startup/status can display local credentials.
Never commit or upload those outputs. The E2E script keeps credentials in memory,
signs up disposable Auth users, updates synthetic fixtures, captures an actual
supabase-js request, executes replay comparisons and runs real inspector tests.
Fixture setup writes are separate from the read-only diagnostic engine. See
[fixture details](fixtures/README.md) and [CI workflow](.github/workflows/ci.yml).

## Development

```sh
pnpm build
pnpm typecheck
pnpm lint
pnpm test
uv run --project python ruff format --check python scripts
uv run --project python ruff check python scripts
uv run --project python mypy --config-file python/pyproject.toml python/src/rls_doctor
uv run --project python pytest python/tests -m "not integration"
```

Build SDK before Python contract tests. Integration tests are opt-in and require a
real disposable PostgreSQL instance; mocked HTTP tests validate client boundaries
only. Python and Node lockfiles are committed. The canonical event schema and
packaged Python copy must be byte-identical (enforced by tests).

Read [architecture](docs/architecture.md), [research](docs/research.md),
[limitations](docs/limitations.md), [security](SECURITY.md),
[troubleshooting](docs/troubleshooting.md) and [contributing](CONTRIBUTING.md).
The original [specification](docs/specification.md) is retained for traceability.
MIT license. No telemetry, paid API or hosted collector.
