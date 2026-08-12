from __future__ import annotations

import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class Job:
    id: str
    kind: str
    state: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "state": self.state,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "result": self.result,
            "error": self.error,
        }


class IntelligenceTaskQueue:
    def __init__(self, max_concurrency: int = 4, history: int = 200) -> None:
        self.max_concurrency = max(1, min(max_concurrency, 32))
        self._sem = asyncio.Semaphore(self.max_concurrency)
        self._jobs: dict[str, Job] = {}
        self._order: deque[str] = deque(maxlen=max(20, history))
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    def submit(
        self, kind: str, factory: Callable[[], Awaitable[Any]]
    ) -> dict[str, Any]:
        job = Job(id=f"job-{uuid.uuid4()}", kind=kind[:120])
        if self._order.maxlen and len(self._order) >= self._order.maxlen:
            evicted = self._order[0]
            if evicted not in self._tasks:
                self._jobs.pop(evicted, None)
        self._jobs[job.id] = job
        self._order.append(job.id)

        async def runner() -> None:
            async with self._sem:
                job.state = "running"
                job.started_at = time.time()
                try:
                    job.result = await factory()
                    job.state = "succeeded"
                except asyncio.CancelledError:
                    job.state = "cancelled"
                    raise
                except Exception as exc:
                    job.state = "failed"
                    job.error = f"{type(exc).__name__}:{str(exc)[:500]}"
                finally:
                    job.finished_at = time.time()
                    self._tasks.pop(job.id, None)

        self._tasks[job.id] = asyncio.create_task(
            runner(), name=f"intel:{kind}:{job.id}"
        )
        return job.to_dict()

    def get(self, job_id: str) -> dict[str, Any] | None:
        job = self._jobs.get(job_id)
        return job.to_dict() if job else None

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        ids = list(self._order)[-max(1, min(limit, 200)) :]
        return [self._jobs[x].to_dict() for x in reversed(ids) if x in self._jobs]

    def cancel(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        if not task:
            return False
        task.cancel()
        return True

    def set_max_concurrency(self, value: int) -> int:
        """Apply a new concurrency limit to jobs submitted after this call.

        Jobs already holding the previous semaphore are allowed to finish; replacing
        the semaphore avoids cancelling analyst work merely because a profile changed.
        """
        next_value = max(1, min(int(value), 32))
        if next_value != self.max_concurrency:
            self.max_concurrency = next_value
            self._sem = asyncio.Semaphore(next_value)
        return self.max_concurrency

    def status(self) -> dict[str, Any]:
        return {
            "max_concurrency": self.max_concurrency,
            "running": sum(1 for x in self._jobs.values() if x.state == "running"),
            "queued": sum(1 for x in self._jobs.values() if x.state == "queued"),
            "history": len(self._jobs),
        }
