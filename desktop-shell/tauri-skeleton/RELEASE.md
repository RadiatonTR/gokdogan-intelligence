# Desktop Release Guide

This directory has a repeatable desktop release path with branded bundle
icons, checksums, SBOM/attestation output, optional signed-updater artifacts,
and optional Windows Authenticode integration. Signing private keys are never
stored in this source tree.

## Entry points

Use any of these:

```bash
# POSIX shell
./build.sh

# Windows PowerShell
./build.ps1

# Cross-platform npm wrapper
npm --prefix desktop-shell run build:desktop
```

Use `--clean` when you want to wipe the previous static export, companion
bundle, managed backend bundle, generated icons, and old installer outputs
before rebuilding.

Prerequisites:

- Rust toolchain
- `cargo tauri` 2.11.4 (the R7 one-click builder installs/verifies the exact CLI)
- Node.js / npm with the frontend dependencies already installed

## CI / GitHub Actions

The repo also has a desktop matrix workflow at:

```text
.github/workflows/desktop-release.yml
```

What it does today:

- builds unsigned desktop artifacts on Windows, macOS, and Linux
- uploads bundle artifacts for PRs and branch builds
- on `v*.*.*` tags, attaches release assets to the GitHub release
- forwards Apple signing/notarization secrets to the macOS build **if** they
  exist, but does not require them

See [RELEASE_INPUTS.md](./RELEASE_INPUTS.md) for the plain-language answer to
"what would I need later?".

## What the build does

1. Generates the desktop icon set in `src-tauri/icons/`
2. Stages a desktop-only frontend export tree that omits Next server-only
   routes/proxy (`src/app/api`, `src/proxy.ts`)
3. Stages a managed backend runtime bundle into `src-tauri/backend-runtime/`
4. Builds the frontend export with `NEXT_OUTPUT=export`
5. Copies `frontend/out` into `src-tauri/companion-www/`
6. Runs `cargo tauri build -- --locked`
7. Writes:
   - `src-tauri/target/release/bundle/SHA256SUMS.txt`
   - `src-tauri/target/release/bundle/release-manifest.json`
   - `src-tauri/target/release/bundle/latest.json` when signed updater
     artifacts are present

For CI/release builds, the backend release-gate attestation is also staged into
the managed backend bundle at `backend-runtime/data/release_attestation.json`,
and the managed-backend updater refreshes that file on version sync without
overwriting the rest of the runtime `data/` directory.

## Release artifacts

Artifacts are emitted under:

```text
desktop-shell/tauri-skeleton/src-tauri/target/release/bundle/
```

Expected bundle types vary by platform:

- Windows: `.msi`, `.exe`
- macOS: `.dmg`, `.app`-related archives
- Linux: `.deb`, `.AppImage`

## What is still distributor-controlled

- Windows Authenticode certificate/private key and public-trust publication.
- A custom update endpoint plus a Tauri updater signing private key, if automatic
  updates are intentionally enabled.
- macOS signing/notarization if non-Windows builds are produced later.

## R7 updater notes

The source configuration contains **no updater endpoint and no updater public
key**. The main WebView also receives no updater/process capability by default.
The Windows build enables update artifacts only when
`SHADOWBROKER_ENABLE_SIGNED_UPDATER=1` and an operator supplies a custom update
endpoint, public verification key, and the Tauri signing private key through
environment/secrets outside the source tree. The build script temporarily
injects those values and restores the least-privilege source configuration
afterward.

Updater package signing and Windows Authenticode signing are separate trust
mechanisms. Both must be configured for a publicly distributed automatic-update
channel.

## Trust model reminder

The packaged build still uses:

- a bundled local backend runtime that the desktop app owns by default
- Rust-authoritative policy enforcement for privileged local control
- the packaged loopback app server for same-origin non-privileged `/api/*`
- reduced-trust browser companion mode with no native bridge injection
