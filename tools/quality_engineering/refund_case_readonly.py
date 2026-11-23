"""Read-only evidence for the user-reported case; no business transitions."""
import json
from pathlib import Path
from tools.data_governance.policy_migration import mysql

CASE = 'cb1282f3-2275-42ba-8528-badba3e42d4b'

def main():
    rows=mysql("SELECT JSON_OBJECT('caseId',case_id,'orderId',order_id,'state',state,'version',version,'planVersion',plan_version) FROM simlect_order.aftersales_case WHERE case_id='"+CASE+"';")
    events=mysql("SELECT JSON_OBJECT('action',action,'version',case_version,'createdAt',created_at,'status',JSON_UNQUOTE(JSON_EXTRACT(IF(JSON_VALID(note),note,'{}'),'$.status')),'accepted',JSON_EXTRACT(IF(JSON_VALID(note),note,'{}'),'$.accepted')) FROM simlect_order.aftersales_audit WHERE case_id='"+CASE+"' ORDER BY case_version;")
    pending=mysql('SELECT COUNT(*) FROM simlect_agent.agent_message WHERE status=1;')
    result={'mode':'READ_ONLY_NO_TRANSITIONS','pendingAgentMessages':int(pending[0]),'case':[json.loads(x) for x in rows],'events':[json.loads(x) for x in events]}
    dest=Path('.cache/refund-status-repair/current-case-before.json')
    if dest.exists():dest=dest.with_name('current-case-latest.json')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
