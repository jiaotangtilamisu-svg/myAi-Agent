"""Regression for the actual 100 -> three -> 100-200 -> <=200 conversation."""
import pytest
from unittest.mock import AsyncMock
from app.shopping import graph
from app.shopping.requirements import understand
from app.shopping.selection import select
from app.shopping.runner import render
from app.services.product_search_query import filter_products_by_query_relevance
from test_shopping_agent import product, run


def headphones():
    return [product('HEAD1', price=89.9, category='耳机'),
            product('HEAD2', price=129.9, category='耳机'),
            product('CASE', price=19.9, category='手机壳')]


def test_new_recommendation_does_not_inherit_old_budget():
    old = understand('推荐100以内的耳机')['requirements']
    req = understand('我帮推荐三个耳机', old)['requirements']
    assert req['budgetMax'] is None and req['budgetMin'] is None
    assert req['requestedCount'] == 3
    assert len(select(headphones(), req)['recommendations']) == 2


def test_explicit_upper_range_replaces_previous_lower_bound():
    old = understand('推荐100-200元的耳机')['requirements']
    req = understand('预算改成200以内', old)['requirements']
    assert req['budgetMin'] is None and req['budgetMax'] == '200'
    assert len(select(headphones(), req)['recommendations']) == 2


def test_followup_colour_preserves_budget():
    old = understand('推荐100以内的耳机')['requirements']
    req = understand('刚才的耳机要白色', old)['requirements']
    assert req['budgetMax'] == '100' and req['attributes']['颜色'] == '白色'


@pytest.mark.parametrize('text,count', [('推荐一个耳机',1),('推荐两款耳机',2),('推荐三个耳机',3),('推荐20款耳机',12)])
def test_requested_count(text,count):
    assert understand(text)['requirements']['requestedCount'] == count


@pytest.mark.parametrize('text',['推荐三个耳机','推荐价格在200以内的耳机','推荐预算200元以内的耳机'])
@pytest.mark.asyncio
async def test_graph_returns_both_eligible_headsets(text,monkeypatch):
    monkeypatch.setattr(graph, 'is_cancelled', AsyncMock(return_value=False))
    result, tools = await run(text, headphones(), monkeypatch)
    assert {r['productId'] for r in result['recommendations']} == {'HEAD1','HEAD2'}
    assert tools.await_count == 2
    assert '不足所需' in render(result)


@pytest.mark.parametrize('query,expected', [('耳机',['H']),('耳机图案手机壳',['C'])])
def test_accessory_is_not_the_requested_device(query,expected):
    rows = [{'product_id':'H','product_name':'头戴式耳机'},
            {'product_id':'C','product_name':'耳机图案手机壳'}]
    assert [p['product_id'] for p in filter_products_by_query_relevance(rows,query)] == expected
