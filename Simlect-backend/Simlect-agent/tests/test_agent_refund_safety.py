import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.auth.token_service import TokenUserInfo, require_login
from app.main import app
from app.services.action_execute_service import (
    ActionExecuteService,
    JavaBridge,
    java_bridge,
)
from app.services.mcp_tools_service import propose_refund
from app.services.pending_action_service import PendingActionService
from app.services.refund_execution_policy import REFUND_ADVICE_ONLY_MESSAGE
from fastapi.testclient import TestClient


@pytest.fixture
def redis_stub():
    redis = MagicMock()
    for name in [
        "ensure_connected",
        "unlock_pending_action",
        "save_pending_action",
        "delete_pending_action",
        "clear_pending_executing",
    ]:
        setattr(redis, name, AsyncMock())
    redis.try_lock_pending_action = AsyncMock(return_value="test-lock-owner")
    redis.get_bound_message_id = AsyncMock(return_value=123)
    redis.get_pending_action = AsyncMock(
        return_value={
            "userId": "u1",
            "actionType": "REFUND",
            "status": 0,
            "paramsJson": json.dumps({"orderItemId": "test-order_1"}),
        }
    )
    redis.try_mark_pending_executing = AsyncMock(return_value=True)
    redis.cas_pending_status = AsyncMock(return_value=True)
    with patch("app.services.pending_action_service.redis_service", redis):
        yield redis


@pytest.mark.asyncio
async def test_refund_proposal_remains_advice_only(redis_stub):
    item = {
        "order_item_id": "test-order_1",
        "order_id": "test-order",
        "order_item_status": 1,
        "item_amount": 20,
        "product_name": "TEST",
        "buy_count": 1,
    }
    order = {"order_id": "test-order", "user_id": "u1", "order_status": 1}
    with (
        patch("app.services.mcp_tools_service.order_service") as orders,
        patch.object(java_bridge, "refund_order", new_callable=AsyncMock) as refund,
    ):
        orders.get_order_item = AsyncMock(return_value=item)
        orders.get_order = AsyncMock(return_value=order)
        result = await propose_refund("u1", "test-order_1")
        assert "退款建议" in result
        assert "不会执行退款" in result
        pending = redis_stub.save_pending_action.call_args.args[1]
        assert pending["actionType"] == "REFUND"
        assert pending["executionEnabled"] is False
        assert pending["paramsJson"]
        orders.get_order_item.assert_awaited_once_with("u1", "test-order_1")
        orders.get_order.assert_awaited_once_with("u1", "test-order")
        refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_confirm_blocks_even_custom_executor(redis_stub):
    executor = AsyncMock()
    with pytest.raises(ValueError, match="仅提供退款建议"):
        await PendingActionService().confirm("u1", "test-action", executor)
    executor.assert_not_awaited()
    redis_stub.cas_pending_status.assert_not_awaited()
    redis_stub.try_mark_pending_executing.assert_not_awaited()
    redis_stub.unlock_pending_action.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params", ["{}", "not-json", '{"actionType":"CONFIRM_RECEIPT"}']
)
async def test_executor_blocks_before_parsing_any_refund_params(params):
    service = ActionExecuteService()
    service._bridge = MagicMock(refund_order=AsyncMock())
    with pytest.raises(ValueError, match="仅提供退款建议"):
        await service.execute(
            {"actionType": "REFUND", "paramsJson": params}, "test-session"
        )
    service._bridge.refund_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_bridge_refund_has_no_http_execution_path():
    bridge = JavaBridge()
    with patch.object(bridge, "_post_form", new_callable=AsyncMock) as post:
        with pytest.raises(ValueError, match="仅提供退款建议"):
            await bridge.refund_order("test-session", "test-order_1")
        post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/order/refundOrder",
        "/order/refundOrder/",
        "/order/refundOrder?enabled=true",
        "/order/../order/refundOrder",
    ],
)
async def test_raw_bridge_cannot_bypass_refund_guard(path):
    with patch("app.services.action_execute_service.httpx.AsyncClient") as client:
        with pytest.raises(ValueError):
            await JavaBridge()._post_form(
                "test-session", path, {"orderItemId": "test-order_1"}
            )
        client.assert_not_called()


