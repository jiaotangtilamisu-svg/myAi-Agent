"""Governance fixtures only; no policies or external vectors are created."""
from datetime import datetime, timedelta, timezone

import pytest

from app.rag.policy import catalog_eligible, render_policy
from app.services.product_facts import normalize_product
from app.shopping.selection import select


def doc(**changes):
    return {"category": "PLATFORM_DEMO", "sourceStatus": "VALID", "effectiveFrom": "2020-01-01T00:00:00Z", "effectiveUntil": "", **changes}


@pytest.mark.parametrize("changes", [
    {"sourceStatus": "UNVERIFIED"}, {"sourceStatus": "INVALID"}, {"category": "INDUSTRY_REFERENCE"},
    {"category": "UNKNOWN"}, {"effectiveFrom": None}, {"effectiveFrom": "2020-01-01T00:00:00"},
    {"effectiveUntil": "2020-01-02T00:00:00Z"},
])
def test_ineligible_catalog_rejected(changes):
    assert not catalog_eligible(doc(**changes))


def test_valid_window_and_reference_category_are_explicit():
    assert catalog_eligible(doc())
    assert catalog_eligible(doc(category="INDUSTRY_REFERENCE"), "INDUSTRY_REFERENCE")
    assert not catalog_eligible(doc(category="LAW"), "PLATFORM_DEMO")
    assert not catalog_eligible(doc(effectiveFrom=(datetime.now(timezone.utc)+timedelta(days=1)).isoformat()))


def test_source_category_is_in_answer_and_not_promoted_to_business_rule():
    hit={"documentName":"TEST ONLY", "section":"fixture", "score":0.9,"text":"Not a policy","source":"fixture://test","revision":1,"documentId":"test","category":"INDUSTRY_REFERENCE","issuer":"TEST","originalUrl":"https://example.invalid/reference"}
    text=render_policy({"status":"SUCCESS","hits":[hit]})
    assert "不是Simlect商城办理规则" in text and "https://example.invalid/reference" in text


@pytest.mark.parametrize("status,value,expected", [("SUCCESS",0,0),("MISSING",None,None),("UNAVAILABLE",None,None)])
def test_product_stock_states_are_not_collapsed(status,value,expected):
    p=normalize_product({"product_id":"test", "status":1,"sku_complete":True,"min_price":None,"max_price":None,"skus":[{"sku_id":"s","price":None,"stock":value,"stock_query_status":status}]})
    assert p["skus"][0]["stock"] is expected
    assert p["min_price"] is None and p["skus"][0]["price"] is None
    assert p["stock_query_status"]==status


def test_unknown_price_never_meets_budget_but_zero_price_can():
    p=normalize_product({"product_id":"test","product_name":"TEST","status":1,"query_status":"SUCCESS","sku_complete":True,"min_price":None,"max_price":None,"skus":[{"sku_id":"s","price":None,"stock":5,"stock_query_status":"SUCCESS"}]})
    assert not select([p],{"budgetMax":"300"})["recommendations"]
    assert not select([p],{"preferences":["便宜"]})["recommendations"]
    p["skus"][0]["price"]="0";p["min_price"]="0";p["max_price"]="0"
    assert select([p],{"budgetMax":"300"})["recommendations"]
