"""Independent rule oracle: raw fixture facts, not Agent helpers or model judgments."""
from decimal import Decimal, InvalidOperation

def decimal_fact(value):
    if type(value) not in (str,int,float) or isinstance(value,bool): return None
    try:
        d=Decimal(str(value))
        return d if d.is_finite() and d>=0 else None
    except (InvalidOperation,ValueError): return None

def assert_shopping_result(result, catalog, *, ceiling=None, floor=None, in_stock=False, real_only=False):
    facts={str(p['product_id']):p for p in catalog}
    seen=set()
    for item in result['recommendations']:
        assert item['productId'] not in seen, 'DUPLICATE_PRODUCT'
        seen.add(item['productId']);p=facts[item['productId']]
        assert p['product_status']=='ON_SALE','OFF_SHELF_RECOMMENDED'
        if real_only:
            origin=p.get('data_provenance') or {}
            assert origin.get('source_type')=='LIVE_API' and origin.get('source_name'),'UNVERIFIED_PRODUCT_SOURCE'
            assert all(origin.get('field_sources',{}).get(k)=='LIVE_API' for k in ('price','sku','stock')),'UNVERIFIED_FIELD_SOURCE'
        canonical={s['sku_id']:s for s in p['skus']}
        assert item['eligibleSkus'],'MISSING_SKU'
        for sku in item['eligibleSkus']:
            original=canonical[sku['sku_id']]
            price=decimal_fact(original['price'])
            assert decimal_fact(sku['price'])==price,'CHANGED_PRICE'
            if ceiling is not None: assert price is not None and price<=Decimal(str(ceiling)),'BUDGET_BREACH'
            if floor is not None: assert price is not None and price>=Decimal(str(floor)),'LOWER_BOUND_BREACH'
            known=type(original.get('stock')) is int and original['stock']>=0 and original.get('stock_query_status')=='SUCCESS'
            assert sku['stock']==(original['stock'] if known else None),'CHANGED_OR_INVENTED_STOCK'
            assert not known or original['stock']>0,'ZERO_STOCK_RECOMMENDED'
            if in_stock:assert known and original['stock']>0,'UNKNOWN_STOCK_AS_AVAILABLE'

def assert_policy_evidence(hits, catalog):
    ids=set()
    for hit in hits:
        key=(hit['documentId'],hit['revision'],hit['chunkId']);assert key not in ids,'DUPLICATE_EVIDENCE';ids.add(key)
        original=catalog[key]
        assert hit['text']==original['text'] and hit['source']==original['source'],'ALTERED_EVIDENCE'
        assert original['published'] and original['effective'],'UNAPPROVED_POLICY'

def assert_route(route, expected):
    agents=[t['agent'] for t in route['tasks']]
    assert len(agents)==len(set(agents)),'DUPLICATE_SPECIALIST'
    assert agents==expected,'WRONG_SPECIALIST'


def expected_simple_candidate_ids(catalog, ceiling):
    """Recall oracle for the controlled price/stock grid, not all business filters."""
    expected=set()
    for p in catalog:
        if p['product_status']!='ON_SALE':continue
        for sku in p['skus']:
            price=decimal_fact(sku['price'])
            known=type(sku.get('stock')) is int and sku['stock']>=0 and sku.get('stock_query_status')=='SUCCESS'
            if price is not None and price<=Decimal(str(ceiling)) and (not known or sku['stock']>0):
                expected.add(p['product_id']);break
    return expected
