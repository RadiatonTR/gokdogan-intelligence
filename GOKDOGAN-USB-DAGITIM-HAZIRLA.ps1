[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$BundleDir,
    [Parameter(Mandatory=$true)][string]$OutputDir
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$bundle = (Resolve-Path -LiteralPath $BundleDir).Path
$installers = @(Get-ChildItem -LiteralPath $bundle -Recurse -File -Filter '*.exe' -ErrorAction Stop |
    Where-Object { $_.Name -match 'setup' -or $_.FullName -match '\\nsis\\' } |
    Sort-Object LastWriteTime -Descending)
if ($installers.Count -lt 1) { throw "NSIS kurulum dosyası bulunamadı: $bundle" }
$installer = $installers[0]

# Üretim yayını imzalı olabilir; sertifika kaynak paketine kesinlikle gömülmez.
$sig = Get-AuthenticodeSignature -LiteralPath $installer.FullName
$signed = $sig.Status -eq 'Valid'
if ($env:SHADOWBROKER_REQUIRE_WINDOWS_SIGNATURE -eq '1' -and -not $signed) {
    throw "Geçerli Authenticode imzası zorunlu fakat kurulum dosyası imzasız/geçersiz: $($sig.Status)"
}

if (Test-Path -LiteralPath $OutputDir) { Remove-Item -LiteralPath $OutputDir -Recurse -Force }
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$targetInstaller = Join-Path $OutputDir 'Gokdogan-Intelligence-v1.0.0-Setup.exe'
Copy-Item -LiteralPath $installer.FullName -Destination $targetInstaller -Force

foreach ($name in @(
    'GOKDOGAN-USB-KUR.ps1','GOKDOGAN-USB-KUR.bat','LICENSE','DATA-ATTRIBUTION.md',
    'README.md','RESPONSIBLE-USE.md','PRIVACY.md','SECURITY.md','release-version.json'
)) {
    $source = Join-Path $root $name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $OutputDir -Force }
}
$attestation = Join-Path $root 'backend\data\release_attestation.json'
if (Test-Path -LiteralPath $attestation) { Copy-Item -LiteralPath $attestation -Destination (Join-Path $OutputDir 'release_attestation.json') -Force }



$hashLines = Get-ChildItem -LiteralPath $OutputDir -File | Where-Object { $_.Name -ne 'SHA256SUMS.txt' } | Sort-Object Name | ForEach-Object {
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    "$hash  $($_.Name)"
}
$hashLines | Set-Content -LiteralPath (Join-Path $OutputDir 'SHA256SUMS.txt') -Encoding ASCII

Write-Host "Gökdoğan Intelligence v1.0.0 USB dağıtımı hazır: $OutputDir" -ForegroundColor Green
Write-Host "Installer Authenticode: $($sig.Status)" -ForegroundColor Gray
Write-Host "Dağıtım dosyaları için SHA-256 manifesti oluşturuldu." -ForegroundColor Gray
