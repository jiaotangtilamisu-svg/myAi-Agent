import pytest
from unittest.mock import AsyncMock
from app.auth.agent_context import agent_user_context
from app.domain.aftersales_intent import classify,resolve
from app.services.mode_routing import effective_mode
from app.shopping.requirements import understand
from app.shopping.selection import select
from tools.quality_engineering.fixtures import product

@pytest.mark.parametrize('alias,brand',[('Samsung','三星'),('Galaxy','三星'),('Apple','苹果'),('iPhone','苹果'),('Redmi','小米'),('Xiaomi','小米'),('Huawei','华为')])
def test_brand_alias_budget_and_mode_agree(alias,brand):
 text=f'推荐5000以上的{alias}手机';r=understand(text)['requirements']
 assert r['brands']==[brand] and r['budgetMin']=='5000' and r['budgetMax'] is None
 assert effective_mode(text,'support')=='shopping'

@pytest.mark.parametrize('text,op',[('我要退一下','RETURN'),('这个商品不想要了','RETURN'),('我的退货申请到哪一步了','AFTERSALES_PROGRESS'),('我要取消刚才的退货申请','CANCEL_APPLICATION'),('我要退202611011536325281K0gVGxDdIOERZy的货','RETURN')])
def test_return_action_object_grammar(text,op):
 assert classify(text)['operation']==op and effective_mode(text,'shopping')=='support'

def test_soft_quality_preference_is_not_aftersales():
 assert effective_mode('推荐质量好一点的三星手机','shopping')=='shopping'
 assert effective_mode('手机有质量问题，另外推荐茶杯','shopping')=='supervisor'
 assert effective_mode('推荐续航七天的手机','support')=='shopping'
 assert effective_mode('不要推荐手机，查询订单','shopping')=='support'

@pytest.mark.parametrize('text,key,value',[('500毫升的陶瓷茶杯','容量','500毫升'),('蓝牙头戴式耳机','耳机类型','头戴式'),('蓝牙头戴式耳机','连接方式','蓝牙'),('电脑内存16GB硬盘1TB','内存','16GB'),('电脑内存16GB硬盘1TB','存储容量','1TB'),('CPU i7-13650笔记本','处理器','i7-13650'),('1200W的家电','功率','1200W')])
def test_typed_attributes_do_not_become_price(text,key,value):
 r=understand(text)['requirements'];assert r['attributes'][key]==value and r['budgetMin'] is None and r['budgetMax'] is None

def test_units_are_normalized_only_when_conversion_is_unambiguous():
 from app.shopping.selection import attribute_equal
 assert attribute_equal('1升','1000ml') and attribute_equal('1kW','1000瓦')
 assert not attribute_equal('256GB','512GB')

def test_java_brand_evidence_can_fill_absent_attribute_but_not_overwrite_conflict():
 p=product(brand='三星',price=6000);p['property_values']=[v for v in p['property_values'] if v['property_name']!='品牌']
 p['brand_evidence']={'value':'三星','source':'PRODUCT_NAME_PREFIX'}
 req=understand('5000以上的三星手机')['requirements']
 r=select([p],req);assert len(r['recommendations'])==1 and r['recommendations'][0]['brandEvidence']==p['brand_evidence']
 p['property_values'].append({'property_name':'品牌','property_value':'苹果'})
 assert not select([p],req)['recommendations']
 p['property_values']=[];p['brand_evidence']={'value':'三星','source':'MODEL_GUESS'}
 assert not select([p],req)['recommendations']

@pytest.mark.asyncio
async def test_engine_dispatches_specialist_not_mode_error(monkeypatch):
 from app.services import agent_engine
 from app.shopping import runner
 from app.supervisor import runner as supervisor
 shop=AsyncMock();sup=AsyncMock();support=AsyncMock()
 monkeypatch.setattr(runner,'run_shopping_agent',shop);monkeypatch.setattr(supervisor,'run_supervisor',sup);monkeypatch.setattr(agent_engine,'run_agent_graph',support)
 with agent_user_context('A','fixture'):
  msg={'userId':'A','messageId':33,'userMessage':'推荐5000以上的三星手机','agentMode':'support'}
  await agent_engine.agent_engine.assistant_answer(msg)
  assert msg['agentMode']=='shopping';shop.assert_awaited_once();sup.assert_not_awaited();support.assert_not_awaited()

@pytest.mark.asyncio
async def test_failure_marker_is_db_failure_not_false_model_success(monkeypatch):
 from app.services import agent_service,agent_runtime
 monkeypatch.setattr(agent_service.agent_message_service,'complete_message',AsyncMock(side_effect=RuntimeError('SQL fault')))
 failure=AsyncMock();ordinary=AsyncMock();monkeypatch.setattr(agent_runtime,'push_persistence_error',failure);monkeypatch.setattr(agent_service.stream_service,'push_error',ordinary)
 await agent_service.agent_orchestrator._finish_error('A',33,'模型超时')
 failure.assert_awaited_once();ordinary.assert_not_awaited()

@pytest.mark.asyncio
async def test_keyword_delegates_shared_java_contract_and_paginated_ids(monkeypatch):
 import httpx
 from types import SimpleNamespace
 from unittest.mock import Mock
 from app.rag import retriever as module
 calls=[]
 def handle(req):
  calls.append(req)
  assert req.url.path=='/api/search/products'
  page='2' if 'pageNo=2' in req.content.decode() else '1'
  return httpx.Response(200,json={'status':'success','code':200,'data':{'pageTotal':2,'list':[{'productId':'P'+page}]}})
 cls=httpx.AsyncClient
 class Client(cls):
  def __init__(self,**kw):super().__init__(transport=httpx.MockTransport(handle),trust_env=False,**kw)
 monkeypatch.setattr(module.httpx,'AsyncClient',Client)
 monkeypatch.setattr(module,'get_settings',lambda:SimpleNamespace(java_web_url='http://127.0.0.1:8080',es_hosts='http://127.0.0.1:9200'))
 monkeypatch.setattr(module.circuit_registry,'get_or_create',lambda *a,**k:SimpleNamespace(allow_request=lambda:True,record_success=Mock(),record_failure=Mock()))
 assert await module.rag_retriever.search_product_keyword_ids('苹果手机',50)==['P1','P2']
 assert len(calls)==2
