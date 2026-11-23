"""Organize validated facts into one report; never summarize free-form specialist prose."""

import json
from copy import deepcopy
from datetime import UTC, datetime

from app.constants import ORDER_STATUS_NAMES
from app.rag.policy import render_policy
from app.shopping.runner import card_rows, safe, render_comparison
from app.supervisor.contracts import checked_result, fingerprint
from app.utils.biz_payload import build_product_payload


def aggregate(plan, raw_results):
    results, uncertain, next_steps, evidence = {}, [], [], []
    for task in plan["tasks"]:
        agent = task["agent"]
        result = checked_result(raw_results[agent], agent)
        payload = result.model_dump()
        payload["fingerprint"] = fingerprint(result.data)
        results[agent] = deepcopy(payload)
        if result.status != "SUCCESS":
            uncertain.append({"agent": agent, "reason": result.status})
        if agent == "aftersales":
            diagnosis = result.data.get("diagnosis")
            policy = (
                diagnosis.get("policyEvidence")
                if diagnosis
                else result.data.get("policy")
            )
            if diagnosis:
                uncertain.extend(
                    {"agent": agent, "reason": v}
                    for v in diagnosis["diagnosis"].get("conflicts", [])
                )
                uncertain.extend(
                    {"agent": agent, "reason": v}
                    for v in ([] if diagnosis.get('requestedOperation')=='RETURN_GUIDANCE' else diagnosis["diagnosis"].get("uncertainties", []))
                )
                evidence.extend(deepcopy(diagnosis.get("evidenceSources") or []))
                next_steps.extend(
                    {
                        "agent": agent,
                        "title": a["title"],
                        "approvalRequired": a.get("approvalRequired", True),
                        "executionAllowed": False,
                    }
                    for a in ([{'title':'补充真实办理原因，生成待确认方案；由本人确认后进入人工审核。','approvalRequired':True}] if diagnosis.get('requestedOperation')=='RETURN_GUIDANCE' and diagnosis.get('orderFacts',{}).get('queryStatus')=='SUCCESS' else diagnosis.get("recommendedActions", []))
                )
            if policy:
                if policy["status"] != "SUCCESS":
                    uncertain.append(
                        {"agent": agent, "reason": "POLICY_" + policy["status"]}
                    )
                if not diagnosis:
                    evidence.extend(
                        {
                            k: h.get(k)
                            for k in (
                                "documentId",
                                "revision",
                                "documentName",
                                "section",
                                "page",
                                "source",
                                "score",
                            )
                        }
                        for h in policy["hits"]
                    )
        else:
            shop = result.data.get("shopping") or {}
            if shop.get("clarification"):
                uncertain.append({"agent": agent, "reason": shop["clarification"]})
            for p in shop.get("recommendations", []):
                evidence.append(
                    {
                        "productId": p["productId"],
                        "source": deepcopy(p.get("source")),
                        "queryTime": p.get("queryTime"),
                    }
                )
                uncertain.extend(
                    {"agent": agent, "productId": p["productId"], "reason": v}
                    for v in p.get("limitations", [])
                )
            if shop.get("recommendations"):
                next_steps.append(
                    {
                        "agent": agent,
                        "title": "按已核实规格比较；购买前重新确认价格、库存与未核实属性。",
                        "approvalRequired": False,
                        "executionAllowed": False,
                    }
                )
    statuses = [v["status"] for v in results.values()]
    success = statuses.count("SUCCESS")
    status = (
        "NEEDS_CLARIFICATION"
        if not statuses or all(v == "NEEDS_CLARIFICATION" for v in statuses)
        else "COMPLETE"
        if success == len(statuses)
        else "PARTIAL"
        if success
        else "FAILED"
    )
    return {
        "schemaVersion": 1,
        "agentType": "supervisor",
        "status": status,
        "plan": deepcopy(plan),
        "results": results,
        "summary": {
            "completedQueries": success,
            "requestedQueries": len(statuses),
            "uncertainty": uncertain,
            "nextSteps": next_steps,
        },
        "evidenceSources": evidence,
        "executionAllowed": False,
        "queryTime": datetime.now(UTC).isoformat(),
    }


