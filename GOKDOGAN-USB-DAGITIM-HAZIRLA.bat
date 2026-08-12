@echo off
setlocal
cd /d "%~dp0"
set "BUNDLE=%~dp0dist\windows\bundle"
set "OUT=%~dp0dist\GOKDOGAN-USB-DAGITIM"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1" -BundleDir "%BUNDLE%" -OutputDir "%OUT%"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo USB DAGITIM PAKETI OLUSTURULAMADI. Hata kodu: %RC%
  pause
  exit /b %RC%
)
echo.
echo USB DAGITIM PAKETI HAZIR: %OUT%
exit /b 0
