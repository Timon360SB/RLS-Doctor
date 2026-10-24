# Getting started

Use Node.js 22.12+/24, pnpm 11.25.0, Python 3.12+ and uv 0.13.5. Local execution
has been checked on Node 24 and Python 3.12. The Node 22/24 and Python 3.12/3.13
CI matrix passed on main commit 216c8b6; the Supabase E2E job failed. The local
API-key fix still needs a complete remote rerun; see [verification](verification.md). Follow the root README to install locked
dependencies and build the SDK before Python contract tests.

## No-database contract check

```sh
node examples/node-basic/capture-event.mjs > event.json
uv run --project python rls-doctor validate event.json --format json
uv run --project python rls-doctor analyze event.json --expected-role authenticated --format json
```

The first command uses the real wrapper with an in-memory Fetch implementation.
The validation is a producer/consumer check only. The offline analysis returns
UNKNOWN / exit 2 because captured metadata cannot confirm the executed identity
or prove an RLS cause. Neither command makes a database claim.

## Reproduce the entire local fixture workflow

Install Docker and Supabase CLI 2.121.0. Use a private local terminal:

```sh
supabase start --workdir fixtures
```

The CLI can print local credentials. Do not record or share its output. Explicitly
approve synthetic fixture setup in the current shell:

```powershell
$env:RLS_DOCTOR_ALLOW_FIXTURE_SETUP = '1'
supabase status --workdir fixtures --output json | uv run --project python python scripts/e2e.py --status-stdin
supabase stop --workdir fixtures
```

On a POSIX shell use `export RLS_DOCTOR_ALLOW_FIXTURE_SETUP=1`. The script reads
status credentials only from stdin, signs up two disposable Auth users, updates
synthetic ownership, captures an actual supabase-js request and runs the real
replay/inspector tests. Passwords and tokens remain in that process and are not
exported to your parent shell. Re-running creates new disposable users; reset the
local fixture stack when finished. No production data or remote project link.

## Run your own explicit scenario

```sh
uv run --project python rls-doctor init
```

This creates `rls-doctor.toml` and `documents.yaml` without overwriting files.
Review the config, point it at your disposable numeric loopback endpoint, allow
the exact API/database ports and resource names, then set `approved_local=true`.
The default remains false. Hostname aliases, DNS, HTTPS, remote destinations,
URL credentials, alternate paths and redirects are rejected in v0.1.

Supply these variables through your private shell or secret manager:

| Variable | Source and purpose |
| --- | --- |
| RLS_DOCTOR_LOCAL_ANON_KEY | Approved local stack's anon or publishable key |
| RLS_DOCTOR_DATABASE_URL | Local DSN with numeric host, explicit port, database and user |
| RLS_DOCTOR_LOCAL_JWT_SECRET | Local-only HS256 secret when using legacy signed keys/tokens |
| RLS_DOCTOR_TEST_TOKEN | Disposable user's access token from local Supabase Auth |

Never paste these values into reports, Git, issues or chat. Authenticated tokens
must have a valid local signature, audience `authenticated`, unexpired claims,
role `authenticated` and issuer `<approved api_url>/auth/v1`. Public-key tokens
use the local JWKS endpoint; no arbitrary key URL is accepted.

```sh
uv run --project python rls-doctor doctor
uv run --project python rls-doctor inspect public.documents --role authenticated
uv run --project python rls-doctor replay documents.yaml --inspect --format json
```

An optional `--event <capture.json>` links a resource-compatible sanitized event.
Replay values still come from YAML. Filters support eq, neq, gt, gte, lt, lte and
is (`null`, `true`, `false`). Reserved query parameters cannot be filter names.
Row expectations use `contains`/`excludes` lists of `{column, value}`; values are
not copied into reports. Examples in missing-auth, incorrect-rls and
tenant-isolation intentionally demonstrate failing expectations. The missing-grant
example expects the permission error and should pass on the matching fixture.

Console/JSON exit codes: PASS 0, FAIL 1, UNKNOWN 2, ERROR 3. Unknown role, incomplete
results or unsupported evidence never become PASS. Inspection alone returns
UNKNOWN about runtime behavior even when individual catalog facts are confirmed.

Legacy HS256 anon API keys from Supabase CLI have no `iat` claim. They still
require a valid local signature, expiry and the `anon` role. Authenticated user
tokens additionally require `iat`, the configured audience, issuer and subject.

## Interactive manual testing on Windows

The [Russian step-by-step guide](manual-testing.ru.md) covers offline checks and
individual real scenarios. With the disposable stack running and fixture consent
set, run `uv run --project python python scripts/manual_session.py` from an
interactive PowerShell. The helper reuses the E2E setup and opens a child shell
with local credentials in memory. Generated TOML/YAML files contain references
and synthetic expectations only. Exit that shell to discard its credentials;
do not rerun setup concurrently, since it changes synthetic ownership.
