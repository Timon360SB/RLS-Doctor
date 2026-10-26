<div align="center">

<img src="docs/assets/mark.svg" width="96" height="96" alt="RLS Doctor logo">

# RLS Doctor

**Understand who can read what in your Supabase application.**

Inspect access settings in existing PostgreSQL/Supabase databases.<br>
Trace requests and run local checks when more evidence is needed.

[**Quick start**](#diagnose-an-existing-database) · [Capabilities](#capabilities) · [Your project](#use-with-your-project) · [Reports](#reports-and-outcomes) · [Documentation](#documentation)

<img src="docs/assets/badges.svg" width="556" height="32" alt="Development preview · Node.js 22.12+ · Python 3.12+ · MIT license">

<br><br>

<img src=".github/preview.png" width="880" alt="Offline example: the SDK emits a sanitized event and Python validates it. This image does not show a live database replay.">

<sub>Development preview targeting v0.1.0. Packages and releases have not been published. <a href="docs/mvp-readiness.md">MVP readiness</a>.</sub>

**English** · [Русский](README.ru.md)

</div>

## Diagnose an existing database

This is the primary workflow: connect to your existing PostgreSQL/Supabase
instance and inspect access settings for a table and role. No test scenarios,
synthetic users, SDK or identity probe are needed.

```powershell
uv sync --project python --frozen
uv run --project python rls-doctor diagnose public.orders --host YOUR_DATABASE_HOST --role authenticated
```

Use your actual table/host/role. Approve the connection, then enter the PostgreSQL
connection string in the hidden prompt, or use a private environment reference.
Remote connections require verify-full TLS. Only catalogs are read; no user rows
or policies are modified. See [English](docs/existing-database.md) /
[Русский](docs/existing-database.ru.md) for credentials, CA certificates and limits.
This command needs Python/uv, not Docker/Node.js. The lab and replay below are optional.

## Why RLS Doctor

A user sees an empty list. Another user unexpectedly sees someone else's record.
The cause could involve authentication, SQL privileges, RLS policies, missing
data or request filters. RLS Doctor helps developers examine those possibilities
with a captured event, catalog facts and a separately defined local test.

**HTTP `200` with `[]` does not prove an RLS denial.** Findings keep that
uncertainty visible. A passing scenario confirms its explicit expectations;
it does not certify an application's security.

## Capabilities

| Capability | What it does |
| --- | --- |
| Existing-database diagnosis | Read-only catalog inspection of an approved PostgreSQL/Supabase connection, without fixtures or scenario files |
| Opt-in Node.js capture SDK | Wraps the application's `fetch` for `supabase-js`; preserves the original request/response and isolates diagnostic failures |
| Minimal diagnostic events | Records supported REST GET metadata, timing, status, header presence and safely normalized filter names/operators; omits secrets, values and bodies |
| Capture controls | Exact origin/resource allowlists, stop control, bounded recording duration/event count and bounded local JSON file storage |
| Offline event analysis | Validates the shared v1 schema and explains observable metadata without database credentials |
| Read-only PostgreSQL inspector | Examines RLS/FORCE RLS, roles, membership, owner/bypass behavior, schema/table/column grants and policy applicability/composition |
| Explicit local GET replay | Uses synthetic YAML scenarios and verified local test identities; compares HTTP status, count, record presence/exclusion and error class |
| Guided setup and managed sessions | Creates reviewed configuration through a wizard; loads matching local Supabase credentials in memory without copying keys |
| Console and JSON reports | Separates expectations, facts, inference and uncertainty; supports direct UTF-8 JSON export and stable outcome exit codes |
| English and Russian | English by default; Russian menus/reports via `-Language ru` in Windows launchers or `--language ru` in the CLI |

## How it works

```text
Application → opt-in SDK → sanitized event → validation / offline analysis
                                  │
                                  └── optional link to a separate local scenario

Explicit YAML expectations → approved local GET + read-only catalog inspection
                                             │
                                             ▼
                              Console / JSON evidence report
```

Capture does not automatically replay traffic. Events omit original values and
the selected database schema/profile. The scenario declares the schema, synthetic
values and expectations independently. A trusted local identity probe can confirm
the replay's executed role; captured headers cannot confirm the original caller.

## Quick start

**Optional practice on Windows:** use the guided practice lab. It prepares a
separate local Supabase database, two synthetic users and eight documents, then
opens a menu. No credentials need copying.

### Prerequisites

| Tool | Requirement |
| --- | --- |
| Docker | Docker Desktop with a running Linux engine for database scenarios |
| Node.js | 22.12 or newer; local checks cover branches 22 and 24 |
| pnpm | 11.25.0, pinned by the repository |
| Python / uv | Python 3.12+ and uv 0.13.5; the Windows launcher prepares Python 3.12 through uv |
| Supabase CLI | 2.121.0; the Windows launcher locates or downloads the pinned CLI |

Clone the repository, or open your existing checkout. Git is needed for cloning.

```powershell
git clone https://github.com/Timon360SB/RLS-Doctor.git
cd RLS-Doctor
.\lab.cmd
```

Answer **y** to prepare the practice database. Choose **18** for the complete
18-row checklist, or follow the individual menu items. Deliberately broken cases
have expected FAIL/ERROR outcomes; the checklist verifies that the intended
evidence matches, rather than accepting any failure.

```powershell
.\lab.cmd -Language ru
.\lab.cmd -Check
.\lab.cmd -Stop
```

These are separate choices: Russian menu, unattended full check, and stop.
Exiting the menu leaves the database running. Stopping preserves its data.
Preparation creates a new test-user pair and reassigns the eight synthetic rows;
old Auth users remain until deliberately removed or the local environment is reset.
An OS lock prevents competing lab launchers from changing ownership mid-session.

The first run can download dependencies and container images. System prerequisites
are checked with actionable errors; they are not silently installed.

**Walkthrough:** [English](docs/practice-testing.md) · [Русский](docs/practice-testing.ru.md).

## Examples and local environments

| Entry point | Purpose | API / database ports |
| --- | --- | --- |
| `lab.cmd` | Guided practice: SDK, identities, access failures, JSON, sessions and actual PostgreSQL regressions | 55321 / 55322 |
| `demo.cmd` | Shorter menu of six synthetic authorization demonstrations | 54321 / 54322 |
| Task-board app | Real `supabase-js` application with installed SDK/CLI packages and its own `task_board` schema | 56321 / 56322 |

The task-board check verifies Alice's two tasks, Bob's one task and zero tasks for
anonymous access. It also exercises the public identity probe independently of
the custom table schema. It is our maintained sample, not independent adoption.

After installing repository dependencies as described under [Development](#development):

```powershell
uv run --project python python scripts/task_board_check.py --check
uv run --project python python scripts/task_board_check.py --stop
```

Run these separately. `--check` explicitly approves setup of this synthetic
sample. `--stop` preserves its data. Full instructions:
[English](examples/task-board/README.md) · [Русский](examples/task-board/README.ru.md).

For a **no-database** introduction, the [Node example](examples/node-basic/README.md)
exercises the real wrapper with an in-memory Fetch implementation. Its offline
analysis returns UNKNOWN because runtime identity and an RLS cause are unverified.

## Use with your project

Use a disposable **local Supabase project** with synthetic data. Install repository
dependencies first, then create configuration with the interactive wizard:

```powershell
uv run --project python rls-doctor init --interactive --directory .rls-doctor/my-project
```

Review the local URL, ports, table, identity and expectations. Replay remains
disabled unless you explicitly approve the destination. Invalid answers repeat
only that question; existing configuration files are preserved. The wizard does
not connect, ask for secrets or create database objects.

Start your own local Supabase stack separately. Replace `path/to/local-project`
below with its folder containing `supabase/config.toml`:

```powershell
uv run --project python rls-doctor session --config .rls-doctor/my-project/rls-doctor.toml --workdir path/to/local-project
```

The session matches CLI status against the approved destination, scopes credentials
to its process, and offers scenario replay or table inspection. A missing test
identity requires an existing valid token reference or explicit synthetic signup
approval. New users do not automatically own your application's existing rows.

Guided configuration leaves the trusted identity probe disabled. Without a
separately reviewed probe, the executed role remains unconfirmed and replay may
return UNKNOWN. Sessions do not install that probe, prepare application rows,
change policies, start/reset your stack or save credentials.

Read [setup](docs/getting-started.md) and managed sessions in
[English](docs/managed-session.md) / [Русский](docs/managed-session.ru.md).
For SDK integration, see the [SDK API](packages/capture-sdk/README.md) and task-board app.

## CLI reference

Commands below follow `uv run --project python rls-doctor` when using the checkout.

| Command | Purpose |
| --- | --- |
| `diagnose public.orders --host YOUR_DATABASE_HOST` | Diagnose existing access settings with hidden/private connection credentials |
| `init --interactive` | Guided configuration and an explicit synthetic scenario |
| `validate event.json` | Check a captured event against the shared schema |
| `analyze event.json --expected-role authenticated` | Explain capture metadata offline |
| `doctor --config project.toml` | Check local database/version, required roles and optional trusted API identity context; no application-table assumption |
| `inspect public.documents --role authenticated --config project.toml` | Read catalog access settings; runtime row visibility remains UNKNOWN |
| `replay documents.yaml --inspect --config project.toml` | Run a synthetic local GET with optional catalog inspection |
| `session --config project.toml --workdir local-project` | Load local credentials in memory and open a diagnostic menu |

Use `--help` on a command for all options and `--version` for the installed version.

| Option | Applies to |
| --- | --- |
| `--language en` / `--language ru` | Human-readable CLI setup/reports; JSON fields remain unchanged |
| `--format console` / `--format json` | Diagnostic commands; session JSON requires `--run` |
| `--output path/to/report.json` | Diagnostic commands; session export requires `--run` |
| `--event path/to/event.json` | Optional event link for replay/session; values still come from YAML |
| `--run` | One unattended session run, preserving its outcome exit code |
| `--create-test-user` | Explicitly allow synthetic local Auth signup in a session when needed |

Ordinary doctor/inspect/replay commands use environment references for local
credentials. A managed session loads matching CLI credentials for its own scope;
see [Getting started](docs/getting-started.md) for both workflows.

<details>
<summary><strong>Example: own-row access and foreign-row exclusion</strong></summary>

```yaml
version: 1
name: document_owner_access
request:
  method: GET
  schema: public
  resource: documents
  columns: [id]
identity:
  type: authenticated
  token_env: RLS_DOCTOR_TEST_TOKEN
expect:
  status: 200
  row_count: 1
  contains:
    - column: id
      value: "10000000-0000-4000-8000-000000000001"
  excludes:
    - column: id
      value: "10000000-0000-4000-8000-000000000002"
```

These are synthetic fixture IDs. Prepare matching local ownership and credentials
before execution. Checking count alone does not establish whose row was returned.

</details>

## Reports and outcomes

Console reports show expectations, observed behavior, identity/catalog evidence,
limitations and next steps. JSON supports automation and direct file export:

```powershell
uv run --project python rls-doctor validate path/to/event.json --format json --output .rls-doctor/reports/event-1.json
```

Replace the event path with an existing sanitized capture. Saved files use UTF-8,
independently of PowerShell redirection encoding. Existing destinations are
rejected before diagnostic work; choose a new filename per run. Error reports can
also be saved. Successful export preserves the outcome code and clean JSON stdout.

Publication is atomic without overwrite, capped at 1 MiB, and requires filesystem
hard-link support. Save failures return ERROR/3. Windows uses the folder's ACLs;
new POSIX files begin with mode 0600.

| Outcome | Exit | Meaning |
| --- | --- | --- |
| PASS | 0 | Observed behavior matches explicit expectations |
| FAIL | 1 | An expectation was violated |
| UNKNOWN | 2 | Evidence cannot establish the required behavior |
| ERROR | 3 | Execution failed or input/environment was rejected |

An expected denial can PASS. A deliberate tenant leak should FAIL. A valid offline
event can still produce UNKNOWN. Separately, **OBSERVED**, **INFERRED** and
**UNVERIFIED** describe the strength of each diagnostic statement.

## Scope and privacy

- Capture is disabled by default and limited to supported Node.js REST table GETs.
  No browser instrumentation, write replay, automatic SQL fixes or web dashboard.
- Events/reports omit raw JWTs, keys, cookies, passwords, bodies and filter values.
  Raw response SQL error codes and policy SQL expressions are not collected.
- Replay targets explicitly approved numeric-loopback HTTP endpoints and allowed
  resources/ports. Redirects and environment proxies are disabled.
- Inspection uses read-only catalog transactions. Example setup is a separate,
  explicit operation which creates synthetic users/data.
- Replay is bounded to 1000 rows and 1 MiB; incomplete results cannot confirm absence or total counts.
  Arbitrary functions, views and policy predicates cannot be fully inferred.
- Docker/Supabase may publish local stack ports on all host interfaces. Outbound
  loopback validation does not restrict inbound publishing or detect forwarding.

See [security boundaries](docs/security.md), [vulnerability reporting](SECURITY.md)
and [limitations](docs/limitations.md).

## Verification and release status

Recorded local evidence as of **2026-10-25**; exact runs and versions are in
[verification.md](docs/verification.md).

| Area | Recorded evidence |
| --- | --- |
| SDK | 46 local tests; real application capture and installed archive/file-sink checks |
| Python / shared contract | 271 tests on Python 3.12.14/Node 24 and Python 3.13.17/Node 22.23.4 |
| PostgreSQL | Eight tests per recorded real integration run; version coverage includes 16/17/18 |
| Local workflows | Full Supabase E2E, 18-row practice checklist and separate custom-schema app passed |
| Direct export | All six diagnostic commands checked for file/stdout parity; live PASS/FAIL/UNKNOWN/ERROR exports passed |
| Packaging | Wheel, sdist and SDK archive built/audited; installed SDK/CLI exercised together |
| Code checks | TypeScript checks and recorded SDK lint/tests; latest Python formatting/lint and strict types passed |

The 271-test invocation excludes the eight integration tests; those have separate
actual execution evidence. These records are not live CI badges.

All eight jobs in [run 40178244545](https://github.com/Timon360SB/RLS-Doctor/actions/runs/40178244545)
passed for `a91c9d5`. The subsequent audited preview-retention workflow changes
require their own committed run. The workflow is configured to retain only three
package archives, checksums and a matching-source manifest for seven days;
[download and acceptance steps](docs/release-review.md) apply after that step passes.

**Still required before release:** fresh GitHub Actions for the current changes,
clean-machine Windows onboarding, and independent maintainer reproduction/review.
The [readiness audit](docs/mvp-readiness.md) maps the implementation to the master
specification. See the [release guide](docs/releases.md) for publication steps.

## Development

Install locked dependencies and build the SDK from the repository root:

```powershell
pnpm.cmd install --frozen-lockfile
uv sync --project python --frozen --group dev
pnpm.cmd build
```

On POSIX shells use `pnpm` instead of `pnpm.cmd`. After setup:

```powershell
pnpm.cmd typecheck
pnpm.cmd lint
pnpm.cmd test
uv run --project python pytest python/tests -m 'not integration' -q
uv run --project python ruff format --check python scripts
uv run --project python ruff check python scripts
```

Package audit: `uv run --project python python scripts/package_check.py`.
Real PostgreSQL compatibility: `uv run --project python python scripts/postgres_matrix.py --versions 16 18`.
These produce local checks/previews, not published packages. Detailed E2E,
strict typing and CI instructions are in [Development](docs/development.md).

## Documentation

| Topic | Guides |
| --- | --- |
| Guided practice | [English](docs/practice-testing.md) · [Русский](docs/practice-testing.ru.md) |
| Existing database | [English](docs/existing-database.md) · [Русский](docs/existing-database.ru.md) |
| Managed sessions | [English](docs/managed-session.md) · [Русский](docs/managed-session.ru.md) |
| Separate task-board app | [English](examples/task-board/README.md) · [Русский](examples/task-board/README.ru.md) |
| Setup and SDK | [Getting started](docs/getting-started.md) · [SDK API](packages/capture-sdk/README.md) · [Node example](examples/node-basic/README.md) |
| Design and fixtures | [Architecture](docs/architecture.md) · [Fixtures](fixtures/README.md) · [Research](docs/research.md) |
| Diagnostics | [Troubleshooting](docs/troubleshooting.md) · [Security](docs/security.md) · [Limitations](docs/limitations.md) |
| Independent acceptance | [English](docs/release-review.md) · [Русский](docs/release-review.ru.md) |
| Progress and release | [Readiness audit](docs/mvp-readiness.md) · [Verification](docs/verification.md) · [Releases](docs/releases.md) · [Changelog](CHANGELOG.md) |

## Contributing and license

[Open an issue](https://github.com/Timon360SB/RLS-Doctor/issues) with a sanitized
description and synthetic reproduction. Read [AGENTS.md](AGENTS.md) for repository
conventions and [SECURITY.md](SECURITY.md) before reporting a vulnerability.
Do not include credentials, customer rows or raw stack status.

[MIT](LICENSE) · RLS Doctor contributors.
