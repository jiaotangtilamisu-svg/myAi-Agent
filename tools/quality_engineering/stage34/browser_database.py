"""Read-only verification of browser effects; never creates business state."""
import hashlib
import json
import re
import sys
from pathlib import Path
from tools.quality_engineering.stage34.isolation import mysql

ROOT = Path(__file__).resolve().parents[3]
RUN = Path(json.loads((ROOT/'.cache/stage34/active.json').read_text())['directory'])
PLAN = json.loads((RUN/'plan.json').read_text())

def snapshot(label):
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', label):
        raise ValueError('INVALID_LABEL')
    tables = {'order': ['order_info','order_item','aftersales_case','aftersales_plan','aftersales_manual_task','aftersales_audit'],
              'agent':['agent_message'], 'product':['product_info','product_sku'], 'stock':['sku_stock']}
    result = {'runId': PLAN['runId'], 'tables': {}}
    for role, names in tables.items():
        db = PLAN['databases'][role]
        assert re.fullmatch('q34_[a-f0-9]{10}_[a-z_]+', db)
        for name in names:
            rows = mysql(f'SELECT * FROM `{db}`.`{name}`;')
            result['tables'][role+'.'+name] = {'rows':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
    db=PLAN['databases']['order']
    result['cases']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('caseId',case_id,'userId',user_id,'orderId',order_id,'sourceMessageId',source_message_id,'state',state,'version',version,'planVersion',plan_version) FROM `{db}`.aftersales_case ORDER BY created_at;")]
    result['audit']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('caseId',case_id,'version',case_version,'planVersion',plan_version,'actorType',actor_type,'action',action,'fromState',from_state,'toState',to_state,'note',note,'createdAt',created_at) FROM `{db}`.aftersales_audit ORDER BY created_at,case_version;")]
    result['plans']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('caseId',case_id,'version',version,'content',content_json) FROM `{db}`.aftersales_plan ORDER BY case_id,version;")]
    result['messages']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('messageId',message_id,'userId',user_id,'status',status,'userMessage',user_message,'aiMessage',assistant_message,'bizData',biz_data) FROM `{PLAN['databases']['agent']}`.agent_message ORDER BY message_id;")]
    result['skuTruth']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('productId',product_id,'skuId',property_value_id_hash,'price',price,'propertyValueIds',property_value_ids) FROM `{PLAN['databases']['product']}`.product_sku;")]
    result['stockTruth']=[json.loads(r) for r in mysql(f"SELECT JSON_OBJECT('productId',product_id,'skuId',property_value_id_hash,'stock',stock) FROM `{PLAN['databases']['stock']}`.sku_stock;")]
    output=RUN/f'browser-database-{label}.json'
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'snapshot':str(output),'cases':len(result['cases']),'audit':len(result['audit']),'messages':len(result['messages'])}))
    return result

if __name__=='__main__':
    snapshot(sys.argv[1])
