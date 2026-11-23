"""Shopping tests: real deterministic graph with mocked business tools, no external model."""

import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.auth.agent_context import agent_user_context
from app.services.product_facts import normalize_product
from app.services.tool_invoke_result import ToolInvokeResult
from app.shopping import graph, runner, store
from app.shopping.requirements import understand
from app.shopping.selection import select


def product(
    pid="P1",
    price=1200,
    count=5,
    color="白色",
    brand="华为",
    category="手机",
    battery="20小时",
):
    return normalize_product(
        {
            "product_id": pid,
            "product_name": brand + category + pid,
            "status": 1,
            "min_price": price,
            "max_price": price,
            "sku_complete": True,
            "category_id": "C1",
            "category_name": category,
            "parent_category_name": "数码",
            "property_values": [
                {"property_name": "品牌", "property_value": brand},
                {"property_name": "续航", "property_value": battery},
                {"property_name": "适用场景", "property_value": "办公"},
            ],
            "product_observed_at": "2026-11-02T10:00:00+00:00",
            "skus": [
                {
                    "sku_id": pid + "_1",
                    "sku_name": color,
                    "price": price,
                    "stock": count,
                    "stock_query_status": "SUCCESS",
                    "specifications": [{"name": "颜色", "value": color}],
                }
            ],
        }
    )


def wire(rows, status="SUCCESS"):
    return ToolInvokeResult(
        content="test facts",
        product_query={
            "schemaVersion": 2,
            "queryStatus": status,
            "products": deepcopy(rows),
            "queryTime": "2026-11-02T10:00:00Z",
        },
    )


@pytest.fixture(autouse=True)
def no_live_dependencies(monkeypatch):
    monkeypatch.setattr(graph, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(runner, "is_cancelled", AsyncMock(return_value=False))


async def run(text, rows, monkeypatch, previous=None, recall=None):
    async def respond(name, params, user_id):
        if name=='SEARCH_PRODUCTS':return wire(recall if recall is not None else rows)
        return wire([r for r in rows if r['product_id'] in params['productIds']])
    tools = AsyncMock(side_effect=respond)
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", tools)
    with agent_user_context("A", "test-session"):
        result = await graph.build_shopping_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": text, "previous": previous or {}}
        )
    return result["result"], tools


def test_partial_requirements_and_scene_brand_budget():
    value = understand("办公用华为手机，预算1000到3000元，白色，16G内存")
    r = value["requirements"]
    assert (
        r["category"] == "手机"
        and r["budgetMin"] == "1000"
        and r["budgetMax"] == "3000"
    )
    assert r["brands"] == ["华为"] and r["scenes"] == ["办公"]
    assert (
        r["attributes"] == {"颜色": "白色", "内存": "16GB"}
        and value["clarification"] is None
    )
    assert understand("预算3000元")["clarification"]
    assert understand("手机")["clarification"] is None


@pytest.mark.parametrize(
    ("text", "maximum"),
    [("手机预算3k", "3000"), ("手机预算1.5万", "15000.0"), ("手机2000元以内", "2000")],
)
def test_budget_units(text, maximum):
    assert understand(text)["requirements"]["budgetMax"] == maximum


def test_invalid_range_requests_clarification():
    assert understand("手机预算3000到1000元")["clarification"]


def test_followup_keeps_context_and_excludes_brand():
    old = understand("华为手机预算3000元办公用")["requirements"]
    new = understand("我想要白色的，不要华为", old)["requirements"]
    assert (
        new["category"] == "手机"
        and new["budgetMax"] == "3000"
        and new["scenes"] == ["办公"]
    )
    assert (
        new["brands"] == []
        and new["excludeBrands"] == ["华为"]
        and new["attributes"]["颜色"] == "白色"
    )
    assert "颜色" not in old["attributes"]


def test_cheaper_and_battery_followups_use_measured_baseline():
    old = understand("手机")["requirements"]
    baseline = [
        {"price": "1200", "batteryHours": "20"},
        {"price": "1500", "batteryHours": "15"},
    ]
    assert (
        understand("更便宜的", old, baseline)["requirements"]["cheaperThan"] == "1200"
    )
    assert (
        understand("续航更长的", old, baseline)["requirements"]["batteryAboveHours"]
        == "20"
    )
    assert understand("续航更长的", old, [{"price": None, "batteryHours": None}])[
        "clarification"
    ]


