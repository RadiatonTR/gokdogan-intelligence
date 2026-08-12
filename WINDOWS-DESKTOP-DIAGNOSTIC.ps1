[CmdletBinding()]
param(
    [string]$OutputPath = (Join-Path $PSScriptRoot 'GOKDOGAN-DIAGNOSTIC.zip')
)
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
$temp = Join-Path $env:TEMP ("gokdogan-diagnostic-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temp -Force | Out-Null

function Add-Text([string]$Name, [object[]]$Lines) {
    $Lines | Out-File -LiteralPath (Join-Path $temp $Name) -Encoding utf8 -Width 240
}

$summary = @()
$summary += 'GÖKDOĞAN INTELLIGENCE v1.0.0 - GÜVENLİ TANI PAKETİ'
$summary += "Oluşturulma: $([DateTime]::UtcNow.ToString('o'))"
$summary += "Windows: $([Environment]::OSVersion.VersionString)"
$summary += "Mimari: $env:PROCESSOR_ARCHITECTURE"
$summary += "PowerShell: $($PSVersionTable.PSVersion)"
$summary += "Kullanıcı profili: [GİZLENDİ]"
$summary += "Paket kökü: $root"
try {
    $drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($root).Substring(0,1))
    if ($drive) { $summary += "Boş disk: $([math]::Round($drive.Free/1GB,2)) GB" }
} catch {}
foreach ($cmd in @('node','npm','python','py','rustc','cargo','winget')) {
    try {
        $found = Get-Command $cmd -ErrorAction Stop
        $version = switch ($cmd) {
            'node' { (& node --version 2>&1 | Out-String).Trim() }
            'npm' { (& npm --version 2>&1 | Out-String).Trim() }
            'python' { (& python --version 2>&1 | Out-String).Trim() }
            'py' { (& py --version 2>&1 | Out-String).Trim() }
            'rustc' { (& rustc --version 2>&1 | Out-String).Trim() }
            'cargo' { (& cargo --version 2>&1 | Out-String).Trim() }
            'winget' { (& winget --version 2>&1 | Out-String).Trim() }
        }
        $summary += "$cmd: $version"
    } catch { $summary += "$cmd: bulunamadı" }
}
Add-Text 'sistem-ozeti.txt' $summary

$log = Join-Path $root 'windows-desktop-build.log'
if (Test-Path -LiteralPath $log) {
    Get-Content -LiteralPath $log -Tail 300 | Out-File -LiteralPath (Join-Path $temp 'windows-desktop-build-son-300-satir.log') -Encoding utf8 -Width 260
}

$files = @(
    'START-HERE.bat',
    'WINDOWS-DESKTOP-ONE-CLICK.bat',
    'WINDOWS-DESKTOP-ONE-CLICK.ps1',
    'WINDOWS-DESKTOP-BUILD-REVISION.txt',
    'release-version.json',
    '.node-version',
    'frontend\package-lock.json',
    'desktop-shell\package-lock.json',
    'desktop-shell\tauri-skeleton\src-tauri\Cargo.lock'
)
$hashRows = foreach ($rel in $files) {
    $path = Join-Path $root $rel
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $h = Get-FileHash -LiteralPath $path -Algorithm SHA256
        "$($h.Hash.ToLowerInvariant())  $rel"
    }
}
Add-Text 'dosya-sha256.txt' $hashRows

# Environment variables are deliberately NOT dumped: they can contain API keys/secrets.
Add-Text 'gizlilik.txt' @(
    'Bu tanı paketi ortam değişkenlerini, API anahtarlarını, tokenları, yerel kasa içeriklerini veya kullanıcı çalışma veritabanını toplamaz.',
    'Yalnız sistem sürümü, araç sürümleri, sınırlı build log kuyruğu ve kaynak dosya hashleri bulunur.'
)

if (Test-Path -LiteralPath $OutputPath) { Remove-Item -LiteralPath $OutputPath -Force }
Compress-Archive -Path (Join-Path $temp '*') -DestinationPath $OutputPath -Force
Remove-Item -LiteralPath $temp -Recurse -Force
Write-Host "Tanı paketi oluşturuldu: $OutputPath" -ForegroundColor Green
