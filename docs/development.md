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
Diagnostics still use read-only transactions. The actual tested server was
PostgreSQL 17.10; selecting a supported major in code is not proof of validation.
For local Auth/REST behavior use the Docker/Supabase E2E instructions instead.

CI installs locked dependencies, runs Node/Python matrices and starts an actual
Supabase fixture stack for E2E. Status secrets are piped through stdin, never
saved as artifacts. Remote workflow execution must be observed before describing
CI as green. Releases/package publication require explicit maintainer approval.

Priorities remain P0 correctness/privacy/local reproduction, P1 independent
clean-machine testing and human review, P2 browser/write/editor/UI features only
after separate design. Inspect the complete flow and relevant real integration
tests before making database or authorization guarantees.
