"""Aftersales policy evidence is quoted, never completed by a language model."""

import re
from datetime import datetime, timezone


def catalog_eligible(doc: dict, category: str | None = None) -> bool:
    """Fail closed on missing governance metadata; industry examples aren't shop rules."""
    if doc.get("category") not in {"LAW", "INDUSTRY_REFERENCE", "PLATFORM_DEMO"}:
        return False
    if doc.get("sourceStatus") != "VALID":
        return False
    if category and doc.get("category") != category:
        return False
    if not category and doc.get("category") == "INDUSTRY_REFERENCE":
        return False
    try:
        start = datetime.fromisoformat(doc["effectiveFrom"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(doc["effectiveUntil"].replace("Z", "+00:00")) if doc.get("effectiveUntil") else None
        now = datetime.now(timezone.utc)
        return start.tzinfo is not None and start <= now and (end is None or end.tzinfo is not None and now < end)
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def needs_policy(text: str, intent=None) -> bool:
    return str(intent or "").upper() == "REFUND" or bool(
        re.search(
            r"售后|退货|退款|换货|保修|维修|退换|运费|能退|可退|可以退|支持退|能换|能不能退|能不能换",
            text or "",
        )
    )


def is_policy_question(text: str) -> bool:
    if re.search(
        r"我的订单|这笔订单|订单号|退款进度|退款状态|物流状态", text or ""
    ) and not re.search(r"政策|规则|标准|条件|规定", text or ""):
        return False
    if (text or "").strip() in {"售后", "退换货", "保修"}:
        return True
    return needs_policy(text) and bool(
        re.search(
            r"政策|规则|规定|条件|说明|须知|几天|多久|多少|如何|怎么|咋|能否|是否|能不能|能退|可退|支持退|谁|流程|期限|[吗么？?]|售后服务",
            text or "",
        )
    )


def policy_result(status: str, hits=None, **extra) -> dict:
    return {"status": status, "hits": hits or [], **extra}


def render_policy(result: dict, *, concise: bool = False) -> str:
    messages = {
        "RETRIEVAL_ERROR": "售后知识检索发生异常，暂时无法核实政策，请稍后重试。",
        "NO_MATCH": "当前没有检索到已确认的相关售后政策，无法确定适用规则。请联系人工客服核实。",
        "LOW_RELEVANCE": "检索结果相关度不足，不能据此判断售后规则。请补充问题或联系人工客服。",
        "EMBEDDING_FAILED": "售后知识向量化服务暂不可用，无法核实政策，请稍后重试。",
        "ES_UNAVAILABLE": "售后知识检索服务暂不可用，无法核实政策，请稍后重试。",
        "CATALOG_UNAVAILABLE": "无法验证售后文档的当前发布状态，暂不能将检索内容作为政策依据。",
    }
    if result.get("status") != "SUCCESS" or not result.get("hits"):
        return messages.get(result.get("status"), messages["NO_MATCH"]) + ("仅凭当前信息不能承诺退换货。" if concise else "")
    if concise:
        from app.rag.evidence_quality import rank_evidence, display_groups, section_label
        query = result.get("query", "")
        hits = rank_evidence(query, result["hits"], 3)
        if not hits:
            return messages["NO_MATCH"]
        if re.search(r"七天|7天|七日|超过", query):
            answer = "仅凭超过七天不能确认是否可退；不能把七日无理由退货视为所有商品、所有情形均适用，也不能据此直接承诺或拒绝退货。"
        elif "换货" in query:
            answer = "是否可换货仍需核对商品问题与适用条款；本次仅查询政策，没有提交换货申请。"
        else:
            answer = "已找到以下相关政策依据；具体订单是否适用仍需核实，不代表已经批准售后。"
        lines = [answer, "适用依据（原文节选；完整条款请展开政策证据）："]
        for i, h in enumerate(display_groups(hits), 1):
            excerpt = h["text"].replace("\n", " ")
            excerpt = re.sub(r'^'+re.escape(section_label(h['section']))+r'[\s　]*','',excerpt)
            lines.append(f"[{i}] {h['documentName']} / 版本：{h['revision']} / {section_label(h['section'])}：{excerpt[:180]}" + ("…（节选）" if len(excerpt) > 180 else ""))
            lines.append(f"来源：{h.get('originalUrl') or h['source']}")
        kinds = {h.get("category") for h in hits}
        if "LAW" in kinds:
            lines.append("国家法规与商城自有承诺不同；本库未收录的引用法律或商城规则无法在此确认。")
        if "PLATFORM_DEMO" in kinds:
            lines.append("平台自有演示规则，不代表真实商业服务承诺。")
        if "INDUSTRY_REFERENCE" in kinds:
            lines.append("行业参考，不作为本商城办理规则。")
        lines.append("无理由退货与质量问题的退换修需要分别核实，不能仅因超过七天排除其他售后权利。还需核实：是否网购、商品类别及不适用例外、交付与通知时间、是否拆封或影响完好、质量证据以及商城额外承诺。可提供这些信息或联系人工客服；Agent不执行退款。")
        return "\n".join(lines)
    lines = ["以下仅引用已确认政策的相关原文片段，不代表已满足具体订单的办理条件："]
    for i, hit in enumerate(result["hits"], 1):
        page = f"，第{hit['page']}页" if hit.get("page") else ""
        match_label = "条款关键词命中（非向量相似度）" if result.get('ranking')=='verified_exact_topic_browse' else f"相关度 {hit['score']:.3f}"
        lines.append(
            f"[{i}] {hit['documentName']} / {hit['section']}{page}（{match_label}）"
        )
        # Prefix every line as a quotation, including content that resembles instructions.
        lines.extend("> " + line for line in hit["text"].splitlines())
        lines.append(
            f"来源：{hit['source']}；版本：{hit['revision']}；文档ID：{hit['documentId']}"
        )
        if hit.get("category") == "INDUSTRY_REFERENCE":
            lines.append("行业对标参考，不是Simlect商城办理规则，不能据此承诺售后权益。")
        elif hit.get("category") == "PLATFORM_DEMO":
            lines.append("平台自有演示规则，不代表真实商业服务承诺。")
        if hit.get("issuer") or hit.get("originalUrl"):
            lines.append(f"发布机构：{hit.get('issuer') or '未知'}；原始网址：{hit.get('originalUrl') or '未提供'}")
    lines.append("退款等操作仍须经过原业务接口校验和人工确认；客服 Agent 不执行退款。")
    return "\n".join(lines)
