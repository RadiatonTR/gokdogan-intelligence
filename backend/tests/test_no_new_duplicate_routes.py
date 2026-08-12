"""Issue #239 (tg12): backend registers duplicate API routes in both
``main.py`` and router modules, so request behavior depends on the
order ``FastAPI`` happened to register them.

This test is the **CI guard** that locks in the invariant going forward.
It does NOT delete any existing duplicates — those are tolerated via an
explicit baseline file. What it DOES block is *new* duplicates appearing
later, which is what the audit was actually asking for: a way to stop
the drift before it gets worse.

Findings (empirically verified, see PR #286 description):

- ``main.app`` calls ``include_router(...)`` for every router at module
  import time around line 3316.
- Every ``@app.get/post/put/...`` decorator inside ``main.py`` runs
  *after* those include_router calls, so the router handler is the one
  that actually serves requests. The duplicates in ``main.py`` are
  dead code at the route-resolution layer.
- Behavior today is deterministic (router wins), but if someone later
  adds a NEW route only in ``main.py``, or edits one copy of an
  existing pair without the other, drift starts.

How this test works:

- Walks ``main.app.routes`` and records every ``(method, path)`` that
  appears more than once, along with which modules registered each
  copy.
- Compares that set against the baseline in
  ``backend/tests/data/duplicate_routes_baseline.json``.
- **Fails** if any duplicate appears that is NOT in the baseline
  (or if the registering modules for an existing duplicate change).
- **Stays green** when duplicates are *removed* by genuinely deduping
  the code. (The baseline is a ceiling, not a floor.)

To extend in the future:

- If you actually dedupe a route, leave the baseline alone — the test
  still passes. Subsequent regenerations of the baseline (``python -m
  scripts.regen_duplicate_routes_baseline`` or the snippet in this
  test's docstring) will shrink it.
- If you legitimately need a new duplicate (you probably do not), add
  it to the baseline AND explain why in the PR description so reviewers
  can push back.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pytest


BASELINE_PATH = (
    Path(__file__).parent / "data" / "duplicate_routes_baseline.json"
)


def _current_duplicates() -> dict[str, list[str]]:
    """Walk ``main.app.routes`` and return ``{'METHOD /path': [module, ...]}``
    for every (method, path) registered more than once."""
    import main

    by_key: dict[str, list[str]] = defaultdict(list)
    for route in main.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods or endpoint is None:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            by_key[f"{method} {path}"].append(endpoint.__module__)

    return {
        key: sorted(modules) for key, modules in by_key.items() if len(modules) > 1
    }


def _load_baseline() -> dict[str, list[str]]:
    if not BASELINE_PATH.exists():
        return {}
    raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    dups = raw.get("duplicates", {})
    if not isinstance(dups, dict):
        return {}
    return {k: sorted(v) for k, v in dups.items()}


def test_no_new_duplicate_route_registrations():
    """Block any (method, path) duplicate not already in the baseline.

    This is the primary CI guard: PRs that add a NEW shadowed
    ``@app.get`` while a router module already serves the same route
    fail here with an actionable message.
    """
    current = _current_duplicates()
    baseline = _load_baseline()

    new_or_changed = []
    for key, modules in sorted(current.items()):
        if key not in baseline:
            new_or_changed.append(
                f"  + {key}  (NEW duplicate; registered in: {modules})"
            )
            continue
        if modules != baseline[key]:
            new_or_changed.append(
                f"  ~ {key}  "
                f"(modules changed: was {baseline[key]}, now {modules})"
            )

    if new_or_changed:
        pytest.fail(
            "Issue #239 CI guard: detected duplicate route registrations "
            "that are NOT in the tolerated baseline.\n"
            "\n"
            "If you added a new @app.get/post/... in main.py for a path "
            "that a router module already serves, please move the handler "
            "into the router and delete the main.py copy — the router "
            "version wins on request routing anyway, so the main.py copy "
            "is dead code that just creates drift risk.\n"
            "\n"
            "Offending entries:\n"
            + "\n".join(new_or_changed)
            + "\n\n"
            "Baseline lives at "
            f"{BASELINE_PATH.relative_to(BASELINE_PATH.parent.parent.parent)}."
        )


def test_baseline_only_lists_real_duplicates():
    """Catch baseline drift in the other direction: if an entry in the
    baseline is no longer actually a duplicate (because someone deduped
    it manually), the baseline is stale and should be shrunk so future
    re-introductions of that duplicate get caught.

    This test is informational — it does NOT fail the build today (the
    audit's main concern is *new* duplicates, not stale baseline
    entries). It prints a warning so the next baseline regeneration
    can clean things up.
    """
    current = _current_duplicates()
    baseline = _load_baseline()
    stale = sorted(k for k in baseline if k not in current)
    if stale:
        # Use warnings instead of fail so this is friendly housekeeping,
        # not a CI blocker. The other test catches the actual safety
        # concern.
        import warnings

        warnings.warn(
            f"duplicate_routes_baseline.json contains {len(stale)} entry/entries "
            "no longer present in app.routes — consider regenerating the baseline. "
            f"Stale: {stale[:5]}{'...' if len(stale) > 5 else ''}",
            stacklevel=2,
        )


def test_router_handler_is_the_one_that_serves():
    """Pin the empirical claim from PR #286: for every duplicated
    (method, path), the FIRST-registered handler is in a router
    module, not in main.py. If this ever flips — e.g. someone moves
    include_router calls to the bottom of main.py — duplicate routes
    start silently changing which handler runs. This catches that
    rearrangement immediately.
    """
    import main

    first_seen: dict[str, str] = {}
    for route in main.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods or endpoint is None:
            continue
        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            key = f"{method} {path}"
            if key not in first_seen:
                first_seen[key] = endpoint.__module__

    main_winning = sorted(
        k for k, mod in first_seen.items() if mod == "main"
    )
    # The duplicates we tolerate are router-first. If main is the first
    # registered for any duplicated path, the router copy gets shadowed
    # instead, which would invalidate every assumption made in audit
    # rounds 5 and 6 about "the router version is canonical."
    baseline = _load_baseline()
    main_first_in_baseline = [k for k in main_winning if k in baseline]
    if main_first_in_baseline:
        pytest.fail(
            "Issue #239 invariant broken: for at least one duplicated "
            "(method, path), main.py is now registered FIRST and is "
            "serving requests instead of the router copy. Audit rounds "
            "5 and 6 assumed the router handler wins.\n"
            "\n"
            "Affected entries:\n"
            + "\n".join(f"  {k}" for k in main_first_in_baseline)
            + "\n\n"
            "Most likely cause: someone moved app.include_router(...) "
            "calls in main.py to after the @app.get decorators. Move "
            "them back to before the @app routes (currently around "
            "line 3316)."
        )
