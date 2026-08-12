#!/usr/bin/env python3
"""Fail a release when likely production credentials are committed to source.

This is intentionally narrow: it ignores tests/fixtures/lockfiles and looks for
private-key PEM blocks, well-known token prefixes, and long literal values bound
to credential-shaped names. It is a release guard, not a replacement for an
enterprise secret-scanning service.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".py", ".js", ".cjs", ".mjs", ".ts", ".tsx", ".rs", ".toml", ".yml", ".yaml", ".ps1", ".sh", ".bat", ".env"}
EXCLUDED_PARTS = {
    "node_modules", ".next", "out", "target", "dist", "build", "build-reports",
    ".desktop-python", ".desktop-browsers", ".desktop-export-build", ".venv", "venv",
    "backend-runtime", "python-runtime", "companion-www", "site-packages",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".git", "tests", "__tests__", "fixtures",
}
EXCLUDED_NAMES = {"package-lock.json", "uv.lock", "Cargo.lock", ".env.example", "check_source_secrets.py", "scan-secrets.sh"}

PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
KNOWN_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|AKIA[0-9A-Z]{16})(?![A-Za-z0-9_-])")
CREDENTIAL_LITERAL = re.compile(
    r"(?im)^\s*[A-Za-z0-9_.-]*(?:api[_-]?key|secret|token|password|passwd|private[_-]?key)[A-Za-z0-9_.-]*"
    r"\s*(?:=|:)\s*[\"\']([^\"\'\n]{20,})[\"\']\s*(?:#.*)?$"
)
DOCKER_DEFAULT = re.compile(
    r"(?i)\$\{[^}:]*(?:secret|token|password|api[_-]?key)[^}:]*:-([^}\n]{20,})\}"
)
PLACEHOLDER_WORDS = {"changeme", "example", "placeholder", "your_", "replace_", "configured", "<", "${", "$", "process.env", "os.getenv", "env("}


def likely_placeholder(value: str) -> bool:
    folded = value.strip().casefold()
    if folded.startswith(("http://", "https://", "file://")):
        return True
    return any(word in folded for word in PLACEHOLDER_WORDS)


def is_generated_or_nonproduction(path: Path) -> bool:
    return any(part.casefold() in EXCLUDED_PARTS for part in path.parts)


def main() -> int:
    findings: list[str] = []
    scanned = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name in EXCLUDED_NAMES:
            continue
        if is_generated_or_nonproduction(path):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS and path.name not in {"Dockerfile", "docker-compose.yml", "docker-compose.override.yml", "docker-compose.participant.yml"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        rel = path.relative_to(ROOT)
        if PRIVATE_KEY.search(text):
            findings.append(f"private_key_pem:{rel}")
        for match in KNOWN_TOKEN.finditer(text):
            findings.append(f"known_token_prefix:{rel}:{match.start()}")
        for regex, kind in ((CREDENTIAL_LITERAL, "credential_literal"), (DOCKER_DEFAULT, "credential_default")):
            for match in regex.finditer(text):
                value = match.group(1).strip()
                if likely_placeholder(value):
                    continue
                findings.append(f"{kind}:{rel}:{match.start()}")
    if findings:
        print("Source secret scan FAILED")
        for finding in findings[:100]:
            print(" -", finding)
        return 1
    print(f"Source secret scan OK — {scanned} production text files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
