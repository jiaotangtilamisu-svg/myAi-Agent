"""Business provenance is distinct from technical Java/Stock query provenance."""

TYPES = {"PUBLIC_DATASET", "SYNTHETIC", "MANUAL", "LIVE_API"}


def classification(value, product_id=""):
    """Technical Java/Stock provenance alone never proves real commercial data."""
    p = provenance(value)
    if (p.get('catalogue_status')=='LOCAL_STORE' and p['source_type'] in {'PUBLIC_DATASET','MANUAL'}
            and p['field_sources'].get('price')=='MANUAL' and p['field_sources'].get('sku')=='MANUAL'
            and p['field_sources'].get('stock') in {'MANUAL','SYNTHETIC'}):
        return 'LOCAL_STORE'
    if str(product_id).upper().startswith("DEMO"):
        return "DEMO"
    if p["source_type"] == "SYNTHETIC" or "SYNTHETIC" in p["field_sources"].values():
        return "TEST"
    # All recommendation-critical business fields must have a verified live source.
    if (p["source_type"] == "LIVE_API" and p.get("source_name")
            and all(p["field_sources"].get(k) == "LIVE_API" for k in ("price", "sku", "stock"))):
        return "REAL"
    return "UNKNOWN"


def provenance(value):
    if not isinstance(value, dict) or value.get("source_type") not in TYPES:
        return {"source_type": "UNRECORDED", "field_sources": {}, "currency": None}
    fields = value.get("field_sources")
    if not isinstance(fields, dict) or any(
        not isinstance(v, str) or v not in TYPES for v in fields.values()
    ):
        return {"source_type": "UNRECORDED", "field_sources": {}, "currency": None}
    currency = value.get("currency")
    return {
        'catalogue_status': 'LOCAL_STORE' if value.get('catalogue_status')=='LOCAL_STORE' else None,
        **{
            k: str(value[k])[:500]
            for k in [
                "source_name",
                "source_record_id",
                "batch_id",
                "version",
                "source_url",
                "observed_at",
            ]
            if value.get(k)
        },
        "source_type": value["source_type"],
        "field_sources": dict(fields),
        "currency": currency if currency in {"CNY", "BRL", "USD", "EUR"} else None,
    }


def label(value):
    p = provenance(value)
    text = {
        "PUBLIC_DATASET": "公开历史数据（非当前交易）",
        "SYNTHETIC": "合成测试数据",
        "MANUAL": "手工维护资料",
        "LIVE_API": "实时业务来源",
        "UNRECORDED": "业务数据来源未登记",
    }[p["source_type"]]
    return text + (
        "；包含合成测试字段"
        if p["source_type"] != "SYNTHETIC"
        and "SYNTHETIC" in p["field_sources"].values()
        else ""
    )
