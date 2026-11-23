"""Opt-in Stage34 fixture provisioning. No production business rows are copied.

Schemas are fresh, randomized and accessed by a user granted only those schemas.
Public approved policy metadata is the sole data copied from an existing schema.
"""
import argparse
import hashlib
import json
import re
import secrets
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))

BASE = ROOT/'.cache/stage34'
SOURCES = ['user','product','stock','order','agent','search','admin','cart','data_governance']


def mysql(query):
    result = subprocess.run(['docker','exec','-i','simlect-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --batch --raw --skip-column-names --default-character-set=utf8mb4'],input=query,text=True,encoding='utf8',capture_output=True)
    if result.returncode:
        # Server messages may echo fixture credentials; reveal only error class
        # and SQL line number, never the failed statement or quoted values.
        errors=[re.sub(r"'[^']*'", "'[REDACTED]'", line) for line in result.stderr.splitlines() if line.startswith('ERROR ')]
        raise RuntimeError('ISOLATED_MYSQL_ERROR: '+'; '.join(errors))
    return result.stdout.splitlines()


def quote(value):
    if value is None:
        return 'NULL'
    if isinstance(value,(int,float)):
        return str(value)
    return "(CONVERT(0x"+str(value).encode('utf8').hex()+" USING utf8mb4) COLLATE utf8mb4_general_ci)"


def insert(db,table,row):
    assert re.fullmatch(r'q34_[a-f0-9]{10}_[a-z_]+',db)
    assert re.fullmatch(r'[a-z_]+',table)
    return 'INSERT INTO `'+db+'`.`'+table+'` ('+','.join('`'+c+'`' for c in row)+') VALUES ('+','.join(quote(v) for v in row.values())+');'


def docker(args):
    r=subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf8')
    if r.returncode:
        raise RuntimeError('ISOLATION_DOCKER_FAILED:'+args[0])
    return r.stdout.strip()


