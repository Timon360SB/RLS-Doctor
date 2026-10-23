-- SETUP ONLY: synthetic fixtures for a disposable local Supabase stack.
-- Diagnostics never execute this migration or change application policies.

grant usage on schema public to anon, authenticated;

create table public.documents (
    id uuid primary key,
    owner_id uuid not null,
    title text not null
);
alter table public.documents enable row level security;
revoke all on public.documents from public, anon, authenticated;
grant select on public.documents to anon, authenticated;
create policy documents_select_own
    on public.documents for select to authenticated
    using ((select auth.uid()) = owner_id);

-- GRANT exists; RLS has no policy and therefore filters every normal caller.
create table public.blocked_documents (like public.documents including all);
alter table public.blocked_documents enable row level security;
revoke all on public.blocked_documents from public, anon, authenticated;
grant select on public.blocked_documents to anon, authenticated;

-- A valid policy cannot replace the missing SQL privilege.
create table public.no_grant_documents (like public.documents including all);
alter table public.no_grant_documents enable row level security;
revoke all on public.no_grant_documents from public, anon, authenticated;
create policy no_grant_documents_select_own
    on public.no_grant_documents for select to authenticated
    using ((select auth.uid()) = owner_id);

-- Intentionally wrong isolation policy: the negative demo must detect this leak.
create table public.leaky_documents (like public.documents including all);
alter table public.leaky_documents enable row level security;
revoke all on public.leaky_documents from public, anon, authenticated;
grant select on public.leaky_documents to anon, authenticated;
create policy leaky_documents_select_all
    on public.leaky_documents for select to authenticated
    using (true);

-- The sole built-in GET RPC probe. It reports the executing database context;
-- it reads no rows, accepts no input, and does not run as its owner.
create function public.rls_doctor_identity()
returns jsonb
language sql
stable
security invoker
set search_path = ''
as $function$
    select pg_catalog.jsonb_build_object('role', current_user, 'uid', auth.uid());
$function$;
revoke all on function public.rls_doctor_identity() from public;
grant execute on function public.rls_doctor_identity() to anon, authenticated;

notify pgrst, 'reload schema';
