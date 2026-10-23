# Architecture and delivery plan

RLS Doctor 0.1.0 targets Node.js 22/24 and Python 3.12+. This is an initial
implementation, not a published or independently validated release.

Capture produces only schema v1 metadata. An explicit origin and resource allowlist
is required; capture is off by default. A wrapped fetch receives exactly the same
arguments and returns the original response without reading its body. Row counts
are inferred only from a valid Content-Range header. Error bodies and JWT claims
are not captured. No event can recreate the original production request.

The Python consumer validates against the canonical JSON Schema and typed models.
Replay consumes a separate, strict YAML scenario and a local environment file.
It permits numeric loopback IP destinations and explicit ports only, disables
redirects, proxies and ambient HTTP auth, and requires explicit local-test approval.
Test tokens are fetched from environment variables, cryptographically verified
against local Auth's JWKS (or an explicitly configured local HS256 test secret),
and checked for issuer, audience, expiry and the expected role. Secrets never enter
reports. A trusted local RPC can confirm the actual database role in the replay
context; an unconfirmed role stays unknown. GET RPC execution is excluded from
user scenarios; the sole identity probe is hard-coded in the local fixture.

Inspection uses Psycopg 3 read-only catalog queries on a separately allowlisted
local Postgres endpoint. SQL privileges are distinct from policy predicates.
Reports separate evidence (OBSERVED/INFERRED/UNVERIFIED) from assertion results
(PASS/FAIL/UNKNOWN/ERROR). The inspector does not evaluate arbitrary predicates.
No diagnostics execute schema changes. Fixture setup is a separate explicit step.

## Priorities and workstreams

| Priority | Work | Dependency | Workstream |
| --- | --- | --- | --- |
| P0 | SDK, shared schema, strict event ingestion | none | A + shared |
| P0 | Typed CLI, assertions and sanitized reports | shared schema | B |
| P0 | Local GET replay and verified test identity | config, fixtures | B |
| P0 | Read-only catalog inspector | local DB config | B |
| P0 | Contract, security, real Postgres/Supabase tests | all above | shared |
| P1 | Lockfiles, CI, docs and reproducible demos | P0 | shared |
| P1 | Independent second-maintainer review and clean-machine run | CI | humans |
| P2 | Browser SDK, writes, HTML, editor integration | separate design | future |

The two workstreams are engineering responsibilities, not fabricated human
contributions. No second GitHub account is invented. Existing AGENTS.md remains
the repository policy. Contract changes require both workstreams' review.

## Honest boundaries

Loopback can still be forwarded to remote infrastructure; operators must approve
only disposable local stacks. Signed claims confirm token validation, not policy
intent. A server-side identity probe is meaningful only in trusted local fixtures.
Empty results never prove RLS caused exclusion. Fixture SQL is synthetic and
must never be applied to production. Full Supabase E2E requires Docker.