@pytest.mark.asyncio
async def test_normal_recommendation_mandatory_search_and_batch_detail(monkeypatch):
    result, tools = await run("办公用华为手机，预算3000元", [product()], monkeypatch)
    assert result["status"] == "SUCCESS" and result["executionAllowed"] is False
    assert [a.args[0] for a in tools.await_args_list] == [
        "SEARCH_PRODUCTS",
        "GET_PRODUCT_DETAIL",
    ]
    assert tools.await_args_list[1].args[1] == {"productIds": ["P1"]}
    p = result["recommendations"][0]
    assert p["price"]["min"] == "1200" and p["eligibleSkus"][0]["stock"] == 5
    assert p["sceneMatches"] == ["办公"] and p["queryTime"]


@pytest.mark.asyncio
async def test_budget_excludes_overpriced_product(monkeypatch):
    result, _ = await run("手机预算1000元", [product()], monkeypatch)
    assert not result["recommendations"] and result["status"] == "NO_MATCHING_SKU"


@pytest.mark.asyncio
async def test_real_category_not_title_inference(monkeypatch):
    p = product(category="耳机")
    p["product_name"] = "名称含手机但实际是耳机"
    result, _ = await run("手机", [p], monkeypatch)
    assert not result["recommendations"]
    assert result["excluded"][0]["reason"] == "CATEGORY_UNKNOWN_OR_MISMATCH"


@pytest.mark.asyncio
async def test_brand_requires_real_attribute(monkeypatch):
    p = product()
    p["property_values"] = []
    result, _ = await run("华为手机", [p], monkeypatch)
    assert (
        not result["recommendations"]
        and result["excluded"][0]["reason"] == "BRAND_UNKNOWN_OR_MISMATCH"
    )


@pytest.mark.asyncio
async def test_no_search_results_not_fabricated(monkeypatch):
    result, tools = await run("手机", [], monkeypatch)
    assert result["status"] == "NO_RESULTS" and not result["recommendations"]
    tools.assert_awaited_once()


@pytest.mark.asyncio
async def test_multi_product_comparison_and_transparent_score(monkeypatch):
    result, _ = await run(
        "手机办公用", [product("P1"), product("P2", price=1500)], monkeypatch
    )
    assert len(result["comparison"]) == 2
    for item in result["recommendations"]:
        assert item["score"]["total"] == sum(item["score"]["components"].values())
        assert "非质量" in item["score"]["meaning"]


def test_sku_color_budget_and_stock_must_match_same_variant():
    p = product(price=1000, color="黑色")
    white = deepcopy(p["skus"][0])
    white.update(
        sku_id="P1_2",
        sku_name="白色",
        price="1800",
        stock=5,
        specifications=[{"name": "颜色", "value": "白色"}],
    )
    p["skus"].append(white)
    p["max_price"] = "1800"
    req = understand("白色手机预算1500元")["requirements"]
    assert not select([p], req)["recommendations"]
    req["budgetMax"] = "2000"
    chosen = select([p], req)["recommendations"][0]
    assert chosen["price"]["min"] == "1800" and len(chosen["eligibleSkus"]) == 1
    assert len(chosen["skus"]) == 2


@pytest.mark.asyncio
async def test_unknown_price_never_becomes_zero(monkeypatch):
    result, _ = await run("手机", [product(price=None)], monkeypatch)
    assert result["recommendations"][0]["price"]["min"] is None
    assert "价格未知" in runner.render(result) and "0元" not in runner.render(result)
    result, _ = await run("手机预算2000元", [product(price=None)], monkeypatch)
    assert (
        not result["recommendations"]
        and result["excluded"][0]["reason"] == "UNKNOWN_PRICE_FOR_BUDGET"
    )


