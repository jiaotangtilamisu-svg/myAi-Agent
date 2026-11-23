"""Shopping adapter for the existing chat transport; no order/payment executors."""

import html
import json
import re

import structlog

from app.auth.agent_context import require_agent_user
from app.services.agent_runtime import is_cancelled, parse_agent_message
from app.services.message_service import agent_message_service as agent_message_service
from app.services.stream_service import stream_service as stream_service
from app.shopping import store
from app.shopping.graph import build_shopping_graph
from app.utils.biz_payload import build_product_payload, build_product_search_message

logger = structlog.get_logger()


def safe(value):
    text = html.escape(str(value))
    return re.sub(r"([\\`*_{}\[\]|])", r"\\\1", text).replace("\n", " ")

def render_comparison(result):
    rows=result.get('comparison') or []
    if len(rows)<2:return result.get('clarification') or '目前没有两款可核实的商品，请先推荐商品后再指定比较对象。'
    def price(row):
        a,b=row.get('priceMin'),row.get('priceMax')
        return '价格未知' if a is None or b is None else str(a)+'元' if a==b else str(a)+'～'+str(b)+'元'
    def inventory(row):
        return '；'.join(str(s.get('sku_name') or '规格待确认')+'：'+('库存'+str(s['stock']) if s.get('stock') is not None and s.get('stock_query_status')=='SUCCESS' else '库存待确认') for s in (row.get('skus') or [])[:6]) or '库存待确认'
    fields=[('售价范围',price),('规格及库存',inventory),('已核实属性',lambda r:'；'.join(k+'：'+'、'.join(v) for k,v in r.get('attributes',{}).items()) or '属性未知'),('在售状态',lambda r:{'ON_SALE':'在售','OFF_SHELF':'已下架'}.get(r.get('productStatus'),'待核实'))]
    lines=[f'比较上一轮指定的 {len(rows)} 款商品，保持原顺序；价格和库存已重新查询。','| 对比项 | '+' | '.join(safe(r.get('productName')) for r in rows)+' |','| --- | '+' | '.join('---' for _ in rows)+' |']
    lines.extend('| '+label+' | '+' | '.join(safe(fn(r)) for r in rows)+' |' for label,fn in fields)
    if all(r.get('priceMin') is not None for r in rows):
        from decimal import Decimal
        cheapest=min(rows,key=lambda r:Decimal(r['priceMin']))
        difference=max(Decimal(r['priceMin']) for r in rows)-Decimal(cheapest['priceMin'])
        lines.append('仅比较已核实的起售价，'+safe(cheapest['productName'])+'最低；这些商品起售价最大相差'+format(difference,'.2f')+'元。起售价对应的规格可能不同，不代表性能优劣。')
    lines.append('未提供的性能、续航等属性不能据此判断优劣；最低价可能对应不同规格，请按相同配置核对。')
    return '\n'.join(lines)


