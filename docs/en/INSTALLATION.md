# Installation Guide

This document contains Windows installation and source-build notes for Gökdoğan Intelligence v1.0.0.

## 1. Supported environment

- Windows 10/11 x64
- Microsoft Edge WebView2 Runtime
- PowerShell 5.1 or newer
- Internet connection for source builds
- Several GB of free disk space recommended for source builds

The builder validates/prepares the Node 24.x, Rust 1.97.1 and Python 3.12 toolchain defined by the release contract.

## 2. End-user installation

The following files may be published through GitHub Releases:

- `Gokdogan-Intelligence-v1.0.0-Setup.exe`
- `Gokdogan-Intelligence-v1.0.0-Windows-Desktop-Bundle.zip`
- `Gokdogan-Intelligence-v1.0.0-OFFLINE-USB.zip`
- `SHA256SUMS.txt`

### SHA-256 verification

PowerShell example:

```powershell
Get-FileHash .\Gokdogan-Intelligence-v1.0.0-Setup.exe -Algorithm SHA256
```

Compare the output with the value published in `SHA256SUMS.txt` in the GitHub Release.

> A build created without a code-signing certificate may appear as unsigned (`NotSigned`) in Windows. Do not run an installer whose hash does not match the published checksum.

## 3. One-click build from source

1. Extract the Source ZIP into a new, empty directory.
2. Prefer a reasonably short directory path.
3. Run `START-HERE.bat`.
4. Read and approve Windows security/UAC prompts when appropriate.
5. Keep the terminal open until the build completes.

### What the builder does

- Windows and architecture preflight checks
- WebView2 checks
- Node/npm locked-dependency installation
- npm audit/release security gates
- Python 3.12 managed-runtime preparation
- Hash-pinned Python dependencies through `uv.lock`
- Cargo/Tauri lock validation
- Backend regression tests
- Frontend ESLint, Vitest and TypeScript checks
- Rust/Tauri unit tests
- Frontend static export
- Managed-backend staging
- NSIS installer creation
- SBOM, SHA-256 and release manifests
- Offline USB package
- Installed-runtime self-test

## 4. Build outputs

After a successful build, the `dist` directory contains the installer and supported bundle/USB distribution packages.

## 5. First launch

1. Start Gökdoğan.
2. Verify that the map opens.
3. Open **Ayarlar → API Anahtarları** (Settings → API Keys).
4. Enter keys only for the providers you need.
5. Run **API SİSTEMİNİ TEST ET** to verify the API system.
6. Check provider status in **Kaynak Sağlığı / İstihbarat Merkezi**.
7. Start with the `DENGELİ` (Balanced) operating profile.

The v1.0.0 desktop UI is Turkish-first; the repository documentation is available in both Turkish and English.

## 6. Updating

- Do not extract a new version over an old source directory.
- Extract each new Source ZIP into a separate directory.
- User runtime data is stored in the application data area under `%LOCALAPPDATA%`.
- Never copy API keys into GitHub or the source directory.

## 7. Build diagnostic files

- `start-here.log`
- `windows-desktop-build.log`
- `GOKDOGAN-DIAGNOSTIC.zip`

Before attaching diagnostics to an issue, make sure they contain no API keys, `.env` contents, private URLs or personal data.
