"""Isolated aftersales facts and real LangGraph tests; no business writes/models."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from app.auth.agent_context import agent_user_context
from app.graph import aftersales_nodes as nodes
from app.services import aftersales_diagnosis as svc
from app.services import aftersales_facts as facts
from app.services.tool_invoke_result import ToolInvokeResult, parse_tool_wire

NOW = datetime(2026, 11, 2, 8, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_live_cancel_store(monkeypatch):
    monkeypatch.setattr(nodes, "is_cancelled", AsyncMock(return_value=False))


def order(status=2):
    return {
        "schemaVersion": 1,
        "kind": "order",
        "orderId": "O-A",
        "queryStatus": "SUCCESS",
        "source": "java.order.agent.order",
        "queriedAt": NOW.isoformat(),
        "data": {
            "orderId": "O-A",
            "ownerVerified": True,
            "orderStatus": status,
            "orderTime": "2026-10-20 12:00:00",
            "items": [],
            "hasPaymentReference": False,
        },
    }


def logistics(status=2):
    return {
        "schemaVersion": 1,
        "kind": "logistics",
        "orderId": "O-A",
        "queryStatus": "SUCCESS",
        "source": "java.order.agent.logistics",
        "queriedAt": NOW.isoformat(),
        "data": {
            "orderId": "O-A",
            "logisticsStatus": status,
            "records": [{"recordTime": "2026-10-25 12:00:00"}],
        },
    }


def policy(status="SUCCESS"):
    return {
        "status": status,
        "hits": [
            {
                "documentId": "TEST-ONLY",
                "revision": 2,
                "documentName": "TEST ONLY",
                "section": "测试章节",
                "page": 1,
                "source": "fixture://test-only",
                "score": 0.9,
                "text": "TEST ONLY 测试样例，不构成正式售后政策。",
            }
        ]
        if status == "SUCCESS"
        else [],
    }


def report(case="LOGISTICS_STAGNATION", of=None, lf=None, pf=None):
    return svc.diagnose(
        case,
        "O-A",
        of if of is not None else order(),
        lf if lf is not None else logistics(),
        pf if pf is not None else policy(),
        now=NOW,
    )


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("订单 O-A 物流长期不更新", "LOGISTICS_STAGNATION"),
        ("订单 O-A 还没发货", "UNSHIPPED_ORDER"),
        ("订单 O-A 支付异常", "PAYMENT_ANOMALY"),
        ("订单 O-A 退款进度异常", "REFUND_PROGRESS"),
        ("订单 O-A 商品质量问题", "PRODUCT_QUALITY"),
        ("订单 O-A 售后咨询", "AFTERSALES_CONSULT"),
        ("退货政策是什么", None),
        ("搜索手机库存", None),
        ("我要退款", "AFTERSALES_CONSULT"),
        ("我的订单", "AFTERSALES_CONSULT"),
    ],
)
def test_intent_boundaries(text, kind):
    assert svc.identify_case(text) == kind


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("订单 O-A", "O-A"),
        ("orderId: O-A userId=other", "O-A"),
        ("订单 O-A 和订单 O-B", None),
        ("订单物流异常", None),
        ("202611020000123456ABCDEFGH_1 物流停滞", "202611020000123456ABCDEFGH"),
    ],
)
def test_order_identifier_clarification(text, expected):
    assert svc.extract_order_id(text) == expected


def test_normal_consultation_is_not_a_guarantee():
    result = report("AFTERSALES_CONSULT")
    assert result["diagnosis"]["status"] == "NOT_OBSERVED"
    assert result["diagnosis"]["anomalyDetected"] is False
    assert not result["executionAllowed"]
    assert "未发现可确认" in svc.render_diagnosis(result)


def test_long_stagnation_does_not_invent_policy_deadline():
    result = report()
    assert result["diagnosis"]["status"] == "UNCERTAIN"
    assert result["diagnosis"]["anomalyDetected"] is None
    text = svc.render_diagnosis(result)
    assert "196.0 小时" in text and "无法认定违反承诺" in text
    assert result["approvalRequired"]


def test_explicit_carrier_anomaly_is_observed():
    result = report(lf=logistics(5))
    assert result["diagnosis"]["status"] == "CONFIRMED"
    assert result["diagnosis"]["anomalyDetected"] is True
    assert "具体原因尚待" in svc.render_diagnosis(result)


def test_unshipped_is_not_unconditionally_overdue():
    result = report("UNSHIPPED_ORDER", of=order(1), lf={"queryStatus": "NO_RECORD"})
    assert result["diagnosis"]["status"] == "UNCERTAIN"
    assert "不能确认已超时" in svc.render_diagnosis(result)


def test_refund_progress_does_not_claim_receipt_or_execute():
    result = report("REFUND_PROGRESS", of=order(6))
    text = svc.render_diagnosis(result)
    assert "不代表银行卡/账户已到账" in text
    assert "本 Agent 不执行退款" in text
    assert result["approvalRequired"] and not result["executionAllowed"]
    assert all(not a["executionAllowed"] for a in result["recommendedActions"])


def test_payment_reference_is_not_payment_confirmation():
    of = order(0)
    of["data"]["hasPaymentReference"] = True
    result = report("PAYMENT_ANOMALY", of=of, lf={"queryStatus": "SKIPPED"})
    assert result["diagnosis"]["status"] == "UNCERTAIN"
    assert "未查询支付流水" in svc.render_diagnosis(result)


def test_conflicting_evidence_requires_review():
    result = report(of=order(1))
    assert result["diagnosis"]["status"] == "CONFLICT"
    assert result["confidence"]["level"] == "LOW" and result["approvalRequired"]


def test_future_timestamp_conflict():
    lf = logistics()
    lf["data"]["records"] = [{"recordTime": "2099-01-01"}]
    assert report(lf=lf)["diagnosis"]["status"] == "CONFLICT"


@pytest.mark.parametrize(
    "status",
    [
        "NO_MATCH",
        "LOW_RELEVANCE",
        "EMBEDDING_FAILED",
        "ES_UNAVAILABLE",
        "CATALOG_UNAVAILABLE",
        "RETRIEVAL_ERROR",
    ],
)
def test_policy_failure_states_are_distinct(status):
    result = report(pf=policy(status))
    assert result["policyEvidence"]["status"] == status
    assert not any(s["type"] == "policy" for s in result["evidenceSources"])
    assert "退款资格结论" in svc.render_diagnosis(result)


def test_policy_source_and_revision_retained():
    result = report()
    source = result["evidenceSources"][0]
    assert source["revision"] == 2 and source["section"] == "测试章节"
    assert source["source"] == "fixture://test-only"


@pytest.mark.parametrize(
    "status",
    ["MISSING_ORDER_ID", "UNAUTHORIZED", "NOT_FOUND_OR_FORBIDDEN", "SERVICE_ERROR"],
)
def test_missing_or_failed_order_not_inferred(status):
    result = report(
        of={"queryStatus": status},
        lf={"queryStatus": "SKIPPED"},
        pf={"status": "SKIPPED"},
    )
    assert result["diagnosis"]["status"] == "UNCERTAIN"
    assert not result["executionAllowed"] and result["orderFacts"].get("data") is None


@pytest.mark.asyncio
async def test_real_projection_removes_private_details(monkeypatch):
    read = AsyncMock(
        return_value={
            "order_id": "O-A",
            "user_id": "A",
            "order_status": 2,
            "receiver_address": "PRIVATE",
            "pay_order_id": "PRIVATE",
            "items": [],
        }
    )
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with agent_user_context("A", "test-session"):
        result = await facts.read_order_facts("A", "O-A")
    assert result.business_facts["data"]["ownerVerified"]
    assert "PRIVATE" not in result.to_wire() and "test-session" not in result.to_wire()
    restored = parse_tool_wire(result.to_wire())
    assert restored.business_facts == result.business_facts


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["B", None])
async def test_projection_rejects_wrong_or_missing_owner(monkeypatch, owner):
    read = AsyncMock(return_value={"order_id": "O-A", "user_id": owner})
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with agent_user_context("A", "test-session"):
        result = await facts.read_order_facts("A", "O-A")
    assert result.business_facts["queryStatus"] == "NOT_FOUND_OR_FORBIDDEN"
    assert result.business_facts["data"] is None


@pytest.mark.asyncio
async def test_projection_not_found_and_error_distinguished(monkeypatch):
    read = AsyncMock(return_value=None)
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with agent_user_context("A", "test-session"):
        assert (await facts.read_order_facts("A", "O-A")).business_facts[
            "queryStatus"
        ] == "NOT_FOUND_OR_FORBIDDEN"
        read.side_effect = RuntimeError("test provider failure")
        assert (await facts.read_order_facts("A", "O-A")).business_facts[
            "queryStatus"
        ] == "SERVICE_ERROR"


@pytest.mark.asyncio
async def test_forged_user_rejected_before_mcp_or_java(monkeypatch):
    invoke, read = AsyncMock(), AsyncMock()
    monkeypatch.setattr(svc.mcp_tool_router, "invoke", invoke)
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with agent_user_context("A", "test-session"):
        assert (await svc.fetch_facts("order", "B", "O-A"))[
            "queryStatus"
        ] == "UNAUTHORIZED"
        assert (await facts.read_order_facts("B", "O-A")).business_facts[
            "queryStatus"
        ] == "UNAUTHORIZED"
    invoke.assert_not_awaited()
    read.assert_not_awaited()


@pytest.mark.asyncio
async def test_router_overrides_forged_argument_and_preserves_facts(monkeypatch):
    from app.services.mcp_tool_router import mcp_streamable_client

    call = AsyncMock(
        return_value=ToolInvokeResult(content="facts", business_facts=order()).to_wire()
    )
    monkeypatch.setattr(mcp_streamable_client, "call_tool", call)
    with agent_user_context("A", "test-session"):
        result = await svc.mcp_tool_router.invoke(
            "QUERY_ORDERS",
            {"userId": "B", "user_id": "B", "orderId": "O-A", "includeFacts": True},
            "A",
        )
    assert call.await_args.args == (
        "QUERY_ORDERS",
        {"userId": "A", "orderId": "O-A", "includeFacts": True},
    )
    assert result.business_facts == order()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        ToolInvokeResult(content="成功"),
        ToolInvokeResult(content="", business_facts={"schemaVersion": 0}),
        RuntimeError("offline"),
    ],
)
async def test_unstructured_old_or_failed_mcp_never_counts_as_fact(
    monkeypatch, response
):
    invoke = (
        AsyncMock(side_effect=response)
        if isinstance(response, Exception)
        else AsyncMock(return_value=response)
    )
    monkeypatch.setattr(svc.mcp_tool_router, "invoke", invoke)
    with agent_user_context("A", "test-session"):
        result = await svc.fetch_facts("order", "A", "O-A")
    assert result["queryStatus"] == "SERVICE_ERROR" and result["data"] is None


@pytest.mark.asyncio
async def test_logistics_projection_and_failure(monkeypatch):
    read = AsyncMock(
        return_value={
            "order_id": "O-A",
            "logistics_status": 5,
            "receiver_phone": "PRIVATE",
            "record_list": [{"record_time": "2026-11-01", "record_address": "PRIVATE"}],
        }
    )
    monkeypatch.setattr(facts.java_internal_client, "get_logistics", read)
    with agent_user_context("A", "test-session"):
        result = await facts.read_logistics_facts("A", "O-A")
        assert (
            result.business_facts["queryStatus"] == "SUCCESS"
            and "PRIVATE" not in result.to_wire()
        )
        read.side_effect = RuntimeError("test outage")
        assert (await facts.read_logistics_facts("A", "O-A")).business_facts[
            "queryStatus"
        ] == "SERVICE_ERROR"


@pytest.mark.asyncio
async def test_missing_order_skips_logistics_and_embedding(monkeypatch):
    invoke, search = AsyncMock(), AsyncMock()
    monkeypatch.setattr(svc.mcp_tool_router, "invoke", invoke)
    monkeypatch.setattr(nodes.rag_retriever, "search_policy", search)
    state = {
        "user_id": "A",
        "message_id": 1,
        "diagnosis_order_id": None,
        "diagnosis_case": "LOGISTICS_STAGNATION",
    }
    with agent_user_context("A", "test-session"):
        state.update(await nodes.diagnosis_order_node(state))
        state.update(await nodes.diagnosis_logistics_node(state))
        state.update(await nodes.diagnosis_policy_node(state))
    assert state["diagnosis_order"]["queryStatus"] == "MISSING_ORDER_ID"
    invoke.assert_not_awaited()
    search.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_ignores_model_text_and_action_tokens(monkeypatch):
    from app.services import agent_runtime as rt

    done, complete, execute = (
        AsyncMock(),
        AsyncMock(),
        AsyncMock(side_effect=AssertionError("never execute")),
    )
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    monkeypatch.setattr(rt, "resolve_action_confirm", execute)
    result = report("REFUND_PROGRESS")
    await rt.finalize_agent_response(
        {"userId": "A", "messageId": 10},
        ["已退款999元 act_" + "a" * 32],
        [],
        tool_biz={"aftersalesDiagnosis": result},
    )
    assert (
        "999" not in done.await_args.args[2] and "act_" not in done.await_args.args[2]
    )
    assert (
        json.loads(complete.await_args.args[3])["aftersalesDiagnosis"][
            "executionAllowed"
        ]
        is False
    )
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_actual_langgraph_branch_runs_tools_then_rag_then_analysis(monkeypatch):
    from app.graph import builder
    from app.graph import nodes as common
    from app.graph.state import initial_state
    from app.services import agent_runtime as rt
    from langgraph.checkpoint.memory import InMemorySaver

    sequence = []

    async def invoke(name, args, user):
        assert user == "A" and args == {"orderId": "O-A", "includeFacts": True}
        sequence.append(name)
        return ToolInvokeResult(
            content="test",
            business_facts=order() if name == "QUERY_ORDERS" else logistics(5),
        )

    async def retrieve(query, **kwargs):
        sequence.append("RAG")
        assert "O-A" not in query and "test-session" not in query
        return policy()

    async def entry(state):
        return {}

    monkeypatch.setattr(builder, "entry_guard", entry)
    monkeypatch.setattr(builder, "_resolve_checkpointer", lambda: InMemorySaver())
    monkeypatch.setattr(builder, "post_turn_node", AsyncMock(return_value={}))
    monkeypatch.setattr(builder, "cleanup_node", AsyncMock(return_value={}))
    monkeypatch.setattr(common.redis_service, "bind_message_id", AsyncMock())
    monkeypatch.setattr(common.redis_service, "clear_bound_message_id", AsyncMock())
    monkeypatch.setattr(
        common.sensitive_word_service,
        "replace",
        AsyncMock(side_effect=lambda text: text),
    )
    classify = AsyncMock(side_effect=AssertionError("no LLM"))
    monkeypatch.setattr(common, "resolve_intent", classify)
    monkeypatch.setattr(svc.mcp_tool_router, "invoke", invoke)
    monkeypatch.setattr(nodes.rag_retriever, "search_policy", retrieve)
    done, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    graph = builder.build_agent_graph()
    state = initial_state(
        {"userId": "A", "messageId": 1}, None, "订单 O-A 物流长期不更新"
    )
    with agent_user_context("A", "test-session"):
        result = await graph.ainvoke(
            state, {"configurable": {"thread_id": "test-only"}}
        )
    assert sequence == ["QUERY_ORDERS", "QUERY_LOGISTICS", "RAG"]
    assert result["diagnosis_report"]["diagnosis"]["status"] == "CONFIRMED"
    assert (
        json.loads(complete.await_args.args[3])["aftersalesDiagnosis"][
            "policyEvidence"
        ]["hits"][0]["revision"]
        == 2
    )
    done.assert_awaited_once()
    classify.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_mcp_facts_option_requires_verified_http_session(monkeypatch):
    from types import SimpleNamespace

    from app.mcp_server import server
    from starlette.requests import Request

    request = Request({"type": "http", "headers": [(b"token", b"test-session")]})
    monkeypatch.setattr(
        server.mcp,
        "get_context",
        lambda: SimpleNamespace(request_context=SimpleNamespace(request=request)),
    )
    login = AsyncMock(return_value=SimpleNamespace(user_id="A"))
    monkeypatch.setattr(server, "get_user_by_token", login)
    read = AsyncMock(
        return_value={"order_id": "O-A", "user_id": "A", "order_status": 1, "items": []}
    )
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with pytest.raises(ValueError, match="身份校验"):
        await server.query_orders("B", "O-A", includeFacts=True)
    read.assert_not_awaited()
    wire = await server.query_orders("A", "O-A", includeFacts=True)
    assert parse_tool_wire(wire).business_facts["data"]["ownerVerified"] is True
    login.return_value = None
    with pytest.raises(ValueError, match="身份校验"):
        await server.query_logistics("A", "O-A", includeFacts=True)


@pytest.mark.asyncio
async def test_user_b_own_order_success(monkeypatch):
    read = AsyncMock(
        return_value={"order_id": "O-B", "user_id": "B", "order_status": 2, "items": []}
    )
    monkeypatch.setattr(facts.java_internal_client, "get_order", read)
    with agent_user_context("B", "test-b-session"):
        result = await facts.read_order_facts("B", "O-B")
    assert result.business_facts["queryStatus"] == "SUCCESS"
    assert result.business_facts["orderId"] == "O-B"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value", [None, {}, {"status": "SUCCESS", "hits": []}, RuntimeError("test failure")]
)
async def test_policy_node_invalid_or_failed_result(monkeypatch, value):
    read = (
        AsyncMock(side_effect=value)
        if isinstance(value, Exception)
        else AsyncMock(return_value=value)
    )
    monkeypatch.setattr(nodes.rag_retriever, "search_policy", read)
    result = await nodes.diagnosis_policy_node(
        {
            "user_id": "A",
            "message_id": 1,
            "diagnosis_case": "PRODUCT_QUALITY",
            "diagnosis_order": order(),
        }
    )
    expected = (
        "NO_MATCH" if value == {"status": "SUCCESS", "hits": []} else "RETRIEVAL_ERROR"
    )
    assert result["diagnosis_policy"]["status"] == expected


@pytest.mark.asyncio
async def test_logistics_outage_preserves_order_facts(monkeypatch):
    monkeypatch.setattr(
        svc.mcp_tool_router,
        "invoke",
        AsyncMock(side_effect=RuntimeError("test outage")),
    )
    state = {
        "user_id": "A",
        "message_id": 1,
        "diagnosis_case": "LOGISTICS_STAGNATION",
        "diagnosis_order_id": "O-A",
        "diagnosis_order": order(),
    }
    with agent_user_context("A", "test-session"):
        result = await nodes.diagnosis_logistics_node(state)
    diagnosed = report(lf=result["diagnosis_logistics"])
    assert diagnosed["orderFacts"]["queryStatus"] == "SUCCESS"
    assert diagnosed["logisticsFacts"]["queryStatus"] == "SERVICE_ERROR"
    assert diagnosed["diagnosis"]["status"] == "UNCERTAIN"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "node",
    [
        nodes.diagnosis_order_node,
        nodes.diagnosis_logistics_node,
        nodes.diagnosis_policy_node,
        nodes.diagnosis_analyze_node,
    ],
)
async def test_cancelled_branch_never_reads_or_analyzes(node):
    assert await node({"cancelled": True}) == {"cancelled": True}


@pytest.mark.asyncio
async def test_external_cancel_flag_stops_next_node(monkeypatch):
    monkeypatch.setattr(nodes, "is_cancelled", AsyncMock(return_value=True))
    result = await nodes.diagnosis_order_node({"user_id": "A", "message_id": 1})
    assert result == {"cancelled": True}


@pytest.mark.asyncio
async def test_mismatched_mcp_order_or_unverified_owner_is_rejected(monkeypatch):
    value = order()
    value["data"]["ownerVerified"] = False
    invoke = AsyncMock(return_value=ToolInvokeResult(content="", business_facts=value))
    monkeypatch.setattr(svc.mcp_tool_router, "invoke", invoke)
    with agent_user_context("A", "test-session"):
        assert (await svc.fetch_facts("order", "A", "O-A"))[
            "queryStatus"
        ] == "SERVICE_ERROR"
        value["orderId"] = "O-B"
        assert (await svc.fetch_facts("order", "A", "O-A"))[
            "queryStatus"
        ] == "SERVICE_ERROR"


def test_quality_claim_is_not_a_confirmed_defect():
    value = report("PRODUCT_QUALITY", lf={"queryStatus": "SKIPPED"})
    assert value["diagnosis"]["status"] == "UNCERTAIN"
    assert "用户陈述" in svc.render_diagnosis(value)
    assert value["recommendedActions"][0]["policyReferences"][0]["revision"] == 2


def test_no_logistics_record_is_not_a_service_outage():
    value = report(lf={"queryStatus": "NO_RECORD"})
    assert value["logisticsFacts"]["queryStatus"] == "NO_RECORD"
    assert value["diagnosis"]["status"] == "UNCERTAIN"
