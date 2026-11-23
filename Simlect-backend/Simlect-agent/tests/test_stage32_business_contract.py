import json
from pathlib import Path
import pytest
from app.shopping.requirements import understand
from app.domain.aftersales_intent import classify,resolve
from app.supervisor.routing import plan

ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tools/quality_engineering/stage32/utterances.json').exists())
UTTERANCES=json.loads((ROOT/'tools/quality_engineering/stage32/utterances.json').read_text(encoding='utf8'))
DIALOGS=json.loads((ROOT/'tools/quality_engineering/stage32/dialogs.json').read_text(encoding='utf8'))

@pytest.mark.parametrize('case',UTTERANCES,ids=lambda c:c['text'])
def test_natural_language_contract(case):
    if case['kind']=='shopping':
        r=understand(case['text'])
        assert not r['clarification']
        req=r['requirements']
        assert (req['category'],req['brands'],req['budgetMin'],req['budgetMax'])==(case['category'],case['brands'],case['min'],case['max'])
        assert [t['agent'] for t in plan(case['text'])['tasks']]==['shopping']
    else:
        assert classify(case['text'])['operation']==case['operation']
        assert [t['agent'] for t in plan(case['text'])['tasks']]==['aftersales']

@pytest.mark.parametrize('dialog',DIALOGS,ids=lambda d:d['id'])
def test_multiturn_hard_constraints_are_preserved(dialog):
    previous={}
    for turn in dialog['turns']:
        r=understand(turn['text'],previous);assert not r['clarification']
        previous=r['requirements']
        assert previous['category']=='手机'
        assert (previous['budgetMin'],previous['budgetMax'],previous['brands'],previous['requireInStock'])==(turn['min'],turn['max'],[turn['brand']],turn['stock'])

def test_return_number_followup_preserves_purpose_without_selecting_other_orders():
    oid='202611011536325281K0gVGxDdIOERZy'
    text,intent=resolve(oid,{'businessIntent':'RETURN'})
    assert intent['operation']=='RETURN' and intent['orderId']==oid
    assert classify('我要退'+oid+'的货')['operation']=='RETURN'
    assert classify('订单号是'+oid+'，我想退货')['orderId']==oid
    second='202611011536325521K0gVGxDdIOERZz'
    assert classify('退货，订单'+oid+'和'+second)['ambiguousOrder']

def test_approximate_budget_needs_confirmed_bounds_not_invented_range():
    result=understand('预算8000左右的手机')
    assert result['clarification'] and result['requirements']['budgetTarget']=='8000'
    assert result['requirements']['budgetMin'] is None and result['requirements']['budgetMax'] is None

def test_soft_brand_does_not_override_previous_hard_brand():
    old=understand('三星手机，5000以上')['requirements']
    new=understand('最好是苹果',old)['requirements']
    assert new['brands']==['三星'] and new['preferredBrands']==['苹果'] and new['budgetMin']=='5000'
