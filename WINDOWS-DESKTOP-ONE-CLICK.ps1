[CmdletBinding()]
param(
    [switch]$SkipPrerequisiteInstall,
    [switch]$SkipBrowserRuntime,
    [switch]$CleanOnly
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-StrictMode -Version Latest

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $RepoRoot 'backend'
$FrontendDir = Join-Path $RepoRoot 'frontend'
$DesktopDir = Join-Path $RepoRoot 'desktop-shell'
$TauriDir = Join-Path $DesktopDir 'tauri-skeleton\src-tauri'
$PortablePythonDir = Join-Path $BackendDir '.desktop-python'
$PortableBrowsersDir = Join-Path $BackendDir '.desktop-browsers'
$DistDir = Join-Path $RepoRoot 'dist\windows'
$BuildLog = Join-Path $RepoRoot 'windows-desktop-build.log'
$BuildReportsDir = Join-Path $RepoRoot 'build-reports'
$NpmCacheDir = Join-Path $RepoRoot '.desktop-npm-cache'
$BuildRevision = 'R24' # Teknik çekirdek; dağıtım etiketi release-version.json içinde Gökdoğan Intelligence v1.0.0
$RequiredNodeMajor = 24
$RequiredRust = '1.97.1'
$RequiredTauriCli = '2.11.4'
$IncludeMeshHardware = ($env:SB_INCLUDE_MESH_HARDWARE -eq '1')
$env:NPM_CONFIG_UPDATE_NOTIFIER = 'false'

try {
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [Console]::InputEncoding = $utf8NoBom
    [Console]::OutputEncoding = $utf8NoBom
    $OutputEncoding = $utf8NoBom
}
catch {
    # Older redirected hosts may not expose a mutable console encoding.
}

function Write-Stage([int]$Number, [string]$Text) {
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
    Write-Host ("[{0:00}/10] {1}" -f $Number, $Text) -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkCyan
}

function Test-Command([string]$Name) {
    return $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

function Clear-StaleGeneratedReleaseArtifacts {
    # A previous interrupted stage-8 run can leave a complete bundled Python
    # tree under src-tauri. It is generated output, not source, and must be
    # removed before source compilation and secret scanning on the next run.
    $staleArtifacts = @(
        (Join-Path $TauriDir 'backend-runtime'),
        (Join-Path $TauriDir 'companion-www'),
        (Join-Path $FrontendDir 'out'),
        (Join-Path $RepoRoot '.desktop-export-build'),
        $DistDir
    )
    if ($env:LOCALAPPDATA) {
        # Stage only Tauri bundle resources here so makensis never sees
        # the much longer extracted release path. This directory is ours.
        $staleArtifacts += (Join-Path $env:LOCALAPPDATA 'SB-R24')
    }
    foreach ($artifact in $staleArtifacts) {
        if (Test-Path $artifact) {
            Write-Host "Removing stale generated release artifact: $artifact" -ForegroundColor Gray
            Remove-Item -LiteralPath $artifact -Recurse -Force -ErrorAction Stop
        }
    }
}

function Invoke-Native([string]$File, [string[]]$Arguments, [string]$WorkingDirectory = $RepoRoot) {
    Push-Location $WorkingDirectory
    try {
        & $File @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed ($LASTEXITCODE): $File $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Invoke-NativeWithRetry([string]$File, [string[]]$Arguments, [string]$WorkingDirectory = $RepoRoot, [int]$Attempts = 3) {
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Invoke-Native $File $Arguments $WorkingDirectory
            return
        }
        catch {
            if ($attempt -ge $Attempts) { throw }
            Write-Warning ("{0} failed on attempt {1}/{2}: {3}. Retrying with existing download cache..." -f $File, $attempt, $Attempts, $_.Exception.Message)
            Start-Sleep -Seconds ([Math]::Min(10, 2 * $attempt))
        }
    }
}

function Invoke-UvNetworkResilient([string[]]$Arguments, [string]$WorkingDirectory = $RepoRoot, [int]$Attempts = 3) {
    $oldRetries = $env:UV_HTTP_RETRIES
    $oldTimeout = $env:UV_HTTP_TIMEOUT
    $oldConnectTimeout = $env:UV_HTTP_CONNECT_TIMEOUT
    try {
        if (-not $env:UV_HTTP_RETRIES) { $env:UV_HTTP_RETRIES = '8' }
        if (-not $env:UV_HTTP_TIMEOUT) { $env:UV_HTTP_TIMEOUT = '120' }
        if (-not $env:UV_HTTP_CONNECT_TIMEOUT) { $env:UV_HTTP_CONNECT_TIMEOUT = '30' }
        Invoke-NativeWithRetry 'uv' $Arguments $WorkingDirectory $Attempts
    }
    finally {
        if ($null -eq $oldRetries) { Remove-Item Env:UV_HTTP_RETRIES -ErrorAction SilentlyContinue } else { $env:UV_HTTP_RETRIES = $oldRetries }
        if ($null -eq $oldTimeout) { Remove-Item Env:UV_HTTP_TIMEOUT -ErrorAction SilentlyContinue } else { $env:UV_HTTP_TIMEOUT = $oldTimeout }
        if ($null -eq $oldConnectTimeout) { Remove-Item Env:UV_HTTP_CONNECT_TIMEOUT -ErrorAction SilentlyContinue } else { $env:UV_HTTP_CONNECT_TIMEOUT = $oldConnectTimeout }
    }
}

function Remove-ProjectNodeModules([string]$WorkingDirectory, [string]$Name) {
    $nodeModules = Join-Path $WorkingDirectory 'node_modules'
    if (-not (Test-Path $nodeModules)) { return $true }

    Write-Host "Eski $Name node_modules klasoru temizleniyor..." -ForegroundColor Gray
    for ($attempt = 1; $attempt -le 6; $attempt++) {
        try {
            Remove-Item -LiteralPath $nodeModules -Recurse -Force -ErrorAction Stop
            return $true
        }
        catch {
            # Windows Defender / Explorer / npm child processes can briefly keep
            # package directories open.  Give them a short bounded grace period.
            Start-Sleep -Milliseconds ([Math]::Min(2500, 350 * $attempt))
        }
    }

    # cmd/rmdir occasionally succeeds where Remove-Item hits a transient EPERM.
    try {
        & cmd.exe /d /c "rmdir /s /q `"$nodeModules`"" 2>$null | Out-Null
    }
    catch { }
    if (-not (Test-Path $nodeModules)) { return $true }

    Write-Host (
        "Bilgi: $Name node_modules tamamen temizlenemedi; npm ci kendi atomik temizligini deneyecek. " +
        "Dosya kilidi surerse editor/terminal/antivirus taramasini kapatip yeniden deneyin."
    ) -ForegroundColor DarkYellow
    return $false
}

function Invoke-NpmCiAttempt(
    [string]$WorkingDirectory,
    [string]$Name,
    [string[]]$Arguments,
    [string]$AttemptLabel
) {
    New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null
    $safeName = ($Name -replace '[^A-Za-z0-9_.-]', '_')
    $attemptLog = Join-Path $BuildReportsDir ("npm-ci-{0}-{1}.log" -f $safeName, $AttemptLabel)

    Push-Location $WorkingDirectory
    try {
        # İlk/geçici ağ hatalarının tüm npm hata yığınını kullanıcı ekranına
        # dökmeyiz; ham çıktı tanı dosyasında korunur ve son deneme de başarısız
        # olursa aşağıda ekrana alınır.
        $npmArgs = $Arguments
        & npm @npmArgs *> $attemptLog
        $exitCode = $LASTEXITCODE
    }
    finally { Pop-Location }

    return @{
        ExitCode = $exitCode
        LogPath = $attemptLog
    }
}

function Invoke-NpmCiResilient([string]$WorkingDirectory, [string]$Name) {
    New-Item -ItemType Directory -Path $NpmCacheDir -Force | Out-Null
    [void](Remove-ProjectNodeModules $WorkingDirectory $Name)

    $npmArgs = @(
        'ci', '--cache', $NpmCacheDir, '--prefer-offline', '--no-audit', '--fund=false',
        '--fetch-retries=5', '--fetch-retry-factor=2',
        '--fetch-retry-mintimeout=5000', '--fetch-retry-maxtimeout=90000'
    )

    Write-Host "Installing locked npm dependencies for $Name (isolated build cache)..." -ForegroundColor Gray
    $first = Invoke-NpmCiAttempt $WorkingDirectory $Name $npmArgs 'attempt1'
    if ([int]$first.ExitCode -eq 0) {
        Write-Host "Locked npm dependencies ready: $Name" -ForegroundColor DarkGreen
        return
    }

    Write-Host (
        "Gecici npm indirme/dosya-kilidi sorunu algilandi (exit $($first.ExitCode)); " +
        "cache dogrulanip kontrollu yeniden deneme yapiliyor."
    ) -ForegroundColor DarkYellow

    $cacheVerifyLog = Join-Path $BuildReportsDir ("npm-cache-verify-{0}.log" -f ($Name -replace '[^A-Za-z0-9_.-]', '_'))
    & npm cache verify --cache $NpmCacheDir *> $cacheVerifyLog
    $cacheVerifyExit = $LASTEXITCODE
    if ($cacheVerifyExit -ne 0) {
        Write-Host "npm cache dogrulamasi basarisiz; yalniz izole build cache sifirlaniyor." -ForegroundColor DarkYellow
        try {
            if (Test-Path $NpmCacheDir) {
                Remove-Item -LiteralPath $NpmCacheDir -Recurse -Force -ErrorAction Stop
            }
        }
        catch {
            throw "Izole npm cache bozuk ve temizlenemedi: $($_.Exception.Message)"
        }
        New-Item -ItemType Directory -Path $NpmCacheDir -Force | Out-Null
    }

    [void](Remove-ProjectNodeModules $WorkingDirectory $Name)
    $retryArgs = @(
        'ci', '--cache', $NpmCacheDir, '--prefer-offline', '--no-audit', '--fund=false',
        '--fetch-retries=8', '--fetch-retry-factor=2',
        '--fetch-retry-mintimeout=5000', '--fetch-retry-maxtimeout=120000'
    )
    $retry = Invoke-NpmCiAttempt $WorkingDirectory $Name $retryArgs 'attempt2'
    if ([int]$retry.ExitCode -eq 0) {
        Write-Host "Locked npm dependencies ready after recovery: $Name" -ForegroundColor DarkGreen
        return
    }

    Write-Host ""
    Write-Host "npm ci son deneme tanisi ($($retry.LogPath)):" -ForegroundColor Red
    if (Test-Path $retry.LogPath) {
        Get-Content -LiteralPath $retry.LogPath -Tail 80 | ForEach-Object { Write-Host $_ }
    }
    # Release contract: will not rewrite package-lock.json during a release build.
    throw (
        "npm ci for $Name failed after isolated-cache recovery (exit $($retry.ExitCode)). " +
        "FINAL R4.8 package-lock.json dosyasini derleme sirasinda degistirmez. " +
        "Ag/proxy/antivirus durumunu ve build-reports altindaki npm-ci loglarini kontrol edin."
    )
}

function Invoke-OptionalNpmAudit([string]$WorkingDirectory, [string]$Name) {
    New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null
    $report = Join-Path $BuildReportsDir ("npm-audit-{0}.json" -f $Name)
    $stderrReport = Join-Path $BuildReportsDir ("npm-audit-{0}-stderr.log" -f $Name)
    try {
        # IMPORTANT (R18): do not use PowerShell native-output redirection here.
        # Windows PowerShell 5.1 can rewrite native stdout as UTF-16LE, which makes
        # a valid `npm audit --json` report unreadable to Node's UTF-8 JSON parser.
        # Capture native stdout/stderr verbatim as text and persist BOM-less UTF-8.
        $npmCommand = (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue)
        if (-not $npmCommand) { $npmCommand = Get-Command 'npm' -ErrorAction Stop }
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $npmPath = $npmCommand.Source
        $nodeCommand = Get-Command 'node.exe' -ErrorAction SilentlyContinue
        if (-not $nodeCommand) { $nodeCommand = Get-Command 'node' -ErrorAction Stop }
        $npmCli = Join-Path (Split-Path $npmPath -Parent) 'node_modules\npm\bin\npm-cli.js'
        if (Test-Path -LiteralPath $npmCli) {
            # Prefer invoking npm's JS entrypoint with node.exe. This avoids .cmd
            # CreateProcess/quoting differences between Windows PowerShell versions.
            $psi.FileName = $nodeCommand.Source
            $psi.Arguments = "`"$npmCli`" audit --omit=dev --json"
        }
        else {
            # Fallback for non-standard Node/npm layouts.
            $psi.FileName = $(if ($env:ComSpec) { $env:ComSpec } else { 'cmd.exe' })
            $escapedNpmPath = $npmPath.Replace('"', '""')
            $psi.Arguments = "/d /s /c `"`"$escapedNpmPath`" audit --omit=dev --json`""
        }
        $psi.WorkingDirectory = $WorkingDirectory
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        if (-not $proc.Start()) { throw "Could not start npm audit for $Name" }
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()
        $proc.WaitForExit()
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        $code = $proc.ExitCode
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($report, $stdout, $utf8NoBom)
        [System.IO.File]::WriteAllText($stderrReport, $stderr, $utf8NoBom)
        if ($code -ne 0) {
            Write-Warning "npm audit for $Name reported findings or could not complete (exit $code). UTF-8 report retained at $report; build continues to the audit policy gate."
        }
    }
    catch {
        Write-Warning "npm audit for $Name could not run: $($_.Exception.Message)"
        $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($stderrReport, $_.Exception.ToString(), $utf8NoBom)
    }
}

function Ensure-WingetPackage([string]$CommandName, [string]$PackageId, [string[]]$ExtraArgs = @()) {
    if (Test-Command $CommandName) { return }
    if ($SkipPrerequisiteInstall) {
        throw "$CommandName is required. Re-run without -SkipPrerequisiteInstall or install $PackageId manually."
    }
    if (-not (Test-Command 'winget')) {
        throw "Windows Package Manager (winget) is required for automatic prerequisite installation."
    }
    Write-Host "Installing $PackageId ..." -ForegroundColor Yellow
    $wingetArgs = @('install', '--id', $PackageId, '-e', '--accept-package-agreements', '--accept-source-agreements', '--silent') + $ExtraArgs
    Invoke-Native 'winget' $wingetArgs
    # Refresh process PATH after machine/user installer changes.
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user"
}

function Find-VCTools {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path $vswhere)) { return $null }
    $path = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if ($LASTEXITCODE -eq 0 -and $path) { return ($path | Select-Object -First 1) }
    return $null
}

