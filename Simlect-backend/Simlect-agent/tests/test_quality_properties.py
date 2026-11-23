"""Deterministic quality properties; no production I/O, corpus independent of parser."""
import json, random
from copy import deepcopy
from pathlib import Path
import pytest
from app.shopping.requirements import understand
from app.shopping.selection import select
from app.supervisor.routing import plan
from tools.quality_engineering.oracles import assert_shopping_result,assert_route,assert_policy_evidence,expected_simple_candidate_ids
from tools.quality_engineering.fixtures import product

CORPUS=json.loads((Path(__file__).resolve().parents[3]/'tools/quality_engineering/scenarios.json').read_text(encoding='utf-8-sig'))
@pytest.mark.parametrize('case',CORPUS['budgets'],ids=lambda c:c['id'])
def test_corpus_budget_equivalence(case):
    got=understand(case['text'])['requirements']
    for key,wanted in case['expected'].items():assert got[key]==wanted
@pytest.mark.parametrize('case',CORPUS['routes'],ids=lambda c:c['id'])
def test_routes_have_no_duplicate_agents(case):assert_route(plan(case['text']),case['agents'])
@pytest.mark.parametrize('text',[None,{},[],0,True,'x'*10001,'第'+'9'*5000+'个手机比较'])
def test_bad_requirement_input_clarifies_without_crashing(text):assert understand(text)['clarification']
@pytest.mark.parametrize('text',[None,{},[],0,True,'订单'*1001])
def test_bad_router_input_clarifies_without_tools(text):assert plan(text)['tasks']==[]
@pytest.mark.parametrize('text',['推荐-20以内的茶杯','预算-1元的耳机','尺寸10到20厘米的水杯'])
def test_negative_or_physical_dimensions_never_become_budget(text):
    r=understand(text)
    assert r['clarification'] or (r['requirements']['budgetMin'] is None and r['requirements']['budgetMax'] is None)
@pytest.mark.parametrize('state',[{'attributes':None},{'brands':None},{'budgetMax':'NaN'},{'attributes':[]},[]])
def test_corrupt_memory_never_silently_drops_constraints(state):assert understand('更便宜的',state)['clarification']

def test_seeded_sku_property_grid_against_independent_oracle():
    rng=random.Random(3101)
    for _ in range(160):
        cap=rng.choice([0,1,20,100,200]);rows=[]
        for i in range(5):
            p=product(str(i),price=rng.choice([None,0,1,20,199,200,201]),count=rng.choice([None,0,1,20]));rows.append(p)
        req=understand(f'预算{cap}以内的手机')['requirements'];req['requestedCount']=12;result=select(rows,req)
        assert_shopping_result(result,rows,ceiling=cap)
        assert {x["productId"] for x in result["recommendations"]}==expected_simple_candidate_ids(rows,cap)
        more=select(rows,{**req,'budgetMax':str(cap+1)})
        assert {p['productId'] for p in result['recommendations']} <= {p['productId'] for p in more['recommendations']}

def test_fuzz_unicode_is_reproducible_and_never_executes():
    rng=random.Random(3101);alphabet='手机耳机预算元内不{}[]<>\\\x00\nＡ１２٣９💰'
    for _ in range(150):
        s=''.join(rng.choice(alphabet) for _ in range(rng.randrange(1,90)))
        value=understand(s);assert isinstance(value['requirements'],dict)

def test_oracle_rejects_deliberately_corrupted_price_stock_and_policy():
    p=product(price=20,count=3);r=select([p],understand('手机')['requirements'])
    for field,value in [('price','0'),('stock',999)]:
        altered=deepcopy(r);altered['recommendations'][0]['eligibleSkus'][0][field]=value
        with pytest.raises(AssertionError):assert_shopping_result(altered,[p])
    h={'documentId':'D','revision':1,'chunkId':'C','source':'fixture','text':'fixture'};c={('D',1,'C'):{**h,'published':True,'effective':True}}
    assert_policy_evidence([h],c)
    with pytest.raises(AssertionError):assert_policy_evidence([h,h],c)
    with pytest.raises(AssertionError):assert_policy_evidence([{**h,'text':'invented'}],c)

@pytest.mark.parametrize('price',[[],[0],{},False,True])
def test_non_numeric_money_is_never_a_price(price):
    from app.services.product_facts import money
    assert money(price) is None

