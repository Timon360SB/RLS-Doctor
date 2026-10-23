# Verification record — 2026-10-23

This records executed local checks. It does not announce a release, successful
GitHub Actions run, production support, independent adoption or two-human review.

## Implemented source

- `packages/capture-sdk/`: transparent opt-in Node Fetch wrapper, metadata
  normalization, bounded private JSON sink and SDK tests.
- `schemas/` and `python/src/rls_doctor/schemas/`: shared v1 JSON Schema;
  strict model/validator and byte-identical packaging contract.
- `python/src/rls_doctor/`: typed CLI, local configuration guards, JWT validation,
  identity probe, read-only catalog inspection, GET replay, assertions and reports.
- `fixtures/`, `examples/`, `scripts/e2e.py`: synthetic fixtures, four explicit
  diagnostic examples, offline producer and real Supabase E2E runner.
- `.github/workflows/ci.yml`, dependency locks, MIT license, contributing/security
  policy and architecture/research/usage documentation.
- Existing `AGENTS.md` preserved; no maintainer account or contribution history invented.

## Observed checks

| Check | Result | Evidence and boundary |
| --- | --- | --- |
| pnpm frozen installation | PASS | Locked Node dependencies installed on this Windows machine. |
| TypeScript build and strict typecheck | PASS | SDK compiled and public declarations generated. |
| ESLint | PASS | SDK source and tests checked. |
| Vitest | 46 PASS | Includes privacy, transparent fetch, failure isolation, limits and Windows junction rejection. |
| Python unit/security/contract suite | 76 PASS | Actual Node SDK producer consumed by Python; HTTP boundary tests use MockTransport and do not prove Supabase behavior. |
| Real PostgreSQL integration | 8 PASS | PostgreSQL 17.10 on disposable loopback instance; not mocks. |
| Ruff format/check | PASS | Python sources, tests and E2E script. |
| Strict mypy | PASS | 20 Python source files. |
| Python sdist and wheel build | PASS | Built from the Python package source. |
| Installed wheel smoke | PASS | Separate environment executes the installed CLI and consumes an actual TypeScript event with the packaged schema. |
| Four YAML examples | PASS | Parsed with the strict scenario loader. This does not prove their live outcome. |
| Workflow/fixture configuration parsing | PASS | YAML/TOML read successfully; no remote workflow execution implied. |

Real PostgreSQL checks exercised read-only transaction enforcement (SQLSTATE
25006 on attempted write), missing grants, default-deny, permissive/restrictive
composition, inherited/NOINHERIT roles, ownership/FORCE/BYPASSRLS, column grants,
policy literal privacy and unsupported view behavior. The temporary PostgreSQL
server was stopped and its disposable data/password file removed. It was a
workspace-only portable instance, not a system service installation.

The ordinary final pytest invocation reports **76 passed, 8 skipped** without
local integration environment variables. Those eight tests also ran separately
against real PostgreSQL and passed; the skipped invocation is not counted as
additional evidence or additional tests.

Code review found and regression-tested malformed dates, impossible Content-Range,
reserved filter overrides, missing/truncated responses, over-cap results and
bounded body reads. Reports exclude raw bodies, test values and secrets.

Transfer checks caught an overly broad Git ignore rule that omitted the Python
report module. The rule is now root-anchored and the actual wheel CLI is checked,
in addition to source-tree imports. A PEP 561 marker identifies the typed package.

## Still unverified / release blockers

1. Complete Docker/Supabase Auth + PostgREST + Capture + Replay E2E has not run
   on this machine: Docker/Supabase services were unavailable. The runnable setup,
   fixtures and CI job are source artifacts, not a passing result.
2. GitHub Actions has not run remotely; no push, PR, release or package publication
   was performed. CI matrix entries Node 22/Python 3.13 are not locally verified.
3. Only Node 24, Python 3.12 and real PostgreSQL 17.10 were exercised locally.
   PostgreSQL 16/18 require actual integration runs before compatibility claims.
4. A second real maintainer must review shared contracts/security and independently
   reproduce a clean-machine demonstration before accepting the full MVP criteria.
5. No general static evaluation of policy SQL, writes, views, browser SDK or remote
   replay. Policy expression text is intentionally not collected.

## Recommended next work

Run the supplied real Supabase E2E pipeline in Docker, fix any environment/API
differences found there, then obtain independent maintainer review and observed
CI results before tagging 0.1.0. Future priorities follow architecture.md.
