<div align="center">

<img src="docs/assets/mark.svg" width="96" height="96" alt="RLS Doctor logo">

# RLS Doctor

**Understand PostgreSQL and Supabase access problems.**

Connect your database → choose a table and role → get findings and next steps.

<img src="docs/assets/badges.svg" width="556" height="32" alt="Development preview · uv launcher · Python 3.12+ · MIT license">

**English** · [Русский](README.ru.md)

[Get started](#get-started) · [Features](#features) · [Results](#understand-the-result) · [Documentation](#documentation)

<sub>Pre-release targeting v0.1.0. Registry packages and a public release are not published yet.</sub>

</div>

## Get started

For database diagnosis, install [uv](https://docs.astral.sh/uv/getting-started/installation/)
and download this repository (ZIP or Git). You need the host, port, database user
and password supplied by your PostgreSQL/Supabase provider.

**Windows:** open PowerShell in the repository and run:

```powershell
.\rls-doctor.cmd
```

The launcher prepares Python 3.12 and the locked runtime dependencies when needed,
then opens the database assistant. No separate dependency-sync command is needed.
First launch needs network access for dependency downloads. It does not install
system tools or require administrator access. Missing uv produces an installation link.

**macOS / Linux, or an existing terminal with uv:**

```sh
uv run --project python --python 3.12 --frozen --no-dev rls-doctor start
```

1. Enter the database host and explicitly approve catalog-only access.
2. Enter connection fields separately; password entry is hidden. Remote hosts use verified TLS.
3. Choose an existing table and the database role to investigate.
4. Read the first report, then use the menu to inspect other targets, review the
   schema, save JSON or switch English/Russian.

The next launch reuses the non-secret profile. Approval and password are requested
once when an action needs a connection; subsequent actions reuse that session.
Closing it releases credential references; no password or full DSN is saved.
Choose **6** to forget session credentials and reconnect. This is not a guarantee
of secure memory erasure. Explicit environment credentials remain under your control.

**Docker, Node.js, a test database and YAML are unnecessary for this workflow.**
The supported database majors are PostgreSQL 16, 17 and 18.

Russian entry point: `.\rls-doctor.cmd start --language ru`. Both menus can switch
language while running. See the [connection guide](docs/existing-database.md)
for TLS, least-privilege credentials and advanced connection strings.

### Install the CLI for use outside this repository

From the checkout, optionally install the local Python package into uv's isolated tool environment:

```sh
uv tool install --python 3.12 ./python
uv tool update-shell
```

Reopen your terminal, enter your application folder and run `rls-doctor start`.
Profiles and explicitly exported reports belong to that working folder. This installs
the local source version; after source changes, reinstall with
`uv tool install --force --python 3.12 ./python`. Remove with `uv tool uninstall rls-doctor`.
The repository launcher follows the checkout's lockfile; a tool installation uses
the package's pinned runtime dependencies. No public registry install is promised yet.

## Features

| Feature | Practical use |
| --- | --- |
| Guided connection and reusable profile | Get a first diagnosis without constructing DSNs, copying environment variables or preparing fixtures |
| Table/role diagnosis | Check schema usage, table/column SELECT, role membership, owner/BYPASSRLS, RLS/FORCE and applicable policies |
| Schema overview | Review up to 30 tables by default, 50 maximum; prioritize access blockers and settings requiring review in one read-only snapshot |
| Narrow policy shapes | Recognize constant true/false and supported exact auth.uid/column equality; keep other conditions unknown |
| Ordered investigation | Separate configuration blockers, authorization evidence, ownership conditions, missing rows and filters |
| Operational guidance | Safe SQLSTATE, connection/catalog phase and concrete EN/RU next steps; unknown causes stay explicit |
| Console and JSON | Human-readable findings plus stable diagnosis IDs, UTC timestamps and no-overwrite JSON export |
| Optional Node.js SDK | Opt-in metadata capture of supported Supabase REST GET requests, bound events and optional Auth verification |
| Optional local replay | Compare explicit synthetic GET expectations with observed results in approved disposable local infrastructure |

## Understand the result

| Output | Meaning |
| --- | --- |
| Access blocker / BLOCKED | Catalog facts establish a basic grant/schema/default-deny obstacle for the selected role |
| Review configuration / REVIEW | RLS is disabled/bypassed or SELECT is column-scoped; check whether that is intended |
| No basic blocker / NO_BASIC_BLOCKER | Basic checks found no obstacle; policy correctness and actual visibility remain unverified |
| UNKNOWN | Runtime behavior or the original request's cause is not established by the available evidence |
| ERROR | The operation could not finish; follow the reported next action |

An UNKNOWN catalog diagnosis can still identify a concrete blocker. HTTP 200 with
an empty array does not prove RLS denial. A chosen database role, a saved event or
a successful Auth check does not establish the PostgreSQL role of the original request.

For one-shot commands, exit codes are **0 PASS, 1 FAIL, 2 UNKNOWN, 3 ERROR**.
`connect` exits 0 when profile setup succeeds, and closing the interactive menu exits
0; neither means runtime access passed. `start --once` preserves UNKNOWN / exit 2.

### Direct commands

In the checkout, prefix these with `uv run --project python rls-doctor`, or use the
Windows launcher in place of `rls-doctor`:

```sh
rls-doctor start
rls-doctor connect --connection-string
rls-doctor diagnose --guide
rls-doctor overview --schema public --role authenticated --limit 30
rls-doctor diagnose public.orders --profile .rls-doctor/project.json --language ru
```

`overview` uses the profile's schema/role by default. Its limit follows table-name
order before priority sorting; an incomplete scan is explicitly marked. Each query
has fixed statement/lock limits and the scan checks a 30-second budget between tables.
Views and unusual identifiers are omitted; no policy predicate executes. For JSON
automation supply the profile-matching DSN privately, use `--approve-read-only
--format json`, and optionally `--output PATH_TO_NEW_REPORT.json`.

## Privacy and limits

- Catalog diagnosis never reads application rows or changes users, policies, grants or data.
- Full DSNs, passwords, tokens, raw server errors, SQL policy text and request/response bodies are not exported.
- Profiles do contain connection metadata and selected catalog names; review reports before sharing them.
- Remote catalog access requires certificate/name verification; forwarding and provider configuration remain operator responsibilities.
- Arbitrary functions, complex SQL policies, views, partition entry points and runtime row visibility need separate investigation.
- Browser instrumentation, writes, automatic fixes, remote replay and a dashboard are outside this MVP.

## Optional SDK and examples

Node.js 22.12+ is needed only for the SDK. It preserves the original fetch/Response
behavior and separates diagnostic failures. Recording and Auth checks are explicitly opt-in.
See [SDK API](packages/capture-sdk/README.md) and [request binding](docs/existing-database.md#bind-application-metadata).

To explore synthetic examples, use `.\lab.cmd` (or `.\lab.cmd -Language ru`).
That separate developer lab needs Docker's Linux engine, Node.js, pinned pnpm and uv;
the launcher prepares its dedicated local Supabase. It is not required to connect your own database.
The [practice guide](docs/practice-testing.md) explains all 18 checks and expected failures.
The [task-board example](examples/task-board/README.md) exercises installed packages
with two owners and anonymous access. These maintained examples are not independent adoption evidence.

## Development and release status

Local verification includes Python unit/privacy/contract tests, actual PostgreSQL
16/17/18 integrations, controlled verified-TLS/least-privilege tests, local
Supabase SDK/Auth flows and installed Python/SDK packages. The current changes
still need a matching remote CI run, clean-machine onboarding and independent
maintainer reproduction before public release. An external hosted customer project
has not been tested. No security certification is implied.

[Developer commands](docs/development.md) · [Release acceptance](docs/release-review.md) ·
[MVP readiness](docs/mvp-readiness.md) · [Roadmap](docs/development-plan.md)

## Documentation

| Guide | Purpose |
| --- | --- |
| [Existing database](docs/existing-database.md) / [Русский](docs/existing-database.ru.md) | Connection, TLS, profiles, overview and request binding |
| [Troubleshooting](docs/troubleshooting.md) | Fixed errors and safe next actions |
| [Architecture](docs/architecture.md) | Components and trust boundaries |
| [Specification](docs/specification.md) | Original scope and acceptance criteria |
| [Security](SECURITY.md) | Privacy and vulnerability reporting |
| [Changelog](CHANGELOG.md) | Implemented changes |

MIT — [LICENSE](LICENSE).
