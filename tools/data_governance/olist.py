"""Streaming CSV inspection on an E-drive SQLite spool, not a new business database."""

import csv
import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DATASET = "olistbr/brazilian-ecommerce"
SOURCE_URL = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"
LICENSE = "CC-BY-NC-SA-4.0"
# Entity: filename, natural key, required columns, validated relationships.
SPECS = {
    "customers": (
        "olist_customers_dataset.csv",
        ("customer_id",),
        ("customer_unique_id",),
        {},
    ),
    "sellers": ("olist_sellers_dataset.csv", ("seller_id",), (), {}),
    "products": (
        "olist_products_dataset.csv",
        ("product_id",),
        ("product_category_name",),
        {},
    ),
    "orders": (
        "olist_orders_dataset.csv",
        ("order_id",),
        ("customer_id", "order_status", "order_purchase_timestamp"),
        {"customer_id": "customers"},
    ),
    "order_items": (
        "olist_order_items_dataset.csv",
        ("order_id", "order_item_id"),
        ("product_id", "seller_id", "price", "freight_value"),
        {"order_id": "orders", "product_id": "products", "seller_id": "sellers"},
    ),
    "order_payments": (
        "olist_order_payments_dataset.csv",
        ("order_id", "payment_sequential"),
        ("payment_type", "payment_installments", "payment_value"),
        {"order_id": "orders"},
    ),
    "order_reviews": (
        "olist_order_reviews_dataset.csv",
        (),
        ("review_id", "order_id", "review_score"),
        {"order_id": "orders"},
    ),
    "geolocation": (
        "olist_geolocation_dataset.csv",
        (),
        ("geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"),
        {},
    ),
    "category_translation": (
        "product_category_name_translation.csv",
        ("product_category_name",),
        ("product_category_name_english",),
        {},
    ),
}
MONEY = {"price", "freight_value", "payment_value"}
NUMBERS = {
    "order_item_id",
    "payment_sequential",
    "payment_installments",
    "review_score",
    "product_weight_g",
    "product_length_cm",
    "product_height_cm",
    "product_width_cm",
    "product_name_lenght",
    "product_description_lenght",
    "product_photos_qty",
}


