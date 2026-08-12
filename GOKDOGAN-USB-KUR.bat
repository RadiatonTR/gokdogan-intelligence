@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GOKDOGAN-USB-KUR.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo GOKDOGAN KURULUMU BASARISIZ. Hata kodu: %RC%
  pause
  exit /b %RC%
)
echo.
echo GOKDOGAN KURULUMU VE DOGRULAMASI TAMAMLANDI.
exit /b 0
