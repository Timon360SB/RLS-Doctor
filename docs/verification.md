# Verification record — local baseline 2026-10-23; follow-up through 2026-10-25

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

## Still unverified / release blockers — updated 2026-10-25

1. The full local Supabase E2E now passes (see below). Remote CI has not been
   rerun for these changes; the earlier remote matrix belongs to `216c8b6`.
2. A fresh-machine installation has not been reproduced. The Windows launcher
   was exercised on this configured computer, including setup cancellation,
   RU menu selection, invalid input, all scenarios, stopping and restarting.
3. Local Node 24 / Python 3.12 and PostgreSQL 17 remain the baseline.
   PostgreSQL 16/18 require actual integration runs before compatibility claims.
4. A second real maintainer must review shared contracts/security and independently
   reproduce a clean-machine demonstration before accepting the full MVP criteria.
5. No general static evaluation of policy SQL, writes, views, browser SDK or remote
   replay. Policy expression text is intentionally not collected.

## Recommended next work

Review the changes, rerun remote CI after the maintainers push them, and test
on a clean Windows machine. Next simplify configuration for a user's own local
project; the guided demo currently uses only the supplied synthetic fixtures.

## Guided demo and actual Docker E2E — 2026-10-25

Docker Desktop 4.96.3 / Engine 29.9.2 with WSL2 successfully started the
four-service `rls-doctor-fixtures` stack on Windows: PostgreSQL 17.11.0.004,
Auth, PostgREST and Kong. The guided demo's six synthetic scenarios produced
their intended PASS/FAIL outcomes. English and Russian reports were exercised.

The complete `scripts/e2e.py --status-stdin` run exited 0: actual supabase-js
capture, schema validation, both test identities, missing authentication,
default deny, missing grant, intentional isolation failure, nonexistent-row
ambiguity, invalid-token rejection and the real PostgreSQL inspector suite.
The normal `postgres` fixture login is not a superuser. Only the separately
approved integration fixture setup uses `supabase_admin` at the validated
numeric loopback destination; diagnostic inspection keeps the ordinary login.
The runner still rejects skipped or incomplete integration evidence.

This supersedes earlier local Docker/WSL and pending-local-E2E blockers.
It does not establish remote CI success, clean-machine onboarding, compatibility
with additional database versions or independent maintainer review. The guided
demo uses synthetic data and does not diagnose the user's own application.

Final regression checks for this change: 118 non-integration Python tests passed
(8 integration tests deselected in that separate unit invocation); Ruff format
and lint passed; strict mypy passed for 21 source files. The complete E2E above
separately executes the actual PostgreSQL integration tests without skips.
The Windows launcher smoke covered declining preparation, RU menu input including
an invalid choice, individual positive/negative scenarios, all scenarios, exit
without stopping, `-Stop` with data preservation, and an EN `-Check` restart.


## Guided CLI configuration and reports — 2026-10-25

Added init --interactive with English default and --language ru. Prompt tests
exercise explicit local approval, cancellation without new files, preservation
of existing files and rejection of unsafe destinations. No credential prompts,
network connections or schema changes occur during configuration. The wizard
keeps the fixture identity probe disabled; doctor respects that flag and cannot
claim API availability or a verified runtime role in that configuration.

Console reports for validate/analyze/doctor/inspect/replay now separate expected
and observed values, observed facts, derived conclusions and unverified caveats.
Catalog-only caveats retain their source context when combined with real REST
observations. JSON fields and exit codes remain unchanged; regression tests
verify language-independent JSON and non-mutation of machine evidence.

Executed checks:
- 133 Python non-integration tests passed; 8 integration tests were deselected
  only in that unit invocation.
- Full actual local Supabase E2E passed separately, including the real PostgreSQL
  inspector integration suite with the no-skip evidence guard.
- Actual own-row PASS and intentional isolation FAIL reports were checked in
  English and Russian; tested credentials were absent from console output.
- Ruff formatting/lint and strict mypy (22 source files) passed.
- sdist/wheel built; the wheel was installed in a separate Python 3.12 environment.
  Its init --help and interactive setup executed successfully; generated replay
  approval remained false when declined.

No TypeScript or shared event schema changed. Fresh remote CI, clean-machine
onboarding, independent maintainer review and publication remain unverified.
See development-plan.md for remaining P0/P1/P2 priorities. Credential onboarding
and a trusted identity probe for a separate local application require further
work; the wizard does not automatically prepare an application's database.


