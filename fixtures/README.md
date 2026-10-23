# Disposable Supabase fixtures

Use these migrations only in a disposable local stack created for this project.
They are installation/setup code, separate from read-only diagnostics.

From the repository root, with Docker running and Supabase CLI **2.121.0**:

```sh
supabase start --workdir fixtures
```

The CLI reads `fixtures/supabase/config.toml`, applies the migrations, and seeds two
entirely synthetic rows per table. The API is on port 54321 and Postgres is on
54322. PostgreSQL major version 17 is selected explicitly. Do not link this
project to a remote Supabase project or run `db push`.

The seed uses two placeholder owner UUIDs. The E2E setup signs up two local Auth
users using generated, temporary passwords, then parameterizes the replacement
of those placeholders with the real local user IDs. It does not insert directly
into Supabase's managed Auth tables. Credentials stay in process memory; never
commit or upload `supabase status` output, startup logs, tokens or local env files.

| Table | SQL SELECT grant | SELECT row policy | Intended authenticated result |
| --- | --- | --- | --- |
| `documents` | yes | `auth.uid() = owner_id` | own row only |
| `blocked_documents` | yes | none | zero rows (default deny) |
| `no_grant_documents` | no | `auth.uid() = owner_id` | privilege error |
| `leaky_documents` | yes | unconditional true | both rows; isolation expectation must fail |

All four tables have RLS enabled. Anonymous callers receive no rows from the
granted tables because no SELECT policy applies to `anon`; the missing-grant
table still returns a privilege error. This table describes fixture intent;
only an actual local integration run verifies the executed behavior.

`public.rls_doctor_identity()` is the only approved probe RPC. It has no
arguments, is STABLE and SECURITY INVOKER, reads no table, and reports `role` and
`uid` from the executed database context. Scenario input cannot select arbitrary
RPCs. Installing a function of the same name elsewhere does not establish trust.

To stop this stack, use `supabase stop --workdir fixtures`. Resetting fixture
data with `supabase db reset --workdir fixtures` is destructive to this local
stack; never point the workdir or command at a project containing real data.
