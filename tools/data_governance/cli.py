"""python -m tools.data_governance.cli; dry-run by default, no live-domain writes."""

import argparse
import json
import re
import tempfile
from pathlib import Path

from .olist import Stager, canonical, file_digest
from .storage import SCHEMA, apply_batch


def verified_backup(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    backup = Path(data["file"]).resolve()
    if (
        not backup.is_file()
        or backup.stat().st_size < 100
        or file_digest(backup) != data["sha256"]
    ):
        raise ValueError("BACKUP_VERIFICATION_FAILED")
    return data


def connect(env_file):
    import pymysql
    from dotenv import dotenv_values

    env = dotenv_values(env_file)
    return pymysql.connect(
        host=env.get("MYSQL_HOST", "127.0.0.1"),
        port=int(env.get("MYSQL_PORT", 13306)),
        user=env["MYSQL_USER"],
        password=env["MYSQL_PASSWORD"],
        database=SCHEMA,
        charset="utf8mb4",
        autocommit=False,
    )


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Olist isolated historical ETL; never writes User/Order/Pay"
    )
    p.add_argument("--input", type=Path, default=Path("data/olist/raw"))
    p.add_argument("--version", required=True)
    p.add_argument(
        "--output", type=Path, default=Path(".cache/data-governance/report.json")
    )
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument(
        "--env-file", type=Path, default=Path("Simlect-backend/Simlect-agent/.env")
    )
    p.add_argument("--backup-manifest", type=Path)
    args = p.parse_args(argv)
    if args.apply and args.dry_run:
        p.error("Choose --apply or --dry-run")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", args.version):
        p.error("Invalid dataset version")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="etl-", dir=args.output.parent) as work:
        stage = Stager(Path(work) / "spool.sqlite")
        try:
            report = stage.inspect(args.input, args.version)
            report["mode"] = "APPLY" if args.apply else "DRY_RUN"
            # Keep quality evidence even when backup or apply validation fails afterwards.
            args.output.write_text(canonical(report), encoding="utf-8")
            if args.apply:
                if not args.backup_manifest:
                    raise ValueError("BACKUP_MANIFEST_REQUIRED")
                verified_backup(args.backup_manifest)
                if report["status"] != "VALID":
                    raise ValueError("DATA_QUALITY_FAILED")
                c = connect(args.env_file)
                try:
                    report["importResult"] = apply_batch(c, report, stage.rows())
                finally:
                    c.close()
            args.output.write_text(canonical(report), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "status": report["status"],
                        "mode": report["mode"],
                        "missingFiles": report["missingFiles"],
                        "errors": report["errors"],
                        "output": str(args.output.resolve()),
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if report["status"] == "VALID" else 2
        finally:
            stage.close()


if __name__ == "__main__":
    raise SystemExit(main())
