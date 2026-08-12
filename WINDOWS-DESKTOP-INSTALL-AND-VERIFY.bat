@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo Install/verify failed with exit code %RC%.
) else (
  echo.
  echo Install and verification completed successfully.
)
if not defined SHADOWBROKER_NO_FINAL_PAUSE pause
exit /b %RC%
