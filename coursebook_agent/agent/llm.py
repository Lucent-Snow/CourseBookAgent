"""Resilient OpenAI-compatible chat client."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from typing import Any

import httpx

from coursebook_agent.config import config

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    def __init__(self, message: str, code: str = "model_error", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class LLMClient:
    def __init__(self, max_retries: int = 3, timeout: float | None = None, transport=None):
        self.max_retries = max(1, max_retries)
        self.transport = transport
        self.timeout = timeout or config.llm.timeout

    async def complete(self, system: str, user: str, *, max_tokens: int = 5000, temperature: float = 0.2) -> str:
        if not (config.llm.base_url and config.llm.api_key and config.llm.model):
            raise LLMError("请先配置模型端点、模型名和 API Key", "configuration")
        url = config.llm.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": config.llm.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        headers = {"Authorization": f"Bearer {config.llm.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                    response = await asyncio.wait_for(client.post(url, json=payload, headers=headers), timeout=self.timeout)
                if response.status_code in {408, 409, 429} or response.status_code >= 500:
                    raise LLMError(f"模型服务暂时不可用（HTTP {response.status_code}）",
                                   "rate_limit" if response.status_code == 429 else "service", True)
                if response.is_error:
                    raise LLMError(f"模型请求失败（HTTP {response.status_code}）",
                                   "authentication" if response.status_code in {401, 403} else "request")
                body = response.json()
                content = _extract_message_text(body)
                if not content.strip():
                    raise LLMError("模型未返回最终内容", "empty_response", True)
                return content.strip()
            except (asyncio.TimeoutError, httpx.HTTPError, ValueError, TypeError, AttributeError, LLMError) as exc:
                if isinstance(exc, LLMError):
                    last_error = exc
                elif isinstance(exc, (asyncio.TimeoutError, httpx.TimeoutException)):
                    last_error = LLMError("模型请求超时", "timeout", True)
                elif isinstance(exc, httpx.HTTPError):
                    last_error = LLMError("模型网络连接失败", "network", True)
                else:
                    last_error = LLMError("模型响应格式无效", "response_format", True)
                logger.warning("LLM attempt %s/%s failed: %s", attempt, self.max_retries, last_error.code)
                if not last_error.retryable:
                    raise last_error from exc
                if attempt < self.max_retries:
                    await asyncio.sleep((2 ** (attempt - 1)) + random.random())
        raise last_error

    async def complete_json(self, system: str, user: str, *, max_tokens: int = 7000) -> dict[str, Any]:
        # Reasoning models spend many tokens on thinking; leave headroom for the final JSON.
        hardened_system = (
            system
            + "\n\n最终答案必须是一个完整 JSON 对象，放在回答正文中。"
            + "不要只思考，不要输出解释或 Markdown 代码块之外的文字。"
        )
        # Reserve budget for reasoning-heavy gateways.
        effective_max = max(max_tokens, 6000)
        raw = await self.complete(hardened_system, user, max_tokens=effective_max)
        try:
            return extract_json_object(raw)
        except (json.JSONDecodeError, ValueError) as first_error:
            logger.warning("Model returned invalid JSON; requesting repair: %s", first_error)
            # Second attempt: regenerate JSON from scratch with a tighter instruction, not only repair.
            regenerate_user = (
                "把下面内容整理成一个合法 JSON 对象。只输出 JSON。\n\n"
                f"原始任务：\n{user[:6000]}\n\n模型输出：\n{raw[:8000]}"
            )
            repair = await self.complete(
                "你是 JSON 生成器。只返回一个合法 JSON 对象，不解释、不使用 Markdown。不得编造任务外字段含义。",
                regenerate_user,
                max_tokens=max(effective_max, 8000),
                temperature=0,
            )
            try:
                return extract_json_object(repair)
            except (json.JSONDecodeError, ValueError) as exc:
                raise LLMError("模型连续返回无法解析的 JSON", "invalid_json") from exc


def _extract_message_text(body: dict[str, Any]) -> str:
    choice = (body.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {None, "text"}:
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        content = "".join(parts)
    if isinstance(content, str) and content.strip():
        return content
    # Reasoning-model fallbacks seen in some OpenAI-compatible gateways.
    for key in ("output_text",):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value
    # Sometimes providers put the answer under choice root.
    for key in ("text", "content"):
        value = choice.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    if not candidate.lstrip().startswith("{"):
        start, end = candidate.find("{"), candidate.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object found")
        candidate = candidate[start : end + 1]
    for attempt in _json_candidates(candidate):
        try:
            parsed = json.loads(attempt)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found")


def _json_candidates(candidate: str) -> list[str]:
    raw = candidate.strip()
    # Strip common trailing prose after the final closing brace.
    end = raw.rfind("}")
    if end > 0:
        raw = raw[: end + 1]
    cleaned = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing commas
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    return [raw, cleaned]
