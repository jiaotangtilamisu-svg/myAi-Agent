"""Durable async delivery, owned reads and real-shaped shopping regression; no network."""
import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from app.auth.agent_context import agent_user_context, require_agent_user
from app.services import agent_service as service
from app.services import message_service
from app.shopping.requirements import understand
from app.shopping.selection import select
from fastapi import FastAPI
from test_shopping_agent import product


@pytest.mark.parametrize('overrides,expected', [({},True),({'shopping_requirement_llm_enabled':False},False)])
def test_real_shopping_understanding_default_and_explicit_offline_switch(monkeypatch,overrides,expected):
    from app.config.settings import Settings
    monkeypatch.delenv('SHOPPING_REQUIREMENT_LLM_ENABLED',raising=False)
    assert Settings(_env_file=None,**overrides).shopping_requirement_llm_enabled is expected


@pytest.mark.parametrize('text', [
    '预算300元以内，推荐适合日常使用的商品，优先考虑库存充足的商品。',
    '请搜索当前商城实际在售的商品，根据我的需求推荐适合的商品',
    '再推荐一款300元以内适合日常使用的商品',
])
def test_catalogue_words_are_not_product_name_filters(text):
    parsed = understand(text)
    assert parsed['clarification'] is None
    assert parsed['requirements']['keyword'] == ''
    result = select([product(price=120, count=8)], parsed['requirements'])
    assert len(result['recommendations']) == 1


def test_specific_keyword_not_relaxed():
    req = understand('搜索保温杯商品')['requirements']
    assert req['keyword'] == '保温杯商品'
    assert not select([product(price=120)], req)['recommendations']


def test_stock_priority_uses_measured_sku_stock():
    req = understand('推荐商品，预算300元以内，优先考虑库存充足')['requirements']
    result = select([product('P1', price=120, count=2), product('P2', price=120, count=99)], req)
    assert result['recommendations'][0]['productId'] == 'P2'
    assert result['recommendations'][0]['eligibleSkus'][0]['stock'] == 99


@pytest.mark.asyncio
async def test_catalogue_reads_java_batch_without_embedding(monkeypatch):
    from app.services import product_service as ps
    search=AsyncMock(return_value=[{'product_id':'P1'}])
    batch=AsyncMock(return_value=[product('P1',price=120)])
    embed=AsyncMock(side_effect=AssertionError('catalogue does not need embedding'))
    monkeypatch.setattr(ps.java_internal_client,'search_on_sale',search)
    monkeypatch.setattr(ps.product_service,'_load_products_by_ids',batch)
    monkeypatch.setattr(ps.rag_retriever,'search_product_vector_ids',embed)
    result=await ps.product_service.search_products('A','')
    assert result[3][0]['product_id']=='P1'
    search.assert_awaited_once()
    assert search.await_args.kwargs['keyword']==''
    batch.assert_awaited_once_with(['P1'])
    embed.assert_not_awaited()


@pytest.mark.asyncio
async def test_deepseek_structured_parser_disables_thinking_only_for_this_copy(monkeypatch):
    from unittest.mock import Mock

    from app.shopping import extraction
    provider=SimpleNamespace(ainvoke=AsyncMock(return_value={'slots':[{'field':'keyword','value':'商品','quote':'推荐商品'},{'field':'attribute','name':'库存','value':'充足','quote':'库存充足'}]}))
    clone=SimpleNamespace(with_structured_output=Mock(return_value=provider))
    llm=SimpleNamespace(extra_body={'other':'preserve'},model_copy=Mock(return_value=clone))
    monkeypatch.setattr(extraction,'create_chat_llm',lambda:llm)
    monkeypatch.setattr(extraction,'get_settings',lambda:SimpleNamespace(shopping_requirement_llm_enabled=True,llm_base_url='https://api.deepseek.com',llm_model='deepseek-flash'))
    result=await extraction.extract('推荐商品，库存充足')
    assert result['source']=='rules+grounded_llm'
    assert result['requirements']['keyword']==''
    assert '库存' not in result['requirements']['attributes']
    assert llm.extra_body=={'other':'preserve'}
    assert llm.model_copy.call_args.kwargs['update']['extra_body']['thinking']=={'type':'disabled'}
    assert clone.with_structured_output.call_args.kwargs=={'method':'function_calling'}


