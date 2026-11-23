"""商品搜索服务模块：混合检索（关键词+向量 RRF）、品类/热销兜底，及搜索工具消息格式化。"""

import re  # import statement — 正则表达式
import structlog  # import statement — 结构化日志

from app.constants import PRODUCT_CANDIDATE_SIZE, PRODUCT_RESULT_SIZE, PRODUCT_STATUS_ON_SALE  # import statement — 检索常量
from app.domain.intent.rules import looks_like_browse_recommend  # import statement — 浏览推荐意图规则
from app.rag.retriever import rag_retriever  # import statement — RAG 检索器
from app.rag.rrf import rrf_merge  # import statement — RRF 融合算法
from app.services.java_internal_client import java_internal_client  # import statement — Java 商品 API
from app.services.product_search_query import (  # import statement — 搜索词规范化与相关性过滤
    filter_products_by_query_relevance,
    normalize_product_search_query,
)
from app.services.search_recommend_service import search_recommend_service  # import statement — 品类/热销推荐
from app.utils.biz_payload import build_product_payload, first_cover  # import statement — 商品卡片构造

logger = structlog.get_logger()

_VAGUE_MARKERS = ("什么", "类似", "同款", "推荐", "有没有", "哪些", "哪个", "吗", "呢", "怎么")  # 模糊搜索标记词

_NOISE_RE = re.compile(r"[\d]+g|[\*×x]\d|装|规格|分享装", re.I)  # 商品名噪声正则 — 规格/包装等

def is_vague_search_keyword(text: str | None) -> bool:  # 判断是否模糊搜索词

    t = (text or "").strip()
    if not t or len(t) < 2:  # 空或过短视为模糊
        return True
    if any(m in t for m in _VAGUE_MARKERS) and len(t) <= 16:  # 含模糊标记且较短
        return True
    return False

_SIMILAR_HINTS = ("类似", "同款", "相近", "同类型", "同款式", "别的款", "其他款")  # 找类似商品提示词

def is_similar_or_recommend_request(text: str | None) -> bool:  # 是否类似/推荐请求

    t = (text or "").strip()
    if not t or len(t) > 40:
        return False
    if any(h in t for h in _SIMILAR_HINTS):
        return True
    if "推荐" in t and len(t) <= 28:
        return True
    return False

def derive_search_keyword(
    keyword: str | None,
    consult_product: dict | None,
) -> str:  # 推导实际搜索关键词 — 模糊词时用咨询商品名/品类

    if isinstance(keyword,str) and keyword.startswith('criteria:'):
        return keyword[len('criteria:'):].strip()
    kw = (keyword or "").strip()
    if consult_product and is_vague_search_keyword(kw):  # 模糊词且有咨询商品

        name = (consult_product.get("productName") or consult_product.get("product_name") or "").strip()
        if name:
            cleaned = _NOISE_RE.sub(" ", name)  # 去除规格噪声
            parts = [p.strip() for p in re.split(r"[\s/|]+", cleaned) if p.strip()]  # 分词
            if parts:
                return " ".join(parts[:4])  # 取前 4 段作为关键词

        category_id = consult_product.get("categoryId") or consult_product.get("category_id")
        if category_id:
            return f"category:{category_id}"  # 降级为品类搜索
    # 「我要吃零食」→「零食」，提升关键词/向量命中率
    return normalize_product_search_query(kw) or kw

