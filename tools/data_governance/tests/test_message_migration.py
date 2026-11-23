from pathlib import Path
import pytest
from tools.data_governance import message_migration as mod

def test_exact_widening_scope():
    mod.validate_sql(Path(__file__).resolve().parents[3]/'sql/23_agent_message_evidence.sql')

@pytest.mark.parametrize('sql',[mod.DDL+'; DELETE FROM simlect_agent.agent_message;',mod.DDL.replace('MEDIUMTEXT','VARCHAR(2000)'),mod.DDL.replace('agent_message','order_info')])
def test_rejects_destructive_or_unrelated_sql(tmp_path,sql):
    file=tmp_path/'migration.sql';file.write_text(sql,encoding='utf-8')
    with pytest.raises(ValueError):mod.validate_sql(file)
