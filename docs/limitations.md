# Limitations

- This is an initial source implementation, not a released or certified product.
- Node.js capture only. No browser integration or arbitrary network interception.
- Events contain no replay values, raw user identity, JWT claims, body or SQLSTATE
  parsed from an HTTP response. Error kind is metadata only; some counts are unknown.
- A captured event cannot faithfully reconstruct a production request. YAML is an
  explicit synthetic test scenario. Only REST table GET requests are supported.
- Replay supports only numeric loopback HTTP endpoints with explicit allowed ports/resources. DNS aliases, remote replay, redirects and compressed responses fail
  closed. Loopback forwarding remains an operator risk.
- Replay requests at most 1000 rows and buffers at most 1 MiB. Reaching the row
  cap or failing to establish completeness yields UNKNOWN rather than proving a
  foreign row absent. No pagination or arbitrary PostgREST filters in v0.1.
- JWT verification accepts local HS256, ES256 and RS256. No token refresh or
  automatic production session reuse. A trusted identity probe is fixture-specific.
- Raw policy predicate text is deliberately omitted. Existing-database diagnosis classifies
  a narrow set of constant/UID-equality shapes on the server without exporting literals.
  Inspection reports operation,
  role applicability, permissive/restrictive composition and predicate-presence
  flags; it cannot evaluate arbitrary functions or establish intent/row visibility.
- Views, foreign tables, hidden function dependencies and partition/inheritance
  entry-point behavior need separate design and runtime checks.
- PostgreSQL 16/17/18 branches are selected by the inspector. Real regression
  runs passed on PostgreSQL 16.15, 17.10, Supabase 17.11 and PostgreSQL 18.6.
  These observations cover the tested versions and scenarios, not every minor release.
  Complete local Supabase E2E passes; fresh remote CI for the latest changes,
  clean-machine onboarding and independent review remain pending. See verification.md.
- Guided init writes local configuration and synthetic expectations only. It does
  not collect credentials or install a trusted identity probe into an application.
  Without such a probe, executed role remains unconfirmed and replay may return
  UNKNOWN. Row counts alone do not prove exclusion of another user's records.
- Console and JSON only. No web UI, editor extension, writes, automatic fixes or
  broad security certification. No two-human review or independent adoption claim.
- File modes protect new POSIX capture files; Windows needs appropriate ACLs.
  Hostile concurrent directory replacement is outside the filesystem boundary.

- Managed session reads credentials only from a selected running local Supabase
  CLI project whose destination matches the approved configuration. It does not
  install system prerequisites or start/reset the user's stack automatically.
- Synthetic Auth signup is explicit, may require local email-confirmation setup,
  and does not prepare application rows. Accounts are not automatically deleted.
  Existing local test-token references remain available; privileged API keys are
  rejected. No runtime identity assurance is added without a trusted probe.

- Supabase CLI/Docker Desktop may publish the local fixture/practice API and
  database ports on all host interfaces. Numeric-loopback replay limits outbound
  destinations; it does not restrict Docker's inbound port publishing. A dedicated
  bridge default binding was tested here and did not override that behavior.
  Use this synthetic environment only on a trusted development computer/network;
  custom host firewall/network configuration remains operator-managed.

- Event v1 identifies a REST resource but does not record the selected database
  schema/profile. Replay schema and filter values remain separately declared;
  linking an event by resource does not prove the original schema or caller.
  The separate task-board app exercises custom-schema routing locally, not
  reconstruction of an original request or independent third-party adoption.


- Existing-database connect/diagnose support approved remote catalog connections
  with verify-full TLS, profiles without secrets, bounded discovery and structural
  policy shapes. Remote application replay remains excluded. Views/custom types,
  arbitrary functions and complex predicates remain unrecognized.
- Opt-in bound event 1.1 records configured project/API/schema metadata and optional
  Auth check outcome. Configuration matching and valid Auth do not establish the
  executed PostgreSQL role, actual database routing or original auth.uid. Captures
  are user-supplied files, not signed attestations.
- Real TLS/least-privilege checks use a controlled local server; actual external
  hosted Supabase/customer access and independent clean-machine review are pending.
