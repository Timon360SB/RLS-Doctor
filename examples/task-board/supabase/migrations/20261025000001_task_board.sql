-- EXPLICIT SAMPLE SETUP ONLY. Diagnostic commands never execute this SQL.
create schema task_board;
grant usage on schema task_board to anon, authenticated;
create table task_board.tasks (
    id uuid primary key,
    owner_id uuid not null,
    title text not null,
    state text not null check (state in ('todo', 'done'))
);
alter table task_board.tasks enable row level security;
revoke all on task_board.tasks from public, anon, authenticated;
grant select on task_board.tasks to anon, authenticated;
create policy tasks_read_own on task_board.tasks for select to authenticated
    using ((select auth.uid()) = owner_id);

-- Explicit test infrastructure: no row access, arguments or SECURITY DEFINER.
grant usage on schema public to anon, authenticated;
create function public.rls_doctor_identity()
returns jsonb language sql stable security invoker set search_path = ''
as $function$
    select pg_catalog.jsonb_build_object('role', current_user, 'uid', auth.uid());
$function$;
revoke all on function public.rls_doctor_identity() from public;
grant execute on function public.rls_doctor_identity() to anon, authenticated;
notify pgrst, 'reload schema';
