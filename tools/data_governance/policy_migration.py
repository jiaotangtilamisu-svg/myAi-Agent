"""Stage 26 additive policy schema only. Dry-run by default, backup required to apply."""
import argparse
import json
import re
import subprocess
from pathlib import Path

from .cli import verified_backup

COLUMNS = {"category", "issuer", "original_url", "published_on", "effective_from", "effective_until", "source_status", "reviewed_revision", "reviewed_by", "index_state"}
TABLES = {"knowledge_document_source", "knowledge_policy_audit"}


def statements(path):
    text = "\n".join(line for line in Path(path).read_text(encoding="utf-8").splitlines() if not line.strip().startswith("--"))
    rows = [part.strip() for part in text.split(";") if part.strip()]
    if len(rows) != 13 or rows[0] != "USE simlect_search":
        raise ValueError("UNEXPECTED_POLICY_MIGRATION_SCOPE")
    columns, tables = set(), set()
    for sql in rows[1:]:
        alter = re.match(r"^ALTER TABLE knowledge_document ADD COLUMN ([a-z_]+)\s", sql)
        create = re.match(r"^CREATE TABLE IF NOT EXISTS ([a-z_]+)\s*\(", sql)
        if alter and alter[1] in COLUMNS:
            if alter[1] in columns: raise ValueError("DUPLICATE_COLUMN")
            columns.add(alter[1])
        elif create and create[1] in TABLES:
            if create[1] in tables: raise ValueError("DUPLICATE_TABLE")
            tables.add(create[1])
        else:
            raise ValueError("UNEXPECTED_POLICY_MIGRATION_SCOPE")
        if re.search(r"\b(DROP|DELETE|TRUNCATE|INSERT|UPDATE|REPLACE|RENAME)\b", sql, re.I):
            raise ValueError("NON_ADDITIVE_POLICY_MIGRATION")
    if columns != COLUMNS or tables != TABLES: raise ValueError("INCOMPLETE_POLICY_MIGRATION")
    return rows


def mysql(query):
    result = subprocess.run(["docker", "exec", "-i", "simlect-mysql", "sh", "-c", 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --raw --skip-column-names --default-character-set=utf8mb4'], input=query, text=True, encoding="utf-8", capture_output=True)
    if result.returncode: raise RuntimeError("POLICY_MIGRATION_DATABASE_ERROR; review server logs, backup retained")
    return result.stdout.splitlines()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--sql", type=Path, default=Path("sql/22_policy_governance.sql"))
    p.add_argument("--backup-manifest", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(argv)
    rows = statements(args.sql)
    report = {"scope": "simlect_search policy tables only", "columns": sorted(COLUMNS), "tables": sorted(TABLES), "applied": [], "skipped": [], "mode": "DRY_RUN"}
    if args.apply:
        if not args.backup_manifest: raise ValueError("BACKUP_REQUIRED")
        manifest = verified_backup(args.backup_manifest)
        if not {"simlect_search", "simlect_product", "simlect_stock", "simlect_order"}.issubset(manifest.get("schemas", [])):
            raise ValueError("BACKUP_SCOPE_INCOMPLETE")
        report["mode"] = "APPLY"
        existing = set(mysql("SELECT COLUMN_NAME FROM information_schema.columns WHERE TABLE_SCHEMA='simlect_search' AND TABLE_NAME='knowledge_document';"))
        for row in rows[1:]:
            alter = re.match(r"^ALTER TABLE knowledge_document ADD COLUMN ([a-z_]+)\s", row)
            if alter and alter[1] in existing:
                report["skipped"].append(alter[1]); continue
            mysql("USE simlect_search;\n" + row + ";")
            report["applied"].append(alter[1] if alter else re.search(r"EXISTS ([a-z_]+)", row)[1])
            args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "appliedCount": len(report["applied"]), "skippedCount": len(report["skipped"])}))


if __name__ == "__main__": main()