## Managed credential session — 2026-10-25

Implemented session with an approved config, a selected local Supabase workdir,
credential loading from CLI JSON in memory, API-origin/database-port validation,
and scoped process environment restoration. No service-role key is loaded into
credential variables. The session snapshots validated config/scenario objects
rather than rereading mutable destinations after binding credentials.

Anonymous scenarios require no Auth signup. Authenticated scenarios reuse an
existing locally verified test token or require explicit approval for one synthetic
Auth signup with a generated password. This setup-only POST is separate from the
GET replay engine. It cannot prepare application table rows, change ownership or
policies, or install an identity probe. New Auth users remain until removed or the
operator intentionally resets the local stack; exit does not delete accounts.

Executed checks:
- 158 Python non-integration tests passed (8 integration deselected there).
- 25 session regressions cover local destination matching, consent, cancellation,
  environment restoration, oversized/malformed status, signup failure/redirects,
  non-leaking errors and preserved PASS/FAIL/UNKNOWN/ERROR one-run exit codes.
- Actual local Supabase: EN/RU menu input, invalid menu choice, catalog inspection,
  anonymous replay, refusal of implicit signup, explicit synthetic signup, verified
  test identity/replay, and reuse of an existing local token all passed.
- The complete local E2E passed separately, including the real PostgreSQL suite.
- Tested CLI keys, DSN/signing secret and access token were absent from session
  output; generated test configuration contained no credentials.
- Ruff format/check and strict mypy (24 source files) passed.
- sdist and wheel rebuilt; the wheel was reinstalled in a separate Python 3.12
  environment and its session entry point/help executed successfully.

This is evidence on the supplied disposable fixture stack, not an independent
application, fresh-machine installation or current remote CI run. General identity
probe provisioning and user application fixture preparation remain unimplemented.


## Isolated hands-on practice database — 2026-10-25

Created and started the separate rls-doctor-practice local Supabase stack on
API 55321 / DB 55322. Four tables contain two synthetic documents each; two
new synthetic Auth users are assigned their own rows by explicit lab setup.
The original fixture stack remained running on ports 54321/54322.

lab.cmd prepares the SDK and isolated database, then offers the actual CLI
walkthrough. English is default; Russian is available with -Language ru.
The detailed user plan is docs/practice-testing.ru.md. Setup/scenarios/reports
live under ignored .rls-doctor/practice; credential values are kept in memory.

Executed checks:
- All 18 checklist rows matched expected behavior, including real SDK capture,
  validation/offline analysis, both users, deliberate failures, protection against
  invalid inputs, session onboarding and the real PostgreSQL regression suite.
- Eight PostgreSQL integration tests ran through the execution-count/no-skip guard
  using only the practice database administrative setup connection.
- 164 Python non-integration tests passed, with eight integration tests deselected
  only in that separate unit invocation.
- SDK typecheck/lint passed and all 46 Vitest tests passed.
- Ruff format/lint and strict mypy (24 source files) passed.
- Practice stop/restart and the full Russian checklist passed; original demo
  default/cancellation still worked.
- Documented wizard values, no-overwrite error and the unconfirmed-role UNKNOWN
  result were executed against the running practice stack.

The database was left running for the user's hands-on checks. The lab reuses
reviewed synthetic fixture definitions; it does not establish independent app
adoption, clean-machine installation, current remote CI or production support.


## Managed session JSON automation — 2026-10-25

session --run --format json emits one structured report with no setup/menu text.
JSON without --run is rejected before loading credentials. Interrupting any
unattended session returns ERROR / SESSION_CANCELLED / exit 3, never a successful
check. Language selection does not translate machine fields.

The live session_check.py verified PASS/0, FAIL/1, UNKNOWN/2, ERROR/3 and Russian
JSON output on both the practice stack and original fixtures. It checked actual
HTTP 200/zero-row responses and the explicit approval guard, not arbitrary failures.
The CI workflow now runs this checker after E2E; that remote workflow has not been
executed for this local change. The last full Python run had 175 passes before
an additional console-interruption regression; the session module's final 37
regressions pass. Ruff and mypy checks passed during this follow-up.

Docker Desktop was found stopped during the initial live check, then restarted;
only checks after service readiness were counted as successful.


## Actual PostgreSQL 16/18 compatibility — 2026-10-25