function Ensure-VCTools {
    if (Find-VCTools) { return }
    if ($SkipPrerequisiteInstall) {
        throw 'Visual Studio 2022 C++ Build Tools (Desktop development with C++) are required by Tauri.'
    }
    if (-not (Test-Command 'winget')) { throw 'winget is required to install Visual Studio Build Tools automatically.' }
    Write-Host 'Installing Visual Studio 2022 C++ Build Tools. This may request elevation...' -ForegroundColor Yellow
    Invoke-Native 'winget' @(
        'install', '--id', 'Microsoft.VisualStudio.2022.BuildTools', '-e',
        '--accept-package-agreements', '--accept-source-agreements', '--silent',
        '--override', '--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
    )
    if (-not (Find-VCTools)) {
        throw 'Visual Studio C++ Build Tools installation could not be verified. Open Visual Studio Installer and add Desktop development with C++.'
    }
}

function Test-WingetPackageInstalled([string]$PackageId) {
    if (-not (Test-Command 'winget')) { return $false }
    $output = & winget list --id $PackageId -e --accept-source-agreements 2>&1
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) { return $false }
    return (($output | Out-String) -match [regex]::Escape($PackageId))
}

function Get-WebView2Version {
    # Official Evergreen WebView2 Runtime client id from Microsoft's deployment
    # documentation. On 64-bit Windows the machine registration normally lives
    # under WOW6432Node; user installs live under HKCU.
    $webViewKeys = @(
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKCU:\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    )
    foreach ($key in $webViewKeys) {
        if (-not (Test-Path $key)) { continue }
        try {
            $version = (Get-ItemProperty -LiteralPath $key -Name 'pv' -ErrorAction Stop).pv
            if ($version -and $version -ne '0.0.0.0') { return [string]$version }
        }
        catch {
            # A damaged/partial registration should not stop the fallback checks.
        }
    }
    return $null
}

