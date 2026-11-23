"""Opt-in, bounded MySQL integration; only a generated disposable schema is writable."""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.data_governance.policy_migration import mysql

def main():
    out=ROOT/('.cache/stage33/mysql' if os.environ.get('QUALITY_STAGE33')=='1' else '.cache/stage32/mysql');out.mkdir(parents=True,exist_ok=True)
    # Backup the existing case tables before any test-schema DDL; never display contents.
    backup=out/'production-cases-backup.sql'
    if not backup.exists():
        dump=subprocess.run(['docker','exec','simlect-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF simlect_order aftersales_case aftersales_plan aftersales_manual_task aftersales_audit'],capture_output=True)
        if dump.returncode:raise RuntimeError('BACKUP_FAILED_NO_SCHEMA_CREATED')
        backup.write_bytes(dump.stdout)
    manifest={'backupSHA256':hashlib.sha256(backup.read_bytes()).hexdigest(),'backupBytes':backup.stat().st_size}
    schema='simlect_quality32_'+uuid.uuid4().hex[:12]
    assert re.fullmatch(r'simlect_quality32_[a-f0-9]{12}',schema)
    secret=subprocess.run(['docker','exec','simlect-mysql','printenv','MYSQL_ROOT_PASSWORD'],capture_output=True,check=True).stdout.decode().strip()
    if not secret:raise RuntimeError('LOCAL_DB_CREDENTIAL_UNAVAILABLE')
    env=os.environ.copy();env.update(QUALITY_MYSQL_SCHEMA=schema,QUALITY_MYSQL_PASSWORD=secret,QUALITY_CASE_OUTPUT=str(out),JAVA_HOME='E:\\JDK17',TEMP='E:\\SimlectRuntime\\tmp',TMP='E:\\SimlectRuntime\\tmp')
    env['PATH']='E:\\JDK17\\bin;'+env['PATH']
    report={**manifest,'schema':schema,'scope':'REAL_ISOLATED_MYSQL_CONTROLLER_TRANSACTION_MAPPER_ORDER_OWNERSHIP_SQL; AUTH_SESSION_FIXTURE_MOCK','realFinanceCalls':0,'cleanup':False}
    created=False
    try:
        mysql('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4;');created=True
        if (out/'maven.log').exists():
            import shutil
            shutil.copy2(out/'maven.log',out/('maven-prior-'+uuid.uuid4().hex[:8]+'.log'))
        with (out/'maven.log').open('wb') as log:
            result=subprocess.run(['E:\\develop\\apache-maven-3.9.4-bin\\apache-maven-3.9.4\\bin\\mvn.cmd','-o','-pl','Simlect-order/app','-am','test','-Dtest=AftersalesCaseMySqlIT','-Dsurefire.failIfNoSpecifiedTests=false','-DargLine=-Xmx256m'],cwd=ROOT/'Simlect-backend',env=env,stdout=log,stderr=subprocess.STDOUT)
        report['exitCode']=result.returncode
        text=(out/'maven.log').read_text(encoding='utf8',errors='replace')
        counts=re.findall(r'Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+).* -- in com.simlect.biz.AftersalesCaseMySqlIT',text)
        if counts:report.update(dict(zip(('tests','failures','errors','skipped'),map(int,counts[-1]))))
        env['PYTHONUTF8']='1'
        with (out/'messages.log').open('wb') as log:
            message_run=subprocess.run([str(ROOT/'Simlect-backend/Simlect-agent/.venv/Scripts/python.exe'),str(ROOT/'tools/quality_engineering/stage32/mysql_messages.py')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['messageExitCode']=message_run.returncode
        report['finalFixtureCounts']=mysql('SELECT (SELECT COUNT(*) FROM `'+schema+'`.aftersales_case),(SELECT COUNT(*) FROM `'+schema+'`.aftersales_audit);')
    finally:
        if created:
            assert re.fullmatch(r'simlect_quality32_[a-f0-9]{12}',schema)
            mysql('DROP DATABASE `'+schema+'`;')  # Only the exact generated disposable schema.
            report['cleanup']=not mysql("SELECT schema_name FROM information_schema.schemata WHERE schema_name='"+schema+"';")
        env.pop('QUALITY_MYSQL_PASSWORD',None);secret=''
        (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'schema','finalFixtureCounts'}}))
    return report.get('exitCode',1) or report.get('messageExitCode',1)

if __name__=='__main__':raise SystemExit(main())
