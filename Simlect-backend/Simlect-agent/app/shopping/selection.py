"""SKU-consistent filtering and evidence-completeness scores, not quality ratings."""

import re
from decimal import Decimal
from collections import Counter

from app.services.product_facts import money, stock
from app.shopping.requirements import BRANDS, CATEGORIES
from app.services.data_provenance import classification


def name_key(name):
    name = str(name or "")
    if any(k in name for k in ("存储容量","机身存储","存储空间","硬盘","ROM")):return "存储容量"
    for key in ("颜色", "内存", "续航", "品牌", "适用场景", "降噪", "材质", "尺寸","处理器","容量","功率","耳机类型","连接方式"):
        if key in name:
            return key
    return name


def properties(rows, sku=False):
    result = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = name_key(row.get("name") if sku else row.get("property_name"))
        val = row.get("value") if sku else row.get("property_value")
        if key and isinstance(val, str) and val:
            result.setdefault(key, [])
            if val not in result[key]:
                result[key].append(val)
    return result


def hours(attrs):
    values = attrs.get("续航") or []
    if len(values) != 1:
        return None
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*(?:小时|h)\s*", values[0], re.IGNORECASE
    )
    return match[1] if match else None


def attribute_equal(value, requested):
    # Exact values with a small unit normalization; no numeric substring matching.
    def clean(s):
        text=re.sub(r"\s", "", s).lower().replace("gb", "g").replace('毫升','ml').replace('千瓦','kw').replace('瓦','w')
        match=re.fullmatch(r'(\d+(?:\.\d+)?)(ml|升|l|kw|w)',text)
        if match:return str(Decimal(match[1])*(1000 if match[2] in {'升','l','kw'} else 1))+('ml' if match[2] in {'ml','升','l'} else 'w')
        return text

    return clean(value) == clean(requested)


