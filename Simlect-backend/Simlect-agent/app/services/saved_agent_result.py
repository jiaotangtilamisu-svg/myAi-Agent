"""Recover owner-scoped completed evidence, independently of ephemeral Redis."""
import json
from app.auth.agent_context import require_agent_user
from app.constants import MSG_STATUS_COMPLETE
from app.services.message_service import agent_message_service

async def load_saved_result(user_id, message_id, agent):
    require_agent_user(user_id)
    if type(message_id) is not int or message_id<1:raise ValueError('Invalid message reference')
    row=await agent_message_service.get_message(user_id,message_id)
    if not row or row.get('status')!=MSG_STATUS_COMPLETE:return None
    data=json.loads(row.get('bizData') or row.get('biz_data') or '{}')
    if data.get('agentType')!=agent or data.get('messageId')!=message_id:return None
    report=data.get('fullReport')
    if not isinstance(report,dict):return None
    if agent=='supervisor':
        if report.get('messageId')!=message_id:raise ValueError('Mismatched report')
        from app.supervisor.contracts import checked_result
        for name,result in report.get('results',{}).items():checked_result(result,name)
    elif report.get('agentType')!='shopping' or report.get('executionAllowed') is not False:
        raise ValueError('Invalid shopping evidence')
    return report
