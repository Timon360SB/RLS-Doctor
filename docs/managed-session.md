# Managed local session

The session reads credentials from a running local Supabase project through its
CLI. It matches the API origin and permitted database port against your approved
configuration. No credential values are written to files or printed.

1. Start Docker and your project's disposable local Supabase stack.
2. Run `rls-doctor init --interactive` in the folder where you want the
   configuration. Review the destination and explicitly approve only your local
   test infrastructure. Use synthetic scenario data.
3. Run from the RLS Doctor repository:

```powershell
uv run --project python rls-doctor session --config path/to/rls-doctor.toml --workdir path/to/local-project
```

Replace both paths. The workdir contains `supabase/config.toml`; the scenario
defaults to `documents.yaml` beside the config. Use `--scenario path/to/test.yaml`
to choose another explicit scenario. English is default; add `--language ru` for
Russian. Supabase CLI must be installed; the Windows demo's cached native CLI is
also discovered automatically. No additional dependency is downloaded by session.

For an anonymous scenario no user token is needed. For authenticated scenarios,
the session verifies an already supplied local test-token reference. If none is
available, it asks before creating one synthetic local Auth user, with a generated
password that is never shown or saved to configuration. This is an Auth setup
operation, not a write replay. No service-role key is used. Declining prevents signup.
In unattended mode, `--run` refuses implicit signup. Explicitly allow it with
`--run --create-test-user` only for your disposable local Auth.

The synthetic Auth user remains in the local stack after exit until you remove
it or intentionally reset that stack. There is no automatic account deletion.
The user does not own pre-existing rows: the session does not insert test table
rows, change ownership, install policies, or install an identity-probe RPC.
Signup may be unavailable if email confirmation is required; settings are never
changed automatically. Restart the session after editing configuration/scenarios.

Choose Run scenario or Inspect table from the menu. Inspector results are UNKNOWN
about runtime behavior. Without a trusted identity probe, an executed role remains
unconfirmed even after token verification. This is intentional, not a successful
identity check. Test expectations must match your independently prepared fixtures.

`--run` returns the scenario exit code: 0 PASS, 1 FAIL, 2 UNKNOWN, 3 ERROR. Exiting
the menu returns 0 for closing the session; it does not summarize previous tests.
On exit/cancellation/error, pre-existing process environment values are restored.
Docker remains running. Credentials are not exported into the calling terminal.

The managed flow requires distinct credential environment references beginning
with `RLS_DOCTOR_`, so setup cannot overwrite system variables. Ordinary replay
still supports its existing environment-reference contract. Loopback validation
cannot prove absence of forwarding; independently verify the local stack.

Common errors:

| Code | Next action |
| --- | --- |
| LOCAL_APPROVAL_REQUIRED | Review configuration and approve only disposable local infrastructure. |
| SUPABASE_PROJECT_MISSING | Select the directory containing supabase/config.toml. |
| SUPABASE_CLI_MISSING | Install the CLI or run the Windows demo launcher. |
| LOCAL_STACK_STATUS_FAILED | Start the selected local stack; do not share raw CLI status output. |
| LOCAL_PROJECT_MISMATCH | Correct API address/workdir; credentials were not used against a different API. |
| TEST_IDENTITY_REQUIRED | Use a valid local test token or explicitly approve synthetic signup. |
| TEST_IDENTITY_SETUP_FAILED | Check local Auth settings; no automatic settings changes or remote fallback. |
| SESSION_VARIABLE_NAMES | Use separate RLS_DOCTOR_ references for API key, DSN, signing secret and token. |


## Machine-readable unattended runs

Add `--run --format json` to emit exactly one report object without setup messages
or a menu. PASS/FAIL/UNKNOWN/ERROR exit codes remain 0/1/2/3. Language selection
does not translate machine fields. JSON without --run returns SESSION_JSON_MODE.
Interrupting an unattended run returns SESSION_CANCELLED / ERROR / 3 in either
console or JSON mode. Interactive menu cancellation still closes the session
without claiming a test result. Signup still requires --create-test-user.

The local integration workflow runs scripts/session_check.py after the full E2E.
This checker verifies actual PASS, FAIL, UNKNOWN and ERROR JSON outcomes and
credential-free output, using only the repository's disposable fixture stacks.


## Link an SDK event explicitly

Add `--event path/to/event.json` to session. The shared-schema event is validated
before CLI credentials are loaded; a different resource returns EVENT_MISMATCH.
Capture operators never become guessed replay values. The scenario still supplies
all synthetic filters/expectations. Existing event_id/findings fields link evidence
without changing the shared event schema. A locally confirmed role applies only
to the local replay, not the identity of the original captured request.

Guided init retries only the invalid answer. Row-count comparison can be omitted
with `skip` (the default for expected HTTP errors), while HTTP status remains an
explicit expectation. Valid earlier answers are preserved.


Event v1 does not retain the selected schema/profile. Matching a resource name
links the report without proving the original schema; replay schema remains
explicit in YAML. The [separate task-board example](../examples/task-board/README.md)
checks actual custom-schema routing with installed packages.


## Save one report without shell redirection

Add `--run --output .rls-doctor/reports/session-1.json`. JSON is saved directly
as UTF-8 while console/JSON stdout follows --format. PASS/FAIL/UNKNOWN/ERROR exit
codes remain unchanged after successful saving. Interactive --output without
--run is rejected with SESSION_OUTPUT_MODE. Existing files are preserved and
rejected before credential loading; use a fresh name for each run. Failed
publication returns ERROR / 3. The filesystem must support hard links; files
are capped at 1 MiB. Windows permissions follow the destination folder's ACLs.
