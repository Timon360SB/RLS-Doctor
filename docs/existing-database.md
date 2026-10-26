# Diagnose an existing database

[Русский](existing-database.ru.md)

Use Python and uv for your PostgreSQL/Supabase database. No Docker, Node.js,
fixture users or YAML scenarios are required. Node.js is needed only for optional
application SDK integration.

## Start with the assistant

On Windows run `.\rls-doctor.cmd` from the checkout; it prepares the locked runtime.
Other systems: `uv run --project python --python 3.12 --frozen --no-dev rls-doctor start`.
First run uses separate connection fields, then shows the first report and a menu.
Subsequent launches reuse the profile. Approval/password are requested once when
needed; no connection is made just to switch language or close the menu. The menu
can diagnose, select a different table/role for this session, show a schema overview,
save the last report or forget session credentials. Profile selection is not silently overwritten.

`connect` also uses separate fields. For a ready-made DSN use
`connect --connection-string`; entry remains hidden. An explicitly configured
RLS_DOCTOR_DATABASE_URL environment reference works as before. Use a direct/session
endpoint supporting ordinary transactions; a Supabase API key is not a DB password.

## Review a schema

`rls-doctor overview` reuses the profile schema/role; override with `--schema` and
`--role`. Default 30 tables, maximum `--limit 50`. One read-only snapshot summarizes
grants, RLS applicability and default-deny. BLOCKED is a basic access obstacle;
REVIEW means disabled/bypassed RLS or column-scoped SELECT; NO_BASIC_BLOCKER is not
proof of runtime visibility. Complex predicates are not interpreted here.
The table-name limit is applied before priority sorting and truncation is explicit.
Only simple-name ordinary/partitioned tables are listed; other objects are omitted.
A 30-second budget is checked between tables, in addition to per-query timeouts.
JSON/output and approval rules match diagnose. No user rows are read.

## Guided connection and reuse

```powershell
uv run --project python --python 3.12 --frozen --no-dev rls-doctor connect
```

Enter the database hostname/IP, approve catalog-only access, then fill in port,
database, user, optional CA file and the hidden password. Use --connection-string
for a ready-made DSN instead. Select a table and role by number. Optionally enter your
Supabase API origin (HTTPS origin only, no paths, keys or query parameters).

The wizard verifies read-only catalog access, inspects the selection and saves
`.rls-doctor/project.json`. This ignored runtime file contains host, port, database,
username, table, role, TLS mode/CA path, optional API origin and a random project UUID.
It contains no password, DSN or token. Choose a different new path with --profile;
existing files are refused. Successful setup exits 0; the report still states UNKNOWN
row visibility.

```powershell
uv run --project python rls-doctor diagnose
uv run --project python rls-doctor diagnose --profile PATH_TO_PROFILE.json --guide
```

Repeat diagnosis asks for approval and only the hidden password. No DSN copying is
needed. For unattended use supply RLS_DOCTOR_DATABASE_URL privately, then add
--approve-read-only --format json. The DSN must match the saved host/port/database/user.
Never place real credentials in arguments, reports, Git or chat.

The original explicit form remains available without a profile:

```powershell
uv run --project python rls-doctor diagnose public.orders --host YOUR_DATABASE_HOST --role authenticated
```

This prompts for a hidden DSN or uses --connection-env NAME. A saved profile defines
its own environment-reference name.

## Investigation and policy shapes

The report orders grant/default-deny blockers, RLS applicability, authorization,
policy conditions and remaining row-visibility questions. --guide asks only
coarse yes/no/unknown questions about independent data existence, actual filters
and runtime role checks. It never asks for row values, tokens or SQL. Operator
statements remain UNVERIFIED; they cannot promote the outcome to a proven cause.

Server-side structural classification recognizes constant true/false and exact
comparisons of auth.uid() with a column, including a simple SELECT auth.uid() form.
It respects permissive OR versus restrictive AND composition. Both USING and
WITH CHECK are described structurally. Raw expression text/literals never leave
PostgreSQL; policy functions are not executed. Complex expressions, casts,
unsupported types and hidden dependencies remain unrecognized. No arbitrary
predicate evaluation or automated SQL repair is performed.

## Bind application metadata

Use the projectId and allowedOrigin printed by connect in your SDK options:

