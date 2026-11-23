from unittest.mock import AsyncMock,Mock
import pytest
from app.auth.agent_context import agent_user_context
from app.supervisor import adapters
from app.supervisor.aggregation import aggregate,display

ORDER='20261105084511284JdzCFzXfcTM0dcR'
def diagnosis():
    return {'schemaVersion':1,'caseType':'AFTERSALES_CONSULT','orderId':ORDER,'executionAllowed':False,'approvalRequired':True,
      'orderFacts':{'queryStatus':'SUCCESS','data':{'orderId':ORDER,'ownerVerified':True,'orderStatus':1}},
      'diagnosis':{'status':'NOT_OBSERVED','reasons':['距下单时间约0.98小时；不是政策阈值'],'conflicts':[],'uncertainties':['缺少规则']},
      'policyEvidence':{'status':'LOW_RELEVANCE','hits':[]},'evidenceSources':[],'recommendedActions':[]}

@pytest.mark.asyncio
async def test_return_alias_shows_application_not_anomaly_and_keeps_full_evidence(monkeypatch):
    report=diagnosis();g=Mock();g.ainvoke=AsyncMock(return_value={'diagnosis_report':report})
    monkeypatch.setattr(adapters,'aftersales_graph',lambda:g)
    monkeypatch.setattr(adapters.store,'hint',AsyncMock(return_value={}))
    monkeypatch.setattr(adapters.store,'save_hint',AsyncMock())
    task={'agent':'aftersales','text':f'帮我退一下订单为{ORDER}的货'}
    with agent_user_context('A','fixture-session'):r=await adapters.invoke(task,'A',1)
    full=aggregate({'tasks':[task]}, {'aftersales':r.model_dump()});shown=display(full)
    assert shown['canCreateCase'] is True
    assert '生成待确认的售后方案' in shown['intro']
    assert '距下单' not in shown['intro'] and '诊断：' not in shown['intro']
    assert full['results']['aftersales']['data']['diagnosis']['diagnosis']['reasons']==report['diagnosis']['reasons']

@pytest.mark.asyncio
async def test_case_progress_uses_current_identity_and_does_not_diagnose_order(monkeypatch):
    from app.services.java_internal_client import java_internal_client
    call=AsyncMock(return_value=[]);monkeypatch.setattr(java_internal_client,'post_json',call)
    with agent_user_context('A','fixture-session'):
        r=await adapters.invoke({'agent':'aftersales','text':'查询我的售后申请进度'},'A',1)
    assert r.status=='SUCCESS' and r.data=={'caseList':[]}
    call.assert_awaited_once_with('/api/order/aftersalesCase/list',{},strict=True)

@pytest.mark.asyncio
async def test_policy_query_with_do_not_submit_does_not_query_case_list(monkeypatch):
    from app.services.java_internal_client import java_internal_client
    call=AsyncMock(side_effect=AssertionError('Wrong route'));monkeypatch.setattr(java_internal_client,'post_json',call)
    g=Mock();g.ainvoke=AsyncMock(return_value={'policy_result':{'status':'NO_MATCH','hits':[]}})
    monkeypatch.setattr(adapters,'aftersales_graph',lambda:g)
    monkeypatch.setattr(adapters.store,'hint',AsyncMock(return_value={}))
    monkeypatch.setattr(adapters.store,'save_hint',AsyncMock())
    with agent_user_context('A','fixture-session'):
        r=await adapters.invoke({'agent':'aftersales','text':'如何换货？请查询现有售后政策，不要提交申请'},'A',1)
    call.assert_not_awaited();assert 'policy' in r.data
