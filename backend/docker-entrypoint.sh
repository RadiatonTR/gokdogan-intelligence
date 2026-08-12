#!/bin/sh
set -eu

# Docker named volumes hide files that were baked into /app/data at image build
# time. Seed safe, static data into a fresh volume so first-run Docker installs
# behave like source installs without bundling local runtime secrets.
if [ -d /app/image-data ]; then
  mkdir -p /app/data
  find /app/image-data -mindepth 1 -maxdepth 1 -type f | while IFS= read -r src; do
    dest="/app/data/$(basename "$src")"
    if [ ! -e "$dest" ]; then
      cp "$src" "$dest" || true
    fi
  done
fi

if [ -z "${PRIVACY_CORE_ALLOWED_SHA256:-}" ] && [ -f /app/libprivacy_core.so ]; then
  PRIVACY_CORE_ALLOWED_SHA256="$(sha256sum /app/libprivacy_core.so | awk '{print $1}')"
  export PRIVACY_CORE_ALLOWED_SHA256
fi

exec "$@"
