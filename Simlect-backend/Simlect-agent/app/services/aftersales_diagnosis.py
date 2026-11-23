"""Evidence-driven aftersales triage. Deterministic, read-only, no invented SLAs."""

import re
from datetime import UTC, datetime, timedelta, timezone

from app.auth.agent_context import require_agent_user
from app.constants import ORDER_STATUS_NAMES
from app.rag.policy import is_policy_question, render_policy
from app.services.mcp_tool_router import mcp_tool_router
from app.utils.order_ids import extract_order_id as existing_order_id

CASES = (
    ("REFUND_PROGRESS", r"退款.*(?:进度|没到|未到|不到账|异常|卡住|多久)|退费.*未到"),
    (
        "PAYMENT_ANOMALY",
        r"支付.*(?:异常|失败|重复|扣款)|扣款|付了.*(?:未付|待付)|付款.*(?:异常|没变|未变)",
    ),
    (
        "LOGISTICS_STAGNATION",
        r"物流.*(?:停滞|不动|不更新|没更新|异常|未更新|慢)|快递.*(?:没到|未到|不动|停滞)|包裹.*(?:没到|未到)",
    ),
    ("UNSHIPPED_ORDER", r"未发货|没发货|不发货|还没发|发货.*(?:超时|太慢|延迟)"),
    ("PRODUCT_QUALITY", r"质量|破损|损坏|坏了|瑕疵|少件|漏发|货不对板"),
)

def wants_return(text: str) -> bool:
    from app.domain.aftersales_intent import classify
    intent=classify(text)
    return bool(intent and intent['operation'] in {'RETURN','REFUND'})


def mark_return_request(report: dict, text: str = '') -> None:
    from app.domain.aftersales_intent import classify
    intent=classify(text) if text else None
    operation=intent['operation'] if intent else 'RETURN'
    report['businessIntent']=operation
    report['requestedOperation']='RETURN_GUIDANCE'
    report['suggestedApplicationType']='refund' if operation=='REFUND' else 'return_refund'
    report['approvalRequired']=True
    actions=report.setdefault('recommendedActions',[])
    if not any(a.get('code')=='REFUND_REVIEW' for a in actions):
        actions.append({'code':'REFUND_REVIEW','title':'核对真实办理原因和申请资料，由本人确认后提交人工审核；不执行退款','approvalRequired':True,'executionAllowed':False})


def extract_order_id(text: str) -> str | None:
    from app.domain.aftersales_intent import order_ids
    ids=order_ids(text)
    return ids[0] if len(ids)==1 else None


def identify_case(text: str) -> str | None:
    if re.search(r"(?:查询|查看|列出).*(?:我自己的|我的|本人).*订单.*(?:列表|有哪些)|(?:我的订单有哪些)", text):
        return "AFTERSALES_CONSULT"
    # Pure policy questions retain stage-17 retrieval and do not require an order.
    from app.domain.aftersales_intent import classify
    operation=classify(text)
    order_reference=bool(operation and operation['requiresOrder'] and re.search(r'这个订单|这笔订单|这单|该订单',text))
    if is_policy_question(text) and not extract_order_id(text) and not order_reference:
        return None
    for kind, pattern in CASES:
        if re.search(pattern, text):
            return kind
    if operation and operation['operation'] not in {'POLICY_QUERY','AFTERSALES_PROGRESS','CANCEL_APPLICATION'}:
        return 'AFTERSALES_CONSULT'
    if re.search(r"售后|退换货|订单异常|退款咨询", text):
        return "AFTERSALES_CONSULT"
    return None


