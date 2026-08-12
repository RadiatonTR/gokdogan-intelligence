from __future__ import annotations

import importlib
import pathlib
import sys

MODULES = (
    "fastapi",
    "uvicorn",
    "playwright",
    "cryptography",
    "numpy",
    "orjson",
)

runtime_root = pathlib.Path(sys.executable).resolve().parent
failures: list[str] = []

if sys.version_info[:2] != (3, 12):
    failures.append(f"runtime Python must be 3.12.x, got {sys.version.split()[0]}")

for name in MODULES:
    try:
        module = importlib.import_module(name)
    except Exception as exc:  # validation should report every failing import
        failures.append(f"{name}: import failed: {exc!r}")
        continue

    module_file = getattr(module, "__file__", None)
    if module_file:
        resolved = pathlib.Path(module_file).resolve()
        try:
            resolved.relative_to(runtime_root)
        except ValueError:
            failures.append(
                f"{name}: imported outside portable runtime: {resolved}"
            )

if failures:
    print("Portable Python runtime validation FAILED", file=sys.stderr)
    for failure in failures:
        print(f" - {failure}", file=sys.stderr)
    raise SystemExit(1)

print(f"Portable Python runtime OK: {sys.executable}")
print(f"Python: {sys.version.split()[0]}")
print("Imports: " + ", ".join(MODULES))
