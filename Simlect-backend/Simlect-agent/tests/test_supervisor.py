"""Supervisor and real specialist graph boundaries, all dependencies mocked."""

import asyncio
import json
from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.auth.agent_context import agent_user_context, current_agent_user
from app.auth.delegation import is_delegated, read_only_delegation
from app.services.aftersales_diagnosis import diagnose
from app.services.product_facts import normalize_product
from app.shopping.requirements import understand
from app.shopping.selection import select
from app.supervisor import adapters, graph, runner, store
from app.supervisor.aggregation import aggregate, display
from app.supervisor.contracts import AgentResult, Task, checked_result, fingerprint
from app.supervisor.routing import plan


def policy():
    return {
        "status": "SUCCESS",
        "hits": [
            {
                "documentId": "TEST-ONLY",
                "chunkId": "TEST-CHUNK",
                "revision": 2,
                "documentName": "TEST ONLY",
                "section": "测试章节",
                "source": "fixture://not-a-real-policy",
                "text": "TEST ONLY：样例不构成正式售后政策。",
                "score": 0.9,
                "page": 1,
            }
        ],
    }


def order():
    return {
        "schemaVersion": 1,
        "kind": "order",
        "orderId": "O-A",
        "queryStatus": "SUCCESS",
        "source": "java.order.agent.order",
        "data": {
            "orderId": "O-A",
            "ownerVerified": True,
            "orderStatus": 6,
            "orderTime": "2026-11-01 10:00:00",
            "items": [],
        },
    }


def diagnosis():
    return diagnose(
        "REFUND_PROGRESS",
        "O-A",
        order(),
        {"queryStatus": "SKIPPED"},
        policy(),
        now=datetime(2026, 11, 2, 8, tzinfo=UTC),
    )


def after():
    return AgentResult(
        agent="aftersales", status="SUCCESS", data={"diagnosis": diagnosis()}
    )


def shopping():
    p = normalize_product(
        {
            "product_id": "P1",
            "product_name": "TEST ONLY 手机",
            "category_name": "手机",
            "status": 1,
            "min_price": "1299.90",
            "max_price": "1299.90",
            "sku_complete": True,
            "product_observed_at": "2026-11-02T10:00:00Z",
            "property_values": [],
            "skus": [
                {
                    "sku_id": "P1_A",
                    "sku_name": "白色",
                    "price": "1299.90",
                    "stock": 3,
                    "stock_query_status": "SUCCESS",
                    "specifications": [{"name": "颜色", "value": "白色"}],
                }
            ],
        }
    )
    data = {
        "schemaVersion": 1,
        "agentType": "shopping",
        "status": "SUCCESS",
        "requirements": understand("手机")["requirements"],
        "toolsCalled": ["SEARCH_PRODUCTS", "GET_PRODUCT_DETAIL"],
        "queryTime": "2026-11-02T10:00:00Z",
        "executionAllowed": False,
        **select([p], understand("手机")["requirements"]),
    }
    return AgentResult(agent="shopping", status="SUCCESS", data={"shopping": data})


