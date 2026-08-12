#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    i18n = (ROOT / "frontend/src/i18n/index.tsx").read_text(encoding="utf-8-sig")
    panel = (ROOT / "frontend/src/components/PublicIntelPanel.tsx").read_text(encoding="utf-8-sig")
    bridge = (ROOT / "frontend/src/components/TurkishUiBridge.tsx").read_text(encoding="utf-8-sig")
    locale_block = i18n.split("export const LOCALES", 1)[1].split("const translations", 1)[0]
    if "code: 'tr'" not in locale_block or re.search(r"code:\s*'(?:en|fr|fa|zh-CN)'", locale_block):
        errors.append("UI dil seçimi yalnız Türkçe olmalı")
    for phrase in ["KÜRESEL HABER", "YEREL HABER", "DİPLOMASİ", "KAMERALAR", "KAYNAK SAĞLIĞI"]:
        if phrase not in panel:
            errors.append(f"Canlı operasyon merkezi etiketi eksik: {phrase}")
    for source_phrase in ["Unknown Region", "Save failed", "Request failed", "Loading..."]:
        if source_phrase not in bridge:
            errors.append(f"Legacy Türkçe köprü çevirisi eksik: {source_phrase}")
    if errors:
        print("Türkçe release profili BAŞARISIZ")
        for error in errors:
            print(f" - {error}")
        return 1
    print("Türkçe release profili OK")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
