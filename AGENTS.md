# AGENTS.md — RLS Doctor

## Purpose

RLS Doctor is an open-source developer tool for **diagnosing unexpected authorization behavior in Supabase applications**. The target workflow is: capture a minimal, sanitized description of an application's request → inspect the relevant PostgreSQL access configuration → reproduce an explicitly defined request in a controlled local Supabase environment → compare observed behavior with an explicit expectation → report evidence, uncertainty, and next steps.

**This project is NOT** a generic RLS linter, an automatic SQL policy fixer, a security certification tool, or an invisible production traffic recorder. Existing tools (including pgrls, rlsautotest, pgTAP, and Supabase facilities) should be considered before duplicating functionality. Uniqueness and product–market fit are hypotheses to validate, not established facts.

The product specification is maintained separately from this file (for example, `docs/specification.md` when added). This file contains **durable repository-wide instructions** for human contributors and coding agents, not a command to implement the entire roadmap.

## Priority and scope

For any change, prioritize: **safety → diagnostic truthfulness → working, tested MVP → maintainability → developer experience → extensibility**.

The proposed v0.1 MVP includes:

- TypeScript SDK integrating with a user-supplied `fetch` in `supabase-js`, initially targeting Node.js.
- **Opt-in** collection of limited, sanitized metadata for supported Supabase REST **GET** requests.
- Versioned diagnostic-event JSON Schema shared by the TypeScript and Python components.
- Python CLI to validate events, inspect PostgreSQL RLS/privileges, run *explicitly configured* read scenarios against an isolated local Supabase instance, and produce console/JSON reports.
- Local, reproducible fixtures and automated unit/integration/security tests.

Out of scope for v0.1 unless the task explicitly expands it: browser instrumentation, arbitrary traffic interception, cloud collection, LLM-based root-cause guessing, UI/dashboard, VS Code extension, automatic policy changes, data migration, dynamic write scenarios (POST/PATCH/PUT/DELETE), and remote/production replay.

## Repository layout (target architecture; verify actual files first)

```text
packages/capture-sdk/       TypeScript SDK: fetch wrapper, normalization, tests
python/src/rls_doctor/      Python CLI: event ingestion, Postgres inspection, replay, reporting
python/tests/               Python unit/integration/security tests
schemas/                    Versioned diagnostic event schema (shared contract)
fixtures/supabase/          Local-only test migrations, fixtures, configuration
examples/                   Reproducible sanitized examples
.github/workflows/          CI checks and release automation
.github/CODEOWNERS          Code ownership and review routing, when configured
docs/                       Architecture, quickstart, security, limits, decisions
```

Do not assume these directories or commands exist in a new or partially implemented repository. Inspect actual files before editing; create only what the current task needs. Follow existing conventions rather than inventing duplicate structures.

## Two-maintainer collaboration

The repository is jointly maintained by **two developers using separate GitHub accounts**. Both must have meaningful implementation, review, maintenance, and release contributions. Do not fabricate or inflate contribution records.

- **Maintainer A — Application Diagnostics / TypeScript:** `packages/capture-sdk/`; fetch integration, event normalization, privacy controls, SDK tests, Node example, SDK documentation.
- **Maintainer B — Database Diagnostics / Python:** `python/`; event validation, PostgreSQL catalog inspection, local replay, assertions, reporting, CLI, integration tests.
- **Shared ownership:** `schemas/`, shared interface decisions, security boundaries, end-to-end examples, CI integration, releases, and roadmap.

Responsibilities describe workstreams, **not access restrictions**. Each maintainer may contribute anywhere; the other reviews changes. Do not invent GitHub handles in `CODEOWNERS` or name a maintainer without their explicit confirmation.

For schema/API-breaking changes:

1. Record the proposed contract change and compatibility consequences in the issue/PR.
2. Update versioned JSON Schema and TypeScript/Python models together.
3. Add producer/consumer compatibility tests and migration or explicit rejection behavior.
4. Get review from both workstreams before merging.

