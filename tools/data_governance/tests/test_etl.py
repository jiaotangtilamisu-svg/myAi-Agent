import csv
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.data_governance.adapters import (
    BusinessReadAdapter,
    StockScenarioAdapter,
    SyntheticBinding,
    order_scenario_plan,
)
from tools.data_governance.catalogue import (
    candidates,
    staged_catalogue,
    validate_candidate,
)
from tools.data_governance.migrate import statements
from tools.data_governance.olist import SPECS, Stager, canonical, digest, normalize
from tools.data_governance.storage import apply_batch


@pytest.fixture
def files(tmp_path):
    rows = {
        "customers": [{"customer_id": "C1", "customer_unique_id": "U1"}],
        "sellers": [{"seller_id": "S1"}],
        "products": [{"product_id": "P1", "product_category_name": "casa"}],
        "orders": [
            {
                "order_id": "O1",
                "customer_id": "C1",
                "order_status": "delivered",
                "order_purchase_timestamp": "2018-01-01 10:00:00",
            }
        ],
        "order_items": [
            {
                "order_id": "O1",
                "order_item_id": "1",
                "product_id": "P1",
                "seller_id": "S1",
                "price": "10.20",
                "freight_value": "0.00",
            }
        ],
        "order_payments": [
            {
                "order_id": "O1",
                "payment_sequential": "1",
                "payment_type": "credit_card",
                "payment_installments": "1",
                "payment_value": "10.20",
            }
        ],
        "order_reviews": [{"review_id": "R1", "order_id": "O1", "review_score": "5"}],
        "geolocation": [
            {
                "geolocation_zip_code_prefix": "00123",
                "geolocation_lat": "-23.5",
                "geolocation_lng": "-46.6",
            }
        ],
        "category_translation": [
            {"product_category_name": "casa", "product_category_name_english": "home"}
        ],
    }

    def write(entity, values):
        with (tmp_path / SPECS[entity][0]).open(
            "w", encoding="utf-8-sig", newline=""
        ) as f:
            writer = csv.DictWriter(f, fieldnames=values[0].keys())
            writer.writeheader()
            writer.writerows(values)

    for entity, values in rows.items():
        write(entity, values)
    return tmp_path, rows, write


def inspect(files, tmp_path):
    s = Stager(tmp_path / "spool.sqlite")
    return s, s.inspect(files[0], "test-v1")


def sink():
    c = sqlite3.connect(":memory:")
    c.executescript("""CREATE TABLE etl_batch(batch_id TEXT PRIMARY KEY,dataset TEXT,source_version TEXT,status TEXT,report_json TEXT,created_at TEXT,completed_at TEXT);
 CREATE TABLE source_record(record_key TEXT PRIMARY KEY,source_type TEXT,source_name TEXT,entity_type TEXT,original_id TEXT,source_version TEXT,batch_id TEXT,content_sha256 TEXT,source_url TEXT,license_code TEXT,currency TEXT,observed_at TEXT,field_sources TEXT);
 CREATE TABLE historical_record(record_key TEXT PRIMARY KEY,entity_type TEXT,payload TEXT);""")
    return c


def test_all_nine_files_and_foreign_keys(files, tmp_path):
    s, r = inspect(files, tmp_path)
    assert (
        r["status"] == "VALID" and len(list(s.rows())) == 9 and r["currency"] == "BRL"
    )
    s.close()


def test_missing_files_never_import(tmp_path):
    s = Stager(tmp_path / "spool.sqlite")
    r = s.inspect(tmp_path, "v1")
    assert len(r["missingFiles"]) == 9
    with pytest.raises(ValueError):
        apply_batch(sink(), r, [], sqlite=True)
    s.close()


def test_rejected_apply_still_writes_quality_report(tmp_path, monkeypatch):
    from tools.data_governance import cli

    monkeypatch.setattr(cli, "verified_backup", lambda _: {})
    connect = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(cli, "connect", connect)
    out = tmp_path / "quality.json"
    with pytest.raises(ValueError, match="DATA_QUALITY_FAILED"):
        cli.main(
            [
                "--input",
                str(tmp_path),
                "--version",
                "test-v1",
                "--output",
                str(out),
                "--apply",
                "--backup-manifest",
                "test-only",
            ]
        )
    assert len(json.loads(out.read_text())["missingFiles"]) == 9
    connect.assert_not_called()


