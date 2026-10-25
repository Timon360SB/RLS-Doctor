# MVP development plan

This follows specification stages 1–8. Technical source completion is separate
from independent review, clean-machine verification and publication.

Detailed requirement coverage and remaining release gates: [MVP audit](mvp-readiness.md).

## P0 — diagnostic correctness and usable local workflow

- Implemented and locally verified: opt-in SDK, shared event contract, offline
  analysis, catalog inspection, explicit synthetic GET replay and full fixture E2E.
- Implemented: one-command Windows demo; English default and explicit Russian.
- Implemented: guided project configuration with per-field correction, readable
  bilingual reports, managed console/JSON sessions and optional captured-event
  linkage. Evidence remains separated; credentials stay scoped in memory.
- Implemented: isolated practice database and 18-step functional walkthrough in English and Russian,
  with an OS lock preventing competing lab launchers.
- Implemented: schema-independent doctor role checks and direct no-overwrite
  UTF-8 JSON export for CLI diagnostics and unattended managed sessions.
- Retain UNKNOWN for unconfirmed runtime roles, incomplete results or undecidable
  policy behavior. Count-only scenarios do not establish row isolation.

## P1 — release readiness (specification stage 7)

- Local package installation checks now cover SDK archives and Python wheel,
  license/schema contents, installed types/file sink/CLI contract and preview
  checksums. Node 22/24 and Python 3.12/3.13 have local regression evidence.
- Real PostgreSQL 16/18 compatibility runners execute eight guarded integration
  tests per server and clean up only owned containers.
- Reproduce onboarding on a clean Windows machine; the current launcher expects
  Docker, Node.js, pinned pnpm and uv and guides installation of missing prerequisites.
- Managed credential onboarding is implemented for running disposable local
  Supabase projects: matching CLI status, scoped credentials and explicit test
  signup. General identity-probe provisioning and application fixture preparation
  remain separate work; no application schema changes occur automatically.
- Implemented/local pass: separate task-board sample application, installed SDK
  archive + CLI wheel, custom schema, two authenticated owners and anonymous
  access. This maintained example does not establish independent adoption.
- Remote CI passed all eight jobs for a91c9d5; subsequent preview-retention
  changes require another committed run. Preserve exact-commit evidence.
- Added EN/RU independent acceptance checklists and audited CI-preview retention;
  the retention step is not remotely verified yet.
- Obtain independent maintainer review and reproduction before release.
- Publish packages/release only when separately authorized and ready. Preserve
  the user's removal of CONTRIBUTING and the pull-request template.

## P2 — after MVP / separate design

Browser capture, HTML reports, dashboards, arbitrary policy interpretation,
writes, remote replay, automatic fixes and automatic schema changes are outside
this implementation. Gather actual user feedback only after the public MVP.

## Ownership and dependencies

TypeScript workstream owns capture/integration; Python workstream owns setup,
inspection, replay and reports. Shared event-contract changes require joint
review. The guided-CLI follow-up changes presentation and local configuration,
not the TypeScript/Python event schema or machine-readable report fields.
