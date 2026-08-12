"""Source-level guard for the route dedupe performed by Desktop Edition.

The runtime guard in test_no_new_duplicate_routes remains authoritative. This
small static guard catches accidental reintroduction even in lightweight CI
jobs that do not import the full backend dependency graph.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "routers"


def _literal_routes(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            method = decorator.func.attr.upper()
            if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
                continue
            route_path = decorator.args[0].value
            if not isinstance(route_path, str):
                continue
            owner = decorator.func.value
            if not isinstance(owner, ast.Name) or owner.id not in {"app", "router"}:
                continue
            yield method, route_path, path.name, node.name


def test_literal_route_ownership_is_unique():
    files = [ROOT / "main.py", *sorted(ROUTERS.glob("*.py"))]
    by_route = defaultdict(list)
    for path in files:
        for method, route_path, filename, function in _literal_routes(path):
            by_route[(method, route_path)].append((filename, function))
    duplicates = {key: value for key, value in by_route.items() if len(value) > 1}
    assert duplicates == {}
