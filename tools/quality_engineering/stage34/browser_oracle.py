"""Independent SQL assertions, separate from the Agent/Java workflow code."""
import json
from .browser_database import RUN, PLAN, snapshot

def main():
    data=snapshot('oracle')
    rows=[]
    def check(name,condition):
        rows.append({'rule':name,'passed':bool(condition)})
    messages={m['messageId']:m for m in data['messages']}
    fixture=json.loads((RUN/'fixture-manifest.json').read_text())
    owners={r['orderId']:r['userId'] for r in fixture['orders']}
    for case in data['cases']:
        cid=case['caseId'];message=messages.get(case['sourceMessageId'])
        check(cid+':owner-and-source-message', bool(message) and message['userId']==case['userId']==owners.get(case['orderId']))
        report=json.loads(message['bizData']) if message else {}
        diagnosis=report.get('aftersalesDiagnosis') or (((report.get('fullReport') or {}).get('results') or {}).get('aftersales') or {}).get('data',{}).get('diagnosis',{})
        check(cid+':trusted-order-identity', diagnosis.get('orderId')==case['orderId'] and diagnosis.get('orderFacts',{}).get('data',{}).get('ownerVerified') is True)
        check(cid+':no-agent-financial-execution', diagnosis.get('executionAllowed') is False)
        events=[e for e in data['audit'] if e['caseId']==cid]
        check(cid+':continuous-audit-versions',[e['version'] for e in events]==list(range(1,case['version']+1)))
        plans=[p for p in data['plans'] if p['caseId']==cid]
        check(cid+':immutable-plan-versions',[p['version'] for p in plans]==list(range(1,case['planVersion']+1)))
        check(cid+':confirmation-role',all(e['actorType']=='USER' for e in events if e['action']=='CONFIRM'))
        check(cid+':administrator-role',all(e['actorType']=='ADMIN' for e in events if e['action'] in {'APPROVE','REJECT','CLAIM','RETURN_ACCEPT','START_MOCK_REFUND','COMPLETE_MOCK_REFUND'}))
        refunds=[e for e in events if e['action'] in {'PREPARE_REFUND','START_MOCK_REFUND','COMPLETE_MOCK_REFUND','TIMEOUT_MOCK_REFUND'}]
        by_plan={}
        for event in refunds:
            value=json.loads(event['note']);by_plan.setdefault(event['planVersion'],[]).append(value['refundId'])
            check(cid+':mock-only:'+str(event['version']),value.get('mode')=='MOCK' and value.get('executionAllowed') is False and value.get('type') in {'refund','return_refund'})
        check(cid+':stable-refund-id',all(len(set(values))==1 for values in by_plan.values()))
        for event in events:
            if event['action']=='COMPLETE_MOCK_REFUND':
                previous=[e for e in events if e['version']<event['version'] and e['action'] in {'START_MOCK_REFUND','TIMEOUT_MOCK_REFUND'}]
                if previous and previous[-1]['action']=='TIMEOUT_MOCK_REFUND':
                    check(cid+':unknown-requires-reconciliation',json.loads(event['note']).get('manualReconciliation') is True)
    baseline=json.loads((RUN/'browser-database-before.json').read_text())
    for table in ['order.order_info','order.order_item','product.product_info','product.product_sku','stock.sku_stock']:
        check(table+':unchanged-by-returns',data['tables'][table]==baseline['tables'][table])
    check('at-least-one-browser-return-archived',any(c['state']=='ARCHIVED' for c in data['cases']))
    check('all-message-json-complete',all(isinstance(json.loads(m['bizData']),dict) for m in data['messages'] if m['bizData']))
    result={'scope':'Read-only isolated MySQL verification, not a substitute for Playwright clicks','assertions':len(rows),'passed':sum(r['passed'] for r in rows),'failed':sum(not r['passed'] for r in rows),'rules':rows}
    (RUN/'browser-sql-oracle.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='rules'},ensure_ascii=False))
    return result['failed']==0

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
