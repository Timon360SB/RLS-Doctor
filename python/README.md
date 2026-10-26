# RLS Doctor Python CLI

Read-only PostgreSQL/Supabase access diagnostics. Requires Python 3.12+.
Start with `rls-doctor start`: first-time connection uses separate fields, then
opens an EN/RU menu for table diagnosis, schema overview, target selection,
JSON export and reconnect. Subsequent launches reuse the non-secret profile.
Use `--language ru` for Russian. No Docker, Node.js, fixtures or YAML are needed.

From the checkout install with `uv tool install --python 3.12 ./python`, or use
`uv run --project python --python 3.12 --frozen --no-dev rls-doctor start`.
The Windows repository launcher is `rls-doctor.cmd`.

For automation use `diagnose` or `overview` with explicit approval and JSON output.
Profiles contain connection/catalog metadata; passwords, full DSNs and tokens are
not saved. Runtime row visibility can remain UNKNOWN even with concrete findings.

See [connection guide](../docs/existing-database.md) /
[Русский](../docs/existing-database.ru.md) for TLS, bound SDK events and limits.
Explicit local synthetic replay remains an optional supporting workflow.
