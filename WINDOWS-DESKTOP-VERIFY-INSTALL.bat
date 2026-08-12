@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-VERIFY-INSTALL.ps1" %*
exit /b %ERRORLEVEL%