@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    monkeypatch.setattr(graph, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(runner, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(graph.stream_service, "push_agent_status", AsyncMock())
    monkeypatch.setattr(
        graph,
        "get_settings",
        lambda: SimpleNamespace(supervisor_agent_timeout_seconds=1),
    )


@pytest.mark.parametrize(
    ("text", "agents"),
    [
        ("售后政策是什么", ["aftersales"]),
        ("订单 O-A 超时未发货", ["aftersales"]),
        ("物流一直不更新", ["aftersales"]),
        ("推荐手机", ["shopping"]),
        ("预算3000买手机", ["shopping"]),
        ("把刚才三个商品对比一下", ["shopping"]),
        ("我手机坏了", ["aftersales"]),
        ("给我推荐售后处理方案", ["aftersales"]),
        ("退货政策，另外推荐手机", ["aftersales", "shopping"]),
        ("订单 O-A 退款进度异常，顺便推荐手机", ["aftersales", "shopping"]),
        ("帮我看看", []),
        ("退款后用退的钱买手机", []),
    ],
)
def test_routing(text, agents):
    assert [t["agent"] for t in plan(text)["tasks"]] == agents


def test_ambiguous_followup_uses_only_clear_last_agent():
    assert plan("继续", "shopping")["tasks"] == [{"agent": "shopping", "text": "继续"}]
    assert plan("继续", "aftersales")["tasks"] == [
        {"agent": "aftersales", "text": "继续"}
    ]
    assert plan("继续")["tasks"] == []
    assert plan("退款政策，另外推荐手机")["reason"] == "COMPOSITE"


@pytest.mark.asyncio
async def test_single_route_never_invokes_both_agents(monkeypatch):
    call = AsyncMock(return_value=shopping())
    monkeypatch.setattr(adapters, "invoke", call)
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "推荐手机"}
        )
    call.assert_awaited_once_with({"agent": "shopping", "text": "推荐手机"}, "A", 1)
    assert (
        state["report"]["status"] == "COMPLETE"
        and not state["report"]["executionAllowed"]
    )


@pytest.mark.asyncio
async def test_unclear_turn_invokes_no_specialist(monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(adapters, "invoke", call)
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "帮我看看"}
        )
    assert state["report"]["status"] == "NEEDS_CLARIFICATION"
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_composite_is_split_sequentially_and_preserves_facts(monkeypatch):
    calls = []
    original = {"aftersales": after(), "shopping": shopping()}

    async def invoke(task, user, message):
        calls.append(task)
        return original[task["agent"]]

    monkeypatch.setattr(adapters, "invoke", invoke)
    before = deepcopy({k: v.data for k, v in original.items()})
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {
                "user_id": "A",
                "message_id": 1,
                "text": "订单 O-A 退款进度异常，另外推荐手机",
            }
        )
    assert [c["agent"] for c in calls] == ["aftersales", "shopping"]
    assert "订单" not in calls[1]["text"] and "推荐" not in calls[0]["text"]
    report = state["report"]
    for name, data in before.items():
        assert report["results"][name]["data"] == data
        assert report["results"][name]["fingerprint"] == fingerprint(data)
    payload = display(report)
    assert "1299.90" in payload["intro"] and "库存3" in payload["intro"]
    assert (
        "fixture://not-a-real-policy" in payload["intro"]
        and "版本：2" in payload["intro"]
    )
    assert (
        report["results"]["aftersales"]["data"]["diagnosis"]["approvalRequired"] is True
    )


@pytest.mark.asyncio
async def test_one_failed_agent_does_not_hide_other_success(monkeypatch):
    async def invoke(task, *_):
        if task["agent"] == "aftersales":
            raise RuntimeError("PRIVATE_PROVIDER_SECRET")
        return shopping()

    monkeypatch.setattr(adapters, "invoke", invoke)
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "退款政策，另外推荐手机"}
        )
    report = state["report"]
    assert (
        report["status"] == "PARTIAL"
        and report["results"]["shopping"]["status"] == "SUCCESS"
    )
    assert "PRIVATE_PROVIDER_SECRET" not in json.dumps(report)


@pytest.mark.asyncio
async def test_timeout_cancels_child_and_continues_next_agent(monkeypatch):
    stopped = []

    async def invoke(task, *_):
        if task["agent"] == "aftersales":
            try:
                await asyncio.sleep(5)
            finally:
                stopped.append(True)
        return shopping()

    monkeypatch.setattr(adapters, "invoke", invoke)
    monkeypatch.setattr(
        graph,
        "get_settings",
        lambda: SimpleNamespace(supervisor_agent_timeout_seconds=0.01),
    )
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "退款政策，另外推荐手机"}
        )
    assert stopped and state["report"]["results"]["aftersales"]["status"] == "TIMEOUT"
    assert state["report"]["status"] == "PARTIAL"


