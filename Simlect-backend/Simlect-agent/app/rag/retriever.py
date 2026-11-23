import json

import httpx
import structlog

from app.config.settings import get_settings
from app.rag.embedding import embed_text
from app.resilience.circuit_breaker import circuit_registry
from app.services.java_internal_client import java_internal_client

logger = structlog.get_logger()

PRODUCT_INDEX = "simlect-index"


def _escape_wildcard(text: str) -> str:
    """转义 ES wildcard 查询中的通配符（防用户输入 * ? 触发前导通配导致性能 DoS / 语义错乱）。"""
    if not text:
        return text
    return text.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def _valid_document_id(value: str) -> bool:
    from uuid import UUID
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError):
        return False


class RagRetriever:

    async def search_policy(self, query: str, top_k: int | None = None, category: str | None = None, *, browse_topics: bool = False) -> dict:
        """Same embedding/index as FAQ, separate type and authoritative publication catalog."""
        import hashlib
        import math
        from app.rag.policy import policy_result, catalog_eligible

        settings = get_settings()
        from app.rag.aftersales_topics import topic, keyword_filter
        overview = bool(__import__('re').fullmatch(r'(?:请|帮我|查询|查看|一下|现有|的|售后|政策|规则|有哪些|有什么|[，。？！?\s])+', query or '')) and '售后' in (query or '')
        lexical_read = browse_topics and (overview or topic(query or '') == 'REPAIR_EXCHANGE')
        if topic(query or '') == 'SHOP_PROMISE':
            return policy_result('NO_MATCH', query=query, reason='NO_VERIFIED_PLATFORM_POLICY')
        k = min(max(top_k if top_k is not None else settings.policy_top_k, 1), 20)
        threshold = min(max(settings.policy_score_threshold, 0.0), 1.0)
        if not (query or '').strip():
            return policy_result('NO_MATCH')
        breaker = circuit_registry.get_or_create('es')
        if not breaker.allow_request():
            return policy_result('ES_UNAVAILABLE')
        try:
            if lexical_read:
                vector = None
            else:
                vector = await embed_text(query[:2000])
            if not lexical_read and (not vector or len(vector) != settings.embedding_dimensions
                    or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vector)
                    or not any(v != 0 for v in vector)):
                return policy_result('EMBEDDING_FAILED')
        except Exception:
            return policy_result('EMBEDDING_FAILED')
        try:
            candidates = min(k * 4, 80)
            body = {'size': candidates, 'knn': {'field': 'embedding', 'query_vector': vector,
                    'k': candidates, 'num_candidates': candidates * 2,
                    'filter': {'bool': {'must': [{'term': {'metadata.dataType.keyword': 'aftersales_policy'}}, {'terms': {'metadata.category.keyword': [category] if category else ['LAW', 'PLATFORM_DEMO']}}]}}},
                    '_source': ['content', 'text', 'metadata']}
            lexical = keyword_filter(query)
            if lexical:
                body['knn']['filter']['bool']['must'].append(lexical)
            if lexical_read:
                filters = body['knn']['filter']['bool']['must']
                if overview:
                    filters.append({'bool':{'should':[{'match_phrase':{'content':t}} for t in ('退货','退款','更换','修理')],'minimum_should_match':1}})
                # Exact topic browsing, not a fabricated vector similarity score.
                body={'size':candidates,'query':{'constant_score':{'filter':{'bool':{'must':filters}}}},'_source':['content','text','metadata']}
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(self._es_url(f'/{settings.es_index}/_search'), json=body)
                response.raise_for_status()
                hits = response.json()['hits']['hits']
                if not isinstance(hits, list) or any(not isinstance(h, dict) or not isinstance(h.get('_source'), dict)
                        or not isinstance(h['_source'].get('metadata'), dict) for h in hits):
                    raise ValueError('Invalid policy search response')
            breaker.record_success()
        except Exception:
            breaker.record_failure()
            return policy_result('ES_UNAVAILABLE')
        if not hits:
            return policy_result('NO_MATCH')
        refs = list(dict.fromkeys(str(h.get('_source', {}).get('metadata', {}).get('documentId') or '') for h in hits))
        refs = [r for r in refs if _valid_document_id(r)]
        if not refs:
            return policy_result('NO_MATCH')
        try:
            catalog = []
            for start in range(0, len(refs), 50):
                part = await java_internal_client.post_json('/internal/knowledge/catalog', {'documentIds': refs[start:start+50], **({'category': category} if category else {})}, strict=True)
                if not isinstance(part, list):
                    raise ValueError('Invalid policy catalog')
                catalog.extend(part)
            if any(not isinstance(d, dict) or not all(isinstance(d.get(k), str) and d[k] for k in ('documentId', 'title', 'filename', 'source'))
                   or type(d.get('revision')) is not int or not isinstance(d.get('chunks'), list) for d in catalog):
                raise ValueError('Invalid policy catalog')
            for doc in catalog:
                if any(not isinstance(c, dict)
                       or not all(isinstance(c.get(key), str) and c[key] for key in ('chunkId', 'sha256', 'section'))
                       or type(c.get('page')) is not int for c in doc['chunks']):
                    raise ValueError('Invalid policy chunk catalog')
            approved = {d['documentId']: d for d in catalog if catalog_eligible(d, category)}
        except Exception:
            return policy_result('CATALOG_UNAVAILABLE')
        valid = []
        seen = set()
        for hit in hits:
            src = hit.get('_source', {})
            meta = src.get('metadata', {})
            if not isinstance(meta.get('documentId'), str) or not isinstance(meta.get('chunkId'), str):
                continue
            doc = approved.get(meta.get('documentId'))
            text = src.get('content') or src.get('text') or ''
            score = hit.get('_score')
            if (not doc or type(meta.get('revision')) is not int or meta.get('revision') != doc.get('revision')
                    or meta.get('dataType') != 'aftersales_policy' or not isinstance(text, str)
                    or type(score) not in (int, float) or not math.isfinite(score)):
                continue
            canonical = next((c for c in doc.get('chunks', []) if c.get('chunkId') == meta.get('chunkId')), None)
            if not canonical or canonical.get('sha256') != hashlib.sha256(text.encode('utf-8')).hexdigest():
                continue
            identity = (doc['documentId'], doc['revision'], meta['chunkId'])
            if identity in seen:
                continue
            seen.add(identity)
            valid.append({'documentId': doc['documentId'], 'revision': doc['revision'], 'chunkId': meta['chunkId'],
                          'documentName': doc['title'], 'filename': doc['filename'], 'source': doc['source'],
                          'section': canonical['section'], 'page': canonical.get('page'), 'text': text, 'score': score, **{key: doc.get(key) for key in ('category', 'issuer', 'originalUrl', 'publishedOn', 'effectiveFrom', 'effectiveUntil', 'sourceStatus')}})
        if not valid:
            return policy_result('NO_MATCH')
        relevant = valid if lexical_read else [h for h in valid if h['score'] >= threshold]
        if not relevant:
            return policy_result('LOW_RELEVANCE', bestScore=max(h['score'] for h in valid))
        from app.rag.evidence_quality import rank_evidence
        from app.rag.aftersales_topics import applicable
        relevant = [h for h in relevant if applicable(query, h)]
        if not relevant:
            return policy_result('NO_MATCH', query=query, reason='INSUFFICIENT_TOPIC_EVIDENCE')
        ranked = rank_evidence(query, relevant, k)
        if not ranked:
            return policy_result('NO_MATCH', query=query, reason='NO_SUBSTANTIVE_CLAUSE')
        return policy_result('SUCCESS', ranked, query=query,
                             ranking='verified_exact_topic_browse' if lexical_read else 'vector_threshold_then_lexical_overlap', threshold=None if lexical_read else threshold)

    def __init__(self):

        self._es_hosts = get_settings().es_hosts

    def _es_url(self, path: str) -> str:

        base = self._es_hosts.split(",")[0].rstrip("/")
        return f"{base}{path}"

    async def search_faq(self, query: str, top_k: int | None = None) -> str:

        docs = await self._vector_search(query, "faq", top_k)
        if not docs:
            return ""

        seen: set[str] = set()
        parts = []
        for d in docs:
            text = d.get("content") or d.get("text") or ""
            if text and text not in seen:
                seen.add(text)
                parts.append(text)
        return "\n".join(parts)

    async def search_product_vector_ids(self, query: str, limit: int) -> list[str]:

        docs = await self._vector_search(query, "product", limit, threshold=0.4)
        ids = []
        for d in docs:
            meta = d.get("metadata") or {}

            pid = meta.get("productId") or meta.get("product_id")
            if pid and str(pid) not in ids:
                ids.append(str(pid))
        return ids

    async def search_product_keyword_ids(self, query: str, limit: int) -> list[str]:
        from app.services.retrieval_trace import mark

        breaker = circuit_registry.get_or_create("es", failure_threshold=3, recovery_timeout=30)
        if not breaker.allow_request() or not query.strip():
            mark("keyword","UNAVAILABLE")
            return []
        try:
            # Delegate keyword concepts to Java Search, shared with the storefront.
            # Bounded pagination preserves the old 50-candidate contract.
            ids=[];target=min(max(limit,1),50)
            async with httpx.AsyncClient(timeout=15) as client:
                for page in range(1,5):
                    resp=await client.post(get_settings().java_web_url.rstrip('/')+'/api/search/products',data={'keyWords':query,'pageNo':page})
                    resp.raise_for_status();body=resp.json()
                    if body.get('status')!='success' or body.get('code')!=200 or not isinstance(body.get('data'),dict):raise ValueError('SEARCH_CONTRACT_INVALID')
                    data=body['data'];rows=data.get('list')
                    if not isinstance(rows,list):raise ValueError('SEARCH_ROWS_INVALID')
                    for row in rows:
                        pid=row.get('productId')
                        if not isinstance(pid,str) or not pid:raise ValueError('SEARCH_ID_INVALID')
                        if pid not in ids:ids.append(pid)
                    if len(ids)>=target or not rows or page>=data.get('pageTotal',page):break
            mark("keyword","SUCCESS");breaker.record_success()
            return ids[:target]
        except Exception as e:
            mark("keyword","DEGRADED")
            breaker.record_failure()
            logger.error("es_keyword_search_failed", error=str(e))

            return await self._product_search_fallback(query, limit)

    async def _vector_search(
        self,
        query: str,
        data_type: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> list[dict]:

        from app.services.retrieval_trace import mark
        settings = get_settings()
        k = top_k or settings.rag_top_k

        th = threshold if threshold is not None else settings.rag_score_threshold
        breaker = circuit_registry.get_or_create("es")
        if not breaker.allow_request():
            if data_type=="product":mark("vector","UNAVAILABLE")
            return []
        vector = await embed_text(query)
        if not vector:
            if data_type=="product":mark("vector","EMBEDDING_FAILED")
            return []
        try:
            body = {
                "size": k,
                "knn": {
                    "field": "embedding",
                    "query_vector": vector,
                    "k": k,
                    "num_candidates": k * 2,
                    "filter": {
                        "bool": {
                            "must": [{"term": {"metadata.dataType.keyword": data_type}}]
                        }
                    },
                },
                "_source": ["content", "metadata", "text"],
            }
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    self._es_url(f"/{settings.es_index}/_search"),
                    json=body,
                )
                if resp.status_code == 404:

                    body["knn"]["field"] = "vector"
                    resp = await client.post(
                        self._es_url(f"/{settings.es_index}/_search"),
                        json=body,
                    )
                resp.raise_for_status()
                hits = resp.json().get("hits", {}).get("hits", [])
            if data_type=="product":mark("vector","SUCCESS")
            breaker.record_success()
            results = []
            for h in hits:
                score = h.get("_score", 0)
                if score < th:
                    continue
                src = h.get("_source", {})
                results.append({
                    "content": src.get("content") or src.get("text", ""),
                    "metadata": src.get("metadata", {}),
                    "score": score,
                })
            return results
        except Exception as e:
            if data_type=="product":mark("vector","UNAVAILABLE")
            breaker.record_failure()
            logger.error("vector_search_failed", data_type=data_type, error=str(e))
            return []

    async def _product_search_fallback(self, query: str, limit: int) -> list[str]:

        try:
            rows = await java_internal_client.search_on_sale(keyword=query, limit=limit)
            ids = []
            for r in rows:
                pid = r.get("product_id") or r.get("productId")
                if pid and str(pid) not in ids:
                    ids.append(str(pid))
            return ids
        except Exception as e:
            logger.error("product_search_fallback_failed", error=str(e))
            return []

rag_retriever = RagRetriever()
