"""Stage28 isolated business fixtures. No live model, embedding or data writes."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from app.shopping.requirements import understand, amount
from app.shopping.selection import select
from app.rag.evidence_quality import rank_evidence
from app.rag.policy import render_policy
from app.supervisor.routing import plan, signals
from app.services.data_provenance import classification
from test_shopping_agent import product


@pytest.mark.parametrize('text,value', [
    ('帮我推荐20以内的茶杯', '20'), ('推荐20元以内的茶杯', '20'),
    ('帮我找20块以下的茶杯', '20'), ('茶杯不超过20元的有吗', '20'),
    ('我想买一个20块钱以内的茶杯', '20'), ('预算20，推荐一个茶杯', '20'),
    ('推荐3000以内的手机', '3000'), ('帮我推荐3000元以内的手机', '3000'),
    ('推荐二十块钱以内的茶杯', '20'), ('茶杯控制在人民币二十元', '20'),
    ('最多两千三百元的手机', '2300'), ('茶杯不到20块', '20'),
])
def test_budget_rules(text, value):
    req = understand(text)['requirements']
    assert req['budgetMax'] == value
    assert req['category'] == ('手机' if '手机' in text else '茶杯')


@pytest.mark.parametrize('text', ['推荐20个茶杯', '买二十个茶杯', '茶杯容量20毫升', '20个茶杯以内', '最多二十个茶杯', '最多20个茶杯'])
def test_quantity_not_budget(text):
    assert understand(text)['requirements']['budgetMax'] is None


@pytest.mark.parametrize('raw,value', [('三千零五', '3005'), ('一万二千', '12000'), ('两百', '200'), ('3000', '3000')])
def test_chinese_numbers(raw, value):
    assert amount(raw) == value


def cup():
    p = product(price='12.3', count=7, category='茶杯')
    p['category_name'] = '生活日用'
    p['skus'].append({**deepcopy(p['skus'][0]), 'sku_id': 'black', 'sku_name': '黑色', 'price': '22.3', 'stock': 0})
    p['max_price'] = '22.3'
    return p


def test_same_sku_budget_and_stock_not_combined():
    selected = select([cup()], understand('20块以内的茶杯')['requirements'])['recommendations']
    assert len(selected) == 1
    assert len(selected[0]['eligibleSkus']) == 1
    assert selected[0]['eligibleSkus'][0]['price'] == '12.3'
    assert selected[0]['eligibleSkus'][0]['stock'] == 7


@pytest.mark.parametrize('name', ['智能手机', '保温杯', '运动水壶', '笔记本电脑'])
def test_no_unrelated_category_even_if_parent_says_cup(name):
    p = cup(); p['product_name'] = name; p['category_name'] = '茶杯'
    assert not select([p], understand('推荐20以内的茶杯')['requirements'])['recommendations']


@pytest.mark.parametrize('state', ['MISSING', 'UNAVAILABLE', 'INVALID_RESPONSE'])
def test_unknown_stock_not_zero(state):
    p = cup(); p['skus'] = p['skus'][:1]; p['skus'][0].update(stock=None, stock_query_status=state)
    sku = select([p], understand('茶杯')['requirements'])['recommendations'][0]['eligibleSkus'][0]
    assert sku['stock'] is None and sku['stock_query_status'] == state


def test_real_mode_rejects_unknown_and_synthetic():
    p = cup()
    assert not select([p], {}, data_mode='REAL')['recommendations']
    p['data_provenance'] = {'source_type': 'SYNTHETIC', 'field_sources': {}}
    assert not select([p], {}, data_mode='REAL')['recommendations']
    assert classification(p['data_provenance']) == 'TEST'
    assert classification(p['data_provenance'], 'DEMO001') == 'DEMO'


def test_real_requires_all_business_field_sources():
    p = cup(); p['data_provenance'] = {'source_type': 'LIVE_API', 'source_name': 'isolated test fixture',
                                      'field_sources': dict.fromkeys(['price', 'sku', 'stock'], 'LIVE_API')}
    assert len(select([p], {}, data_mode='REAL')['recommendations']) == 1
    p['data_provenance']['field_sources']['stock'] = 'SYNTHETIC'
    assert not select([p], {}, data_mode='REAL')['recommendations']


def hit(cid='c1', text='第十九条 测试样例退货条件', section='第十九条', score=.9):
    return dict(documentId='TEST_ONLY', revision=1, chunkId=cid, text=text, section=section,
                score=score, documentName='TEST ONLY 文档', source='fixture://test', category='LAW')


def test_policy_dedupe_preserves_different_articles():
    a = hit(); b = hit('c2'); c = hit('c3', '第二十条 测试样例其他条件', '第二十条')
    assert len(rank_evidence('退货条件', [a,a,b,c])) == 2
    assert rank_evidence('退货条件', [c,a])[0]['chunkId'] == 'c1'


def test_adjacent_overlap_is_removed_only_in_display_not_saved_evidence():
    from app.rag.evidence_quality import display_groups
    overlap = '相邻切片中完全相同的重叠条款内容，不得重复展示。'
    first = hit(text='独立条件甲。'+overlap)
    second = hit('c2',text=overlap+'独立条件乙。')
    originals = deepcopy([first,second])
    groups = display_groups([first,second])
    assert len(groups)==1 and groups[0]['text'].count(overlap)==1
    assert '独立条件甲' in groups[0]['text'] and '独立条件乙' in groups[0]['text']
    assert groups[0]['sourceChunkIds']==['c1','c2'] and [first,second]==originals


def test_metadata_heading_is_not_a_policy_clause():
    assert rank_evidence('退货', [hit(text='中华人民共和国消费者权益保护法实施条例',section='标题')])==[]


def test_policy_concise_no_full_wall_or_invented_promise():
    a = hit(text='第十九条 测试样例。' * 100)
    result = {'status': 'SUCCESS', 'hits': [a,a], 'query': '超过七天还能退货吗'}
    text = render_policy(result, concise=True)
    assert '不能确认' in text and '国家法规' in text and '完整条款' in text
    assert text.count('版本：1') == 1 and len(text) < 850
    assert result['hits'][0]['text'] == a['text']  # originals remain complete


@pytest.mark.parametrize('status', ['NO_MATCH','LOW_RELEVANCE','EMBEDDING_FAILED','ES_UNAVAILABLE','CATALOG_UNAVAILABLE'])
def test_rag_failure_is_not_policy_success(status):
    text = render_policy({'status': status, 'hits': []}, concise=True)
    assert '以下仅引用' not in text and '退款成功' not in text


def test_past_purchase_not_shopping_and_compound_independent():
    assert signals('我购买的商品超过七天还能退货吗') == (True,False)
    tasks = plan('查询退货政策，另外推荐20元以内的茶杯')['tasks']
    assert [t['agent'] for t in tasks] == ['aftersales','shopping']
    assert plan('超过七天还能退吗')['tasks'][0]['agent']=='aftersales'
    assert [t['agent'] for t in plan('超过七天还能退吗，另外推荐20元以内的茶杯')['tasks']]==['aftersales','shopping']


@pytest.mark.asyncio
async def test_missing_order_queries_own_list_but_never_auto_selects(monkeypatch):
    import json
    from app.graph import aftersales_nodes
    from app.services.mcp_tool_router import mcp_tool_router
    from app.services.tool_invoke_result import ToolInvokeResult
    from app.auth.agent_context import agent_user_context
    monkeypatch.setattr(aftersales_nodes, 'is_cancelled', AsyncMock(return_value=False))
    call = AsyncMock(return_value=ToolInvokeResult(content='TEST ONLY', assistant_cards=json.dumps([{'orderId':'A1'},{'orderId':'A2'}])))
    monkeypatch.setattr(mcp_tool_router, 'invoke', call)
    with agent_user_context('A','test'):
        result = await aftersales_nodes.diagnosis_order_node({'user_id':'A','message_id':1, 'user_text':'查询我自己的订单列表'})
    facts = result['diagnosis_order']
    assert facts['queryStatus'] == 'MISSING_ORDER_ID' and facts['orderOptions'] == ['A1','A2']
    assert facts['orderId'] is None and call.await_args.args == ('QUERY_ORDERS', {}, 'A')
    assert result['tools_called']==['QUERY_ORDERS']


@pytest.mark.asyncio
async def test_order_list_failure_is_not_empty_or_missing_identity(monkeypatch):
    from app.graph import aftersales_nodes
    from app.services.mcp_tool_router import mcp_tool_router
    from app.auth.agent_context import agent_user_context
    monkeypatch.setattr(aftersales_nodes,'is_cancelled',AsyncMock(return_value=False))
    monkeypatch.setattr(mcp_tool_router,'invoke',AsyncMock(side_effect=TimeoutError()))
    with agent_user_context('A','test'):
        result=await aftersales_nodes.diagnosis_order_node({'user_id':'A','message_id':1,'user_text':'查询我的订单列表'})
    assert result['diagnosis_order']['queryStatus']=='SERVICE_ERROR'
    assert result['tools_called']==['QUERY_ORDERS']


@pytest.mark.asyncio
async def test_demo_logistics_does_not_become_real_delivery(monkeypatch):
    from app.services import aftersales_facts, aftersales_diagnosis
    from app.auth.agent_context import agent_user_context
    from test_aftersales_diagnosis import order, NOW
    monkeypatch.setattr(aftersales_facts.java_internal_client, 'get_logistics', AsyncMock(return_value={
        'order_id':'O-A', 'logistics_status':5, 'receiver_address':'LOCAL DEMO - no physical delivery',
        'record_list':[{'record_time':'2026-10-01 12:00:00'}]}))
    with agent_user_context('A','test'):
        facts = (await aftersales_facts.read_logistics_facts('A','O-A')).business_facts
    assert facts['data']['dataClass'] == 'DEMO'
    report = aftersales_diagnosis.diagnose('LOGISTICS_STAGNATION','O-A',order(),facts,{'status':'NO_MATCH','hits':[]},now=NOW)
    text = aftersales_diagnosis.render_diagnosis(report)
    assert '演示记录' in text and '物流业务接口明确标记异常' not in text


@pytest.mark.asyncio
async def test_explicit_miss_cannot_hot_fallback(monkeypatch):
    from app.services import product_service as ps
    monkeypatch.setattr(ps.rag_retriever,'search_product_keyword_ids',AsyncMock(return_value=[]))
    monkeypatch.setattr(ps.rag_retriever,'search_product_vector_ids',AsyncMock(return_value=[]))
    monkeypatch.setattr(ps.java_internal_client,'search_on_sale',AsyncMock(return_value=[]))
    hot = AsyncMock(side_effect=AssertionError('Unrelated fallback forbidden'))
    monkeypatch.setattr(ps.search_recommend_service,'load_hot_sale',hot)
    result = await ps.product_service.search_products('A','茶杯',user_text='推荐茶杯')
    assert result[3] == []
    hot.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,text', [('support','推荐20元以内的茶杯'), ('shopping','如何换货'), ('support','查询退货政策，另外推荐手机')])
async def test_mode_resolution_dispatches_actual_required_agent(monkeypatch, mode, text):
    from app.services import agent_engine, agent_runtime
    from app.auth.agent_context import agent_user_context
    from app.shopping import runner
    persist = AsyncMock(); support = AsyncMock(); shopping = AsyncMock(); supervisor=AsyncMock()
    from app.supervisor import runner as supervisor_runner
    monkeypatch.setattr(supervisor_runner,"run_supervisor",supervisor)
    monkeypatch.setattr(agent_runtime, '_persist_and_notify', persist)
    monkeypatch.setattr(agent_engine, 'run_agent_graph', support)
    monkeypatch.setattr(runner, 'run_shopping_agent', shopping)
    with agent_user_context('A', 'test'):
        await agent_engine.agent_engine.assistant_answer({'userId':'A','messageId':98,'userMessage':text,'agentMode':mode})
    persist.assert_not_awaited()
    if '另外' in text:supervisor.assert_awaited_once();support.assert_not_awaited();shopping.assert_not_awaited()
    elif mode=='support':shopping.assert_awaited_once();support.assert_not_awaited();supervisor.assert_not_awaited()
    else:support.assert_awaited_once();shopping.assert_not_awaited();supervisor.assert_not_awaited()