@pytest.mark.asyncio
async def test_invalid_child_identity_or_execution_fields_are_rejected(monkeypatch):
    value = shopping().model_dump()
    value["userId"] = "B"
    monkeypatch.setattr(adapters, "invoke", AsyncMock(return_value=value))
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "推荐手机"}
        )
    assert state["report"]["results"]["shopping"]["status"] == "INVALID_RESULT"
    assert not state["report"]["results"]["shopping"]["data"]


@pytest.mark.parametrize(
    "change",
    ["price", "zero", "unknown", "wrongAgent", "write", "private", "missingTool"],
)
def test_contract_rejects_tampered_product_facts(change):
    value = shopping().model_dump()
    p = value["data"]["shopping"]["recommendations"][0]
    if change == "price":
        p["price"]["min"] = "0"
    elif change == "zero":
        p["eligibleSkus"][0]["stock"] = 0
    elif change == "unknown":
        p["eligibleSkus"][0]["stock"] = None
    elif change == "wrongAgent":
        value["agent"] = "aftersales"
    elif change == "write":
        value["executionAllowed"] = True
    elif change == "private":
        value["data"]["token"] = "SECRET"
    else:
        value["data"]["shopping"]["toolsCalled"] = []
    with pytest.raises((ValueError, TypeError, KeyError)):
        checked_result(value, "shopping")


@pytest.mark.parametrize("change", ["source", "owner", "approval", "execute"])
def test_contract_rejects_missing_policy_identity_or_human_review(change):
    value = after().model_dump()
    d = value["data"]["diagnosis"]
    if change == "source":
        d["policyEvidence"]["hits"][0].pop("source")
    elif change == "owner":
        d["orderFacts"]["data"]["ownerVerified"] = False
    elif change == "approval":
        d["approvalRequired"] = False
    else:
        d["recommendedActions"][0]["executionAllowed"] = True
    with pytest.raises(ValueError):
        checked_result(value, "aftersales")


def test_task_cannot_override_user_or_choose_a_tool():
    for extra in ({"userId": "B"}, {"tool": "REFUND"}, {"executionAllowed": True}):
        with pytest.raises(ValueError):
            Task.model_validate({"agent": "shopping", "text": "手机", **extra})


@pytest.mark.asyncio
async def test_user_identity_is_checked_before_any_dispatch(monkeypatch):
    call = AsyncMock()
    monkeypatch.setattr(adapters, "invoke", call)
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await graph.build_supervisor_graph().ainvoke(
            {"user_id": "B", "message_id": 1, "text": "推荐手机"}
        )
    call.assert_not_awaited()


@pytest.mark.asyncio
async def test_multi_user_concurrent_contextvars_do_not_leak(monkeypatch):
    async def invoke(task, user, message):
        await asyncio.sleep(0)
        assert current_agent_user().user_id == user
        return shopping()

    monkeypatch.setattr(adapters, "invoke", invoke)

    async def run(user):
        with agent_user_context(user, "test-session-" + user):
            return await graph.build_supervisor_graph().ainvoke(
                {"user_id": user, "message_id": 1, "text": "推荐手机"}
            )

    assert all(
        s["report"]["status"] == "COMPLETE"
        for s in await asyncio.gather(run("A"), run("B"))
    )
    assert current_agent_user() is None


