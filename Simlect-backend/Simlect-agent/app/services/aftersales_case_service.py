"""Persist only server-generated diagnosis; no execution/approval capability."""

import json
from copy import deepcopy

from app.auth.agent_context import require_agent_user
from app.constants import MSG_STATUS_COMPLETE
from app.db.pool import acquire
from app.services.java_internal_client import java_internal_client


async def create_case(user_id: str, message_id: int, report: dict) -> dict:
    require_agent_user(user_id)
    if type(message_id) is not int or message_id < 1 or not isinstance(report, dict):
        raise ValueError("诊断消息参数无效")
    data = deepcopy(report)
    data.pop("caseWorkflow", None)
    if (
        data.get("executionAllowed") is not False
        or (data.get("orderFacts") or {}).get("queryStatus") != "SUCCESS"
    ):
        raise ValueError("当前诊断没有可验证订单，不能创建案件")
    result = await java_internal_client.post_json(
        "/internal/order/aftersales/create",
        {"sourceMessageId": message_id, "report": data},
        strict=True,
    )
    if (
        not isinstance(result, dict)
        or not result.get("caseId")
        or result.get("executionAllowed") is not False
    ):
        raise ValueError("案件服务返回结果无效")
    return result


async def create_from_message(user_id: str, message_id: int) -> dict:
    require_agent_user(user_id)
    if type(message_id) is not int or message_id < 1:
        raise ValueError("诊断消息参数无效")
    async with acquire() as cur:
        await cur.execute(
            "SELECT biz_data FROM agent_message WHERE message_id=%s AND user_id=%s AND status=%s",
            (message_id, user_id, MSG_STATUS_COMPLETE),
        )
        row = await cur.fetchone()
    if not row:
        raise ValueError("诊断消息不存在、未完成或无权访问")
    try:
        saved = json.loads(row["biz_data"])
        if not isinstance(saved, dict):
            raise ValueError("Message does not contain a diagnosis")
        if saved.get("agentType") == "supervisor":
            from app.supervisor.store import result
            from app.supervisor.contracts import checked_result
            value = saved.get("fullReport") or await result(user_id,message_id)
            if not value or value.get("messageId") != message_id:
                raise ValueError("Supervisor diagnosis has expired")
            report = checked_result(value["results"]["aftersales"],"aftersales").data["diagnosis"]
        else:
            report = saved["aftersalesDiagnosis"]
    except (ValueError, TypeError, KeyError) as exc:
        raise ValueError("消息不是售后诊断报告") from exc
    return await create_case(user_id, message_id, report)
