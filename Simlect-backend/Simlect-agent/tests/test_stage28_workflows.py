"""Run original specialist graphs together with isolated transport/storage/model boundaries."""
import json
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from app.auth.agent_context import agent_user_context
from app.graph import builder, nodes, aftersales_nodes
from app.rag import advice
from app.services import agent_runtime as runtime, agent_service, message_service
from app.services.mcp_tool_router import mcp_tool_router
from app.services.tool_invoke_result import ToolInvokeResult
from app.shopping import graph as shopping_graph, runner as shopping_runner, store as shopping_store
from app.supervisor import adapters, graph as supervisor_graph, store as supervisor_store
from test_shopping_agent import wire, product
from test_stage28_quality import cup, hit


def capabilities():
    source = (Path(__file__).resolve().parents[3] / 'Simlect-front/Simlect-web/src/utils/agentCapabilities.ts').read_text(encoding='utf8')
    return [(mode, text) for modes,text in re.findall(r"modes: \[([^\]]+)\], text: '([^']+)'", source)
            for mode in re.findall(r"'(support|shopping|supervisor)'", modes)]


@pytest.fixture
def boundaries(monkeypatch):
    calls = []
    async def invoke(tool, args, user):
        assert user == 'A'
        calls.append((tool,args))
        if tool == 'QUERY_ORDERS':
            return ToolInvokeResult(content='TEST ONLY',assistant_cards=json.dumps([{'orderId':'A1'},{'orderId':'A2'}]))
        rows = [product(price=1200), cup()]
        if tool == 'GET_PRODUCT_DETAIL':
            rows = [p for p in rows if p['product_id'] in args['productIds']]
        # Distinct IDs make this a faithful multi-product batch fixture.
        return wire(rows)
    p = product(price=1200)
    p['product_id']='PHONE';p['skus'][0]['sku_id']='PHONE-SKU'
    c = cup()
    async def tools(tool,args,user):
        if tool == 'QUERY_ORDERS': return await invoke(tool,args,user)
        assert user == 'A'; calls.append((tool,args))
        rows = [p,c]
        if tool == 'GET_PRODUCT_DETAIL':rows=[r for r in rows if r['product_id'] in args['productIds']]
        return wire(rows)
    monkeypatch.setattr(mcp_tool_router,'invoke',tools)
    for module in (runtime,shopping_graph,shopping_runner,aftersales_nodes,supervisor_graph):
        monkeypatch.setattr(module,'is_cancelled',AsyncMock(return_value=False))
    monkeypatch.setattr(runtime.redis_service,'bind_message_id',AsyncMock())
    monkeypatch.setattr(runtime.redis_service,'clear_bound_message_id',AsyncMock())
    monkeypatch.setattr(nodes.sensitive_word_service,'replace',AsyncMock(side_effect=lambda x:x))
    monkeypatch.setattr(nodes.rag_retriever,'search_policy',AsyncMock(return_value={'status':'SUCCESS','hits':[hit()]}))
    monkeypatch.setattr(advice,'policy_advice',AsyncMock(return_value={'status':'UNAVAILABLE','failureCode':'MODEL_TIMEOUT'}))
    monkeypatch.setattr(builder,'post_turn_node',AsyncMock(return_value={}))
    monkeypatch.setattr(builder,'cleanup_node',AsyncMock(return_value={}))
    for store in (shopping_store,supervisor_store):
        monkeypatch.setattr(store,'acquire',AsyncMock(return_value='test-lock'))
        monkeypatch.setattr(store,'load',AsyncMock(return_value={}))
        monkeypatch.setattr(store,'save',AsyncMock())
        monkeypatch.setattr(store,'release',AsyncMock())
    monkeypatch.setattr(supervisor_store,'hint',AsyncMock(return_value={}))
    monkeypatch.setattr(supervisor_store,'save_hint',AsyncMock())
    monkeypatch.setattr(runtime.stream_service,'push_agent_status',AsyncMock())
    monkeypatch.setattr(runtime.stream_service,'push_done',AsyncMock())
    monkeypatch.setattr(runtime.agent_message_service,'complete_message',AsyncMock(return_value=True))
    # Clear only test process graph caches, never live checkpoints or Redis data.
    adapters.aftersales_graph.cache_clear()
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,text',capabilities())
async def test_each_visible_prompt_reaches_original_specialist_workflow(boundaries,mode,text):
    message={'userId':'A','messageId':28,'userMessage':text,'agentMode':mode}
    with agent_user_context('A','isolated-fixture-session'):
        if mode == 'shopping':
            result=await shopping_runner.run_shopping_agent(message,collect_only=True)
            if '对比' in text:
                assert result['status']=='NEEDS_CLARIFICATION'  # first turn has no comparison history
            else:
                assert result['status']=='SUCCESS'
                assert [c[0] for c in boundaries]==['SEARCH_PRODUCTS','GET_PRODUCT_DETAIL']
        elif mode == 'support':
            result=await adapters.invoke({'agent':'aftersales','text':text},'A',28)
            assert result.status in ('SUCCESS','NEEDS_CLARIFICATION')
            if '订单列表' in text:
                assert [r['orderId'] for r in result.data['orderList']]==['A1','A2']
                assert boundaries==[('QUERY_ORDERS',{})]
            else:
                assert result.data['policy']['hits'][0]['source']=='fixture://test'
        else:
            state=await supervisor_graph.build_supervisor_graph().ainvoke({'user_id':'A','message_id':28,'text':text})
            report=state['report']
            assert all(r['status'] in ('SUCCESS','NEEDS_CLARIFICATION') for r in report['results'].values())
            assert len(report['results'])==(2 if '另外' in text else 1)
            if '另外' in text:
                assert report['results']['aftersales']['data']['policy']['hits']
                assert report['results']['shopping']['data']['shopping']['recommendations']


@pytest.mark.asyncio
async def test_background_db_error_is_not_relabelled_model_failure(monkeypatch):
    monkeypatch.setattr(agent_service.agent_engine,'assistant_answer',AsyncMock(side_effect=message_service.MessagePersistenceError()))
    failed=AsyncMock();generic=AsyncMock()
    monkeypatch.setattr(runtime,'push_persistence_error',failed)
    monkeypatch.setattr(agent_service.agent_orchestrator,'_finish_error',generic)
    await agent_service.agent_orchestrator._run_agent({'userId':'A','messageId':28})
    failed.assert_awaited_once();generic.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_shopping_result_cannot_send_done(boundaries,monkeypatch):
    done=AsyncMock()
    monkeypatch.setattr(runtime.stream_service,'push_done',done)
    monkeypatch.setattr(runtime.agent_message_service,'complete_message',AsyncMock(return_value=False))
    with agent_user_context('A','test'):
        await shopping_runner.run_shopping_agent({'userId':'A','messageId':28,'userMessage':'推荐20元以内的茶杯'})
    done.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_supervisor_cannot_emit_done_or_success(boundaries,monkeypatch):
    from app.supervisor import runner
    monkeypatch.setattr(runner,'is_cancelled',AsyncMock(return_value=False))
    done=AsyncMock();progress=AsyncMock()
    monkeypatch.setattr(runtime.stream_service,'push_done',done)
    monkeypatch.setattr(runtime.stream_service,'push_agent_status',progress)
    monkeypatch.setattr(runtime.agent_message_service,'complete_message',AsyncMock(return_value=False))
    with agent_user_context('A','test'):
        await runner.run_supervisor({'userId':'A','messageId':28,'userMessage':'推荐20元以内的茶杯'})
    done.assert_not_awaited()
    assert not any(c.args[2:]==('supervisor','SUCCESS') for c in progress.await_args_list)
