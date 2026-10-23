# Node.js example

Requires the repository dependencies and built SDK (`pnpm build`). Node.js 22/24
are the supported runtime targets. Run commands from the repository root.

## Offline contract example

```sh
node examples/node-basic/capture-event.mjs > event.json
```

This invokes the real capture wrapper with an in-memory Fetch implementation.
It writes one schema v1 JSON event to stdout. It makes no network request, uses
no token, and does not prove that Supabase or PostgreSQL behavior is correct.
The `owner_id` value is deliberately omitted from the resulting event. Pass the
event to the Python CLI using the event ingestion command in the root quickstart.

## Disposable local Supabase fixture

Start and populate the local fixture as described in [the fixture guide](../../fixtures/README.md).
Provide the local stack's anon key through environment variables, then run:

```sh
RLS_DOCTOR_LOCAL_ANON_KEY='<local synthetic anon key>' RLS_DOCTOR_APPROVE_LOCAL_TEST=true node examples/node-basic/index.mjs
```

In PowerShell, set `$env:RLS_DOCTOR_LOCAL_ANON_KEY` and
`$env:RLS_DOCTOR_APPROVE_LOCAL_TEST = 'true'` before running the Node command.
Do not paste keys into tracked files. The destination is fixed to numeric
loopback `http://127.0.0.1:54321`; approve only a disposable local stack.

The sample integrates with the real `@supabase/supabase-js` client and captures
only `documents` GET requests. It prints a status and the presence of an
application error, never rows or raw errors. Sanitized JSON is written to
`.rls-doctor/captures`. This example does not sign in a user: header presence is
not proof of a user identity, and an empty result does not establish an RLS cause.
File writes are awaited here so the demonstration can report persistence errors;
the capture wrapper itself never waits on its sink before returning the response.
