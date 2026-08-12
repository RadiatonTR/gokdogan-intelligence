from __future__ import annotations
import os, subprocess, sys, time

ATTEMPTS = 3
TRANSIENT = ("ENOTFOUND", "EAI_AGAIN", "getaddrinfo", "ECONNRESET", "ETIMEDOUT")

def main() -> int:
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        proc = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            text=True,
            capture_output=True,
            env=os.environ.copy(),
        )
        last = proc
        if proc.returncode == 0:
            if proc.stdout.strip():
                print(proc.stdout.rstrip())
            stderr = proc.stderr.strip()
            if stderr:
                if any(token in stderr for token in TRANSIENT):
                    print("Playwright browser mirror fallback recovered from a transient network/DNS failure.")
                else:
                    print(stderr, file=sys.stderr)
            return 0
        if attempt < ATTEMPTS:
            print(f"Playwright runtime install attempt {attempt}/{ATTEMPTS} failed; retrying with the existing download cache.", file=sys.stderr)
            time.sleep(min(10, 2 * attempt))
    assert last is not None
    if last.stdout.strip(): print(last.stdout.rstrip())
    if last.stderr.strip(): print(last.stderr.rstrip(), file=sys.stderr)
    return last.returncode or 1

if __name__ == "__main__":
    raise SystemExit(main())
