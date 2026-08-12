#!/usr/bin/env bash
# scan-secrets.sh — Catch keys, secrets, and credentials before they hit git.
#
# Usage:
#   ./backend/scripts/scan-secrets.sh          # Scan staged files (pre-commit)
#   ./backend/scripts/scan-secrets.sh --all     # Scan entire working tree
#   ./backend/scripts/scan-secrets.sh --staged  # Scan staged files only (default)
#
# Exit code: 0 = clean, 1 = secrets found

set -euo pipefail

RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m'

MODE="${1:---staged}"
FOUND=0

# ── Get file list based on mode ─────────────────────────────────────────
if [[ "$MODE" == "--all" ]]; then
    FILELIST=$(mktemp)
    { git ls-files 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null; } > "$FILELIST"
    echo -e "${YELLOW}Scanning entire working tree...${NC}"
else
    FILELIST=$(mktemp)
    git diff --cached --name-only --diff-filter=ACMR 2>/dev/null > "$FILELIST" || true
    if [[ ! -s "$FILELIST" ]]; then
        echo -e "${GREEN}No staged files to scan.${NC}"
        rm -f "$FILELIST"
        exit 0
    fi
    echo -e "${YELLOW}Scanning $(wc -l < "$FILELIST" | tr -d ' ') staged files...${NC}"
fi

# ── Check 1: Dangerous file extensions ──────────────────────────────────
KEY_EXT='\.key$|\.pem$|\.p12$|\.pfx$|\.jks$|\.keystore$|\.p8$|\.der$'
SECRET_EXT='\.secret$|\.secrets$|\.credential$|\.credentials$'

HITS=$(grep -iE "$KEY_EXT|$SECRET_EXT" "$FILELIST" 2>/dev/null || true)
if [[ -n "$HITS" ]]; then
    echo -e "\n${RED}BLOCKED: Key/secret files detected:${NC}"
    echo "$HITS" | while read -r f; do echo -e "  ${RED}$f${NC}"; done
    FOUND=1
fi

# ── Check 2: Dangerous filenames ────────────────────────────────────────
RISKY='id_rsa|id_ed25519|id_ecdsa|private_key|private\.key|secret_key|master\.key'
RISKY+='|serviceaccount|gcloud.*\.json|firebase.*\.json|\.htpasswd'

HITS=$(grep -iE "$RISKY" "$FILELIST" 2>/dev/null || true)
if [[ -n "$HITS" ]]; then
    echo -e "\n${RED}BLOCKED: Risky filenames detected:${NC}"
    echo "$HITS" | while read -r f; do echo -e "  ${RED}$f${NC}"; done
    FOUND=1
fi

# ── Check 3: .env files (not .env.example) ──────────────────────────────
HITS=$(grep -E '(^|/)\.env(\.[^e].*)?$' "$FILELIST" 2>/dev/null | grep -v '\.example' || true)
if [[ -n "$HITS" ]]; then
    echo -e "\n${RED}BLOCKED: Environment files detected:${NC}"
    echo "$HITS" | while read -r f; do echo -e "  ${RED}$f${NC}"; done
    FOUND=1
fi

# ── Check 4: _domain_keys directory (project-specific) ──────────────────
HITS=$(grep '_domain_keys/' "$FILELIST" 2>/dev/null || true)
if [[ -n "$HITS" ]]; then
    echo -e "\n${RED}BLOCKED: Domain keys directory detected:${NC}"
    echo "$HITS" | while read -r f; do echo -e "  ${RED}$f${NC}"; done
    FOUND=1
fi

