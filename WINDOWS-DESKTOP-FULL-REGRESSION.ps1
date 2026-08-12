param(
    [switch]$KeepTestWorkspace
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RepoRoot 'backend'
$PortablePython = Join-Path $BackendDir '.desktop-python\python.exe'
$BuildReportsDir = Join-Path $RepoRoot 'build-reports'
$TestVenvDir = Join-Path $BuildReportsDir '.desktop-full-regression-venv'
$TestPython = Join-Path $TestVenvDir 'Scripts\python.exe'
$TestRequirements = Join-Path $BuildReportsDir 'backend-full-regression-requirements.lock.txt'
$TestDataDir = Join-Path $BuildReportsDir '.desktop-full-regression-data'
$PrivacyCoreManifest = Join-Path $RepoRoot 'privacy-core\Cargo.toml'
$PrivacyCoreDll = Join-Path $RepoRoot 'privacy-core\target\release\privacy_core.dll'

function Invoke-Native([string]$File, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location $WorkingDirectory
    try {
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')" }
    }
    finally { Pop-Location }
}

if (-not (Test-Path $PortablePython)) {
    throw 'Portable Python runtime missing. Run START-HERE.bat through Stage 4 first.'
}
New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null

$oldCargoRetry=$env:CARGO_NET_RETRY; $oldCargoTimeout=$env:CARGO_HTTP_TIMEOUT
$oldData=$env:SB_DATA_DIR; $oldPath=$env:PYTHONPATH; $oldLib=$env:PRIVACY_CORE_LIB
$oldAllowed=$env:PRIVACY_CORE_ALLOWED_SHA256; $oldSecret=$env:MESH_SECURE_STORAGE_SECRET
try {
    if (-not $env:CARGO_NET_RETRY) { $env:CARGO_NET_RETRY='8' }
    if (-not $env:CARGO_HTTP_TIMEOUT) { $env:CARGO_HTTP_TIMEOUT='120' }
    if (-not (Test-Path $PrivacyCoreDll)) {
        Write-Host 'Building privacy-core release DLL for full diagnostic regression...' -ForegroundColor Gray
        Invoke-Native 'cargo' @('build','--release','--locked','--manifest-path',$PrivacyCoreManifest) $RepoRoot
    }
    if (-not (Test-Path $PrivacyCoreDll)) { throw "privacy-core DLL missing: $PrivacyCoreDll" }
    $privacySha=(Get-FileHash -LiteralPath $PrivacyCoreDll -Algorithm SHA256).Hash.ToLowerInvariant()

    if (Test-Path $TestVenvDir) { Remove-Item $TestVenvDir -Recurse -Force }
    if (Test-Path $TestDataDir) { Remove-Item $TestDataDir -Recurse -Force }
    New-Item -ItemType Directory -Path $TestDataDir -Force | Out-Null

    Invoke-Native 'uv' @('export','--frozen','--python',$PortablePython,'--package','backend','--group','dev','--no-emit-project','--format','requirements.txt','--output-file',$TestRequirements) $RepoRoot
    Invoke-Native 'uv' @('venv','--python',$PortablePython,'--no-python-downloads','--clear',$TestVenvDir) $RepoRoot
    if (-not (Test-Path $TestPython)) { throw "Full regression Python missing: $TestPython" }
    Invoke-Native 'uv' @('pip','install','--python',$TestPython,'--compile-bytecode','--require-hashes','-r',$TestRequirements) $RepoRoot

    $env:SB_DATA_DIR=$TestDataDir
    $env:PYTHONPATH=$BackendDir
    $env:PRIVACY_CORE_LIB=$PrivacyCoreDll
    $env:PRIVACY_CORE_ALLOWED_SHA256=$privacySha
    $env:MESH_SECURE_STORAGE_SECRET='shadowbroker-r23-full-regression-test-only-secret-1f93cfe2'

    Write-Host 'Running the complete backend development regression suite (diagnostic, not a release blocker)...' -ForegroundColor Yellow
    Invoke-Native $TestPython @('-m','pytest','-q','backend\tests','--tb=short') $RepoRoot
}
finally {
    if ($null -eq $oldCargoRetry) { Remove-Item Env:CARGO_NET_RETRY -ErrorAction SilentlyContinue } else { $env:CARGO_NET_RETRY=$oldCargoRetry }
    if ($null -eq $oldCargoTimeout) { Remove-Item Env:CARGO_HTTP_TIMEOUT -ErrorAction SilentlyContinue } else { $env:CARGO_HTTP_TIMEOUT=$oldCargoTimeout }
    if ($null -eq $oldData) { Remove-Item Env:SB_DATA_DIR -ErrorAction SilentlyContinue } else { $env:SB_DATA_DIR=$oldData }
    if ($null -eq $oldPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH=$oldPath }
    if ($null -eq $oldLib) { Remove-Item Env:PRIVACY_CORE_LIB -ErrorAction SilentlyContinue } else { $env:PRIVACY_CORE_LIB=$oldLib }
    if ($null -eq $oldAllowed) { Remove-Item Env:PRIVACY_CORE_ALLOWED_SHA256 -ErrorAction SilentlyContinue } else { $env:PRIVACY_CORE_ALLOWED_SHA256=$oldAllowed }
    if ($null -eq $oldSecret) { Remove-Item Env:MESH_SECURE_STORAGE_SECRET -ErrorAction SilentlyContinue } else { $env:MESH_SECURE_STORAGE_SECRET=$oldSecret }
    if (-not $KeepTestWorkspace) {
        if (Test-Path $TestVenvDir) { Remove-Item $TestVenvDir -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path $TestDataDir) { Remove-Item $TestDataDir -Recurse -Force -ErrorAction SilentlyContinue }
    }
}
