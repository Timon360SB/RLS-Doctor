# Test RLS Doctor with the practice database

[Русская версия](practice-testing.ru.md)

This walkthrough exercises a real local Supabase stack: PostgreSQL, Auth,
REST API, the Node SDK and Python CLI. It uses synthetic users/documents.
It does not connect to your application or establish its security.

## 1. Start the lab

Open Docker Desktop and wait for the Linux engine to run. You also need
Node.js 22.12+/24, pnpm 11.25.0 and uv. Open PowerShell in the repository root.
For this checkout:

```powershell
cd C:\Users\sbtim\Documents\GitHub\RLS-Doctor
.\lab.cmd
```

Answer **y** to `Prepare practice database?`. Wait for `Ready` and the menu.
First preparation can take longer while dependencies/container images download.
Type a menu number, then Enter. No keys or environment variables need copying.
Use `.\lab.cmd -Language ru` for Russian.

| Component | Address / purpose |
| --- | --- |
| API | `http://127.0.0.1:55321` |
| PostgreSQL | `127.0.0.1:55322` |
| Docker project | `rls-doctor-practice` |
| Setup files | `.rls-doctor/practice/supabase/` |
| Current scenarios/reports | `.rls-doctor/practice/run-…/` shown after preparation |

The original demo uses different ports. Do not run two practice sessions at once:
the launcher holds an OS lock to prevent conflicting ownership changes.
Close the first menu with **0** if you see `LAB_SESSION_BUSY`. A leftover
`.session.lock` file is normal; do not delete it. A crashed process releases
its lock automatically. Direct Supabase commands are outside this protection.

The lab creates a new pair of Auth users on each preparation and assigns its
eight synthetic rows to them. Old users remain until explicitly removed or the
local stack is reset. No application rows or policies are changed.

| Table | Deliberate setup |
| --- | --- |
| `documents` | Two owner-scoped documents: Alice can read hers, Bob can read his |
| `blocked_documents` | SELECT privilege exists, but no permitting RLS policy |
| `no_grant_documents` | Missing SELECT privilege |
| `leaky_documents` | Deliberately broad policy exposes both documents |

Supabase/Docker may publish these ports on all host interfaces even though
RLS Doctor sends requests only to numeric loopback. See [limitations](limitations.md).
Use this disposable environment on a trusted development computer/network.

## 2. Read the outcome correctly

| Outcome / exit | Meaning |
| --- | --- |
| PASS / 0 | Observed behavior matches the explicit expectation |
| FAIL / 1 | An expectation was violated |
| UNKNOWN / 2 | Evidence cannot establish the required behavior |
| ERROR / 3 | Execution failed or an input/environment was rejected |

An expected FAIL or ERROR is the correct result in deliberately broken examples.
Compare `Expected / Actual` and `MATCH`. A matching lab example is not a general
security verdict. Reports distinguish OBSERVED facts, INFERRED conclusions and
UNVERIFIED statements needing another check.

## 3. Check the working path

Select each item separately; the menu returns after its report.

1. **Check connection:** expect PASS / 0. Local API, database and the trusted
   fixture identity probe must work before relying on subsequent results.
2. **Capture SDK request and validate:** expect PASS / 0. Real `supabase-js`
   sends Alice's GET; the SDK emits `event.json`, and Python validates it against
   the shared schema. The event contains metadata, not tokens/passwords/rows.
3. **Offline event analysis:** expect UNKNOWN / 2. A fresh SDK event is analyzed
   without replay or catalog access. Authorization-header presence cannot prove
   the executed identity or explain the RLS result.
4. **Alice: own row only:** expect PASS / 0, HTTP 200, one row and confirmed
   `authenticated` role. Her row must be present and Bob's row absent.
5. **Bob: own row only:** expect PASS / 0, HTTP 200, one row. The reverse
   presence/exclusion assertions must pass too.

## 4. Detect deliberately broken access

| Menu | Expected evidence | What to understand |
| --- | --- | --- |
| 6: Missing authorization | FAIL / 1, HTTP 200, zero rows, anon role | The anonymous request does not meet authenticated expectations |
| 7: No allowing policy | FAIL / 1, HTTP 200, zero rows | SQL privilege alone does not grant visibility through RLS |
| 8: Expected SELECT denial | PASS / 0, HTTP 403, permission error class | A denial can match the scenario; RLS does not grant SQL privileges |
| 9: Detect another user's row | FAIL / 1, HTTP 200, two rows, failed exclusion | The deliberately broad policy leaks the other synthetic document |
| 10: Nonexistent row ambiguity | PASS / 0, HTTP 200, zero rows; EMPTY_RESULT_AMBIGUOUS / UNVERIFIED | An expected empty answer still does not prove its cause was RLS |
| 11: Inspect missing privilege | UNKNOWN / 2, SELECT_PRIVILEGE_MISSING | Catalog facts expose missing rights without establishing runtime row visibility |

