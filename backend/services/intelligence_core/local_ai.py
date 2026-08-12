from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

import httpx


class LocalAIService:
    """Local-only analyst helper.

    Uses Ollama when it is already running on 127.0.0.1. No cloud provider is
    contacted. Deterministic extractive summarization and local hashed-vector
    embeddings remain available without any model runtime.
    """

    base_url = "http://127.0.0.1:11434"
    HASHED_EMBED_MODEL = "shadowbroker-hash-embed-v1"
    HASHED_DIMENSIONS = 256
    MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9._-]+)?$")

    @classmethod
    def validate_model_name(cls, model: str) -> str:
        value = str(model or "").strip()
        if not value or len(value) > 200 or not cls.MODEL_NAME_RE.fullmatch(value):
            raise ValueError("invalid_local_model_name")
        # Model management is deliberately name-based only; URLs, query
        # strings, credentials and arbitrary local paths are not accepted.
        if "://" in value or ".." in value.split("/"):
            raise ValueError("invalid_local_model_name")
        return value

    async def status(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()
                data = response.json()
                try:
                    running_response = await client.get(f"{self.base_url}/api/ps")
                    running_response.raise_for_status()
                    running_data = running_response.json()
                except Exception:
                    running_data = {"models": []}
            details = []
            models = []
            for item in data.get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                if not name:
                    continue
                models.append(name)
                details.append({
                    "name": name,
                    "size": int(item.get("size") or 0),
                    "modified_at": item.get("modified_at"),
                    "digest": str(item.get("digest") or "")[:128],
                    "details": item.get("details") or {},
                })
            running = []
            total_vram = 0
            for item in running_data.get("models") or []:
                name = str(item.get("name") or item.get("model") or "").strip()
                size_vram = int(item.get("size_vram") or 0)
                total_vram += max(0, size_vram)
                running.append({
                    "name": name,
                    "size": int(item.get("size") or 0),
                    "size_vram": size_vram,
                    "context_length": int(item.get("context_length") or 0),
                    "expires_at": item.get("expires_at"),
                })
            return {
                "available": True,
                "provider": "ollama-local",
                "models": models,
                "model_details": details,
                "running": running,
                "running_vram_bytes": total_vram,
                "fallback_embedding_model": self.HASHED_EMBED_MODEL,
            }
        except Exception:
            return {
                "available": False,
                "provider": "heuristic-local",
                "models": [],
                "model_details": [],
                "running": [],
                "running_vram_bytes": 0,
                "fallback_embedding_model": self.HASHED_EMBED_MODEL,
            }

    async def pull_model(self, model: str) -> dict[str, Any]:
        name = self.validate_model_name(model)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=3.0)) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"model": name, "stream": False, "insecure": False},
                )
                response.raise_for_status()
                payload = response.json() if response.content else {}
            return {"ok": True, "provider": "ollama-local", "model": name, "status": payload.get("status") or "success"}
        except httpx.HTTPError as exc:
            raise RuntimeError(f"ollama_pull_failed:{type(exc).__name__}") from exc

    async def delete_model(self, model: str) -> dict[str, Any]:
        name = self.validate_model_name(model)
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0)) as client:
                response = await client.request("DELETE", f"{self.base_url}/api/delete", json={"model": name})
                response.raise_for_status()
            return {"ok": True, "provider": "ollama-local", "model": name, "status": "deleted"}
        except httpx.HTTPError as exc:
            raise RuntimeError(f"ollama_delete_failed:{type(exc).__name__}") from exc

    @staticmethod
    def extractive_summary(text: str, max_sentences: int = 5) -> str:
        clean = re.sub(r"\s+", " ", text or " ").strip()
        if not clean:
            return ""
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", clean) if x.strip()]
        if len(sentences) <= max_sentences:
            return " ".join(sentences)
        words = [w.casefold() for w in re.findall(r"[\w'-]{3,}", clean, flags=re.UNICODE)]
        freq = Counter(words)
        common = {
            "the", "and", "for", "with", "this", "that", "from", "were", "have", "has", "are", "was", "but", "not", "you",
            "bir", "ve", "ile", "bu", "şu", "için", "olan",
        }
        for key in list(freq):
            if key in common:
                freq.pop(key, None)
        scored = []
        for idx, sentence in enumerate(sentences):
            toks = [w.casefold() for w in re.findall(r"[\w'-]{3,}", sentence, flags=re.UNICODE)]
            score = sum(freq.get(w, 0) for w in toks) / max(1, len(toks))
            scored.append((score, idx, sentence))
        chosen = sorted(sorted(scored, reverse=True)[:max_sentences], key=lambda x: x[1])
        return " ".join(x[2] for x in chosen)

    async def summarize(self, text: str, model: str | None = None, max_sentences: int = 5) -> dict[str, Any]:
        text = text[:100_000]
        if model:
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": model,
                            "prompt": "Summarize the following intelligence material. Separate observed facts from assessment. Do not invent facts.\n\n" + text,
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                return {"provider": "ollama-local", "model": model, "summary": str(data.get("response") or "").strip()}
            except Exception:
                pass
        return {"provider": "heuristic-local", "model": None, "summary": self.extractive_summary(text, max_sentences)}

    @classmethod
    def hashed_embedding(cls, text: str, dimensions: int | None = None) -> list[float]:
        """Deterministic, local lexical embedding used when no model is available.

        This is deliberately labelled as a hashed lexical vector rather than an
        AI semantic embedding. It gives private/offline similarity search without
        pretending to provide model-level semantic understanding.
        """
        dims = max(32, min(int(dimensions or cls.HASHED_DIMENSIONS), 2048))
        vec = [0.0] * dims
        tokens = [x.casefold() for x in re.findall(r"[\w'-]{2,}", text or "", flags=re.UNICODE)]
        if not tokens:
            return vec
        counts = Counter(tokens)
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "little") % dims
            sign = -1.0 if digest[8] & 1 else 1.0
            vec[index] += sign * (1.0 + math.log1p(count))
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [round(x / norm, 8) for x in vec]

    async def embed(self, text: str, model: str | None = None) -> dict[str, Any]:
        clean = (text or "")[:100_000]
        if model:
            # Ollama supports a local embed endpoint in current releases; a
            # compatibility fallback handles older local servers.
            try:
                async with httpx.AsyncClient(timeout=90.0) as client:
                    response = await client.post(f"{self.base_url}/api/embed", json={"model": model, "input": clean})
                    if response.status_code < 400:
                        data = response.json()
                        embeddings = data.get("embeddings") or []
                        vector = embeddings[0] if embeddings and isinstance(embeddings[0], list) else None
                        if vector:
                            return {"provider": "ollama-local", "model": model, "vector": [float(x) for x in vector]}
                    response = await client.post(f"{self.base_url}/api/embeddings", json={"model": model, "prompt": clean})
                    response.raise_for_status()
                    data = response.json()
                    vector = data.get("embedding")
                    if isinstance(vector, list) and vector:
                        return {"provider": "ollama-local", "model": model, "vector": [float(x) for x in vector]}
            except Exception:
                pass
        return {
            "provider": "deterministic-local",
            "model": self.HASHED_EMBED_MODEL,
            "vector": self.hashed_embedding(clean),
        }

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na <= 0 or nb <= 0:
            return 0.0
        return max(-1.0, min(1.0, dot / (na * nb)))
