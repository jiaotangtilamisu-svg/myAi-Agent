"""Source mutation in memory only: never edits production files or executes services."""
import inspect,json,textwrap
from pathlib import Path
from app.services.product_facts import money,stock
from app.shopping.selection import select
from app.shopping.requirements import understand
from app.rag.policy import catalog_eligible
from app.services.refund_execution_policy import deny_agent_refund_execution
from app.services.mode_routing import effective_mode
from tools.quality_engineering.oracles import assert_shopping_result,expected_simple_candidate_ids
from tools.quality_engineering.fixtures import product

def mutated(fn,before,after):
    src=textwrap.dedent(inspect.getsource(fn));assert before in src,'MUTANT_LOCATION_CHANGED'
    ns=fn.__globals__.copy();exec(compile(src.replace(before,after,1),'<quality-mutant>','exec'),ns)
    return ns[fn.__name__]

def price_check(fn):assert fn(-1) is None

def stock_check(fn):assert fn(-1) is None

def budget_check(fn):
    p=product(price=201,count=2);r=fn([p],understand('200以内的手机')['requirements']);assert_shopping_result(r,[p],ceiling=200)

def zero_check(fn):
    p=product(price=20,count=0);assert_shopping_result(fn([p],understand('手机')['requirements']),[p])

def policy_check(fn):assert not fn({'category':'LAW','sourceStatus':'VALID','effectiveFrom':'2020-01-01T00:00:00Z','effectiveUntil':'2020-02-01T00:00:00Z'})

def refund_check(fn):
    try:fn()
    except ValueError:return
    raise AssertionError('REFUND_GUARD_MISSING')

def recall_check(fn):
    p=product(price=20,count=3);r=fn([p],understand('200以内的手机')['requirements'])
    assert {x['productId'] for x in r['recommendations']}==expected_simple_candidate_ids([p],200)

def lower_check(fn):
    rows=[product('A',price=7999),product('B',price=8000),product('C',price=8001)]
    result=fn(rows,understand('8000元以上的手机')['requirements'])
    assert {p['productId'] for p in result['recommendations']}=={'B','C'}
    assert_shopping_result(result,rows,floor=8000)

def strict_lower_check(fn):
    rows=[product('B',price=8000),product('C',price=8001)]
    assert [p['productId'] for p in fn(rows,understand('高于8000元的手机')['requirements'])['recommendations']]==['C']

def soft_brand_check(fn):
    rows=[product('B',brand='小米'),product('A',brand='苹果')]
    result=fn(rows,understand('推荐手机，优先苹果')['requirements'])
    assert [p['productId'] for p in result['recommendations']]==['A','B']

def mode_check(fn):
    assert fn('推荐5000以上的三星手机','support')=='shopping'
    assert fn('查询订单物流','shopping')=='support'
    assert fn('查询售后政策并推荐手机','support')=='supervisor'

cases=[('empty-recall',select,'recommendations[:min(12, max(1, int(req.get("requestedCount", 3))))]','[]',recall_check),('negative-price' ,money,'number >= 0','True',price_check),('negative-stock',stock,'value >= 0','True',stock_check),('budget-upper',select,'Decimal(price) > Decimal(','Decimal(price) < Decimal(',budget_check),('zero-stock',select,'count == 0','False',zero_check),('expired-policy',catalog_eligible,'now < end','True',policy_check),('agent-refund',deny_agent_refund_execution,'raise ValueError(REFUND_ADVICE_ONLY_MESSAGE)','return None',refund_check)]
cases.extend([('budget-lower',select,'Decimal(price) < Decimal(','Decimal(price) > Decimal(',lower_check),('strict-lower-bound',select,'req.get("budgetMinExclusive")','False',strict_lower_check),('brand-preference-order',select,'int(any(matches_brand(b)','int(not any(matches_brand(b)',soft_brand_check)])
cases.append(('shopping-mode-routing',effective_mode,"if shopping:return 'shopping'","if shopping:return 'support'",mode_check))
rows=[]
for name,fn,a,b,oracle in cases:
    oracle(fn) # baseline must pass before calling a mutant killed.
    try:oracle(mutated(fn,a,b))
    except AssertionError:rows.append({'id':name,'status':'KILLED'})
    except Exception as exc:rows.append({'id':name,'status':'ERROR','errorType':type(exc).__name__})
    else:rows.append({'id':name,'status':'SURVIVED'})
out={'scope':'explicit Python source mutants; not whole-project mutation coverage','mutants':rows,'killed':sum(r['status']=='KILLED' for r in rows),'survived':sum(r['status']=='SURVIVED' for r in rows),'errors':sum(r['status']=='ERROR' for r in rows)}
Path(__import__('os').environ['QUALITY_MUTATION_OUTPUT']).write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out));raise SystemExit(0 if out['killed']==len(rows) else 1)
