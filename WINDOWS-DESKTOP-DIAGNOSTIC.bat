@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-DIAGNOSTIC.ps1"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" echo Tani paketi olusturulamadi. Hata kodu: %EXITCODE%
if not defined SHADOWBROKER_NO_FINAL_PAUSE pause
exit /b %EXITCODE%
