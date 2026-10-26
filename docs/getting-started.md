# Getting started

For the primary existing-database workflow, start with [catalog diagnosis](existing-database.md) / [Русский](existing-database.ru.md). The fixture/replay paths below are optional.

Use Node.js 22.12+/24, pnpm 11.25.0, Python 3.12+ and uv 0.13.5. Local execution
has been checked on all four combinations of Node 22.23.4 / 24.22.1 and
Python 3.12.14 / 3.13.17. The local Supabase workflow and installed-package checks
have separate execution evidence; see [verification](verification.md). Current
remote CI, independent review and clean-machine onboarding remain release gates.
Follow the root README to install locked dependencies and build the SDK before
Python contract tests.

## Windows: start with the guided practice lab

Run `.\lab.cmd` in PowerShell from the repository root. The launcher checks tools,
prepares an isolated synthetic database and opens an English menu. Use
`.\lab.cmd -Language ru` for Russian. No credentials need copying.

Choose **18** for all functional checks or follow the numbered menu individually.
An expected FAIL in a deliberately broken scenario demonstrates detection;
it is not a launcher failure. The checklist compares expected and actual outcomes.
See the [detailed walkthrough](practice-testing.md) for each scenario's meaning.

Only one lab session can hold the practice lock at a time, preventing another
launcher from reassigning your test rows. Close the first lab menu before opening
a second. The OS releases this lock even after a process crash; do not delete its
file. Exit with **0**; stop the practice stack later with `.\lab.cmd -Stop`.


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

## Guided local configuration

Run `uv run --project python rls-doctor init --interactive` (add `--language ru`
for Russian). Choose `--directory .rls-doctor/my-project` for ignored local files.
The wizard validates the local URL and identifiers, previews expectations and
asks before enabling local replay or saving. Cancelling leaves no new files.
Configuration does not start Docker, connect to a service, copy production data,
create database objects, or ask for credentials.

Supply the local-only credential references listed below through a private
shell or secret manager. The wizard deliberately sets `confirm_identity=false`:
it does not install the fixture-specific identity RPC into your application.
Without a trusted probe, replay keeps the executed role unconfirmed (UNKNOWN)
and `doctor` does not call that RPC or claim API readiness. Enabling the flag
requires separately reviewed local infrastructure; it is not an installation fix.
Row-count-only expectations do not prove that another user's row was excluded;
add explicit synthetic `contains`/`excludes` assertions to test isolation.

Human-readable reports support `--language en` (default) and `--language ru`
on validate, analyze, doctor, inspect and replay. They group evidence by
OBSERVED / INFERRED / UNVERIFIED and show failed expectations separately.
`--format json` and exit codes are unchanged in either language.

## Local credentials without copy/paste

Use `rls-doctor session --config path/to/rls-doctor.toml --workdir path/to/local-project`
for automatic local CLI status loading and a diagnostic menu. The selected stack
must already run, and configuration must explicitly approve its local address.
The session never persists credentials or installs database objects. Synthetic
Auth signup requires a separate prompt/flag and does not prepare application rows.
See [managed sessions](managed-session.md) / [Русский](managed-session.ru.md).
Manual environment-variable setup below remains available for ordinary commands.

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


## Save a report directly

Add `--output .rls-doctor/reports/check-1.json` to validate, analyze, doctor,
inspect or replay. For managed sessions use `--run --output ...`. The CLI writes
UTF-8 JSON independently of shell encoding; `--format json` still emits only JSON
on stdout, and the original outcome exit code remains unchanged when saving works.
Console display remains available without --format json. Error reports can also
be saved. Existing files are never overwritten: choose a new filename for each run.
Directories are created as needed; existing destinations are rejected before
network/credential setup. Reports are capped at 1 MiB; atomic publication requires
filesystem hard-link support. A failed save returns ERROR / 3.

```powershell
uv run --project python rls-doctor replay documents.yaml --output .rls-doctor/reports/check-1.json
```

Use an approved synthetic scenario and local configuration as described above.
See [the readiness audit](mvp-readiness.md) for the remaining release gates.


For optional scenario authoring, `init --interactive --advanced` adds projected
columns, typed filters, required/forbidden records and error-class expectations.
Values are hidden during entry and stored only in the confirmed local synthetic
scenario. Columns used by assertions are included automatically. An existing
reviewed public identity probe can be explicitly enabled; nothing is installed.
The simple wizard and read-only diagnose workflow do not depend on this mode.