# ── Check 5: Content scan for embedded secrets (single grep pass) ───────
# Build one mega-pattern and run grep once across all files (fast!)
SECRET_REGEX='PRIVATE KEY-----|'
SECRET_REGEX+='ssh-rsa AAAA[0-9A-Za-z+/]|'
SECRET_REGEX+='ssh-ed25519 AAAA[0-9A-Za-z+/]|'
SECRET_REGEX+='ghp_[0-9a-zA-Z]{36}|'                          # GitHub PAT
SECRET_REGEX+='github_pat_[0-9a-zA-Z]{22}_[0-9a-zA-Z]{59}|'   # GitHub fine-grained
SECRET_REGEX+='gho_[0-9a-zA-Z]{36}|'                          # GitHub OAuth
SECRET_REGEX+='sk-[0-9a-zA-Z]{48}|'                           # OpenAI key
SECRET_REGEX+='sk-ant-[0-9a-zA-Z-]{90,}|'                     # Anthropic key
SECRET_REGEX+='AKIA[0-9A-Z]{16}|'                             # AWS access key
SECRET_REGEX+='AIzaSy[0-9A-Za-z_-]{33}|'                      # Google API key
SECRET_REGEX+='xox[bpoas]-[0-9a-zA-Z-]+|'                     # Slack token
SECRET_REGEX+='npm_[0-9a-zA-Z]{36}|'                          # npm token
SECRET_REGEX+='pypi-[0-9a-zA-Z-]{50,}'                        # PyPI token

# Filter to text-like files only (skip binaries by extension + skip this script)
TEXT_FILES=$(grep -ivE '\.(png|jpg|jpeg|gif|ico|svg|woff2?|ttf|eot|pbf|zip|tar|gz|db|sqlite|xlsx|pdf|mp[34]|wav|ogg|webm|webp|avif)$' "$FILELIST" | grep -v 'scan-secrets\.sh$' || true)

if [[ -n "$TEXT_FILES" ]]; then
    # Known-public exclusions: lines matching `<host-or-ip> ssh-<algo> <key>`
    # are SSH known_hosts entries — the host's PUBLIC fingerprint, which is
    # by definition safe to commit (the whole point of pinning known_hosts
    # is to publish the fingerprint widely so MITM is detectable). Filter
    # these out before flagging the file.
    KNOWN_HOSTS_LINE='^[[:space:]]*[a-zA-Z0-9._:,*-]+([[:space:]]+[a-zA-Z0-9._:,*-]+)?[[:space:]]+(ssh-rsa|ssh-ed25519|ssh-dss|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521)[[:space:]]+AAAA'

    # Use grep with file list, skip missing/binary, limit output
    CONTENT_HITS=$(echo "$TEXT_FILES" | xargs grep -lE "$SECRET_REGEX" 2>/dev/null || true)
    if [[ -n "$CONTENT_HITS" ]]; then
        REAL_HITS=""
        REAL_REPORT=""
        while IFS= read -r f; do
            [[ -z "$f" ]] && continue
            # Re-grep this file, but filter out known_hosts-style lines.
            FILE_HITS=$(grep -nE "$SECRET_REGEX" "$f" 2>/dev/null | grep -vE "$KNOWN_HOSTS_LINE" || true)
            if [[ -n "$FILE_HITS" ]]; then
                REAL_HITS+="$f"$'\n'
                REAL_REPORT+="  ${RED}$f${NC}"$'\n'
                # Show first 2 matching lines for context
                while IFS= read -r line; do
                    [[ -z "$line" ]] && continue
                    REAL_REPORT+="    ${YELLOW}$line${NC}"$'\n'
                done < <(echo "$FILE_HITS" | head -2)
            fi
        done <<< "$CONTENT_HITS"
        if [[ -n "$REAL_HITS" ]]; then
            echo -e "\n${RED}BLOCKED: Embedded secrets/tokens found in:${NC}"
            echo -en "$REAL_REPORT"
            FOUND=1
        fi
    fi
fi

rm -f "$FILELIST"

# ── Result ──────────────────────────────────────────────────────────────
echo ""
if [[ $FOUND -eq 1 ]]; then
    echo -e "${RED}Secret scan FAILED. Add these to .gitignore or remove them before committing.${NC}"
    echo -e "${YELLOW}If intentional (e.g. test fixtures): git commit --no-verify${NC}"
    exit 1
else
    echo -e "${GREEN}Secret scan passed. No keys or secrets detected.${NC}"
    exit 0
fi
