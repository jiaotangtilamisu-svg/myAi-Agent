"""Explicit additive initialization, with a verified pre-operation backup."""

import argparse
import re
from pathlib import Path

from .cli import verified_backup


def statements(path):
    text = "\n".join(
        line
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )
    result = [s.strip() for s in text.split(";") if s.strip()]
    if len(result) != 5:
        raise ValueError("UNEXPECTED_MIGRATION_SCOPE")
    for sql in result:
        if not (
            re.match(
                r"^CREATE DATABASE IF NOT EXISTS simlect_data_governance\s", sql, re.I
            )
            or sql == "USE simlect_data_governance"
            or re.match(
                r"^CREATE TABLE IF NOT EXISTS (etl_batch|source_record|historical_record)\s*\(",
                sql,
                re.I,
            )
        ):
            raise ValueError("UNEXPECTED_MIGRATION_SCOPE")
        if re.search(r"\b(DROP|TRUNCATE|DELETE|ALTER|UPDATE|INSERT)\b", sql, re.I):
            raise ValueError("NON_ADDITIVE_MIGRATION")
    return result


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--sql", type=Path, default=Path("sql/21_data_governance.sql"))
    p.add_argument(
        "--env-file", type=Path, default=Path("Simlect-backend/Simlect-agent/.env")
    )
    p.add_argument("--backup-manifest", type=Path)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    sql = statements(a.sql)
    if not a.apply:
        print("VALIDATED: one new schema, three new tables; no business DDL/DML")
        return
    if not a.backup_manifest:
        raise ValueError("BACKUP_REQUIRED")
    verified_backup(a.backup_manifest)
    import pymysql
    from dotenv import dotenv_values

    e = dotenv_values(a.env_file)
    c = pymysql.connect(
        host=e.get("MYSQL_HOST", "127.0.0.1"),
        port=int(e.get("MYSQL_PORT", 13306)),
        user=e["MYSQL_USER"],
        password=e["MYSQL_PASSWORD"],
        charset="utf8mb4",
    )
    try:
        with c.cursor() as cursor:
            for command in sql:
                cursor.execute(command)
        print(
            "APPLIED: isolated schema and three tables; existing business tables unchanged"
        )
    finally:
        c.close()


if __name__ == "__main__":
    main()
