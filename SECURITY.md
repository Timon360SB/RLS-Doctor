# Security policy

This initial implementation supports only explicitly approved disposable local
test environments. It is not a security certification or a production scanner.
No published version is currently designated as supported for production.

Do not post secrets, customer data, raw tokens or exploit credentials in public
issues. Report a vulnerability using GitHub's private vulnerability reporting
interface **if the repository owner has enabled it**. Otherwise ask the owner for
a private reporting route without disclosing the sensitive details. No reporting
email address or private reporting configuration is invented here.

Capture is opt-in, bounded and allowlist-based. Only Node.js Supabase REST table
GET metadata is supported. No body, raw header, token or URL query value is stored.
File permissions use POSIX 0700/0600 where available; Windows deployments must
use a private directory with appropriate inherited ACLs. Hostile concurrent local
filesystem replacement is outside the sink's guarantee.

Replay uses numeric loopback origins and explicit ports/resources; proxies and
redirects are disabled. Tokens require a verified local signature and claims.
Opaque publishable API keys cannot be independently attributed to a project;
the operator must obtain them from the approved local stack. Loopback tunnels,
malicious local services, trusted fixture tampering, functions and extensions can
weaken the environment boundary. GET and read-only SQL are not universal protection
against external side effects in a malicious database. See docs/security.md.

Do not use production credentials even with a local endpoint. Diagnostics never
apply migrations; the clearly labeled fixture setup is separate and may write
synthetic users/data only in an approved disposable instance.
