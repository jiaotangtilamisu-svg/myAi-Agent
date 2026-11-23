"""Real SDK over MockTransport only: no paid requests or sockets."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.config.settings import Settings
from app.rag import advice
from app.services import llm_factory

EVIDENCE = {"status": "SUCCESS", "hits": [{"chunkId": "known", "documentId": "doc",
    "source": "fixture://policy", "text": "TEST ONLY"}]}


@pytest.fixture
def config(monkeypatch):
    settings = Settings(_env_file=None, llm_api_key="test-key-not-real",
        llm_base_url="https://model.invalid/v1", policy_llm_timeout_seconds=20)
    monkeypatch.setattr(advice, "get_settings", lambda: settings)
    monkeypatch.setattr(llm_factory, "get_settings", lambda: settings)
    return settings


def mock_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    class MockClient(original):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), trust_env=False, **kwargs)
    monkeypatch.setattr(advice.httpx, "AsyncClient", MockClient)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [503, 401, 400, "read_timeout", "connect_error"])
async def test_provider_network_and_configuration_errors_are_single_attempt(monkeypatch, config, failure):
    attempts = []
    def handler(request):
        attempts.append(request)
        if failure == "read_timeout":
            raise httpx.ReadTimeout("private-provider-details", request=request)
        if failure == "connect_error":
            raise httpx.ConnectError("private-provider-details", request=request)
        return httpx.Response(failure, json={"error": {"message": "private-provider-details", "type": "test"}})
    mock_transport(monkeypatch, handler)
    log = Mock(); monkeypatch.setattr(advice, "logger", log)
    result = await advice.policy_advice("TEST", EVIDENCE)
    assert result["status"] == "UNAVAILABLE" and result["executionAllowed"] is False
    assert len(attempts) == 1  # SDK is real, automatic retries must be disabled.
    fields = log.warning.call_args.kwargs
    assert fields["attempts"] == 1
    assert fields["status_code"] == (failure if isinstance(failure, int) else None)
    assert "private-provider-details" not in str(log.mock_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("valid", [True, False])
@pytest.mark.parametrize("deepseek", [True, False])
async def test_http_success_is_not_confused_with_valid_business_result(monkeypatch, config, valid, deepseek):
    if deepseek:
        config.llm_base_url = "https://api.deepseek.com"
    attempts = []
    def handler(request):
        attempts.append(request)
        content = json.dumps({"selectedChunkIds": ["known" if valid else "invented"], "neededFacts": ["category"]})
        return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 1,
            "model": "mock", "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}})
    mock_transport(monkeypatch, handler)
    result = await advice.policy_advice("TEST", EVIDENCE)
    assert result["status"] == ("MODEL_GROUNDED" if valid else "UNAVAILABLE")
    assert len(attempts) == 1
    payload = json.loads(attempts[0].content)
    assert payload.get("stream") is not True
    if deepseek:
        assert payload["max_tokens"] == 512 and "max_completion_tokens" not in payload
        assert payload["thinking"] == {"type": "disabled"}
    else:
        assert payload["max_completion_tokens"] == 512


@pytest.mark.asyncio
async def test_wall_clock_deadline_cancels_slow_model_without_retry(monkeypatch, config):
    config.policy_llm_timeout_seconds = 0.02
    cancelled = []
    async def slow(*args):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    call = AsyncMock(side_effect=slow)
    monkeypatch.setattr(advice, "create_policy_llm", lambda **kw: SimpleNamespace(ainvoke=call))
    result = await advice.policy_advice("TEST", EVIDENCE)
    assert result["status"] == "UNAVAILABLE" and cancelled == [True]
    call.assert_awaited_once()


@pytest.mark.asyncio
async def test_policy_factory_does_not_change_normal_chat(config):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(500))) as client:
        model = llm_factory.create_policy_llm(http_async_client=client)
        assert model.streaming is False and model.root_async_client.max_retries == 0
        assert model.request_timeout.read == config.policy_llm_timeout_seconds
        assert model.request_timeout.connect == min(5, config.policy_llm_timeout_seconds)
        assert llm_factory.create_chat_llm().streaming is True


@pytest.mark.asyncio
async def test_deepseek_policy_selection_disables_thinking_only_for_that_call(monkeypatch, config):
    config.llm_base_url = "https://api.deepseek.com"
    async with httpx.AsyncClient() as client:
        policy = llm_factory.create_policy_llm(http_async_client=client)
        assert policy.extra_body == {"thinking": {"type": "disabled"}, "max_tokens": 512}
        assert llm_factory.create_chat_llm().extra_body is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["SUCCESS", "NO_MATCH", "ES_UNAVAILABLE"])
async def test_policy_turn_never_schedules_an_extra_memory_model(monkeypatch, status):
    from app.memory import post_turn as mod
    service = mod.PostTurnService()
    memory = SimpleNamespace(state={})
    monkeypatch.setattr(mod.session_memory_service, "load", AsyncMock(return_value=memory))
    monkeypatch.setattr(mod.session_memory_service, "save", AsyncMock())
    saved = AsyncMock()
    monkeypatch.setattr(mod, "redis_service", SimpleNamespace(client=object(), save_history_condensed=saved))
    monkeypatch.setattr(service, "_sync_consult_product", AsyncMock())
    monkeypatch.setattr(service, "_sync_pending_action", AsyncMock())
    monkeypatch.setattr(service, "_sync_tool_results", Mock())
    monkeypatch.setattr(mod, "_extract_search_result_cards", lambda *args: [])
    schedule = Mock(); compress = AsyncMock()
    monkeypatch.setattr(mod, "schedule_assistant_condense", schedule)
    monkeypatch.setattr(mod.compress_service, "maybe_schedule_compress", compress)
    await service.run(user_id="test", message_id=1, user_text="TEST", assistant_text="x"*1000,
        tools_called=[], tool_biz={"policyQuery": {"status": status}}, card=None,
        assistant_cards=None, working_turns=[], working_oldest_id=None)
    schedule.assert_not_called(); compress.assert_not_awaited(); saved.assert_awaited_once()

