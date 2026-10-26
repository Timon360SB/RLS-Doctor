# Troubleshooting

For existing databases, see [English](existing-database.md) / [Русский](existing-database.ru.md).
Connection errors now include a fixed category, next action and SQLSTATE when available.
The local replay-specific guidance below applies only to disposable test workflows.

| Symptom | Safe next step |
| --- | --- |
| LOCAL_APPROVAL_REQUIRED | Review the disposable fixture destination before enabling approved_local. |
| UNSAFE_ENDPOINT / UNSAFE_DATABASE | Use the explicit numeric loopback origin/host and configured port; remove libpq service/options and URL credentials. |
| MISSING_CREDENTIAL | Set the named local-test environment credentials in your private shell; never put values in reports. |
| INVALID_TEST_TOKEN | Obtain a fresh local Auth access token; check local issuer, audience, expiry, signature/key and role. Decoding claims is not verification. |
| UNKNOWN executed_role | Install the supplied trusted identity probe in the disposable fixture stack. Do not infer a role from headers. |
| UNKNOWN result_completeness | Request a bounded synthetic dataset; check a consistent Content-Range and the local server row cap. |
| HTTP 200 with zero rows | Verify fixture existence/ownership and explicit filters before examining applicable policies. This alone does not prove RLS rejection. |
| Permission error / 42501 | Check schema USAGE and exact table/column grants; a policy cannot replace SQL privileges. Policy functions can also raise errors, so do not overstate the cause. |
| POSTGRES_INSPECTION_FAILED | Follow error.diagnostic and SQLSTATE when present. Without SQLSTATE, TLS/network/authentication causes may remain unverified. Raw server/DSN text is suppressed. |
| RESOURCE_NOT_ALLOWED | Explicitly approve the intended local resource; do not widen to arbitrary endpoints. |
| RESPONSE_ENCODING / RESPONSE_LIMIT | Use uncompressed, smaller synthetic responses; do not disable the limits. |
| Python contract test cannot find SDK dist | Run pnpm build first. |
| Integration tests skipped | Set explicit disposable DB DSN and fixture setup consent, or use the real Supabase E2E stdin pipeline. A skip is not a pass. |

Sanitized bug reports should include command/version, result code, synthetic
scenario and fixed diagnostic codes. Exclude tokens, keys, DSNs, query values,
server error bodies and customer data. Do not enable verbose third-party logs
around secrets just to obtain additional context.


| Report export code | Safe next step |
| --- | --- |
| REPORT_EXISTS | Choose a new --output filename; existing files are never replaced. |
| REPORT_WRITE_FAILED | Use a writable local folder/filesystem supporting hard links; check available storage and permissions. |
| REPORT_LIMIT | Reduce the diagnostic scope; the generated report exceeds 1 MiB. |
| SESSION_OUTPUT_MODE | Add --run; one saved session report represents one execution. |

Doctor checks required roles directly in catalog metadata; application tables
may live outside public. A missing required role yields FAIL. An opted-out or
unconfirmed identity probe retains UNKNOWN even when role availability passes.


## Operational categories

The existing error.code remains available. error.diagnostic adds a fixed category,
evidence, English summary and next_steps. Console mode localizes these to EN/RU.
DNS failure, host/profile mismatch, unsupported DSN options, CA-file availability,
client timeout and protocol-reported password requirements are separate cases.
When the server supplies a valid five-character SQLSTATE, it is retained, including
inside a failed replay inspector component. Examples: 42501 insufficient privilege,
28P01 rejected password authentication, 3D000 missing database, 57014 cancelled query,
55P03 unavailable lock, 53300 connection limit and 57P03 server not ready.

SQLSTATE does not identify the exact object or establish an application's RLS
root cause. Client connection failures often have no SQLSTATE; these remain
UNVERIFIED instead of guessing between certificate, network and credential errors.
Raw exception messages, server details, SQL, DSNs and passwords are not exported.
See [PostgreSQL error codes](https://www.postgresql.org/docs/18/errcodes-appendix.html).

Every CLI report carries report_version, diagnosis_id and diagnosed_at (UTC).
Captured-request time is separate in captured_at; legacy timestamp fields remain.
Saving and displaying the same report preserves its ID/time and all observations.
