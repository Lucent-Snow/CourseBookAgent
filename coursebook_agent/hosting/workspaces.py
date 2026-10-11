"""Signed anonymous identity and context-local configuration/state."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import MutableMapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from coursebook_agent.config import AppConfig, LLMConfig, ZhiyunConfig, _base_config, _workspace_config

COOKIE = "coursebook_guest"
MAX_AGE = 90 * 86400
owner_context: ContextVar[str] = ContextVar("workspace_owner", default="")
request_workspace: ContextVar[object | None] = ContextVar("request_workspace", default=None)


def enabled() -> bool:
    return os.getenv("COURSEBOOK_CLOUD") == "1" or os.getenv("COURSEBOOK_GUEST_MODE") == "1"


def session_secret() -> bytes:
    value = os.getenv("COURSEBOOK_SESSION_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("游客模式必须配置至少 32 字符的 COURSEBOOK_SESSION_SECRET")
    return value.encode()


def issue_cookie() -> str:
    payload = f"{secrets.token_hex(24)}.{int(time.time())}"
    return payload + "." + hmac.new(session_secret(), payload.encode(), hashlib.sha256).hexdigest()


def verify_cookie(value: str | None) -> str | None:
    if not value or not re.fullmatch(r"[a-f0-9]{48}\.\d{10}\.[a-f0-9]{64}", value):
        return None
    owner, timestamp, signature = value.split(".")
    expected = hmac.new(session_secret(), f"{owner}.{timestamp}".encode(), hashlib.sha256).hexdigest()
    age = time.time() - int(timestamp)
    return owner if 0 <= age <= MAX_AGE and hmac.compare_digest(expected, signature) else None


@contextmanager
def workspace_scope(owner: str, root: Path):
    if not re.fullmatch(r"[a-f0-9]{48}", owner):
        raise ValueError("invalid workspace owner")
    current = _base_config.model_copy(deep=True)
    current.data_dir, current.output_dir = root, root / "output"
    # Do not expose the operator's credentials to public guests.
    current.llm = LLMConfig(api_key="", base_url="", model="")
    path = root / "llm-settings.json"
    if path.exists():
        current.llm = LLMConfig.model_validate_json(path.read_text())
    current.zhiyun = ZhiyunConfig(jwt="", session_file=root / "zhiyun/session.json")
    current.ensure_dirs()
    token = _workspace_config.set(current)
    identity = owner_context.set(owner)
    try:
        yield current
    finally:
        owner_context.reset(identity)
        _workspace_config.reset(token)


class ScopedMapping(MutableMapping):
    """Keep local background tasks separate; cloud requests never reuse job cache."""
    def __init__(self):
        self.entries = {}

    def _key(self, key):
        return owner_context.get(), key

    def __getitem__(self, key):
        return self.entries[self._key(key)]

    def __setitem__(self, key, value):
        self.entries[self._key(key)] = value

    def __delitem__(self, key):
        del self.entries[self._key(key)]

    def __iter__(self):
        owner = owner_context.get()
        return iter([key for identity, key in self.entries if identity == owner])

    def __len__(self):
        return sum(identity == owner_context.get() for identity, _ in self.entries)
