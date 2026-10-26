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


## Existing-database integration and temporary build files

`scripts/database_check.py` creates an owned PostgreSQL TLS container and verifies
CA/name/expiry rejection, restricted catalog access, structural policy privacy,
profiles and the guided connection. With --workdir fixtures and explicit
RLS_DOCTOR_ALLOW_FIXTURE_SETUP=1, it also checks actual local SDK/Auth capture,
then removes only its synthetic Auth user. It never resets the existing stack.
Generated certificates, profiles and event samples stay in OS temporary folders;
container/volume cleanup checks the unique ownership label.

Use `python scripts/package_check.py --scratch-dir PATH_TO_TEMP_DIRECTORY` to keep
preview build/install files outside the source checkout. This performs no publication.


## Required scenario coverage

This maps specification T01–T12 to reproducible checks, not a claim about a user's
application. Run the unit/integration/E2E commands above; skip is never pass.

| ID | Maintained check |
| --- | --- |
| T01 Missing authorization | scripts/e2e.py missing_auth; capture analysis unit tests |
| T02 Authorized user | scripts/e2e.py own_row_and_other_user_denial / second_test_user |
| T03 RLS disabled | integration/test_postgres.py test_real_disabled_rls_is_reported_without_default_deny |
| T04 No SELECT policy | integration/test_postgres.py test_real_missing_select_grant_and_default_deny; E2E default_deny |
| T05 Missing GRANT | Same real integration test; E2E missing_grant; database_check actual SQLSTATE 42501 |
| T06 Wrong user | E2E own_row_and_other_user_denial / second_test_user |
| T07 Incorrect policy | E2E tenant_isolation_leak plus result assertions |
| T08 Actually empty table | scripts/database_check.py empty_table_check: owned empty table, permissive policy, SDK/Auth, replay and ambiguity assertion |
| T09 Invalid token | E2E invalid_token; replay signature/expiry/issuer unit regressions |
| T10 Unavailable database | scripts/database_check.py unavailable_check; operational error privacy tests |
| T11 Secrets | SDK capture/file-sink tests; operational tests and live integration privacy assertions |
| T12 Unsupported request | Strict scenario/event validation and replay endpoint/operator guards |

The T08 helper creates/drops only one random synthetic table in an explicitly
approved local fixture. A zero-row expectation can pass while the cause of an
original empty response remains UNVERIFIED. It never labels zero rows as proof
that an RLS predicate rejected an existing row.


## Primary user workflow checks

The runtime-only Windows entry point is rls-doctor.cmd. It uses uv and the Python
lockfile without the developer dependency group. The Windows CI job restores its
Python 3.13 developer environment after launcher verification.
Unit coverage includes separate fields, hidden credentials, profile reuse,
EN/RU switching, session reconnect, cancellation, no-overwrite export, JSON parity
and bounded schema-overview scope/time. The real database_check runner covers
both field/DSN onboarding, one-password menu reuse and overview export over verified
TLS with a role lacking SELECT on customer tables. Eleven PostgreSQL integration
tests per version cover actual catalog/grant/RLS behavior and overview truncation.
The package checker exercises installed start/overview/connect entry points,
python -m rls_doctor and noninteractive no-argument help.