def test_identical_duplicates_are_reported(files, tmp_path):
    path, rows, write = files
    write("order_items", rows["order_items"] * 2)
    s, r = inspect(files, tmp_path)
    assert r["status"] == "VALID" and r["duplicates"]["order_items"] == 1
    s.close()


def test_conflicting_duplicate_rejected(files, tmp_path):
    path, rows, write = files
    write(
        "order_items",
        [rows["order_items"][0], {**rows["order_items"][0], "price": "99.00"}],
    )
    s, r = inspect(files, tmp_path)
    assert r["errors"]["CONFLICTING_DUPLICATE"] == 1
    s.close()


@pytest.mark.parametrize(
    "entity,field",
    [
        ("orders", "customer_id"),
        ("order_items", "product_id"),
        ("order_items", "seller_id"),
        ("order_items", "order_id"),
        ("order_payments", "order_id"),
        ("order_reviews", "order_id"),
    ],
)
def test_orphan_reference_rejected(files, tmp_path, entity, field):
    path, rows, write = files
    write(entity, [{**rows[entity][0], field: "MISSING"}])
    s, r = inspect(files, tmp_path)
    assert r["status"] == "INVALID" and any(
        k.startswith("ORPHAN_REFERENCE") for k in r["errors"]
    )
    s.close()


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-1", "1.001", "a"])
def test_invalid_money_rejected(value):
    with pytest.raises(ValueError):
        normalize({"price": value})


def test_null_is_not_zero_and_zip_prefix_is_not_integer():
    assert normalize({"price": "", "geolocation_zip_code_prefix": "00123"}) == {
        "price": None,
        "geolocation_zip_code_prefix": "00123",
    }


def test_reviews_same_review_id_distinct_order_rows_preserved(files, tmp_path):
    path, rows, write = files
    write(
        "order_reviews",
        [rows["order_reviews"][0], {**rows["order_reviews"][0], "review_score": "4"}],
    )
    s, r = inspect(files, tmp_path)
    assert r["counts"]["order_reviews"] == 2
    s.close()


def test_geolocation_has_no_fake_zip_primary_key(files, tmp_path):
    path, rows, write = files
    write(
        "geolocation",
        [
            rows["geolocation"][0],
            {**rows["geolocation"][0], "geolocation_lat": "-23.6"},
        ],
    )
    s, r = inspect(files, tmp_path)
    assert r["counts"]["geolocation"] == 2
    s.close()


def test_idempotent_import_and_origin(files, tmp_path):
    s, r = inspect(files, tmp_path)
    c = sink()
    assert apply_batch(c, r, s.rows(), sqlite=True)["inserted"] == 9
    assert apply_batch(c, r, s.rows(), sqlite=True)["status"] == "ALREADY_IMPORTED"
    assert c.execute(
        "SELECT DISTINCT source_type,currency,license_code FROM source_record"
    ).fetchall() == [("PUBLIC_DATASET", "BRL", "CC-BY-NC-SA-4.0")]
    assert c.execute("SELECT COUNT(*) FROM historical_record").fetchone()[0] == 9
    s.close()
    c.close()


def test_rollback_keeps_no_partial_data(files, tmp_path):
    s, r = inspect(files, tmp_path)
    rows = list(s.rows())
    entity, rid, payload, sha = rows[-1]
    rows[-1] = (entity, rid, payload, "wrong")
    c = sink()
    with pytest.raises(ValueError):
        apply_batch(c, r, rows, sqlite=True)
    assert c.execute("SELECT COUNT(*) FROM historical_record").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM source_record").fetchone()[0] == 0
    assert c.execute("SELECT status FROM etl_batch").fetchone()[0] == "FAILED"
    assert apply_batch(c, r, s.rows(), sqlite=True)["status"] == "COMMITTED"
    s.close()
    c.close()


def test_same_version_changes_rejected_without_overwriting(files, tmp_path):
    s, r = inspect(files, tmp_path)
    c = sink()
    rows = list(s.rows())
    apply_batch(c, r, rows, sqlite=True)
    changed = deepcopy(r)
    changed["batchId"] = "different-batch"
    entity, rid, _, _ = rows[0]
    payload = canonical({"changed": True})
    with pytest.raises(ValueError):
        apply_batch(c, changed, [(entity, rid, payload, digest(payload))], sqlite=True)
    assert c.execute("SELECT COUNT(*) FROM historical_record").fetchone()[0] == 9
    s.close()
    c.close()


