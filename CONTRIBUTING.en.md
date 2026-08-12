# Contributing to Gökdoğan Intelligence

Thank you for your interest in contributing to Gökdoğan Intelligence.

The project brings public or properly authorized OSINT/data sources into a map-based Windows desktop workspace. Contributions should be safe, maintainable, testable and compatible with the project's responsible-use boundaries.

## Before you start

1. Check existing Issues and Pull Requests.
2. For large changes, open a feature request or design discussion first.
3. Do not disclose security vulnerabilities in a public Issue; follow `SECURITY.en.md`.
4. Never commit API keys, tokens, passwords, private keys, personal data or runtime databases.

## Development principles

- New user-facing text should be localization-ready. Turkish remains the default desktop language, and English text should be supplied for global-facing UI where the relevant component supports localization.
- Use public or properly authorized data sources.
- Do not add access-control bypassing, password cracking, closed-camera discovery, person-targeted surveillance or operational targeting capabilities.
- Document license, attribution, quota and API-key requirements for new providers.
- Provider outages should degrade gracefully through health, fallback or cache behavior instead of crashing the application.
- Secrets must never appear in plain text in logs, errors or API responses.

## Local development

On Windows, the root-level `START-HERE.bat` can be used for source builds. The release flow validates dependencies, release gates, tests, Rust/Tauri compilation and Windows packaging.

Main components:

- Frontend: TypeScript / Next.js / MapLibre
- Backend: Python / FastAPI
- Desktop: Rust / Tauri / WebView2

## Before submitting a change

When applicable:

- run relevant backend tests,
- run frontend lint/typecheck/tests,
- run Rust/Tauri tests,
- validate new JSON/YAML configuration,
- update `DATA-ATTRIBUTION.md` and provider documentation when adding a data source,
- add or update English/Turkish documentation for user-visible behavior.

## Commit messages

Short, descriptive messages are preferred, for example:

- `fix: improve AIS reconnect behavior`
- `feat: add public disaster data source`
- `docs: update API setup notes`
- `test: extend Windows runtime regression coverage`

## Pull Requests

A Pull Request should explain:

- what changed,
- why the change is needed,
- how it was tested,
- screenshots for UI changes,
- license/attribution/API requirements for new external data sources.

By submitting a PR, you agree to follow the project Code of Conduct, responsible-use boundaries and license terms.

Turkish contributor guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
