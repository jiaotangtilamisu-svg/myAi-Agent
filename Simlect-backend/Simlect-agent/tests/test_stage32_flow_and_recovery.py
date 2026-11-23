import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from test_stage32_business_contract import DIALOGS
from tools.quality_engineering.fixtures import product
from tools.quality_engineering.oracles import assert_shopping_result
from app.auth.agent_context import agent_user_context
from app.services.product_facts import normalize_product,query_result
from app.services.tool_invoke_result import ToolInvokeResult

@pytest.mark.asyncio
@pytest.mark.parametrize('dialog',DIALOGS,ids=lambda d:d['id'])
async def test_six_turn_graph_mcp_contract_and_message_result_persistence(monkeypatch,dialog):
    from app.shopping import runner,graph,store
    raw=[product(brand+str(price),price=price,brand=brand,count=2) for brand in ['三星','苹果','华为','小米','荣耀','OPPO','vivo'] for price in [4000,7000]]
    # Fixture identities are deliberately ASCII, like the actual Java SKU contract.
    for i,p in enumerate(raw):p['product_id']='P'+str(i);p['skus'][0]['sku_id']='S'+str(i)
    facts=[normalize_product(p) for p in raw];memory={};saved=[];calls=[]
    async def tool(name,args,user):
        calls.append(name)
        rows=facts if name=='SEARCH_PRODUCTS' else [p for p in facts if p['product_id'] in args['productIds']]
        return ToolInvokeResult(product_query=query_result(deepcopy(rows)))
    async def persist(user,token,mid,context,result):memory.clear();memory.update(deepcopy(context))
    async def complete(mid,text,kind,data):saved.append((mid,json.loads(data)));return True
    monkeypatch.setattr(graph.mcp_tool_router,'invoke',tool);monkeypatch.setattr(graph,'is_cancelled',AsyncMock(return_value=False))
    monkeypatch.setattr(runner,'is_cancelled',AsyncMock(return_value=False))
    monkeypatch.setattr(store,'acquire',AsyncMock(return_value='fixture-lease'))
    monkeypatch.setattr(store,'load',AsyncMock(side_effect=lambda user:deepcopy(memory)))
    monkeypatch.setattr(store,'save',persist);monkeypatch.setattr(store,'release',AsyncMock())
    monkeypatch.setattr(runner.agent_message_service,'complete_message',complete)
    monkeypatch.setattr(runner.stream_service,'push_done',AsyncMock())
    with agent_user_context('FIXTURE-A','isolated-not-a-real-session'):
        for mid,turn in enumerate(dialog['turns'],1):
            await runner.run_shopping_agent({'userId':'FIXTURE-A','messageId':mid,'userMessage':turn['text']})
            report=saved[-1][1]['fullReport'];r=report['requirements']
            assert (r['budgetMin'],r['budgetMax'],r['brands'],r['category'])==(turn['min'],turn['max'],[turn['brand']],'手机')
            assert_shopping_result(report,raw,ceiling=turn['max'],floor=turn['min'],in_stock=turn['stock'])
            assert all(turn['brand'] in p['productName'] for p in report['recommendations'])
            assert memory['requirements']==r and saved[-1][0]==mid
    assert len(saved)==6 and calls.count('SEARCH_PRODUCTS')==6
    assert len(calls)<=12  # No repeated tool loop or hidden model/tool retry.

@pytest.mark.asyncio
async def test_durable_supervisor_report_recovers_without_redis_or_cross_user_access(monkeypatch):
    from app.services import saved_agent_result as saved
    from test_supervisor import after
    report={'messageId':42,'results':{'aftersales':after().model_dump()}}
    async def row(user,mid):return {'status':2,'bizData':json.dumps({'agentType':'supervisor','messageId':42,'fullReport':report})} if user=='A' and mid==42 else None
    get=AsyncMock(side_effect=row);monkeypatch.setattr(saved.agent_message_service,'get_message',get)
    with agent_user_context('A','fixture'):
        assert await saved.load_saved_result('A',42,'supervisor')==report
        with pytest.raises(ValueError):await saved.load_saved_result('B',42,'supervisor')
    with agent_user_context('B','other-fixture'):assert await saved.load_saved_result('B',42,'supervisor') is None

@pytest.mark.asyncio
async def test_mcp_error_text_does_not_replay_java_query_or_count_success(monkeypatch):
    from app.services.mcp_tool_router import mcp_tool_router,mcp_streamable_client
    from app.services import mcp_tools_service
    from app.services.tool_audit import business_status
    remote=AsyncMock(return_value='【工具调用超时】未完成');local=AsyncMock(side_effect=AssertionError('no duplicate fallback'))
    monkeypatch.setattr(mcp_streamable_client,'call_tool',remote);monkeypatch.setattr(mcp_tools_service,'tool_query_orders',local)
    with agent_user_context('A','fixture'):r=await mcp_tool_router.invoke('QUERY_ORDERS',{},'A')
    assert business_status(r)=='ERROR';remote.assert_awaited_once();local.assert_not_awaited()
    assert business_status(ToolInvokeResult(content='some ordinary text'))=='UNKNOWN'

def test_no_match_reason_distinguishes_unknown_zero_and_service_failure():
    from app.shopping.selection import select
    from app.shopping.requirements import understand
    from app.shopping.explanations import explain_unmatched
    req=understand('手机必须有货')['requirements']
    for count,status,word in [(0,'SUCCESS','零'),(None,'MISSING','待确认'),(None,'UNAVAILABLE','不可用')]:
        row=product(count=count);row['skus'][0]['stock_query_status']=status
        r=select([row],req);assert not r['recommendations'];assert word in explain_unmatched(r)