@pytest.fixture
def http_client(redis_stub, monkeypatch):
    async def logged_in():
        return TokenUserInfo(user_id="u1", token="test-session")

    from app.api.routes.agent import limiter, rate_limit_service

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(rate_limit_service, "allow", AsyncMock(return_value=True))
    app.dependency_overrides[require_login] = logged_in
    try:
        # No lifespan: database initialization and model clients are not started.
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_login, None)


@pytest.mark.parametrize("enabled", [None, "false", "true"])
def test_http_confirm_always_blocked_and_repeat_safe(
    http_client, redis_stub, monkeypatch, enabled
):
    if enabled is None:
        monkeypatch.delenv("AGENT_REFUND_EXECUTION_ENABLED", raising=False)
    else:
        monkeypatch.setenv("AGENT_REFUND_EXECUTION_ENABLED", enabled)
    with patch.object(java_bridge, "refund_order", new_callable=AsyncMock) as refund:
        for _ in range(2):
            response = http_client.post(
                "/api/agent/confirmAction",
                headers={"token": "test-session"},
                data={
                    "actionToken": "test-action",
                    "actionType": "CONFIRM_RECEIPT",
                    "userId": "another-user",
                    "AGENT_REFUND_EXECUTION_ENABLED": "true",
                    "paramsJson": '{"executionEnabled":true}',
                },
            )
            assert response.status_code == 200
            result = response.json()["data"]
            assert result["success"] is False
            assert result["resultMessage"] == REFUND_ADVICE_ONLY_MESSAGE
        refund.assert_not_awaited()


@pytest.mark.parametrize(
    "record", [None, {"userId": "other-user", "actionType": "REFUND", "status": 0}]
)
def test_forged_or_foreign_action_cannot_execute(http_client, redis_stub, record):
    redis_stub.get_pending_action.return_value = record
    with patch.object(java_bridge, "refund_order", new_callable=AsyncMock) as refund:
        result = http_client.post(
            "/api/agent/confirmAction",
            headers={"token": "test-session"},
            data={"actionToken": "forged-action"},
        ).json()["data"]
        assert result["success"] is False
        refund.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_refund_agent_action_still_uses_existing_bridge():
    with patch.object(
        java_bridge, "confirm_order", new_callable=AsyncMock, return_value="OK"
    ) as receipt:
        result = await ActionExecuteService().execute(
            {"actionType": "CONFIRM_RECEIPT", "paramsJson": '{"orderId":"test-order"}'},
            "test-session",
        )
        assert result == "OK"
        receipt.assert_awaited_once_with("test-session", "test-order")


@pytest.mark.asyncio
async def test_audit_contains_reason_without_credentials_or_order_data():
    with patch("app.services.refund_execution_policy.logger") as logger:
        with pytest.raises(ValueError):
            await JavaBridge().refund_order("do-not-log-token", "do-not-log-order")
        logger.warning.assert_called_once_with(
            "agent_refund_execution_blocked", channel="agent", reason="advice_only"
        )


def test_refund_cards_include_legacy_pending_as_advice_only():
    from app.utils.biz_payload import build_action_confirm_payload

    # Existing pending records need not be rewritten to receive the safe presentation.
    assistant, _ = build_action_confirm_payload(
        {
            "actionType": "REFUND",
            "token": "test-action",
            "status": 0,
            "paramsJson": '{"orderItemId":"test-order_1","refundAmount":20}',
        }
    )
    card = json.loads(assistant)
    assert card["executionEnabled"] is False
    assert card["label"] == "退款建议"
    assert card["confirmText"] == "仅查看退款建议"
    assert card["riskTip"] == REFUND_ADVICE_ONLY_MESSAGE
    assert "确认后将立即执行" not in assistant
