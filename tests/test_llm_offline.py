"""Model transport tests without real HTTP requests."""
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from coursebook_agent.agent.llm import LLMClient, LLMError
from coursebook_agent.config import config


class ModelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        for key, value in [("api_key", "offline-dummy"), ("base_url", "https://offline.invalid/v1"), ("model", "fake")]:
            p = patch.object(config.llm, key, value)
            p.start()
            self.addCleanup(p.stop)

    async def test_401_does_not_retry_or_expose_response_body(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(401, text="secret-provider-body")
        with self.assertRaises(LLMError) as ctx:
            await LLMClient(transport=httpx.MockTransport(handler)).complete("s", "u")
        self.assertEqual(len(calls), 1)
        self.assertEqual(ctx.exception.code, "authentication")
        self.assertNotIn("secret", str(ctx.exception))

    async def test_transient_failure_retries_then_succeeds(self):
        for status in (429, 503):
            calls = []
            def handler(request):
                calls.append(request)
                if len(calls) == 1:
                    return httpx.Response(status)
                return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})
            with patch("coursebook_agent.agent.llm.asyncio.sleep", AsyncMock()):
                result = await LLMClient(transport=httpx.MockTransport(handler)).complete("s", "u")
            self.assertEqual(result, "OK")
            self.assertEqual(len(calls), 2)

    async def test_timeout_has_bounded_attempts(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("sensitive url", request=request)
        with patch("coursebook_agent.agent.llm.asyncio.sleep", AsyncMock()):
            with self.assertRaises(LLMError) as ctx:
                await LLMClient(max_retries=2, transport=httpx.MockTransport(handler)).complete("s", "u")
        self.assertEqual(len(calls), 2)
        self.assertEqual(ctx.exception.code, "timeout")

    async def test_invalid_json_repairs_once(self):
        client = LLMClient()
        with patch.object(client, "complete", AsyncMock(side_effect=["bad", '{"ok":true}'])) as complete:
            self.assertEqual(await client.complete_json("s", "u"), {"ok": True})
            self.assertEqual(complete.await_count, 2)
        with patch.object(client, "complete", AsyncMock(return_value="bad")):
            with self.assertRaises(LLMError) as ctx:
                await client.complete_json("s", "u")
            self.assertEqual(ctx.exception.code, "invalid_json")

    async def test_reasoning_only_is_not_a_final_answer(self):
        def handler(request):
            return httpx.Response(200, json={"choices": [{"message": {"reasoning_content": "private reasoning"}}]})
        with self.assertRaises(LLMError) as ctx:
            await LLMClient(max_retries=1, transport=httpx.MockTransport(handler)).complete("s", "u")
        self.assertEqual(ctx.exception.code, "empty_response")