@pytest.mark.asyncio
async def test_terminal_result_persisted_even_if_pubsub_fails(monkeypatch):
    events = []
    async def save(*args): events.append('persist')
    async def push(*args):
        events.append('push')
        raise RuntimeError('offline')
    monkeypatch.setattr(service.agent_message_service, 'complete_message', save)
    monkeypatch.setattr(service.stream_service, 'push_error', push)
    await service.agent_orchestrator._finish_error('A', 7, 'failed')
    assert events == ['persist', 'push']


@pytest.mark.parametrize('failure', [RuntimeError('LLM failure'), TimeoutError()])
@pytest.mark.asyncio
async def test_background_failure_is_terminal(monkeypatch, failure):
    monkeypatch.setattr(service.agent_engine, 'assistant_answer', AsyncMock(side_effect=failure))
    monkeypatch.setattr(service, 'get_settings', lambda: SimpleNamespace(agent_task_timeout_seconds=1))
    save, push = AsyncMock(), AsyncMock()
    monkeypatch.setattr(service.agent_message_service, 'complete_message', save)
    monkeypatch.setattr(service.stream_service, 'push_error', push)
    await service.agent_orchestrator._run_agent({'userId':'A','messageId':7})
    save.assert_awaited_once()
    assert save.await_args.args[2] == 'agent_error'
    assert ('超时' in save.await_args.args[1]) == isinstance(failure, TimeoutError)


@pytest.mark.parametrize('mode', ['support', 'shopping', 'supervisor'])
@pytest.mark.asyncio
async def test_send_schedules_inherited_identity_without_waiting_for_reply(monkeypatch, mode):
    monkeypatch.setattr(service, 'get_settings', lambda: SimpleNamespace(ai_chat_limit=0, task_queue_max=8, agent_task_timeout_seconds=300))
    monkeypatch.setattr(service.rate_limit_service, 'allow', AsyncMock(return_value=True))
    monkeypatch.setattr(service.input_guard, 'detect_injection', lambda _:False)
    monkeypatch.setattr(service.sensitive_word_service, 'replace', AsyncMock(side_effect=lambda x:x))
    monkeypatch.setattr(service.redis_service, 'pause_consult', AsyncMock())
    monkeypatch.setattr(service.agent_message_service, 'save_user_message', AsyncMock(return_value={'userId':'A','messageId':8}))
    calls=[]
    async def run(msg):
        calls.append((require_agent_user('A').user_id,msg.get('agentMode','support')))
    monkeypatch.setattr(service.agent_engine, 'assistant_answer', run)
    with agent_user_context('A','test-session'):
        reply=await service.agent_orchestrator.send_message('A','推荐商品',agent_mode=mode)
    assert reply['messageId']==8
    await asyncio.gather(*tuple(service._tasks))
    assert calls == [('A','supervisor' if mode=='supervisor' else 'shopping')]
    assert reply['agentMode']==calls[0][1] and reply['requestedMode']==mode


@pytest.mark.asyncio
async def test_result_sql_contains_user_ownership(monkeypatch):
    cursor=AsyncMock()
    cursor.fetchone.return_value=None
    @asynccontextmanager
    async def acquire(): yield cursor
    monkeypatch.setattr(message_service,'acquire',acquire)
    assert await message_service.agent_message_service.get_message('A',7) is None
    sql,args=cursor.execute.await_args.args
    assert 'message_id=%s AND user_id=%s' in sql
    assert args==(7,'A')


@pytest.mark.parametrize('row,code', [(None,404),({'messageId':7,'status':2,'assistantMessage':'answer'},200)])
@pytest.mark.asyncio
async def test_result_http_ignores_forged_user_id(monkeypatch,row,code):
    from app.api.routes import agent
    app=FastAPI(); app.include_router(agent.router,prefix='/api')
    async def login():
        with agent_user_context('A','test-session'): yield SimpleNamespace(user_id='A')
    app.dependency_overrides[agent.require_login]=login
    read=AsyncMock(return_value=row)
    monkeypatch.setattr(agent.agent_message_service,'get_message',read)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test.invalid') as client:
        response=await client.post('/api/agent/getMessage',data={'messageId':7,'userId':'B'})
    assert response.json()['code']==code
    read.assert_awaited_once_with('A',7)