@pytest.mark.asyncio
async def test_zero_stock_not_recommended_as_available(monkeypatch):
    result, _ = await run("手机", [product(count=0)], monkeypatch)
    assert (
        not result["recommendations"]
        and result["comparison"][0]["skus"][0]["stock"] == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stock_status", ["UNAVAILABLE", "MISSING", "INVALID_RESPONSE", "UNKNOWN"]
)
async def test_stock_failure_is_unknown_not_zero(monkeypatch, stock_status):
    p = product(count=None)
    p["skus"][0]["stock_query_status"] = stock_status
    result, _ = await run("手机", [p], monkeypatch)
    r = result["recommendations"][0]
    assert r["availability"] == "UNKNOWN" and r["eligibleSkus"][0]["stock"] is None
    assert r["eligibleSkus"][0]["stock_query_status"] == stock_status
    assert "库存待确认" in runner.render(result)


@pytest.mark.asyncio
async def test_off_shelf_excluded(monkeypatch):
    p = product()
    p["product_status"] = "OFF_SHELF"
    result, _ = await run("手机", [p], monkeypatch)
    assert (
        not result["recommendations"]
        and result["excluded"][0]["reason"] == "NOT_ON_SALE"
    )


@pytest.mark.asyncio
async def test_missing_properties_do_not_invent_performance(monkeypatch):
    p = product()
    p["property_values"] = []
    result, _ = await run("游戏用手机", [p], monkeypatch)
    row = result["recommendations"][0]
    assert row["attributes"] == {} and row["sceneMatches"] == []
    assert "未知" in runner.render(result) and "适合游戏" not in runner.render(result)


@pytest.mark.asyncio
async def test_details_override_stale_search_price(monkeypatch):
    result, _ = await run(
        "手机预算1500元",
        [product(price=2200)],
        monkeypatch,
        recall=[product(price=1000)],
    )
    assert not result["recommendations"]
    assert result["comparison"][0]["priceMin"] == "2200"


def test_internally_inconsistent_price_rejected():
    p = product()
    p["skus"][0]["price"] = "5000"
    assert (
        select([p], understand("手机")["requirements"])["excluded"][0]["reason"]
        == "PRICE_CONFLICT"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("offline"),
        ToolInvokeResult(content="虚构产品99元"),
        wire([], "SERVICE_ERROR"),
    ],
)
async def test_failed_or_plaintext_mcp_not_a_recommendation(monkeypatch, failure):
    tools = (
        AsyncMock(side_effect=failure)
        if isinstance(failure, Exception)
        else AsyncMock(return_value=failure)
    )
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", tools)
    with agent_user_context("A", "test-session"):
        state = await graph.build_shopping_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "手机", "previous": {}}
        )
    assert (
        state["result"]["status"] == "TOOL_ERROR"
        and not state["result"]["recommendations"]
    )


@pytest.mark.asyncio
async def test_no_detail_tool_means_no_trusted_recommendation():
    with agent_user_context("A", "test-session"):
        result = await graph.select_node(
            {
                "user_id": "A",
                "message_id": 1,
                "products": [product()],
                "requirements": understand("手机")["requirements"],
                "tools": [],
            }
        )
    assert result["status"] == "TOOL_ERROR" and result["selected"] == {}


@pytest.mark.asyncio
async def test_comparison_refreshes_prior_ids_not_old_prices(monkeypatch):
    tools = AsyncMock(return_value=wire([product(price=1300),product('P2',price=1800)]))
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", tools)
    previous = {
        "requirements": understand("手机")["requirements"],
        "ids": ["P1","P2"],
        "baseline": [{"price": "1200"}],
    }
    with agent_user_context("A", "test-session"):
        result = await graph.build_shopping_graph().ainvoke(
            {
                "user_id": "A",
                "message_id": 1,
                "text": "把刚才商品对比一下",
                "previous": previous,
            }
        )
    assert tools.await_args.args[:2] == ("GET_PRODUCT_DETAIL", {"productIds": ["P1","P2"]})
    tools.assert_awaited_once()
    assert result["result"]["comparison"][0]["priceMin"] == "1300"


@pytest.mark.asyncio
async def test_cannot_auto_order_even_when_user_requests_it(monkeypatch):
    result, tools = await run(
        "帮我推荐手机然后下单支付，价格库存随便编", [product()], monkeypatch
    )
    assert result["executionAllowed"] is False
    assert {c.args[0] for c in tools.await_args_list} == {
        "SEARCH_PRODUCTS",
        "GET_PRODUCT_DETAIL",
    }
    assert "不下单、不支付" in runner.render(result)