def render(result):
    if result.get('isComparison'):return render_comparison(result)
    status = result["status"]
    messages = {
        "NEEDS_CLARIFICATION": result.get("clarification"),
        "NO_RESULTS": "未召回真实商品，请换一个关键词；不会补造商品凑数。",
        "NO_MATCHING_SKU": "当前没有来源已核实且符合条件的商品可推荐；不会用演示或测试商品替代。",
        "TOOL_ERROR": "商品工具查询失败，暂时无法核实商品、价格与库存，请稍后重试。",
        "CONTEXT_UNAVAILABLE": "购物上下文暂不可用，本轮未保存推荐，请稍后重试。",
        "SHOPPING_BUSY": "上一轮导购仍在处理，请等待完成后再追加条件。",
    }
    lines = [
        messages.get(status)
        or "以下依据实时业务查询结果比较，评分只表示证据完整度与条件匹配。"
    ]
    if result.get("dataMode", "DEMO") == "DEMO":
        lines.insert(0, "当前为演示商品环境；以下数据库记录不代表真实商业商品，来源未登记的资料不作为真实数据。")
    req = result.get("requirements") or {}
    count = len(result.get("recommendations", []))
    if count:
        wanted = req.get("requestedCount", 3)
        lines.append(f"找到 {count} 款符合本次条件的商品。" + (f"当前仅有这 {count} 款，不足所需的 {wanted} 款。" if count < wanted else ""))
    if req.get("cheaperThan"):
        lines.append(
            "本轮筛选价格低于上轮最低已知价格 "
            + safe(req["cheaperThan"])
            + " 元的 SKU。"
        )
    if req.get("batteryAboveHours"):
        lines.append(
            "本轮要求标称续航高于上轮最大已知值 "
            + safe(req["batteryAboveHours"])
            + " 小时；测试条件是否相同仍需核实。"
        )
    from app.shopping.explanations import explain_unmatched
    explanation=explain_unmatched(result)
    if explanation:lines.append(explanation)
    for item in result.get("recommendations", []):
        price = item["price"]
        value = (
            price["min"] + "～" + price["max"] + "元"
            if price["min"] is not None
            else "价格未知"
        )
        lines.append(
            "\n**"
            + safe(item["productName"])
            + "**："
            + safe(value)
            + "；"
            + (
                "存在已核实有货规格"
                if item["availability"] == "IN_STOCK"
                else "库存待确认"
            )
        )
        attrs = item["attributes"]
        lines.append(
            "属性："
            + (
                safe("；".join(k + ":" + "/".join(v) for k, v in attrs.items()))[:700]
                if attrs
                else "未知"
            )
        )
        lines.extend("推荐依据：" + safe(r) for r in item["reasons"])
        lines.extend("优势依据：" + safe(r) for r in item["advantages"])
        lines.extend("不足/待核实：" + safe(r) for r in item["limitations"])
        for sku in item["eligibleSkus"][:6]:
            count = (
                "库存" + str(sku["stock"])
                if sku["stock"] is not None
                else "库存未知（"
                + {
                    "UNAVAILABLE": "库存服务暂不可用",
                    "MISSING": "未找到库存记录",
                    "INVALID_RESPONSE": "库存响应异常",
                }.get(sku.get("stock_query_status"), "等待核实")
                + "）"
            )
            lines.append(
                "规格："
                + safe(sku.get("sku_name") or "标准规格")[:200]
                + "；"
                + safe(sku["price"] + "元" if sku["price"] is not None else "价格未知")
                + "；"
                + safe(count)
            )
        if len(item["eligibleSkus"]) > 6:
            lines.append("更多规格请查看商品详情。")
        names={"verifiedAvailableSku":"有货规格","knownSkuPrice":"价格明确","matchedRequiredAttributes":"规格匹配","explicitSceneMatches":"标称场景匹配","preferredBrandMatches":"优先品牌匹配","preferredAttributeMatches":"优先属性匹配"}
        lines.append("匹配分："+str(item["score"]["total"])+"；构成："+"；".join(names[k]+" "+str(v) for k,v in item["score"]["components"].items()))
        lines.append("查询时间：" + safe(item.get("queryTime") or result["queryTime"]))
    if result.get("comparison"):
        lines.append("\n对比（商品标称属性，无数据不推测）：")
        for row in result["comparison"][:8]:
            attrs = row["attributes"]
            range_text = (
                row["priceMin"] + "～" + row["priceMax"] + "元"
                if row["priceMin"] is not None and row["priceMax"] is not None
                else "价格未知"
            )
            lines.append(
                safe(row.get("productName") or row["productId"])
                + "：状态 "
                + {
                    "ON_SALE": "在售",
                    "OFF_SHELF": "已下架",
                    "DELETED": "已删除",
                    "NOT_FOUND": "不存在",
                }.get(row["productStatus"], "未知")
                + "；商品全规格价格区间 "
                + safe(range_text)
                + "；属性 "
                + safe(json.dumps(attrs, ensure_ascii=False) if attrs else "未知")[:500]
            )
            for sku in row["skus"][:3]:
                count = (
                    sku.get("stock")
                    if sku.get("stock_query_status") == "SUCCESS"
                    else None
                )
                lines.append(
                    "  规格："
                    + safe(sku.get("sku_name") or "未知")[:100]
                    + "；"
                    + ("库存未知" if count is None else "库存" + str(count))
                )
    lines.append(
        "只提供导购建议，不下单、不支付；价格和库存以查询时点为准，购买前需重新核实。"
    )
    return "\n".join(lines)


