"""Manual unbranded test catalogue: every commercial number is explicitly synthetic."""

from decimal import Decimal

from .olist import canonical, digest

GROUPS = {
    "数码": ["无线键盘", "USB集线器", "有线耳机"],
    "家电": ["桌面风扇", "阅读台灯", "迷你加湿器"],
    "生活日用": ["帆布收纳袋", "保温杯", "桌面收纳盒"],
    "办公": ["笔记本套装", "文件夹", "显示器支架"],
    "运动": ["跳绳", "瑜伽垫", "运动水杯"],
}


def candidates():
    rows = []
    for category, names in GROUPS.items():
        for name in names:
            key = digest("synthetic-catalogue-v1:" + category + ":" + name)[:12]
            values = [
                {
                    "sourceSkuId": key + "-STD",
                    "specifications": {"规格": "测试标准款"},
                    "price": "99.00",
                    "stock": 30,
                },
                {
                    "sourceSkuId": key + "-PLUS",
                    "specifications": {"规格": "测试加大款"},
                    "price": "149.00",
                    "stock": 0,
                },
            ]
            rows.append(
                {
                    "sourceRecordId": key,
                    "productName": "[合成测试] " + name,
                    "category": category,
                    "currency": "CNY",
                    "skus": values,
                    "sourceType": "SYNTHETIC",
                    "sourceName": "Simlect手工维护无品牌测试目录",
                    "sourceUrl": "project://tools/data_governance/catalogue.py",
                    "version": "synthetic-catalogue-v1",
                    "fieldSources": {
                        "productName": "MANUAL",
                        "category": "MANUAL",
                        "sku": "SYNTHETIC",
                        "price": "SYNTHETIC",
                        "stock": "SYNTHETIC",
                    },
                    "publicationStatus": "NOT_PUBLISHED",
                }
            )
    return rows


def validate_candidate(row):
    if row.get("sourceType") != "SYNTHETIC" or not row.get(
        "productName", ""
    ).startswith("[合成测试] "):
        raise ValueError("TEST_LABEL_REQUIRED")
    if row.get("currency") != "CNY":
        raise ValueError("CURRENCY_MISMATCH_NO_IMPLICIT_FX")
    ids = set()
    for sku in row.get("skus", []):
        if sku["sourceSkuId"] in ids:
            raise ValueError("DUPLICATE_SKU")
        ids.add(sku["sourceSkuId"])
        price = Decimal(sku["price"])
        if not price.is_finite() or price < 0:
            raise ValueError("INVALID_PRICE")
        if type(sku["stock"]) is not int or sku["stock"] < 0:
            raise ValueError("INVALID_STOCK")
    if not ids:
        raise ValueError("SKU_REQUIRED")
    return row


def staged_catalogue():
    rows = [validate_candidate(r) for r in candidates()]
    report = {
        "status": "VALID",
        "batchId": digest(canonical(rows)),
        "dataset": "simlect-synthetic-catalogue",
        "sourceType": "SYNTHETIC",
        "version": "synthetic-catalogue-v1",
        "sourceUrl": "project://tools/data_governance/catalogue.py",
        "license": "PROJECT-TEST-DATA",
        "currency": "CNY",
        "fieldSources": {
            "productName": "MANUAL",
            "category": "MANUAL",
            "price": "SYNTHETIC",
            "sku": "SYNTHETIC",
            "stock": "SYNTHETIC",
        },
        "counts": {"catalogue_candidate": len(rows)},
        "publicationStatus": "NOT_PUBLISHED",
    }
    return report, [
        ("catalogue_candidate", r["sourceRecordId"], canonical(r), digest(canonical(r)))
        for r in rows
    ]
