> MVP usability follow-up: start menu, runtime-only Windows launcher, separate
> connection fields, reconnect, target/language selection, explicit export and
> bounded schema overview are implemented. New isolated runtime/tool installs do
> not substitute for clean-machine or independent human acceptance. The release
> gates below remain open for the final committed revision.
>
> Current existing-database workflow: connect/diagnose, non-secret profiles, bound
> schema 1.1 capture, opt-in Auth verification, narrow server-side policy shapes
> and guided investigation are implemented. Real controlled TLS/least-privilege
> and local Supabase SDK/Auth checks exist in scripts/database_check.py. By user
> choice the external-connection check uses this isolated TLS stand; no actual
> external hosted/customer project is claimed. The historical table below describes
> the original local MVP; its old counts/remote baseline are not current-code CI.

# MVP readiness audit

Scope: specification.md sections 6–8, 14–18 and 20–23. Status as of 2026-10-25.
This is a source/evidence audit, not a published release or security certification.
The user's removal of CONTRIBUTING.md and the pull-request template takes
precedence over the original documentation list; neither is restored.

## Requirement coverage

| Requirement | Current implementation / evidence | Remaining boundary |
| --- | --- | --- |
| RC-01, RC-05: Fetch integration and failure isolation | Opt-in Node wrapper, request/response preservation, sink failures separated; SDK tests and actual supabase-js application | No browser SDK in v0.1 |
| RC-02, RC-03: minimal private events | Shared strict v1 contract, metadata allowlist, no tokens/rows/filter values; installed producer/consumer checks and live sample output guards | Raw response error codes are not parsed; error kind/status only. This is an explicit privacy constraint, not full SQLSTATE diagnosis |
| RC-04: capture controls | Enabled flag, resource/origin allowlist, stop, capture time/count limits, bounded local file sink | No silent capture or remote collection |
| ID-01–03: identity/evidence | Header presence separated from verified local test JWT and trusted executed-role probe; OBSERVED/INFERRED/UNVERIFIED | Captured headers do not verify the original caller; no trusted probe means UNKNOWN |
| PG-01: local connection | Validated numeric-loopback DSN, Psycopg read-only transaction, bounded catalog inspection | Loopback cannot rule out operator-configured forwarding |
| PG-02: metadata | RLS/FORCE, grants/schema/column rights, role membership, owner/bypass behavior, policy operation/composition and predicate-presence flags | USING/WITH CHECK SQL text is deliberately omitted to avoid retaining raw SQL/literals. Arbitrary predicate semantics are not evaluated |
| PG-03–04: conclusions and limits | Missing grants/policies, disabled/bypassed RLS and observed catalog facts; real PostgreSQL regression evidence | Views/functions/partition entry points and runtime row visibility require separate checks |
| RP-01–05: replay | Explicit synthetic local table GET, approved ports/resources, bounded responses, redirect/write rejection | No original-value reconstruction, production replay or writes |
| CP-01–03: comparisons | Status/count/error class, explicit contains/excludes and completeness checks, four outcome codes | Counts alone do not prove row isolation; empty rows do not prove RLS denial |
| §7–8: console/JSON CLI | init/validate/analyze/doctor/inspect/replay/session, bilingual presentation and direct --output JSON export | session export requires --run; existing files are preserved |
| §15: mandatory negative scenarios | Missing auth, missing policy/grant, tenant leak, nonexistent-row ambiguity and invalid inputs in lab/E2E | Synthetic examples do not certify a user's application |
| §18.1–12: local functional chain | Installed SDK + wheel exercised with separate task-board app, two owners/anonymous access, custom schema/public probe and persisted reports | Maintained example, not independent third-party adoption |
| §18.13: automatic GitHub checks | Linux/runtime matrix, Windows unit job, actual Supabase/sample app and PostgreSQL compatibility jobs defined | Latest working-tree changes have not completed a remote run |
| §18.14: independent reproduction | Reproducible EN/RU practice/sample guides | Requires two actual maintainers to reproduce/review; no substitute claim from automated tests |
| Clean environment | Isolated package consumers and separate runtime versions checked locally | Not a fresh Windows installation; clean-machine onboarding remains unverified |

## Prioritized findings and actions

### P0 — correctness

1. **Fixed: doctor assumed an application table in public.** A custom-schema
   application could pass replay but fail environment validation. Required-role
   availability is now read directly from pg_roles inside the read-only catalog
   transaction. Doctor needs no application table, reports individual role checks,
   and retains UNKNOWN when API/runtime identity is unconfirmed.
2. **Retain existing evidence boundaries.** Event schema/profile omission, no
   predicate evaluation and no original identity reconstruction are explicit
   constraints. They must not be hidden by positive outcome labels.

### P1 — usable release candidate

1. **Implemented: direct report export.** --output writes generated UTF-8 JSON
   for validate/analyze/doctor/inspect/replay and session --run, while preserving
   normal console or clean JSON stdout and outcome exit codes. Error reports may
   also be saved. Existing destinations are rejected before diagnostic work.
   Atomic hard-link publication refuses concurrent replacement; file size is
   capped at 1 MiB. POSIX files begin with mode 0600; Windows uses inherited ACLs.
   A filesystem without hard-link support returns REPORT_WRITE_FAILED rather than
   weakening the no-overwrite behavior. Hostile parent-directory replacement is
   outside the documented filesystem boundary.
2. **Remote baseline verified; follow-up needs a fresh run.** All eight jobs in
   [run 40178244545](https://github.com/Timon360SB/RLS-Doctor/actions/runs/40178244545)
   passed for a91c9d5973e048b331fd41fff70265f3304ae085, including actual Supabase,
   Windows, both compatibility jobs and all four runtime pairs. The subsequent
   CI preview-retention changes need their own committed remote run; this green
   baseline does not verify later code.
3. **Pending external evidence: clean Windows onboarding.** Use
   [the acceptance checklist](release-review.md) / [Русский](release-review.ru.md). Follow the practice
   guide in an ordinary terminal on a clean machine and record installation,
   paths, language, setup, successful/negative results and stop/restart behavior.
4. **Pending human evidence: independent maintainer review/reproduction.** Review
   both workstreams and reproduce the demonstration without private setup notes.
5. **Release only after those gates.** Preserve preview/private package status
   until explicitly authorized release/version/package publication work.

### P2 — outside this MVP

Browser capture, HTML/dashboard UI, arbitrary SQL interpretation, automatic
fixes, writes and remote replay remain separate designs. Adding them would not
resolve the current release evidence gaps.

## Release decision

The core local workflow is implemented with executed evidence. The product is
approaching a release candidate, but §18's remote CI, clean-machine and
independent-reproduction requirements are still open. Do not label the public
MVP complete or claim production/security guarantees from the current results.
See verification.md for exact commands, counts and runtime evidence.
