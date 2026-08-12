#!/usr/bin/env python3
"""Prevent legacy monoliths from growing while R8 moves new work into modules."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BUDGETS={
 'backend/main.py':465_000,
 'frontend/src/components/MaplibreViewer.tsx':273_000,
 'frontend/src/components/MeshTerminal.tsx':255_000,
 'backend/routers/ai_intel.py':190_000,
}
failed=[]
for rel,limit in BUDGETS.items():
 p=ROOT/rel
 if not p.exists(): failed.append(f'missing:{rel}'); continue
 size=p.stat().st_size
 print(f'{rel}: {size}/{limit} bytes')
 if size>limit: failed.append(f'architecture_budget_exceeded:{rel}:{size}>{limit}')
if failed:
 print('Architecture budget FAILED')
 for x in failed: print(' -',x)
 raise SystemExit(1)
print('Architecture budget OK — new features must stay modular.')
