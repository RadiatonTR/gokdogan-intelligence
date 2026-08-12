@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-FULL-REGRESSION.ps1"
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" echo Full diagnostic regression reported failures. See output above.
exit /b %RC%
