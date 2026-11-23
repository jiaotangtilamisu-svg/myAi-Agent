import pytest
from app.shopping.selection import select
from app.shopping.requirements import understand
from app.services.product_search_query import filter_products_by_query_relevance
from test_shopping_agent import product
from test_aftersales_policy_rag import setup
from app.rag import retriever

@pytest.mark.parametrize('name',['360行车记录仪手机WiFi互联','手机支架','手机互联监控摄像头','手机无线充电宝'])
def test_phone_mention_does_not_prove_phone_type(name):
    p=product(price=199);p['product_name']=name
    assert not select([p],understand('推荐3000以内的手机')['requirements'])['recommendations']
    assert not filter_products_by_query_relevance([p],'手机')

def test_car_category_is_not_phone_even_with_phone_title():
    p=product(price=199);p['product_name']='手机互联设备';p['category_name']='车载电器'
    assert not select([p],understand('推荐手机')['requirements'])['recommendations']

def test_actual_phone_still_eligible():
    assert len(select([product(price=1999)],understand('推荐3000以内的手机')['requirements'])['recommendations'])==1

@pytest.mark.asyncio
async def test_explicit_policy_browse_does_not_call_embedding(setup):
    result=await retriever.rag_retriever.search_policy('帮我查询一下售后政策',browse_topics=True)
    setup.embedding.assert_not_awaited()
    assert 'constant_score' in setup.post.await_args.kwargs['json']['query']
    assert setup.read.await_count==1  # Publication/version/hash verification retained.
    assert result['ranking']=='verified_exact_topic_browse'
