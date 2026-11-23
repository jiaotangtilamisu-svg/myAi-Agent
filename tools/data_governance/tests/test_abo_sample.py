import json,sqlite3,hashlib,shutil
from pathlib import Path
import pytest
from tools.data_governance.abo_sample import inspect,localized
from tools.data_governance.storage import apply_batch
from tools.data_governance.public_sample import rollback_batch
ROOT=Path(__file__).resolve().parents[3]

@pytest.fixture
def sample(tmp_path):
 src=ROOT/'data/public-catalogue/stage31/abo'
 for name in ('sample.jsonl','manifest.json','LICENSE-CC-BY-4.0.txt'):shutil.copyfile(src/name,tmp_path/name)
 return tmp_path

def sink():
 c=sqlite3.connect(':memory:');c.executescript('''CREATE TABLE etl_batch(batch_id TEXT PRIMARY KEY,dataset TEXT,source_version TEXT,status TEXT,report_json TEXT,created_at TEXT,completed_at TEXT);
 CREATE TABLE source_record(record_key TEXT PRIMARY KEY,source_type TEXT,source_name TEXT,entity_type TEXT,original_id TEXT,source_version TEXT,batch_id TEXT,content_sha256 TEXT,source_url TEXT,license_code TEXT,currency TEXT,observed_at TEXT,field_sources TEXT);
 CREATE TABLE historical_record(record_key TEXT PRIMARY KEY,entity_type TEXT,payload TEXT);''');return c

def test_official_sample_size_types_and_unknowns(sample):
 r,rows=inspect(sample);assert r['status']=='VALID' and len(rows)==100 and len(r['categories'])==3
 for _,rid,payload,sha in rows:
  p=json.loads(payload);assert p['currentPrice'] is None and p['historicalPrice'] is None and p['stock'] is None
  assert p['purchasable'] is False and p['license']=='CC-BY-4.0' and p['sourceId']==rid and p['attribution']

def test_import_is_idempotent_and_soft_rollback_preserves_audit(sample):
 r,rows=inspect(sample);c=sink()
 assert apply_batch(c,r,rows,sqlite=True)['inserted']==100
 assert apply_batch(c,r,rows,sqlite=True)['status']=='ALREADY_IMPORTED'
 assert rollback_batch(c,r['batchId'],sqlite=True)['deleted']==0
 assert c.execute('SELECT COUNT(*) FROM historical_record').fetchone()[0]==100
 assert c.execute("SELECT COUNT(*) FROM historical_record h JOIN source_record s USING(record_key) JOIN etl_batch b USING(batch_id) WHERE b.status='COMMITTED'").fetchone()[0]==0
 assert apply_batch(c,r,rows,sqlite=True)['inserted']==0
 assert c.execute('SELECT status FROM etl_batch').fetchone()[0]=='COMMITTED'

def test_tampered_sample_is_rejected(sample):
 (sample/'sample.jsonl').write_bytes(b'{}\n')
 with pytest.raises(ValueError,match='INTEGRITY'):inspect(sample)

def test_source_language_selection_does_not_translate():
 assert localized([{'language_tag':'en_US','value':'original'},{'language_tag':'zh_CN','value':'原始中文'}])=='原始中文'
 assert localized(None) is None

def test_roll_back_cannot_target_other_batches():
 with pytest.raises(ValueError,match='OWN_PUBLIC_BATCH'):rollback_batch(sink(),'other',sqlite=True)

def test_phone_case_not_relabelled_as_phone(sample):
 r,rows=inspect(sample)
 assert all(json.loads(p)['category']=='手机壳' for _,_,p,_ in rows if json.loads(p)['originalProductType']=='CELLULAR_PHONE_CASE')

def test_transaction_failure_leaves_no_partial_records(sample):
 r,rows=inspect(sample);rows[-1]=(*rows[-1][:3],'invalid hash');c=sink()
 with pytest.raises(ValueError,match='CONTENT_HASH'):apply_batch(c,r,rows,sqlite=True)
 assert c.execute('SELECT COUNT(*) FROM source_record').fetchone()[0]==0
 assert c.execute('SELECT status FROM etl_batch').fetchone()[0]=='FAILED'