def select(products: list[dict], req: dict, *, data_mode: str = "DEMO") -> dict:
    recommendations, excluded, comparison = [], [], []
    product_counts=Counter(str(p.get("product_id") or "") for p in products)
    for p in products:
        pid = str(p.get("product_id") or "")
        attrs = properties(p.get("property_values"))
        battery = hours(attrs)
        skus = p.get("skus") if isinstance(p.get("skus"), list) else []
        comparison.append(
            {
                "productId": pid,
                "productName": p.get("product_name"),
                "productStatus": p.get("product_status", "UNKNOWN"),
                "attributes": attrs,
                "skus": skus,
                "priceMin": money(p.get("min_price")),
                "priceMax": money(p.get("max_price")),
                "queryTime": p.get("product_observed_at"),
                "skuComplete": p.get("sku_complete") is True,
            }
        )
        reason = 'DUPLICATE_PRODUCT_FACTS' if product_counts[pid]>1 else None
        sku_ids=[s.get('sku_id') for s in skus if isinstance(s,dict)]
        if len(sku_ids)!=len(skus) or any(not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',v) for v in sku_ids) or len(set(sku_ids))!=len(sku_ids):reason='INVALID_SKU_IDENTITY' 
        data_class = classification(p.get("data_provenance"), pid)
        if (data_mode == "REAL" or req.get("requireRealData")) and data_class != "REAL":
            reason = "UNVERIFIED_LIVE_PROVENANCE"
        if (p.get('data_provenance') or {}).get('source_type') == 'PUBLIC_DATASET' and not (data_mode=='LOCAL_STORE' and data_class=='LOCAL_STORE' and not req.get('requireRealData')):
            reason = 'HISTORICAL_RECORD_NOT_LIVE'
        if data_mode=='LOCAL_STORE' and data_class not in {'REAL','LOCAL_STORE'}:
            reason='UNAPPROVED_CATALOGUE'
        if p.get("product_status") != "ON_SALE" or p.get("query_status") == "NOT_FOUND":
            reason = "NOT_ON_SALE"
        elif (
            len(skus) > 100
            or not isinstance(p.get("product_name"), str)
            or not p["product_name"]
        ):
            reason = "INCOMPLETE_PRODUCT"
        category_names = (
            str(p.get("category_name") or "")
            + " "
            + str(p.get("parent_category_name") or "")
        )
        # Specific business names can identify a leaf class when the DB only has
        # a broad parent category. Longest alias wins (电脑 must not match 笔记本电脑).
        name_categories = [(len(a), key) for key, aliases in CATEGORIES.items()
                           for a in aliases if a in str(p.get("product_name") or "")]
        named_category = max(name_categories, default=(0, None))[1]
        if req.get("category") == "手机" and (
            re.search(r"记录仪|摄像|监控|路由器|打印机|投影|音箱|支架|充电|贴膜|保护套|手机壳", str(p.get("product_name") or ""))
            or (p.get("category_name") and not re.search(r"手机|通讯", str(p.get("category_name"))))
        ):
            reason = reason or "CATEGORY_UNKNOWN_OR_MISMATCH"
        if req.get("category") == "手机" and re.search(r"手机壳|手机支架|手机贴膜|手机配件", str(p.get("product_name") or "")):
            reason = reason or "ACCESSORY_NOT_REQUESTED_PRODUCT"
        if req.get("categoryId") and str(p.get("category_id")) != req["categoryId"]:
            reason = reason or "CATEGORY_MISMATCH"
        if req.get("category") and (
            named_category is not None and named_category != req["category"]
            or named_category is None and not any(
                a in category_names for a in CATEGORIES.get(req["category"], (req["category"],))
            )
        ):
            reason = reason or "CATEGORY_UNKNOWN_OR_MISMATCH"
        keyword = req.get("keyword")
        if (
            keyword
            and keyword != req.get("category")
            and not all(
                t.lower() in str(p.get("product_name") or "").lower()
                for t in keyword.split()
            )
        ):
            reason = reason or "KEYWORD_MISMATCH"
        brand_values = attrs.get("品牌", [])
        evidence=p.get('brand_evidence') or {}
        if not brand_values and evidence.get('source') in {'PROPERTY_VALUE','PRODUCT_NAME_PREFIX'} and evidence.get('value') in BRANDS:
            brand_values=[evidence['value']]
            attrs={**attrs,'品牌':brand_values}

        def matches_brand(b, values=brand_values):
            aliases = BRANDS.get(b, (b,))
            return any(attribute_equal(v, a) for v in values for a in aliases)

        if req.get("brands") and not any(matches_brand(b) for b in req["brands"]):
            reason = reason or "BRAND_UNKNOWN_OR_MISMATCH"
        if req.get("excludeBrands") and (
            not brand_values or any(matches_brand(b) for b in req["excludeBrands"])
        ):
            reason = reason or "EXCLUDED_OR_UNKNOWN_BRAND"
        if req.get("batteryAboveHours") is not None and (
            battery is None or Decimal(battery) <= Decimal(req["batteryAboveHours"])
        ):
            reason = reason or "BATTERY_UNKNOWN_OR_INSUFFICIENT"
        if req.get("minBatteryHours") is not None and (
            battery is None or Decimal(battery) < Decimal(req["minBatteryHours"])
        ):
            reason = reason or "BATTERY_UNKNOWN_OR_INSUFFICIENT"
        lower, upper = money(p.get("min_price")), money(p.get("max_price"))
        eligible = []
        unknown_price = False
        sku_gaps=set()
        for s in skus:
            if not isinstance(s, dict):
                reason = reason or "INVALID_SKU"
                continue
            price = money(s.get("price"))
            if (
                price is not None
                and lower is not None
                and upper is not None
                and not Decimal(lower) <= Decimal(price) <= Decimal(upper)
            ):
                reason = reason or "PRICE_CONFLICT"
            specs = properties(s.get("specifications"), sku=True)
            satisfies = True
            if req.get("excludeColors"):
                colors = specs.get("颜色") or attrs.get("颜色") or []
                if len(colors) != 1 or colors[0] in req["excludeColors"]:
                    satisfies = False
            for key, wanted in req.get("attributes", {}).items():
                values = specs.get(key) if key in specs else attrs.get(key, [])
                if len(values) != 1 or not attribute_equal(values[0], wanted):
                    satisfies = False
            if not satisfies:
                sku_gaps.add("SKU_ATTRIBUTES")
                continue
            has_budget = any(
                req.get(k) is not None
                for k in ("budgetMin", "budgetMax", "cheaperThan")
            )
            if price is None and (has_budget or "便宜" in req.get("preferences", [])):
                unknown_price = True
                sku_gaps.add("UNKNOWN_PRICE_FOR_BUDGET")
                continue
            if price is not None:
                if req.get("budgetMin") is not None and Decimal(price) < Decimal(
                    req["budgetMin"]
                ):
                    sku_gaps.add("PRICE_RANGE")
                    continue
                if req.get("budgetMinExclusive") and req.get("budgetMin") is not None and Decimal(price)==Decimal(req["budgetMin"]):sku_gaps.add("PRICE_RANGE");continue
                if req.get("budgetMax") is not None and Decimal(price) > Decimal(
                    req["budgetMax"]
                ):
                    sku_gaps.add("PRICE_RANGE")
                    continue
                if req.get("budgetMaxExclusive") and Decimal(price) == Decimal(
                    req["budgetMax"]
                ):
                    continue
                if req.get("cheaperThan") is not None and Decimal(price) >= Decimal(
                    req["cheaperThan"]
                ):
                    continue
            count = (
                stock(s.get("stock"))
                if s.get("stock_query_status") == "SUCCESS"
                else None
            )
            if count == 0 or (req.get("requireInStock") and count is None):
                sku_gaps.add("NO_STOCK" if count==0 else "STOCK_UNAVAILABLE" if s.get("stock_query_status")=="UNAVAILABLE" else "STOCK_UNKNOWN")
                continue
            eligible.append(
                {
                    **s,
                    "price": price,
                    "stock": count,
                    "stock_query_status": "INVALID_RESPONSE"
                    if count is None and s.get("stock_query_status") == "SUCCESS"
                    else s.get("stock_query_status")
                    if count is None
                    else "SUCCESS",
                    "availability": "IN_STOCK" if count is not None else "UNKNOWN",
                }
            )
        if not eligible:
            reason = reason or (
                "UNKNOWN_PRICE_FOR_BUDGET" if unknown_price else "NO_ELIGIBLE_SKU"
            )
        if reason:
            excluded.append({"productId": pid, "reason": reason,"failureReasons":sorted(sku_gaps)})
            continue
        known_prices = [Decimal(s["price"]) for s in eligible if s["price"] is not None]
        availability = (
            "IN_STOCK"
            if any(s["stock"] is not None and s["stock"] > 0 for s in eligible)
            else "UNKNOWN"
        )
        scene_matches = [
            s
            for s in req.get("scenes", [])
            if any(s in v for v in attrs.get("适用场景", []))
        ]
        components = {
            "verifiedAvailableSku": 2 if availability == "IN_STOCK" else 0,
            "knownSkuPrice": 1 if known_prices else 0,
            "matchedRequiredAttributes": len(req.get("attributes", {})),
            "explicitSceneMatches": len(scene_matches),
            "preferredBrandMatches": int(any(matches_brand(b) for b in req.get("preferredBrands",[]))),
            "preferredAttributeMatches": sum(any(attribute_equal(v,w) for v in attrs.get(k,[]) + [v for sku in eligible for v in properties(sku.get("specifications"),sku=True).get(k,[])]) for k,w in req.get("preferredAttributes",{}).items()),
        }
        warnings = []
        if availability == "UNKNOWN":
            warnings.append("库存待确认；不能作为现货承诺")
        if len(known_prices) != len(eligible):
            warnings.append("部分或全部 SKU 价格未知")
        if not attrs:
            warnings.append("商品属性缺失，性能及适用场景未知")
        if p.get("sku_complete") is not True:
            warnings.append("SKU 列表不完整，未展示规格仍需核实")
        reasons = ["商品在售；价格仅依据符合条件的同一 SKU"]
        if req.get("category") or req.get("categoryId"):
            reasons.append("匹配 Java 返回的实际品类")
        if components["preferredBrandMatches"]:reasons.append("符合优先品牌偏好（非必选条件）")
        if components["preferredAttributeMatches"]:reasons.append("符合部分优先属性偏好（非必选条件）")
        if req.get("brands"):
            reasons.append("匹配实际品牌属性：" + "/".join(req["brands"]))
        if req.get("attributes"):
            reasons.append("匹配规格：" + "；".join(str(k)+"："+str(v) for k,v in req["attributes"].items()))
        if len(scene_matches) < len(req.get("scenes", [])):
            warnings.append("部分使用场景没有业务属性支持，适用性待确认")
        for pref in req.get("preferences", []):
            if pref not in {"便宜", "续航"} and pref not in attrs:
                warnings.append(pref + "缺少可核实属性")
        price_min = str(min(known_prices)) if known_prices else None
        price_max = str(max(known_prices)) if known_prices else None
        recommendations.append(
            {
                "productId": pid,
                "productName": p["product_name"],
                "cover": p.get("cover"),
                "price": {
                    "min": price_min,
                    "max": price_max,
                    "complete": len(known_prices) == len(eligible),
                },
                "attributes": attrs,
                "categoryName": p.get("category_name"),
                "dataProvenance": p.get("data_provenance"),
                "brandEvidence": evidence,
                "dataClass": data_class,
                "skus": skus,
                "eligibleSkus": eligible,
                "availability": availability,
                "productStatus": "ON_SALE",
                "reasons": reasons,
                "advantages": ["存在已核实有货 SKU"]
                if availability == "IN_STOCK"
                else [],
                "limitations": warnings,
                "matchStatus": "CONDITIONAL" if warnings else "VERIFIED",
                "sceneMatches": scene_matches,
                "score": {
                    "total": sum(components.values()),
                    "components": components,
                    "meaning": "事实完整度及明确条件匹配分，非质量/销量/用户评价评分",
                },
                "queryTime": p.get("product_observed_at"),
                "batteryHours": battery,
                "source": p.get("sources")
                or {"product": "Java Product", "stock": "Java Stock"},
            }
        )
    recommendations.sort(
        key=lambda r: (
            -max((s.get("stock") or 0 for s in r["eligibleSkus"]), default=0)
            if "库存充足" in req.get("preferences", []) else 0,
            Decimal(r["price"]["min"])
            if "便宜" in req.get("preferences", []) and r["price"]["min"] is not None
            else Decimal("Infinity")
            if "便宜" in req.get("preferences", [])
            else 0,
            -r["score"]["total"],
            Decimal(r["price"]["min"])
            if r["price"]["min"] is not None
            else Decimal("Infinity"),
            r["productId"],
        )
    )
    return {
        "recommendations": recommendations[:min(12, max(1, int(req.get("requestedCount", 3))))],
        "matchingCount": len(recommendations),
        "excluded": excluded,
        "comparison": comparison,
    }