async def fetch_facts(kind: str, user_id: str, order_id: str | None) -> dict:
    base = {"schemaVersion": 1, "kind": kind, "orderId": order_id, "data": None}
    try:
        require_agent_user(user_id)
    except ValueError:
        return {**base, "queryStatus": "UNAUTHORIZED"}
    if not order_id:
        return {**base, "queryStatus": "MISSING_ORDER_ID"}
    try:
        name = "QUERY_ORDERS" if kind == "order" else "QUERY_LOGISTICS"
        result = await mcp_tool_router.invoke(
            name, {"orderId": order_id, "includeFacts": True}, user_id
        )
        facts = result.business_facts
        if (
            not isinstance(facts, dict)
            or facts.get("schemaVersion") != 1
            or facts.get("kind") != kind
            or facts.get("orderId") != order_id
            or facts.get("queryStatus")
            not in {
                "SUCCESS",
                "NOT_FOUND_OR_FORBIDDEN",
                "NO_RECORD",
                "UNAUTHORIZED",
                "SERVICE_ERROR",
            }
        ):
            return {**base, "queryStatus": "SERVICE_ERROR"}
        if facts["queryStatus"] == "SUCCESS":
            data = facts.get("data")
            if (
                not isinstance(data, dict)
                or data.get("orderId") != order_id
                or (kind == "order" and data.get("ownerVerified") is not True)
            ):
                return {**base, "queryStatus": "SERVICE_ERROR"}
            if kind == "order":
                if (
                    data.get("orderStatus") is not None
                    and type(data["orderStatus"]) is not int
                ) or not isinstance(data.get("items", []), list):
                    return {**base, "queryStatus": "SERVICE_ERROR"}
            elif not isinstance(data.get("records"), list) or (
                data.get("logisticsStatus") is not None
                and type(data["logisticsStatus"]) is not int
            ):
                return {**base, "queryStatus": "SERVICE_ERROR"}
        else:
            facts = {**facts, "data": None}
        return facts
    except Exception:  # noqa: BLE001 -- Boundary fails closed without exposing provider errors.
        return {**base, "queryStatus": "SERVICE_ERROR"}


def parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value))
        # Existing Java timestamps have no zone and represent the local China time.
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone(timedelta(hours=8)))
    except (ValueError, TypeError):
        return None


