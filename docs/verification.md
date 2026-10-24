# Verification record — local baseline 2026-10-23; follow-up 2026-10-24

This records executed local checks and a dated inspection of remote CI. It does
not announce a release, an entirely passing workflow, production support,
independent adoption or two-human review.

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
| Strict mypy | PASS | 21 Python source files. |
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

## Remote CI follow-up — checked 2026-10-24

[GitHub Actions run 40008000986](https://github.com/Timon360SB/RLS-Doctor/actions/runs/40008000986) executed on
main commit `216c8b6a8ca956962a114ee81f0967b721725bda` on 2026-10-23.
All four Node 22/24 × Python 3.12/3.13 check jobs passed, including lint,
types, tests and installed-wheel execution. The complete workflow failed.

The Supabase integration job started the actual local fixture stack. It logged
`PASS actual supabase-js GET -> Capture SDK -> JSON Schema -> Python`, then
`ERROR INVALID_TEST_TOKEN` before the first replay case completed. Cleanup passed.
This proves the capture/contract stage ran remotely; it does not prove replay or
that job's PostgreSQL integration suite passed.

A local regression reproduces this failure using the legacy HS256 anon API-key
claim shape emitted by the pinned CLI: `iss`, `role`, `exp`, with no `iat`.
See the upstream [CLI v2.121.0 signer](https://github.com/supabase/cli/blob/v2.121.0/apps/cli/src/command-internal/go-jwt.ts).
The validator previously required `iat` for both API keys and user tokens.
The local fix requires it for authenticated user tokens while keeping local
signature, expiry and exact-role checks for legacy anon keys. No issuer,
audience or signature checks on user tokens were relaxed.

Observed local checks after the fix on 2026-10-24:

| Check | Result | Boundary |
| --- | --- | --- |
| New regression before fix | 1 failed, 7 passed | Valid CLI-shaped anon key reproduced `INVALID_TEST_TOKEN`. |
| Python unit/security/contract suite after fix | 112 PASS, 8 integration tests deselected | Includes API-key, E2E evidence, manual-session and capture-analysis regressions; this is not a live Supabase rerun. |
| Ruff format and lint | PASS | 32 Python files formatted; lint passed. |
| Strict mypy | PASS | 21 Python source files. |

New cases cover the CLI anon key without `iat`, expired/missing-exp/missing-role
keys, service-role rejection, invalid signatures, publishable API-key headers,
and continued rejection of authenticated access tokens without `iat`.

## Manual testing and E2E evidence follow-up — 2026-10-24

The fixture setup is shared by the automated E2E and a new Windows manual-session
helper. That helper fetches local status in memory, requires fixture consent and
an interactive terminal, creates synthetic YAML/TOML without credentials, and
starts a child PowerShell in the repository root. The parent terminal receives
no new secret variables. See [manual testing](manual-testing.ru.md).

Negative E2E cases now require the intended HTTP status, row count and failing
assertion instead of accepting any aggregate FAIL. The PostgreSQL child reports
only execution counts; skipped or uncollected tests cannot count as a pass.
These changes are covered by 14 E2E-evidence tests and 6 manual-session tests,
in addition to the 8 API-key regressions and original 76 tests.

The offline steps in the manual guide were executed: actual SDK event -> UTF-8
file -> CLI PASS/0; invalid schema -> INVALID_EVENT/3; disabled init config ->
LOCAL_APPROVAL_REQUIRED/3. PowerShell blocks parse successfully. The full new
interactive fixture session is still unverified against live Supabase.

The strengthened integration runner also executed against a fresh disposable
loopback PostgreSQL 17.10 cluster on 2026-10-24. All 8 real integration tests
passed through the execution-count guard. The server was stopped, and that
run's temporary cluster and generated password file were removed. This checks
PostgreSQL inspection and the execution guard, not Supabase Auth/REST replay.
Docker installation was postponed at the user's request. Its prerequisite
Virtual Machine Platform is disabled, so no Docker runtime was started.

## Offline capture analysis — 2026-10-24

The new `analyze` CLI command consumes the same strict event schema without
configuration, credentials, network requests or database inspection. It reports
captured facts and uncertainty, with an overall UNKNOWN result and exit code 2.
It never converts a present Authorization header into a confirmed identity.
Missing HTTP status only becomes a network finding if the event classifies it
as a network failure; otherwise the failure type remains unknown.

Eight new CLI tests cover offline execution with network/database clients blocked,
missing expected authorization, header-presence uncertainty, network vs unknown
status, optional expectations, invalid-event privacy and console/error behavior.
The full non-integration suite passed: 112 tests, with 8 integration tests deselected.
Ruff checked 32 Python files; strict mypy passed for 21 source files.

The sdist and wheel were rebuilt successfully. The wheel was reinstalled in a
separate existing test environment, then its CLI analyzed an actual SDK producer
event and returned UNKNOWN / exit 2 with HTTP_OBSERVED, MISSING_EXPECTED_AUTH
and EMPTY_RESULT_AMBIGUOUS. This is offline evidence; full Supabase E2E remains
unverified and Docker remains postponed.

## Still unverified / release blockers

1. Full Supabase replay E2E remains unverified. The remote run failed as described
   above; the local compatibility fix has not run in a new workflow. Docker installation is postponed and
   Supabase CLI is absent on this Windows machine, so a complete local rerun
   could not be performed.
2. The four passing remote matrix jobs apply to `216c8b6`, before this local fix.
   Commit and push the reviewed change, then verify a new complete workflow.
   No new push, PR, tag, release or package publication was performed by this fix.
3. Local Node 24/Python 3.12 checks remain the baseline; PostgreSQL 17.10
   integration was rerun on 2026-10-24 through the strengthened runner.
   Remote CI additionally exercised Node 22 and Python 3.13. PostgreSQL 16/18
   still require actual integration runs before compatibility claims.
4. A second real maintainer must review shared contracts/security and independently
   reproduce a clean-machine demonstration before accepting the full MVP criteria.
5. No general static evaluation of policy SQL, writes, views, browser SDK or remote
   replay. Policy expression text is intentionally not collected.

## Recommended next work

Commit the reviewed API-key fix and rerun the supplied Supabase CI workflow.
Confirm all replay assertions and real inspector tests pass, then obtain
independent maintainer review before tagging a stable 0.1.0 release.
