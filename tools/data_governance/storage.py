"""Append-only MySQL sink, limited to its own schema. SQLite sink is for offline tests."""

from datetime import datetime, timezone

from .olist import canonical, digest

SCHEMA = "simlect_data_governance"
SOURCE_TYPES = {"PUBLIC_DATASET", "SYNTHETIC", "MANUAL", "LIVE_API"}


def record_key(dataset, entity, rid, version):
    return digest(canonical([dataset, entity, rid, version]))


def apply_batch(connection, report, rows, *, sqlite=False):
    if report.get("status") != "VALID" or not report.get("batchId"):
        raise ValueError("VALIDATED_BATCH_REQUIRED")
    if report.get("sourceType") not in SOURCE_TYPES:
        raise ValueError("INVALID_SOURCE_TYPE")
    database = getattr(connection, "db", None)
    if isinstance(database, bytes):
        database = database.decode()
    if not sqlite and database != SCHEMA:
        raise ValueError("ISOLATED_SCHEMA_REQUIRED")
    placeholder = "?" if sqlite else "%s"

    def query(cur, sql, args=()):
        return cur.execute(sql.replace("?", placeholder), args)

    cur = connection.cursor()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if sqlite:
        now = now.isoformat(sep=" ")
    batch = report["batchId"]
    inserted = 0
    try:
        query(
            cur,
            "SELECT status FROM etl_batch WHERE batch_id=?"
            + ("" if sqlite else " FOR UPDATE"),
            (batch,),
        )
        existing = cur.fetchone()
        if existing and existing[0] == "COMMITTED":
            connection.rollback()
            return {"status": "ALREADY_IMPORTED", "inserted": 0}
        if existing:
            query(
                cur,
                "UPDATE etl_batch SET status=? WHERE batch_id=?",
                ("RUNNING", batch),
            )
        else:
            query(
                cur,
                "INSERT INTO etl_batch(batch_id,dataset,source_version,status,report_json,created_at) VALUES(?,?,?,?,?,?)",
                (
                    batch,
                    report["dataset"],
                    report["version"],
                    "RUNNING",
                    canonical(report),
                    now,
                ),
            )
        for entity, rid, payload, sha in rows:
            if sha != digest(payload):
                raise ValueError("CONTENT_HASH_MISMATCH")
            key = record_key(report["dataset"], entity, rid, report["version"])
            query(
                cur,
                "SELECT content_sha256 FROM source_record WHERE record_key=?",
                (key,),
            )
            prior = cur.fetchone()
            if prior:
                if prior[0] != sha:
                    raise ValueError("IMMUTABLE_VERSION_CONFLICT")
                continue
            fields = canonical(
                report.get("fieldSources") or {"*": report["sourceType"]}
            )
            query(
                cur,
                "INSERT INTO source_record(record_key,source_type,source_name,entity_type,original_id,source_version,batch_id,content_sha256,source_url,license_code,currency,observed_at,field_sources) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    report["sourceType"],
                    report["dataset"],
                    entity,
                    rid,
                    report["version"],
                    batch,
                    sha,
                    report["sourceUrl"],
                    report["license"],
                    report.get("currency"),
                    now,
                    fields,
                ),
            )
            query(
                cur,
                "INSERT INTO historical_record(record_key,entity_type,payload) VALUES(?,?,?)",
                (key, entity, payload),
            )
            inserted += 1
        query(
            cur,
            "UPDATE etl_batch SET status=?,completed_at=? WHERE batch_id=?",
            ("COMMITTED", now, batch),
        )
        connection.commit()
        return {"status": "COMMITTED", "inserted": inserted}
    except Exception:
        connection.rollback()
        # Audit failure separately; no partial historical rows survive.
        try:
            query(cur, "SELECT status FROM etl_batch WHERE batch_id=?", (batch,))
            prior = cur.fetchone()
            audit = {**report, "lastExecutionFailure": "TRANSACTION_ROLLED_BACK"}
            if not prior:
                query(
                    cur,
                    "INSERT INTO etl_batch(batch_id,dataset,source_version,status,report_json,created_at) VALUES(?,?,?,?,?,?)",
                    (
                        batch,
                        report["dataset"],
                        report["version"],
                        "FAILED",
                        canonical(audit),
                        now,
                    ),
                )
            elif prior[0] != "COMMITTED":
                query(
                    cur,
                    "UPDATE etl_batch SET status=?,report_json=? WHERE batch_id=? AND status<>?",
                    ("FAILED", canonical(audit), batch, "COMMITTED"),
                )
            connection.commit()
        except Exception:
            connection.rollback()
        raise
    finally:
        cur.close()
