"""Bounded aftersales branch of the existing graph, not a second agent."""

from app.rag.retriever import rag_retriever
from app.services.aftersales_diagnosis import diagnose, fetch_facts, render_diagnosis
from app.services.agent_runtime import is_cancelled


async def cancelled(state):
    return state.get("cancelled") or await is_cancelled(
        state["user_id"], state["message_id"]
    )


async def diagnosis_order_node(state):
    if await cancelled(state):
        return {"cancelled": True}
    facts = await fetch_facts(
        "order", state["user_id"], state.get("diagnosis_order_id")
    )
    if facts["queryStatus"] == "MISSING_ORDER_ID" and state.get("user_text"):
        import json
        from app.services.mcp_tool_router import mcp_tool_router
        try:
            result = await mcp_tool_router.invoke("QUERY_ORDERS", {}, state["user_id"])
            rows = json.loads(result.assistant_cards or "null")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Order list not available")
            # References only. Do not choose the newest or infer an order from model text.
            ids = list(dict.fromkeys(str(row.get("orderId") or row.get("order_id") or "") for row in rows))
            facts = {**facts, "orderOptions": [i for i in ids if i][:20], "listStatus": "SUCCESS"}
        except Exception:
            facts = {**facts, "queryStatus": "SERVICE_ERROR", "orderOptions": [], "listStatus": "SERVICE_ERROR"}
    return {
        "diagnosis_order": facts,
        "tools_called": ["QUERY_ORDERS"]
        if facts.get("listStatus") or facts["queryStatus"] not in {"UNAUTHORIZED", "MISSING_ORDER_ID"}
        else [],
    }


async def diagnosis_logistics_node(state):
    if await cancelled(state):
        return {"cancelled": True}
    order = state.get("diagnosis_order") or {}
    from app.domain.aftersales_intent import classify
    intent=classify(state.get("user_text") or "")
    needed = bool(intent and intent["operation"]=="LOGISTICS_QUERY") or state["diagnosis_case"] == "LOGISTICS_STAGNATION" or (
        state["diagnosis_case"] == "UNSHIPPED_ORDER"
        and (order.get("data") or {}).get("orderStatus") in {1, 2}
    )
    if order.get("queryStatus") != "SUCCESS" or not needed:
        return {
            "diagnosis_logistics": {
                "kind": "logistics",
                "queryStatus": "SKIPPED",
                "data": None,
            }
        }
    facts = await fetch_facts(
        "logistics", state["user_id"], state["diagnosis_order_id"]
    )
    return {"diagnosis_logistics": facts, "tools_called": ["QUERY_LOGISTICS"]}


async def diagnosis_policy_node(state):
    if await cancelled(state):
        return {"cancelled": True}
    if (state.get("diagnosis_order") or {}).get("queryStatus") != "SUCCESS":
        return {"diagnosis_policy": {"status": "SKIPPED", "hits": []}}
    try:
        # No order identifier or user token needs to be sent to the embedding API.
        queries = {
            "LOGISTICS_STAGNATION": "物流停滞 运输异常 售后处理政策",
            "UNSHIPPED_ORDER": "订单未发货 发货期限 售后处理政策",
            "PAYMENT_ANOMALY": "支付异常 重复扣款 人工核实政策",
            "REFUND_PROGRESS": "退款进度 到账时间 人工核实政策",
            "PRODUCT_QUALITY": "商品质量 破损 退换货 售后政策",
            "AFTERSALES_CONSULT": "售后咨询 退换货 处理政策",
        }
        policy = await rag_retriever.search_policy(queries[state["diagnosis_case"]], browse_topics=True)
        if (
            not isinstance(policy, dict)
            or not isinstance(policy.get("hits"), list)
            or policy.get("status")
            not in {
                "SUCCESS",
                "NO_MATCH",
                "LOW_RELEVANCE",
                "EMBEDDING_FAILED",
                "ES_UNAVAILABLE",
                "CATALOG_UNAVAILABLE",
            }
        ):
            raise ValueError("Invalid policy retrieval result")
        if policy["status"] == "SUCCESS" and not policy["hits"]:
            policy = {"status": "NO_MATCH", "hits": []}
    except Exception:  # noqa: BLE001 -- Boundary fails closed without exposing provider errors.
        policy = {"status": "RETRIEVAL_ERROR", "hits": []}
    return {"diagnosis_policy": policy}


async def diagnosis_analyze_node(state):
    if await cancelled(state):
        return {"cancelled": True}
    report = diagnose(
        state["diagnosis_case"],
        state.get("diagnosis_order_id"),
        state["diagnosis_order"],
        state["diagnosis_logistics"],
        state["diagnosis_policy"],
    )
    import re
    text=state.get('user_text') or ''
    from app.services.aftersales_diagnosis import wants_return, mark_return_request
    from app.domain.aftersales_intent import classify
    intent=classify(text)
    if intent:report['businessIntent']=intent['operation']
    if wants_return(text):mark_return_request(report,text)
    if intent and intent['operation'] in {'EXCHANGE','CANCEL_ORDER'}:
        report['requestedOperation']=intent['operation']+'_GUIDANCE'
        if intent['operation']=='EXCHANGE':
            report['approvalRequired']=True;report['suggestedApplicationType']='exchange'
            report['recommendedActions'].append({'code':'MANUAL_REVIEW','title':'核对换货需求，由本人确认提交人工审核；不执行退款或发货','approvalRequired':True,'executionAllowed':False})
    if intent and intent['operation']=='ORDER_QUERY' and report['orderFacts'].get('listStatus')=='SUCCESS':report['listOnly']=True
    if re.search(r'(?:查询|查看|列出).*订单(?:列表|有哪些)',text) and report['orderFacts'].get('listStatus')=='SUCCESS':report['listOnly']=True
    return {
        "diagnosis_report": report,
        "tool_biz": {"aftersalesDiagnosis": report},
        "chunks": [render_diagnosis(report)],
        "route": "finalize",
    }
