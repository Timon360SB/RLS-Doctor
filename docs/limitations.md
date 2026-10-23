# Limitations

- This is an initial source implementation, not a released or certified product.
- Node.js capture only. No browser integration or arbitrary network interception.
- Events contain no replay values, user identity, JWT claims, body or SQLSTATE
  parsed from an HTTP response. Error kind is metadata only; some counts are unknown.
- A captured event cannot faithfully reconstruct a production request. YAML is an
  explicit synthetic test scenario. Only REST table GET requests are supported.
- Only numeric loopback HTTP endpoints with explicit allowed ports/resources are
  supported. DNS aliases, remote replay, redirects and compressed responses fail
  closed. Loopback forwarding remains an operator risk.
- Replay requests at most 1000 rows and buffers at most 1 MiB. Reaching the row
  cap or failing to establish completeness yields UNKNOWN rather than proving a
  foreign row absent. No pagination or arbitrary PostgREST filters in v0.1.
- JWT verification accepts local HS256, ES256 and RS256. No token refresh or
  automatic production session reuse. A trusted identity probe is fixture-specific.
- Policy predicate text is deliberately omitted. Inspection reports operation,
  role applicability, permissive/restrictive composition and predicate-presence
  flags; it cannot evaluate arbitrary functions or establish intent/row visibility.
- Views, foreign tables, hidden function dependencies and partition/inheritance
  entry-point behavior need separate design and runtime checks.
- PostgreSQL 16/17/18 branches are selected by the inspector; only 17.10 has been
  exercised in real database integration here. Node 22/Python 3.13 CI and a complete
  Supabase Docker run remain unexecuted locally. See verification.md.
- Console and JSON only. No web UI, editor extension, writes, automatic fixes or
  broad security certification. No two-human review or independent adoption claim.
- File modes protect new POSIX capture files; Windows needs appropriate ACLs.
  Hostile concurrent directory replacement is outside the filesystem boundary.
