@echo off
setlocal
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\demo.ps1" -Mode lab %*
exit /b %errorlevel%
