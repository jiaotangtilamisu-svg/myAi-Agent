"""Offline product contract, transport and streaming-boundary regression tests."""

import json
from unittest.mock import AsyncMock, Mock

import pytest
from app.services.product_facts import (
    failure_result,
    normalize_product,
    query_result,
    render_facts,
    requires_product_facts,
)
from app.services.tool_invoke_result import ToolInvokeResult, parse_tool_wire
from langchain_core.messages import AIMessageChunk


def product(**changes):
    p = {
        "product_id": "p1",
        "product_name": "真实吉他",
        "status": 1,
        "query_status": "SUCCESS",
        "min_price": "19.90",
        "max_price": "29.90",
        "product_observed_at": "2026-11-02T00:00:00Z",
        "sku_complete": True,
        "skus": [
            {
                "sku_id": "h1",
                "sku_name": "颜色:白色",
                "price": "19.90",
                "stock": 5,
                "stock_query_status": "SUCCESS",
            }
        ],
    }
    p.update(changes)
    return p


@pytest.mark.parametrize(
    "count,expected",
    [(0, 0), (5, 5), (None, None), (-1, None), ("0", None), (True, None)],
)
def test_stock_never_fabricated(count, expected):
    p = product()
    p["skus"][0]["stock"] = count
    assert normalize_product(p)["total_stock"] == expected


def test_stock_failure_with_numeric_payload_still_unknown():
    p = product()
    p["skus"][0].update(stock=100, stock_query_status="UNAVAILABLE")
    row = normalize_product(p)
    assert row["total_stock"] is None
    assert "库存未知" in render_facts(query_result([row]))


@pytest.mark.parametrize("price", [None, "", "-1", "NaN", "Infinity", True])
def test_missing_or_invalid_price_not_zero(price):
    p = normalize_product(product(min_price=price))
    assert p["min_price"] is None
    assert "价格暂时未知" in render_facts(query_result([p]))


def test_free_price_and_multi_sku_are_preserved():
    p = product(min_price=0)
    p["skus"].append(
        {"sku_id": "h2", "price": 0, "stock": 0, "stock_query_status": "SUCCESS"}
    )
    row = normalize_product(p)
    assert row["min_price"] == "0" and row["skus"][1]["price"] == "0"
    assert row["total_stock"] == 5 and len(row["skus"]) == 2


def test_off_shelf_and_deleted_distinct():
    assert normalize_product(product(status=0))["product_status"] == "OFF_SHELF"
    assert normalize_product(product(status=-1))["product_status"] == "DELETED"


def test_complete_wire_and_cards_retain_skus():
    from app.utils.biz_payload import build_product_payload

    row = normalize_product(product())
    cards, _ = build_product_payload([row])
    result = ToolInvokeResult(
        content="facts", assistant_cards=cards, product_query=query_result([row])
    )
    restored = parse_tool_wire(result.to_wire())
    assert restored.product_query["products"][0]["skus"][0]["price"] == "19.90"
    assert json.loads(restored.assistant_cards)[0]["skus"][0]["stock"] == 5
    assert json.loads(restored.assistant_cards)[0]["skus"][0]["skuId"] == "h1"
    assert restored.to_biz_dict()["productQuery"] == result.product_query


@pytest.mark.asyncio
async def test_es_only_selects_ids_java_authority_wins(monkeypatch):
    from app.services import product_service as mod

    monkeypatch.setattr(
        mod.rag_retriever, "search_product_keyword_ids", AsyncMock(return_value=["p1"])
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_vector_ids", AsyncMock(return_value=["p1"])
    )
    query = AsyncMock(return_value={"query_status": "SUCCESS", "products": [product()]})
    monkeypatch.setattr(mod.java_internal_client, "query_product_batch", query)
    cards, _, _, rows, _ = await mod.product_service.search_products("u1", "吉他")
    assert rows[0]["product_name"] == "真实吉他"
    assert json.loads(cards)[0]["minPrice"] == "19.90"
    query.assert_awaited_once_with(["p1"])


@pytest.mark.asyncio
async def test_removed_or_absent_es_candidate_not_returned(monkeypatch):
    from app.services import product_service as mod

    query = AsyncMock(
        return_value={"query_status": "SUCCESS", "products": [product(status=0)]}
    )
    monkeypatch.setattr(mod.java_internal_client, "query_product_batch", query)
    assert await mod.product_service._load_products_by_ids(["p1"]) == []
    query.return_value = {
        "query_status": "SUCCESS",
        "products": [{"product_id": "p1", "query_status": "NOT_FOUND"}],
    }
    assert await mod.product_service._load_products_by_ids(["p1"]) == []