def test_boolean_sale_status_is_not_sale_approval():
    from app.services.product_facts import normalize_product
    assert normalize_product({'status':True,'skus':[]})['product_status']=='UNKNOWN'

def test_missing_or_duplicated_sku_ids_cannot_be_recommended():
    req=understand('手机')['requirements']
    for value in ['',None]:
        p=product();p['skus'][0]['sku_id']=value;assert not select([p],req)['recommendations']
    p=product();p['skus'].append(deepcopy(p['skus'][0]));assert not select([p],req)['recommendations']

def test_duplicate_product_facts_are_not_arbitrarily_chosen():
    p=product();q=deepcopy(p);q['skus'][0]['price']='999'
    assert not select([p,q],understand('手机')['requirements'])['recommendations']

@pytest.mark.parametrize('text,category',[('不要耳机，推荐手机','手机'),('不买手机，推荐耳机','耳机'),('推荐耳几','耳机'),('推荐手几','手机')])
def test_negated_category_and_common_typo(text,category):assert understand(text)['requirements']['category']==category
@pytest.mark.parametrize('baseline',[[None],[{'price':'NaN'}],[{'price':True}],{}])
def test_corrupt_baseline_is_a_clarification_not_a_guess(baseline):assert understand('更便宜的',{'category':'手机','keyword':'手机'},baseline)['clarification']

def test_independent_provenance_oracle_rejects_unverified_business_fields():
 p=product();p['data_provenance']={'source_type':'LIVE_API','source_name':'fixture-only','field_sources':{'price':'LIVE_API','sku':'LIVE_API','stock':'LIVE_API'}}
 req=understand('手机')['requirements'];result=select([p],req,data_mode='REAL');assert result['recommendations'];assert_shopping_result(result,[p],real_only=True)
 for key in ('price','sku','stock'):
  bad=deepcopy(p);bad['data_provenance']['field_sources'][key]='SYNTHETIC'
  assert not select([bad],req,data_mode='REAL')['recommendations']
  with pytest.raises(AssertionError):assert_shopping_result(result,[bad],real_only=True)

def test_seeded_multisku_offshelf_and_unknown_fault_grid():
 rng=random.Random(3102)
 for _ in range(80):
  p=product(price=rng.choice([None,0,20,201]),count=rng.choice([None,0,1]))
  second=deepcopy(p['skus'][0]);second['sku_id']='variant2';p['skus'].append(second)
  p['product_status']=rng.choice(['ON_SALE','OFF_SHELF','DELETED']);p['skus'][1]['stock_query_status']=rng.choice(['SUCCESS','UNAVAILABLE','INVALID_RESPONSE'])
  req=understand('200以内的手机')['requirements'];out=select([p],req);assert_shopping_result(out,[p],ceiling=200)

@pytest.mark.parametrize('state',[{'requestedCount':'NaN'},{'requestedCount':True},{'requireInStock':'false'},{'budgetMaxExclusive':1},{'keyword':{}},{'category':[]},{'categoryId':False}])
def test_all_persisted_constraint_field_types_fail_closed(state):assert understand('再看一下',state)['clarification']
def test_full_width_numbers_are_equivalent_budget_not_different_facts():
 assert understand('预算３０００元以内的手机')['requirements']['budgetMax']=='3000'

@pytest.mark.parametrize('raw',[None,0,19.9,'19.90','NaN',True,[],{},-1,'0x10'])
def test_normalizer_price_is_checked_against_raw_fixture_not_itself(raw):
 from app.services.product_facts import normalize_product
 from tools.quality_engineering.oracles import decimal_fact
 p=normalize_product({'product_id':'P','status':1,'min_price':raw,'max_price':raw,'skus':[{'sku_id':'S','price':raw,'stock':1,'stock_query_status':'SUCCESS'}]})
 assert decimal_fact(p['skus'][0]['price'])==decimal_fact(raw)
 assert decimal_fact(p['min_price'])==decimal_fact(raw)

@pytest.mark.parametrize('text',['不超过-10元的手机','价格-10到20元的耳机','-10到20元的茶杯'])
def test_all_explicit_negative_budget_forms_require_clarification(text):assert understand(text)['clarification']
