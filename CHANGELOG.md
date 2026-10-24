# Changelog

## Unreleased — 0.1.0 implementation

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
