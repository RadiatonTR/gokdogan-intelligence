[CmdletBinding()]
param([string]$ExePath='')
$ErrorActionPreference='Stop'
$candidates=@()
if($ExePath){$candidates+=$ExePath}
$candidates += @(
  (Join-Path $PSScriptRoot 'desktop-shell\tauri-skeleton\src-tauri\target\release\Gokdogan Intelligence Desktop.exe'),
  (Join-Path $env:LOCALAPPDATA 'Programs\Gokdogan Intelligence Desktop\Gokdogan Intelligence Desktop.exe'),
  (Join-Path $env:ProgramFiles 'Gokdogan Intelligence Desktop\Gokdogan Intelligence Desktop.exe')
)
$exe=$candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if(-not $exe){ throw 'Gokdogan desktop executable was not found. Pass -ExePath with the installed EXE path.' }
Write-Host "Launching safe mode: $exe" -ForegroundColor Cyan
$env:SB_DESKTOP_SAFE_MODE='true'
$env:SB_ALLOW_ACTIVE_RECON='false'
$env:SB_ALLOW_AGENT_SHELL='false'
Start-Process -FilePath $exe -ArgumentList '--safe-mode'
