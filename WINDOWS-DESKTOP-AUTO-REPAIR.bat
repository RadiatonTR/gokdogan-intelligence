@echo off
setlocal
cd /d "%~dp0"
title Gokdogan Intelligence Desktop - Auto Repair
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-DATA-MAINTENANCE.ps1" -Action AutoRepair
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" echo AutoRepair failed with exit code %EXITCODE%.
pause
exit /b %EXITCODE%
