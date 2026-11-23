"""One-column widening, verified backup required, row fingerprints checked."""
import argparse
import json
from pathlib import Path
from .cli import verified_backup
from .policy_migration import mysql

DDL = "ALTER TABLE simlect_agent.agent_message MODIFY COLUMN biz_data MEDIUMTEXT NULL COMMENT '业务数据及完整证据JSON'"

def validate_sql(path):
    text = '\n'.join(line for line in Path(path).read_text(encoding='utf-8-sig').splitlines() if not line.strip().startswith('--'))
    if ' '.join(text.strip().rstrip(';').split()) != DDL:
        raise ValueError('UNEXPECTED_MESSAGE_MIGRATION_SCOPE')

def snapshot():
    rows=mysql("START TRANSACTION READ ONLY; SELECT JSON_OBJECT('type',DATA_TYPE,'maxBytes',CHARACTER_OCTET_LENGTH) FROM information_schema.columns WHERE TABLE_SCHEMA='simlect_agent' AND TABLE_NAME='agent_message' AND COLUMN_NAME='biz_data'; SELECT JSON_OBJECT('rows',COUNT(*),'nulls',SUM(biz_data IS NULL),'maxChars',MAX(CHAR_LENGTH(biz_data)),'maxBytes',MAX(OCTET_LENGTH(biz_data)),'invalidJson',SUM(biz_data IS NOT NULL AND NOT JSON_VALID(biz_data))) FROM simlect_agent.agent_message; SELECT JSON_OBJECT('id',message_id,'sha256',SHA2(CAST(JSON_OBJECT('a',assistant_message,'u',user_message,'t',send_time,'owner',user_id,'s',status,'kind',biz_type,'data',biz_data) AS CHAR CHARACTER SET utf8mb4),256)) FROM simlect_agent.agent_message ORDER BY message_id; ROLLBACK;")
    data=[json.loads(row) for row in rows]
    return {'column':data[0], 'stats':data[1], 'rowHashes':data[2:]}

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--sql',type=Path,default=Path('sql/23_agent_message_evidence.sql'));p.add_argument('--backup-manifest',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args(argv)
    validate_sql(a.sql)
    if a.output.exists():raise ValueError('REPORT_EXISTS_PRESERVE_EVIDENCE')
    before=snapshot();report={'before':before,'mode':'DRY_RUN','changed':False}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    if a.apply:
        if not a.backup_manifest:raise ValueError('BACKUP_REQUIRED')
        backup=verified_backup(a.backup_manifest)
        if 'simlect_agent' not in backup.get('schemas',[]):raise ValueError('BACKUP_SCOPE_INCOMPLETE')
        if before['column']['type'] not in {'varchar','text','mediumtext','longtext'}:raise ValueError('UNEXPECTED_COLUMN_TYPE')
        report['mode']='APPLY';report['backupSha256']=backup['sha256']
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if before['column']['type'] not in {'mediumtext','longtext'}:
            mysql('SET SESSION lock_wait_timeout=5; '+DDL+';');report['changed']=True
        after=snapshot();report['after']=after
        report['rowsPreserved']=before['rowHashes']==after['rowHashes']
        if not report['rowsPreserved']:
            a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');raise RuntimeError('ROW_FINGERPRINT_CHANGED_INSPECT_NO_AUTOMATIC_ROLLBACK')
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'before','after'}},ensure_ascii=False))

if __name__=='__main__':main()