Do not coordinate by assuming that two Codex conversations share state. The Git repository, PRs, issues, and reviewed design documents are the source of truth. Do not overwrite another maintainer's uncommitted work; inspect `git status` before editing. Avoid unrelated edits and destructive Git operations.

## Non-negotiable security boundaries

**All diagnostic capture is explicitly opt-in and disabled by default.** Never introduce silent instrumentation or telemetry.

- Do **not** collect, print, persist, upload, or include in test snapshots: raw JWTs, bearer tokens, refresh tokens, cookies, passwords, service-role/secret keys, full authorization headers, request/response bodies, user table contents, or raw SQL containing potentially sensitive values.
- Prefer a strict **allowlist of fields** over redacting arbitrary raw requests after collection. Avoid storing full query strings, URL userinfo, or sensitive route parameters; normalize resource names and filter operators where safe.
- The SDK must not alter application auth, headers, URLs, method, request body, response body, or status; it must not consume the response stream. A diagnostic failure must not cause the application's original request to fail.
- Limit v0.1 capture to the configured Supabase REST GET paths. Treat RPC and unknown endpoints as unsupported; do not assume that all GET endpoints are side-effect-free.
- Capture only fields actually observable from the instrumented request. `Authorization` header presence **does not** prove identity, token validity, role, or successful authentication. Decoded but unverified JWT claims are not trusted proof.
- No automatic retransmission of captured requests. Sanitized events generally lack data required for faithful replay. Replay is a **separate, explicit, user-authored test scenario** using synthetic fixtures and local test credentials.
- Replay must be disabled unless its destination and environment are explicitly approved as local test infrastructure. Restrict destination schemes/hosts/ports with an explicit allowlist and validation; disable redirects and reject URL/userinfo tricks. `localhost` checks alone do not prove a target is safe (e.g., tunnels/proxies). Do not claim these controls protect against every misconfiguration.
- Never use production credentials, production rows, or live customer data in fixtures or replay. No schema modification, policy changes, or arbitrary SQL execution as part of diagnostics. Database inspection should use read-only catalog queries with least-privilege credentials where possible.
- **Do not run write operations** in MVP replay, and do not accept raw SQL/shell commands embedded in diagnostic events or YAML scenarios.
- Any later write tests must be designed separately for isolated disposable databases; a transaction rollback is not a universal side-effect boundary.
- Restrict logs, temporary files, artifacts and CI output to sanitized data. Add automated tests proving representative secrets cannot leak through errors or debug output.
- Never label an application, database, policy, or system as "secure" based solely on this tool's checks.

If requested functionality conflicts with these guardrails, explain the problem and propose a narrower, safer implementation instead of silently weakening the controls.

## Diagnostic correctness

- Distinguish **observations**, **derived conclusions**, and **unverified hypotheses**. For report evidence, use `OBSERVED`, `INFERRED`, and `UNVERIFIED` with explicit source/limitations. Separately use `PASS`, `FAIL`, `UNKNOWN`, and `ERROR` for test outcomes.
- Never claim that an HTTP `200` with `[]` proves an RLS rejection: there might be no matching rows or the request filters may exclude them.
- PostgreSQL SQL privileges and RLS are separate controls. Check schema usage, relevant table/column privileges, role membership, owner behavior, `FORCE ROW LEVEL SECURITY`, and `BYPASSRLS` where applicable.
- Account for permissive/restrictive policy composition and differences between `USING` and `WITH CHECK`. Inspect the applicable PostgreSQL version's documented semantics.
- `auth.uid()`, JWT claims, and PostgREST role context depend on the *executed* environment. Do not infer trusted server-side identity solely from unverified client metadata.
- Arbitrary SQL functions, views, dynamic SQL, external services, and hidden side effects may be undecidable from static inspection. Return `UNKNOWN`/`UNVERIFIED` where appropriate, with a next diagnostic step.
- Prefer exact PostgreSQL error codes, documented catalog facts, and actual local replay outputs over guessed root causes. Report version/feature limitations explicitly.
- Never say a diagnosis or regression test passed unless it was executed and its result observed.

