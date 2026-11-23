from unittest.mock import AsyncMock
import pytest
from app.auth.agent_context import agent_user_context
from app.graph import builder
from app.services.aftersales_context import load_case_progress, store
from app.services.java_internal_client import java_internal_client

@pytest.mark.parametrize('state,expected',[
    ({'route':'finalize'},'finalize'),({'route':'diagnosis'},'diagnosis_order'),
    ({'route':'agent_loop'},'agent_loop'),({'route':'end'},'cleanup'),
    ({'route':'finalize','cancelled':True},'cleanup'),({},'agent_loop'),
])
def test_context_route_is_honored(state,expected):
    assert builder._after_build_context(state)==expected

@pytest.mark.asyncio
async def test_complete_graph_case_progress_never_calls_llm(monkeypatch):
    call=AsyncMock(return_value=[{'caseId':'case-a','orderId':'order-a','state':'ARCHIVED','version':12}])
    monkeypatch.setattr(java_internal_client,'post_json',call)
    monkeypatch.setattr(store,'hint',AsyncMock(return_value={}))
    monkeypatch.setattr(builder,'entry_guard',AsyncMock(return_value={}))
    llm=AsyncMock(side_effect=AssertionError('A completed progress read must not invoke a model'))
    monkeypatch.setattr(builder,'agent_loop_node',llm)
    for name in ['finalize_node','post_turn_node','cleanup_node']:
        monkeypatch.setattr(builder,name,AsyncMock(return_value={}))
    with agent_user_context('A','unit-fixture'):
        result=await builder.build_agent_graph(persist_checkpoint=False).ainvoke({'user_id':'A','message_id':1,'user_text':'查看售后申请进度'})
    assert result['tool_biz']['caseProgress'][0]['caseId']=='case-a'
    call.assert_awaited_once_with('/api/order/aftersalesCase/list',{},strict=True)
    llm.assert_not_awaited()

@pytest.mark.asyncio
async def test_case_progress_rejects_untrusted_user_before_http(monkeypatch):
    call=AsyncMock();monkeypatch.setattr(java_internal_client,'post_json',call)
    with agent_user_context('A','unit-fixture'):
        with pytest.raises(ValueError,match='登录用户身份'):
            await load_case_progress('B')
    call.assert_not_awaited()

@pytest.mark.asyncio
async def test_failed_progress_query_finalizes_error_instead_of_model_fallback(monkeypatch):
    monkeypatch.setattr(java_internal_client,'post_json',AsyncMock(side_effect=RuntimeError('isolated failure')))
    monkeypatch.setattr(store,'hint',AsyncMock(return_value={}))
    monkeypatch.setattr(builder,'entry_guard',AsyncMock(return_value={}))
    llm=AsyncMock(side_effect=AssertionError('Do not hide a business read failure with model prose'))
    monkeypatch.setattr(builder,'agent_loop_node',llm)
    for name in ['finalize_node','post_turn_node','cleanup_node']:
        monkeypatch.setattr(builder,name,AsyncMock(return_value={}))
    with agent_user_context('A','unit-fixture'):
        result=await builder.build_agent_graph(persist_checkpoint=False).ainvoke({'user_id':'A','message_id':1,'user_text':'查询我的售后申请进度'})
    assert result['tool_biz']['caseProgressError'] is True
    assert builder._after_build_context(result)=='finalize'
    llm.assert_not_awaited()
