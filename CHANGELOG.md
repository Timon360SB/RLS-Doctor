# Changelog

## Unreleased — 0.1.0 implementation

- Fix doctor environment checks for custom-schema applications by checking roles
  directly in read-only catalogs, independently of public application tables.
- Save generated JSON reports with --output, including session --run; preserve
  exit codes/stdout and refuse existing or concurrently created destinations.

- Separate synthetic task-board app exercises installed SDK/CLI packages,
  non-public schema routing, exact owner isolation and anonymous access; EN/RU
  walkthroughs and local-integration CI use the same explicit setup runner.

- Prevent simultaneous practice sessions from reassigning each other's fixture rows;
  release the OS lock automatically after closure or process failure.
- Link captured events to managed local scenarios without guessing replay values.
- Retry invalid wizard fields without discarding previous valid answers.

- Fix the trusted public identity probe inheriting a non-public table profile in
  replay; doctor now explicitly selects the same trusted public probe schema.
- Audit/install both distribution packages, include the Python MIT license text,
  check installed SDK types/file sink and CLI version, and generate preview hashes.
- Real PostgreSQL 16/18 compatibility checks with owned-container cleanup and CI jobs.

- Clean JSON output for unattended managed sessions, preserved outcome exit codes,
  structured interruption errors, and live JSON-contract checks in the CI workflow.

- Isolated practice database launcher with two synthetic users, eight documents,
  18 verified checklist steps, and a detailed Russian testing walkthrough.

- Managed local session: automatic CLI credential loading with endpoint matching,
  in-memory scope, diagnostic menu, and explicit synthetic Auth signup approval.
  Existing local tokens can be reused; application data/policies remain untouched.

- Guided `init --interactive` local scenario configuration with explicit approval,
  no secret prompts, no connections, and no overwrite of existing files.
- Readable English/Russian CLI reports with expectation tables, separated
  evidence levels, catalog privilege summaries and diagnostic next steps.
- `doctor` respects an opted-out fixture identity probe and reports UNKNOWN
  rather than implying that API availability or the executed role was verified.

- One-command Windows demo launcher with dependency checks, pinned Supabase CLI,
  automatic fixture setup, bilingual scenario menu and human-readable reports.
- Separate approved local fixture admin connection for PostgreSQL role-creation
  integration tests; ordinary diagnostic connections retain their original rights.

- Opt-in Node Fetch wrapper and bounded, private JSON event sink.
- Shared v1 event schema, strict Python consumer and contract tests.
- Typed CLI: init, validate, analyze, doctor, inspect and replay.
- Offline capture analysis with explicit expectations, evidence levels and
  UNKNOWN outcomes instead of unverified server-side identity claims.
- Explicit numeric-loopback GET replay with verified local-test JWTs and identity probe.
- Read-only PostgreSQL role, privilege and RLS catalog inspector.
- Evidence-aware console/JSON reports and expectation comparisons.
- Synthetic Supabase fixtures, security regressions and local integration CI.
- English/Russian project pages, localized graphics and release guides.
- Disposable manual PowerShell session with synthetic scenarios and a Russian
  step-by-step testing guide; credentials remain in child-process memory.
- E2E negative cases require the intended HTTP/check evidence, and real
  PostgreSQL integration cannot pass merely because all tests were skipped.
- Accept valid legacy Supabase HS256 anon API keys without `iat`; authenticated
  access tokens still require it, with signature/expiry/role checks preserved.

This entry describes source changes, not a published or independently validated
release. See docs/verification.md for executed checks and unverified requirements.
