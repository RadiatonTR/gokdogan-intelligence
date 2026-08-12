param(
  [switch]$Clean
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..\..")
$frontendDir = Join-Path $repoRoot "frontend"
$frontendOut = Join-Path $frontendDir "out"
$srcTauriDir = Join-Path $scriptDir "src-tauri"
$tauriConfigPath = Join-Path $srcTauriDir "tauri.conf.json"
$capabilityPath = Join-Path $srcTauriDir "capabilities\main.json"
$defaultCompanionDir = Join-Path $srcTauriDir "companion-www"
$defaultBackendRuntimeDir = Join-Path $srcTauriDir "backend-runtime"
$shortResourceRoot = $null
if ($env:OS -eq "Windows_NT") {
  if (-not $env:LOCALAPPDATA) {
    throw "LOCALAPPDATA is required to stage Windows installer resources on a short physical path."
  }
  # makensis still uses Win32 path-limited file APIs. Keep its physical input
  # path independent of the user's (possibly very long) extracted ZIP path.
  $shortResourceRoot = Join-Path $env:LOCALAPPDATA "SB-R24"
  $companionDir = Join-Path $shortResourceRoot "companion-www"
  $backendRuntimeDir = Join-Path $shortResourceRoot "backend-runtime"
}
else {
  $companionDir = $defaultCompanionDir
  $backendRuntimeDir = $defaultBackendRuntimeDir
}
$originalBackendRuntimeOutput = $env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT
$iconsScript = Join-Path $scriptDir "scripts\generate-icons.cjs"
$exportScript = Join-Path $scriptDir "scripts\build-frontend-export.cjs"
$backendRuntimeScript = Join-Path $scriptDir "scripts\build-backend-runtime.cjs"
$manifestScript = Join-Path $scriptDir "scripts\write-release-manifest.cjs"
$localUpdaterKey = Join-Path $repoRoot "release-secrets\shadowbroker-updater.key"
$localUpdaterKeyPassword = Join-Path $repoRoot "release-secrets\shadowbroker-updater.key.pass"
$tauriBundleAttempts = 4
$tauriReleaseExe = Join-Path $srcTauriDir "target\release\shadowbroker-tauri-shell.exe"

function Invoke-External {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Command,
    [string]$WorkingDirectory = $scriptDir
  )

  $exe = $Command[0]
  $commandArgs = @()
  if ($Command.Length -gt 1) {
    $commandArgs = $Command[1..($Command.Length - 1)]
  }

  Push-Location $WorkingDirectory
  try {
    & $exe @commandArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Command failed: $($Command -join ' ')"
    }
  }
  finally {
    Pop-Location
  }
}

function Write-Utf8NoBom {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [Parameter(Mandatory = $true)]
    [string]$Content
  )

  $encoding = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Convert-ToTauriResourceSource {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Path
  )

  # Tauri's source-to-target resource map accepts absolute source paths. A
  # trailing slash means "copy this directory's contents" into the target.
  return (([System.IO.Path]::GetFullPath($Path) -replace '\\', '/').TrimEnd('/') + '/')
}

function Test-TransientTauriToolFailure {
  param([string]$Output)

  if (-not $Output) {
    return $false
  }
  $hasToolDownloadContext = $Output -match '(?i)(github(?:usercontent)?\.com|tauri.{0,40}(?:tool|download)|wix.{0,40}download|nsis.{0,40}download)'
  $hasNetworkFailure = $Output -match '(?i)(could not resolve|name resolution|\bDNS\b|timed? out|connection (?:reset|refused)|failed to download|error sending request)'
  return $hasToolDownloadContext -and $hasNetworkFailure
}

foreach ($tool in @("cargo", "npm", "node")) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    throw "$tool is required for desktop packaging."
  }
}

if (-not (Get-Command "cargo-tauri" -ErrorAction SilentlyContinue)) {
  throw "The pinned Cargo Tauri CLI is required for desktop packaging. Run the root WINDOWS-DESKTOP-ONE-CLICK.bat bootstrap first."
}

