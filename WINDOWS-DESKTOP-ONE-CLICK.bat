@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1
title Gokdogan Windows Masaustu Derleyici
set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" set "PS_EXE=powershell.exe"
"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0WINDOWS-DESKTOP-ONE-CLICK.ps1"
set "EXITCODE=%ERRORLEVEL%"
echo.
if not "%EXITCODE%"=="0" (
  echo Derleme basarisiz. Cikis kodu: %EXITCODE%.
  echo Ayrinti icin windows-desktop-build.log dosyasina bakin.
) else (
  echo Derleme basariyla tamamlandi.
)
if not defined SB_NO_PAUSE pause
exit /b %EXITCODE%
