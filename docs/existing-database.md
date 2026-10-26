# Diagnose an existing database

[Русский](existing-database.ru.md)

The primary workflow reads access-control settings in your existing PostgreSQL or
Supabase database. No fixture, synthetic user, YAML scenario, SDK or identity RPC
is required. The command reads catalogs only in a read-only transaction, with
statement/lock timeouts. It does not query customer rows or change policies.

## Connect

From the source checkout, install Python dependencies with
`uv sync --project python --frozen`, then run:

```powershell
uv run --project python rls-doctor diagnose public.orders --host YOUR_DATABASE_HOST --role authenticated
```

Replace table, exact host and role with your real target. Explicitly confirm the
catalog-only connection. If RLS_DOCTOR_DATABASE_URL is not already supplied through
your private environment/secret manager, paste the PostgreSQL connection string
into the hidden terminal prompt. It is not saved. Never put the real DSN/password
in command arguments, Git, reports or chat. Do not use a Supabase API key here:
this is a PostgreSQL connection. Prefer a least-privilege inspection login.

Node.js, pnpm and Docker are not required for this Python catalog-only command.
The local lab and SDK remain optional, separately documented workflows.

## Remote TLS

Non-loopback connections require verify-full TLS: both CA trust and hostname
verification. The DSN may specify sslrootcert with a trusted CA file provided by
your database operator; otherwise libpq uses sslrootcert=system. A provider using
a private CA requires its CA, not a weaker TLS mode. This implementation uses the
locked Psycopg binary/libpq 18 client; client-certificate/GSS authentication is not
supported by this initial path. Use a direct/session database endpoint that accepts
ordinary PostgreSQL transactions and startup settings.

Example connection-string structure for the hidden prompt (placeholders only):

```text
host=YOUR_DATABASE_HOST port=5432 dbname=YOUR_DATABASE user=INSPECTOR password=YOUR_PASSWORD sslmode=verify-full sslrootcert=PATH_TO_TRUSTED_CA
```

An explicit numeric loopback connection can use sslmode=disable for local services.
Host/port/database/user are required. Arbitrary options, service files, hostaddr
and multi-host overrides are rejected; resolved IP is pinned while TLS verifies
the approved hostname. The existing local replay allowlist is unchanged.

## What you receive

The report shows RLS/FORCE RLS, role/owner/bypass information, schema/table/column
privileges and policy applicability/composition. Missing SELECT, schema USAGE or
permissive policies are concrete configuration findings. Policy expressions and
user rows are not collected, so actual request identity, predicate behavior and
row visibility remain unverified. UNKNOWN refers to that runtime uncertainty;
individual catalog facts remain useful and explicitly labelled.

For unattended output, supply the chosen environment reference privately:

```powershell
uv run --project python rls-doctor diagnose public.orders --host YOUR_DATABASE_HOST --approve-read-only --format json --output .rls-doctor/reports/database-1.json
```

JSON mode never prompts for approval or credentials. Use --connection-env NAME for
a different environment reference. Existing output files are preserved.

## Verification boundary

The catalog-only command was executed against existing local PostgreSQL tables,
including missing-GRANT diagnosis, without setup/users/HTTP requests. Remote host
matching, TLS requirements and rejection/privacy paths have automated tests.
No actual hosted/customer database or remote TLS connection has been verified yet.
