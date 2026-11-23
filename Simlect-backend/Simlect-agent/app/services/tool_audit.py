"""Request-scoped, non-secret tool observability and business result checks."""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import re

message_id=ContextVar('agent_tool_message_id',default=None)
transport_path=ContextVar('agent_tool_transport_path',default='GUARD')
transport_status=ContextVar('agent_tool_transport_status',default='NOT_CALLED')
@contextmanager
def audit_message(value):
    token=message_id.set(value if type(value) is int and value>0 else None)
    try:yield
    finally:message_id.reset(token)

def business_status(result):
    if result.product_query:
        return {'SUCCESS':'SUCCESS','NOT_FOUND':'EMPTY'}.get(result.product_query.get('queryStatus'),'ERROR')
    if result.business_facts:
        return {'SUCCESS':'SUCCESS','NO_RECORD':'EMPTY'}.get(result.business_facts.get('queryStatus'),'ERROR')
    if re.search(r'【[^】\n]{0,40}(?:失败|超时)[^】\n]*】|^\s*(?:ERROR|FAILED)\b',result.content or '',re.I):return 'ERROR'
    if result.assistant_cards:
        try:
            rows=json.loads(result.assistant_cards)
            if isinstance(rows,list):return 'SUCCESS' if rows else 'EMPTY'
        except (ValueError,TypeError):return 'ERROR'
    return 'UNKNOWN'