## 5. Verify rejected inputs

| Menu | Expected result |
| --- | --- |
| 12: Invalid token | ERROR / 3, INVALID_TEST_TOKEN, before table access |
| 13: Unsupported event version | ERROR / 3, INVALID_EVENT |
| 14: Missing local approval | ERROR / 3, LOCAL_APPROVAL_REQUIRED |
| 15: Remote address | ERROR / 3, UNSAFE_ENDPOINT |
| 16: PATCH replay | ERROR / 3, INVALID_SCENARIO; writes are unsupported |

These examples use separate invalid inputs and preserve the working configuration.
A failure with an unrelated reason does not count as the intended successful check.

## 6. Session menu, full checklist and JSON

Select **17** for managed session onboarding. Choose **1** there to run the
scenario or **2** to inspect the table. **0** returns to the outer practice menu.
Credentials remain scoped to the session; no child PowerShell window is needed.

Select **18** for the full 18-row checklist. Every row should match its expected
outcome. The final regression suite executes eight real PostgreSQL tests,
including owner/FORCE RLS/BYPASSRLS behavior, membership, policy composition and
column rights. Its explicit setup uses an administrative connection only in the
lab to create/remove temporary roles/schema. Normal diagnostics retain their
ordinary connection. Select **20** to run that regression suite separately.

For an unattended full run, first exit the menu with **0**, then run:

```powershell
.\lab.cmd -Check
Write-Host "Lab exit code: $LASTEXITCODE"
```

Expect exit 0. `-Check` explicitly approves only this synthetic lab preparation.

Select **19** to export the actual own-row replay report. Open the printed
`report.json` path and check PASS, HTTP 200, one row and confirmed authenticated
role. The launcher writes UTF-8 directly; old PowerShell output redirection is
unnecessary. Do not save or share raw `supabase status` output.

## 7. Try guided configuration

Exit the lab menu with **0**, leaving its database running. Run:

```powershell
uv run --project python rls-doctor init --interactive --directory .rls-doctor/practice/manual-project
```

| Question | Answer |
| --- | --- |
| Local API URL | `http://127.0.0.1:55321` |
| Local PostgreSQL port | `55322` |
| Test table | `public.documents` |
| Test identity | `anon` |
| Expected HTTP status | `200` |
| Expected number of rows | `0` |
| Approve destination | `y`, after reviewing its address |
| Save configuration | `y` |

Two files are created: `rls-doctor.toml` and `documents.yaml`. No secrets are
requested. Incorrect answers repeat only that question. Cancelling does not save
new files. Repeating the same destination yields INIT_EXISTS / 3 without
replacing files; use a new directory such as `manual-project-2` for another try.

```powershell
uv run --project python rls-doctor session --config .rls-doctor/practice/manual-project/rls-doctor.toml --workdir .rls-doctor/practice
```

Choose **1**. Expect HTTP 200, zero rows and UNKNOWN / 2: guided init deliberately
does not enable/provision a trusted role probe. Loading credentials does not
prove the executed role. Choose **0** to exit. See [managed sessions](managed-session.md)
for JSON automation and optional SDK event linkage.

## 8. Check the source and installed packages

After closing all menus, run these optional developer checks individually:

```powershell
pnpm.cmd typecheck
pnpm.cmd lint
pnpm.cmd test
uv run --project python pytest python/tests -m 'not integration' -q
uv run --project python ruff format --check python scripts
uv run --project python ruff check python scripts
```

Expect exit 0 from each. The pytest command excludes integration tests; only the
actual executed regression suite establishes their result. For Python types:

```powershell
Push-Location python
uv run mypy
Pop-Location
```

To build/install/audit local preview packages without publishing them:

```powershell
uv run --project python python scripts/package_check.py
```

Expect PASS lines and a preview artifact directory with hashes/manifest. These
checks do not establish registry publication or a clean-machine installation.

## 9. Stop and resume

Exit the session submenu with **0**, then the practice menu with **0**. Run:

```powershell
.\lab.cmd -Stop
```

Only the practice stack stops; local data remains. `.\lab.cmd` restarts it and
prepares a new synthetic user pair/ownership. No database reset is needed.

Record the item number, expected/actual outcome and sanitized report if a check
fails unexpectedly. Do not share tokens, environment dumps, rows or raw stack
status. Passing these examples verifies this synthetic workflow; your own app,
independent review and release checks remain separate work.