## Code and API conventions

- TypeScript: strict mode, explicit public SDK types, no `any` without documented justification, idiomatic `fetch` semantics, `Vitest` for tests.
- Python: typed public interfaces, `Pydantic` for validated schemas, `Psycopg 3` for PostgreSQL, `HTTPX` for HTTP, `Typer` for CLI, `pytest` for tests, `Ruff` and `mypy` when configured.
- Keep core analysis logic separate from I/O, CLI, and UI/report formatting. Prefer small testable functions and explicit error types.
- Represent all diagnostic events as versioned, validated data. Do not silently accept unknown incompatible schema versions or fields carrying raw secrets.
- Use parameterized SQL and safe identifier quoting. Never interpolate untrusted role, schema, table, or column names into SQL strings.
- Errors should tell users what failed, why it is known or unknown, and what they can safely check next; redact secrets before formatting messages.
- Do not introduce a paid external API or cloud dependency into the MVP without explicit agreement. Do not add dependencies merely for convenience.
- Source code, public identifiers, commit subjects, and technical docs should generally use English; user-facing text may be localized separately. Preserve existing project conventions if already established.

## Testing and verification

For every functional change, add or update the smallest meaningful automated tests. Test at the appropriate layer:

- **TypeScript unit:** fetch wrapper preserves request/response behavior; opt-in controls; malformed requests; sanitization; diagnostic failure isolation; no response-body consumption.
- **Python unit:** schema validation; distinction between observation/inference/hypothesis; handling of unknown causes; report serialization; failure paths.
- **PostgreSQL integration:** missing `GRANT`, no SELECT policy, owner/BYPASSRLS behavior, role membership, permissive/restrictive combinations, test-fixture isolation.
- **Replay end-to-end:** own-row access, other-user denial, nonexistent-row ambiguity, invalid/absent test identity, intentionally mismatched expectations.
- **Security regression:** tokens and query values do not appear in logs/events/reports; unsupported endpoints, redirects, unsafe URLs, malformed scenario inputs are rejected.
- **Contract:** producer examples from TypeScript validate against the same JSON Schema parsed by Python; incompatible schema versions fail clearly.

Prefer live local PostgreSQL/Supabase integration tests where they are needed to establish behavior. Mocks are acceptable for unit boundaries, not as evidence that a database-level invariant holds.

Before describing a change as complete, run the **relevant commands that actually exist** in the repository (for example `pytest`, TypeScript test/typecheck, lint, integration tests) and report which passed, failed, or could not run. Do not invent a verified command or a passing result. Keep tests deterministic and runnable on contributors' machines, with optional Docker requirements documented.

## Working procedure for coding agents

1. Read the user task and inspect only the relevant code, tests, and project documentation. Consult detailed architecture/specification docs when the change affects their domain; do not reread the entire repository for trivial edits.
2. Check `git status`, locate ownership/contract boundaries, and preserve unrelated work.
3. For changes crossing workstreams, changing shared schemas, or touching auth/security, describe the intended interface and safety impact first; use a short plan for nontrivial tasks.
4. Implement the smallest complete change requested, with tests and necessary documentation. Never expand MVP scope on your own.
5. Run relevant checks; inspect diffs for secrets, unsafe endpoints, accidental new dependencies, and behavior changes.
6. In the final summary, state: **changed files**, **observable behavior**, **checks actually run and their results**, **known limitations**, and **recommended next step**.

Do not claim to have completed actions you cannot verify. Do not create or publish releases, push commits, modify remote GitHub configuration, deploy services, or contact third parties unless specifically requested and authorized.

## Definition of done

A task is done when its behavior matches the accepted scope, relevant tests demonstrate it, safety and uncertainty rules remain intact, public interfaces and examples are updated if necessary, and another maintainer can reproduce the result from the repository. An entire MVP is not "done" merely because skeleton directories and placeholders exist.
