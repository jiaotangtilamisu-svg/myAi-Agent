from pathlib import Path
import pytest
from tools.data_governance import case_migration as m
SQL=Path(__file__).resolve().parents[3]/'sql/09_aftersales_cases.sql'

def test_only_existing_reviewed_ddl(): assert len(m.reviewed_statements(SQL))==4

def test_rejects_extra_write(tmp_path):
 p=tmp_path/'bad.sql';p.write_bytes(SQL.read_bytes()+b'\nDELETE FROM order_info;')
 with pytest.raises(ValueError,match='UNREVIEWED'):m.reviewed_statements(p)

def test_dry_run_does_not_write_database(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'columns',lambda _:set())
 monkeypatch.setattr(m,'mysql',lambda _:pytest.fail('write attempted'))
 result=m.run(SQL,tmp_path/'plan.json');assert result['create']==list(m.TABLES) and not result['applied']

def test_apply_requires_verified_backup(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'columns',lambda _:set())
 monkeypatch.setattr(m,'mysql',lambda _:pytest.fail('write attempted'))
 with pytest.raises(ValueError,match='BACKUP_REQUIRED'):m.run(SQL,tmp_path/'plan.json',apply=True)

def test_existing_incompatible_table_blocks(monkeypatch,tmp_path):
 monkeypatch.setattr(m,'columns',lambda _:{'unrelated_column'})
 with pytest.raises(ValueError,match='MISMATCH'):m.run(SQL,tmp_path/'plan.json',apply=True)