def prepare(resume=False):
    if (BASE/'active.json').exists() and not resume:
        raise RuntimeError('ACTIVE_STAGE34_PLAN_EXISTS_NO_DUPLICATE_PROVISIONING')
    existing = json.loads((BASE/'active.json').read_text()) if resume else None
    runid=Path(existing['directory']).name if existing else uuid.uuid4().hex[:10]
    assert re.fullmatch('[a-f0-9]{10}',runid)
    run=BASE/runid
    if not resume:
        run.mkdir(parents=True,exist_ok=False)
    if (run/'provisioned.json').exists():
        raise RuntimeError('ALREADY_PROVISIONED')
    dbs={s:'q34_'+runid+'_'+s for s in SOURCES}
    private={'dbUser':'q34_'+runid,'dbPassword':secrets.token_urlsafe(24),'internalToken':secrets.token_urlsafe(36),'mqUser':'q34_'+runid,'mqPassword':secrets.token_urlsafe(24),'adminAccount':'quality34-admin','adminPassword':secrets.token_urlsafe(18),'userPassword':secrets.token_urlsafe(18)}
    plan={'runId':runid,'directory':str(run),'databases':dbs,'indexPrefix':'q34_'+runid+'_','productIndex':'q34_'+runid+'_products','vectorIndex':'q34_'+runid+'_vectors','rabbitVhost':'q34_'+runid,'redisContainer':'q34-'+runid+'-redis','redisPort':26379,'nacosGroup':'QUALITY34_'+runid,'nacosNamespace':'','userA':'QA34A00001','userB':'QA34B00001','emailA':'qa34-a@example.invalid','emailB':'qa34-b@example.invalid','ports':{'gateway':18080,'user':18105,'product':18099,'stock':18102,'order':18093,'search':18108,'admin':18111,'cart':18084,'mcp':17060,'agent':17050,'web':16001,'admin-ui':16002,'guard':19200},'realApiCaps':{'llm':4,'embedding':6,'outputTokens':512,'timeoutSeconds':20,'automaticRetries':0}}
    if resume:
        private=json.loads((run/'private.json').read_text())
    (run/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2),encoding='utf8')
    (run/'private.json').write_text(json.dumps(private,ensure_ascii=False),encoding='utf8')
    (BASE/'active.json').write_text(json.dumps({'directory':str(run)}),encoding='utf8')
    # Schema-only backup: no users, credentials, orders or other private rows.
    backup=subprocess.run(['docker','exec','simlect-mysql','sh','-c','MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --no-data --skip-comments --set-gtid-purged=OFF --databases '+' '.join('simlect_'+s for s in SOURCES)],capture_output=True) if not resume else subprocess.CompletedProcess([],0,stdout=(run/'production-schema-backup.sql').read_bytes())
    if backup.returncode:
        raise RuntimeError('SCHEMA_BACKUP_FAILED')
    (run/'production-schema-backup.sql').write_bytes(backup.stdout)
    operations=[]
    for source in SOURCES:
        dest=dbs[source]
        operations.append('CREATE DATABASE IF NOT EXISTS `'+dest+'` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;')
        tables=mysql("SELECT table_name FROM information_schema.tables WHERE table_schema='simlect_"+source+"' AND table_type='BASE TABLE';")
        for table in tables:
            assert re.fullmatch(r'[a-z_]+',table)
            operations.append('CREATE TABLE IF NOT EXISTS `'+dest+'`.`'+table+'` LIKE `simlect_'+source+'`.`'+table+'`;')
    # Credentials are generated in memory and never printed or passed in CLI args.
    operations.append("CREATE USER IF NOT EXISTS '"+private['dbUser']+"'@'%' IDENTIFIED BY '"+private['dbPassword']+"';")
    for db in dbs.values():
        operations.append("GRANT ALL PRIVILEGES ON `"+db+"`.* TO '"+private['dbUser']+"'@'%';")
    mysql('\n'.join(operations))
    grants=mysql("SHOW GRANTS FOR '"+private['dbUser']+"'@'%';")
    assert all('ON *.*' not in row or 'GRANT USAGE' in row for row in grants)
    assert all('simlect_' not in row for row in grants)
    (run/'database-grants.json').write_text(json.dumps({'grants':[row.split(' TO ')[0] for row in grants]}),encoding='utf8')
    seed=[]
    if resume:
        # First attempt inserted only synthetic A before B's duplicate nickname.
        # Refuse resuming if anything beyond that known bootstrap exists.
        assert mysql('SELECT COUNT(*) FROM `'+dbs['order']+'`.order_info;')==['0']
        assert mysql('SELECT COUNT(*) FROM `'+dbs['product']+'`.product_info;')==['0']
        seed.append('DELETE FROM `'+dbs['user']+'`.user_info WHERE user_id IN ('+quote(plan['userA'])+','+quote(plan['userB'])+');')
    for uid,email in [(plan['userA'],plan['emailA']),(plan['userB'],plan['emailB'])]:
        # Exercise the real legacy-password upgrade path on these synthetic users.
        seed.append(insert(dbs['user'],'user_info',{'user_id':uid,'nick_name':'隔离测试'+uid[4],'email':email,'password':hashlib.md5(private['userPassword'].encode()).hexdigest(),'join_time':'2026-11-06 00:00:00','status':1}))
    for cid,name,parent in [('Q340','隔离测试商品','0'),('Q341','手机','Q340'),('Q342','耳机','Q340'),('Q343','茶杯','Q340')]:
        seed.append(insert(dbs['product'],'sys_category',{'category_id':cid,'category_name':name,'p_category_id':parent,'sort':1}))
    fixtures=[('DEMO34S1','三星 Galaxy 隔离测试手机A','三星','Q341',6000,2),('DEMO34S2','Samsung Galaxy 隔离测试手机B','三星','Q341',4500,2),('DEMO34A1','Apple 苹果 iPhone 隔离测试手机C','苹果','Q341',7000,2),('DEMO34A2','Apple 苹果 iPhone 隔离测试手机D','苹果','Q341',4000,2),('DEMO34H1','隔离测试蓝牙耳机','QA34','Q342',199,1),('DEMO34C1','隔离测试陶瓷茶杯','QA34','Q343',19,1)]
    skus={}
    for pid,name,brand,cat,price,count in fixtures:
        seed.append(insert(dbs['product'],'product_info',{'product_id':pid,'product_name':name,'product_desc':'第34阶段完全合成测试资料；价格、SKU与库存均不代表真实商业数据。','cover':'/favicon.svg','create_time':'2026-11-06 00:00:00','category_id':cat,'p_category_id':'Q340','status':1,'min_price':price,'max_price':price+500 if count==2 else price,'total_sale':0,'commend_type':1}))
        props=[('BR','品牌',brand),('COL','颜色','黑色')]+([('256','存储容量','256GB'),('512','存储容量','512GB')] if count==2 else [('STD','规格','隔离测试标准款')])
        for n,(suffix,key,val) in enumerate(props):
            seed.append(insert(dbs['product'],'product_property_value',{'product_id':pid,'property_id':str(n+1),'property_name':key,'property_sort':n,'cover_type':0,'property_value_id':pid+suffix,'property_value':val,'sort':n}))
        for i in range(count):
            specs=pid+('256' if i==0 else '512') if count==2 else pid+'STD'
            sku=hashlib.md5((pid+':'+str(i)).encode()).hexdigest()
            skus[(pid,i)]=sku
            seed.append(insert(dbs['product'],'product_sku',{'product_id':pid,'property_value_id_hash':sku,'property_value_ids':pid+'COL-'+specs,'price':price+i*500,'sort':i}))
            if (pid,i)!=('DEMO34A2',1):
                seed.append(insert(dbs['stock'],'sku_stock',{'product_id':pid,'property_value_id_hash':sku,'stock':0 if pid=='DEMO34C1' else 10+i}))
    orders=[]
    for i,status in enumerate([3,2,1,5,6,3]):
        uid=plan['userB'] if i==5 else plan['userA']
        oid='20261106090000000QA34'+('B' if i==5 else 'A')+str(i).zfill(10)
        assert len(oid)==32
        pid='DEMO34S1'
        seed.append(insert(dbs['order'],'order_info',{'order_id':oid,'user_id':uid,'amount':6000,'goods_amount':6000,'order_time':'2026-11-04 12:00:00','order_status':status,'pay_scene':'QUALITY34_SYNTHETIC','pay_channel':'MOCK','subject':'隔离测试订单；无真实支付'}))
        seed.append(insert(dbs['order'],'order_item',{'order_item_id':'QA34ITEM'+str(i),'order_id':oid,'product_id':pid,'product_name':'三星 Galaxy 隔离测试手机A','property_value_id_hash':skus[(pid,0)],'property_info':'颜色:黑色/存储容量:256GB','item_amount':6000,'buy_count':1,'order_item_status':0,'remark':'QUALITY34_SYNTHETIC_NO_FUNDS','cover':'/favicon.svg'}))
        seed.append(insert(dbs['order'],'order_logistics_info',{'order_id':oid,'user_id':uid,'logistics_no':'QA34LOGISTICS'+str(i),'logistics_company':'隔离测试物流（非承运商）','sender_name':'QA34测试仓','sender_address':'隔离测试地址，无实体配送','receiver_name':'QA34测试用户','receiver_address':'隔离测试地址，无个人信息','logistics_status':2 if status==3 else 0}))
        seed.append(insert(dbs['order'],'order_logistics_info_record',{'order_id':oid,'record_time':'2026-11-05 12:00:00','record_address':'QUALITY34：合成物流轨迹，不是真实承运商数据'}))
        orders.append({'orderId':oid,'userId':uid,'status':status,'productId':pid,'skuId':skus[(pid,0)]})
    mysql('START TRANSACTION;\n'+'\n'.join(seed)+'\nCOMMIT;')
    doc='f85d1c36-053a-430b-a05f-e9ce88810e99'
    # Public law copy, not personal cases or private administrator audit records.
    for table in ['knowledge_document','knowledge_document_revision','knowledge_document_source']:
        cols=mysql("SELECT column_name FROM information_schema.columns WHERE table_schema='simlect_search' AND table_name='"+table+"' ORDER BY ordinal_position;")
        projections=[quote('QUALITY34_REVIEWER') if c=='reviewed_by' else '`'+c+'`' for c in cols]
        mysql('INSERT INTO `'+dbs['search']+'`.`'+table+'` SELECT '+','.join(projections)+" FROM simlect_search.`"+table+"` WHERE document_id='"+doc+"';")
    (run/'fixture-manifest.json').write_text(json.dumps({'synthetic':True,'users':2,'products':len(fixtures),'skus':len(skus),'stockRows':len(skus)-1,'orders':orders,'officialPolicyReadOnlyCopy':doc,'schemaBackupSHA256':hashlib.sha256(backup.stdout).hexdigest()},ensure_ascii=False,indent=2),encoding='utf8')
    docker(['exec','simlect-rabbitmq','rabbitmqctl','add_vhost',plan['rabbitVhost']])
    docker(['exec','simlect-rabbitmq','rabbitmqctl','add_user',private['mqUser'],private['mqPassword']])
    docker(['exec','simlect-rabbitmq','rabbitmqctl','set_permissions','-p',plan['rabbitVhost'],private['mqUser'],'.*','.*','.*'])
    image=json.loads(docker(['inspect','simlect-redis']))[0]['Config']['Image']
    docker(['run','-d','--name',plan['redisContainer'],'--restart=no','--memory=128m','-p','127.0.0.1:26379:6379',image,'redis-server','--save','','--appendonly','no'])
    (run/'provisioned.json').write_text(json.dumps({'databaseSchemas':dbs,'redisContainer':plan['redisContainer'],'rabbitVhost':plan['rabbitVhost'],'productionBusinessWrites':0,'policyPublishedByTest':False},indent=2),encoding='utf8')
    print(json.dumps({'directory':str(run),'schemaCount':len(dbs),'syntheticUsers':2,'syntheticProducts':6,'syntheticOrders':6}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['prepare'])
    parser.add_argument('--resume',action='store_true')
    args=parser.parse_args()
    if args.operation=='prepare':
        prepare(args.resume)
