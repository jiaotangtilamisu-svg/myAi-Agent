"""Only mocked case persistence; no approval executor, DB writes or real models."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from app.auth.agent_context import agent_user_context
from app.graph import case_nodes
from app.services import aftersales_case_service as svc

CASE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def report():
    return {
        "schemaVersion": 1,
        "orderId": "O-A",
        "executionAllowed": False,
        "orderFacts": {"queryStatus": "SUCCESS", "data": {"ownerVerified": True}},
        "caseWorkflow": {"status": "ON_REQUEST"},
    }


def state():
    return {
        "user_id": "A",
        "message_id": 1,
        "diagnosis_report": report(),
        "tool_biz": {"aftersalesDiagnosis": report()},
    }


@pytest.mark.asyncio
async def test_case_creation_uses_verified_context_and_strips_runtime_fields(
    monkeypatch,
):
    post = AsyncMock(return_value={"caseId": CASE, "executionAllowed": False})
    monkeypatch.setattr(svc.java_internal_client, "post_json", post)
    original = report()
    with agent_user_context("A", "test-session"):
        result = await svc.create_case("A", 1, original)
    assert result["caseId"] == CASE and original["caseWorkflow"]
    assert post.await_args.args[0] == "/internal/order/aftersales/create"
    payload = post.await_args.args[1]
    assert payload["sourceMessageId"] == 1 and "caseWorkflow" not in payload["report"]
    assert "test-session" not in json.dumps(payload) and "userId" not in payload
    assert post.await_args.kwargs["strict"] is True


@pytest.mark.asyncio
async def test_forged_user_does_not_reach_java(monkeypatch):
    post = AsyncMock()
    monkeypatch.setattr(svc.java_internal_client, "post_json", post)
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await svc.create_case("B", 1, report())
    post.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutate", ["execution", "missing-order", "bad-id"])
async def test_unusable_diagnosis_cannot_create_case(monkeypatch, mutate):
    post = AsyncMock()
    monkeypatch.setattr(svc.java_internal_client, "post_json", post)
    value = report()
    if mutate == "execution":
        value["executionAllowed"] = True
    elif mutate == "missing-order":
        value["orderFacts"] = {"queryStatus": "SERVICE_ERROR"}
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await svc.create_case("A", 0 if mutate == "bad-id" else 1, value)
    post.assert_not_awaited()


def fake_message_store(monkeypatch, row):
    cur = AsyncMock()
    cur.fetchone.return_value = row
    cm = Mock()
    cm.__aenter__ = AsyncMock(return_value=cur)
    cm.__aexit__ = AsyncMock()
    monkeypatch.setattr(svc, "acquire", lambda: cm)
    return cur


@pytest.mark.asyncio
async def test_on_request_loads_only_completed_own_server_diagnosis(monkeypatch):
    cur = fake_message_store(
        monkeypatch, {"biz_data": json.dumps({"aftersalesDiagnosis": report()})}
    )
    create = AsyncMock(return_value={"caseId": CASE})
    monkeypatch.setattr(svc, "create_case", create)
    with agent_user_context("A", "test-session"):
        assert (await svc.create_from_message("A", 1))["caseId"] == CASE
    sql, args = cur.execute.await_args.args
    assert "user_id=%s" in sql and "status=%s" in sql and args == (1, "A", 2)
    create.assert_awaited_once_with("A", 1, report())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "row", [None, {"biz_data": "{}"}, {"biz_data": "invalid"}, {"biz_data": None}]
)
async def test_other_or_non_diagnosis_message_rejected(monkeypatch, row):
    fake_message_store(monkeypatch, row)
    create = AsyncMock()
    monkeypatch.setattr(svc, "create_case", create)
    with agent_user_context("A", "test-session"), pytest.raises(ValueError):
        await svc.create_from_message("A", 1)
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_record_off_by_default_does_not_touch_java_or_redis(monkeypatch):
    monkeypatch.setattr(
        case_nodes,
        "get_settings",
        lambda: SimpleNamespace(aftersales_cases_auto_create=False),
    )
    create, cancel = AsyncMock(), AsyncMock()
    monkeypatch.setattr(case_nodes, "create_case", create)
    monkeypatch.setattr(case_nodes, "is_cancelled", cancel)
    result = await case_nodes.case_record_node(state())
    assert result["diagnosis_report"]["caseWorkflow"]["status"] == "ON_REQUEST"
    create.assert_not_awaited()
    cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_record_enabled_returns_case_but_no_confirmation(monkeypatch):
    monkeypatch.setattr(
        case_nodes,
        "get_settings",
        lambda: SimpleNamespace(aftersales_cases_auto_create=True),
    )
    monkeypatch.setattr(case_nodes, "is_cancelled", AsyncMock(return_value=False))
    create = AsyncMock(
        return_value={"caseId": CASE, "state": "AWAITING_USER", "version": 1}
    )
    monkeypatch.setattr(case_nodes, "create_case", create)
    result = await case_nodes.case_record_node(state())
    assert result["diagnosis_report"]["caseWorkflow"] == {
        "status": "RECORDED",
        "caseId": CASE,
        "caseState": "AWAITING_USER",
        "version": 1,
        "executionAllowed": False,
    }
    assert create.await_args.args[:2] == ("A", 1)


@pytest.mark.asyncio
async def test_case_outage_preserves_diagnosis_and_does_not_claim_success(monkeypatch):
    monkeypatch.setattr(
        case_nodes,
        "get_settings",
        lambda: SimpleNamespace(aftersales_cases_auto_create=True),
    )
    monkeypatch.setattr(case_nodes, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        case_nodes, "create_case", AsyncMock(side_effect=RuntimeError("test outage"))
    )
    result = await case_nodes.case_record_node(state())
    assert result["diagnosis_report"]["orderId"] == "O-A"
    assert result["diagnosis_report"]["caseWorkflow"]["status"] == "UNAVAILABLE"


@pytest.mark.asyncio
async def test_unverified_order_and_cancelled_never_create(monkeypatch):
    create = AsyncMock()
    monkeypatch.setattr(case_nodes, "create_case", create)
    s = state()
    s["diagnosis_report"]["orderFacts"] = {"queryStatus": "UNAUTHORIZED"}
    assert (await case_nodes.case_record_node(s))["diagnosis_report"]["caseWorkflow"][
        "status"
    ] == "INELIGIBLE"
    s["cancelled"] = True
    assert await case_nodes.case_record_node(s) == {"cancelled": True}
    create.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["RECORDED", "ON_REQUEST", "UNAVAILABLE"])
async def test_response_retains_case_workflow_and_is_not_executable(
    monkeypatch, status
):
    from app.services import agent_runtime as rt

    monkeypatch.setattr(
        rt,
        "resolve_action_confirm",
        AsyncMock(side_effect=AssertionError("no action execution")),
    )
    done, complete = AsyncMock(), AsyncMock()
    monkeypatch.setattr(rt.stream_service, "push_done", done)
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    monkeypatch.setattr(
        "app.services.aftersales_diagnosis.render_diagnosis", lambda _: "test diagnosis"
    )
    value = report()
    value["caseWorkflow"] = {"status": status, "caseId": CASE}
    await rt.finalize_agent_response(
        {"userId": "A", "messageId": 1},
        ["act_fake"],
        [],
        tool_biz={"aftersalesDiagnosis": value},
    )
    assert (
        json.loads(complete.await_args.args[3])["aftersalesDiagnosis"][
            "executionAllowed"
        ]
        is False
    )
    assert "act_fake" not in done.await_args.args[2]


@pytest.mark.asyncio
async def test_route_ignores_client_report_identity_and_uses_saved_message(monkeypatch):
    from app.api.routes.agent import create_aftersales_case

    create = AsyncMock(return_value={"caseId": CASE})
    monkeypatch.setattr(svc, "create_from_message", create)
    result = await create_aftersales_case(
        messageId=1, user=SimpleNamespace(user_id="A")
    )
    create.assert_awaited_once_with("A", 1)
    assert result.data["caseId"] == CASE


@pytest.mark.asyncio
async def test_http_case_creation_ignores_forged_identity_and_report(monkeypatch):
    import httpx
    from app.api.routes import agent
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(agent.router, prefix="/api")

    async def login():
        with agent_user_context("A", "test-session"):
            yield SimpleNamespace(user_id="A")

    app.dependency_overrides[agent.require_login] = login
    create = AsyncMock(return_value={"caseId": CASE})
    monkeypatch.setattr(svc, "create_from_message", create)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://local.invalid"
    ) as client:
        response = await client.post(
            "/api/agent/aftersales/cases",
            data={"messageId": "1", "userId": "B", "report": "forged"},
        )
    assert response.json()["data"]["caseId"] == CASE
    create.assert_awaited_once_with("A", 1)


@pytest.mark.asyncio
async def test_real_graph_records_case_after_business_and_policy_evidence(monkeypatch):
    from app.graph import aftersales_nodes, builder, nodes
    from app.graph.state import initial_state
    from app.services import aftersales_diagnosis as diagnostic
    from app.services import agent_runtime as rt
    from app.services.tool_invoke_result import ToolInvokeResult
    from langgraph.checkpoint.memory import InMemorySaver

    sequence = []

    async def read(tool, args, user):
        sequence.append(tool)
        return ToolInvokeResult(
            content="test",
            business_facts={
                "schemaVersion": 1,
                "kind": "order",
                "orderId": "O-A",
                "queryStatus": "SUCCESS",
                "data": {
                    "orderId": "O-A",
                    "ownerVerified": True,
                    "orderStatus": 6,
                    "items": [],
                },
            },
        )

    async def policy(query, **kwargs):
        sequence.append("RAG")
        return {"status": "NO_MATCH", "hits": []}

    async def record(user, message, data):
        sequence.append("CASE")
        assert (
            user == "A"
            and message == 1
            and data["policyEvidence"]["status"] == "NO_MATCH"
        )
        assert data["executionAllowed"] is False
        return {"caseId": CASE, "state": "AWAITING_USER", "version": 1}

    monkeypatch.setattr(builder, "entry_guard", AsyncMock(return_value={}))
    monkeypatch.setattr(builder, "post_turn_node", AsyncMock(return_value={}))
    monkeypatch.setattr(builder, "cleanup_node", AsyncMock(return_value={}))
    monkeypatch.setattr(builder, "_resolve_checkpointer", lambda: InMemorySaver())
    monkeypatch.setattr(nodes.redis_service, "bind_message_id", AsyncMock())
    monkeypatch.setattr(nodes.redis_service, "clear_bound_message_id", AsyncMock())
    monkeypatch.setattr(
        nodes.sensitive_word_service,
        "replace",
        AsyncMock(side_effect=lambda text: text),
    )
    monkeypatch.setattr(
        nodes, "resolve_intent", AsyncMock(side_effect=AssertionError("no model"))
    )
    monkeypatch.setattr(aftersales_nodes, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(case_nodes, "is_cancelled", AsyncMock(return_value=False))
    monkeypatch.setattr(
        case_nodes,
        "get_settings",
        lambda: SimpleNamespace(aftersales_cases_auto_create=True),
    )
    monkeypatch.setattr(case_nodes, "create_case", record)
    monkeypatch.setattr(diagnostic.mcp_tool_router, "invoke", read)
    monkeypatch.setattr(aftersales_nodes.rag_retriever, "search_policy", policy)
    monkeypatch.setattr(rt.stream_service, "push_done", AsyncMock())
    complete = AsyncMock()
    monkeypatch.setattr(rt.agent_message_service, "complete_message", complete)
    graph = builder.build_agent_graph()
    with agent_user_context("A", "test-session"):
        result = await graph.ainvoke(
            initial_state(
                {"userId": "A", "messageId": 1}, None, "订单 O-A 退款进度异常"
            ),
            {"configurable": {"thread_id": "test-cases-only"}},
        )
    assert sequence == ["QUERY_ORDERS", "RAG", "CASE"]
    assert result["diagnosis_report"]["caseWorkflow"]["status"] == "RECORDED"
    assert CASE in complete.await_args.args[1]
    assert "待用户确认" in complete.await_args.args[1]
