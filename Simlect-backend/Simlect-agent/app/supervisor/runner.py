"""One message owner for Supervisor; full evidence cached separately from compact metadata."""

import json

import structlog

from app.auth.agent_context import require_agent_user
from app.services.agent_runtime import is_cancelled, parse_agent_message
from app.services.message_service import agent_message_service as agent_message_service
from app.services.stream_service import stream_service
from app.supervisor import store
from app.supervisor.aggregation import aggregate, display
from app.supervisor.graph import build_supervisor_graph

logger = structlog.get_logger()


async def run_supervisor(agent_msg):
    user = require_agent_user(agent_msg["userId"]).user_id
    message_id = agent_msg["messageId"]
    token = None
    try:
        token = await store.acquire(user)
        context = await store.load(user)
        await stream_service.push_agent_status(
            user, message_id, "supervisor", "ROUTING"
        )
        _, text = parse_agent_message(agent_msg)
        state = await build_supervisor_graph().ainvoke(
            {
                "user_id": user,
                "message_id": message_id,
                "text": text,
                "context": context,
            }
        )
        if state.get("cancelled") or await is_cancelled(user, message_id):
            await stream_service.push_agent_status(
                user, message_id, "supervisor", "CANCELLED"
            )
            return
        report = state["report"]
        report["messageId"] = message_id
        tasks = report["plan"]["tasks"]
        # A composite task does not establish an unambiguous follow-up destination.
        new_context = {"lastRoute": tasks[0]["agent"] if len(tasks) == 1 else None}
        await store.save(user, token, message_id, new_context, report)
    except Exception:  # noqa: BLE001 -- Routing/cache failures cannot become invented facts.
        report = aggregate(
            {
                "tasks": [],
                "reason": "COORDINATION_UNAVAILABLE",
                "question": "统一调度上下文暂不可用或上一轮仍在处理，请稍后重试。",
            },
            {},
        )
        report["status"] = "FAILED"
    finally:
        if token:
            try:
                await store.release(user, token)
            except Exception:  # noqa: BLE001 -- Expiring lease, never force-delete another request's lock.
                logger.warning("supervisor_release_failed", message_id=message_id)
    if await is_cancelled(user, message_id):
        return
    payload = display(report)
    assistant = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if len(assistant) > 15500:
        payload["intro"] = (
            "本次证据较多，已保留完整报告，请展开完整证据核对。没有执行退款、支付、下单或审批。"
        )
        assistant = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    metadata = json.dumps(
        {
            "agentType": "supervisor",
            "fullReport": report,
            "status": report["status"],
            "messageId": message_id,
            "executionAllowed": False,
        },
        ensure_ascii=False,
    )
    from app.services.agent_runtime import _persist_and_notify
    if not await _persist_and_notify(agent_msg, assistant, "supervisor", metadata):
        return
    state = (
        "ERROR"
        if report["status"] == "FAILED"
        else "NEEDS_CLARIFICATION"
        if report["status"] == "NEEDS_CLARIFICATION"
        else "SUCCESS"
    )
    await stream_service.push_agent_status(user, message_id, "supervisor", state)