The standalone compatibility runner pulled official postgres images and tested
actual server versions 160015 (16.15) and 180006 (18.6). Each collected/executed
8 integration tests, with 8 passes, zero skips and zero failures. The verified
execution counters come from the same guarded child runner used by E2E.
Image digests and counts are stored locally in ignored postgres-matrix.json.

Only uniquely named containers created for these checks were removed; cleanup
checks a per-run ownership label before deleting a container/anonymous volumes.
A subsequent docker listing showed no compatibility-labelled containers. Existing
Supabase fixture/practice stacks remained running. New unit regressions cover
owned cleanup, refusal to delete a foreign-labelled object and cleanup after a
test failure. CI now includes separate 16/18 jobs, not yet executed remotely.

A packaging audit found that the Python wheel lacked the root MIT license text.
An identical python/LICENSE copy was added; fresh package contents are being
verified before any publication. No license terms, authorship or version changed.


## Installed distributions and runtime matrix — 2026-10-25

Superseding earlier partial test counts: 203 non-integration Python tests passed
on all four local combinations of Node 22.23.4 / 24.22.1 and Python 3.12.14 /
3.13.17. The eight integration tests were deliberately deselected in those unit
invocations; actual full Supabase E2E including those eight tests passed separately
on both Python versions. All 46 SDK tests, TypeScript and ESLint passed on both Node
versions. These are separate local runtimes, not clean-machine installations.

The packaging checker builds wheel, sdist and SDK tarball, audits contents/license
texts, installs the wheel and tarball in separate consumer directories, exercises
the SDK file sink without consuming the response body, validates the resulting
event with the installed CLI, verifies installed CLI version and SDK public types,
and writes preview hashes/manifest. It passed using Python 3.12/3.13 with Node 24
and again with Python 3.13 / Node 22. The latest checked artifact directory is
`.rls-doctor/distribution-check-ja8_9l2g/artifacts`; these ignored local archives
are previews of the working tree, not published releases or immutable CI builds.

Managed sessions can link an explicitly selected captured event to a separate
local scenario without inventing omitted filter values or trusted identity.
Guided setup now retries individual invalid answers while retaining valid fields.
Unit and actual local request checks cover these paths. The trusted public identity
RPC explicitly uses the public profile independently of a table's selected schema;
custom-schema header routing has unit evidence, not a separate live schema trial.

An attempted dedicated Docker bridge with default host binding 127.0.0.1 did not
restrict the published ports in this Docker Desktop/Supabase CLI combination:
NetworkSettings.Ports still reported 0.0.0.0 and :: for API/database. The attempted
launcher change was withdrawn rather than presented as a working restriction.
No global Docker/firewall settings were changed. The existing stack publishing
behavior remains a documented local-environment limitation.


## Practice concurrency and launcher usability — 2026-10-25

The lab now holds a nonblocking OS lock across setup and its menu. Real subprocess
checks verify that another process is excluded and that abrupt process exit frees
the lock despite the persistent file. Error paths also release it. No credential
or PID is stored in that file. Separate test tools or direct Supabase commands
remain operator-managed; this guard coordinates lab launchers only.

All 205 non-integration Python tests passed on Python 3.12 / Node 24 and on
Python 3.13 / Node 22 after this change. Ruff and strict mypy passed. The full
18-row live lab checklist passed in English and Russian; the latter now localizes
all result labels, and the previously hidden PostgreSQL-regression menu item 20
is displayed. The PowerShell launcher checks minimum Node and pinned pnpm before
build, names the correct entry point in errors, and passed actual EN/RU launch
and cancellation on Windows PowerShell without preparing new users.

A Windows CI job was added to build the SDK, parse the launcher and execute unit,
privacy, shared-contract and real process-lock tests. It does not install Docker
or prove clean-machine Supabase onboarding. This new job remains unexecuted
remotely until maintainers commit/push and inspect its result.


The English practice-testing.md walkthrough now mirrors the functional scope of
the Russian guide: all menu items, intended negative results, JSON export, guided
configuration, developer checks and preserved-data stop/restart. Relative links
and UTF-8 were checked. The final local source run remains 205 unit/security/
contract passes, eight integration tests excluded in that invocation; the live
18-row lab check independently executed its PostgreSQL regression suite.


## Separate task-board app / installed packages — 2026-10-25

