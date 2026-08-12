# Windows Authenticode Code Signing

The Gökdoğan Intelligence Windows release workflow is ready to sign the installer when a valid code-signing certificate is supplied. Never commit the certificate or its password to source control, issues, pull requests or documentation.

## Required GitHub Actions secrets

Under **Repository → Settings → Secrets and variables → Actions**, define these repository secrets:

- `GOKDOGAN_WINDOWS_CERT_PFX_B64`
- `GOKDOGAN_WINDOWS_CERT_PASSWORD`

`GOKDOGAN_WINDOWS_CERT_PFX_B64` is the Base64 representation of the valid PFX/P12 code-signing certificate. `GOKDOGAN_WINDOWS_CERT_PASSWORD` is the PFX password.

## Creating the Base64 value locally

Without copying the certificate into the repository, run PowerShell:

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes('C:\PRIVATE\PATH\gokdogan-code-signing.pfx')) | Set-Clipboard
```

Paste that value directly into the GitHub Actions secret field. Do not add the PFX file to Git.

## Workflow behavior

When both secrets are present, `.github/workflows/desktop-release.yml`:

1. Decodes the PFX into the temporary GitHub runner directory.
2. Temporarily imports it into `Cert:\CurrentUser\My`.
3. Passes its thumbprint to the builder as `SHADOWBROKER_WINDOWS_CERT_THUMBPRINT`.
4. Sets `SHADOWBROKER_REQUIRE_WINDOWS_SIGNATURE=1` so signing becomes mandatory.
5. Removes the imported certificate from the runner certificate store during cleanup.

When the secrets are absent, the import step is skipped and the current workflow may produce an unsigned build. Always verify Authenticode status before a professional release.

## Verification

After downloading the release installer:

```powershell
Get-AuthenticodeSignature .\Gokdogan-Intelligence-v1.0.0-Setup.exe | Format-List Status,StatusMessage,SignerCertificate
```

For a signed professional release, the expected `Status` is `Valid`. Also verify the installer SHA-256 value against the manifest published with the GitHub Release.

## Security rules

- Never commit PFX/P12 files.
- Never put the certificate password in `.env`, workflow YAML or README files.
- Never disclose secret values in issues, PRs or logs.
- Rotate/update GitHub secrets when the certificate is renewed.
- If certificate compromise is suspected, follow the certificate authority's revocation process.
