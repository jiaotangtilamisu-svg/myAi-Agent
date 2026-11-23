from pathlib import Path

import pytest

from tools.data_governance.policy_migration import statements

SQL = Path(__file__).resolve().parents[3] / 'sql' / '22_policy_governance.sql'


def test_policy_schema_scope_is_additive_and_complete():
    assert len(statements(SQL)) == 13


@pytest.mark.parametrize('replacement', ['DROP TABLE knowledge_document', 'TRUNCATE knowledge_document', 'ALTER TABLE product_info ADD COLUMN bad int', 'UPDATE knowledge_document SET approved=true'])
def test_policy_migration_rejects_unrelated_or_destructive_sql(tmp_path, replacement):
    text=SQL.read_text(encoding='utf-8').replace("ALTER TABLE knowledge_document ADD COLUMN category varchar(32) NOT NULL DEFAULT 'PLATFORM_DEMO'",replacement)
    path=tmp_path/'bad.sql';path.write_text(text,encoding='utf-8')
    with pytest.raises(ValueError): statements(path)