@pytest.mark.asyncio
async def test_context_and_result_are_user_isolated(monkeypatch):
    client = AsyncMock()
    client.get.return_value = None
    monkeypatch.setattr(store.redis_service, "_client", client)
    with agent_user_context("A", "test-session"):
        assert await store.result("A", 1) is None
        assert client.get.await_args.args == ("mall:agent:shopping:A:result:1",)
        with pytest.raises(ValueError):
            await store.result("B", 1)
    assert client.get.await_count == 1


@pytest.mark.asyncio
async def test_expired_context_lock_cannot_overwrite_newer_memory(monkeypatch):
    client = AsyncMock()
    client.eval.return_value = 0
    monkeypatch.setattr(store.redis_service, "_client", client)
    with (
        agent_user_context("A", "test-session"),
        pytest.raises(ValueError, match="expired"),
    ):
        await store.save("A", "old-lock", 1, {}, {"status": "SUCCESS"})
    assert "GET" in client.eval.await_args.args[0]
    assert client.eval.await_args.args[1] == 3


@pytest.mark.asyncio
async def test_multi_round_runner_retains_budget_and_adds_filters(monkeypatch):
    memory = {}

    async def load(_):
        return deepcopy(memory)

    async def save(_, token, message, context, result):
        memory.update(deepcopy(context))

    monkeypatch.setattr(store, "acquire", AsyncMock(return_value="test-lock"))
    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(store, "save", save)
    monkeypatch.setattr(store, "release", AsyncMock())
    monkeypatch.setattr(runner.agent_message_service, "complete_message", AsyncMock())
    monkeypatch.setattr(runner.stream_service, "push_done", AsyncMock())
    tools = AsyncMock(return_value=wire([product()]))
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", tools)
    with agent_user_context("A", "test-session"):
        await runner.run_shopping_agent(
            {"userId": "A", "messageId": 1, "userMessage": "华为手机预算3000元"}
        )
        assert (
            memory["requirements"]["budgetMax"] == "3000"
            and memory["baseline"][0]["price"] == "1200"
        )
        tools.return_value = wire([product("P2", price=900)])
        await runner.run_shopping_agent(
            {"userId": "A", "messageId": 2, "userMessage": "有没有更便宜的？"}
        )
        assert memory["requirements"]["cheaperThan"] == "1200" and memory["ids"] == [
            "P2"
        ]
        await runner.run_shopping_agent(
            {"userId": "A", "messageId": 3, "userMessage": "我想要白色的"}
        )
        assert memory["requirements"]["attributes"]["颜色"] == "白色"
        assert memory["requirements"]["budgetMax"] == "3000"
    saved=json.loads(runner.agent_message_service.complete_message.await_args.args[3])
    assert saved['fullReport']['requirements']==memory['requirements']
    assert saved['fullReport']['recommendations'][0]['productId']=='P2'
    assert len(runner.agent_message_service.complete_message.await_args.args[3].encode()) < 512*1024


@pytest.mark.asyncio
async def test_cancelled_graph_never_invokes_mcp(monkeypatch):
    monkeypatch.setattr(graph, "is_cancelled", AsyncMock(return_value=True))
    invoke = AsyncMock()
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", invoke)
    with agent_user_context("A", "test-session"):
        state = await graph.build_shopping_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "手机"}
        )
    assert state["result"]["status"] == "CANCELLED"
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_detail_preserves_skus_in_one_java_request(monkeypatch):
    from app.services.product_service import ProductService, java_internal_client

    rows = [product(), product("P2")]
    for row in rows:
        row["query_status"] = "SUCCESS"
    query = AsyncMock(return_value={"query_status": "SUCCESS", "products": rows})
    monkeypatch.setattr(java_internal_client, "query_product_batch", query)
    result = await ProductService().get_product_details(["P1", "P2"])
    assert len(result["products"]) == 2 and result["products"][0]["skus"]
    query.assert_awaited_once_with(["P1", "P2"])