try {
  if ($shortResourceRoot) {
    if (Test-Path $shortResourceRoot) {
      Remove-Item -LiteralPath $shortResourceRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Path $shortResourceRoot -Force | Out-Null
  }
  $env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT = $backendRuntimeDir

if ($Clean) {
  Write-Host "=== Cleaning previous desktop release artifacts ==="
  foreach ($path in @(
    $frontendOut,
    $companionDir,
    $backendRuntimeDir,
    $defaultCompanionDir,
    $defaultBackendRuntimeDir,
    (Join-Path $srcTauriDir "icons"),
    (Join-Path $srcTauriDir "target\\release\\bundle"),
    (Join-Path $srcTauriDir "target\\release\\wix"),
    (Join-Path $srcTauriDir "target\\release\\nsis")
  )) {
    if (Test-Path $path) {
      Remove-Item -LiteralPath $path -Recurse -Force
    }
  }
  Write-Host ""
}

Write-Host "=== Generating branded desktop icons ==="
Invoke-External -Command @("node", $iconsScript)
Write-Host ""

Write-Host "=== Building frontend static export for desktop packaging ==="
Invoke-External -Command @("node", $exportScript)
Write-Host ""

Write-Host "=== Staging managed backend runtime for desktop packaging ==="
Invoke-External -Command @("node", $backendRuntimeScript)
Write-Host ""

Write-Host "=== Validating staged managed backend runtime ==="
$stagedPython = Join-Path $backendRuntimeDir "python-runtime\python.exe"
$stagedRuntimeValidator = Join-Path $repoRoot "scripts\validate_staged_desktop_runtime.py"
if (-not (Test-Path $stagedPython)) {
  throw "Staged portable Python missing: $stagedPython"
}
# The validator executes with the staged interpreter, so it must not mutate the
# runtime tree merely by importing stdlib modules before integrity checks run.
$originalDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
try {
  $env:PYTHONDONTWRITEBYTECODE = "1"
  Invoke-External -Command @($stagedPython, "-B", $stagedRuntimeValidator, "--runtime", $backendRuntimeDir) -WorkingDirectory $repoRoot
}
finally {
  if ($null -eq $originalDontWriteBytecode) {
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
  }
  else {
    $env:PYTHONDONTWRITEBYTECODE = $originalDontWriteBytecode
  }
}
Write-Host ""

if (-not (Test-Path $frontendOut)) {
  throw "frontend/out was not produced by NEXT_OUTPUT=export npm run build"
}
if (-not (Test-Path $backendRuntimeDir)) {
  throw "backend-runtime was not produced by build-backend-runtime.cjs: $backendRuntimeDir"
}

Write-Host "Copying frontend export to companion-www..."
if (Test-Path $companionDir) {
  Remove-Item -LiteralPath $companionDir -Recurse -Force
}
Copy-Item -LiteralPath $frontendOut -Destination $companionDir -Recurse
$fileCount = (Get-ChildItem -LiteralPath $companionDir -Recurse -File | Measure-Object).Count
Write-Host "  -> $fileCount files"
Write-Host ""

if ($shortResourceRoot) {
  $resourceFiles = @(Get-ChildItem -LiteralPath $shortResourceRoot -Recurse -File -Force)
  if ($resourceFiles.Count -eq 0) {
    throw "NSIS resource staging produced no files: $shortResourceRoot"
  }
  $longestResourceFile = $resourceFiles |
    Sort-Object { $_.FullName.Length } -Descending |
    Select-Object -First 1
  $maxResourcePathLength = $longestResourceFile.FullName.Length
  if ($maxResourcePathLength -ge 240) {
    throw "NSIS resource source path preflight failed: $maxResourcePathLength characters (limit 239): $($longestResourceFile.FullName)"
  }
  Write-Host "NSIS resource source path preflight: PASS ($maxResourcePathLength/239 characters)" -ForegroundColor Green
  Write-Host ""
}

Push-Location $srcTauriDir
$tauriConfigBackup = $null
$capabilityBackup = $null
$originalTauriToolsMirror = $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR
try {
  if (-not $env:SHADOWBROKER_BACKEND_URL) {
    $env:SHADOWBROKER_BACKEND_URL = "http://127.0.0.1:8000"
  }
  if (
    -not $env:TAURI_SIGNING_PRIVATE_KEY -and
    -not $env:TAURI_SIGNING_PRIVATE_KEY_PATH -and
    (Test-Path $localUpdaterKey)
  ) {
    $env:TAURI_SIGNING_PRIVATE_KEY = Get-Content -LiteralPath $localUpdaterKey -Raw
    if (($null -eq $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) -and (Test-Path $localUpdaterKeyPassword)) {
      $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = (Get-Content -LiteralPath $localUpdaterKeyPassword -Raw).Trim()
    }
  }

  $enableSignedUpdater = $env:SHADOWBROKER_ENABLE_SIGNED_UPDATER -eq "1"
  $tauriConfigBackup = Get-Content -LiteralPath $tauriConfigPath -Raw
  $capabilityBackup = Get-Content -LiteralPath $capabilityPath -Raw
  $tauriConfig = $tauriConfigBackup | ConvertFrom-Json
  $capability = $capabilityBackup | ConvertFrom-Json

  # Use Tauri's source-to-target resource map: makensis reads from the short
  # physical paths, while the installed application still receives the exact
  # companion-www/ and backend-runtime/ directory names expected at runtime.
  $resourceMap = [ordered]@{}
  $resourceMap[(Convert-ToTauriResourceSource $companionDir)] = "companion-www/"
  $resourceMap[(Convert-ToTauriResourceSource $backendRuntimeDir)] = "backend-runtime/"
  $tauriConfig.bundle.resources = $resourceMap

  Write-Host "=== ShadowBroker Tauri Build ==="
  Write-Host "Frontend dist:    $frontendOut"
  Write-Host "Companion www:    $companionDir"
  Write-Host "Backend runtime:  $backendRuntimeDir"
  Write-Host "Backend URL:      $env:SHADOWBROKER_BACKEND_URL"

  $windowsCertThumbprint = ($env:SHADOWBROKER_WINDOWS_CERT_THUMBPRINT -replace '\s','').ToUpperInvariant()
  if ($windowsCertThumbprint) {
    if ($windowsCertThumbprint -notmatch '^[0-9A-F]{40,64}$') {
      throw "SHADOWBROKER_WINDOWS_CERT_THUMBPRINT has an invalid format."
    }
    $certPath = "Cert:\CurrentUser\My\$windowsCertThumbprint"
    if (-not (Test-Path $certPath)) {
      throw "Windows code-signing certificate not found in CurrentUser/My: $windowsCertThumbprint"
    }
    $tauriConfig.bundle.windows | Add-Member -NotePropertyName certificateThumbprint -NotePropertyValue $windowsCertThumbprint -Force
    if ($env:SHADOWBROKER_WINDOWS_TIMESTAMP_URL) {
      $tauriConfig.bundle.windows.timestampUrl = $env:SHADOWBROKER_WINDOWS_TIMESTAMP_URL
    }
    Write-Host "Authenticode:     enabled ($windowsCertThumbprint)"
  } else {
    if ($tauriConfig.bundle.windows.PSObject.Properties.Name -contains 'certificateThumbprint') {
      $tauriConfig.bundle.windows.PSObject.Properties.Remove('certificateThumbprint')
    }
    Write-Host "Authenticode:     disabled (no certificate thumbprint configured)"
  }

  if ($enableSignedUpdater) {
    if (-not $env:SHADOWBROKER_UPDATE_ENDPOINT) {
      throw "SHADOWBROKER_ENABLE_SIGNED_UPDATER=1 requires SHADOWBROKER_UPDATE_ENDPOINT (the full latest.json URL)."
    }
    if (-not $env:SHADOWBROKER_UPDATER_PUBKEY) {
      throw "SHADOWBROKER_ENABLE_SIGNED_UPDATER=1 requires SHADOWBROKER_UPDATER_PUBKEY."
    }
    if (-not ($env:TAURI_SIGNING_PRIVATE_KEY -or $env:TAURI_SIGNING_PRIVATE_KEY_PATH)) {
      throw "Signed updater is enabled but no Tauri signing private key is configured."
    }
    $tauriConfig.bundle.createUpdaterArtifacts = $true
    $tauriConfig.plugins.updater.pubkey = $env:SHADOWBROKER_UPDATER_PUBKEY
    $tauriConfig.plugins.updater.endpoints = @($env:SHADOWBROKER_UPDATE_ENDPOINT)
    # Updater/process IPC capability is granted only for a deliberately configured,
    # signed custom channel. The source tree itself stays least-privilege.
    $capability.permissions = @("core:default", "gokdogan-main-native", "updater:default", "process:default")
    $env:SHADOWBROKER_TAURI_UPDATER_ENABLED = "1"
    Write-Host "Updater signing:  enabled for explicit custom channel"
    Write-Host "Updater endpoint: $env:SHADOWBROKER_UPDATE_ENDPOINT"
  }
  else {
    $tauriConfig.bundle.createUpdaterArtifacts = $false
    $tauriConfig.plugins.updater.pubkey = ""
    $tauriConfig.plugins.updater.endpoints = @()
    $capability.permissions = @("core:default", "gokdogan-main-native")
    $env:SHADOWBROKER_TAURI_UPDATER_ENABLED = "0"
    Write-Host "Updater signing:  disabled; updater/process IPC permissions removed"
  }

  $tauriConfig |
    ConvertTo-Json -Depth 100 |
    ForEach-Object { Write-Utf8NoBom -Path $tauriConfigPath -Content ($_ + "`n") }
  $capability |
    ConvertTo-Json -Depth 100 |
    ForEach-Object { Write-Utf8NoBom -Path $capabilityPath -Content ($_ + "`n") }
  Write-Host ""

  # Tauri downloads its pinned WiX/NSIS tools from GitHub on first use. Keep
  # already downloaded bytes in Tauri's verified cache and retry only the
  # bundle command so a transient DNS/connection failure does not discard the
  # completed Rust release compilation. An explicit HTTPS mirror can be
  # supplied without changing the reproducible source package.
  if (-not $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR -and $env:SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR) {
    $configuredMirror = $env:SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR.Trim().TrimEnd('/')
    $mirrorUri = $null
    if (-not [Uri]::TryCreate($configuredMirror, [UriKind]::Absolute, [ref]$mirrorUri) -or $mirrorUri.Scheme -ne 'https') {
      throw "SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR must be an absolute HTTPS URL."
    }
    $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR = $configuredMirror
    Write-Host "Tauri bundler tools mirror: explicit HTTPS mirror enabled"
  }

  $tauriBundleSucceeded = $false
  $completedBundleAttempts = 0
  $lastBundleOutput = ""
  for ($bundleAttempt = 1; $bundleAttempt -le $tauriBundleAttempts; $bundleAttempt++) {
    # The bundled Python/Chromium runtime contains thousands of files. WiX 3's
    # light.exe is not a reliable linker for this payload, while Tauri's NSIS
    # target is the supported single-EXE installer already preferred by the
    # install-and-verify flow.
    # Windows PowerShell 5.1 converts native stderr redirected through a
    # pipeline into NativeCommandError records. Cargo/Tauri writes normal
    # progress and Info lines to stderr, so the script-wide Stop preference
    # would otherwise terminate a successful build on its first Info line.
    # Temporarily keep those records non-terminating, normalize each to plain
    # text, mirror it live, and retain it for precise failure classification.
    $bundleOutputLines = New-Object 'System.Collections.Generic.List[string]'
    $bundleErrorActionPreference = $ErrorActionPreference
    try {
      $ErrorActionPreference = "Continue"
      & cargo tauri build --bundles nsis -- --locked 2>&1 | ForEach-Object {
        $bundleLine = if ($_ -is [System.Management.Automation.ErrorRecord] -and $_.Exception -and $_.Exception.Message) {
          $_.Exception.Message
        } else {
          $_.ToString()
        }
        if ([string]::IsNullOrWhiteSpace($bundleLine) -or $bundleLine -eq 'System.Management.Automation.RemoteException') { return }
        [void]$bundleOutputLines.Add($bundleLine)
        Write-Host $bundleLine
      }
      $bundleExitCode = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $bundleErrorActionPreference
    }
    $completedBundleAttempts = $bundleAttempt
    $lastBundleOutput = $bundleOutputLines -join [Environment]::NewLine
    if ($bundleExitCode -eq 0) {
      $tauriBundleSucceeded = $true
      if ($bundleAttempt -gt 1) {
        Write-Host "Tauri bundler download/package retry recovered on attempt $bundleAttempt/$tauriBundleAttempts." -ForegroundColor Green
      }
      break
    }

    $isTransientToolFailure = Test-TransientTauriToolFailure $lastBundleOutput
    if (-not $isTransientToolFailure) {
      Write-Host "Tauri NSIS bundle attempt $bundleAttempt/$tauriBundleAttempts failed with a non-transient build/package error; automatic retry skipped." -ForegroundColor Red
      break
    }
    if ($bundleAttempt -lt $tauriBundleAttempts) {
      $retryDelaySeconds = [Math]::Min(20, 4 * $bundleAttempt)
      Write-Host "Tauri NSIS bundle attempt $bundleAttempt/$tauriBundleAttempts hit a transient tool-download network error; restoring an unpatched release binary and retrying with the verified tool cache in $retryDelaySeconds seconds..." -ForegroundColor Yellow
      # Tauri writes its bundle-type marker into the release executable before
      # packaging. Reusing that already-patched binary causes the misleading
      # '__TAURI_BUNDLE_TYPE variable not found' warning on a retry. Rebuild the
      # executable from Cargo's incremental cache before the next attempt.
      if (Test-Path $tauriReleaseExe) {
        Remove-Item -LiteralPath $tauriReleaseExe -Force
      }
      cargo build --release --locked
      if ($LASTEXITCODE -ne 0) {
        throw "Failed to restore the unpatched Rust release executable before Tauri bundle retry."
      }
      if (-not (Test-Path $tauriReleaseExe)) {
        throw "Cargo reported success but the restored Rust release executable is missing: $tauriReleaseExe"
      }
      Start-Sleep -Seconds $retryDelaySeconds
    }
  }
  if (-not $tauriBundleSucceeded) {
    $firstBundlerError = $lastBundleOutput -split "`r?`n" |
      Where-Object { $_ -match '(?i)(File: failed|Error in script|failed to bundle|error:|could not resolve|failed to download)' } |
      Select-Object -First 1
    if (-not $firstBundlerError) {
      $firstBundlerError = "No specific bundler error line was captured; inspect the output immediately above."
    }
    if (Test-TransientTauriToolFailure $lastBundleOutput) {
      throw "cargo tauri NSIS build failed after $completedBundleAttempts transient tool-download attempt(s). First error: $firstBundlerError Set SHADOWBROKER_TAURI_TOOLS_GITHUB_MIRROR only if the error explicitly names a GitHub DNS/download failure."
    }
    throw "cargo tauri NSIS build failed after $completedBundleAttempts attempt(s). First error: $firstBundlerError"
  }

  $bundleDir = Join-Path $srcTauriDir "target\release\bundle"
  if (Test-Path $bundleDir) {
    Write-Host ""
    Write-Host "=== Writing release manifest ==="
    Invoke-External -Command @("node", $manifestScript, $bundleDir)
  }
}
finally {
  if ($null -ne $tauriConfigBackup) {
    Write-Utf8NoBom -Path $tauriConfigPath -Content $tauriConfigBackup
  }
  if ($null -ne $capabilityBackup) {
    Write-Utf8NoBom -Path $capabilityPath -Content $capabilityBackup
  }
  if ($null -eq $originalTauriToolsMirror) {
    Remove-Item Env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR -ErrorAction SilentlyContinue
  } else {
    $env:TAURI_BUNDLER_TOOLS_GITHUB_MIRROR = $originalTauriToolsMirror
  }
  Pop-Location
}
}
finally {
  if ($null -eq $originalBackendRuntimeOutput) {
    Remove-Item Env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT -ErrorAction SilentlyContinue
  }
  else {
    $env:SHADOWBROKER_BACKEND_RUNTIME_OUTPUT = $originalBackendRuntimeOutput
  }
  if ($shortResourceRoot -and (Test-Path $shortResourceRoot)) {
    Remove-Item -LiteralPath $shortResourceRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
