# RLS Doctor Python CLI

Read-only PostgreSQL/Supabase access diagnostics. Requires Python 3.12+.
Run `rls-doctor connect` to choose your existing database table/role, then
`rls-doctor diagnose --guide` to reuse its non-secret profile. Use --language ru
for Russian. Passwords/DSNs are not persisted. No Docker is needed for diagnosis.

See [connection guide](../docs/existing-database.md) /
[Русский](../docs/existing-database.ru.md) for TLS, bound SDK events and limits.
Explicit local synthetic replay remains an optional supporting workflow.
