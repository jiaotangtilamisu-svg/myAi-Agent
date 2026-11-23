"""Regressions from the bounded real policy + shopping acceptance."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from app.shopping.requirements import understand
from app.shopping import extraction

def test_budget_and_available_catalogue_request_is_not_a_product_name():
    parsed=understand('推荐300元以内适合日常使用且有库存的商品')
    assert parsed['requirements']['keyword']==''
    assert parsed['requirements']['catalogBrowse'] is True
    assert parsed['requirements']['budgetMax']=='300'
    assert understand('搜索保温杯')['requirements']['keyword']=='保温杯'
    restored=understand('推荐300元以内适合日常使用且有库存的商品',{'attributes':{'库存状态':'有库存','颜色':'白色'}})
    assert restored['requirements']['attributes']=={'颜色':'白色'}

@pytest.mark.asyncio
async def test_model_stock_status_is_not_a_catalogue_attribute(monkeypatch):
    model=SimpleNamespace(ainvoke=AsyncMock(return_value={'slots':[{'field':'attribute','name':'库存状态','value':'有库存','quote':'有库存'}]}))
    monkeypatch.setattr(extraction,'create_chat_llm',lambda:SimpleNamespace(with_structured_output=Mock(return_value=model)))
    monkeypatch.setattr(extraction,'get_settings',lambda:SimpleNamespace(shopping_requirement_llm_enabled=True,llm_base_url='https://model.invalid'))
    result=await extraction.extract('推荐300元以内适合日常使用且有库存的商品')
    assert result['source']=='rules+grounded_llm'
    assert result['requirements']['attributes']=={}
