@echo off
setlocal
cd /d "%~dp0"
title ShadowBroker R24 - Build with optional Mesh Hardware SDK
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-BUILD-WITH-MESH-HARDWARE.ps1"
set EXITCODE=%ERRORLEVEL%
if not "%EXITCODE%"=="0" (
  echo.
  echo Mesh Hardware build failed with exit code %EXITCODE%.
  echo This optional profile requires Meshtastic/BLE packages from PyPI.
  pause
)
exit /b %EXITCODE%
