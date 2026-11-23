import json
from unittest.mock import Mock
import httpx
import pytest
from app.rag import advice
from test_policy_model_resilience import config,mock_transport,EVIDENCE

@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['empty_choices','empty_content','json_array','connect_timeout','read_timeout','503'])
async def test_policy_failures_keep_input_evidence_and_report_failure(monkeypatch,config,failure):
 before=json.dumps(EVIDENCE,sort_keys=True);calls=[]
 def handler(request):
  calls.append(request)
  if failure=='connect_timeout':raise httpx.ConnectTimeout('PRIVATE',request=request)
  if failure=='read_timeout':raise httpx.ReadTimeout('PRIVATE',request=request)
  if failure=='503':return httpx.Response(503,json={'error':{'message':'PRIVATE'}})
  choices=[] if failure=='empty_choices' else [{'index':0,'message':{'role':'assistant','content':'' if failure=='empty_content' else '[]'},'finish_reason':'stop'}]
  return httpx.Response(200,json={'id':'fixture','object':'chat.completion','created':1,'model':'mock','choices':choices})
 mock_transport(monkeypatch,handler);log=Mock();monkeypatch.setattr(advice,'logger',log)
 r=await advice.policy_advice('TEST ONLY',EVIDENCE)
 expected='MODEL_UPSTREAM_UNAVAILABLE' if failure=='503' else 'MODEL_TIMEOUT' if 'timeout' in failure else 'MODEL_INVALID_RESPONSE'
 assert r['failureCode']==expected and r['status']=='UNAVAILABLE' and not r['executionAllowed']
 assert len(calls)==1 and json.dumps(EVIDENCE,sort_keys=True)==before
 assert 'PRIVATE' not in str(log.mock_calls)