@pytest.mark.asyncio
async def test_real_aftersales_graph_collects_only_no_message_or_auto_case(monkeypatch):
    from app.graph import aftersales_nodes, case_nodes
    from app.graph import nodes as common
    from app.services import agent_runtime as rt

    adapters.aftersales_graph.cache_clear()
    monkeypatch.setattr(common.rt, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(aftersales_nodes, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        case_nodes,
        "get_settings",
        lambda: SimpleNamespace(aftersales_cases_auto_create=True),
    )
    fetch = AsyncMock(return_value=order())
    monkeypatch.setattr(aftersales_nodes, "fetch_facts", fetch)
    monkeypatch.setattr(
        aftersales_nodes.rag_retriever,
        "search_policy",
        AsyncMock(return_value=policy()),
    )
    monkeypatch.setattr(store, "hint", AsyncMock(return_value={}))
    saved = AsyncMock()
    monkeypatch.setattr(store, "save_hint", saved)
    create = AsyncMock(side_effect=AssertionError("no automatic case/approval"))
    monkeypatch.setattr(case_nodes, "create_case", create)
    finish, done, bind, clear = AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(common.agent_message_service, "complete_message", finish)
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(common.redis_service, "bind_message_id", bind)
    monkeypatch.setattr(common.redis_service, "clear_bound_message_id", clear)
    with agent_user_context("A", "test-session"):
        response = await adapters.invoke(
            {"agent": "aftersales", "text": "订单 O-A 退款进度异常"}, "A", 1
        )
    assert response.data["diagnosis"]["caseWorkflow"]["status"] == "ON_REQUEST"
    fetch.assert_awaited_once_with("order", "A", "O-A")
    for call in (create, finish, done, bind, clear):
        call.assert_not_awaited()
    assert not is_delegated()


@pytest.mark.asyncio
async def test_aftersales_followup_requeries_verified_order_not_shopping_context(
    monkeypatch,
):
    fake = SimpleNamespace(
        ainvoke=AsyncMock(return_value={"diagnosis_report": diagnosis()})
    )
    monkeypatch.setattr(adapters, "aftersales_graph", lambda: fake)
    monkeypatch.setattr(
        store,
        "hint",
        AsyncMock(
            return_value={"kind": "order", "orderId": "O-A", "budget": "untrusted"}
        ),
    )
    monkeypatch.setattr(store, "save_hint", AsyncMock())
    from app.services.java_internal_client import java_internal_client
    read_progress=AsyncMock(return_value=[])
    monkeypatch.setattr(java_internal_client,'post_json',read_progress)
    with agent_user_context("A", "test-session"):
        await adapters.invoke(
            {"agent": "aftersales", "text": "这笔订单退款进度呢"}, "A", 1
        )
        read_progress.assert_awaited_once_with('/api/order/aftersalesCase/list',{'orderId':'O-A'},strict=True)
        assert "untrusted" not in str(read_progress.await_args)
        fake.ainvoke.assert_not_awaited()
        with pytest.raises(ValueError, match="different order"):
            await adapters.invoke(
                {"agent": "aftersales", "text": "另一个订单有问题"}, "A", 2
            )
        assert "O-A" not in fake.ainvoke.await_args.args[0]["user_text"]


@pytest.mark.asyncio
async def test_shopping_adapter_reuses_own_context_and_suppresses_publish(monkeypatch):
    async def run(message, *, collect_only):
        assert collect_only and is_delegated()
        assert message == {"userId": "A", "messageId": 1, "userMessage": "更便宜的手机"}
        return shopping().data["shopping"]

    monkeypatch.setattr(adapters, "run_shopping_agent", run)
    with agent_user_context("A", "test-session"):
        value = await adapters.invoke(
            {"agent": "shopping", "text": "更便宜的手机"}, "A", 1
        )
    assert value.status == "SUCCESS" and not is_delegated()


@pytest.mark.asyncio
async def test_write_tools_bridge_and_confirmation_blocked_during_delegation(
    monkeypatch,
):
    from app.services.action_execute_service import JavaBridge, action_execute_service
    from app.services.mcp_streamable_client import mcp_streamable_client
    from app.services.mcp_tool_router import mcp_tool_router

    remote = AsyncMock()
    monkeypatch.setattr(mcp_streamable_client, "_session", remote)
    with agent_user_context("A", "test-session"), read_only_delegation():
        value = await mcp_tool_router.invoke(
            "PROPOSE_REFUND", {"orderItemId": "O-A_1"}, "A"
        )
        assert "不允许" in value.content
        with pytest.raises(ValueError):
            await mcp_streamable_client.call_tool("PROPOSE_CONFIRM_RECEIPT", {})
        for action in ("REFUND", "CONFIRM_RECEIPT", "PRODUCT_REVIEW"):
            with pytest.raises(ValueError):
                await action_execute_service.execute(
                    {"actionType": action}, "test-session"
                )
        with pytest.raises(ValueError):
            await JavaBridge()._post_form("test-session", "/order/confirmOrder", {})
    remote.assert_not_awaited()


@pytest.mark.asyncio
async def test_delegated_stream_messages_never_reach_customer(monkeypatch):
    from app.services.stream_service import redis_service, stream_service

    publish = AsyncMock()
    monkeypatch.setattr(redis_service, "publish_ws", publish)
    with read_only_delegation():
        await stream_service.push_chunk("A", 1, "UNVERIFIED PRICE")
        await stream_service.push_done("A", 1, "CHILD FINAL")
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_routing_memory_result_and_aftersales_hint_have_distinct_user_keys(
    monkeypatch,
):
    client = AsyncMock()
    client.get.return_value = None
    monkeypatch.setattr(store.redis_service, "_client", client)
    with agent_user_context("A", "test-session"):
        await store.load("A")
        await store.result("A", 1)
        await store.hint("A")
        assert [c.args[0] for c in client.get.await_args_list] == [
            "mall:agent:supervisor:A:routing",
            "mall:agent:supervisor:A:result:1",
            "mall:agent:aftersales:supervisor:A",
        ]
        with pytest.raises(ValueError):
            await store.result("B", 1)


@pytest.mark.asyncio
async def test_lease_expiry_cannot_overwrite_newer_routing(monkeypatch):
    client = AsyncMock()
    client.eval.return_value = 0
    monkeypatch.setattr(store.redis_service, "_client", client)
    with (
        agent_user_context("A", "test-session"),
        pytest.raises(ValueError, match="expired"),
    ):
        await store.save("A", "old", 1, {"lastRoute": "shopping"}, {})


@pytest.mark.asyncio
async def test_runner_one_final_message_and_two_agent_switches(monkeypatch):
    context = {}
    reports = []

    async def load(_):
        return deepcopy(context)

    async def save(_, token, message, meta, report):
        context.update(meta)
        reports.append(deepcopy(report))

    monkeypatch.setattr(store, "acquire", AsyncMock(return_value="lock"))
    monkeypatch.setattr(store, "load", load)
    monkeypatch.setattr(store, "save", save)
    monkeypatch.setattr(store, "release", AsyncMock())

    async def invoke(task, *_):
        return shopping() if task["agent"] == "shopping" else after()

    monkeypatch.setattr(adapters, "invoke", invoke)
    complete, done = AsyncMock(), AsyncMock()
    monkeypatch.setattr(runner.agent_message_service, "complete_message", complete)
    monkeypatch.setattr(runner.stream_service, "push_done", done)
    with agent_user_context("A", "test-session"):
        for i, text in enumerate(("推荐手机", "订单 O-A 退款进度异常", "继续"), 1):
            await runner.run_supervisor(
                {"userId": "A", "messageId": i, "userMessage": text}
            )
    assert context == {"lastRoute": "aftersales"}
    assert len(reports) == 3 and complete.await_count == 3 and done.await_count == 3
    assert reports[-1]["plan"]["tasks"][0]["agent"] == "aftersales"
    assert all(json.loads(c.args[3])['fullReport']==r for c,r in zip(complete.await_args_list,reports))
    assert all(len(c.args[3].encode()) < 512*1024 for c in complete.await_args_list)
    assert json.loads(complete.await_args.args[1])["type"] == "SUPERVISOR_RESULT"


@pytest.mark.asyncio
async def test_case_creation_from_own_completed_supervisor_diagnosis(monkeypatch):
    from app.services import aftersales_case_service as cases

    cur = AsyncMock()
    cur.fetchone.return_value = {"biz_data": json.dumps({"agentType": "supervisor"})}
    cm = Mock()
    cm.__aenter__ = AsyncMock(return_value=cur)
    cm.__aexit__ = AsyncMock()
    monkeypatch.setattr(cases, "acquire", lambda: cm)
    monkeypatch.setattr(
        store,
        "result",
        AsyncMock(
            return_value={
                "messageId": 1,
                "results": {"aftersales": after().model_dump()},
            }
        ),
    )
    create = AsyncMock(return_value={"caseId": "TEST ONLY"})
    monkeypatch.setattr(cases, "create_case", create)
    with agent_user_context("A", "test-session"):
        assert (await cases.create_from_message("A", 1))["caseId"] == "TEST ONLY"
    assert cur.execute.await_args.args[1] == (1, "A", 2)
    create.assert_awaited_once_with("A", 1, diagnosis())


@pytest.mark.asyncio
async def test_original_three_engine_modes_remain_separate(monkeypatch):
    from app.services import agent_engine
    from app.shopping import runner as shopping_runner

    support, shop, supervisor = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(agent_engine, "run_agent_graph", support)
    monkeypatch.setattr(shopping_runner, "run_shopping_agent", shop)
    monkeypatch.setattr(runner, "run_supervisor", supervisor)
    engine = agent_engine.AgentEngine()
    for mode in ("support", "shopping", "supervisor"):
        await engine.assistant_answer({"agentMode": mode})
    for call in (support, shop, supervisor):
        call.assert_awaited_once()


@pytest.mark.parametrize("unknown", ["price", "stock"])
def test_unknown_product_values_are_preserved_not_zeroed(unknown):
    response = shopping()
    p = response.data["shopping"]["recommendations"][0]
    if unknown == "price":
        p["price"] = {"min": None, "max": None, "complete": False}
        p["eligibleSkus"][0]["price"] = None
        p["skus"][0]["price"] = None
    else:
        p["eligibleSkus"][0]["stock"] = None
        p["eligibleSkus"][0]["stock_query_status"] = "UNAVAILABLE"
        p["skus"][0]["stock"] = None
        p["skus"][0]["stock_query_status"] = "UNAVAILABLE"
        p["availability"] = "UNKNOWN"
    expected = deepcopy(response.data)
    value = aggregate(plan("推荐手机"), {"shopping": response.model_dump()})
    assert value["results"]["shopping"]["data"] == expected
    assert ("价格未知" if unknown == "price" else "库存待确认") in display(value)[
        "intro"
    ]


def test_no_policy_match_remains_uncertain_no_made_up_rules():
    d = diagnose(
        "REFUND_PROGRESS",
        "O-A",
        order(),
        {"queryStatus": "SKIPPED"},
        {"status": "NO_MATCH", "hits": []},
    )
    result = aggregate(
        plan("订单 O-A 退款进度异常"),
        {
            "aftersales": AgentResult(
                agent="aftersales", status="SUCCESS", data={"diagnosis": d}
            ).model_dump()
        },
    )
    assert any(
        v["reason"] == "POLICY_NO_MATCH" for v in result["summary"]["uncertainty"]
    )
    assert "无法确定适用规则" in display(result)["intro"]
    assert not any("documentName" in e for e in result["evidenceSources"])


@pytest.mark.asyncio
async def test_supervisor_enforces_read_only_even_for_a_bad_adapter(monkeypatch):
    from app.services.action_execute_service import action_execute_service

    async def bad_adapter(*_):
        assert is_delegated()
        await action_execute_service.execute(
            {"actionType": "CONFIRM_RECEIPT"}, "test-session"
        )
        raise AssertionError("must not reach here")

    monkeypatch.setattr(adapters, "invoke", bad_adapter)
    with agent_user_context("A", "test-session"):
        state = await graph.build_supervisor_graph().ainvoke(
            {"user_id": "A", "message_id": 1, "text": "订单 O-A 退款进度异常"}
        )
    assert state["report"]["results"]["aftersales"]["status"] == "ERROR"
    assert not is_delegated()


@pytest.mark.asyncio
async def test_child_cannot_write_original_message_or_create_another_message(
    monkeypatch,
):
    from app.services import message_service
    from app.services.message_service import agent_message_service

    database = Mock(side_effect=AssertionError("no child SQL"))
    monkeypatch.setattr(message_service, "acquire", database)
    with read_only_delegation():
        await agent_message_service.complete_message(1, "untrusted child final")
        await agent_message_service.interrupt_message("A", 1, "child partial")
        with pytest.raises(ValueError):
            await agent_message_service.save_user_message("A", "nested user")
    database.assert_not_called()


@pytest.mark.asyncio
async def test_real_policy_graph_preserves_citation_without_model_or_publish(
    monkeypatch,
):
    from app.graph import nodes as common

    adapters.aftersales_graph.cache_clear()
    monkeypatch.setattr(common.rt, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        common.rag_retriever, "search_policy", AsyncMock(return_value=policy())
    )
    model = Mock(side_effect=AssertionError("policy evidence needs no model"))
    monkeypatch.setattr(common.rt, "bind_agent_llm", model)
    monkeypatch.setattr(store, "hint", AsyncMock(return_value={}))
    monkeypatch.setattr(store, "save_hint", AsyncMock())
    bind, clear = AsyncMock(), AsyncMock()
    monkeypatch.setattr(common.redis_service, "bind_message_id", bind)
    monkeypatch.setattr(common.redis_service, "clear_bound_message_id", clear)
    with agent_user_context("A", "test-session"):
        response = await adapters.invoke(
            {"agent": "aftersales", "text": "售后政策是什么"}, "A", 1
        )
    assert response.data["policy"] == policy()
    model.assert_not_called()
    bind.assert_not_awaited()
    clear.assert_not_awaited()


@pytest.mark.asyncio
async def test_routing_context_discards_specialist_fields(monkeypatch):
    client = AsyncMock()
    client.get.return_value = json.dumps(
        {"lastRoute": "shopping", "orderId": "PRIVATE_ORDER", "budget": 999}
    )
    monkeypatch.setattr(store.redis_service, "_client", client)
    with agent_user_context("A", "test-session"):
        assert await store.load("A") == {"lastRoute": "shopping"}


@pytest.mark.asyncio
async def test_case_creation_requires_nonexpired_owned_supervisor_evidence(monkeypatch):
    from app.services import aftersales_case_service as cases

    cur = AsyncMock()
    cur.fetchone.return_value = {"biz_data": json.dumps({"agentType": "supervisor"})}
    cm = Mock()
    cm.__aenter__ = AsyncMock(return_value=cur)
    cm.__aexit__ = AsyncMock()
    monkeypatch.setattr(cases, "acquire", lambda: cm)
    monkeypatch.setattr(store, "result", AsyncMock(return_value=None))
    create = AsyncMock()
    monkeypatch.setattr(cases, "create_case", create)
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await cases.create_from_message("A", 1)
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_http_supervisor_mode_and_report_use_authenticated_identity(monkeypatch):
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
    read = AsyncMock(return_value={"status": "COMPLETE"})
    monkeypatch.setattr(agent.agent_orchestrator, "send_message", send)
    monkeypatch.setattr(store, "result", read)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local.invalid"
    ) as client:
        response = await client.post(
            "/api/agent/sendMessage",
            headers={"token": "unique-supervisor-test"},
            data={"message": "推荐手机", "agentMode": "supervisor", "userId": "B"},
        )
        assert response.json()["data"]["messageId"] == 1
        assert (
            await client.post(
                "/api/agent/supervisor/result", data={"messageId": "1", "userId": "B"}
            )
        ).json()["data"]["status"] == "COMPLETE"
    assert send.await_args.args[0] == "A" and send.await_args.kwargs == {
        "agent_mode": "supervisor"
    }
    read.assert_awaited_once_with("A", 1)
