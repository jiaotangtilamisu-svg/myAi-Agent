"""Opt-in cleanup of disposable browser-generated rows in the recorded test DBs.

Keeps synthetic accounts/catalogue/orders and copied law vectors for reuse.
Never drops a schema/container/volume, resets an identity, or flushes Redis.
"""
import argparse
import json
import re
from .browser_database import RUN, PLAN, snapshot
from .isolation import mysql, docker, quote

def cleanup(execute=False):
    original=json.loads((RUN/'browser-database-before.json').read_text())
    if original['cases'] or original['messages']:
        raise RuntimeError('INITIAL_BROWSER_BASELINE_NOT_EMPTY_REFUSE_CLEANUP')
    current=snapshot('before-cleanup')
    owners={PLAN['userA'],PLAN['userB']}
    if any(row['userId'] not in owners for row in current['cases']+current['messages']):
        raise RuntimeError('UNRECOGNIZED_OWNER_REFUSE_CLEANUP')
    orderdb=PLAN['databases']['order'];agentdb=PLAN['databases']['agent']
    assert all(re.fullmatch('q34_[a-f0-9]{10}_[a-z_]+',v) for v in [orderdb,agentdb])
    record={'mode':'EXECUTED' if execute else 'DRY_RUN','schemas':[orderdb,agentdb],
            'caseIds':[row['caseId'] for row in current['cases']],
            'messageIds':[row['messageId'] for row in current['messages']],
            'retained':'synthetic accounts, six products, ten SKUs, nine stocks, six orders, 61 policy vector copies',
            'formalWrites':0,'flushOperations':0,'schemaDrops':0}
    for value in record['caseIds']:
        if not re.fullmatch('[a-f0-9-]{36}',value):raise ValueError('INVALID_CASE_ID')
    for value in record['messageIds']:
        if type(value) is not int or value<1:raise ValueError('INVALID_MESSAGE_ID')
    if execute:
        statements=['START TRANSACTION;']
        if record['caseIds']:
            ids=','.join(quote(v) for v in record['caseIds'])
            for table in ['aftersales_audit','aftersales_manual_task','aftersales_plan','aftersales_case']:
                statements.append(f'DELETE FROM `{orderdb}`.`{table}` WHERE case_id IN ({ids});')
        if record['messageIds']:
            ids=','.join(str(v) for v in record['messageIds'])
            statements.append(f'DELETE FROM `{agentdb}`.agent_message WHERE message_id IN ({ids}) AND user_id IN ({quote(PLAN["userA"])},{quote(PLAN["userB"])});')
        statements.append(f'DELETE FROM `{agentdb}`.agent_session_memory WHERE user_id IN ({quote(PLAN["userA"])},{quote(PLAN["userB"])});')
        statements.append('COMMIT;');mysql('\n'.join(statements))
        # Delete only named agent/test checkpoint namespaces from the separate
        # recorded Redis. Never read values, login credentials, or user Tokens.
        info=json.loads(docker(['inspect',PLAN['redisContainer']]))[0]
        assert any(p.get('HostPort')==str(PLAN['redisPort']) for p in info['NetworkSettings']['Ports']['6379/tcp'])
        keys=set()
        for user in owners:
            for prefix in ['mall:agent:*','mall:cancel:agent:*']:
                keys.update(docker(['exec',PLAN['redisContainer'],'redis-cli','--scan','--pattern',prefix+user+'*']).splitlines())
        keys.update(docker(['exec',PLAN['redisContainer'],'redis-cli','--scan','--pattern',PLAN['indexPrefix']+'checkpoint*']).splitlines())
        for key in keys:
            assert key.startswith(('mall:agent:','mall:cancel:agent:',PLAN['indexPrefix']+'checkpoint'))
            docker(['exec',PLAN['redisContainer'],'redis-cli','DEL',key])
        record['testCacheKeysDeleted']=len(keys)
        final=snapshot('after-cleanup')
        assert not final['cases'] and not final['messages']
        for table in ['order.order_info','order.order_item','product.product_info','product.product_sku','stock.sku_stock']:
            assert final['tables'][table]==current['tables'][table]
        record['verified']=True
    (RUN/'browser-cleanup.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in record.items() if k not in {'caseIds','messageIds'}},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    cleanup(args.execute)
