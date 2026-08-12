[CmdletBinding()]
param(
    [string]$BundleDir,
    [switch]$PreferMsi
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$stateDir = Join-Path $env:LOCALAPPDATA 'com.gokdogan.desktop'

function Stop-StaleGokdoganProcesses {
    $managedRoot = Join-Path $stateDir 'managed-backend'
    $names = @('shadowbroker-tauri-shell.exe', 'Gokdogan Intelligence Desktop.exe')
    $stopped = 0
    try {
        $processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
        foreach ($process in $processes) {
            $pidValue = [int]$process.ProcessId
            if ($pidValue -le 0 -or $pidValue -eq $PID) { continue }
            $name = [string]$process.Name
            $exePath = [string]$process.ExecutablePath
            $commandLine = [string]$process.CommandLine
            $owned = $names -contains $name
            if (-not $owned -and $managedRoot) {
                if ($exePath -and $exePath.StartsWith($managedRoot, [StringComparison]::OrdinalIgnoreCase)) { $owned = $true }
                elseif ($commandLine -and $commandLine.IndexOf($managedRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0) { $owned = $true }
            }
            if ($owned) {
                Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
                $stopped++
            }
        }
    } catch {}
    if ($stopped -gt 0) {
        Write-Host "Eski Gökdoğan çalışma süreçleri kapatıldı: $stopped" -ForegroundColor DarkYellow
        Start-Sleep -Milliseconds 900
    }
    if (Test-Path -LiteralPath $managedRoot) {
        try {
            $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            & icacls.exe $managedRoot /inheritance:e /grant "${identity}:(OI)(CI)F" /T /C /Q 2>$null | Out-Null
        } catch {}
    }
}

$statePath = Join-Path $stateDir 'install-state.json'
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
function Write-InstallState {
    param([string]$Status, [hashtable]$Extra = @{})
    $base = [ordered]@{
        product = 'Gokdogan Intelligence Desktop'
        version = '0.10.3'
        revision = 'R24'
        status = $Status
        updated_at = (Get-Date).ToUniversalTime().ToString('o')
    }
    foreach ($key in $Extra.Keys) { $base[$key] = $Extra[$key] }
    ($base | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $statePath -Encoding UTF8
}

if (-not $BundleDir) {
    $candidates = @(
        (Join-Path $root 'dist\windows\bundle'),
        (Join-Path $root 'bundle'),
        (Join-Path $root 'desktop-shell\tauri-skeleton\src-tauri\target\release\bundle')
    )
    $BundleDir = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $BundleDir -or -not (Test-Path $BundleDir)) {
    throw 'Windows installer bundle directory not found. Build R24 first or pass -BundleDir.'
}
$resolvedBundle = (Resolve-Path $BundleDir).Path
$nsis = @(Get-ChildItem -Path $resolvedBundle -Recurse -File -Filter '*.exe' -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\nsis\\|setup' } | Sort-Object LastWriteTime -Descending)
$msi = @(Get-ChildItem -Path $resolvedBundle -Recurse -File -Filter '*.msi' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending)

$installer = $null
$kind = $null
if ($PreferMsi -and $msi.Count -gt 0) { $installer = $msi[0]; $kind = 'msi' }
elseif ($nsis.Count -gt 0) { $installer = $nsis[0]; $kind = 'nsis' }
elseif ($msi.Count -gt 0) { $installer = $msi[0]; $kind = 'msi' }
if (-not $installer) { throw "No NSIS Setup EXE or MSI installer found under: $resolvedBundle" }
$installerHash = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$startedAtUtc = (Get-Date).ToUniversalTime().ToString('o')
Write-InstallState 'installing' @{ installer = $installer.FullName; installer_sha256 = $installerHash; installer_kind = $kind; bundle_dir = $resolvedBundle; started_at = $startedAtUtc }

Write-Host 'Gokdogan Intelligence Desktop - Install + Verify' -ForegroundColor Cyan
Write-Host "Installer: $($installer.FullName)" -ForegroundColor Gray
Write-Host 'Kurulum öncesi açık/eski Gökdoğan süreçleri kapatılıyor.' -ForegroundColor Yellow
Stop-StaleGokdoganProcesses

try {
    if ($kind -eq 'msi') {
        $proc = Start-Process -FilePath 'msiexec.exe' -ArgumentList @('/i', $installer.FullName) -Wait -PassThru
    } else {
        $proc = Start-Process -FilePath $installer.FullName -Wait -PassThru
    }
    if ($proc.ExitCode -ne 0) {
        Write-InstallState 'installer_failed' @{ installer = $installer.FullName; installer_sha256 = $installerHash; installer_kind = $kind; installer_exit_code = $proc.ExitCode; started_at = $startedAtUtc }
        throw "Installer failed with exit code $($proc.ExitCode)."
    }

    $verify = Join-Path $root 'WINDOWS-DESKTOP-VERIFY-INSTALL.ps1'
    if (-not (Test-Path $verify)) { throw "Installed-runtime verifier missing: $verify" }
    Write-Host 'Installer completed. Running headless installed-runtime self-test...' -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -LaunchAfterVerify
    $verifyExit = $LASTEXITCODE
    if ($verifyExit -ne 0) {
        Write-InstallState 'verification_failed' @{ installer = $installer.FullName; installer_sha256 = $installerHash; installer_kind = $kind; installer_exit_code = $proc.ExitCode; verify_exit_code = $verifyExit; started_at = $startedAtUtc }
        throw "Post-install verification failed with exit code $verifyExit."
    }
    $selfTestReport = Join-Path $stateDir 'desktop-self-test.json'
    $runtimeState = Join-Path $stateDir 'desktop-runtime-state.json'
    Write-InstallState 'verified' @{ installer = $installer.FullName; installer_sha256 = $installerHash; installer_kind = $kind; installer_exit_code = $proc.ExitCode; verify_exit_code = 0; started_at = $startedAtUtc; self_test_report = $selfTestReport; runtime_state = $runtimeState; verified_at = (Get-Date).ToUniversalTime().ToString('o') }
    Write-Host "Install state: $statePath" -ForegroundColor Gray
    Write-Host 'INSTALL + VERIFY PASSED.' -ForegroundColor Green
}
catch {
    if (-not (Test-Path $statePath)) {
        Write-InstallState 'failed' @{ installer = $installer.FullName; installer_sha256 = $installerHash; installer_kind = $kind; started_at = $startedAtUtc; error = $_.Exception.Message }
    }
    throw
}
