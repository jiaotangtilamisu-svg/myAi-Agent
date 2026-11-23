"""Apply only reviewed stage19 additive DDL; no startup migration or automatic rollback."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from .cli import verified_backup
from .policy_migration import mysql

TABLES = ('aftersales_case', 'aftersales_plan', 'aftersales_manual_task', 'aftersales_audit')
DDL_SHA256 = 'f3c90cb5bf6345b2eada8818916fd4fd23947795de4fb616c3887255fb8d6be7'


def reviewed_statements(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != DDL_SHA256:
        raise ValueError('UNREVIEWED_CASE_DDL')
    text = '\n'.join(s for s in raw.decode('utf8').splitlines() if not s.strip().startswith('--'))
    parts = [s.strip() for s in text.split(';') if s.strip()]
    if len(parts) != 5 or parts[0] != 'USE simlect_order' or any(
            not s.startswith('CREATE TABLE IF NOT EXISTS '+t+' (') for s,t in zip(parts[1:],TABLES)):
        raise ValueError('UNEXPECTED_CASE_DDL_SCOPE')
    return parts[1:]


def columns(table):
    return set(mysql("SELECT COLUMN_NAME FROM information_schema.columns WHERE TABLE_SCHEMA='simlect_order' AND TABLE_NAME='"+table+"';"))


def run(sql_path, output, *, apply=False, backup_manifest=None):
    if Path(output).exists():
        raise ValueError('REPORT_EXISTS_PRESERVE_EVIDENCE')
    statements = reviewed_statements(sql_path)
    expected = [set(re.findall(r'^  ([a-z_]+) (?:varchar|bigint|int|char|mediumtext|datetime)',s,re.M)) for s in statements]
    existing = [columns(t) for t in TABLES]
    if any(c and not e.issubset(c) for c,e in zip(existing,expected)):
        raise ValueError('EXISTING_CASE_SCHEMA_MISMATCH')
    report={'mode':'APPLY' if apply else 'DRY_RUN','create':[t for t,c in zip(TABLES,existing) if not c],
            'existing':[t for t,c in zip(TABLES,existing) if c],'applied':[],'scope':'simlect_order additive four tables only'}
    if apply:
        backup=verified_backup(backup_manifest) if backup_manifest else None
        if not backup or 'simlect_order' not in backup.get('schemas',[]):
            raise ValueError('VERIFIED_ORDER_BACKUP_REQUIRED')
        report['backupSha256']=backup['sha256']
        Path(output).write_text(json.dumps(report,indent=2),encoding='utf8')
        # MySQL DDL autocommits. Persist progress; never claim all-or-nothing rollback.
        for table,statement,c in zip(TABLES,statements,existing):
            if not c:
                mysql('SET SESSION lock_wait_timeout=5; USE simlect_order; '+statement+';')
                report['applied'].append(table)
                Path(output).write_text(json.dumps(report,indent=2),encoding='utf8')
        if any(not e.issubset(columns(t)) for t,e in zip(TABLES,expected)):
            raise RuntimeError('CASE_SCHEMA_VERIFY_FAILED_NO_AUTOMATIC_DROP')
        report['verified']=True
    Path(output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--sql',type=Path,default=Path('sql/09_aftersales_cases.sql'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--backup-manifest',type=Path);p.add_argument('--apply',action='store_true')
    a=p.parse_args();print(json.dumps(run(a.sql,a.output,apply=a.apply,backup_manifest=a.backup_manifest)))
