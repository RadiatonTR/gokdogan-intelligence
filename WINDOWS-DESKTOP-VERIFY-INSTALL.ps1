[CmdletBinding()]
param(
    [string]$ExePath,
    [switch]$LaunchAfterVerify
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

function Find-GokdoganExe {
    param([string]$Explicit)
    if ($Explicit -and (Test-Path $Explicit)) { return (Resolve-Path $Explicit).Path }
    $registryRoots = @(
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'
    )
    foreach ($reg in $registryRoots) {
        foreach ($item in @(Get-ItemProperty $reg -ErrorAction SilentlyContinue)) {
            if ($item.DisplayName -like 'Gokdogan Intelligence Desktop*') {
                if ($item.DisplayIcon) {
                    $candidate = ([string]$item.DisplayIcon).Trim('"').Split(',')[0]
                    if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
                }
                if ($item.InstallLocation -and (Test-Path $item.InstallLocation)) {
                    foreach ($name in @('Gokdogan Intelligence Desktop.exe', 'shadowbroker-tauri-shell.exe')) {
                        $candidate = Join-Path ([string]$item.InstallLocation) $name
                        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
                    }
                }
            }
        }
    }
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Gokdogan Intelligence Desktop\Gokdogan Intelligence Desktop.exe'),
        (Join-Path $env:LOCALAPPDATA 'Gokdogan Intelligence Desktop\Gokdogan Intelligence Desktop.exe'),
        (Join-Path $env:ProgramFiles 'Gokdogan Intelligence Desktop\Gokdogan Intelligence Desktop.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return (Resolve-Path $candidate).Path }
    }
    return $null
}
$exe = Find-GokdoganExe $ExePath
if (-not $exe) { throw 'Installed Gokdogan executable not found. The verifier will not fall back to a legacy ShadowBroker install.' }
Write-Host 'Gokdogan Intelligence Desktop - Installed Runtime Verification' -ForegroundColor Cyan
Write-Host "Executable: $exe" -ForegroundColor Gray
Write-Host 'Kurulum doğrulaması için açık/eski Gökdoğan süreçleri otomatik kapatılıyor.' -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Stop-StaleGokdoganProcesses
$report = Join-Path $stateDir 'desktop-self-test.json'
$selfTestStdout = Join-Path $stateDir 'desktop-self-test.stdout.log'
$selfTestStderr = Join-Path $stateDir 'desktop-self-test.stderr.log'
foreach ($path in @($report, $selfTestStdout, $selfTestStderr)) { if (Test-Path $path) { Remove-Item -LiteralPath $path -Force } }
$startedAt = Get-Date
$proc = Start-Process -FilePath $exe -ArgumentList '--self-test' -Wait -PassThru -RedirectStandardOutput $selfTestStdout -RedirectStandardError $selfTestStderr
if (Test-Path $selfTestStdout) {
    $stdoutText = Get-Content -LiteralPath $selfTestStdout -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($stdoutText) { Write-Host '--- installed self-test stdout ---' -ForegroundColor DarkGray; Write-Host $stdoutText }
}
if (Test-Path $selfTestStderr) {
    $stderrText = Get-Content -LiteralPath $selfTestStderr -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
    if ($stderrText) {
        # WebView2 can emit this harmless Chromium class-unregister message while
        # the headless self-test window is shutting down. Suppress only this
        # exact known shutdown noise; all other stderr remains visible.
        $stderrLines = @($stderrText -split "`r?`n" | Where-Object {
            $_ -and $_ -notmatch 'Failed to unregister class Chrome_WidgetWin_0\. Error = 1412'
        })
        if ($stderrLines.Count -gt 0) {
            Write-Host '--- installed self-test stderr ---' -ForegroundColor Yellow
            $stderrLines | Write-Host
        }
    }
}
$result = $null
if (Test-Path $report) {
    $reportItem = Get-Item -LiteralPath $report
    if ($reportItem.LastWriteTime -lt $startedAt.AddSeconds(-2)) { throw 'Installed runtime self-test report is stale.' }
    try { $result = Get-Content -LiteralPath $report -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw "Self-test report is not valid JSON: $($_.Exception.Message)" }
    Write-Host "Self-test report: $report" -ForegroundColor Gray
    Get-Content -LiteralPath $report -Encoding UTF8 | Write-Host
}
if ($proc.ExitCode -ne 0) {
    $backendData = Join-Path $stateDir 'managed-backend\data'
    foreach ($backendLogName in @('backend_stderr.log', 'backend_stdout.log')) {
        $backendLog = Join-Path $backendData $backendLogName
        if (Test-Path $backendLog) {
            Write-Host "--- $backendLogName (last 120 lines) ---" -ForegroundColor Yellow
            Get-Content -LiteralPath $backendLog -Tail 120 -Encoding UTF8 -ErrorAction SilentlyContinue | Write-Host
        }
    }
    $failureDetail = if ($result -and $result.failures) { ($result.failures -join ', ') } else { 'no self-test JSON failure detail was produced' }
    throw "Installed Gokdogan runtime self-test failed with exit code $($proc.ExitCode): $failureDetail"
}
if (-not $result) { throw "Installed runtime self-test returned success but did not create report: $report" }
if (-not $result.ok) { throw "Installed runtime self-test report indicates failure: $($result.failures -join ', ')" }
if ($result.PSObject.Properties.Name -notcontains 'api_key_system' -or -not $result.api_key_system) { throw 'Kurulu runtime öz testi API anahtar sistemini doğrulayamadı.' }
if ($result.PSObject.Properties.Name -notcontains 'runtime_integrity_enforced' -or -not $result.runtime_integrity_enforced) { throw 'Installed runtime self-test did not confirm runtime integrity enforcement.' }
$runtimeState = Join-Path $stateDir 'desktop-runtime-state.json'
if (-not (Test-Path $runtimeState)) { throw "Desktop runtime state report missing: $runtimeState" }
try { $runtime = Get-Content -LiteralPath $runtimeState -Raw -Encoding UTF8 | ConvertFrom-Json } catch { throw "Desktop runtime state is not valid JSON: $($_.Exception.Message)" }
if ($runtime.revision -ne 'R24' -or $runtime.version -ne '0.10.3') { throw "Installed runtime version mismatch. Expected 0.10.3/R24, got $($runtime.version)/$($runtime.revision)." }
if (-not $runtime.runtime_integrity_enforced) { throw 'Desktop runtime state reports integrity enforcement disabled.' }
if ($runtime.status -ne 'self_test_passed' -or -not $runtime.self_test_ok) { throw "Desktop runtime state is not healthy: $($runtime.status)" }
Write-Host "Runtime state: $runtimeState" -ForegroundColor Gray
Write-Host 'Installed Gokdogan runtime self-test PASSED.' -ForegroundColor Green
if ($LaunchAfterVerify) {
    Write-Host 'Opening Gokdogan Intelligence Desktop...' -ForegroundColor Cyan
    Start-Process -FilePath $exe
}