def diagnose(
    case: str,
    order_id: str | None,
    order: dict,
    logistics: dict,
    policy: dict,
    *,
    now=None,
) -> dict:
    now = now or datetime.now(UTC)
    data, transport = order.get("data") or {}, logistics.get("data") or {}
    reasons, gaps, conflicts = [], [], []
    status, confidence = "UNCERTAIN", "LOW"
    order_status = data.get("orderStatus")
    actions = []

    def action(code, title, review=False):
        actions.append(
            {
                "code": code,
                "title": title,
                "risk": "REVIEW" if review else "ADVICE",
                "approvalRequired": review,
                "executionAllowed": False,
            }
        )

    if order.get("queryStatus") != "SUCCESS":
        messages = {
            "MISSING_ORDER_ID": "请提供一个明确订单号；不自动选择订单，也不处理多个订单的歧义。",
            "UNAUTHORIZED": "当前登录身份无法验证，请重新登录。",
            "NOT_FOUND_OR_FORBIDDEN": "未找到当前用户可访问的订单；不区分订单不存在与不属于本人。",
        }
        gaps.append(
            messages.get(
                order.get("queryStatus"), "订单查询服务失败，不能把失败当成订单不存在。"
            )
        )
        action("VERIFY_ORDER", gaps[-1])
    else:
        reasons.append(
            f"业务订单状态：{ORDER_STATUS_NAMES.get(order_status, '未知')}（{order_status}）。"
        )
        if order_status not in ORDER_STATUS_NAMES:
            gaps.append("订单状态未知，不能推断支付、发货或退款结果。")
        created = parse_time(data.get("orderTime"))
        age = round((now - created).total_seconds() / 3600, 2) if created else None
        if age is not None:
            reasons.append(f"距下单时间约 {age} 小时；该时长不是售后政策阈值。")
            if age < 0:
                conflicts.append("订单时间晚于检查时间，需要核对时区或数据。")
        if transport.get("dataClass") == "DEMO":
            gaps.append("该物流为 LOCAL DEMO 演示记录，没有真实配送；不能据此判断真实物流停滞或承诺送达。")
        elif logistics.get("queryStatus") == "SUCCESS":
            ls = transport.get("logisticsStatus")
            if order_status in {0, 1, 4, 5} and ls in {1, 2, 3, 4}:
                conflicts.append("订单未处于已发货状态，但物流已揽收/运输/签收。")
            if ls == 5:
                status, confidence = "CONFIRMED", "MEDIUM"
                reasons.append("物流业务接口明确标记异常；具体原因尚待承运方核实。")
            times = [
                parse_time(r.get("recordTime"))
                for r in transport.get("records", [])
                if isinstance(r, dict)
            ]
            times = [t for t in times if t]
            if times:
                elapsed = round((now - max(times)).total_seconds() / 3600, 2)
                reasons.append(f"最新物流节点距检查时间约 {elapsed} 小时。")
                if elapsed < 0:
                    conflicts.append("物流节点时间晚于检查时间。")
            elif case == "LOGISTICS_STAGNATION":
                gaps.append("缺少可解析的物流节点时间。")
        elif case == "LOGISTICS_STAGNATION":
            gaps.append("物流无记录或查询失败，不能据此认定停滞。")

        if case == "LOGISTICS_STAGNATION":
            gaps.append("未获得经确认且可机器判定的物流停滞时限，无法认定违反承诺。")
            action(
                "CONTACT_CARRIER",
                "请人工联系承运方核实节点更新、运输情况和预计到达时间。",
            )
        elif case == "UNSHIPPED_ORDER":
            if order_status == 1:
                reasons.append("订单已付款、待发货；可以确认尚未发货，不能确认已超时。")
                action(
                    "CONTACT_MERCHANT", "向商家核实发货计划；确认承诺期限前不判定超时。"
                )
            elif order_status == 0:
                status, confidence = "NOT_OBSERVED", "MEDIUM"
                reasons.append("订单当前待付款，不属于已付款待发货的超时判断范围。")
                action(
                    "VERIFY_PAYMENT",
                    "如已实际扣款，请人工核对支付流水，不要重复付款。",
                    True,
                )
            elif order_status in {2, 3, 8}:
                status, confidence = "NOT_OBSERVED", "MEDIUM"
                reasons.append("当前订单状态不支持“尚未发货”的判断。")
            gaps.append("当前接口不提供承诺发货截止时间。")
        elif case == "PAYMENT_ANOMALY":
            gaps.append(
                "只有订单状态及是否存在支付引用，未查询支付流水/回调，不能认定扣款或重复支付。"
            )
            action(
                "PAYMENT_REVIEW",
                "请人工核对支付凭证、交易流水和回调；不要重复付款。",
                True,
            )
        elif case == "REFUND_PROGRESS":
            if order_status in {6, 7}:
                reasons.append(
                    "订单业务状态显示已退款或部分退款；这不代表银行卡/账户已到账。"
                )
            gaps.append(
                "当前订单接口没有退款申请时间、处理流水或到账时间，无法判断退款进度是否超时。"
            )
            action(
                "REFUND_REVIEW",
                "请人工核实退款申请和渠道流水；本 Agent 不执行退款。",
                True,
            )
        elif case == "PRODUCT_QUALITY":
            gaps.append("质量问题目前是用户陈述，尚无商品检验或人工核验证据。")
            action(
                "QUALITY_REVIEW",
                "保留商品照片、包装及问题描述，交由人工核实是否申请售后。",
                True,
            )
        else:
            status, confidence = "NOT_OBSERVED", "MEDIUM"
            reasons.append(
                "仅凭当前只读订单事实未发现可确认的异常，不代表已排除所有问题。"
            )
            action("CLARIFY_CASE", "请补充具体问题，由人工结合订单事实与政策核实。")
    if policy.get("status") != "SUCCESS":
        gaps.append(
            f"政策证据未通过检索：{policy.get('status', 'NO_MATCH')}。不能给出政策期限、赔偿或退款资格结论。"
        )
        if order.get("queryStatus") == "SUCCESS":
            action(
                "VERIFY_POLICY",
                "缺少有效政策依据，请人工确认适用规则后再决定售后方案。",
                True,
            )
    else:
        gaps.append(
            "政策片段供人工核对适用范围；本轮不从自然语言政策自动推导时限或裁定退款资格。"
        )
    if conflicts:
        status, confidence = "CONFLICT", "LOW"
        action(
            "RECONCILE_EVIDENCE",
            "订单与物流证据冲突，请人工对账，暂不据此办理业务。",
            True,
        )
    if status == "UNCERTAIN" and not actions:
        action("MANUAL_REVIEW", "证据不足，请人工核实订单与相关政策。", True)
    hits = policy.get("hits") if policy.get("status") == "SUCCESS" else []
    sources = [
        {
            "type": "policy",
            **{
                k: h.get(k)
                for k in (
                    "documentId",
                    "revision",
                    "documentName",
                    "section",
                    "page",
                    "source",
                    "score",
                    "category",
                    "issuer",
                    "originalUrl",
                    "publishedOn",
                    "effectiveFrom",
                    "effectiveUntil",
                )
            },
        }
        for h in hits or []
    ]
    for facts in (order, logistics):
        if facts.get("queryStatus") == "SUCCESS":
            sources.append(
                {
                    "type": facts["kind"],
                    "source": facts.get("source"),
                    "queriedAt": facts.get("queriedAt"),
                }
            )
    for suggestion in actions:
        suggestion["policyReferences"] = [
            {
                "documentId": h.get("documentId"),
                "revision": h.get("revision"),
                "section": h.get("section"),
                "chunkId": h.get("chunkId"),
            }
            for h in hits or []
        ]
        suggestion["basis"] = {
            "orderQueryStatus": order.get("queryStatus"),
            "logisticsQueryStatus": logistics.get("queryStatus"),
            "policyStatus": policy.get("status"),
        }
    return {
        "schemaVersion": 1,
        "caseType": case,
        "orderId": order_id,
        "diagnosis": {
            "status": status,
            "anomalyDetected": True
            if status == "CONFIRMED"
            else False
            if status == "NOT_OBSERVED"
            else None,
            "reasons": reasons,
            "uncertainties": gaps,
            "conflicts": conflicts,
            "rootCause": "现有只读证据不能确认根因；异常状态与具体责任原因应分别核实。",
        },
        "orderFacts": order,
        "logisticsFacts": logistics,
        "policyEvidence": policy,
        "evidenceSources": sources,
        "confidence": {"level": confidence, "meaning": "证据充分程度，非统计概率"},
        "recommendedActions": actions,
        "approvalRequired": status in {"UNCERTAIN", "CONFLICT"}
        or any(a["approvalRequired"] for a in actions),
        "executionAllowed": False,
        "checkedAt": now.isoformat(),
    }


