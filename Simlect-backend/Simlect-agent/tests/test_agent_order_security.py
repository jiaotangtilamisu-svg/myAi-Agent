import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.auth.agent_context import agent_user_context, current_agent_user
from app.auth.token_service import TokenUserInfo
from app.main import app
from app.services.java_internal_client import JavaInternalClient
from app.services.java_internal_client_db import JavaInternalClientDb
from app.services.mcp_tool_router import McpToolRouter
from app.services.order_service import OrderService
from fastapi.testclient import TestClient
from starlette.requests import Request

ORDER_METHODS = [
    "get_order",
    "get_order_item",
    "list_order_items",
    "get_logistics",
    "get_comment",
    "list_orders",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ORDER_METHODS)
@pytest.mark.parametrize("user", ["user-a", "user-b"])
async def test_internal_http_order_queries_bind_verified_identity(method, user):
    client = JavaInternalClient()
    client.post_json = AsyncMock(return_value=None)
    with agent_user_context(user, "test-session"):
        args = [user] if method == "list_orders" else [user, "test-id"]
        await getattr(client, method)(*args)
        assert client.post_json.call_args.args[1]["userId"] == user
        assert client._headers()["token"] == "test-session"


@pytest.mark.asyncio
@pytest.mark.parametrize("client_class", [JavaInternalClient, JavaInternalClientDb])
@pytest.mark.parametrize("method", ORDER_METHODS)
async def test_foreign_user_id_is_rejected_before_http_or_db(client_class, method):
    client = client_class()
    with (
        patch("app.services.java_internal_client_db._db_cur") as db,
        patch.object(JavaInternalClient, "post_json", new_callable=AsyncMock) as post,
    ):
        with (
            agent_user_context("user-a", "test-session"),
            pytest.raises(ValueError, match="身份校验"),
        ):
            args = ["user-b"] if method == "list_orders" else ["user-b", "test-id"]
            await getattr(client, method)(*args)
        db.assert_not_called()
        post.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_verified_context_cannot_read_order():
    with pytest.raises(ValueError, match="身份校验"):
        await JavaInternalClient().get_order("user-a", "test-order")


@pytest.mark.asyncio
async def test_router_replaces_model_user_id_and_rejects_forged_context():
    with (
        patch(
            "app.services.mcp_tool_router.mcp_streamable_client.call_tool",
            new_callable=AsyncMock,
            return_value="mock logistics",
        ) as call,
        agent_user_context("user-a", "test-session"),
    ):
        await McpToolRouter().invoke(
            "QUERY_LOGISTICS", {"userId": "user-b", "orderId": "test-order"}, "user-a"
        )
        assert call.call_args.args[1]["userId"] == "user-a"
        call.reset_mock()
        result = await McpToolRouter().invoke(
            "QUERY_ORDERS", {"userId": "user-b"}, "user-b"
        )
        assert "身份校验未通过" in result.content
        call.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_identity_is_task_local_and_inherited_by_background_task():
    async def read(user):
        with agent_user_context(user, "test-session"):

            async def child():
                await asyncio.sleep(0)
                return current_agent_user().user_id

            return await asyncio.create_task(child())

    assert await asyncio.gather(read("user-a"), read("user-b")) == ["user-a", "user-b"]
    assert current_agent_user() is None


@pytest.mark.asyncio
async def test_mcp_order_handler_requires_session_and_cannot_forge_user_id():
    from app.mcp_server import server

    request = Request({"type": "http", "headers": [(b"token", b"test-session")]})
    context = SimpleNamespace(request_context=SimpleNamespace(request=request))
    with (
        patch.object(server.mcp, "get_context", return_value=context),
        patch.object(server, "get_user_by_token", new_callable=AsyncMock) as login,
        patch.object(
            server.tools,
            "tool_query_orders",
            new_callable=AsyncMock,
            return_value="mock orders",
        ) as orders,
    ):
        login.return_value = None
        with pytest.raises(ValueError, match="身份校验"):
            await server.query_orders("user-a")
        login.return_value = TokenUserInfo(user_id="user-a", token="test-session")
        with pytest.raises(ValueError, match="身份校验"):
            await server.query_orders("user-b")
        orders.assert_not_awaited()
        assert await server.query_orders("user-a") == "mock orders"
        orders.assert_awaited_once_with("user-a", None)
        assert current_agent_user() is None


@pytest.mark.asyncio
async def test_mcp_transport_forwards_session_only_in_http_header():
    from app.services.mcp_streamable_client import McpStreamableClient

    session = MagicMock(initialize=AsyncMock())
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)
    transport_cm = MagicMock()
    transport_cm.__aenter__ = AsyncMock(return_value=(None, None, None))
    transport_cm.__aexit__ = AsyncMock(return_value=None)
    with (
        patch(
            "mcp.client.streamable_http.streamablehttp_client",
            return_value=transport_cm,
        ) as transport,
        patch("mcp.ClientSession", return_value=session_cm),
    ):
        with agent_user_context("user-a", "test-session"):
            async with McpStreamableClient()._session():
                pass
        assert transport.call_args.kwargs["headers"]["token"] == "test-session"


@pytest.mark.asyncio
async def test_order_query_preserves_real_refund_status_from_business_data():
    order = {
        "order_id": "test-order",
        "user_id": "user-a",
        "order_status": 6,
        "amount": 20,
        "items": [
            {
                "order_item_id": "test-order_1",
                "order_id": "test-order",
                "product_name": "TEST",
                "order_item_status": 0,
                "item_amount": 20,
                "buy_count": 1,
            }
        ],
    }
    with patch(
        "app.services.order_service.java_internal_client.list_orders",
        new_callable=AsyncMock,
        return_value=[order],
    ):
        assistant, _, kind = await OrderService().query_orders("user-a", "test-order")
        assert kind == "query_order"
        assert json.loads(assistant)[0]["orderStatus"] == 6


