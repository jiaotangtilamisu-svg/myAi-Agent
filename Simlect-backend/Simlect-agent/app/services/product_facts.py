"""Agent product facts: unknown stays unknown; all user-visible numbers come from Java reads."""

import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation


def camelize(value):
    if isinstance(value, list):
        return [camelize(v) for v in value]
    if isinstance(value, dict):
        return {
            re.sub(r"_([a-z])", lambda m: m[1].upper(), k): camelize(v)
            for k, v in value.items()
        }
    return value


def restore_product_query(value):
    if not isinstance(value, dict):
        return None

    def snake(data):
        if isinstance(data, list):
            return [snake(v) for v in data]
        if isinstance(data, dict):
            return {
                re.sub(r"(?<!^)(?=[A-Z])", "_", k).lower(): snake(v)
                for k, v in data.items()
            }
        return data

    return {**value, "products": snake(value.get("products", []))}


def money(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return str(number) if number.is_finite() and number >= 0 else None
    except (InvalidOperation, ValueError):
        return None


def stock(value):
    return value if type(value) is int and value >= 0 else None


def normalize_product(row: dict) -> dict:
    """Input has recursively normalized snake_case keys from the internal Java client."""
    p = dict(row)
    from app.services.data_provenance import provenance
    p['data_provenance'] = provenance(p.get('data_provenance'))
    p["min_price"], p["max_price"] = (
        money(p.get("min_price")),
        money(p.get("max_price")),
    )
    p["price_status"] = (
        "KNOWN"
        if p["min_price"] is not None and p["max_price"] is not None
        else "UNKNOWN"
    )
    p["product_status"] = {1: "ON_SALE", 0: "OFF_SHELF", -1: "DELETED"}.get(
        p.get("status") if type(p.get("status")) is int else None, "UNKNOWN"
    )
    skus = []
    for raw in p.get("skus") or []:
        s = dict(raw)
        s["price"] = money(s.get("price"))
        s["price_status"] = "KNOWN" if s["price"] is not None else "UNKNOWN"
        s["stock"] = (
            stock(s.get("stock")) if s.get("stock_query_status") == "SUCCESS" else None
        )
        if s["stock"] is None and s.get("stock_query_status") == "SUCCESS":
            s["stock_query_status"] = "INVALID_RESPONSE"
        s["availability"] = (
            "UNKNOWN"
            if s["stock"] is None
            else "IN_STOCK"
            if s["stock"] > 0
            else "OUT_OF_STOCK"
        )
        skus.append(s)
    p["skus"] = skus
    complete = p.get("sku_complete") is True
    known = bool(skus) and complete and all(s["stock"] is not None for s in skus)
    p["total_stock"] = sum(s["stock"] for s in skus) if known else None
    failures = {s.get("stock_query_status") for s in skus} - {"SUCCESS"}
    p["stock_query_status"] = (
        "SUCCESS"
        if known
        else "UNAVAILABLE"
        if "UNAVAILABLE" in failures
        else "INVALID_RESPONSE"
        if "INVALID_RESPONSE" in failures
        else "MISSING"
        if "MISSING" in failures
        else "UNKNOWN"
    )
    p["availability"] = (
        "NOT_SALEABLE"
        if p["product_status"] != "ON_SALE"
        else "UNKNOWN"
        if not known
        else "IN_STOCK"
        if p["total_stock"] > 0
        else "OUT_OF_STOCK"
    )
    return p


def query_result(products=None, *, status="SUCCESS", source=None, message=None):
    return {
        "schemaVersion": 2,
        "queryStatus": status,
        "queryTime": datetime.now(UTC).isoformat(),
        "retrievalSource": source,
        "products": products or [],
        "message": message,
    }


def failure_result():
    return query_result(
        status="SERVICE_ERROR",
        message="商品查询服务暂时不可用，无法核实价格、SKU 和库存，请稍后重试。",
    )


def render_facts(data: dict) -> str:
    if data.get("queryStatus") == "SERVICE_ERROR":
        return failure_result()["message"]
    if not data.get("products"):
        return "商品不存在或未找到相关商品。"
    lines = []
    if data.get("retrievalSource") in {"hot_sale", "browse"}:
        lines.append("以下为另荐商品，不代表与原搜索关键词匹配。")
    for p in data["products"]:
        if (
            p.get("query_status") == "NOT_FOUND"
            or p.get("product_status") == "NOT_FOUND"
        ):
            lines.append("商品不存在。")
            continue
        status = {"ON_SALE": "在售", "OFF_SHELF": "已下架", "DELETED": "已删除"}.get(
            p.get("product_status"), "商品状态未知"
        )
        price = (
            f"{p['min_price']}～{p['max_price']}元"
            if p.get("price_status") == "KNOWN"
            else "价格暂时未知"
        )
        lines.append(
            f"商品：{p.get('product_name') or p.get('product_id')}；{status}；{price}。"
        )
        for s in p.get("skus") or []:
            value = f"{s['price']}元" if s.get("price") is not None else "价格未知"
            reason = {
                "UNAVAILABLE": "库存服务暂时不可用",
                "MISSING": "未找到库存记录",
                "INVALID_RESPONSE": "库存响应异常",
            }.get(s.get("stock_query_status"), "暂时无法核实")
            count = (
                f"库存未知（{reason}）"
                if s.get("stock") is None
                else f"库存{s['stock']}（{'缺货' if s['stock'] == 0 else '有货'}）"
            )
            lines.append(
                f"{s.get('sku_name') or '标准规格'}：{value}；{count}。"
            )
        if not p.get("skus"):
            lines.append("SKU 信息暂不可用，库存未知。")
        lines.append(
            f"查询时间：{p.get('product_observed_at') or data.get('queryTime')}。库存以下单时为准。"
        )
    return "\n".join(lines)


def requires_product_facts(text: str, intent=None, card=None) -> bool:
    # A service-side rule, independent of whether the model chooses to call a tool.
    if str(intent or "").upper() in {"PRODUCT_SEARCH", "PRODUCT_CONSULT"}:
        return True
    if str(intent or "").upper() not in {"", "CHAT"}:
        return False
    if re.search(
        r"价格|价钱|多少钱|售价|库存|有货|缺货|现货|SKU|sku|规格|商品|产品|搜[索一下]|推荐|同款|类似|下架|上架",
        text or "",
    ):
        return True
    return bool(card) and bool(
        re.search(r"这款|这个|它|还有吗|几件|几台|几双", text or "")
    )