function Ensure-WebView2 {
    $version = Get-WebView2Version
    if ($version) {
        Write-Host "Microsoft Edge WebView2 Runtime detected: $version" -ForegroundColor DarkGreen
        return
    }

    # Registry virtualization, enterprise images, or future installer changes can
    # make the registration key unavailable even though WinGet sees the runtime.
    if (Test-WingetPackageInstalled 'Microsoft.EdgeWebView2Runtime') {
        Write-Host 'Microsoft Edge WebView2 Runtime detected by WinGet.' -ForegroundColor DarkGreen
        return
    }

    if ($SkipPrerequisiteInstall) {
        Write-Warning 'WebView2 Runtime was not detected. Tauri requires it on Windows.'
        return
    }
    if (-not (Test-Command 'winget')) {
        throw 'WebView2 Runtime was not detected and winget is unavailable for automatic installation.'
    }

    Write-Host 'Installing Microsoft Edge WebView2 Runtime...' -ForegroundColor Yellow
    & winget install --id Microsoft.EdgeWebView2Runtime -e --accept-package-agreements --accept-source-agreements --silent
    $wingetExit = $LASTEXITCODE

    # WinGet can return a non-zero "no applicable upgrade" style code when the
    # package is already installed. Re-detect before deciding that the build must
    # fail; an installed runtime is the actual prerequisite we care about.
    $version = Get-WebView2Version
    $detectedByWinget = Test-WingetPackageInstalled 'Microsoft.EdgeWebView2Runtime'
    if ($version -or $detectedByWinget) {
        if ($wingetExit -ne 0) {
            Write-Warning "WinGet returned $wingetExit, but WebView2 Runtime is installed; continuing."
        }
        else {
            Write-Host 'Microsoft Edge WebView2 Runtime installation verified.' -ForegroundColor DarkGreen
        }
        return
    }

    if ($wingetExit -ne 0) {
        throw "WebView2 Runtime installation failed (winget exit $wingetExit) and the runtime could not be detected afterward."
    }
    throw 'WebView2 Runtime installer returned success, but the runtime could not be detected afterward.'
}