def canonical(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize(row):
    result = {}
    for key, value in row.items():
        if key is None or not isinstance(value, str):
            raise ValueError("CSV_COLUMN_COUNT")
        value = value.strip()
        if len(value) > 32768:
            raise ValueError("FIELD_TOO_LONG")
        if not value:
            result[key] = None
            continue
        if key in MONEY:
            try:
                number = Decimal(value)
            except InvalidOperation as e:
                raise ValueError("INVALID_MONEY") from e
            if (
                not number.is_finite()
                or number < 0
                or number > Decimal("9999999999.99")
            ):
                raise ValueError("INVALID_MONEY")
            if number != number.quantize(Decimal(".01")):
                raise ValueError("MONEY_PRECISION")
            result[key] = format(number.quantize(Decimal(".01")), "f")
        elif key in NUMBERS:
            if not value.isdigit():
                raise ValueError("INVALID_INTEGER")
            result[key] = int(value)
        elif (
            key.endswith("_timestamp")
            or key.endswith("_date")
            or key in {"shipping_limit_date", "order_estimated_delivery_date"}
        ):
            try:
                datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                raise ValueError("INVALID_TIMESTAMP") from e
            result[key] = value  # Source-local time, never pretend this is UTC.
        elif key in {"geolocation_lat", "geolocation_lng"}:
            try:
                number = Decimal(value)
            except InvalidOperation as e:
                raise ValueError("INVALID_COORDINATE") from e
            bound = 90 if key.endswith("lat") else 180
            if not number.is_finite() or abs(number) > bound:
                raise ValueError("INVALID_COORDINATE")
            result[key] = str(number)
        else:
            result[key] = value
    return result


class Stager:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.executescript("""CREATE TABLE IF NOT EXISTS records(entity TEXT, record_id TEXT, payload TEXT NOT NULL, sha TEXT NOT NULL, PRIMARY KEY(entity,record_id));
   CREATE TABLE IF NOT EXISTS refs(entity TEXT,record_id TEXT,ref_entity TEXT,ref_id TEXT);
   CREATE INDEX IF NOT EXISTS ref_lookup ON refs(ref_entity,ref_id);""")

    def close(self):
        self.db.close()

    def rows(self):
        yield from self.db.execute(
            "SELECT entity,record_id,payload,sha FROM records ORDER BY entity,record_id"
        )

    def inspect(self, directory, version):
        directory = Path(directory).resolve()
        report = {
            "dataset": DATASET,
            "sourceType": "PUBLIC_DATASET",
            "sourceUrl": SOURCE_URL,
            "license": LICENSE,
            "version": version,
            "currency": "BRL",
            "sourceTimezone": "UNSPECIFIED",
            "files": {},
            "counts": {},
            "duplicates": {},
            "errors": {},
            "warnings": {},
            "missingFiles": [],
            "status": "INVALID",
        }
        for entity, (filename, *_) in SPECS.items():
            path = directory / filename
            if not path.is_file():
                report["missingFiles"].append(filename)
        if report["missingFiles"]:
            return report
        if self.db.execute("SELECT COUNT(*) FROM records").fetchone()[0]:
            raise ValueError("Stager must be empty")

        def error(code):
            report["errors"][code] = report["errors"].get(code, 0) + 1

        for entity, (filename, keys, required, relations) in SPECS.items():
            path = directory / filename
            if not path.resolve().is_relative_to(directory):
                raise ValueError("INPUT_PATH_ESCAPE")
            before_hash = file_digest(path)
            count = duplicate = 0
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                if (
                    not reader.fieldnames
                    or len(set(reader.fieldnames)) != len(reader.fieldnames)
                    or not set(keys + required).issubset(reader.fieldnames)
                ):
                    error("MISSING_OR_DUPLICATE_COLUMNS:" + entity)
                    continue
                for raw in reader:
                    try:
                        row = normalize(raw)
                        if any(
                            row.get(k) is None
                            for k in keys + required
                            if k != "product_category_name"
                        ):
                            raise ValueError("MISSING_REQUIRED_VALUE")
                        if (
                            entity == "order_reviews"
                            and not 1 <= row["review_score"] <= 5
                        ):
                            raise ValueError("INVALID_REVIEW_SCORE")
                        if entity == "order_items" and row["order_item_id"] < 1:
                            raise ValueError("INVALID_ITEM_SEQUENCE")
                        payload = canonical(row)
                        sha = digest(payload)
                        # Reviews and geolocation have no reliable single-column PK; retain distinct source rows.
                        rid = canonical([str(row[k]) for k in keys]) if keys else sha
                        found = self.db.execute(
                            "SELECT sha FROM records WHERE entity=? AND record_id=?",
                            (entity, rid),
                        ).fetchone()
                        if found:
                            if found[0] != sha:
                                raise ValueError("CONFLICTING_DUPLICATE")
                            duplicate += 1
                            continue
                        self.db.execute(
                            "INSERT INTO records VALUES(?,?,?,?)",
                            (entity, rid, payload, sha),
                        )
                        for field, target in relations.items():
                            self.db.execute(
                                "INSERT INTO refs VALUES(?,?,?,?)",
                                (entity, rid, target, canonical([str(row[field])])),
                            )
                        if (
                            entity == "orders"
                            and row.get("order_delivered_customer_date")
                            and row["order_delivered_customer_date"]
                            < row["order_purchase_timestamp"]
                        ):
                            report["warnings"]["DELIVERY_BEFORE_PURCHASE"] = (
                                report["warnings"].get("DELIVERY_BEFORE_PURCHASE", 0)
                                + 1
                            )
                        count += 1
                    except (ValueError, KeyError) as e:
                        error(
                            str(e)
                            if isinstance(e, ValueError)
                            else "MISSING_REQUIRED_VALUE"
                        )
            after_hash = file_digest(path)
            if before_hash != after_hash:
                error("FILE_CHANGED_DURING_READ:" + entity)
            report["files"][filename] = {
                "sha256": before_hash,
                "bytes": path.stat().st_size,
            }
            report["counts"][entity] = count
            report["duplicates"][entity] = duplicate
            self.db.commit()
        for entity, missing in self.db.execute(
            "SELECT r.entity,COUNT(*) FROM refs r LEFT JOIN records p ON p.entity=r.ref_entity AND p.record_id=r.ref_id WHERE p.record_id IS NULL GROUP BY r.entity"
        ):
            report["errors"]["ORPHAN_REFERENCE:" + entity] = missing
        report["batchId"] = digest(
            canonical(
                {"dataset": DATASET, "version": version, "files": report["files"]}
            )
        )
        report["status"] = "VALID" if not report["errors"] else "INVALID"
        return report
