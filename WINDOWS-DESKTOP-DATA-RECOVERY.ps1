[CmdletBinding()]
param(
    [ValidateSet('Check','RestoreLatest')]
    [string]$Action = 'Check',
    [string]$DataDir,
    [switch]$Yes
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $DataDir) {
    $DataDir = Join-Path $env:LOCALAPPDATA 'com.gokdogan.desktop\managed-backend\data'
}
$helper = Join-Path $root 'scripts\windows\recover_intelligence_database.py'
if (-not (Test-Path $helper)) { throw "Recovery helper missing: $helper" }
$installedPython = Join-Path (Split-Path -Parent $DataDir) 'python-runtime\python.exe'
$python = $null
if (Test-Path $installedPython) { $python = $installedPython }
elseif (Get-Command python.exe -ErrorAction SilentlyContinue) { $python = 'python.exe' }
elseif (Get-Command py.exe -ErrorAction SilentlyContinue) { $python = 'py.exe' }
else { throw 'No Python runtime was found. Install/run Gokdogan once or run the R24 one-click builder first.' }

Write-Host 'Gokdogan Intelligence Desktop - Data Recovery' -ForegroundColor Cyan
Write-Host "Data directory: $DataDir" -ForegroundColor Gray
if ($Action -eq 'RestoreLatest' -and -not $Yes) {
    Write-Host 'This will replace the current Intelligence Core database with the newest VALID full snapshot.' -ForegroundColor Yellow
    Write-Host 'A safety database backup is created first. .env and native secrets are not modified.' -ForegroundColor Gray
    $answer = Read-Host 'Type RESTORE to continue'
    if ($answer -ne 'RESTORE') { Write-Host 'Cancelled.' -ForegroundColor DarkYellow; exit 1 }
}
$actionArg = if ($Action -eq 'RestoreLatest') { 'restore-latest' } else { 'check' }
$report = Join-Path $root 'windows-data-recovery-report.json'
if ($python -eq 'py.exe') {
    & $python -3 $helper --data-dir $DataDir --action $actionArg --json-output $report
} else {
    & $python $helper --data-dir $DataDir --action $actionArg --json-output $report
}
$code = $LASTEXITCODE
if ($code -eq 0) { Write-Host "Recovery check/action completed successfully. Report: $report" -ForegroundColor Green }
else { Write-Host "Recovery check/action failed (exit $code). Report: $report" -ForegroundColor Red }
exit $code
