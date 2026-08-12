# GitHub Main Branch Ruleset / Ana Dal Koruma Kuralları

This document defines the recommended repository ruleset for the default `main` branch.

Bu belge varsayılan `main` dalı için önerilen repository ruleset yapılandırmasını tanımlar.

## Recommended ruleset / Önerilen ruleset

**Name / Ad:** `Protect main / Ana dal koruması`

**Target:** Branch

**Enforcement:** Active

**Target branch:** Default branch (`~DEFAULT_BRANCH`, currently `main`)

### Rules / Kurallar

- Restrict deletions / Dal silmeyi engelle
- Block force pushes / Force push engelle
- Require a pull request before merging / Birleştirmeden önce PR zorunlu
- Require status checks to pass / Durum kontrolleri zorunlu
- Require branches to be up to date before merging / PR dalı birleştirmeden önce güncel olmalı
- Require linear history / Doğrusal geçmiş zorunlu
- Require conversation resolution before merging / PR konuşmaları çözülmüş olmalı

### Required checks / Zorunlu kontroller

Use the exact GitHub Actions job names:

- `Frontend Tests & Build`
- `Backend Lint & Test`

Do not require the Windows release job on every PR because the Windows release workflow is a release/distribution gate rather than the normal PR CI gate.

### Pull request review policy / PR inceleme politikası

For the current single-maintainer phase:

- Required approving reviews: `0`
- Dismiss stale reviews on push: optional / not required while approval count is zero
- Require Code Owner review: disabled
- Require approval of the most recent reviewable push: disabled
- Require conversation resolution: enabled
- Allowed merge methods: Squash and Rebase

This keeps the audit trail and CI protections without locking the sole maintainer out of the repository. If more maintainers join later, raise required approvals to `1` and consider CODEOWNERS.

### Bypass / Atlatma

Recommended for the repository owner:

- Actor: `RadiatonTR`
- Mode: `For pull requests only`

This allows emergency administrative handling through a Pull Request while preserving a PR/audit trail. Avoid `Always allow` unless an emergency workflow truly requires direct pushes.

## Not enabled yet / Şimdilik etkinleştirilmemesi önerilenler

- **Require signed commits:** do not enable until the maintainer's normal Git/GitHub signing workflow is configured and verified; existing release history includes unsigned commits.
- **Merge queue:** unnecessary for the current repository size and maintainer model.
- **Required deployments:** no production deployment environment is currently part of normal PR merging.
- **Code scanning requirement:** enable only after a stable code-scanning workflow consistently reports on every PR.

## Import file / İçe aktarma dosyası

The repository contains a prepared ruleset definition at:

`.github/rulesets/main-protection.json`

If GitHub offers **Import a ruleset**, use that file and review the values before activating it.

## After activation / Etkinleştirme sonrası

1. Open a test branch.
2. Create a Pull Request targeting `main`.
3. Confirm `Frontend Tests & Build` and `Backend Lint & Test` are required.
4. Confirm direct force-push and branch deletion are blocked.
5. Merge only after required checks are green and conversations are resolved.
