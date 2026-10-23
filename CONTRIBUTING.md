# Contributing

Read AGENTS.md and docs/development.md. Open an issue describing a reproducible
problem using only sanitized events and synthetic data. Work on a feature branch;
submit a PR and run the documented checks before review. Shared schema/security
changes require review across both engineering workstreams. No fabricated
maintainer identities, reviews, commits, stars or usage statistics.

Application diagnostics owns packages/capture-sdk and the Node integration;
database diagnostics owns python and catalog/replay behavior. Both share schemas,
security, fixtures and CI. CODEOWNERS remains comments until real maintainers
confirm their GitHub accounts. This does not establish a two-person review record.

PRs should explain observable behavior, evidence and limitations. Include a
regression test for a bug; use real PostgreSQL/Supabase tests for database claims.
Do not include credentials, customer rows, raw request/error bodies or full URLs.
Do not auto-publish packages, releases, policies or infrastructure changes.

After independent testing, maintainers can track opt-in feedback using issue
labels and a manual aggregate: independent testers, external projects, reproducible
reports, resolved defects, returning testers and outside contributors. No automatic
telemetry is included and no testers or adoption are claimed.
