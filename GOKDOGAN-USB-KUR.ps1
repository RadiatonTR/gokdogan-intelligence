[CmdletBinding()]
param(
    [switch]$Silent,
    [switch]$NoLaunch
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$installer = Join-Path $root 'Gokdogan-Intelligence-Desktop-Setup.exe'
$checksumFile = Join-Path $root 'SHA256SUMS.txt'
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


function Find-GokdoganExe {
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Gokdogan Intelligence Desktop\shadowbroker-tauri-shell.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Gokdogan Intelligence Desktop\shadowbroker-tauri-shell.exe'),
        (Join-Path $env:ProgramFiles 'Gokdogan Intelligence Desktop\shadowbroker-tauri-shell.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Gokdogan Intelligence Desktop'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Gokdogan Intelligence Desktop')
    )
    foreach ($scanRoot in $roots) {
        if (-not (Test-Path -LiteralPath $scanRoot)) { continue }
        $found = Get-ChildItem -LiteralPath $scanRoot -Filter 'shadowbroker-tauri-shell.exe' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    return $null
}

if (-not [Environment]::Is64BitOperatingSystem) {
    throw 'Gokdogan Windows desktop package requires 64-bit Windows.'
}
if (-not (Test-Path -LiteralPath $installer)) {
    throw "Gokdogan installer is missing from the USB distribution folder: $installer"
}
if (-not (Test-Path -LiteralPath $checksumFile)) {
    throw "SHA256SUMS.txt is missing: $checksumFile"
}

$expectedLine = Get-Content -LiteralPath $checksumFile -Encoding UTF8 | Where-Object { $_ -match 'Gokdogan-Intelligence-Desktop-Setup\.exe' } | Select-Object -First 1
if (-not $expectedLine) { throw 'Installer checksum entry was not found in SHA256SUMS.txt.' }
$expected = (($expectedLine -split '\s+')[0]).Trim().ToLowerInvariant()
$actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {
    throw "Installer SHA-256 verification failed. Expected $expected but got $actual"
}
Write-Host 'Gökdoğan kurulum öncesi eski çalışma süreçleri kapatılıyor.' -ForegroundColor Yellow
Stop-StaleGokdoganProcesses

$installerArgs = @()
if ($Silent) { $installerArgs += '/S' }
if ($installerArgs.Count -gt 0) {
    $proc = Start-Process -FilePath $installer -ArgumentList $installerArgs -Wait -PassThru
} else {
    $proc = Start-Process -FilePath $installer -Wait -PassThru
}
if ($proc.ExitCode -ne 0) { throw "Installer failed with exit code $($proc.ExitCode)." }

# Bazı NSIS yapılandırmaları kurulum sonunda uygulamayı otomatik açabilir.
# Öz testten önce yeni açılan pencere/managed backend de kapatılır.
Stop-StaleGokdoganProcesses

$exe = Find-GokdoganExe
if (-not $exe) { throw 'Gokdogan executable was not found after installation.' }
Write-Host "Installed executable: $exe" -ForegroundColor Gray
Write-Host 'Running installed-runtime self-test...' -ForegroundColor Cyan
$selfTest = Start-Process -FilePath $exe -ArgumentList @('--self-test') -Wait -PassThru
if ($selfTest.ExitCode -ne 0) {
    $stateDir = Join-Path $env:LOCALAPPDATA 'com.gokdogan.desktop'
    foreach ($name in @('desktop-self-test.json','backend_stderr.log','backend_stdout.log')) {
        $path = Join-Path $stateDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name ---" -ForegroundColor Yellow
            Get-Content -LiteralPath $path -Tail 120 -Encoding UTF8 -ErrorAction SilentlyContinue
        }
    }
    throw "Installed Gokdogan self-test failed with exit code $($selfTest.ExitCode)."
}
Write-Host 'Gokdogan installed-runtime self-test: PASS' -ForegroundColor Green
if (-not $NoLaunch) {
    Start-Process -FilePath $exe | Out-Null
}
