param(
  [Parameter(Mandatory=$true)][string]$BundleDir
)
$ErrorActionPreference='Stop'
$resolved=(Resolve-Path $BundleDir).Path
$installers=Get-ChildItem -LiteralPath $resolved -Recurse -File | Where-Object { $_.Extension -in @('.msi','.exe') }
if(-not $installers){ throw "No Windows MSI/EXE bundle artifact found under $resolved" }
$manifest=Join-Path $resolved 'release-manifest.json'
$checksums=Join-Path $resolved 'SHA256SUMS.txt'
if(-not (Test-Path $manifest)){ throw "release-manifest.json missing" }
if(-not (Test-Path $checksums)){ throw "SHA256SUMS.txt missing" }
$data=Get-Content -LiteralPath $manifest -Raw | ConvertFrom-Json
if(-not $data.metadata -or -not $data.artifacts){ throw "release manifest malformed" }
foreach($installer in $installers){
  if($installer.Length -lt 100kb){ throw "Installer unexpectedly small: $($installer.FullName)" }
  $sig=Get-AuthenticodeSignature -LiteralPath $installer.FullName
  $signed=($sig.Status -eq 'Valid')
  Write-Host ("Bundle artifact: {0} ({1:N1} MB) Authenticode={2}" -f $installer.Name,($installer.Length/1mb),$sig.Status)
  if($env:SHADOWBROKER_REQUIRE_WINDOWS_SIGNATURE -eq '1' -and -not $signed){ throw "Required Authenticode signature is not valid: $($installer.Name) [$($sig.Status)]" }
}
Write-Host "Windows bundle structural validation OK"
