[CmdletBinding()]
param(
  [ValidateSet('Status','Health','AutoRepair','Backup','ClearCache','FactoryReset')][string]$Action='Status',
  [string]$DataDir='',
  [switch]$ConfirmFactoryReset
)
$ErrorActionPreference='Stop'
if(-not $DataDir){$DataDir=Join-Path $env:LOCALAPPDATA 'com.gokdogan.desktop'}
$DataDir=[IO.Path]::GetFullPath($DataDir)
Write-Host "Data directory: $DataDir" -ForegroundColor Cyan
function Show-JsonState([string]$Name, [string]$Path) {
  if(-not(Test-Path $Path)){Write-Host "$Name: not found" -ForegroundColor DarkGray; return}
  try {
    $obj=Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    Write-Host "$Name:" -ForegroundColor Cyan
    $obj | ConvertTo-Json -Depth 6 | Write-Host
  } catch { Write-Warning "$Name could not be parsed: $($_.Exception.Message)" }
}
if($Action -eq 'Status'){
  if(-not(Test-Path $DataDir)){Write-Host 'No local desktop data directory found.'; exit 0}
  $bytes=(Get-ChildItem -LiteralPath $DataDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
  Write-Host ("Size: {0:N2} MB" -f (($bytes | ForEach-Object {[double]$_})/1MB))
  Get-ChildItem -LiteralPath $DataDir -Force | Select-Object Name,Length,LastWriteTime
  exit 0
}
if($Action -eq 'Health'){
  Show-JsonState 'Install state' (Join-Path $DataDir 'install-state.json')
  Show-JsonState 'Runtime state' (Join-Path $DataDir 'desktop-runtime-state.json')
  Show-JsonState 'Self-test' (Join-Path $DataDir 'desktop-self-test.json')
  $verify=Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) 'WINDOWS-DESKTOP-VERIFY-INSTALL.ps1'
  if(-not(Test-Path $verify)){throw "Verifier not found: $verify"}
  Write-Host 'Running installed-runtime verification...' -ForegroundColor Cyan
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify
  exit $LASTEXITCODE
}
if($Action -eq 'AutoRepair'){
  if(-not(Test-Path $DataDir)){throw 'Desktop data directory does not exist; AutoRepair requires an existing installation.'}
  $root=Split-Path -Parent $MyInvocation.MyCommand.Path
  $verify=Join-Path $root 'WINDOWS-DESKTOP-VERIFY-INSTALL.ps1'
  if(Test-Path $verify){
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify
    if($LASTEXITCODE -eq 0){Write-Host 'Installed runtime is already healthy; no repair was required.' -ForegroundColor Green; exit 0}
  }
  $stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
  $backup=Join-Path ([Environment]::GetFolderPath('MyDocuments')) "Gokdogan-Before-AutoRepair-$stamp.zip"
  Compress-Archive -Path (Join-Path $DataDir '*') -DestinationPath $backup -CompressionLevel Optimal -Force
  Write-Host "Safety backup created: $backup" -ForegroundColor Yellow
  $installVerify=Join-Path $root 'WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1'
  if(-not(Test-Path $installVerify)){throw "Install + Verify script not found: $installVerify"}
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $installVerify
  if($LASTEXITCODE -ne 0){throw "AutoRepair reinstall/verification failed with exit code $LASTEXITCODE. Safety backup: $backup"}
  Write-Host 'AutoRepair completed and installed runtime verification passed.' -ForegroundColor Green
  exit 0
}
if(-not(Test-Path $DataDir)){throw 'Desktop data directory does not exist.'}
$stamp=Get-Date -Format 'yyyyMMdd-HHmmss'
if($Action -eq 'Backup'){
  $dest=Join-Path ([Environment]::GetFolderPath('MyDocuments')) "Gokdogan-Desktop-Data-$stamp.zip"
  Compress-Archive -Path (Join-Path $DataDir '*') -DestinationPath $dest -CompressionLevel Optimal
  Write-Host "Backup created: $dest" -ForegroundColor Green
  exit 0
}
if($Action -eq 'ClearCache'){
  $cacheNames=@('Cache','Code Cache','GPUCache','DawnCache','gate-state-cache')
  foreach($name in $cacheNames){$p=Join-Path $DataDir $name;if(Test-Path $p){Remove-Item -LiteralPath $p -Recurse -Force;Write-Host "Cleared $name"}}
  Write-Host 'Persistent intelligence database, cases, evidence, and secret vault were not removed.' -ForegroundColor Green
  exit 0
}
if($Action -eq 'FactoryReset'){
  if(-not $ConfirmFactoryReset){throw 'FactoryReset deletes ALL local Gokdogan desktop data. Re-run with -ConfirmFactoryReset.'}
  $backup=Join-Path ([Environment]::GetFolderPath('MyDocuments')) "Gokdogan-Before-FactoryReset-$stamp.zip"
  Compress-Archive -Path (Join-Path $DataDir '*') -DestinationPath $backup -CompressionLevel Optimal
  Remove-Item -LiteralPath $DataDir -Recurse -Force
  Write-Host "Factory reset complete. Safety backup: $backup" -ForegroundColor Yellow
}
