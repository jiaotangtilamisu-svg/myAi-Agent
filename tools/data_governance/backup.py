"""Backup the existing project databases without exposing a password on the host CLI."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "before-governance.sql"
    if target.exists():
        raise ValueError("BACKUP_ALREADY_EXISTS")
    schemas = [
        "simlect_user",
        "simlect_product",
        "simlect_stock",
        "simlect_cart",
        "simlect_order",
        "simlect_pay",
        "simlect_coupon",
        "simlect_search",
        "simlect_agent",
        "simlect_admin",
    ]
    command = (
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --events --hex-blob --no-tablespaces --set-gtid-purged=OFF --databases '
        + " ".join(schemas)
    )
    with target.open("xb") as out:
        result = subprocess.run(
            ["docker", "exec", "simlect-mysql", "sh", "-c", command],
            stdout=out,
            stderr=subprocess.PIPE,
            check=False,
        )
    if result.returncode:
        raise RuntimeError(
            "BACKUP_FAILED; incomplete file retained, no database changes permitted"
        )
    h = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    manifest = {
        "file": str(target.resolve()),
        "sha256": h.hexdigest(),
        "schemas": schemas,
        "bytes": target.stat().st_size,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "mode": "single-transaction",
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "backup": str(target.resolve()),
                "bytes": manifest["bytes"],
                "sha256": manifest["sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
