from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .storage import IntelligenceStore

COUNTRY_ALIASES = {
    "us": "United States", "usa": "United States", "u.s.": "United States", "united states of america": "United States",
    "uk": "United Kingdom", "u.k.": "United Kingdom", "great britain": "United Kingdom",
    "turkiye": "Türkiye", "turkey": "Türkiye", "republic of türkiye": "Türkiye",
    "russia": "Russian Federation", "russian federation": "Russian Federation",
}


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\-. ]+", " ", value.casefold(), flags=re.UNICODE)).strip()


class EntityResolver:
    def __init__(self, store: IntelligenceStore) -> None:
        self.store = store

    def resolve(self, entity_type: str, value: str, candidates: list[str] | None = None, identifiers: dict[str, str] | None = None) -> dict[str, Any]:
        normalized = normalize_text(value)
        exact_identifier = self.store.resolve_identifier(entity_type, identifiers or {})
        if exact_identifier:
            return {"input": value, "canonical": exact_identifier["canonical_value"], "confidence": exact_identifier["confidence"], "method": "exact_identifier", "matched_identifier": exact_identifier["identifier_type"]}
        stored = self.store.resolve_alias(entity_type, normalized)
        if stored:
            return {"input": value, "canonical": stored["canonical_value"], "confidence": stored["confidence"], "method": "alias_store"}
        if entity_type.casefold() in {"country", "country_code"} and normalized in COUNTRY_ALIASES:
            canonical = COUNTRY_ALIASES[normalized]
            self.store.upsert_alias(entity_type, value, canonical, 1.0, "builtin")
            for key, identifier in (identifiers or {}).items(): self.store.upsert_identifier(entity_type, key, identifier, canonical, 1.0, "builtin")
            return {"input": value, "canonical": canonical, "confidence": 1.0, "method": "builtin_country_alias"}
        best: tuple[str, float] | None = None
        for candidate in candidates or []:
            ratio = SequenceMatcher(None, normalized, normalize_text(candidate)).ratio()
            if best is None or ratio > best[1]:
                best = (candidate, ratio)
        if best and best[1] >= 0.92:
            self.store.upsert_alias(entity_type, value, best[0], best[1], "fuzzy")
            for key, identifier in (identifiers or {}).items(): self.store.upsert_identifier(entity_type, key, identifier, best[0], best[1], "fuzzy")
            return {"input": value, "canonical": best[0], "confidence": round(best[1], 4), "method": "fuzzy"}
        return {"input": value, "canonical": value.strip(), "confidence": 0.5, "method": "unresolved"}
