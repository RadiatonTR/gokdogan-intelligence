from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class AdapterMetadata:
    id: str
    name: str
    category: str
    attribution: str = ""
    license: str = ""
    permissions: tuple[str, ...] = ("network:public-data",)
    default_enabled: bool = True
    active_collection: bool = False
    config_keys: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


class IntelligenceAdapter(ABC):
    metadata: AdapterMetadata

    @abstractmethod
    async def fetch(self, **kwargs: Any) -> Any:
        raise NotImplementedError

    def normalize(self, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [x for x in raw if isinstance(x, dict)]
        if isinstance(raw, dict):
            items = raw.get("items")
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
            return [raw]
        return []

    def validate_permissions(self) -> None:
        if self.metadata.active_collection:
            raise RuntimeError(f"active_adapter_requires_explicit_host_authorization:{self.metadata.id}")


class CallableAdapter(IntelligenceAdapter):
    """Wrap a known passive async fetch function in the adapter SDK."""

    def __init__(self, metadata: AdapterMetadata, fetcher: Callable[..., Awaitable[Any]]) -> None:
        self.metadata = metadata
        self._fetcher = fetcher

    async def fetch(self, **kwargs: Any) -> Any:
        return await self._fetcher(**kwargs)


@dataclass
class AdapterRegistry:
    _items: dict[str, IntelligenceAdapter] = field(default_factory=dict)

    def register(self, adapter: IntelligenceAdapter) -> None:
        adapter.validate_permissions()
        if not adapter.metadata.id or len(adapter.metadata.id) > 128:
            raise ValueError("invalid_adapter_id")
        self._items[adapter.metadata.id] = adapter

    def get(self, adapter_id: str) -> IntelligenceAdapter | None:
        return self._items.get(adapter_id)

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                "id": a.metadata.id,
                "name": a.metadata.name,
                "category": a.metadata.category,
                "attribution": a.metadata.attribution,
                "license": a.metadata.license,
                "permissions": list(a.metadata.permissions),
                "default_enabled": a.metadata.default_enabled,
                "active_collection": a.metadata.active_collection,
                "config_keys": list(a.metadata.config_keys),
                "tags": list(a.metadata.tags),
            }
            for a in sorted(self._items.values(), key=lambda x: (x.metadata.category, x.metadata.name.lower()))
        ]
