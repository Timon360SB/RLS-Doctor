# Task-board application example

[Русский](README.ru.md)

A small Node application reads synthetic tasks from its own `task_board` schema.
It demonstrates integrating the **installed SDK archive** with real
`@supabase/supabase-js`, then diagnosing a separate, explicitly authored scenario
using the **installed Python wheel**. It does not import the source SDK or use
the documents/demo tables. No browser UI is included.

This is a maintained synthetic example, not an independent user's application
or evidence of external adoption. Its own reviewed migration installs a trusted
public identity probe explicitly; diagnostic commands never install it.

## Run from the repository root

Start Docker Desktop's Linux engine. Install the repository's documented tools:
Node.js 22.12+/24, pnpm 11.25.0 and uv. Install locked repository dependencies once:

```powershell
pnpm.cmd install --frozen-lockfile
uv sync --project python --frozen --group dev
uv run --project python python scripts/task_board_check.py --check
```

On POSIX shells use `pnpm` instead of `pnpm.cmd`. `--check` explicitly approves
this sample's setup: starting its separate stack, creating two synthetic Auth
users, and assigning three seeded task rows to those users. The first run may
download container images and locked sample dependencies. Raw stack startup,
credentials, task bodies and error bodies are not printed or saved by the checker.

| Resource | Value |
| --- | --- |
| Docker project | `rls-doctor-task-board` |
| API | `http://127.0.0.1:56321` |
| PostgreSQL | `127.0.0.1:56322` |
| Table | `task_board.tasks` |
| Setup and reports | Ignored `.rls-doctor/task-board/` |
| Distribution previews | Ignored `.rls-doctor/distribution-check-…/` |

The original fixtures (54321/54322) and practice lab (55321/55322) are separate.
The checker holds a project-scoped OS lock; close a running check before starting
another one. Edited setup files are preserved and cause SAMPLE_FILES_CHANGED;
the checker never automatically resets the database or overwrites your changes.

Docker/Supabase port publishing may include all host interfaces. Numeric-loopback
replay does not restrict inbound publishing; use a trusted development environment.
See [limitations](../../docs/limitations.md).

## What is actually checked

1. Build SDK tarball/Python wheel/sdist; audit archive paths, license/schema
   contents, installed SDK types/file sink and installed CLI event contract.
2. Install the sample's exact lockfile in a fresh ignored consumer directory,
   then install the just-built SDK archive. No package registry publication.
3. Create two local test identities. Assign Alice two synthetic tasks and Bob one;
   only the three seeded row IDs are updated during this explicit setup.
4. Run the real application separately for Alice, Bob and anonymous access.
   The app reads its response normally, checks exact task membership and saves
   one sanitized event through the real file sink. Rows/titles/tokens are omitted.
5. Validate each event with the installed CLI. Run a separate local GET scenario
   linked by event ID, confirming HTTP/count, own-row presence, foreign-row
   exclusion, server-side role and read-only catalog inspection of the actual
   `task_board.tasks` table with RLS enabled.

| Case | Expected application/replay result |
| --- | --- |
| Alice | PASS, HTTP 200, two own tasks; Bob's task excluded |
| Bob | PASS, HTTP 200, one own task; Alice's two tasks excluded |
| Anonymous | PASS, HTTP 200, zero tasks; all three task IDs excluded |

The trusted identity GET RPC lives in `public`, independently of the selected
table schema. This provides actual runtime coverage of non-public table routing
and public identity-probe routing. A sanitized v1 event records the resource,
not a complete original request; schema/filters/test values remain explicit in
the scenario. The linked replay does not establish the original caller's identity.

Expect three PASS lines with expected/observed row counts and process exit 0.
The checker prints a run directory containing `summary.json` plus each case's
`event.json`, `tasks.yaml`, `report.json` and capture file. Inspect those sanitized
artifacts rather than raw Supabase status. No secrets need copying.

## Read the integration

`app.mjs` configures `db.schema`, supplies `createCaptureFetch` through
`global.fetch`, disables session persistence/refresh and awaits the demo's file
sink before exit. The application consumes the response; the SDK must preserve
it. Runtime credentials/expected task IDs are supplied only by the approved
checker. The sample's package.json locks its application dependency; the SDK is
installed by the checker because it is still a private development preview.

`supabase/migrations/` and `seed.sql` are explicit disposable application setup.
They are never applied to a user's app by `doctor`, `inspect`, `session` or replay.

## Stop and resume

```powershell
uv run --project python python scripts/task_board_check.py --stop
```

Only this sample's stack stops; data is preserved. Re-run `--check` to create a
new user pair and reassign the three sample tasks. Old synthetic Auth users remain
until you deliberately remove them or reset this local project. No automatic
deletion/reset or changes to other stacks occur.

This workflow is included in local-integration CI. A local pass does not establish
that the latest remote CI, independent review or clean-machine onboarding passed.
