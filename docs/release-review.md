# Independent release-candidate check

[Русский](release-review.ru.md)

Use this checklist on a separate Windows computer or fresh Windows environment.
Its purpose is to check whether another maintainer can reproduce the product
without the original developer's installed tools or private setup knowledge.
Running it again on the original machine does not establish clean-machine setup.

## 0. Primary existing-database journey

Use an approved database you control; record no credentials. With only uv and the
checkout, launch `.\rls-doctor.cmd` or the README uv command. Confirm first-run
dependency preparation, field-by-field connection, hidden password, table/role
selection and the initial report. Close/reopen; confirm profile reuse. In the menu
diagnose, view the schema, change target, switch EN/RU, export one JSON and reconnect.
Verify a second export to the same destination is refused. Runtime visibility must
remain UNKNOWN unless separately observed. Catalog diagnosis must not change rows/policies.
This is a manual acceptance gate; automated/local runs do not establish a fresh-machine pass.

## 1. Prepare and identify the candidate

For the optional lab steps below, install the tools listed in the
[README examples](../README.md#optional-sdk-and-examples):
Git for cloning, Node.js 22.12+/24, pnpm 11.25.0, uv 0.13.5 and Docker Desktop.
Start Docker Desktop and wait for its Linux engine to run. The Windows launcher
prepares Python 3.12 and locates/downloads pinned Supabase CLI 2.121.0.

Use the branch/commit agreed with the release maintainer. For the development branch:

```powershell
git clone --branch feat/mvp-foundation https://github.com/Timon360SB/RLS-Doctor.git RLS-Doctor-review
cd RLS-Doctor-review
git rev-parse HEAD
git status --short
node --version
pnpm.cmd --version
uv --version
```

Record the full commit SHA and tool versions. The initial working tree should be
clean. Use `pnpm.cmd` in PowerShell; changing the system execution policy is not
required for these instructions. Test only synthetic local infrastructure on a
trusted development computer/network; local port publishing is described in
[limitations](limitations.md).

## 2. Follow the normal user path

```powershell
.\lab.cmd
```

Approve preparation with **y**. Choose **18** and expect every row of the 18-check
table to match its intended outcome. A deliberate denial/leak/invalid-input
scenario can correctly produce PASS, FAIL or ERROR; the expected/actual comparison
explains whether the tool behaved correctly. Full details: [practice guide](practice-testing.md).

Exit with **0**, then try `.\lab.cmd -Language ru` to check Russian menus/reports.
Do not keep two practice sessions open. Exit again with **0** and run:

```powershell
.\lab.cmd -Stop
.\lab.cmd -Check
Write-Host "Lab exit code: $LASTEXITCODE"
```

Expect exit 0 after the second command. It checks restart with preserved data;
preparation creates a new synthetic user pair and reassigns the lab's eight rows.
Old synthetic Auth users remain until deliberately removed/reset.

## 3. Verify installed packages with the separate app

After the launcher has prepared repository dependencies:

```powershell
uv run --project python python scripts/task_board_check.py --check
Write-Host "App exit code: $LASTEXITCODE"
```

Expect installed doctor PASS and Alice/Bob/anonymous counts **2 / 1 / 0**, with
all three app/replay checks passing and exit 0. The script builds/audits packages,
installs them into separate consumers, checks the custom-schema app and compares
directly exported reports with JSON stdout. Source SDK imports cannot replace
this installed-package evidence. See [app guide](../examples/task-board/README.md).

The printed run directory contains sanitized reports/summary only where documented.
Send those selected files if needed; do not send the entire .rls-doctor directory,
which also contains local dependencies and environment state.

## 4. Finish and record a result

```powershell
uv run --project python python scripts/task_board_check.py --stop
.\lab.cmd -Stop
git status --short
```

Both environments should stop with data preserved. The tracked source should
remain unchanged. Complete this receipt yourself; do not mark checks you did not run.

```text
Commit SHA:
Fresh Windows environment: yes / no
Windows version:
Node / pnpm / uv versions:
English lab: matched all 18 / failed at item ... / not run
Russian menu/report: checked / not run
Preserved-data stop/restart: passed / failed / not run
Installed task-board app: Alice 2, Bob 1, anonymous 0 / other / not run
Doctor and report export: passed / failed / not run
Stop both environments: passed / failed / not run
Tracked files unchanged: yes / no
Issues: step, expected/actual result, fixed diagnostic code
Reviewer conclusion: ready / changes needed / incomplete
```

Never include passwords, tokens, keys, raw Supabase status/startup output,
environment dumps or user data. A co-author line does not constitute independent
review; record who actually performed the check through the normal review process.

## CI preview downloads

Workflows containing the preview-retention step save artifacts named
`preview-<commit>-node-<version>-py-<version>-attempt-<number>` for seven days.
Open the exact GitHub Actions run, select its artifact and download it while signed
in to GitHub. The extracted bundle should contain exactly three package archives,
SHA256SUMS and manifest.json. Confirm that manifest.git_head matches the candidate
and that the file hashes match SHA256SUMS before using the packages.

These are preview artifacts of that run. A green run for an earlier commit does
not verify later changes. Package preview download, independent review and an
actual public release are separate steps.