@pytest.mark.asyncio
async def test_explicit_engine_mode_never_enters_aftersales_graph(monkeypatch):
    from app.services import agent_engine

    support, shopping = AsyncMock(), AsyncMock()
    monkeypatch.setattr(agent_engine, "run_agent_graph", support)
    monkeypatch.setattr(runner, "run_shopping_agent", shopping)
    await agent_engine.AgentEngine().assistant_answer({"agentMode": "shopping"})
    shopping.assert_awaited_once()
    support.assert_not_awaited()


def test_budget_revision_multiple_brands_and_generic_keyword():
    old = understand("华为或者小米手机预算3000元")["requirements"]
    assert set(old["brands"]) == {"华为", "小米"}
    assert understand("预算改成2000元", old)["requirements"]["budgetMax"] == "2000"
    assert understand("想买咖啡")["requirements"]["keyword"] == "咖啡"
    assert understand("平板电脑")["requirements"]["category"] == "平板"


def test_foreign_or_negative_budget_not_silently_converted():
    assert understand("手机预算100美元")["clarification"]
    assert understand("手机预算-100元")["clarification"]


def test_strict_budget_and_negative_color():
    r = understand("手机价格低于1200元")["requirements"]
    assert not select([product()], r)["recommendations"]
    r = understand("不要白色的手机")["requirements"]
    assert "颜色" not in r["attributes"] and r["excludeColors"] == ["白色"]
    assert not select([product()], r)["recommendations"]


def test_minimum_battery_and_measured_longer_battery():
    r = understand("手机续航至少24小时")["requirements"]
    assert r["minBatteryHours"] == "24"
    assert not select([product()], r)["recommendations"]
    assert select([product(battery="30小时")], r)["recommendations"]
    r = understand(
        "续航更长的", understand("手机")["requirements"], [{"batteryHours": "20"}]
    )["requirements"]
    assert not select([product(battery="20小时")], r)["recommendations"]
    assert select([product(battery="21小时")], r)["recommendations"]


@pytest.mark.asyncio
async def test_detail_failure_never_falls_back_to_search_prices(monkeypatch):
    tools = AsyncMock(side_effect=[wire([product()]), RuntimeError("detail offline")])
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", tools)
    with agent_user_context("A", "test-session"):
        result = await graph.build_shopping_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "手机"}
        )
    assert (
        result["result"]["status"] == "TOOL_ERROR"
        and not result["result"]["recommendations"]
    )


@pytest.mark.asyncio
async def test_mcp_batch_wire_preserves_real_properties_price_and_stock(monkeypatch):
    from app.services.mcp_tool_router import mcp_streamable_client, mcp_tool_router

    p = product(count=None)
    remote = AsyncMock(return_value=wire([p]).to_wire())
    monkeypatch.setattr(mcp_streamable_client, "call_tool", remote)
    result = await mcp_tool_router.invoke(
        "GET_PRODUCT_DETAIL", {"productIds": ["P1"]}, "A"
    )
    assert remote.await_args.args == (
        "GET_PRODUCT_DETAIL",
        {"userId": "A", "productIds": ["P1"]},
    )
    restored = result.product_query["products"][0]
    assert restored["property_values"] == p["property_values"]
    assert (
        restored["skus"][0]["stock"] is None and restored["skus"][0]["price"] == "1200"
    )


@pytest.mark.asyncio
async def test_mismatched_batch_ids_rejected(monkeypatch):
    from app.services.product_service import ProductService, java_internal_client

    query = AsyncMock(
        return_value={
            "query_status": "SUCCESS",
            "products": [{"product_id": "OTHER", "query_status": "SUCCESS"}],
        }
    )
    monkeypatch.setattr(java_internal_client, "query_product_batch", query)
    with pytest.raises(ValueError):
        await ProductService().get_product_details(["P1"])


@pytest.mark.asyncio
async def test_invalid_agent_mode_rejected_before_other_services():
    from app.services.agent_service import AgentOrchestrator

    with pytest.raises(ValueError, match="Agent"):
        await AgentOrchestrator().send_message("A", "手机", agent_mode="unknown_agent")


@pytest.mark.asyncio
async def test_current_user_cannot_supply_another_user_to_shopping_graph():
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await graph.build_shopping_graph().ainvoke(
            {"user_id": "B", "message_id": 1, "text": "手机"}
        )