Implemented a maintained Node sample with its own task_board.tasks table, three
synthetic tasks, owner-scoped SELECT policy, public trusted identity probe and
separate Supabase project/ports 56321/56322. It does not reuse the documents tables
or fixture migrations. --check explicitly approves setup, two Auth signups and
updates of only the three seeded task IDs. Modified copied setup is preserved;
a project-scoped OS lock prevents overlapping sample checks. --stop preserves data.

Executed real app requests use the newly built/installed SDK archive plus pinned
supabase-js dependencies installed with npm ci in an ignored consumer. There are
no source SDK imports. The app reads its response, checks exact task membership,
awaits the real file sink, and emits only sanitized status/count/event-path metadata.
The newly installed Python wheel validates each event, runs managed JSON replay
with event linkage, confirms actual role, checks own/foreign task IDs and inspects
the actual custom-schema table with RLS enabled. Raw rows, titles and credentials
are checked for absence from event/report output.

Observed cases: Alice PASS / HTTP 200 / two own tasks; Bob PASS / HTTP 200 / one
own task; anonymous PASS / HTTP 200 / zero tasks. Confirmed roles were authenticated,
authenticated and anon respectively. This establishes actual custom-schema table
routing alongside the public identity RPC, superseding the prior unit-only limit
for that particular path. Event v1 still omits the original schema/profile; this
coverage does not establish reconstruction of arbitrary original requests.

The full installed-package/app flow passed on Node 24 with Python 3.12 and after
preserved-data stop/restart on Node 22.23.4 with Python 3.13.17. The latter used
artifacts in .rls-doctor/distribution-check-_1pgjf2b/artifacts. Sanitized persisted
results were re-read from task-board/run-dh7yn4x3 and task-board/run-g_6o397h.
Both had expected counts 2/1/0 and catalog evidence for task_board.tasks/RLS.

All 219 Python non-integration tests passed on both runtime pairs; the eight
integration tests are separately deselected in those unit invocations. Ruff
format/lint and strict mypy (24 source files) passed. New regressions cover
preservation/isolation, exact-membership scenario construction, intended runtime
and catalog evidence, private output rejection, and distinct project locks.

EN/RU sample walkthroughs and root/developer links were added and checked. The
local-integration CI job now runs and stops this sample, but that updated remote
workflow has not been executed. No package publication, clean-machine installation,
independent application adoption or independent maintainer review is claimed.

The sample was stopped after verification with data preserved. Existing fixture
and practice stacks remained running and healthy. No hosted project was linked,
no global Docker/firewall configuration was changed, and no other stack was reset.


## Master-prompt readiness audit, schema-independent doctor and report files — 2026-10-25

The requirement audit is docs/mvp-readiness.md. It maps specification sections
6–8/14–18/20–23 to implemented behavior, intentional privacy/scope limits and
remaining external release gates. CONTRIBUTING and the PR template remain removed
as requested by the user. The audit does not invent review, clean-machine or
current remote-CI results.

Doctor no longer inspects public.<first resource> merely to establish that anon
and authenticated roles exist. doctor_database reads those role records directly
inside the existing read-only transaction. Doctor reports their individual checks,
FAIL for missing required roles and UNKNOWN for unconfirmed API identity. It needs
no application tables in public. The installed wheel passed doctor against the
separate task_board sample, then all three owner/anonymous replay scenarios.

Direct --output export is available for validate/analyze/doctor/inspect/replay and
session --run. Generated JSON is written as UTF-8 with a 1 MiB bound. A fresh
same-directory temporary file is fsynced then published by atomic hard-link creation
which refuses replacement, including a destination created concurrently. Existing
paths are rejected before diagnostic/credential work. Error reports can be saved;
a publication failure returns ERROR/3 without replacing a file. POSIX mode starts
at 0600; Windows inherits folder ACLs. Hard-link-less filesystems fail explicitly;
hostile parent-directory replacement remains outside the filesystem boundary.

Observed checks:
- All 230 non-integration Python tests passed on Python 3.12.14/Node 24 and
  Python 3.13.17/Node 22.23.4; eight integration tests were deselected only in
  these unit invocations. Ruff format/lint passed; strict mypy passed 25 sources.
- Unit regressions cover four saved outcomes/codes, UTF-8 parity, existing-file
  preservation, a real competing-destination creation at publication, failed
  publication cleanup, size limits, redacted invalid-input reports and early
  rejection before database access. Doctor's missing-role/no-table branch is tested.
- Real fixture session_check.py verified PASS/0, FAIL/1, UNKNOWN/2, ERROR/3 and
  Russian JSON; each exported file equalled clean stdout and excluded known secrets.