class ProductService:  # 商品搜索服务 — 类似 Java @Service

    async def search_products(
        self,
        user_id: str,
        keyword: str | None,
        user_text: str = "",
        consult_product: dict | None = None,
        exclude_product_id: str | None = None,
    ) -> tuple[str, str | None, str, list[dict], str]:  # 返回 (卡片JSON, bizData, bizType, 商品List, source)

        from app.services import retrieval_trace
        retrieval_trace.start()
        query = derive_search_keyword(keyword, consult_product)  # 推导搜索词
        if not query:
            query = (keyword or "").strip()
        if is_vague_search_keyword(query):  # 仍模糊则再次推导
            query = derive_search_keyword(None, consult_product) or query

        biz_type = "product_search"  # 默认业务类型
        product_ids: list[str] = []  # List<String> 融合后的 ID
        source = "none"  # 数据来源标记

        if query.startswith("category:"):  # 品类搜索

            category_id = query.split(":", 1)[1]
            products = await search_recommend_service.load_by_category(category_id, 12)
            source = "category"
        elif query:  # 混合检索

            try:
                keyword_ids = await rag_retriever.search_product_keyword_ids(query, 50)
            except Exception:
                keyword_ids = []
                retrieval_trace.mark("keyword","UNAVAILABLE")
            try:
                from app.config.settings import get_settings
                if get_settings().shopping_data_mode=='LOCAL_STORE':
                    vector_ids=[];retrieval_trace.mark('vector','DISABLED')
                else:vector_ids=await rag_retriever.search_product_vector_ids(query, PRODUCT_CANDIDATE_SIZE)
            except Exception:
                vector_ids = []
                retrieval_trace.mark("vector","UNAVAILABLE")
            product_ids = rrf_merge(keyword_ids, vector_ids, 50)  # Filter business constraints before cutting the detail batch.
            logger.info(
                "hybrid_search",
                query=query,
                keyword_hits=len(keyword_ids),
                vector_hits=len(vector_ids),
                merged=len(product_ids),
            )
            products = await self._load_products_by_ids(product_ids)  # 批量加载商品详情
            if products:
                source = "hybrid"
                # Vector/keyword often returns unrelated hot junk — drop non-matching titles.
                relevant = filter_products_by_query_relevance(products, query)  # 标题相关性过滤
                if not relevant:
                    logger.info(
                        "hybrid_relevance_miss",
                        query=query,
                        candidates=len(products),
                    )
                    products = []
                    source = "none"
                elif len(relevant) < len(products):
                    logger.info(
                        "hybrid_relevance_filtered",
                        query=query,
                        before=len(products),
                        after=len(relevant),
                    )
                    products = relevant
        else:
            # Explicit catalogue browsing still gets facts from Java and batch SKU/Stock queries.
            candidates = await java_internal_client.search_on_sale(keyword="", limit=PRODUCT_RESULT_SIZE)
            products = await self._load_products_by_ids([str(p.get("product_id")) for p in candidates])
            source = "mysql_catalogue"

        if not products and query and not query.startswith("category:"):
            candidates = await java_internal_client.search_on_sale(keyword=query, limit=PRODUCT_RESULT_SIZE)
            products = await self._load_products_by_ids([str(p.get("product_id")) for p in candidates])
            if products:
                source = "mysql_keyword"
                for product in products:
                    product["retrieval_source"] = "MYSQL_KEYWORD"

        if exclude_product_id:  # 排除指定商品 — 如找类似时排除当前咨询商品
            products = [p for p in products if str(p.get("product_id")) != str(exclude_product_id)]

        similar_intent = _similar_intent(keyword, consult_product)  # 是否找类似商品意图
        if products and similar_intent and source == "hybrid":  # 类似意图但品类不匹配
            if not _products_match_consult_category(products, consult_product):
                logger.info(
                    "similar_hybrid_category_mismatch",
                    consult_category=_consult_category_id(consult_product),
                )
                products = []
                source = "none"

        if not products and consult_product and is_vague_search_keyword(keyword or user_text):  # 品类兜底
            category_id = consult_product.get("categoryId") or consult_product.get("category_id")
            if category_id:
                logger.info("category_fallback", category_id=category_id)
                products = await search_recommend_service.load_by_category(str(category_id), 8)
                if exclude_product_id:
                    products = [p for p in products if str(p.get("product_id")) != str(exclude_product_id)]
                if products:
                    source = "category"

        if not products and not query and looks_like_browse_recommend(user_text):  # Only explicit broad browsing.
            products = await search_recommend_service.load_recommend_products(user_id, 8)
            if products:
                biz_type = "BROWSE_RECOMMEND"
                source = "browse"

        if not products and not query:  # Never replace an explicit category miss with unrelated hot products.
            logger.info("hot_sale_fallback", user_id=user_id)
            products = await search_recommend_service.load_hot_sale(8)
            if products:
                biz_type = "product_search"
                source = "hot_sale"

        if source not in {"hybrid", "mysql_keyword", "mysql_catalogue"} and products:
            products = await self._load_products_by_ids([str(p.get("product_id") or p.get("productId")) for p in products])
        if exclude_product_id:
            products = [p for p in products if str(p.get("product_id")) != str(exclude_product_id)]
        if query and not query.startswith("category:"):
            # Apply identical relevance rules to MySQL fallbacks as to ES hits.
            products = filter_products_by_query_relevance(products, query)
        assistant, biz_data = build_product_payload(products)  # 构造前端卡片 JSON
        return assistant, biz_data, biz_type, products, source

    async def get_product_detail_text(self, product_id: str) -> str:
        from app.services.product_facts import render_facts
        return render_facts(await self.get_product_detail(product_id))

    async def get_product_details(self, product_ids: list[str]) -> dict:
        from app.services.product_facts import normalize_product, query_result
        if (not isinstance(product_ids, list) or not 1 <= len(product_ids) <= 12
                or any(not isinstance(i, str) or not i or len(i) > 64 for i in product_ids)):
            raise ValueError("Invalid detail batch")
        ids = list(dict.fromkeys(product_ids))
        batch = await java_internal_client.query_product_batch(ids)
        rows = batch.get("products")
        if (batch.get("query_status") != "SUCCESS" or not isinstance(rows, list)
                or len(rows) != len(ids) or any(not isinstance(r, dict) for r in rows)
                or {r.get("product_id") for r in rows} != set(ids)):
            raise ValueError("Invalid detail batch response")
        products = []
        for row in rows:
            if row.get("query_status") == "NOT_FOUND":
                products.append(row)
            elif row.get("query_status") == "SUCCESS":
                products.append(normalize_product(row))
            else:
                raise ValueError("Detail query failed")
        return query_result(products, source="java_batch")

    async def get_product_detail(self, product_id: str) -> dict:
        from app.services.product_facts import normalize_product, query_result
        batch = await java_internal_client.query_product_batch([product_id])
        rows = batch.get("products")
        if not isinstance(rows, list) or len(rows) != 1 or str(rows[0].get("product_id")) != str(product_id):
            raise ValueError("Invalid product detail response")
        row = rows[0]
        if row.get("query_status") == "NOT_FOUND":
            return query_result(status="NOT_FOUND")
        if row.get("query_status") != "SUCCESS":
            raise ValueError("Product query failed")
        return query_result([normalize_product(row)])

    async def _load_products_by_ids(self, product_ids: list[str]) -> list[dict]:
        from app.services.product_facts import normalize_product
        if not product_ids:
            return []
        ids = list(dict.fromkeys(str(i) for i in product_ids))[:50]
        batch = await java_internal_client.query_product_batch(ids)
        if batch.get("query_status") != "SUCCESS" or not isinstance(batch.get("products"), list):
            raise ValueError("Invalid product query response")
        rows = batch["products"]
        if len(rows) != len(ids) or {str(r.get("product_id")) for r in rows} != set(ids):
            raise ValueError("Incomplete product query response")
        result = {}
        for row in rows:
            if row.get("query_status") == "NOT_FOUND":
                continue
            if row.get("query_status") != "SUCCESS":
                raise ValueError("Product query failed")
            if row.get("status") == PRODUCT_STATUS_ON_SALE:
                product = normalize_product(row)
                product["cover"] = first_cover(product.get("cover"))
                result[str(product["product_id"])] = product
        return [result[i] for i in ids if i in result]

