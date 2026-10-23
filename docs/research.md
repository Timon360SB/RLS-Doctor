# Research and positioning notes

Accessed **2026-10-23**. These are source-based observations, not independent
benchmarks or an endorsement of competitors' correctness claims. Versions and
product availability may change. No competitor was executed for this review.

## Existing tools

| Tool | Observed scope from its primary source | Implication for this MVP |
| --- | --- | --- |
| [pgrls](https://github.com/pgrls/pgrls) | PostgreSQL RLS static analysis, policy diffing, access matrices, posture reports, and pytest isolation support. The README documents limitations including unmodeled schema usage and opaque function/view behavior. | A catalog inspector or broad RLS linter is already overlapping territory. Reuse or integration deserves evaluation before adding rules. |
| [rlsautotest](https://github.com/unitautogen/rlsautotest) | Generates identities, seed data, access reports and pgTAP suites using live database probes. Its README warns that ordinary report/generation modes execute writes, triggers and sequences despite rollback and require a disposable database. | Automated regression generation already exists. RLS Doctor deliberately starts with explicit user-authored read scenarios; rollback is not its safety boundary. |
| Supabase RLS Tester | [April preview announcement](https://supabase.com/changelog/45233-feature-preview-rls-tester) described role/user impersonation and SELECT policy debugging. Later [merged PR #47866](https://github.com/supabase/supabase/pull/47866) explicitly paused development to reevaluate direction and removed its UI and sandbox. | The older changelog alone is insufficient evidence of present availability. The verified later primary-source action is removal/pause; no live Dashboard availability was tested here. |

**Positioning hypothesis:** an opt-in bridge from sanitized application request
metadata to explicit local reproduction may reduce the distance between an
application symptom and reproducible database evidence. The sources above do
not prove that this workflow is unique, demanded, or commercially viable. Validate
with real developer interviews and comparative tasks before expanding scope.

## PostgreSQL semantics used by the implementation

[PostgreSQL 17 RLS documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)
separates object privileges from row policies. With RLS enabled and no applicable
allowing policy, ordinary callers see no rows. Owners normally bypass RLS unless
FORCE applies; superusers and BYPASSRLS roles bypass it. Applicable permissive
policies combine with OR and restrictive policies with AND. SELECT uses USING;
WITH CHECK governs new row values for relevant writes. Policy role applicability
uses normal role membership and inheritance. Empty output alone does not identify
which predicate or filter caused it.

[PostgreSQL 17 role membership](https://www.postgresql.org/docs/17/role-membership.html)
documents per-membership INHERIT and SET options. A membership edge without
INHERIT stops immediate privilege inheritance; the ability to SET ROLE is a
different question. Therefore membership alone cannot establish that a policy
applies to the current executing role.

[Privilege inquiry functions](https://www.postgresql.org/docs/17/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE)
provide `has_schema_privilege`, `has_table_privilege`,
`has_column_privilege`, and `pg_has_role`. For `pg_has_role`, MEMBER tests
membership, USAGE tests privileges available immediately, and SET tests whether a
role switch is allowed. Catalog findings remain observations; arbitrary predicates
are not evaluated by the inspector.

The fixture pins PostgreSQL major version 17. This is a version-specific
implementation boundary; other server versions require validation.

## Supported Supabase integration surfaces

[The JavaScript initialization reference](https://supabase.com/docs/reference/javascript/initializing)
provides `global.fetch` as a custom transport hook. A client-wide hook also sees
unsupported traffic, so capture must explicitly allow only configured REST GET
table paths. The wrapper preserves the original fetch call and response.

[Supabase JWT documentation](https://supabase.com/docs/guides/auth/jwts)
documents `/auth/v1/.well-known/jwks.json` for public asymmetric verification keys;
HS256-only projects can return no keys. Signature verification must also constrain
issuer, audience and lifetime. Decoding a token or seeing an Authorization header
does not establish trusted identity. Supabase recommends Auth-server verification
for shared-secret tokens; this MVP's optional local HS256 secret is restricted to
disposable fixtures and never enters capture events or reports.

[PostgREST RPC documentation](https://docs.postgrest.org/en/stable/references/api/functions.html)
explains that exposed executable functions are accessible under `/rpc`. Arbitrary
GET endpoints are therefore not assumed safe. User scenarios exclude RPC; a
hard-coded `GET /rest/v1/rpc/rls_doctor_identity` probes only the fixture's STABLE,
SECURITY INVOKER function, returning the actual database role and `auth.uid()`.
This trusts the installed fixture function and local infrastructure, not arbitrary
production functions.

## Toolchain choices and repeatability

The [npm registry](https://registry.npmjs.org/@supabase/supabase-js/latest)
reported `@supabase/supabase-js` 2.118.0 with Node.js >=22. Node 22/24 are the
initial CI targets; the workflow uses sufficiently recent 22.x for its tooling.
TypeScript 5.9.3 is a deliberate compatibility pin rather than a claim to use the
newest compiler. Dependency locks, installed tests, and CI determine actual
compatibility; registry existence alone does not prove it.

[Supabase CLI stable release 2.121.0](https://github.com/supabase/cli/releases/tag/v2.121.0)
and [setup-cli 2.1.2](https://github.com/supabase/setup-cli/releases/tag/v2.1.2)
were verified as available. The workflow pins both rather than the moving
`latest` tag. [CLI configuration](https://supabase.com/docs/guides/local-development/cli/config)
documents API schemas, ports, database version and seed configuration. A Docker
run and its captured output are still required before claiming integration passes.
