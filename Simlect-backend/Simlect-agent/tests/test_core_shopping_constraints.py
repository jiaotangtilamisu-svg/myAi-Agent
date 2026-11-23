from copy import deepcopy
import pytest
from app.shopping.requirements import understand
from app.shopping.selection import select
from test_shopping_agent import product

@pytest.mark.parametrize('text',['推荐20以内的茶杯','推荐预算20元以内的茶杯','20块钱以下的茶杯'])
def test_equivalent_budgets(text):
 r=understand(text)['requirements'];assert r['category']=='茶杯' and r['budgetMax']=='20'

def test_soft_brand_is_not_hard_and_keeps_alternatives():
 req=understand('推荐3000以内的手机，优先华为')['requirements']
 assert req['brands']==[] and req['preferredBrands']==['华为']
 rows=select([product('B',brand='小米'),product('A',brand='华为')],req)['recommendations']
 assert len(rows)==2 and rows[0]['productId']=='A'
 assert rows[0]['score']['components']['preferredBrandMatches']==1

def test_explicit_brand_remains_hard():
 req=understand('推荐华为手机')['requirements'];assert req['brands']==['华为']
 assert not select([product(brand='小米')],req)['recommendations']

def test_required_inventory_excludes_unknown_but_optional_keeps_unknown():
 p=product(count=None);p['skus'][0]['stock_query_status']='UNAVAILABLE'
 assert select([p],understand('手机')['requirements'])['recommendations']
 assert not select([p],understand('手机必须有货')['requirements'])['recommendations']

@pytest.mark.parametrize('text,attrs',[('推荐不锈钢水杯',{'材质':'不锈钢'}),('推荐15.6英寸笔记本',{'尺寸':'15.6英寸'})])
def test_material_size_are_explicit_hard_constraints(text,attrs):
 req=understand(text)['requirements'];assert all(req['attributes'][k]==v for k,v in attrs.items())

def test_preferred_color_does_not_exclude_and_can_cancel():
 a=understand('推荐手机，优先白色')['requirements'];assert a['attributes']=={} and a['preferredAttributes']=={'颜色':'白色'}
 assert select([product(color='黑色')],a)['recommendations']
 b=understand('不限颜色',a)['requirements'];assert '颜色' not in b['preferredAttributes']

def test_multiturn_cancel_material_and_stock_keeps_category():
 a=understand('推荐必须有货的不锈钢水杯')['requirements']
 b=understand('取消材质，库存不限',a)['requirements'];assert b['category']=='水杯' and not b['attributes'] and not b['requireInStock']

def test_attribute_filtering_uses_same_sku_not_another_variant():
 p=product(category='水杯');p['skus'][0]['specifications'].append({'name':'材质','value':'玻璃'})
 req=understand('推荐不锈钢水杯')['requirements'];assert not select([p],req)['recommendations']

def test_colloquial_cup_and_brand_preference_not_hard():
 r=understand('20块钱以下有什么杯子')['requirements'];assert r['category']=='水杯' and r['budgetMax']=='20'
 r=understand('推荐手机，品牌偏好：华为')['requirements'];assert r['brands']==[] and r['preferredBrands']==['华为']