def card_rows(result):
    rows = []
    for item in result.get("recommendations", []):
        rows.append(
            {
                "product_id": item["productId"],
                "product_name": item["productName"][:160],
                "data_provenance": item.get("dataProvenance"),
                "cover": item.get("cover"),
                "min_price": item["price"]["min"],
                "max_price": item["price"]["max"],
                "price_status": "KNOWN" if item["price"]["complete"] else "UNKNOWN",
                "product_status": "ON_SALE",
                "availability": item["availability"],
                "sku_complete": False,
                "skus": item.get("eligibleSkus", []),
                "recommendation_reasons": item.get("reasons", []),
                "product_observed_at": item.get("queryTime"),
                "data_class": item.get("dataClass", "UNKNOWN"),
            }
        )
    return rows


async def run_shopping_agent(agent_msg, *, collect_only: bool = False):
    user_id = require_agent_user(agent_msg["userId"]).user_id
    message_id = agent_msg["messageId"]
    token = None
    result = None
    try:
        token = await store.acquire(user_id)
        previous = await store.load(user_id)
        _, text = parse_agent_message(agent_msg)
        state = await build_shopping_graph().ainvoke(
            {
                "user_id": user_id,
                "message_id": message_id,
                "text": text,
                "previous": previous,
            }
        )
        result = state["result"]
        if result["status"] == "CANCELLED" or await is_cancelled(user_id, message_id):
            return {"status": "CANCELLED"} if collect_only else None
        recommendations = result["recommendations"]
        context = {
            "requirements": previous.get('requirements',result['requirements']) if result.get('isComparison') else result["requirements"],
            "ids": previous.get("ids", []),
            "baseline": previous.get("baseline", []),
        }
        if recommendations and not result.get('isComparison'):
            context["ids"] = [p["productId"] for p in recommendations]
            context["baseline"] = [
                {"price": p["price"]["min"], "batteryHours": p["batteryHours"]}
                for p in recommendations
            ]
        elif context["requirements"].get("category") != (
            previous.get("requirements") or {}
        ).get("category") or re.search(r"重新选|清空条件|重新开始", text):
            context["ids"], context["baseline"] = [], []
        await store.save(user_id, token, message_id, context, result)
    except ValueError as exc:
        result = {
            "status": "SHOPPING_BUSY"
            if str(exc) == "SHOPPING_BUSY"
            else "CONTEXT_UNAVAILABLE"
        }
    except Exception as exc:  # noqa: BLE001 -- Never publish stale facts or provider exception details.
        logger.warning('shopping_context_failed', message_id=message_id, error_type=type(exc).__name__)
        result = {"status": "CONTEXT_UNAVAILABLE"}
    finally:
        if token:
            try:
                await store.release(user_id, token)
            except Exception:  # noqa: BLE001 -- The expiring lock is a safety net, no force deletion.
                logger.warning("shopping_context_release_failed", message_id=message_id)
    if collect_only:
        return result
    text = render(result)
    cards, _ = build_product_payload(card_rows(result))
    assistant = (
        build_product_search_message(text, cards)
        if result.get("recommendations")
        else text
    )
    kind = "product_search" if result.get("recommendations") else "agent"
    # Persist the verified report as well as cache it: Redis expiry must not lose evidence.
    metadata = json.dumps(
        {
            "agentType": "shopping",
            "fullReport": result,
            "status": result["status"],
            "messageId": message_id,
            "productIds": [p["productId"] for p in result.get("recommendations", [])],
            "executionAllowed": False,
        },
        ensure_ascii=False,
    )
    from app.services.agent_runtime import _persist_and_notify
    await _persist_and_notify(agent_msg, assistant, kind, metadata)
