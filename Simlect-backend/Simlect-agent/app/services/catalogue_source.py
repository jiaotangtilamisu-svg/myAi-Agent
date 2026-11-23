"""Read-only supplier boundary. No configured supplier, HTTP endpoint or publication fallback.

An operator supplies an approved adapter and persisted product/SKU bindings. Model and
request arguments cannot register sources or create LIVE_API attestations.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from typing import Protocol


class ReadOnlySource(Protocol):
    async def read_products(self, source_ids: tuple[str, ...]) -> list[dict]: ...


@dataclass(frozen=True)
class SourceApproval:
    name: str
    authorization_reference: str
    documentation_url: str
    currency: str
    max_age_seconds: int = 300


def _number(value, *, integer=False):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError('INVALID_BUSINESS_NUMBER')
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or integer and n != n.to_integral_value():
            raise ValueError('INVALID_BUSINESS_NUMBER')
        return int(n) if integer else str(n)
    except (InvalidOperation, TypeError):
        raise ValueError('INVALID_BUSINESS_NUMBER') from None


class CatalogueSourceAdapter:
    def __init__(self, *, approval: SourceApproval | None = None,
                 source: ReadOnlySource | None = None, bindings=None, now=None):
        self.approval, self.source = approval, source
        # Key=(provider product ID, provider SKU ID); value=(existing product ID, SKU hash).
        self.bindings = dict(bindings or {})
        self.now = now or (lambda: datetime.now(timezone.utc))

    async def read(self, source_ids: list[str]) -> dict:
        a = self.approval
        if not a or not self.source:
            return {'queryStatus': 'BLOCKED', 'reason': 'NO_APPROVED_COMMERCIAL_SOURCE', 'products': []}
        if not all((a.name, a.authorization_reference, a.documentation_url.startswith('https://'),
                    a.currency == 'CNY', 0 < a.max_age_seconds <= 3600)):
            raise ValueError('INVALID_OPERATOR_SOURCE_APPROVAL')
        if not isinstance(source_ids, list) or not 1 <= len(source_ids) <= 12 or any(
                not isinstance(i, str) or not i or len(i) > 200 for i in source_ids):
            raise ValueError('BOUNDED_SOURCE_IDS_REQUIRED')
        try:
            rows = await self.source.read_products(tuple(dict.fromkeys(source_ids)))
        except Exception:
            return {'queryStatus': 'SERVICE_ERROR', 'reason': 'SOURCE_READ_FAILED', 'products': []}
        if not isinstance(rows, list) or len(rows) > len(set(source_ids)):
            return {'queryStatus': 'INVALID_RESPONSE', 'products': []}
        try:
            products, seen, targets = [], set(), set()
            for row in rows:
                sid = row['sourceRecordId']
                if sid not in source_ids or sid in seen:
                    raise ValueError('UNREQUESTED_OR_DUPLICATE_PRODUCT')
                seen.add(sid)
                observed = datetime.fromisoformat(row['observedAt'].replace('Z', '+00:00'))
                if observed.tzinfo is None or not -timedelta(minutes=5) <= self.now()-observed <= timedelta(seconds=a.max_age_seconds):
                    raise ValueError('STALE_OR_INVALID_OBSERVATION')
                if not isinstance(row['productName'], str) or not row['productName'].strip() or row['status'] not in {'ON_SALE', 'OFF_SHELF'}:
                    raise ValueError('INVALID_PRODUCT_FACTS')
                if not isinstance(row.get('version'), str) or not row['version'].strip():
                    raise ValueError('SOURCE_VERSION_REQUIRED')
                evidence = row['fieldEvidence']
                if any(not isinstance(evidence.get(k), str) or not evidence[k].strip()
                       for k in ('name', 'price', 'sku', 'stock')):
                    raise ValueError('FIELD_EVIDENCE_REQUIRED')
                if not isinstance(row['skus'], list) or not 1 <= len(row['skus']) <= 100:
                    raise ValueError('INVALID_SKUS')
                skus, product_id, sku_seen = [], None, set()
                for sku in row['skus']:
                    pair = self.bindings.get((sid, sku['sourceSkuId']))
                    if not pair or len(pair) != 2 or not all(isinstance(v, str) and v for v in pair):
                        raise ValueError('EXISTING_SKU_BINDING_REQUIRED')
                    if product_id is not None and product_id != pair[0] or pair in sku_seen:
                        raise ValueError('CROSS_PRODUCT_OR_DUPLICATE_SKU')
                    product_id = pair[0]; sku_seen.add(pair)
                    price = _number(sku.get('price'))
                    stock_status = sku.get('stockQueryStatus')
                    if stock_status not in {'SUCCESS', 'UNKNOWN', 'UNAVAILABLE'}:
                        raise ValueError('INVALID_STOCK_STATUS')
                    quantity = _number(sku.get('stock'), integer=True) if stock_status == 'SUCCESS' else None
                    if not isinstance(sku.get('specifications'), dict) or not sku['specifications'] or any(
                            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
                            for k,v in sku['specifications'].items()):
                        raise ValueError('SKU_SPECIFICATIONS_REQUIRED')
                    skus.append({'product_id': pair[0], 'sku_id': pair[1],
                        'property_value_id_hash': pair[1], 'price': price,
                        'price_status': 'UNKNOWN' if price is None else 'KNOWN', 'stock': quantity,
                        'stock_query_status': 'UNKNOWN' if stock_status == 'SUCCESS' and quantity is None else stock_status,
                        'specifications': [{'name': k, 'value': v} for k, v in sku['specifications'].items()]})
                if product_id in targets:
                    raise ValueError('DUPLICATE_TARGET_PRODUCT')
                targets.add(product_id)
                products.append({'product_id': product_id, 'product_name': row['productName'],
                    'product_status': row['status'], 'query_status': 'SUCCESS', 'skus': skus,
                    'sku_complete': True, 'product_observed_at': observed.isoformat(),
                    'data_provenance': {'source_type': 'LIVE_API', 'source_name': a.name,
                        'source_record_id': sid, 'source_url': a.documentation_url,
                        'observed_at': observed.isoformat(), 'version': str(row['version']),
                        'currency': a.currency,
                        'field_sources': {k: 'LIVE_API' for k in ('name', 'price', 'sku', 'stock')},
                        'field_evidence': {k: evidence[k] for k in ('name', 'price', 'sku', 'stock')}}})
            return {'queryStatus': 'SUCCESS' if products else 'NOT_FOUND', 'products': products}
        except (ValueError, TypeError, KeyError, AttributeError):
            # Never expose provider payloads, nor promote partially invalid data to REAL.
            return {'queryStatus': 'INVALID_RESPONSE', 'products': []}