product_service = ProductService()  # 模块级单例

def _similar_intent(keyword: str | None, consult: dict | None) -> bool:  # 模糊词 + 有咨询商品 = 类似意图

    return is_vague_search_keyword(keyword) and bool(consult)

def _consult_category_id(consult: dict | None) -> str:  # 提取咨询商品品类 ID

    if not consult:
        return ""
    return str(consult.get("categoryId") or consult.get("category_id") or "")

def _products_match_consult_category(products: list[dict], consult: dict | None) -> bool:  # 结果是否含同品类商品

    consult_cat = _consult_category_id(consult)
    if not consult_cat or not products:
        return False
    return any(str(p.get("category_id") or "") == consult_cat for p in products)  # any 类似 Stream.anyMatch

def format_search_tool_message(
    keyword: str,
    consult: dict | None,
    products: list[dict],
    source: str,
) -> str:  # 格式化 SEARCH_PRODUCTS 工具返回文案

    from app.domain.intent.rules import looks_like_browse_recommend, looks_like_hot_sale_recommend  # 延迟 import
    from app.services.product_search_query import filter_products_by_query_relevance

    consult_name = (consult or {}).get("productName") or (consult or {}).get("product_name") or "当前商品"
    similar_intent = _similar_intent(keyword, consult)
    alternative_sources = {"browse", "hot_sale"}  # 兜底来源集合
    kw = (keyword or "").strip()
    kw_display = (normalize_product_search_query(kw) or kw)[:24] if kw else "你的需求"

    if similar_intent and source in alternative_sources:  # 找类似但走了兜底
        return (
            f"【类似商品】暂未找到与「{consult_name}」类似或同款的商品。\n"
            f"【另荐热销】已为您另外推荐热销商品（非同款，请查看下方卡片）。"
        )
    if similar_intent and source == "category":  # 同品类推荐
        return f"【同品类推荐】找到 {len(products)} 个同品类商品（请查看下方卡片）。"

    # Even if source claims hybrid, never brand irrelevant titles as「找到」.
    if products and kw and source not in ("category",):  # 混合检索需验证相关性
        relevant = filter_products_by_query_relevance(products, kw)
        intentional_alt = looks_like_hot_sale_recommend(kw) or looks_like_browse_recommend(kw)
        if not relevant and not intentional_alt:  # 无相关且非故意要热销/浏览
            return (
                f"【搜索结果】暂未找到与「{kw_display}」相关的商品。\n"
                f"【另荐热销】已为您另外推荐热销商品，请查看下方卡片。"
            )

    # Keyword search missed → hot-sale / browse backfill: never label as「搜索结果找到」.
    if products and source in alternative_sources:  # 关键词未命中，走了兜底
        intentional_alt = looks_like_hot_sale_recommend(kw) or looks_like_browse_recommend(kw)
        if intentional_alt and source == "hot_sale":
            return f"【热销推荐】为您推荐 {len(products)} 个热销商品（请查看下方卡片）。"
        if intentional_alt and source == "browse":
            return f"【浏览推荐】根据你的浏览为你推荐 {len(products)} 个商品（请查看下方卡片）。"
        alt_label = "【另荐热销】" if source == "hot_sale" else "【浏览推荐】"
        alt_body = (
            "已为您另外推荐热销商品，请查看下方卡片。"
            if source == "hot_sale"
            else "已根据浏览为您另外推荐商品，请查看下方卡片。"
        )
        return (
            f"【搜索结果】暂未找到与「{kw_display}」相关的商品。\n"
            f"{alt_label}{alt_body}"
        )

    if not products:  # 完全无结果
        if kw:
            return f"【搜索结果】暂未找到与「{kw_display}」相关的商品。"
        return "【搜索结果】未找到相关商品。"
    return f"【搜索结果】找到 {len(products)} 个商品（请查看下方卡片）。"  # 正常命中
