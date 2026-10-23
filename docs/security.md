# Security boundaries

The supported threat model is an operator-approved disposable local Supabase
stack with synthetic data. A malicious local service, tunnel, database extension
or compromised operator machine is outside a strong isolation guarantee.

Capture allows an exact origin and simple resource names. It preserves the
original fetch arguments/Promise/Response and reads no body. It stores only
versioned allowlisted metadata. Authorization/apikey presence are booleans;
neither establishes user identity. Capture defaults off and limits recording time
and accepted event count. Sink failures report fixed codes, never raw exceptions.
Dedicated sink directories reject symlink/junction components and exclusive file
creation prevents overwrite. Windows ACL privacy remains an operator requirement;
concurrent hostile filesystem replacement is not solved by these checks.

Replay permits numeric loopback HTTP endpoints and configured ports/resources.
HTTPX ignores ambient proxies and does not follow redirects. User-authored RPCs,
writes, raw SQL/shell, unknown YAML keys, aliases and reserved parameter overrides
are rejected. Input files are bounded before parsing. HTTP response memory and
rows are bounded; compression is refused. All response data is synthetic and held
in memory only for comparison. No raw errors or table rows enter reports.

Authenticated tokens are verified cryptographically using the local JWKS or an
explicit local HS256 test secret. Algorithm, expiry, issuer, audience and role are
checked. The hard-coded trusted fixture identity RPC additionally confirms the
executing role/subject. An unavailable probe leaves the actual role unknown.
Legacy anon JWTs require the local signature and anon role. Opaque publishable keys
cannot independently establish project provenance; obtain them from the approved
local stack. A loopback address alone cannot identify or exclude a forwarded
production backend. Never supply production credentials.

The inspector uses fixed parameterized catalog queries with statement/lock
timeouts and a repeatable-read, read-only transaction. The validated DSN pins
hostaddr to the explicit local numeric host and rejects libpq service/options
overrides. Policy expressions are not collected, because their literals may
contain sensitive values. No diagnostic operation applies migrations or repairs
policies. Fixture setup is a separate explicit write-capable action.

No telemetry, collector or paid service is present. For reporting vulnerabilities,
follow the repository SECURITY.md; no unverified reporting destination is assumed.
