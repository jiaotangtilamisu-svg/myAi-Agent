import json

from app.services.data_provenance import label, provenance
from app.services.product_facts import normalize_product
from app.utils.biz_payload import build_product_payload


def test_unregistered_business_source_is_not_assumed_live():
    assert provenance(None)["source_type"] == "UNRECORDED"
    assert "未登记" in label({"source_type": "UNKNOWN"})


def test_field_sources_survive_product_mcp_and_card_projection():
    origin = {
        "source_type": "MANUAL",
        "source_name": "test-only",
        "currency": "CNY",
        "field_sources": {"price": "SYNTHETIC", "stock": "SYNTHETIC"},
    }
    p = normalize_product(
        {"product_id": "P1", "status": 1, "data_provenance": origin, "skus": []}
    )
    cards, _ = build_product_payload([p])
    assert (
        json.loads(cards)[0]["dataProvenance"]["fieldSources"]["price"] == "SYNTHETIC"
    )


def test_illegal_source_field_does_not_get_trusted():
    assert (
        provenance({"source_type": "LIVE_API", "field_sources": {"stock": "invented"}})[
            "source_type"
        ]
        == "UNRECORDED"
    )


def test_unknown_price_and_stock_unchanged_by_origin():
    p = normalize_product(
        {
            "product_id": "P1",
            "status": 1,
            "min_price": None,
            "max_price": None,
            "skus": [{"stock": None, "price": None}],
        }
    )
    assert p["min_price"] is None and p["skus"][0]["stock"] is None


def test_history_cannot_be_recommended_as_current_sale():
    from app.shopping.selection import select
    from test_shopping_agent import product

    p = product()
    p["data_provenance"] = {"source_type": "PUBLIC_DATASET"}
    result = select([p], {})
    assert (
        not result["recommendations"]
        and result["excluded"][0]["reason"] == "HISTORICAL_RECORD_NOT_LIVE"
    )