def render_diagnosis(report: dict) -> str:
    if report.get('listOnly'):
        ids=report['orderFacts'].get('orderOptions') or []
        return ('本人订单列表：\n'+'\n'.join(ids)+'\n可选择订单号继续查询详情或物流。本次未修改订单。') if ids else '当前登录账号暂无订单。'
    if report.get('requestedOperation') in {'EXCHANGE_GUIDANCE','CANCEL_ORDER_GUIDANCE'}:
        action='换货' if report['requestedOperation']=='EXCHANGE_GUIDANCE' else '取消订单'
        if report['requestedOperation']=='EXCHANGE_GUIDANCE':
            return f"已识别换货需求；订单：{report.get('orderId') or '请补充订单号'}。核实本人订单后，可在下方生成待确认的人工换货方案；由本人确认后提交管理员审核。本次没有提交申请、退款或发货，人工处理结果不代表已实际补发商品。"
        return f"已识别{action}需求；订单：{report.get('orderId') or '请补充订单号'}。请先核实本人订单及商品状态，再从订单详情中的相应入口确认操作；本次未提交申请、取消订单或执行退款。当前案件退款履约只支持仅退款、退货退款，不会将换货伪装成退款申请。"
    if report.get('requestedOperation') == 'RETURN_GUIDANCE':
        order = report.get('orderFacts') or {}
        if order.get('queryStatus') != 'SUCCESS':
            if order.get('queryStatus')=='MISSING_ORDER_ID':
                options=order.get('orderOptions') or []
                return '已识别退货或退款需求，请选择要办理的本人订单号。'+('可选订单：'+'、'.join(options)+'。' if options else '暂未取得可选订单，请提供订单号或稍后重试。')+'不会自动选择订单；补充后继续核实，本次没有提交申请或退款。'
            return '暂未核实该订单属于当前登录用户。请核对订单号和登录账号，核实后才能生成售后方案；本次没有提交申请或退款。'
        data = order.get('data') or {}
        status = data.get('orderStatus')
        instruction = ('订单尚未发货，可提交仅退款申请。' if status == 1 else
                       '订单已发货，请先申请退货退款，等待审核给出的退货地址及要求，不要自行寄回。' if status == 2 else
                       '请结合订单状态与真实原因选择退款或退货退款，是否符合条件由业务校验和审核确定。')
        return '\n'.join([
            f"订单：{report.get('orderId') or '待核实'}",
            instruction,
            '在下方点击“生成待确认的售后方案”，填写真实原因、核对方案后确认提交。',
            '若已提交，直接查看现有申请进度；待管理员审核不是退款失败，也不代表已经退款。',
            '审核通过后按方案办理；需要退货的须物流登记和验收。真实资金到账以支付渠道退款结果为准，本助手不会自动划款。',
            '适用条件及完整政策原文可展开查看；法规不等于商城额外承诺。',
        ])
    diagnosis = report["diagnosis"]
    lines = [
        f"售后咨询：{ {'LOGISTICS_STAGNATION':'物流更新','UNSHIPPED_ORDER':'待发货订单','PAYMENT_ANOMALY':'支付状态核实','REFUND_PROGRESS':'退款进度','PRODUCT_QUALITY':'商品质量','AFTERSALES_CONSULT':'售后规则'}.get(report['caseType'],'待核实问题')}；订单：{report.get('orderId') or '待确认'}",
        f"判断：{ {'CONFIRMED':'有业务证据支持','UNCERTAIN':'仍需核实','NO_ANOMALY':'尚未发现可确认的异常'}.get(diagnosis['status'],'证据不足，需人工核实')}",
    ]
    lines += diagnosis["reasons"] + diagnosis["conflicts"] + diagnosis["uncertainties"]
    if report.get('requestedOperation')=='RETURN_GUIDANCE':
        lines.insert(0,'办理指引：打开“我的订单”中的该订单详情，查看可用退款/售后入口，选择商品与真实原因并核对申请；未发货与已发货的处理不同，未经确认不要自行寄回。是否符合办理条件须业务校验和人工审核，本次没有提交申请或执行退款。')
    lines += ["建议：" + a["title"] for a in report["recommendedActions"]]
    order = report.get("orderFacts") or {}
    if order.get("listStatus") == "SERVICE_ERROR":
        lines.append("本人订单列表查询失败，不能据此认定没有订单。请稍后重试或提供订单号。")
    elif order.get("queryStatus") == "MISSING_ORDER_ID":
        if order.get("listStatus") == "SUCCESS":
            options = order.get("orderOptions") or []
            lines.append("本人订单候选：" + "、".join(options) + "。请选择要查询的订单号，不会自动选择其中一笔。" if options else "本人订单列表为空，请核实登录账号或提供订单号。")
    policy = report["policyEvidence"]
    if policy.get("status") != "SKIPPED":
        lines.append(render_policy(policy, concise=True))
    lines.append("本报告仅供建议，不执行退款、支付或其他订单变更。")
    return "\n".join(lines)