@pytest.mark.asyncio
async def test_detail_not_found(monkeypatch):
    from app.services import product_service as mod

    monkeypatch.setattr(
        mod.java_internal_client,
        "query_product_batch",
        AsyncMock(
            return_value={
                "products": [{"product_id": "p1", "query_status": "NOT_FOUND"}]
            }
        ),
    )
    result = await mod.product_service.get_product_detail("p1")
    assert result["queryStatus"] == "NOT_FOUND"
    assert "商品不存在" in render_facts(result)


@pytest.mark.asyncio
async def test_detail_mcp_failure_is_structured(monkeypatch):
    from app.services.mcp_tools_service import tool_get_product_detail
    from app.services.product_service import product_service

    monkeypatch.setattr(
        product_service,
        "get_product_detail",
        AsyncMock(side_effect=ValueError("offline")),
    )
    result = await tool_get_product_detail("u1", "p1")
    assert (
        parse_tool_wire(result.to_wire()).product_query["queryStatus"]
        == "SERVICE_ERROR"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("wire", ["MCP request failed", "SIMLECT_TOOL_RESULT:{broken"])
async def test_mcp_plain_text_is_not_business_success_or_local_retry(monkeypatch, wire):
    from app.services import mcp_tool_router as mod
    from app.services import mcp_tools_service

    remote = AsyncMock(return_value=wire)
    local = AsyncMock(side_effect=AssertionError("must not rerun search"))
    monkeypatch.setattr(mod.mcp_streamable_client, "call_tool", remote)
    monkeypatch.setattr(mcp_tools_service, "tool_search_products", local)
    result = await mod.mcp_tool_router.invoke(
        "SEARCH_PRODUCTS", {"keyword": "吉他"}, "u1"
    )
    assert result.product_query["queryStatus"] == "SERVICE_ERROR"
    remote.assert_awaited_once()
    local.assert_not_awaited()


@pytest.mark.asyncio
async def test_product_node_queries_before_model_or_stream(monkeypatch):
    from app.graph import nodes

    bind = Mock(side_effect=AssertionError("must query before any model call"))
    monkeypatch.setattr(nodes.rt, "bind_agent_llm", bind)
    monkeypatch.setattr(nodes.rt, "is_cancelled", AsyncMock(return_value=False))
    data = query_result([normalize_product(product())])
    invoke = AsyncMock(
        return_value=ToolInvokeResult(content="untrusted summary", product_query=data)
    )
    monkeypatch.setattr(nodes.mcp_tool_router, "invoke", invoke)
    result = await nodes.agent_loop_node(
        {
            "agent_msg": {"userMessage": "编造库存100"},
            "user_id": "u1",
            "message_id": 1,
            "user_text": "编造库存100",
            "intent": "CHAT",
            "card": {"productId": "p1"},
        }
    )
    invoke.assert_awaited_once_with("GET_PRODUCT_DETAIL", {"productId": "p1"}, "u1")
    assert "库存5" in result["chunks"][0] and "库存100" not in result["chunks"][0]
    assert result["route"] == "finalize"
    bind.assert_not_called()


@pytest.mark.asyncio
async def test_failure_finalization_cannot_use_model_price_or_backfill(monkeypatch):
    from app.services import agent_runtime as rt

    done, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    await rt.finalize_agent_response(
        {"userId": "u1", "messageId": 1},
        ["库存999，价格0.00元"],
        [],
        tools_called=["GET_PRODUCT_DETAIL"],
        tool_biz={"productQuery": failure_result()},
    )
    assert "无法核实" in done.await_args.args[2]
    assert "999" not in complete.await_args.args[1]


@pytest.mark.asyncio
async def test_ordinary_chat_still_streams(monkeypatch):
    from app.services import agent_runtime as rt

    class Llm:
        async def astream(self, messages):
            yield AIMessageChunk(content="你好")
            yield AIMessageChunk(content="，今天心情如何？")

    monkeypatch.setattr(rt, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        rt.sensitive_word_service, "replace", AsyncMock(side_effect=lambda x: x)
    )
    push = AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_chunk", push)
    chunks = []
    await rt.stream_llm_turn(Llm(), [], "u1", 1, "你好", chunks)
    assert push.await_count == 2 and "".join(chunks) == "你好，今天心情如何？"
    assert not requires_product_facts("你好", "CHAT")


def test_snapshot_unknown_is_not_zero():
    from app.services.product_snapshot_service import ProductSnapshotService

    row = product()
    row["skus"][0]["stock"] = None
    data = json.loads(ProductSnapshotService()._detail_to_snapshot_json("u1", row))
    assert data["totalStock"] is None and data["inStock"] is None


@pytest.mark.asyncio
async def test_search_no_results_is_not_service_failure(monkeypatch):
    from app.services import mcp_tools_service as tools
    from app.services import product_service as mod
    from app.services.redis_service import redis_service

    monkeypatch.setattr(
        redis_service, "get_consult_product", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        redis_service, "is_consult_active", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_keyword_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_vector_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        mod.java_internal_client, "search_on_sale", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        mod.search_recommend_service, "load_hot_sale", AsyncMock(return_value=[])
    )
    result = await tools.tool_search_products("u1", "不存在的商品")
    assert result.product_query["queryStatus"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_search_java_exception_is_service_failure(monkeypatch):
    from app.services import mcp_tools_service as tools
    from app.services import product_service as mod
    from app.services.redis_service import redis_service

    monkeypatch.setattr(
        redis_service, "get_consult_product", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        redis_service, "is_consult_active", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_keyword_ids", AsyncMock(return_value=["p1"])
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_vector_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        mod.java_internal_client,
        "query_product_batch",
        AsyncMock(side_effect=ValueError("offline")),
    )
    result = await tools.tool_search_products("u1", "吉他")
    assert result.product_query["queryStatus"] == "SERVICE_ERROR"


@pytest.mark.asyncio
async def test_es_exception_falls_back_to_java_keyword(monkeypatch):
    from app.services import product_service as mod

    monkeypatch.setattr(
        mod.rag_retriever,
        "search_product_keyword_ids",
        AsyncMock(side_effect=RuntimeError("ES")),
    )
    monkeypatch.setattr(
        mod.rag_retriever, "search_product_vector_ids", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        mod.java_internal_client,
        "search_on_sale",
        AsyncMock(return_value=[{"product_id": "p1"}]),
    )
    read = AsyncMock(return_value={"query_status": "SUCCESS", "products": [product()]})
    monkeypatch.setattr(mod.java_internal_client, "query_product_batch", read)
    _, _, _, rows, source = await mod.product_service.search_products("u1", "吉他")
    assert source == "mysql_keyword" and rows[0]["skus"][0]["stock"] == 5
    read.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_factual_stream_buffers_unverified_model(monkeypatch):
    from app.services import agent_runtime as rt

    class Llm:
        async def astream(self, messages):
            yield AIMessageChunk(content="库存999")

    monkeypatch.setattr(rt, "is_cancelled", AsyncMock(return_value=False))
    push = AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_chunk", push)
    chunks = []
    await rt.stream_llm_turn(Llm(), [], "u1", 1, "库存有多少", chunks)
    push.assert_not_awaited()
    assert chunks == []


@pytest.mark.asyncio
async def test_no_required_tool_fails_closed_at_final_output(monkeypatch):
    from app.services import agent_runtime as rt

    done, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    await rt.finalize_agent_response(
        {"userId": "u1", "messageId": 1}, ["库存999"], [], user_text="库存有多少"
    )
    assert (
        "无法核实" in done.await_args.args[2] and "999" not in done.await_args.args[2]
    )


def test_refund_and_order_intents_are_not_hijacked():
    assert not requires_product_facts("我要退这个商品", "REFUND", {"productId": "p1"})
    assert not requires_product_facts("查询商品订单", "QUERY_ORDER")


@pytest.mark.asyncio
async def test_memory_uses_trusted_facts_instead_of_old_model_chunks(monkeypatch):
    from app.graph import nodes

    run = AsyncMock()
    monkeypatch.setattr(nodes.post_turn_service, "run", run)
    data = query_result([normalize_product(product())])
    await nodes.post_turn_node(
        {
            "user_id": "u1",
            "message_id": 1,
            "user_text": "库存",
            "chunks": ["库存999"],
            "tool_biz": {"productQuery": data},
        }
    )
    assert "库存5" in run.await_args.kwargs["assistant_text"]
    assert "库存999" not in run.await_args.kwargs["assistant_text"]