def test_http_send_uses_verified_session_and_never_client_user_id(monkeypatch):
    from app.api.routes.agent import agent_orchestrator, limiter
    from app.constants import REDIS_TOKEN_WEB

    monkeypatch.setattr(limiter, "enabled", False)
    observed = []

    async def send(user_id, *args):
        user = current_agent_user()
        observed.append((user_id, user.user_id, user.token))
        return {"messageId": 123}

    with (
        patch("app.auth.token_service.redis_service") as redis,
        patch.object(
            agent_orchestrator, "send_message", new_callable=AsyncMock, side_effect=send
        ),
    ):
        redis.client.get = AsyncMock(
            return_value=json.dumps({"userId": "user-a", "token": "stale-stored-token"})
        )
        result = TestClient(app).post(
            "/api/agent/sendMessage",
            headers={"token": "test-session-a"},
            data={"message": "test", "userId": "user-b", "token": "forged-session"},
        )
        assert result.json()["code"] == 200
        assert observed == [("user-a", "user-a", "test-session-a")]
        redis.client.get.assert_awaited_once_with(REDIS_TOKEN_WEB + "test-session-a")
        assert current_agent_user() is None


def test_http_refund_confirmation_requires_valid_login_before_loading_action(
    monkeypatch,
):
    from app.api.routes.agent import limiter, pending_action_service

    monkeypatch.setattr(limiter, "enabled", False)
    with (
        patch("app.auth.token_service.redis_service") as redis,
        patch.object(
            pending_action_service, "confirm", new_callable=AsyncMock
        ) as confirm,
    ):
        redis.client.get = AsyncMock(return_value=None)
        response = TestClient(app).post(
            "/api/agent/confirmAction",
            headers={"token": "invalid-session"},
            data={"actionToken": "test-action", "userId": "user-b"},
        )
        assert response.json()["code"] == 901
        confirm.assert_not_awaited()


@pytest.mark.asyncio
async def test_registered_mcp_refund_tool_is_proposal_only():
    from app.mcp_server.server import mcp

    tools = {tool.name for tool in await mcp.list_tools()}
    assert {tool for tool in tools if "REFUND" in tool} == {"PROPOSE_REFUND"}


@pytest.mark.asyncio
async def test_mcp_http_protocol_passes_verified_identity_to_tool():
    """Use the real MCP protocol in-process, with mocked session storage and business reads."""
    import httpx
    from app.mcp_server import server
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    inner = server.mcp.streamable_http_app()
    protected = server._InternalTokenMiddleware(inner, "test-internal")

    def client_factory(**kwargs):
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=protected), **kwargs)

    async def lookup(token):
        return (
            TokenUserInfo(user_id="user-a", token=token)
            if token == "test-session-a"
            else None
        )

    async def query(user_id, order_id):
        assert current_agent_user().user_id == user_id == "user-a"
        assert current_agent_user().token == "test-session-a"
        return "MOCK authenticated orders"

    with (
        patch.object(server.redis_service, "ensure_connected", new_callable=AsyncMock),
        patch.object(
            server, "get_user_by_token", new_callable=AsyncMock, side_effect=lookup
        ),
        patch.object(
            server.tools, "tool_query_orders", new_callable=AsyncMock, side_effect=query
        ) as orders,
    ):
        async with (
            asyncio.timeout(15),
            inner.router.lifespan_context(inner),
            streamablehttp_client(
                "http://localhost:7060/mcp",
                headers={
                    "X-Internal-Token": "test-internal",
                    "token": "test-session-a",
                },
                httpx_client_factory=client_factory,
            ) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            result = await session.call_tool("QUERY_ORDERS", {"userId": "user-a"})
            assert not result.isError
            assert result.content[0].text == "MOCK authenticated orders"
            orders.assert_awaited_once()
            result = await session.call_tool("QUERY_ORDERS", {"userId": "user-b"})
            assert result.isError
            assert orders.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_order", "get_order_item", "list_order_items"])
@pytest.mark.parametrize(
    "user,target,allowed",
    [
        ("user-a", "a", True),
        ("user-b", "b", True),
        ("user-a", "b", False),
    ],
)
async def test_db_fallback_sql_enforces_parent_ownership_in_memory(
    method, user, target, allowed
):
    """Run the adapter's actual SELECT/JOIN against temporary in-memory rows, not a development DB."""
    import sqlite3
    from contextlib import asynccontextmanager

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        "CREATE TABLE order_info (order_id TEXT, user_id TEXT);"
        "CREATE TABLE order_item (order_item_id TEXT, order_id TEXT);"
        "INSERT INTO order_info VALUES ('order-a','user-a'),('order-b','user-b');"
        "INSERT INTO order_item VALUES ('item-a','order-a'),('item-b','order-b');"
    )

    class Cursor:
        async def execute(self, sql, params):
            self.cursor = connection.execute(sql.replace("%s", "?"), params)

        async def fetchone(self):
            return self.cursor.fetchone()

        async def fetchall(self):
            return self.cursor.fetchall()

    @asynccontextmanager
    async def cursor():
        yield Cursor()

    try:
        with (
            agent_user_context(user, "test-session"),
            patch("app.services.java_internal_client_db._db_cur", cursor),
        ):
            identifier = ("item-" if method == "get_order_item" else "order-") + target
            result = await getattr(JavaInternalClientDb(), method)(user, identifier)
            assert bool(result) is allowed
    finally:
        connection.close()
