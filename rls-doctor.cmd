@echo off
setlocal
where uv >nul 2>nul
if errorlevel 1 (
  echo RLS Doctor requires uv. Install it from https://docs.astral.sh/uv/getting-started/installation/
  echo Then reopen this terminal and run this launcher again.
  exit /b 3
)
set "PYTHONUTF8=1"
if "%~1"=="" (
  uv run --project "%~dp0python" --frozen --no-dev --python 3.12 rls-doctor start
) else (
  uv run --project "%~dp0python" --frozen --no-dev --python 3.12 rls-doctor %*
)
exit /b %errorlevel%