```typescript
import { createCaptureFetch, createJsonFileSink } from '@rls-doctor/capture-sdk';

const captureFetch = createCaptureFetch(fetch, {
  enabled: true,
  projectId: 'UUID_FROM_CONNECT',
  allowedOrigin: 'https://YOUR_PROJECT.supabase.co',
  resources: ['orders'],
  verifyAuth: true,
  sink: createJsonFileSink({ directory: '.rls-doctor/captures' }),
});
// Supply captureFetch as global.fetch when creating your Supabase client.
```

Project binding opts into event 1.1: project UUID, API-origin SHA-256 (never a token
hash), Accept-Profile schema and simple selected-column names. Complex projections
are unknown. Filter values and customer rows are omitted. Without projectId the SDK
continues to emit event 1.0. New readers accept both versions; old 1.0-only readers
reject 1.1 explicitly. Use matching SDK/Python previews for binding.

verifyAuth defaults off. Enabling it explicitly permits an extra GET /auth/v1/user
to the same origin with that request's headers. Redirects are refused; the check
is bounded to 3 seconds/32 KiB. Auth data is inspected only in memory; the event
contains a state, never user ID/email/token/body. Application request arguments,
Promise and Response are preserved, and its body is never read. The application
response is not held back; the diagnostic event may arrive later.

```powershell
uv run --project python rls-doctor diagnose --event PATH_TO_EVENT.json --guide
```

Bound events require the saved profile. Mismatched project ID, API-origin digest,
schema or resource is rejected before connecting. A configuration match is not
cryptographic proof of actual API-to-database routing. A valid Auth user session
does not establish the executed PostgreSQL role or an earlier auth.uid value.
The captured event is not replayed.

## Remote TLS and least privilege

Prefer a restricted inspector account; customer-row SELECT is unnecessary for
catalog access. Provider-specific catalog restrictions may still apply. Use a
direct/session endpoint supporting normal transactions and startup settings.
Client certificate and GSS authentication are unsupported.

Non-numeric-loopback hosts require verify-full TLS (trusted CA and server-name
verification). sslrootcert defaults to system; supply an operator-trusted CA file
for private CAs. Its absolute path is retained in the profile, not its contents.
The locked Psycopg binary uses libpq 18. Placeholder-only DSN example:

```text
host=YOUR_DATABASE_HOST port=5432 dbname=postgres user=INSPECTOR password=YOUR_PASSWORD sslmode=verify-full sslrootcert=PATH_TO_TRUSTED_CA
```

Numeric loopback permits sslmode=disable. Arbitrary options/service/hostaddr and
multi-host DSNs are rejected. DNS pins the first IPv4 address, or the first other
address family; automatic connection failover is not implemented. The hostname
remains available for certificate verification.

## Troubleshoot an operational failure

Errors include diagnosis ID/time, a fixed category and a next action. Follow the
reported category: DNS, host/profile mismatch, unsupported connection settings,
CA-file availability, client timeout or a server SQLSTATE. Common SQLSTATE values:
42501 insufficient privilege, 28P01 password authentication rejection, 3D000 missing
database, 57014 cancellation, 55P03 lock unavailable, 53300 connection limit and
57P03 server not ready. No exact object names or server-message details are exported.

A connection failure without SQLSTATE remains UNVERIFIED: the tool does not guess
whether TLS, routing or credentials caused it. Check the approved endpoint/port,
network, trusted certificates and private credential source. Keep verification on.
See [troubleshooting](troubleshooting.md) for the machine-readable error structure.

## Results and export

All CLI reports include diagnosis_id and diagnosed_at (UTC). captured_at keeps
the original request time separate; legacy timestamp fields remain compatible.
Reports include the selected role, privileges, RLS/FORCE, policy
shapes and ordered next actions. Captured-request time is separate. UNKNOWN runtime
visibility does not hide established configuration blockers. connect/diagnose never
change rows, policies or users, and never execute application queries/probes.

```powershell
uv run --project python rls-doctor diagnose --approve-read-only --format json --output .rls-doctor/reports/database-1.json
```

Supply the DSN privately beforehand for JSON mode. Existing exports are preserved.
diagnose exit codes remain 0 PASS, 1 FAIL, 2 UNKNOWN, 3 operational error.

Real verification covers disposable TLS PostgreSQL with a restricted inspector,
CA/name/expiry rejection, and local Supabase SDK/Auth integration. No actual
external hosted/customer project has been verified yet.
