@echo off
setlocal
cd /d "%~dp0"
title Gokdogan Intelligence Desktop - Health Check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-DATA-MAINTENANCE.ps1" -Action Health
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo Health check failed with exit code %EXITCODE%.
pause
exit /b %EXITCODE%