def display(report):
    lines = []
    if report["plan"].get("question"):
        lines.append(report["plan"]["question"])
    summary = report["summary"]
    if len(report['results'])>1:
        lines.append('已分别查询各项需求；未找到匹配商品或政策依据的部分将在对应结果中说明。')
        short_shop=(((report['results'].get('shopping') or {}).get('data') or {}).get('shopping') or {})
        if short_shop:
            short_req=short_shop.get('requirements') or {};found=len(short_shop.get('recommendations') or [])
            lines.append('选购结果：'+('找到'+str(found)+'款匹配商品。' if found else '未找到'+(str(short_req['budgetMax'])+'元以内的' if short_req.get('budgetMax') is not None else '')+safe(short_req.get('category') or '目标商品')+'；未放宽品类或预算。'))
    after = report["results"].get("aftersales") or {}
    diagnosis = (after.get("data") or {}).get("diagnosis")
    policy = (
        diagnosis.get("policyEvidence")
        if diagnosis
        else (after.get("data") or {}).get("policy")
    )
    if after:
        lines.append("\n### 售后与订单核实")
        cases=(after.get('data') or {}).get('caseList')
        if cases is not None:
            from app.services.aftersales_context import render_case_progress
            lines.append(render_case_progress(cases))
        orders = (after.get('data') or {}).get('orderList')
        if orders is not None:
            lines.append('本人订单列表：' if orders else '当前账号暂无订单。')
            for order in orders:
                lines.append(safe(order['orderId'])+'；状态：'+safe(ORDER_STATUS_NAMES.get(order.get('orderStatus'),'待核实')))
            if orders:lines.append('可提供上述订单号继续查看详情或物流；本次没有修改订单。')
        if diagnosis:
            facts = diagnosis["orderFacts"]
            if facts.get("queryStatus") == "SUCCESS":
                state = (facts.get("data") or {}).get("orderStatus")
                lines.append(
                    "订单："
                    + safe(diagnosis.get("orderId"))
                    + "；业务状态："
                    + safe(ORDER_STATUS_NAMES.get(state, "未知"))
                )
            else:
                lines.append("订单未取得可验证事实，不能据此确认异常或办理条件。")
            if diagnosis.get('businessIntent') in {'EXCHANGE','CANCEL_ORDER'}:
                from app.services.aftersales_diagnosis import render_diagnosis
                lines.append(render_diagnosis(diagnosis))
            returning=diagnosis.get('requestedOperation')=='RETURN_GUIDANCE'
            if returning:
                lines.append('办理退货/退款：先核对本笔订单及商品，点击下方“生成待确认的售后方案”，核对后再由本人确认提交，随后进入审核或人工处理。本次没有提交申请，也没有执行退款。未发货与已发货的办理选项可能不同；未经确认不要自行寄回商品。' if facts.get('queryStatus')=='SUCCESS' else '尚未验证订单，请先核对订单号和登录状态；验证本人订单后才能生成申请方案。')
            if not returning:lines.append(
                "诊断："
                + {
                    "CONFIRMED": "存在业务异常标记，根因仍需核实",
                    "NOT_OBSERVED": "当前证据未发现可确认异常",
                    "CONFLICT": "证据冲突，需人工核对",
                    "UNCERTAIN": "证据不足，暂不确定",
                }.get(diagnosis["diagnosis"]["status"], "暂不确定")
            )
            if not returning:lines.extend(safe(r) for r in diagnosis["diagnosis"].get("reasons", [])[:4])
        if policy and not (diagnosis and diagnosis.get('requestedOperation')=='RETURN_GUIDANCE' and policy.get('status')!='SUCCESS'):
            # Display whole original excerpts, not a model paraphrase or a cut policy clause.
            shown = {**policy, "hits": policy["hits"][:2]}
            if policy["status"] == "SUCCESS":
                lines.append("\n### 政策证据")
                quoted = {
                    **shown,
                    "hits": [
                        {
                            **h,
                            **{
                                k: safe(h[k])
                                for k in ("documentName", "section", "source", "text")
                            },
                        }
                        for h in shown["hits"]
                    ],
                }
                lines.append(render_policy(quoted, concise=True))
                if len(policy["hits"]) > 2:
                    lines.append("另有政策来源保留在完整报告中。")
            else:
                lines.append(render_policy(policy, concise=True))
                
    shopping = ((report["results"].get("shopping") or {}).get("data") or {}).get(
        "shopping"
    )
    cards = []
    if shopping:
        lines.append("\n### 商品比较与选购")
        from app.shopping.explanations import explain_unmatched
        explanation=explain_unmatched(shopping)
        if explanation:lines.append(explanation)
        comparing=shopping.get('isComparison') is True
        if comparing:lines.append(render_comparison(shopping))
        count = len(shopping["recommendations"])
        wanted = (shopping.get("requirements") or {}).get("requestedCount", 3)
        if count and not comparing:
            lines.append(f"找到 {count} 款符合本次条件的商品。" + (f"当前仅有这 {count} 款，不足所需的 {wanted} 款。" if count < wanted else ""))
        if shopping.get("clarification"):
            lines.append(safe(shopping["clarification"]))
        if not shopping["recommendations"] and not comparing:
            req=shopping.get('requirements') or {};category=req.get('category') or req.get('keyword') or '商品'
            budget=('、预算'+str(req['budgetMax'])+'元以内') if req.get('budgetMax') is not None else ''
            lines.append(('当前在售目录未检索到该品类条目：' if shopping.get('status')=='NO_RESULTS' else '已查询候选，但没有核实到符合条件的在售规格：')+'“'+safe(category)+safe(budget)+'”。这不等于库存为零；没有用其他品类或超预算商品替代。你可以指定另一个品类或调整预算继续查询。')
        for p in ([] if comparing else shopping["recommendations"]):
            value = p["price"]
            quote = (
                value["min"] + "～" + value["max"] + "元"
                if value["min"] is not None and value["max"] is not None
                else "价格未知"
            )
            lines.append(
                "**"
                + safe(p["productName"])
                + "**："
                + safe(quote)
                + "；"
                + (
                    "有已核实有货规格"
                    if p["availability"] == "IN_STOCK"
                    else "库存待确认"
                )
            )
            lines.append("属性：" + safe("；".join(str(k)+"："+"、".join(map(str,v)) for k,v in (p.get("attributes") or {}).items()) or "待核实")[:350])
            for s in p["eligibleSkus"][:3]:
                count = "库存未知" if s["stock"] is None else "库存" + str(s["stock"])
                lines.append(
                    "规格 "
                    + safe(s.get("sku_name") or "标准规格")[:100]
                    + "；"
                    + safe(s["price"] + "元" if s["price"] is not None else "价格未知")
                    + "；"
                    + count
                )
            lines.append(
                "数据时间：" + safe(p.get("queryTime") or shopping["queryTime"])
            )
        cards = json.loads(build_product_payload(card_rows(shopping))[0])
    if summary["uncertainty"]:
        lines.append("\n### 未确认与未完成事项")
        for u in summary["uncertainty"][:8]:
            reason = {
                "ERROR": "查询失败，未取得有效结果",
                "TIMEOUT": "查询超时，尚未完成",
                "INVALID_RESULT": "结果未通过校验，已拒绝使用",
                "NEEDS_CLARIFICATION": "需要补充信息",
                "POLICY_LOW_RELEVANCE": "现有条款与问题不够相关，请说明退货、换货、质量还是运费问题",
                "POLICY_NO_MATCH": "现有知识库未收录适用依据",
                "POLICY_SKIPPED": "本轮未查询政策，不能据此判定办理资格",
            }.get(u["reason"], u["reason"])
            for code,label in {'SKIPPED':'本轮未进行政策检索','LOW_RELEVANCE':'条款相关性不足','NO_MATCH':'未收录适用依据','EMBEDDING_FAILED':'政策向量服务暂不可用','ES_UNAVAILABLE':'知识检索服务暂不可用','CATALOG_UNAVAILABLE':'政策发布状态暂无法核验'}.items():
                reason=reason.replace(code,label)
            lines.append(
                ("售后：" if u["agent"] == "aftersales" else "导购：") + safe(reason)
            )
    if summary["nextSteps"]:
        lines.append("\n### 下一步")
        lines.extend(
            safe(a["title"]) + ("（需要人工审核）" if a["approvalRequired"] else "")
            for a in summary["nextSteps"][:5]
        )
    if diagnosis and diagnosis["orderFacts"].get("queryStatus") == "SUCCESS" and diagnosis.get('requestedOperation') not in {'RETURN_GUIDANCE','CANCEL_ORDER_GUIDANCE'}:
        lines.append(
            "如需办理售后，可基于本条诊断创建案件；仍须用户确认，并按风险经过管理员审批和人工处理。"
        )
    intro = "\n".join(lines)
    # Never truncate JSON, prices or a policy clause to fit the old message column.
    if len(intro) > 12500:
        intro = "本次报告较长，完整事实与来源已保留，请查看完整报告；本助手没有执行退款、下单或审批。"
    return {
        "type": "SUPERVISOR_RESULT",
        "intro": intro,
        "products": cards,
        "agents": [
            {"agent": k, "status": v["status"]} for k, v in report["results"].items()
        ],
        "status": report["status"],
        "canCreateCase": bool(diagnosis and diagnosis.get('orderFacts',{}).get('queryStatus')=='SUCCESS' and diagnosis.get('businessIntent') not in {'CANCEL_ORDER'}),
        "showCaseProgress": bool(diagnosis or 'orderList' in (after.get('data') or {}) or 'caseList' in (after.get('data') or {})),
    }
