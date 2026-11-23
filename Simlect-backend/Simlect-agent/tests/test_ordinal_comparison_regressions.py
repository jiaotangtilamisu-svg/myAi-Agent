import pytest
from unittest.mock import AsyncMock
from app.auth.agent_context import agent_user_context
from app.shopping import graph, runner, store
from app.shopping.requirements import understand
from app.shopping.runner import render_comparison
from app.services.aftersales_diagnosis import wants_return,identify_case
from test_shopping_agent import product, run

@pytest.mark.parametrize('text',['帮我比较一下第一个和第二个手机','对比第一款和第二款手机','比较第1个与第2个手机','比较第一和第二款手机','前两款手机比一下'])
@pytest.mark.asyncio
async def test_ordinals_are_references_not_recommendation_count(text,monkeypatch):
    monkeypatch.setattr(graph,'is_cancelled',AsyncMock(return_value=False))
    rows=[product('P1'),product('P2',price=1800),product('P3',price=2000)]
    prior={'ids':['P1','P2','P3'],'requirements':understand('推荐三个手机')['requirements']}
    result,tools=await run(text,rows,monkeypatch,previous=prior)
    assert result['isComparison'] is True
    assert [r['productId'] for r in result['comparison']]==['P1','P2']
    assert result['requirements']['requestedCount']==2
    assert tools.await_count==1 and tools.await_args.args[0]=='GET_PRODUCT_DETAIL'
    assert tools.await_args.args[1]['productIds']==['P1','P2']
    text=render_comparison(result);assert 'P1' in text and 'P2' in text and 'P3' not in text

@pytest.mark.asyncio
async def test_nonexistent_ordinal_requests_clarification_without_tools(monkeypatch):
    monkeypatch.setattr(graph,'is_cancelled',AsyncMock(return_value=False))
    result,tools=await run('比较第一个和第三个手机',[],monkeypatch,previous={'ids':['P1','P2'],'requirements':understand('推荐手机')['requirements']})
    assert result['status']=='NEEDS_CLARIFICATION';tools.assert_not_awaited()

@pytest.mark.parametrize('text',['帮我退一下订单1234567890的货','我想把订单退了应该怎么操作','退一下','申请退款','帮我退一退这个商品'])
def test_return_variants(text):assert wants_return(text)

def test_independent_support_also_recognizes_return_request():
    assert identify_case('帮我退一下订单1234567890的货')=='AFTERSALES_CONSULT'

@pytest.mark.parametrize('text',['查询退款进度','退款多久到账','查询退货政策','不要提交退款申请'])
def test_policy_or_progress_does_not_start_new_application(text):assert not wants_return(text)

@pytest.mark.asyncio
async def test_comparison_does_not_destroy_original_three_recommendations(monkeypatch):
    prior={'ids':['P1','P2','P3'],'requirements':understand('推荐三个手机')['requirements'],'baseline':[{'price':'1200'}]}
    monkeypatch.setattr(graph,'is_cancelled',AsyncMock(return_value=False));monkeypatch.setattr(runner,'is_cancelled',AsyncMock(return_value=False))
    monkeypatch.setattr(store,'acquire',AsyncMock(return_value='fixture'));monkeypatch.setattr(store,'load',AsyncMock(return_value=prior))
    save=AsyncMock();monkeypatch.setattr(store,'save',save);monkeypatch.setattr(store,'release',AsyncMock())
    from test_shopping_agent import wire
    monkeypatch.setattr(graph.mcp_tool_router,'invoke',AsyncMock(return_value=wire([product('P1'),product('P2')])))
    with agent_user_context('A','test-session'):
        result=await runner.run_shopping_agent({'userId':'A','messageId':1,'userMessage':'比较第一个和第二个手机'},collect_only=True)
    assert result['isComparison']
    assert save.await_args.args[3]['ids']==['P1','P2','P3']
    assert save.await_args.args[3]['requirements']['requestedCount']==3
