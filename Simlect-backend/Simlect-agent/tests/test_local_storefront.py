from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.shopping.requirements import understand
from app.shopping.selection import select
from app.services.product_facts import normalize_product,render_facts
from app.services.data_provenance import classification
from app.services.product_search_query import normalize_product_search_query,filter_products_by_query_relevance
from app.services import product_service as module

def item(stock=100,price='19.90',approved=True):
 return normalize_product({'product_id':'ABOB0853X2F4M','product_name':'Solimo 木纹手机壳（适用三星 Galaxy J7）','status':1,
  'min_price':price,'max_price':price,'category_name':'手机壳','category_id':'A311','sku_complete':True,
  'data_provenance':{'source_type':'PUBLIC_DATASET','source_name':'本商城商品目录','catalogue_status':'LOCAL_STORE' if approved else None,
   'field_sources':{'price':'MANUAL','sku':'MANUAL','stock':'SYNTHETIC'}},
  'skus':[{'sku_id':'8479ccd48da12bf8771c8538c16df615','sku_name':'规格：木纹','price':price,'stock':stock,
   'stock_query_status':'SUCCESS' if stock is not None else 'MISSING','specifications':[{'name':'规格','value':'木纹'}]}]})

@pytest.mark.parametrize('text',['帮我推荐手机壳','搜索手机壳','手机保护壳'])
def test_case_intent_never_becomes_phone(text):
 assert understand(text)['requirements']['category']=='手机壳'
 assert normalize_product_search_query(text) in {'手机壳','手机保护壳'}

def test_approved_local_products_are_recommendable_without_claiming_supplier_reality():
 p=item();assert classification(p['data_provenance'])=='LOCAL_STORE'
 assert len(select([p],understand('推荐20元以内的手机壳')['requirements'],data_mode='LOCAL_STORE')['recommendations'])==1
 assert not select([p],understand('推荐手机壳')['requirements'],data_mode='REAL')['recommendations']

def test_unapproved_dataset_stays_excluded():
 assert not select([item(approved=False)],understand('推荐手机壳')['requirements'],data_mode='LOCAL_STORE')['recommendations']

def test_stock_zero_unknown_and_missing_price_are_not_invented():
 req=understand('推荐20元以内的手机壳')['requirements']
 assert not select([item(stock=0)],req,data_mode='LOCAL_STORE')['recommendations']
 unknown=select([item(stock=None)],req,data_mode='LOCAL_STORE')['recommendations'][0]
 assert unknown['eligibleSkus'][0]['stock'] is None
 assert not select([item(price=None)],req,data_mode='LOCAL_STORE')['recommendations']

def test_phone_request_never_returns_phone_cases():
 assert not select([item()],understand('推荐手机')['requirements'],data_mode='LOCAL_STORE')['recommendations']

def test_case_relevance_does_not_accept_unrelated_phone():
 rows=[item(),{'product_name':'三星智能手机'}]
 assert filter_products_by_query_relevance(rows,'手机壳')==rows[:1]

def test_consumer_product_copy_has_no_raw_sku_hash_or_unregistered_source_diagnostics():
 text=render_facts({'products':[item()],'queryStatus':'SUCCESS'})
 assert '8479ccd48da12bf8771c8538c16df615' not in text
 assert '业务数据来源未登记' not in text
 assert '库存100' in text and '19.90' in text

@pytest.mark.asyncio
async def test_local_recall_has_no_embedding_call(monkeypatch):
 import app.config.settings as settings
 monkeypatch.setattr(settings,'get_settings',lambda:SimpleNamespace(shopping_data_mode='LOCAL_STORE'))
 keyword=AsyncMock(return_value=['ABOB0853X2F4M']);vector=AsyncMock(side_effect=AssertionError('paid embedding forbidden'))
 monkeypatch.setattr(module.rag_retriever,'search_product_keyword_ids',keyword)
 monkeypatch.setattr(module.rag_retriever,'search_product_vector_ids',vector)
 service=module.ProductService();monkeypatch.setattr(service,'_load_products_by_ids',AsyncMock(return_value=[item()]))
 result=await service.search_products('A','手机壳')
 assert result[3];vector.assert_not_awaited();keyword.assert_awaited_once()