- All six actual CLI commands were executed with --output against appropriate
  fixture/offline inputs: validate 0, analyze 2, doctor 0, inspect 2, replay 0,
  session 0. Files/stdout matched and known credentials were absent. Sanitized
  results are in .rls-doctor/export-check-7t_kbl5t.
- Installed-package task-board flow passed with doctor.json and session report
  files written by the installed CLI, not manually by the runner. Preview build:
  .rls-doctor/distribution-check-ublh_g1y/artifacts; app run: task-board/run-n9bpsmai.

session_check.py and task_board_check.py retain these assertions for CI. The
current remote workflow has not run. Independent review/reproduction and clean
Windows installation remain required release gates; the source is still a preview.


## Remote baseline and audited CI preview handoff — 2026-10-25

GitHub run https://github.com/Timon360SB/RLS-Doctor/actions/runs/40178244545
completed successfully for exact commit a91c9d5973e048b331fd41fff70265f3304ae085.
All eight jobs were read back as completed/success: all four Node 22/24 × Python
3.12/3.13 Linux pairs, Windows Node 22/Python 3.13, real Supabase/PostgreSQL E2E
including session export and installed task-board app, and PostgreSQL 16/18.
The workflow was triggered by the user's push; no dispatch/rerun/push was performed
by this work. This confirms that baseline, not subsequent working-tree changes.

Added explicit --github-output packaging handoff and a pinned upload-artifact
v7.0.2 workflow step. Its official action metadata uses node24; only the hosted
Linux checks matrix uses this new step. Artifacts are named by full source SHA,
Node/Python pair and run attempt, retained seven days, and restricted to the exact
verified artifact directory. The helper requires clean source matching GITHUB_SHA,
rejects extra files/directories/links and modified hashes/checksums, and refuses
CI metadata destinations inside the package directory. Local context is rejected
before build when the explicit CI-only flag is used.

The first strict bundle audit caught uv's generated .gitignore beside packages.
Intermediate Python builds now stay in a separate python-build directory; only
the explicit wheel/sdist are copied into the final export directory. A fresh full
build/install check passed with exactly three archives plus SHA256SUMS/manifest.
Verified local bundle: .rls-doctor/distribution-check-03ch956z/artifacts. It is a
working-tree preview with honest dirty state, not a released or clean-source CI
artifact. Actual new upload-step execution remains pending a subsequent commit/run.

All 241 non-integration tests passed locally on Python 3.12/Node 24 and Python
3.13/Node 22; eight integration tests were deselected in these invocations. New
regressions cover modified/unexpected bundle contents, preserved CI step outputs,
clean matching SHA, metadata isolation and explicit CI context. Ruff format/lint
and strict mypy (25 package source files) passed. Workflow handoff/retention fields,
the actual five-file bundle and EN/RU guide links were checked.

Independent release-review checklists now record the exact candidate, tool
versions, both languages, the 18-row lab, preserved-data restart, installed app
counts/doctor/export and safe issue reporting. No second maintainer has been
reported as having completed them. Clean Windows onboarding and independent human
review/reproduction remain required; source/co-author metadata is not a substitute.


## Existing databases first - 2026-10-26

Added `diagnose` for an explicitly approved existing PostgreSQL/Supabase table
and role. No fixture setup, scenario, SDK or identity probe is required. The
connection reads access-control catalogs in a bounded read-only transaction;
customer table rows and policy expressions are not collected. Runtime visibility
remains UNKNOWN even when concrete catalog problems are established.

Connection tests cover approval before DNS, exact hostname matching, verified
remote TLS, rejected connection overrides, and hidden credential input. A live
local run inspected existing documents, no_grant_documents and leaky_documents
without fixture preparation, new users, writes or application HTTP requests.
Missing SELECT was observed. Actual remote TLS/database access remains unverified.

The optional advanced scenario wizard supports typed filters and row assertions;
it remains a supporting local workflow. All 271 non-integration Python tests
passed on Python 3.12/Node 24 and Python 3.13/Node 22; eight integration tests were
deselected. Ruff and strict mypy (27 package sources) passed.

Installed-package verification produced
`.rls-doctor/distribution-check-qeyw2sv3/artifacts/manifest.json`, including
installed-diagnose-help, installed-event-contract and offline-unknown checks.
These are working-tree preview artifacts, not a release or current remote CI run.
