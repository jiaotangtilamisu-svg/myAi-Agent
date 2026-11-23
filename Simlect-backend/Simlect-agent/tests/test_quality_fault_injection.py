"""Faults are injected into production orchestration; no external service calls."""
from unittest.mock import AsyncMock,Mock
import pytest
import httpx
from app.auth.agent_context import agent_user_context
from app.services import agent_runtime as rt,message_service as messages
from app.shopping import extraction
from app.supervisor import graph

@pytest.mark.asyncio
@pytest.mark.parametrize('error',[httpx.ConnectError('fixture'),httpx.ReadTimeout('fixture'),RuntimeError('fixture')])
async def test_post_persistence_notification_failure_keeps_durable_result(monkeypatch,error):
 saved=AsyncMock(return_value=True);push=AsyncMock(side_effect=error)
 monkeypatch.setattr(rt.agent_message_service,'complete_message',saved);monkeypatch.setattr(rt.stream_service,'push_done',push)
 await rt._persist_and_notify({'userId':'fixture','messageId':17},'saved','agent','{}')
 saved.assert_awaited_once();push.assert_awaited_once()

@pytest.mark.asyncio
async def test_invalid_input_does_not_spend_model_call(monkeypatch):
 model=Mock(side_effect=AssertionError('MODEL_MUST_NOT_RUN'));monkeypatch.setattr(extraction,'create_chat_llm',model)
 r=await extraction.extract(None);assert r['clarification'];model.assert_not_called()

@pytest.mark.asyncio
async def test_persistence_error_never_becomes_success_event(monkeypatch):
 monkeypatch.setattr(rt.agent_message_service,'complete_message',AsyncMock(side_effect=messages.MessagePersistenceError()))
 done=AsyncMock();monkeypatch.setattr(rt.stream_service,'push_done',done)
 with pytest.raises(messages.MessagePersistenceError):await rt._persist_and_notify({'userId':'fixture','messageId':17},'saved','agent','{}')
 done.assert_not_awaited()

@pytest.mark.asyncio
@pytest.mark.parametrize('status',[200,503])
async def test_vector_recall_contract_or_failure_never_invents_ids(monkeypatch,status):
 from types import SimpleNamespace
 from contextlib import asynccontextmanager
 from app.rag import retriever as mod
 client=Mock();response=Mock();response.status_code=status
 if status==503:response.raise_for_status.side_effect=httpx.HTTPStatusError('fixture',request=httpx.Request('POST','https://invalid'),response=httpx.Response(503))
 else:response.raise_for_status.return_value=None
 response.json.return_value={'hits':{'hits':[{'_score':0.9,'_source':{'content':'fixture','metadata':{'productId':'P2'}}},{'_score':0.8,'_source':{'content':'fixture','metadata':{'productId':'P2'}}},{'_score':0.1,'_source':{'metadata':{'productId':'IRRELEVANT'}}}]}}
 client.post=AsyncMock(return_value=response)
 @asynccontextmanager
 async def factory(**kw):yield client
 monkeypatch.setattr(mod.httpx,'AsyncClient',factory)
 monkeypatch.setattr(mod,'embed_text',AsyncMock(return_value=[1.0,0.0]))
 monkeypatch.setattr(mod,'get_settings',lambda:SimpleNamespace(es_hosts=['http://127.0.0.1:19200'],es_index='fixture',rag_top_k=5,rag_score_threshold=0.4,elasticsearch_url='http://127.0.0.1:19200',es_base_url='http://127.0.0.1:19200'))
 monkeypatch.setattr(mod.RagRetriever,'_es_url',lambda self,path:'http://127.0.0.1:19200'+path)
 breaker=Mock();breaker.allow_request.return_value=True;monkeypatch.setattr(mod.circuit_registry,'get_or_create',lambda *a,**kw:breaker)
 ids=await mod.RagRetriever().search_product_vector_ids('fixture',5)
 assert ids==(['P2'] if status==200 else [])
 body=client.post.await_args.kwargs['json'];assert body['knn']['query_vector']==[1.0,0.0]
 assert body['knn']['filter']['bool']['must']==[{'term':{'metadata.dataType.keyword':'product'}}]
 if status==503:breaker.record_failure.assert_called_once()

@pytest.mark.asyncio
async def test_empty_embedding_never_makes_es_query(monkeypatch):
 from app.rag import retriever as mod
 monkeypatch.setattr(mod,'embed_text',AsyncMock(return_value=None));client=Mock(side_effect=AssertionError('ES_MUST_NOT_BE_QUERIED'));monkeypatch.setattr(mod.httpx,'AsyncClient',client)
 breaker=Mock();breaker.allow_request.return_value=True;monkeypatch.setattr(mod.circuit_registry,'get_or_create',lambda *a,**kw:breaker)
 assert await mod.RagRetriever().search_product_vector_ids('fixture',5)==[];client.assert_not_called()

def test_rrf_has_hand_calculated_order_and_no_duplicate_candidates():
 from app.rag.rrf import rrf_merge
 assert rrf_merge(['P1','P2'],['P2','P3'],3)==['P2','P1','P3']
