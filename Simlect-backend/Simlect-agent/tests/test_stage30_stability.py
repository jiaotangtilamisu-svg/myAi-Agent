from types import SimpleNamespace
from unittest.mock import Mock
import httpx
import pytest
from app.rag import embedding
from app.services import llm_factory
from app.config.settings import Settings

@pytest.mark.asyncio
@pytest.mark.parametrize('case',['ok','503','connect_timeout','read_timeout','json','empty','dimension','nan'])
async def test_embedding_faults_are_single_attempt_and_redacted(monkeypatch,case):
 calls=[]
 def handler(request):
  calls.append(request)
  if case=='503':return httpx.Response(503,text='PRIVATE KEY token=secret')
  if case in {'connect_timeout','read_timeout'}:raise (httpx.ConnectTimeout if case=='connect_timeout' else httpx.ReadTimeout)('PRIVATE KEY',request=request)
  if case=='json':return httpx.Response(200,text='PRIVATE malformed')
  if case=='empty':return httpx.Response(200,json={'data':[]})
  v=[1.,0.] if case=='ok' else [1.] if case=='dimension' else ['NaN',0.]
  return httpx.Response(200,json={'data':[{'embedding':v}]})
 cls=httpx.AsyncClient
 class Client(cls):
  def __init__(self,**kw):super().__init__(transport=httpx.MockTransport(handler),trust_env=False,**kw)
 monkeypatch.setattr(embedding.httpx,'AsyncClient',Client)
 monkeypatch.setattr(embedding,'get_settings',lambda:SimpleNamespace(embedding_base_url='https://embedding.invalid',embedding_api_key='TEST',embedding_model='test',embedding_dimensions=2))
 breaker=SimpleNamespace(allow_request=lambda:True,record_success=Mock(),record_failure=Mock())
 monkeypatch.setattr(embedding.circuit_registry,'get_or_create',lambda *a,**kw:breaker)
 log=Mock();monkeypatch.setattr(embedding,'logger',log)
 result=await embedding.embed_text('TEST ONLY')
 assert len(calls)==1 and (result==[1.,0.] if case=='ok' else result is None)
 assert 'PRIVATE' not in str(log.mock_calls) and 'secret' not in str(log.mock_calls)

def test_all_model_factories_disable_hidden_retries(monkeypatch):
 monkeypatch.setattr(llm_factory,'get_settings',lambda:Settings(_env_file=None,llm_api_key='test',llm_base_url='https://model.invalid'))
 for factory in (llm_factory.create_chat_llm,llm_factory.create_memory_llm):
  model=factory();assert model.root_async_client.max_retries==0
