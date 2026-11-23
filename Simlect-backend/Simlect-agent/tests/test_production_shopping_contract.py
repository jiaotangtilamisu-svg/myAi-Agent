from app.shopping.requirements import understand
from app.shopping.selection import select
from tools.quality_engineering.fixtures import product
import pytest

@pytest.mark.parametrize('q,low,high,exclusive',[('推荐8000以上的手机','8000',None,False),('推荐8000元以上的手机','8000',None,False),('预算8000元以上的手机','8000',None,False),('预算八千元起的手机','8000',None,False),('推荐高于8000元的手机','8000',None,True),('推荐8000到10000元的手机','8000','10000',False),('推荐预算3000元以内的手机',None,'3000',False)])
def test_complete_price_boundaries(q,low,high,exclusive):
 r=understand(q)['requirements'];assert (r['budgetMin'],r['budgetMax'],r['budgetMinExclusive'])==(low,high,exclusive)

def test_five_turn_requirement_chain_preserves_bounds_and_replaces_brand():
 r=understand('推荐8000以上的手机')['requirements']
 for q in ('最好是苹果','最好有512GB存储','价格提高到10000元以上','不要苹果，换成华为'):
  parsed=understand(q,r);assert not parsed['clarification'];r=parsed['requirements']
 assert r['category']=='手机' and r['budgetMin']=='10000' and r['budgetMax'] is None
 assert r['brands']==['华为'] and '苹果' in r['excludeBrands'] and '苹果' not in r['preferredBrands']
 assert r['preferredAttributes']['存储容量']=='512GB'
 r=understand('只推荐有现货的商品',r)['requirements'];assert r['requireInStock'] and r['category']=='手机' and r['keyword']=='手机'

@pytest.mark.parametrize('q',['预算8000mAh的手机','预算8GB的手机','预算256GB的手机','预算8gb的手机','不低于八千mah的手机','低于256gb的手机','高于8000 mAh的手机'])
def test_memory_battery_units_are_not_money(q):
 r=understand(q)['requirements'];assert r['budgetMin'] is None and r['budgetMax'] is None

def test_minimum_is_filtered_at_same_sku_with_inclusion():
 rows=[product('A',price=7999),product('B',price=8000),product('C',price=8001)]
 assert [p['productId'] for p in select(rows,understand('8000元以上的手机')['requirements'])['recommendations']]==['B','C']
 assert [p['productId'] for p in select(rows,understand('高于8000元的手机')['requirements'])['recommendations']]==['C']

def test_ram_and_storage_are_separate_attributes():
 r=understand('推荐8GB内存和256GB存储的手机')['requirements']
 assert r['attributes']['内存']=='8GB' and r['attributes']['存储容量']=='256GB'
 assert r['budgetMax'] is None

def test_every_canonical_category_is_a_valid_query_not_only_aliases():
 from app.shopping.requirements import CATEGORIES
 for name in CATEGORIES:
  result=understand('推荐'+name)
  assert result['requirements']['category']==name and not result['clarification']
 r=understand('我想买一款轻薄、续航好的笔记本')['requirements']
 assert r['category']=='笔记本' and set(r['preferences'])>={'轻薄','续航'}

@pytest.mark.asyncio
async def test_grounded_model_cannot_silently_harden_soft_preferences(monkeypatch):
 from types import SimpleNamespace
 from unittest.mock import AsyncMock
 from app.shopping import extraction
 model=SimpleNamespace(ainvoke=AsyncMock(return_value={'slots':[{'field':'brand','value':'苹果','quote':'苹果'},{'field':'attribute','name':'存储容量','value':'512GB','quote':'512GB'}]}))
 monkeypatch.setattr(extraction,'create_chat_llm',lambda:SimpleNamespace(with_structured_output=lambda *a,**k:model))
 monkeypatch.setattr(extraction,'get_settings',lambda:SimpleNamespace(shopping_requirement_llm_enabled=True))
 previous=understand('推荐8000以上的手机')['requirements']
 r=(await extraction.extract('最好是苹果，最好有512GB存储',previous))['requirements']
 assert r['brands']==[] and r['preferredBrands']==['苹果'] and r['attributes']=={} and r['preferredAttributes']['存储容量']=='512GB' and r['budgetMin']=='8000'
