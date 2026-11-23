import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, Mock
import httpx
import pytest
from app.services import agent_runtime as rt, message_service as messages
from app.rag import advice
from test_policy_model_resilience import config, mock_transport, EVIDENCE

def evidence():
    return {'status':'SUCCESS','hits':[{'chunkId':f'chunk-{i}','documentId':'fixture-only','documentName':'TEST ONLY',
        'revision':7,'score':0.9,'section':f'Section {i}','text':'证据'*3000,'source':'TEST ONLY fixture://source'} for i in range(5)]}

@pytest.mark.asyncio
@pytest.mark.parametrize('model',[{'status':'MODEL_GROUNDED','neededFacts':['category']},
    {'status':'UNAVAILABLE','failureCode':'MODEL_TIMEOUT'}, {'status':'UNAVAILABLE','failureCode':'MODEL_UPSTREAM_UNAVAILABLE'}])
async def test_complete_and_degraded_policy_save_full_json_before_notification(monkeypatch,model):
    events=[];payload=evidence()
    async def save(mid,text,kind,data):
        events.append('persist');parsed=json.loads(data)
        assert len(data)>2000 and parsed['hits']==payload['hits'] and parsed['messageId']==91
        assert parsed['modelStatus']==model['status']
        return True
    async def push(*args,**kwargs):
        events.append('notify');assert json.loads(kwargs['biz_data'])['hits']==payload['hits']
    monkeypatch.setattr(rt.agent_message_service,'complete_message',save)
    monkeypatch.setattr(rt.stream_service,'push_done',push)
    await rt.finalize_agent_response({'userId':'test','messageId':91},[],[],user_text='七天后还能退货吗？',
        tool_biz={'policyQuery':payload,'policyAdvice':model})
    assert events==['persist','notify']

@pytest.mark.asyncio
async def test_failed_db_write_cannot_emit_done_or_null_evidence_success(monkeypatch):
    monkeypatch.setattr(rt.agent_message_service,'complete_message',AsyncMock(side_effect=messages.MessagePersistenceError()))
    done=AsyncMock();monkeypatch.setattr(rt.stream_service,'push_done',done)
    with pytest.raises(messages.MessagePersistenceError):
        await rt.finalize_agent_response({'userId':'test','messageId':91},[],[],user_text='还能退货吗？',tool_biz={'policyQuery':evidence()})
    done.assert_not_awaited()

def test_invalid_evidence_json_cannot_be_silently_replaced_or_reported_as_success():
    with pytest.raises(messages.MessagePersistenceError): rt._evidence_json({'value': float('nan')})
    with pytest.raises(messages.MessagePersistenceError): rt._evidence_json({'value': object()})

@pytest.mark.asyncio
async def test_failed_db_write_uses_explicit_failure_marker_and_error_code(monkeypatch):
    mark=AsyncMock();error=AsyncMock();success=AsyncMock()
    monkeypatch.setattr(rt.agent_message_service,'mark_persistence_failed',mark)
    monkeypatch.setattr(rt.agent_message_service,'complete_message',success)
    monkeypatch.setattr(rt.stream_service,'push_error',error)
    await rt.push_persistence_error({'userId':'test','messageId':91})
    mark.assert_awaited_once_with('test',91);success.assert_not_awaited()
    assert error.await_args.kwargs['error_code']=='DB_PERSISTENCE_FAILED'

@pytest.mark.asyncio
async def test_graph_does_not_reclassify_persistence_error_as_model_completion(monkeypatch):
    from app.graph import nodes
    monkeypatch.setattr(nodes.rt,'finalize_agent_response',AsyncMock(side_effect=messages.MessagePersistenceError()))
    failure=AsyncMock();legacy=AsyncMock()
    monkeypatch.setattr(nodes.rt,'push_persistence_error',failure)
    monkeypatch.setattr(nodes.rt,'push_chat_error',legacy)
    monkeypatch.setattr(nodes.sensitive_word_service,'replace',AsyncMock(side_effect=lambda t:t))
    monkeypatch.setattr(nodes.redis_service,'clear_bound_message_id',AsyncMock())
    result=await nodes.finalize_node({'agent_msg':{'userId':'test','messageId':91},'user_id':'test','message_id':91,'chunks':['TEST']})
    assert result['persistence_failed'] is True
    failure.assert_awaited_once();legacy.assert_not_awaited()
    assert (await nodes.post_turn_node(result))['finished'] is True

@pytest.mark.asyncio
async def test_notification_failure_keeps_durable_result(monkeypatch):
    saved=AsyncMock(return_value=True)
    monkeypatch.setattr(rt.agent_message_service,'complete_message',saved)
    monkeypatch.setattr(rt.stream_service,'push_done',AsyncMock(side_effect=RuntimeError('offline')))
    await rt._persist_and_notify({'userId':'test','messageId':91},'saved','agent','{}')
    saved.assert_awaited_once()

@pytest.mark.asyncio
async def test_message_service_passes_large_json_unchanged(monkeypatch):
    data=json.dumps(evidence(),ensure_ascii=False);cur=Mock();cur.execute=AsyncMock(return_value=1)
    @asynccontextmanager
    async def acquire():yield cur
    monkeypatch.setattr(messages,'acquire',acquire)
    assert await messages.agent_message_service.complete_message(91,'TEST','agent',data)
    assert cur.execute.await_args.args[1][2]==data

@pytest.mark.asyncio
async def test_message_service_wraps_db_error_not_model_error(monkeypatch):
    @asynccontextmanager
    async def acquire():raise RuntimeError('database unavailable');yield
    monkeypatch.setattr(messages,'acquire',acquire)
    with pytest.raises(messages.MessagePersistenceError):
        await messages.agent_message_service.complete_message(91,'TEST','agent','{}')

class SlowBody(httpx.AsyncByteStream):
    closed = False
    async def aclose(self): self.closed = True
    async def __aiter__(self):
        await asyncio.sleep(10)
        yield b'{}'

class BrokenBody(httpx.AsyncByteStream):
    closed = False
    async def aclose(self): self.closed = True
    async def __aiter__(self):
        yield b'{"choices":'
        raise httpx.ReadError('MOCK incomplete body')

@pytest.mark.asyncio
@pytest.mark.parametrize('body',['delayed','broken','invalid_json'])
async def test_http200_headers_do_not_mean_a_complete_response(monkeypatch,config,body):
    from app.services.llm_factory import create_policy_llm
    async with httpx.AsyncClient() as warm:create_policy_llm(http_async_client=warm)
    if body=='delayed':config.policy_llm_timeout_seconds=0.2
    calls=[];streams=[]
    def handler(request):
        calls.append(request)
        if body=='invalid_json':return httpx.Response(200,content=b'not-json')
        stream=SlowBody() if body=='delayed' else BrokenBody();streams.append(stream)
        return httpx.Response(200,stream=stream)
    mock_transport(monkeypatch,handler)
    log=Mock();monkeypatch.setattr(advice,'logger',log)
    result=await advice.policy_advice('TEST',EVIDENCE)
    assert result['status']=='UNAVAILABLE' and len(calls)==1
    assert log.warning.call_args.kwargs['status_code']==200
    assert log.warning.call_args.kwargs['phase']=='BODY'
    assert all(stream.closed for stream in streams)
    if body=='invalid_json': assert result['failureCode']=='MODEL_INVALID_RESPONSE'