def test_versioned_append_retains_old_records(files, tmp_path):
    s, r = inspect(files, tmp_path)
    c = sink()
    rows = list(s.rows())
    apply_batch(c, r, rows, sqlite=True)
    v = deepcopy(r)
    v["version"] = "v2"
    v["batchId"] = "batch-v2"
    apply_batch(c, v, rows, sqlite=True)
    assert c.execute("SELECT COUNT(*) FROM historical_record").fetchone()[0] == 18
    s.close()
    c.close()


def test_wrong_live_schema_blocked_before_query():
    c = Mock()
    c.db = "simlect_order"
    r, _ = staged_catalogue()
    with pytest.raises(ValueError):
        apply_batch(c, r, [])
    c.cursor.assert_not_called()


def test_catalogue_has_five_groups_and_explicit_synthetic_fields():
    rows = candidates()
    assert len(rows) == 15 and len({r["category"] for r in rows}) == 5
    assert all(
        validate_candidate(r)["fieldSources"]["price"] == "SYNTHETIC" for r in rows
    )
    assert all(r["publicationStatus"] == "NOT_PUBLISHED" for r in rows)


def test_no_implicit_currency_conversion():
    r = candidates()[0]
    r["currency"] = "BRL"
    with pytest.raises(ValueError):
        validate_candidate(r)


def test_stock_adapter_reuses_java_idempotency_and_compensation():
    transport = Mock()
    binding = SyntheticBinding("SRC1", "P1", "a" * 32, "SYNTHETIC", "SYNTH_A")
    intents = {}

    def claim(k, v):
        if k in intents and intents[k] != v:
            raise ValueError("CHANGED_INTENT")
        intents[k] = v

    adapter = StockScenarioAdapter(transport, lambda _: binding, claim)
    adapter.reserve("SRC1", "case1", 2)
    adapter.reserve("SRC1", "case1", 2)
    first = transport.post.call_args.args[1]
    assert first["items"][0]["changeAmount"] == -2
    adapter.release("SRC1", "case1", 2)
    release = transport.post.call_args.args[1]
    assert (
        release["requiredOperationId"] == first["operationId"]
        and release["items"][0]["changeAmount"] == 2
    )
    with pytest.raises(ValueError):
        adapter.reserve("SRC1", "case1", 3)


@pytest.mark.parametrize(
    "source,user",
    [
        ("PUBLIC_DATASET", "SYNTH_A"),
        ("SYNTHETIC", "LOCALDEMO"),
        ("LIVE_API", "SYNTH_A"),
    ],
)
def test_stock_simulation_cannot_touch_unbound_real_users_or_history(source, user):
    adapter = StockScenarioAdapter(
        Mock(), lambda _: SyntheticBinding("SRC1", "P1", "a" * 32, source, user), Mock()
    )
    with pytest.raises(ValueError):
        adapter.reserve("SRC1", "case1", 1)


def test_order_adapter_requires_verified_identity():
    transport = Mock(spec=["post"])
    a = BusinessReadAdapter(transport)
    with pytest.raises(ValueError):
        a.owned_order("O1")
    transport.verified_user_id = "A"
    a.owned_order("O1")
    assert transport.post.call_args.args[1] == {"orderId": "O1", "userId": "A"}


def test_scenario_is_plan_not_financial_execution():
    r = order_scenario_plan(
        SyntheticBinding("SRC", "P1", "a" * 32, "SYNTHETIC", "SYNTH_A")
    )
    assert (
        r["executionAllowed"] is False
        and r["existingContracts"]["mockPayment"] == "/api/order/localPay"
    )


def test_product_payload_reuses_existing_schema_and_does_not_publish():
    from tools.data_governance.adapters import product_save_dto

    dto = product_save_dto(candidates()[0], "C1", "P1", "SPEC1")
    assert dto["productInfo"]["status"] == 0
    assert "productId" not in dto["productInfo"]
    assert len(dto["skuList"]) == 2 and all("stock" not in s for s in dto["skuList"])
    assert dto["productInfo"]["minPrice"] == "99.00"
    assert all(len(s["propertyValueIdHash"]) == 32 for s in dto["skuList"])


def test_migration_is_only_new_schema_and_tables():
    assert (
        len(
            statements(
                Path(__file__).resolve().parents[3] / "sql/21_data_governance.sql"
            )
        )
        == 5
    )
