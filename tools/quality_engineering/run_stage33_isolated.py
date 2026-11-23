"""Bounded opt-in real MySQL + ES + Java HTTP integration. No paid APIs."""
from pathlib import Path
import json,os,re,subprocess,sys,uuid,urllib.request,urllib.error,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.data_governance.policy_migration import mysql
OUT=ROOT/'.cache/stage33/isolated'
def es(path,body=None,method=None):
    req=urllib.request.Request('http://127.0.0.1:9200/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'},method=method)
    with urllib.request.urlopen(req,timeout=12) as r:return json.load(r)
def main():
    OUT.mkdir(parents=True,exist_ok=True);schema='simlect_quality33_'+uuid.uuid4().hex[:12];index=schema
    assert re.fullmatch(r'simlect_quality33_[a-f0-9]{12}',schema)
    secret=subprocess.run(['docker','exec','simlect-mysql','printenv','MYSQL_ROOT_PASSWORD'],capture_output=True,check=True).stdout.decode().strip()
    assert secret
    backup=OUT/'production-product-backup.sql'
    if not backup.exists():
        r=subprocess.run(['docker','exec','simlect-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF simlect_product product_info product_sku product_property_value'],capture_output=True,check=True);backup.write_bytes(r.stdout)
    report={'scope':'ACTUAL_LOOPBACK_JAVA_SPRING_MVC_MYBATIS_MYSQL_AND_ES_DSL; NOT_BROWSER_OR_REAL_LLM','backupSHA256':hashlib.sha256(backup.read_bytes()).hexdigest(),'realLlmCalls':0,'realEmbeddingCalls':0,'checks':[]}
    created_db=created_index=False
    try:
        mysql('CREATE DATABASE `'+schema+'` CHARACTER SET utf8mb4;');created_db=True
        for table in ['product_info','product_sku','product_property_value']:mysql(f'CREATE TABLE `{schema}`.`{table}` LIKE simlect_product.`{table}`;')
        # Six explicit synthetic fixtures; no imported bulk dataset or formal IDs.
        fixtures=[('QA','Apple/苹果 iPhone 手机',6500,'256GB',1),('QS','Samsung/三星 Galaxy 手机',6000,'256GB',1),('QH','Huawei/华为 手机',4500,'128GB',1),('QO','OPPO 手机',2500,'256GB',1),('QC','通用手机壳适用苹果三星',20,'不适用',1),('QOFF','Apple/苹果 iPhone 手机',5000,'256GB',0)]
        for pid,name,price,capacity,status in fixtures:
            mysql(f"INSERT INTO `{schema}`.product_info(product_id,product_name,product_desc,status,min_price,max_price,total_sale,category_id,create_time) VALUES('{pid}','{name}','ISOLATED SYNTHETIC TEST',{status},{price},{price},0,'QCAT',NOW());")
            mysql(f"INSERT INTO `{schema}`.product_property_value(product_id,property_id,property_name,property_value_id,property_value) VALUES('{pid}','QPROP','存储容量','{pid}V','{capacity}');")
        env=os.environ.copy();env.update(QUALITY_MYSQL_SCHEMA=schema,QUALITY_MYSQL_PASSWORD=secret,QUALITY_HTTP_EVIDENCE=str(OUT/'java-http.json'),QUALITY_ES_EXPORT=str(OUT/'java-es-dsl.json'),JAVA_HOME='E:\\JDK17',TEMP='E:\\SimlectRuntime\\tmp',TMP='E:\\SimlectRuntime\\tmp')
        env['PATH']='E:\\JDK17\\bin;'+env['PATH']
        with (OUT/'maven.log').open('wb') as log:
            r=subprocess.run(['E:\\develop\\apache-maven-3.9.4-bin\\apache-maven-3.9.4\\bin\\mvn.cmd','-o','-f','Simlect-backend/pom.xml','-pl','Simlect-product/app,Simlect-search','-am','test','-Dtest=ProductCatalogMySqlHttpIT,ProductLexicalQueryTest','-Dsurefire.failIfNoSpecifiedTests=false','-DargLine=-Xmx256m'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        report['javaExitCode']=r.returncode
        if r.returncode:raise RuntimeError('JAVA_ISOLATED_HTTP_TEST_FAILED')
        report['httpQueries']=json.loads((OUT/'java-http.json').read_text(encoding='utf8'))
        report['checks'].extend({'kind':'JAVA_HTTP_MYSQL','query':v['query'],'status':'PASS','ids':v['ids']} for v in report['httpQueries'])
        mapping=json.loads((ROOT/'.cache/stage33/es-mapping.json').read_text(encoding='utf8'))['simlect-index']['mappings']
        mapping['properties'].update({k:{'type':'text','analyzer':'ik_max_word','search_analyzer':'ik_smart'} for k in ['searchText','brand','categoryName']})
        es(index,{'mappings':mapping,'settings':{'number_of_shards':1,'number_of_replicas':0}},'PUT');created_index=True
        for pid,name,price,capacity,status in fixtures:
            if status!=1:continue
            # Read the facts back from isolated SQL; do not substitute a Mock search result.
            row=mysql(f"SELECT JSON_OBJECT('productId',p.product_id,'productName',p.product_name,'minPrice',p.min_price,'maxPrice',p.max_price,'searchText',(SELECT GROUP_CONCAT(property_value SEPARATOR ' ') FROM `{schema}`.product_property_value v WHERE v.product_id=p.product_id)) FROM `{schema}`.product_info p WHERE product_id='{pid}';")
            doc=json.loads(row[0]);es(index+'/_doc/'+pid,doc,'PUT')
        es(index+'/_refresh',method='POST')
        queries=json.loads((OUT/'java-es-dsl.json').read_text(encoding='utf8'))
        expected={'苹果手机':{'QA'},'Apple手机':{'QA'},'iPhone':{'QA'},'苹果256G':{'QA'},'三星手机':{'QS'},'Samsung手机':{'QS'},'Galaxy手机':{'QS'},'华为手机':{'QH'},'OPPO手机':{'QO'},'不存在型号':set(),'手机壳':{'QC'}}
        for q,dsl in queries.items():
            data=es(index+'/_search',{'query':dsl,'size':20});ids=[v['_source']['productId'] for v in data['hits']['hits']]
            if q in expected:assert set(ids)==expected[q],(q,ids)
            if q=='苹果':assert 'QA' in ids
            report['checks'].append({'kind':'REAL_ES','query':q,'status':'PASS','ids':ids})
        report['passed']=len(report['checks']);report['failed']=0
    except Exception as exc:
        report['passed']=len(report['checks']);report['failed']=1;report['failureType']=type(exc).__name__
        raise
    finally:
        if created_index:es(index,method='DELETE')
        if created_db:mysql('DROP DATABASE `'+schema+'`;')
        report['databaseRemoved']=not mysql("SELECT schema_name FROM information_schema.schemata WHERE schema_name='"+schema+"';")
        try:es(index);report['indexRemoved']=False
        except urllib.error.HTTPError as e:report['indexRemoved']=e.code==404
        (OUT/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');secret='';env.pop('QUALITY_MYSQL_PASSWORD',None) if 'env' in locals() else None
    print(json.dumps({'passed':report['passed'],'failed':report['failed'],'databaseRemoved':report['databaseRemoved'],'indexRemoved':report['indexRemoved']}))
if __name__=='__main__':main()
