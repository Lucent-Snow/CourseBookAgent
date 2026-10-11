"""One bounded batch of model responses per durable step, with private Job-scoped replay."""
from __future__ import annotations
import asyncio
import hashlib
import json
from contextvars import ContextVar
from pathlib import Path

from coursebook_agent.config import config
from coursebook_agent.storage import atomic_write_text

execution_context: ContextVar[object | None] = ContextVar('durable_model_execution', default=None)


class StepPending(BaseException):
    """Stop replay at the next uncached call without triggering Agent fallbacks."""


class StepBudgetExceeded(BaseException):
    pass


class ModelReplay:
    def __init__(self, root: Path, concurrency: int = 1):
        self.root = root
        self.used = 0
        self.active = 0
        self.concurrency = max(1, concurrency)
        self.finished = asyncio.Event()
        self.finished.set()
        self.lock = asyncio.Lock()

    async def complete(self, client, system, user, temperature, invoke):
        payload = json.dumps([config.llm.base_url, config.llm.model, system, user, temperature], ensure_ascii=False)
        key = hashlib.sha256(payload.encode()).hexdigest()
        path = self.root / (key + '.json')
        async with self.lock:
            if path.exists():
                return json.loads(path.read_text())['content']
            allowed = self.used < self.concurrency and (self.used == 0 or self.active > 0)
            if allowed:
                self.used += 1
                self.active += 1
                self.finished.clear()
        if not allowed:
            # Finish all calls already accepted by the provider before pausing.
            await self.finished.wait()
            raise StepPending()
        try:
            try:
                result = await asyncio.wait_for(invoke(), timeout=235)
            except asyncio.TimeoutError:
                raise StepBudgetExceeded() from None
            atomic_write_text(path, json.dumps({'content': result}, ensure_ascii=False))
            return result
        finally:
            async with self.lock:
                self.active -= 1
                if self.active == 0:
                    self.finished.set()
