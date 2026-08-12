# Security Policy — Gökdoğan Intelligence

## Supported versions

The actively supported public release line is `v1.x`. Security fixes are applied to the latest stable release whenever practical.

## Reporting a vulnerability

Do not publish security vulnerabilities in public GitHub Issues, Discussions, screenshots or social-media posts.

If **Private Vulnerability Reporting** is available in the repository's Security section, use it. If it is unavailable, establish a private contact channel with the project owner through the GitHub profile before sharing technical details.

A useful report should include:

- affected Gökdoğan version,
- concise technical description,
- safe and minimal reproduction steps,
- expected impact,
- a suggested remediation when available.

## Never include

- real API keys or tokens,
- passwords,
- PFX/PEM/private-key files,
- personal data,
- content obtained without authorization from third-party systems,
- credentials for closed/private camera systems,
- sensitive person or operational target data.

## Project security approach

The release flow uses controls including:

- `scripts/check_release_cleanliness.py`,
- runtime integrity manifests,
- SHA-256 artifact summaries,
- release attestation/provenance,
- dependency lock files,
- Windows runtime self-tests,
- GitHub Actions CI and release gates.

Authenticode code signing is recommended for production Windows distribution. Certificates and private keys must never be embedded in source code or release packages.

## API keys

Real API keys must not be committed to GitHub. `.env.example` should contain only variable names and safe example values. Real credentials belong in the local user environment or the application's secure-storage layer.

## Out of scope

Gökdoğan Intelligence is not designed for access-control bypassing, password cracking, private/closed-camera discovery, person-targeted surveillance or operational targeting. Requests for those capabilities are not considered supported use cases or security features.

Turkish security policy: [`SECURITY.md`](SECURITY.md)
