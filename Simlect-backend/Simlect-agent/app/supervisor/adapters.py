"""Small adapters around the existing complete specialist graphs, no business reimplementation."""

import re
import json
from functools import lru_cache

from app.auth.agent_context import require_agent_user
from app.auth.delegation import read_only_delegation
from app.graph.builder import build_agent_graph
from app.graph.state import initial_state
from app.rag.policy import is_policy_question
from app.services.aftersales_diagnosis import extract_order_id, wants_return, mark_return_request
from app.shopping.runner import run_shopping_agent
from app.supervisor import store
from app.supervisor.contracts import AgentResult, Task, checked_result


@lru_cache(maxsize=1)
def aftersales_graph():
    return build_agent_graph(persist_checkpoint=False)


async def invoke(task, user_id, message_id):
    user = require_agent_user(user_id)
    task = task if isinstance(task, Task) else Task.model_validate(task)
    message = {
        "userId": user.user_id,
        "messageId": message_id,
        "userMessage": task.text,
    }
    with read_only_delegation():
        if task.agent == "shopping":
            value = await run_shopping_agent(message, collect_only=True)
            code = (value or {}).get("status")
            if code in {
                "SUCCESS",
                "NO_RESULTS",
                "NO_MATCHING_SKU",
                "NEEDS_CLARIFICATION",
            }:
                return checked_result(
                    AgentResult(
                        agent="shopping",
                        status="NEEDS_CLARIFICATION"
                        if code == "NEEDS_CLARIFICATION"
                        else "SUCCESS",
                        data={"shopping": value},
                    ),
                    "shopping",
                )
            return AgentResult(
                agent="shopping",
                status="CANCELLED" if code == "CANCELLED" else "ERROR",
                errorCode=code
                if code
                in {"TOOL_ERROR", "SHOPPING_BUSY", "CONTEXT_UNAVAILABLE", "CANCELLED"}
                else "SPECIALIST_FAILED",
            )
        from app.services.aftersales_context import prepare_turn
        text,business=await prepare_turn(user.user_id,task.text)
        if (business and (business['operation']=='CANCEL_APPLICATION' or business['operation']=='AFTERSALES_PROGRESS' and business.get('progressQueryOnly',True))) or (not business and re.search(r'(?:查询|查看|跟踪|查)[^，,。；;\n]*(?:售后申请|售后案件|售后处理进度|售后进度|申请进度)|^我的售后申请[？?。]*$',text)):
            from app.services.aftersales_context import load_case_progress
            rows=await load_case_progress(user.user_id,(business or {}).get('orderId'))
            if not isinstance(rows,list) or any(not isinstance(r,dict) or not r.get('caseId') for r in rows):
                return AgentResult(agent='aftersales',status='ERROR',errorCode='TOOL_ERROR')
            data={'caseList':rows[:20]}
            if business and business.get('orderId'):data['caseOrderId']=business['orderId']
            return checked_result(AgentResult(agent='aftersales',status='SUCCESS',data=data),'aftersales')
        if (business and business["operation"]=="ORDER_QUERY") or re.search(r"(?:查询|查看|列出).*订单(?:列表|有哪些)|我的订单有哪些", text) and not extract_order_id(text):
            from app.services.mcp_tool_router import mcp_tool_router
            tool = await mcp_tool_router.invoke("QUERY_ORDERS", {}, user.user_id)
            rows = json.loads(tool.assistant_cards or "null")
            if not isinstance(rows, list) or any(not isinstance(r,dict) or not (r.get('orderId') or r.get('order_id')) for r in rows):
                return AgentResult(agent='aftersales',status='ERROR',errorCode='TOOL_ERROR')
            return checked_result(AgentResult(agent='aftersales',status='SUCCESS',data={'orderList':[
                {'orderId':str(r.get('orderId') or r.get('order_id')), 'orderStatus':r.get('orderStatus',r.get('order_status'))}
                for r in rows[:20]]}), 'aftersales')
        previous = await store.hint(user.user_id)
        followup = bool(
            re.fullmatch(
                r"(?:继续|再试试|接着说|然后呢|还有吗|刚才那个呢)[？?。！!]*",
                text.strip(),
            )
        )
        if (
            followup
            and previous.get("kind") == "policy"
            and previous.get("policyQuery")
        ):
            text = previous["policyQuery"]
        if not is_policy_question(text):
            # Force the existing read-only diagnosis path, not the legacy free-form action loop.
            if (
                not extract_order_id(text)
                and previous.get("orderId")
                and (followup or re.search(r"这笔|这单|该订单|刚才.*订单", text))
            ):
                text += "；订单号：" + previous["orderId"]
            text = "售后咨询：" + text
        message["userMessage"] = text
        state = initial_state(message, None, text)
        state["collect_only"] = True
        state = await aftersales_graph().ainvoke(state)
        if state.get("cancelled"):
            return AgentResult(agent="aftersales", status="CANCELLED")
        report = state.get("diagnosis_report")
        if report:
            if wants_return(task.text):
                mark_return_request(report,text)
            if report.get("orderId") != extract_order_id(text):
                raise ValueError("Specialist returned facts for a different order")
            query = (report.get("orderFacts") or {}).get("queryStatus")
            status = (
                "NEEDS_CLARIFICATION"
                if query == "MISSING_ORDER_ID"
                else "ERROR"
                if query in {"UNAUTHORIZED", "SERVICE_ERROR", "NOT_FOUND_OR_FORBIDDEN"}
                else "SUCCESS"
            )
            response = checked_result(
                AgentResult(
                    agent="aftersales", status=status, data={"diagnosis": report}
                ),
                "aftersales",
            )
            if query == "SUCCESS":
                await store.save_hint(
                    user.user_id, {"kind": "order", "orderId": report["orderId"],"businessIntent":report.get("businessIntent","ORDER_DETAIL")}
                )
            return response
        evidence = state.get("policy_result")
        if evidence:
            status = (
                "SUCCESS"
                if evidence.get("status") in {"SUCCESS", "NO_MATCH", "LOW_RELEVANCE"}
                else "ERROR"
            )
            response = checked_result(
                AgentResult(
                    agent="aftersales", status=status, data={"policy": evidence, "policyAdvice": state.get("policy_advice")}
                ),
                "aftersales",
            )
            await store.save_hint(
                user.user_id, {"kind": "policy", "policyQuery": text[:300]}
            )
            return response
        raise ValueError("Specialist did not return structured evidence")