function Prepare-PortablePython {
    if (-not (Test-Command 'uv')) { throw 'uv is required before preparing the portable Python runtime.' }
    Invoke-UvNetworkResilient -Arguments @('python', 'install', '3.12') -WorkingDirectory $RepoRoot -Attempts 3
    $managedPython = (& uv python find --managed-python 3.12).Trim()
    if (-not $managedPython -or -not (Test-Path $managedPython)) {
        throw 'uv python find 3.12 did not return a usable interpreter.'
    }
    $managedRoot = Split-Path -Parent $managedPython
    if (Test-Path $PortablePythonDir) { Remove-Item $PortablePythonDir -Recurse -Force }
    Write-Host "Copying relocatable Python runtime from $managedRoot" -ForegroundColor Gray
    Copy-Item -LiteralPath $managedRoot -Destination $PortablePythonDir -Recurse
    $portablePython = Join-Path $PortablePythonDir 'python.exe'
    if (-not (Test-Path $portablePython)) { throw "Portable python.exe missing at $portablePython" }

    # uv-managed standalone interpreters intentionally carry an EXTERNALLY-MANAGED
    # marker. The copy above is application-owned, but mutating it through
    # `uv pip --python` still trips PEP 668. Install into the copied runtime's
    # site-packages using the repository's hash-pinned uv.lock instead of
    # resolving the newest compatible packages on every build.
    $portableSitePackages = Join-Path $PortablePythonDir 'Lib\site-packages'
    New-Item -ItemType Directory -Path $portableSitePackages -Force | Out-Null
    New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null
    $runtimeRequirements = Join-Path $BuildReportsDir 'backend-runtime-requirements.lock.txt'
    Write-Host 'Validating Python workspace lock presence (frozen release mode)...' -ForegroundColor Gray
    $uvLockPath = Join-Path $RepoRoot 'uv.lock'
    if (-not (Test-Path $uvLockPath)) { throw 'uv.lock is required for the frozen release build.' }
    Write-Host 'Exporting hash-pinned backend runtime requirements from uv.lock...' -ForegroundColor Gray
    $runtimeExportArgs = @(
        'export', '--frozen', '--python', $portablePython,
        '--package', 'backend', '--no-dev', '--no-emit-project',
        '--format', 'requirements.txt', '--output-file', $runtimeRequirements
    )
    if ($IncludeMeshHardware) {
        Write-Host 'Including optional Mesh Hardware SDK (Meshtastic/BLE) in the packaged runtime.' -ForegroundColor Yellow
        $runtimeExportArgs += @('--extra', 'mesh-hardware')
    }
    else {
        Write-Host 'Core runtime profile: optional Mesh Hardware SDK is excluded (set SB_INCLUDE_MESH_HARDWARE=1 to include it).' -ForegroundColor DarkGray
    }
    Invoke-Native 'uv' $runtimeExportArgs $RepoRoot
    if ((-not $IncludeMeshHardware) -and (Select-String -LiteralPath $runtimeRequirements -Pattern '^meshtastic==' -Quiet)) {
        throw 'Core runtime export unexpectedly contains meshtastic; dependency boundary is broken.'
    }
    Write-Host 'Installing locked backend Python dependencies into portable Lib\site-packages...' -ForegroundColor Gray
    $runtimeInstallArgs = @(
        'pip', 'install',
        '--python', $portablePython,
        '--target', $portableSitePackages,
        '--compile-bytecode', '--require-hashes',
        '-r', $runtimeRequirements
    )
    Invoke-UvNetworkResilient -Arguments $runtimeInstallArgs -WorkingDirectory $RepoRoot -Attempts 3

    Write-Host 'Validating packaged Python runtime imports...' -ForegroundColor Gray
    # Do not pass Python source through `python -c` here. Windows PowerShell 5.1
    # re-serializes native-process arguments and can strip the quotes embedded in
    # the code string (for example print("...") becomes print(...)), producing a
    # misleading SyntaxError even though the portable runtime is healthy. Execute
    # a real validation script instead so the check is shell-quoting independent.
    $runtimeValidator = Join-Path $RepoRoot 'scripts\windows\validate_portable_runtime.py'
    if (-not (Test-Path $runtimeValidator)) {
        throw "Portable runtime validator missing: $runtimeValidator"
    }
    Invoke-Native $portablePython @($runtimeValidator) $BackendDir

    if (-not $SkipBrowserRuntime) {
        if (Test-Path $PortableBrowsersDir) { Remove-Item $PortableBrowsersDir -Recurse -Force }
        New-Item -ItemType Directory -Path $PortableBrowsersDir -Force | Out-Null
        $oldBrowsers = $env:PLAYWRIGHT_BROWSERS_PATH
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PortableBrowsersDir
            Write-Host 'Installing bundled Playwright Chromium runtime...' -ForegroundColor Gray
            $playwrightInstaller = Join-Path $RepoRoot 'scripts\windows\install_playwright_runtime.py'
            if (-not (Test-Path $playwrightInstaller)) { throw "Playwright runtime installer helper missing: $playwrightInstaller" }
            Invoke-Native $portablePython @($playwrightInstaller) $BackendDir
        }
        finally {
            $env:PLAYWRIGHT_BROWSERS_PATH = $oldBrowsers
        }
    }
}

