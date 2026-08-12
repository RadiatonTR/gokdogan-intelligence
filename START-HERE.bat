@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul 2>&1

set "BOOTLOG=%~dp0start-here.log"
>"%BOOTLOG%" echo [%date% %time%] GOKDOGAN INTELLIGENCE v1.0.0 baslatici basladi.

title Gokdogan Intelligence v1.0.0
echo ============================================================
echo   GOKDOGAN INTELLIGENCE v1.0.0
echo ============================================================
echo.
echo Baslatici kontrol ediliyor...

if not exist "%~dp0WINDOWS-DESKTOP-ONE-CLICK.bat" (
  echo HATA: WINDOWS-DESKTOP-ONE-CLICK.bat bulunamadi.
  echo HATA: ONE-CLICK BAT bulunamadi.>>"%BOOTLOG%"
  pause
  exit /b 10
)
if not exist "%~dp0WINDOWS-DESKTOP-ONE-CLICK.ps1" (
  echo HATA: WINDOWS-DESKTOP-ONE-CLICK.ps1 bulunamadi.
  echo HATA: ONE-CLICK PS1 bulunamadi.>>"%BOOTLOG%"
  pause
  exit /b 11
)

set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if exist "%PS_EXE%" goto :powershell_found
set "PS_EXE="
for /f "delims=" %%P in ('where powershell.exe 2^>nul') do if not defined PS_EXE set "PS_EXE=%%P"
if defined PS_EXE goto :powershell_found
for /f "delims=" %%P in ('where pwsh.exe 2^>nul') do if not defined PS_EXE set "PS_EXE=%%P"

:powershell_found
if not defined PS_EXE (
  echo HATA: PowerShell bulunamadi.
  echo Windows PowerShell 5.1 veya PowerShell 7 kurulu olmalidir.
  echo HATA: PowerShell bulunamadi.>>"%BOOTLOG%"
  pause
  exit /b 12
)

echo PowerShell: %PS_EXE%
echo PowerShell: %PS_EXE%>>"%BOOTLOG%"

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $p=Join-Path (Get-Location) 'WINDOWS-DESKTOP-ONE-CLICK.ps1'; $b=[IO.File]::ReadAllBytes($p); if($b.Length -ge 6 -and $b[0]-eq 239 -and $b[1]-eq 187 -and $b[2]-eq 191 -and $b[3]-eq 239 -and $b[4]-eq 187 -and $b[5]-eq 191){exit 42}; try {[void][ScriptBlock]::Create([IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)); exit 0} catch {Write-Error $_; exit 43}" >>"%BOOTLOG%" 2>&1
set "PRECHECK=%ERRORLEVEL%"
if "%PRECHECK%"=="42" (
  echo HATA: PowerShell dosyasinda cift UTF-8 BOM bulundu.
  type "%BOOTLOG%"
  pause
  exit /b 42
)
if not "%PRECHECK%"=="0" (
  echo HATA: PowerShell on kontrolu basarisiz. Kod: %PRECHECK%
  echo Ayrinti: %BOOTLOG%
  type "%BOOTLOG%"
  pause
  exit /b %PRECHECK%
)

if not defined GOKDOGAN_LIVE_DATA set "GOKDOGAN_LIVE_DATA=true"
if not defined SB_INCLUDE_MESH_HARDWARE set "SB_INCLUDE_MESH_HARDWARE=1"
set "SB_NO_PAUSE=1"

echo.
echo Derleme, kurulum ve dogrulama baslatiliyor...
echo [%date% %time%] ONE-CLICK baslatiliyor.>>"%BOOTLOG%"
call "%~dp0WINDOWS-DESKTOP-ONE-CLICK.bat"
set "BUILD_EXIT=%ERRORLEVEL%"
echo [%date% %time%] ONE-CLICK cikis kodu: %BUILD_EXIT%>>"%BOOTLOG%"

if not "%BUILD_EXIT%"=="0" (
  echo.
  echo DERLEME BASARISIZ. Bu pencere acik kalacak.
echo Cikis kodu: %BUILD_EXIT%
  echo Teshis: windows-desktop-build.log ve GOKDOGAN-DIAGNOSTIC.zip
  if exist "%~dp0WINDOWS-DESKTOP-DIAGNOSTIC.bat" (
    set "SHADOWBROKER_NO_FINAL_PAUSE=1"
    call "%~dp0WINDOWS-DESKTOP-DIAGNOSTIC.bat" >nul 2>&1
    set "SHADOWBROKER_NO_FINAL_PAUSE="
  )
  echo Baslatici logu: %BOOTLOG%
  if not defined SHADOWBROKER_NO_FINAL_PAUSE pause
  exit /b %BUILD_EXIT%
)

set "INSTALL_VERIFY=%~dp0dist\windows\WINDOWS-DESKTOP-INSTALL-AND-VERIFY.bat"
if not exist "%INSTALL_VERIFY%" (
  echo.
  echo HATA: Kurulum/dogrulama yardimcisi bulunamadi:
  echo %INSTALL_VERIFY%
  pause
  exit /b 20
)

echo.
echo Derleme basarili. Kurulum ve dogrulama baslatiliyor...
set "SHADOWBROKER_NO_FINAL_PAUSE=1"
call "%INSTALL_VERIFY%"
set "INSTALL_EXIT=%ERRORLEVEL%"
set "SHADOWBROKER_NO_FINAL_PAUSE="

if not "%INSTALL_EXIT%"=="0" (
  echo.
  echo KURULUM VEYA DOGRULAMA BASARISIZ. Kod: %INSTALL_EXIT%
  echo Ayrinti icin windows-desktop-build.log dosyasini kontrol edin.
  pause
  exit /b %INSTALL_EXIT%
)

echo.
echo ============================================================
echo   DERLEME, KURULUM VE DOGRULAMA BASARILI
echo ============================================================
echo OFFLINE USB paketi dist klasorunde olusturulmustur.
echo Baslatici logu: %BOOTLOG%
pause
exit /b 0