@pytest.mark.asyncio
async def test_busy_runner_does_not_use_old_results_or_call_tools(monkeypatch):
    monkeypatch.setattr(
        store, "acquire", AsyncMock(side_effect=ValueError("SHOPPING_BUSY"))
    )
    complete = AsyncMock()
    monkeypatch.setattr(runner.agent_message_service, "complete_message", complete)
    monkeypatch.setattr(runner.stream_service, "push_done", AsyncMock())
    invoke = AsyncMock()
    monkeypatch.setattr(graph.mcp_tool_router, "invoke", invoke)
    with agent_user_context("A", "test-session"):
        await runner.run_shopping_agent({"userId": "A", "messageId": 1})
    assert "上一轮" in complete.await_args.args[1]
    invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_ui_mode_http_dispatch_uses_authenticated_user(monkeypatch):
    import httpx
    from app.api.routes import agent
    from fastapi import FastAPI

    app = FastAPI()
    app.state.limiter = agent.limiter
    app.include_router(agent.router, prefix="/api")

    async def login():
        with agent_user_context("A", "test-session"):
            yield SimpleNamespace(user_id="A")

    app.dependency_overrides[agent.require_login] = login
    send = AsyncMock(return_value={"messageId": 1})
    monkeypatch.setattr(agent.agent_orchestrator, "send_message", send)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local.invalid"
    ) as client:
        response = await client.post(
            "/api/agent/sendMessage",
            data={"message": "手机", "agentMode": "shopping", "userId": "B"},
        )
    assert response.json()["data"]["messageId"] == 1
    assert send.await_args.args[0] == "A" and send.await_args.kwargs == {
        "agent_mode": "shopping"
    }


@pytest.mark.asyncio
async def test_optional_model_only_extracts_grounded_customer_requirements(monkeypatch):
    from app.shopping import extraction

    provider = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value={
                "slots": [{"field": "keyword", "value": "咖啡", "quote": "想买咖啡"}]
            }
        )
    )
    factory = SimpleNamespace(with_structured_output=lambda _, **kwargs: provider)
    monkeypatch.setattr(extraction, "create_chat_llm", lambda: factory)
    monkeypatch.setattr(
        extraction,
        "get_settings",
        lambda: SimpleNamespace(shopping_requirement_llm_enabled=True),
    )
    result = await extraction.extract("想买咖啡")
    assert (
        result["source"] == "rules+grounded_llm"
        and result["requirements"]["keyword"] == "咖啡"
    )
    assert "test-session" not in str(provider.ainvoke.await_args.args)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "output",
    [
        {"slots": [], "stock": 999},
        {"slots": [{"field": "keyword", "value": "编造商品", "quote": "不存在的引文"}]},
        {"slots": [{"field": "userId", "value": "B", "quote": "手机"}]},
    ],
)
async def test_model_cannot_supply_facts_identity_or_ungrounded_requirements(
    monkeypatch, output
):
    from app.shopping import extraction

    model = SimpleNamespace(ainvoke=AsyncMock(return_value=output))
    monkeypatch.setattr(
        extraction,
        "create_chat_llm",
        lambda: SimpleNamespace(with_structured_output=lambda _, **kwargs: model),
    )
    monkeypatch.setattr(
        extraction,
        "get_settings",
        lambda: SimpleNamespace(shopping_requirement_llm_enabled=True),
    )
    result = await extraction.extract("手机预算1000元")
    assert (
        result["source"] == "rules_fallback"
        and result["requirements"]["budgetMax"] == "1000"
    )
    assert (
        result["requirements"]["keyword"] == "手机"
        and "stock" not in result["requirements"]
    )


@pytest.mark.asyncio
async def test_disabled_model_is_not_constructed(monkeypatch):
    from app.shopping import extraction

    factory = Mock(side_effect=AssertionError("no real model"))
    monkeypatch.setattr(extraction, "create_chat_llm", factory)
    monkeypatch.setattr(
        extraction,
        "get_settings",
        lambda: SimpleNamespace(shopping_requirement_llm_enabled=False),
    )
    assert (await extraction.extract("手机"))["source"] == "rules"
    factory.assert_not_called()