function Run-StaticChecks {
    $portablePython = Join-Path $PortablePythonDir 'python.exe'
    Invoke-Native $portablePython @('scripts\compile_backend_sources.py') $RepoRoot
    Invoke-Native $portablePython @('scripts\validate_intelligence_core.py') $RepoRoot
    Invoke-Native $portablePython @('scripts\generate_release_attestation.py') $RepoRoot
    Invoke-Native $portablePython @('scripts\validate_r24_release.py') $RepoRoot
    Invoke-Native $portablePython @('scripts\check_source_secrets.py') $RepoRoot
    Invoke-Native $portablePython @('scripts\check_architecture_budgets.py') $RepoRoot

    # R24 release tests intentionally mirror the maintained backend CI smoke lane.
    # The complete development suite remains available through
    # WINDOWS-DESKTOP-FULL-REGRESSION.bat, but it is not a packaging gate because
    # it contains lab/live-network/stale-contract tests that are not part of CI.
    Write-Host 'Running maintained backend release smoke + desktop regression lanes in isolated Python 3.12...' -ForegroundColor Gray
    New-Item -ItemType Directory -Path $BuildReportsDir -Force | Out-Null
    $testVenvDir = Join-Path $BuildReportsDir '.desktop-test-venv'
    $testPython = Join-Path $testVenvDir 'Scripts\python.exe'
    $testRequirements = Join-Path $BuildReportsDir 'backend-test-requirements.lock.txt'
    $testDataDir = Join-Path $BuildReportsDir '.desktop-test-data'
    $privacyCoreDll = Join-Path $RepoRoot 'privacy-core\target\release\privacy_core.dll'
    if (-not (Test-Path $privacyCoreDll)) { throw "privacy-core release DLL missing before test gate: $privacyCoreDll" }
    $privacyCoreSha = (Get-FileHash -LiteralPath $privacyCoreDll -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($privacyCoreSha -notmatch '^[0-9a-f]{64}$') { throw 'privacy-core SHA-256 could not be determined for the test lane.' }

    if (Test-Path $testVenvDir) { Remove-Item $testVenvDir -Recurse -Force }
    if (Test-Path $testDataDir) { Remove-Item $testDataDir -Recurse -Force }
    New-Item -ItemType Directory -Path $testDataDir -Force | Out-Null

    $oldSbDataDir = $env:SB_DATA_DIR
    $oldPythonPath = $env:PYTHONPATH
    $oldPrivacyCoreLib = $env:PRIVACY_CORE_LIB
    $oldPrivacyCoreAllowed = $env:PRIVACY_CORE_ALLOWED_SHA256
    $oldSecureStorageSecret = $env:MESH_SECURE_STORAGE_SECRET
    try {
        Invoke-Native 'uv' @('export', '--frozen', '--python', $portablePython, '--package', 'backend', '--group', 'dev', '--no-emit-project', '--format', 'requirements.txt', '--output-file', $testRequirements) $RepoRoot
        Invoke-Native 'uv' @('venv', '--python', $portablePython, '--no-python-downloads', '--clear', $testVenvDir) $RepoRoot
        if (-not (Test-Path $testPython)) { throw "Isolated backend test Python was not created: $testPython" }
        Invoke-UvNetworkResilient -Arguments @('pip', 'install', '--python', $testPython, '--compile-bytecode', '--require-hashes', '-r', $testRequirements) -WorkingDirectory $RepoRoot -Attempts 3

        $env:SB_DATA_DIR = $testDataDir
        $env:PYTHONPATH = $BackendDir
        $env:PRIVACY_CORE_LIB = $privacyCoreDll
        $env:PRIVACY_CORE_ALLOWED_SHA256 = $privacyCoreSha
        $env:MESH_SECURE_STORAGE_SECRET = 'shadowbroker-r24-release-test-only-secret-7f6c52e1'

        $releaseSmoke = @(
            'tests\mesh\test_mesh_node_bootstrap_runtime.py',
            'tests\mesh\test_mesh_infonet_sync_support.py',
            'tests\mesh\test_mesh_canonical.py',
            'tests\mesh\test_mesh_merkle.py',
            'tests\test_release_helper.py',
            'tests\mesh\test_privacy_core_startup_policy.py'
        )
        $smokeArgs = @('-m', 'pytest') + $releaseSmoke + @('-q', '--tb=short')
        Invoke-Native $testPython $smokeArgs $BackendDir

        # Windows desktop/intelligence contracts run from repository root because
        # these tests intentionally reference repository-relative paths.
        $desktopRegression = @(
            'backend\tests\test_intelligence_core.py',
            'backend\tests\test_intelligence_core_r7.py',
            'backend\tests\test_intelligence_core_r8.py',
            'backend\tests\test_intelligence_core_r9.py',
            'backend\tests\test_desktop_runtime_manifest_contract.py',
            'backend\tests\test_windows_desktop_builder_contract.py',
            'backend\tests\test_r24_windows_release_gate.py',
            'backend\tests\test_gokdogan_hf12_desktop_resilience.py',
            'backend\tests\test_gokdogan_hf13_feature_readiness.py',
            'backend\tests\test_gokdogan_hf14_usb_public_camera.py',
            'backend\tests\test_gokdogan_hf15_tauri_async_command_contract.py',
            'backend\tests\test_gokdogan_hf16_runtime_live_data.py',
            'backend\tests\test_gokdogan_hf17_acl_links_live_defaults.py',
            'backend\tests\test_gokdogan_hf18_frontend_live_defaults_contract.py',
            'backend\tests\test_gokdogan_final_acl_contract.py',
            'backend\tests\test_gokdogan_gd1_r1_final.py',
            'backend\tests\test_gokdogan_gd1_r2_public_ops.py',
            'backend\tests\test_gokdogan_gd1_r3_health_turkish.py',
            'backend\tests\test_gokdogan_gd1_r4_operations.py',
            'backend\tests\test_gokdogan_r46_api_system_stability.py',
            'backend\tests\test_gokdogan_r47_runtime_lock_cleanup.py',
            'backend\tests\test_gokdogan_r48_usb_powershell_parser.py',
            'backend\tests\test_gokdogan_v1_release_contract.py'
        )
        $regressionArgs = @('-m', 'pytest') + $desktopRegression + @('-q', '--tb=short')
        Invoke-Native $testPython $regressionArgs $RepoRoot
    }
    finally {
        if ($null -eq $oldSbDataDir) { Remove-Item Env:SB_DATA_DIR -ErrorAction SilentlyContinue } else { $env:SB_DATA_DIR = $oldSbDataDir }
        if ($null -eq $oldPythonPath) { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue } else { $env:PYTHONPATH = $oldPythonPath }
        if ($null -eq $oldPrivacyCoreLib) { Remove-Item Env:PRIVACY_CORE_LIB -ErrorAction SilentlyContinue } else { $env:PRIVACY_CORE_LIB = $oldPrivacyCoreLib }
        if ($null -eq $oldPrivacyCoreAllowed) { Remove-Item Env:PRIVACY_CORE_ALLOWED_SHA256 -ErrorAction SilentlyContinue } else { $env:PRIVACY_CORE_ALLOWED_SHA256 = $oldPrivacyCoreAllowed }
        if ($null -eq $oldSecureStorageSecret) { Remove-Item Env:MESH_SECURE_STORAGE_SECRET -ErrorAction SilentlyContinue } else { $env:MESH_SECURE_STORAGE_SECRET = $oldSecureStorageSecret }
        if (Test-Path $testVenvDir) { Remove-Item $testVenvDir -Recurse -Force -ErrorAction SilentlyContinue }
        if (Test-Path $testDataDir) { Remove-Item $testDataDir -Recurse -Force -ErrorAction SilentlyContinue }
    }

    Write-Host 'Running warning-free frontend ESLint gate...' -ForegroundColor Gray
    Invoke-Native 'npm' @('--prefix', 'frontend', 'run', 'lint') $RepoRoot
    Write-Host 'Running full frontend Vitest suite...' -ForegroundColor Gray
    Invoke-Native 'npm' @('--prefix', 'frontend', 'test') $RepoRoot
    Write-Host 'Running Rust/Tauri unit tests...' -ForegroundColor Gray
    # tauri-build validates every configured bundle resource even for
    # `cargo test`. The real companion/frontend and managed backend trees are
    # generated later by build.ps1, so provide temporary directory roots for
    # this unit-test-only compile and remove only the directories created here.
    $tauriTestResourceRoots = @(
        (Join-Path $TauriDir 'companion-www'),
        (Join-Path $TauriDir 'backend-runtime')
    )
    $temporaryTauriTestResourceRoots = @()
    try {
        foreach ($resourceRoot in $tauriTestResourceRoots) {
            if (-not (Test-Path $resourceRoot)) {
                New-Item -ItemType Directory -Path $resourceRoot -Force | Out-Null
                $temporaryTauriTestResourceRoots += $resourceRoot
            }
        }
        Invoke-Native 'cargo' @('test', '--locked', '--manifest-path', 'desktop-shell\tauri-skeleton\src-tauri\Cargo.toml') $RepoRoot
    }
    finally {
        foreach ($resourceRoot in $temporaryTauriTestResourceRoots) {
            if (Test-Path $resourceRoot) {
                Remove-Item -LiteralPath $resourceRoot -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Invoke-Native 'node' @('--check', 'desktop-shell\tauri-skeleton\scripts\build-backend-runtime.cjs') $RepoRoot
    Invoke-Native 'npm' @('--prefix', 'desktop-shell', 'run', 'typecheck') $RepoRoot
    $frontendTsc = Join-Path $FrontendDir 'node_modules\.bin\tsc.cmd'
    if (-not (Test-Path $frontendTsc)) { throw "Frontend TypeScript compiler missing: $frontendTsc" }
    Invoke-Native $frontendTsc @('--noEmit') $FrontendDir
}

Start-Transcript -Path $BuildLog -Force | Out-Null
try {
    Write-Stage 1 'Windows / architecture preflight'
    if ($env:OS -ne 'Windows_NT') { throw 'This build entrypoint must run on Windows.' }
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows is required.' }
    Write-Host "Windows: $([Environment]::OSVersion.VersionString)"
    Write-Host "Repository: $RepoRoot"
    Write-Host "Desktop builder revision: $BuildRevision"
    Clear-StaleGeneratedReleaseArtifacts

    Write-Stage 2 'Build prerequisites'
    Ensure-WingetPackage 'node' 'OpenJS.NodeJS.LTS'
    Ensure-WingetPackage 'uv' 'astral-sh.uv'
    Ensure-WingetPackage 'rustup' 'Rustlang.Rustup'
    Ensure-VCTools
    Ensure-WebView2
    if (-not (Test-Command 'cargo')) {
        $cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
        if (Test-Path $cargoBin) { $env:Path = "$cargoBin;$env:Path" }
    }
    foreach ($cmd in @('node', 'npm', 'uv', 'rustup', 'cargo')) {
        if (-not (Test-Command $cmd)) { throw "$cmd was not available after prerequisite setup." }
    }
    $installedToolchains = (& rustup toolchain list | Out-String)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect locally installed Rust toolchains.' }
    $requiredRustPattern = ('(?m)^' + [regex]::Escape($RequiredRust) + '(?:-|\s|$)')
    if ($installedToolchains -match $requiredRustPattern) {
        Write-Host "Rust $RequiredRust is already installed locally; skipping rustup network sync/install." -ForegroundColor Green
    }
    else {
        Write-Host "Rust $RequiredRust is not installed locally. Installing pinned minimal toolchain..." -ForegroundColor Gray
        $oldRustupRetry = $env:RUSTUP_MAX_RETRIES
        try {
            if (-not $env:RUSTUP_MAX_RETRIES) { $env:RUSTUP_MAX_RETRIES = '5' }
            Invoke-NativeWithRetry 'rustup' @('toolchain', 'install', $RequiredRust, '--profile', 'minimal', '--no-self-update') $RepoRoot 3
        }
        catch {
            throw "Rust $RequiredRust is required but was not installed locally and rustup could not download it. Check DNS/network access to static.rust-lang.org, then rerun START-HERE.bat. Original error: $($_.Exception.Message)"
        }
        finally {
            if ($null -eq $oldRustupRetry) { Remove-Item Env:RUSTUP_MAX_RETRIES -ErrorAction SilentlyContinue } else { $env:RUSTUP_MAX_RETRIES = $oldRustupRetry }
        }
    }
    Invoke-Native 'rustup' @('override', 'set', $RequiredRust) $RepoRoot
    $rustVersion = (& rustup run $RequiredRust rustc --version | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $rustVersion -notmatch [regex]::Escape($RequiredRust)) { throw "Rust toolchain mismatch. Expected $RequiredRust, got: $rustVersion" }
    $nodeMajor = [int]((& node -p "process.versions.node.split('.')[0]").Trim())
    if ($nodeMajor -ne $RequiredNodeMajor) { throw "Node.js major mismatch. Expected $RequiredNodeMajor.x, got $(& node --version)" }

    Write-Stage 3 'Node dependencies (R24 security-patched locked installs)'
    Invoke-Native 'node' @('scripts\validate-npm-locks.cjs') $RepoRoot
    Invoke-Native 'node' @('scripts\verify-npm-security-baseline.cjs', '--source') $RepoRoot
    Invoke-Native 'python' @('scripts\check_release_cleanliness.py') $RepoRoot
    Invoke-Native 'python' @('scripts\check_turkish_release_profile.py') $RepoRoot
    # FINAL R4: kilit dosyalari kaynak agacinda degistirilmez; npm ci yalniz --locked kaynakla calisir.
    Invoke-NpmCiResilient $BackendDir 'backend-node'
    Invoke-NpmCiResilient $FrontendDir 'frontend'
    Invoke-NpmCiResilient $DesktopDir 'desktop-shell'
    Invoke-Native 'node' @('scripts\test-npm-audit-encoding.cjs') $RepoRoot
    Invoke-Native 'node' @('scripts\test-npm-audit-policy.cjs') $RepoRoot
    Invoke-OptionalNpmAudit $BackendDir 'backend-node'
    Invoke-OptionalNpmAudit $FrontendDir 'frontend'
    Invoke-OptionalNpmAudit $DesktopDir 'desktop-shell'
    Invoke-Native 'node' @('scripts\evaluate-npm-audits.cjs', $BuildReportsDir) $RepoRoot

    Write-Stage 4 'Self-contained Python 3.12 backend runtime'
    Prepare-PortablePython

    Write-Stage 5 'Tauri CLI and Rust desktop toolchain'
    $tauriCliWorkDir = $RepoRoot
    $cargoManifestPath = Join-Path $TauriDir 'Cargo.toml'
    $cargoLockPath = Join-Path $TauriDir 'Cargo.lock'
    $cargoBin = Join-Path $env:USERPROFILE '.cargo\bin'
    if ((Test-Path $cargoBin) -and ($env:Path -notlike "*$cargoBin*")) { $env:Path = "$cargoBin;$env:Path" }

    function Get-PinnedTauriCliVersion {
        if (-not (Test-Command 'cargo-tauri')) { return $null }
        try {
            $versionText = (& cargo-tauri -V 2>&1 | Out-String).Trim()
            if ($LASTEXITCODE -ne 0) { return $null }
            return $versionText
        }
        catch { return $null }
    }

    $oldCargoNetRetry = $env:CARGO_NET_RETRY
    $oldCargoHttpTimeout = $env:CARGO_HTTP_TIMEOUT
    try {
        if (-not $env:CARGO_NET_RETRY) { $env:CARGO_NET_RETRY = '8' }
        if (-not $env:CARGO_HTTP_TIMEOUT) { $env:CARGO_HTTP_TIMEOUT = '120' }

        $tauriVersion = Get-PinnedTauriCliVersion
        if (-not $tauriVersion -or $tauriVersion -notmatch [regex]::Escape($RequiredTauriCli)) {
            if ($tauriVersion) {
                Write-Host "Replacing Tauri CLI '$tauriVersion' with pinned $RequiredTauriCli..." -ForegroundColor Yellow
            } else {
                Write-Host "Tauri CLI is not installed. Installing pinned Tauri CLI $RequiredTauriCli..." -ForegroundColor Yellow
            }
            Invoke-NativeWithRetry 'cargo' @('install', 'tauri-cli', '--version', $RequiredTauriCli, '--locked', '--force') $tauriCliWorkDir 3
            if ((Test-Path $cargoBin) -and ($env:Path -notlike "*$cargoBin*")) { $env:Path = "$cargoBin;$env:Path" }
            $tauriVersion = Get-PinnedTauriCliVersion
        }
        if (-not $tauriVersion -or $tauriVersion -notmatch [regex]::Escape($RequiredTauriCli)) {
            throw "Tauri CLI mismatch after bootstrap. Expected $RequiredTauriCli, got: $tauriVersion"
        }
        Write-Host "Tauri CLI: $tauriVersion" -ForegroundColor Green

        if (-not (Test-Path $cargoManifestPath)) { throw "Tauri Cargo.toml not found: $cargoManifestPath" }

        # R18 never relies on the caller's current directory for Cargo project
        # discovery. The manifest path is explicit for lock refresh, metadata,
        # and dependency-tree validation.
        $requiredCargoPackages = @(
            @{ Name = 'tauri'; Version = '2.11.5' },
            @{ Name = 'tauri-plugin-single-instance'; Version = '2.4.3' },
            @{ Name = 'tauri-plugin-notification'; Version = '2.3.3' },
            @{ Name = 'tauri-plugin-updater'; Version = '2.10.1' },
            @{ Name = 'tauri-plugin-process'; Version = '2.3.1' }
        )
        $cargoLockNeedsRefresh = -not (Test-Path $cargoLockPath)
        if (-not $cargoLockNeedsRefresh) {
            $cargoLockText = Get-Content -LiteralPath $cargoLockPath -Raw
            foreach ($package in $requiredCargoPackages) {
                $pattern = '(?ms)^\[\[package\]\]\s+name = "' + [regex]::Escape($package.Name) + '"\s+version = "' + [regex]::Escape($package.Version) + '"'
                if ($cargoLockText -notmatch $pattern) {
                    $cargoLockNeedsRefresh = $true
                    break
                }
            }
        }
        if ($cargoLockNeedsRefresh) {
            Write-Host 'Cargo.lock eksik veya sabitlenmis Tauri surumleriyle uyumsuz; tam sabitlenmis Cargo.toml surumlerinden yeniden olusturuluyor...' -ForegroundColor Yellow
            $oldCargoLockHash = $null
            if (Test-Path $cargoLockPath) {
                try { $oldCargoLockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $cargoLockPath).Hash.ToLowerInvariant() } catch { }
            }

            # Cargo.toml kritik Tauri bagimliliklarini exact (=x.y.z) olarak sabitler.
            # Bu nedenle eski/eksik lock dosyasini kullaniciya birakmak yerine burada
            # kontrollu bicimde yeniden uretip hemen ardindan exact surumleri dogrulariz.
            Invoke-NativeWithRetry 'cargo' @('generate-lockfile', '--manifest-path', $cargoManifestPath) $RepoRoot 3
            if (-not (Test-Path $cargoLockPath)) {
                throw 'Cargo.lock yeniden olusturulamadi.'
            }

            $cargoLockText = Get-Content -LiteralPath $cargoLockPath -Raw
            foreach ($package in $requiredCargoPackages) {
                $pattern = '(?ms)^\[\[package\]\]\s+name = "' + [regex]::Escape($package.Name) + '"\s+version = "' + [regex]::Escape($package.Version) + '"'
                if ($cargoLockText -notmatch $pattern) {
                    throw ("Cargo.lock yeniden olusturuldu ancak beklenen sabit paket cozulmedi: {0} {1}" -f $package.Name, $package.Version)
                }
            }

            $newCargoLockHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $cargoLockPath).Hash.ToLowerInvariant()
            $lockRepairReport = Join-Path $RepoRoot 'build-reports\cargo-lock-repair.txt'
            $reportLines = @(
                'GOKDOGAN INTELLIGENCE v1.0.0 Cargo.lock self-repair',
                ('time_utc=' + [DateTime]::UtcNow.ToString('o')),
                ('old_sha256=' + $(if ($oldCargoLockHash) { $oldCargoLockHash } else { 'missing' })),
                ('new_sha256=' + $newCargoLockHash),
                'source=Cargo.toml exact pinned Tauri dependencies'
            )
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $lockRepairReport) | Out-Null
            Set-Content -LiteralPath $lockRepairReport -Value $reportLines -Encoding UTF8
            Write-Host "Cargo.lock onarildi; sha256=$newCargoLockHash" -ForegroundColor Green
        }

        Invoke-NativeWithRetry 'cargo' @('metadata','--manifest-path',$cargoManifestPath,'--locked','--format-version','1','--no-deps') $RepoRoot 3
        Push-Location $RepoRoot
        try {
            $tree = (& cargo tree --manifest-path $cargoManifestPath --locked -p shadowbroker-tauri-shell | Out-String)
            if ($LASTEXITCODE -ne 0) { throw 'cargo tree failed for the pinned Tauri manifest.' }
        }
        finally { Pop-Location }
        foreach ($required in @('tauri v2.11.5','tauri-plugin-single-instance v2.4.3','tauri-plugin-notification v2.3.3','tauri-plugin-updater v2.10.1','tauri-plugin-process v2.3.1')) {
            if ($tree -notmatch [regex]::Escape($required)) { throw "Pinned Rust dependency not resolved: $required" }
        }


        # R24: privacy-core is a first-class runtime prerequisite, not a late
        # packaging side effect. Build the Windows cdylib before backend tests so
        # maintained MLS/privacy smoke tests exercise the same native artifact
        # that will be staged into the desktop runtime.
        $privacyCoreManifest = Join-Path $RepoRoot 'privacy-core\Cargo.toml'
        $privacyCoreDll = Join-Path $RepoRoot 'privacy-core\target\release\privacy_core.dll'
        if (-not (Test-Path $privacyCoreManifest)) { throw "privacy-core Cargo.toml not found: $privacyCoreManifest" }
        Write-Host 'Building pinned privacy-core release DLL before backend release tests...' -ForegroundColor Gray
        Invoke-NativeWithRetry 'cargo' @('build', '--release', '--locked', '--manifest-path', $privacyCoreManifest) $RepoRoot 3
        if (-not (Test-Path $privacyCoreDll)) { throw "privacy-core build completed but Windows DLL is missing: $privacyCoreDll" }
        $privacyCoreSha = (Get-FileHash -LiteralPath $privacyCoreDll -Algorithm SHA256).Hash.ToLowerInvariant()
        Write-Host "privacy-core release DLL ready: sha256=$privacyCoreSha" -ForegroundColor Green
    }
    finally {
        if ($null -eq $oldCargoNetRetry) { Remove-Item Env:CARGO_NET_RETRY -ErrorAction SilentlyContinue } else { $env:CARGO_NET_RETRY = $oldCargoNetRetry }
        if ($null -eq $oldCargoHttpTimeout) { Remove-Item Env:CARGO_HTTP_TIMEOUT -ErrorAction SilentlyContinue } else { $env:CARGO_HTTP_TIMEOUT = $oldCargoHttpTimeout }
    }

    Write-Stage 6 'Static checks and desktop contract typecheck'
    Run-StaticChecks

    if ($CleanOnly) {
        Write-Host 'Clean/check-only run requested; stopping before packaging.' -ForegroundColor Yellow
        return
    }

    Write-Stage 7 'Frontend static export + managed backend staging'
    # build.ps1 performs both operations and validates the staged trees.
    Write-Host 'The next stage is executed by the desktop build wrapper.' -ForegroundColor Gray

    Write-Stage 8 'Windows Tauri release build (single NSIS installer)'
    # Custom source builds must never consume the upstream updater channel by
    # accident. Signed auto-update is enabled only when the builder is given an
    # explicit custom update endpoint/public key and SHADOWBROKER_ENABLE_SIGNED_UPDATER=1.
    if ($env:SHADOWBROKER_ENABLE_SIGNED_UPDATER -eq '1') {
        $env:NEXT_PUBLIC_SB_CUSTOM_DESKTOP = '0'
        Write-Host 'Signed desktop updater: explicitly enabled.' -ForegroundColor DarkGreen
    }
    else {
        $env:NEXT_PUBLIC_SB_CUSTOM_DESKTOP = '1'
        Write-Host 'Signed desktop updater: disabled for custom local build.' -ForegroundColor DarkGray
    }
    $env:SB_BUILD_REVISION = $BuildRevision
    Invoke-Native 'npm' @('--prefix', 'desktop-shell', 'run', 'build:desktop:clean') $RepoRoot

    Write-Stage 9 'Collect installers, manifests, checksums, SBOM, and audit reports'
    $portablePython = Join-Path $PortablePythonDir 'python.exe'
    $portableSitePackages = Join-Path $PortablePythonDir 'Lib\site-packages'
    Invoke-Native $portablePython @('scripts\generate_sbom.py', '--root', $RepoRoot, '--site-packages', $portableSitePackages, '--output', (Join-Path $RepoRoot 'SBOM-R24.cdx.json')) $RepoRoot
    Invoke-Native $portablePython @('scripts\generate_release_attestation.py') $RepoRoot
    $bundleDir = Join-Path $TauriDir 'target\release\bundle'
    if (-not (Test-Path $bundleDir)) { throw "Tauri bundle output not found: $bundleDir" }
    Invoke-Native 'powershell.exe' @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $RepoRoot 'scripts\validate_windows_bundle.ps1'),'-BundleDir',$bundleDir) $RepoRoot
    if (Test-Path $DistDir) { Remove-Item $DistDir -Recurse -Force }
    New-Item -ItemType Directory -Path $DistDir -Force | Out-Null
    Copy-Item -LiteralPath $bundleDir -Destination (Join-Path $DistDir 'bundle') -Recurse
    foreach ($name in @('release-manifest.json', 'SHA256SUMS.txt')) {
        $candidate = Join-Path $bundleDir $name
        if (Test-Path $candidate) { Copy-Item $candidate $DistDir }
    }
    foreach ($name in @(
        'SBOM-R24.cdx.json',
        'R24-IMPLEMENTATION-MANIFEST.json',
        'WINDOWS-DESKTOP-VERIFY-INSTALL.ps1',
        'WINDOWS-DESKTOP-VERIFY-INSTALL.bat',
        'WINDOWS-DESKTOP-DATA-RECOVERY.ps1',
        'WINDOWS-DESKTOP-DATA-RECOVERY.bat',
        'WINDOWS-DESKTOP-INSTALL-AND-VERIFY.ps1',
        'WINDOWS-DESKTOP-INSTALL-AND-VERIFY.bat',
        'WINDOWS-DESKTOP-DATA-MAINTENANCE.ps1',
        'WINDOWS-DESKTOP-HEALTH-CHECK.bat',
        'WINDOWS-DESKTOP-AUTO-REPAIR.bat'
    )) {
        $candidate = Join-Path $RepoRoot $name
        if (Test-Path $candidate) { Copy-Item $candidate $DistDir }
    }
    $recoveryHelper = Join-Path $RepoRoot 'scripts\windows\recover_intelligence_database.py'
    if (Test-Path $recoveryHelper) {
        $recoveryScriptDir = Join-Path $DistDir 'scripts\windows'
        New-Item -ItemType Directory -Path $recoveryScriptDir -Force | Out-Null
        Copy-Item -LiteralPath $recoveryHelper -Destination $recoveryScriptDir -Force
    }
    # Do not copy transient build reports into user-facing distribution output.
    # They remain in the builder workspace for diagnostics but are intentionally
    # excluded from the USB/install bundle.

    Write-Stage 10 'Create clean Windows + USB distribution packages'
    $zipPath = Join-Path $RepoRoot 'dist\Gokdogan-Intelligence-v1.0.0-Windows-Desktop-Bundle.zip'
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Compress-Archive -Path (Join-Path $DistDir '*') -DestinationPath $zipPath -CompressionLevel Optimal

    $usbDir = Join-Path $RepoRoot 'dist\GOKDOGAN-INTELLIGENCE-v1.0.0-OFFLINE-USB'
    $usbPrepare = Join-Path $RepoRoot 'GOKDOGAN-USB-DAGITIM-HAZIRLA.ps1'
    if (-not (Test-Path -LiteralPath $usbPrepare)) { throw "USB distribution helper missing: $usbPrepare" }
    Invoke-Native 'powershell.exe' @('-NoProfile','-ExecutionPolicy','Bypass','-File',$usbPrepare,'-BundleDir',$bundleDir,'-OutputDir',$usbDir) $RepoRoot
    $usbZip = Join-Path $RepoRoot 'dist\Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip'
    if (Test-Path -LiteralPath $usbZip) { Remove-Item -LiteralPath $usbZip -Force }
    Compress-Archive -Path (Join-Path $usbDir '*') -DestinationPath $usbZip -CompressionLevel Optimal

    Write-Host ""
    Write-Host 'BUILD COMPLETE' -ForegroundColor Green
    Write-Host "Installers: $DistDir" -ForegroundColor Green
    Write-Host "Bundle ZIP: $zipPath" -ForegroundColor Green
    Write-Host "USB folder: $usbDir" -ForegroundColor Green
    Write-Host "USB ZIP: $usbZip" -ForegroundColor Green
    Write-Host "Log: $BuildLog" -ForegroundColor DarkGray
    Write-Host "START-HERE will now continue automatically with NSIS install, verification, and app launch." -ForegroundColor Yellow
    try { if (Test-Path $NpmCacheDir) { Remove-Item -LiteralPath $NpmCacheDir -Recurse -Force -ErrorAction Stop } } catch { Write-Warning "Could not remove temporary npm build cache: $($_.Exception.Message)" }
}
finally {
    Stop-Transcript | Out-Null
}
