-- SETUP ONLY. These identifiers and contents are entirely synthetic.
-- No passwords, JWTs, Auth hashes, service keys, or production data belong here.
-- The bootstrap script signs up disposable users through local Auth, then
-- replaces these two owner placeholders with the returned local user UUIDs.

insert into public.documents (id, owner_id, title) values
    ('10000000-0000-4000-8000-000000000001',
     '11111111-1111-4111-8111-111111111111', 'Synthetic document A'),
    ('10000000-0000-4000-8000-000000000002',
     '22222222-2222-4222-8222-222222222222', 'Synthetic document B');

insert into public.blocked_documents select * from public.documents;
insert into public.no_grant_documents select * from public.documents;
insert into public.leaky_documents select * from public.documents;
