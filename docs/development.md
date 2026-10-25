# Development

Read AGENTS.md. Keep work on a feature branch; preserve other contributors'
changes. The existing repository policy remains authoritative. Use actual GitHub
accounts for ownership/review; comments in CODEOWNERS reserve no invented handles.

Install with pnpm 11.25.0 and `uv sync --project python --frozen --group dev`.
The root README lists build, lint, type and unit/contract test commands.
Build TypeScript before Python contract tests. Python uses a src layout and
strict mypy; Node SDK uses strict TypeScript, ESLint and Vitest.

`schemas/diagnostic-event-v1.schema.json` is the canonical contract. A byte-identical
copy is packaged under the Python module. Update both plus TypeScript event types,
Python model, compatibility tests and docs together. Unknown fields or schema
versions must fail explicitly. Cross-workstream review is required before merge.

To run real inspector integration, use a disposable local PostgreSQL superuser
DSN in RLS_DOCTOR_INTEGRATION_DSN and RLS_DOCTOR_ALLOW_FIXTURE_SETUP=1, then:

```sh
uv run --project python pytest python/tests/integration -q
```

Setup creates/drops only randomized synthetic schemas and NOLOGIN roles.
Diagnostics still use read-only transactions. Real tests passed on PostgreSQL 16.15, 17.10, Supabase 17.11 and 18.6.
Selecting a supported major in code alone is not proof of validation.
For local Auth/REST behavior use the Docker/Supabase E2E instructions instead.

CI installs locked dependencies, runs Node/Python matrices and starts an actual
Supabase fixture stack for E2E. Status secrets are piped through stdin, never
saved as artifacts. Remote workflow execution must be observed before describing
CI as green. Releases/package publication require explicit maintainer approval.

Priorities remain P0 correctness/privacy/local reproduction, P1 independent
clean-machine testing and human review, P2 browser/write/editor/UI features only
after separate design. Inspect the complete flow and relevant real integration
tests before making database or authorization guarantees.


## Validate installable preview packages

After locked dependency installation, run:

```sh
uv run --project python python scripts/package_check.py
```

The checker builds Python wheel/sdist and a local SDK tarball, audits member
paths/licenses/schema, installs both into separate consumers and verifies the
installed SDK, file sink, public TypeScript declarations, CLI version and shared
producer/consumer contract. The request is an in-memory Fetch fixture, not a live
Supabase replay. Actual database/Auth checks run separately.

Output contains three archives, SHA256SUMS and manifest.json under an ignored
artifacts directory printed by the checker. The consumer node_modules, Python
venv and capture event are outside that artifacts directory. Only manifest-listed
files are candidates for later attachment. Working-tree state and source commit
are recorded; preview validation does not publish packages or establish a release.

For real PostgreSQL compatibility beyond the Supabase stack, run:

```sh
uv run --project python python scripts/postgres_matrix.py --versions 16 18
```

Each official image runs in an owned disposable container on loopback port 55416
or 55418. The helper verifies the server version and actual test counts, then
removes only its uniquely labelled container and anonymous volumes. No raw DSN,
password, pytest output or container environment is saved in the evidence file.
The CI configuration has corresponding jobs; observe their remote execution
before claiming the workflow passed for a commit.


## Separate application / installed-package integration

Run `uv run --project python python scripts/task_board_check.py --check` to
explicitly prepare the separate synthetic task-board project on ports 56321/56322.
It builds/audits packages, installs the SDK archive into an app with a frozen npm
lockfile, and uses the installed Python wheel for event validation and managed
replay/inspection. Alice/Bob/anonymous checks assert exact task membership and
actual server roles against `task_board.tasks`, with the identity probe in public.

The setup runner alone creates test users and assigns the three seeded task IDs.
Diagnostics remain read-only. Reports and scoped runtime credentials follow the
same privacy boundary as the lab. Stop with the same command's `--stop` option.
See [the app walkthrough](../examples/task-board/README.md). The local-integration
workflow includes this scenario; its source is our maintained synthetic sample,
not independent adoption evidence.
