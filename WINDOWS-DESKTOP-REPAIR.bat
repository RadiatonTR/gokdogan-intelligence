@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-REPAIR.ps1"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" pause
exit /b %RC%