@pytest.mark.asyncio
async def test_retrieval_diagnostics_are_task_local():
    from app.services.retrieval_trace import start,mark,snapshot
    async def run(value):start();mark('keyword',value);await asyncio.sleep(0);return snapshot()['keyword']
    assert await asyncio.gather(run('SUCCESS'),run('UNAVAILABLE'))==['SUCCESS','UNAVAILABLE']

@pytest.mark.asyncio
async def test_aftersales_pending_reference_is_user_scoped_and_never_executes(monkeypatch):
    from app.services.aftersales_context import prepare_turn
    from app.supervisor import store
    memories={}
    async def read(user):return deepcopy(memories.get(user,{}))
    async def write(user,value):memories[user]=deepcopy(value)
    monkeypatch.setattr(store,'hint',read);monkeypatch.setattr(store,'save_hint',write)
    oid='202611011536325281K0gVGxDdIOERZy'
    with agent_user_context('A','fixture'):
        _,r=await prepare_turn('A','我买错了，帮我退掉');assert r['operation']=='RETURN' and r['orderId'] is None
        _,r=await prepare_turn('A',oid);assert r['operation']=='RETURN' and r['orderId']==oid
        _,r=await prepare_turn('A','继续');assert r['orderId']==oid and r['operation']=='RETURN'
    with agent_user_context('B','other-fixture'):
        _,r=await prepare_turn('B','我要退这个订单');assert r['orderId'] is None and oid not in str(memories['B'])

@pytest.mark.asyncio
async def test_progress_query_in_support_mode_uses_existing_case_endpoint_not_llm(monkeypatch):
    from app.graph.nodes import build_context_node
    from app.services.aftersales_context import store
    from app.services.java_internal_client import java_internal_client
    monkeypatch.setattr(store,'hint',AsyncMock(return_value={}))
    call=AsyncMock(return_value=[{'caseId':'TEST-CASE','orderId':'O-A','state':'ADMIN_REVIEW','version':2}]);monkeypatch.setattr(java_internal_client,'post_json',call)
    with agent_user_context('A','fixture'):
        s=await build_context_node({'user_id':'A','message_id':7,'user_text':'查看售后申请进度'})
    assert s['route']=='finalize' and s['tool_biz']['caseProgress'][0]['caseId']=='TEST-CASE'
    call.assert_awaited_once_with('/api/order/aftersalesCase/list',{},strict=True)

@pytest.mark.parametrize('text',['不要退款','不用帮我退货','别自动换货','暂不取消订单'])
def test_negated_request_never_becomes_executable_application(text):
    from app.domain.aftersales_intent import classify
    assert classify(text)['operation'] not in {'RETURN','REFUND','EXCHANGE','CANCEL_ORDER'}

def test_missing_order_return_displays_verified_candidates_instead_of_generic_intent_question():
    from app.services.aftersales_diagnosis import render_diagnosis
    text=render_diagnosis({'requestedOperation':'RETURN_GUIDANCE','orderFacts':{'queryStatus':'MISSING_ORDER_ID','orderOptions':['OWN-A','OWN-B']}})
    assert 'OWN-A' in text and 'OWN-B' in text and '不会自动选择' in text

@pytest.mark.asyncio
async def test_tool_audit_distinguishes_guard_from_actual_remote_attempt(monkeypatch):
    from app.services import mcp_tool_router as module
    from app.services.tool_audit import audit_message
    logs=[]
    monkeypatch.setattr(module.logger,'info',lambda event,**values:logs.append(values))
    remote=AsyncMock(return_value='ordinary unverified response')
    monkeypatch.setattr(module.mcp_streamable_client,'call_tool',remote)
    with audit_message(71),agent_user_context('A','fixture'):
        await module.mcp_tool_router.invoke('NOT_A_TOOL',{},'A')
        await module.mcp_tool_router.invoke('QUERY_ORDERS',{},'A')
    assert [v['path'] for v in logs]==['GUARD','REMOTE_MCP']
    assert logs[0]['business_status']=='DENIED' and logs[0]['transport_status']=='NOT_CALLED'
    assert logs[-1]['transport_status']=='COMPLETED'
    assert all(v['message_id']==71 and v['duration_ms']>=0 for v in logs)
    assert logs[-1]['business_status']=='UNKNOWN'
    remote.assert_awaited_once()

def test_order_eligibility_reference_keeps_order_and_return_purpose():
    from app.domain.aftersales_intent import resolve
    from app.services.aftersales_diagnosis import identify_case,extract_order_id
    oid='202611011536325281K0gVGxDdIOERZy'
    text,intent=resolve('这个订单还能退吗？',{'orderId':oid,'businessIntent':'ORDER_DETAIL'})
    assert intent['operation']=='RETURN' and intent['orderId']==oid
    assert identify_case(text)=='AFTERSALES_CONSULT' and extract_order_id(text)==oid
    assert identify_case('这个订单还能退吗？')=='AFTERSALES_CONSULT'

def test_general_application_howto_is_policy_not_a_submission():
    from app.domain.aftersales_intent import classify
    from app.services.aftersales_diagnosis import identify_case
    assert classify('怎么申请售后？')['operation']=='POLICY_QUERY'
    assert identify_case('怎么申请售后？') is None
