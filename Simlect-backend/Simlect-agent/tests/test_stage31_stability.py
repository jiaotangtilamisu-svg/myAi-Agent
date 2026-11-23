import httpx
import pytest
from app.rag import advice
from test_policy_model_resilience import config,mock_transport,EVIDENCE

@pytest.mark.asyncio
@pytest.mark.parametrize('code,expected',[(429,'MODEL_RATE_LIMITED'),(500,'MODEL_UPSTREAM_UNAVAILABLE')])
async def test_rate_limit_and_server_fault_are_not_configuration_errors(monkeypatch,config,code,expected):
 calls=[]
 def handler(request):calls.append(request);return httpx.Response(code,json={'error':{'message':'fixture only'}})
 mock_transport(monkeypatch,handler)
 value=await advice.policy_advice('TEST ONLY',EVIDENCE)
 assert value['status']=='UNAVAILABLE' and value['failureCode']==expected and value['executionAllowed'] is False
 assert len(calls)==1 and EVIDENCE['hits'][0]['chunkId']=='known'
