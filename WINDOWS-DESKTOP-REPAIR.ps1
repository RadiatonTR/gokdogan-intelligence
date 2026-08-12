[CmdletBinding()]
param(
    [switch]$SkipPrerequisiteInstall,
    [switch]$SkipBrowserRuntime
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host 'Gokdogan Intelligence Desktop - Build Repair' -ForegroundColor Cyan
Write-Host 'This removes generated build/runtime staging only. User intelligence data is not touched.' -ForegroundColor Gray
$targets=@(
    (Join-Path $root 'backend\.desktop-python'),
    (Join-Path $root 'backend\.desktop-browsers'),
    (Join-Path $root 'frontend\out'),
    (Join-Path $root 'desktop-shell\tauri-skeleton\src-tauri\backend-runtime'),
    (Join-Path $root 'desktop-shell\tauri-skeleton\src-tauri\companion-www'),
    (Join-Path $root 'dist\windows')
)
foreach($target in $targets){ if(Test-Path $target){ Write-Host "Removing $target" -ForegroundColor DarkGray; Remove-Item -LiteralPath $target -Recurse -Force } }
$builder=Join-Path $root 'WINDOWS-DESKTOP-ONE-CLICK.ps1'
$builderArgs=@()
if($SkipPrerequisiteInstall){$builderArgs+='-SkipPrerequisiteInstall'}
if($SkipBrowserRuntime){$builderArgs+='-SkipBrowserRuntime'}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $builder @builderArgs
exit $LASTEXITCODE
