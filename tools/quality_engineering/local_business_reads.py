"""Opt-in local integration. Public reads only; not authenticated chat E2E.

Run with the existing Agent runtime Python from project root. No paid APIs.
Supervisor notifications and model advice are explicitly mocked. Memory writes
use one random test namespace and only its known keys are removed afterwards.
"""
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.cache/productionization-20261105/local-business-reads.json'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Simlect-backend/Simlect-agent'))
os.environ['SHOPPING_DATA_MODE'] = 'LOCAL_STORE'
os.environ['SHOPPING_REQUIREMENT_LLM_ENABLED'] = 'false'
os.chdir(ROOT / 'Simlect-backend/Simlect-agent')
import httpx

calls = []
original_send = httpx.AsyncClient.send
async def local_send(client, request, *args, **kwargs):
    if request.url.host not in {'127.0.0.1', 'localhost', '::1'}:
        raise AssertionError('EXTERNAL_API_FORBIDDEN')
    calls.append({'path': request.url.path, 'method': request.method})
    return await original_send(client, request, *args, **kwargs)
httpx.AsyncClient.send = local_send

from app.auth.agent_context import agent_user_context
from app.shopping.graph import build_shopping_graph
from app.services.redis_service import redis_service
from app.services.stream_service import stream_service
from app.supervisor.graph import build_supervisor_graph
from app.rag import advice
from tools.quality_engineering.oracles import assert_shopping_result

async def main():
    user = 'QUALITYPROD_' + uuid.uuid4().hex
    checks = []
    output = {'scope':'HYBRID_LOCAL_PUBLIC_READS_NOT_LOGIN_OR_BROWSER_E2E', 'realLlmCalls':0,
              'realEmbeddingCalls':0, 'messagePersistence':'NOT_EXERCISED', 'checks':checks}
    await redis_service.connect()
    mid = 2100032010
    try:
        async with httpx.AsyncClient() as client:
            health=(await client.get('http://127.0.0.1:7050/health')).json()
            assert health['status']=='ok' and health['java_web'] is True
            assert health['catalogue']['mode']=='LOCAL_STORE' and health['catalogue']['llmRequirementParsing'] is False
        previous={}
        with agent_user_context(user, 'public-product-read-fixture-not-an-authenticated-session'):
            for n,q in enumerate(['推荐8000以上的手机','最好是苹果','最好有512GB存储','价格提高到10000元以上','不要苹果，换成华为','只推荐有现货的商品']):
                s=await build_shopping_graph().ainvoke({'user_id':user,'message_id':mid+n,'text':q,'previous':previous})
                r=s['result'];req=r['requirements']
                assert r['status'] in {'SUCCESS','NO_MATCHING_SKU','NO_RESULTS'}, r['status']
                assert req['category']=='手机' and req['budgetMin']==('8000' if n<3 else '10000')
                assert req['budgetMax'] is None
                assert_shopping_result(r,s.get('products',[]),floor=req['budgetMin'],in_stock=req['requireInStock'])
                if n>=2:assert req['preferredAttributes']['存储容量']=='512GB'
                if n>=4:assert req['brands']==['华为'] and '苹果' in req['excludeBrands']
                checks.append({'question':q,'status':r['status'],'requirements':req,'productIds':[p['productId'] for p in r['recommendations']], 'tools':r['toolsCalled']})
                previous={'requirements':req,'ids':[p['productId'] for p in r['recommendations']], 'baseline':[{'price':p['price']['min']} for p in r['recommendations']]}
            s=await build_shopping_graph().ainvoke({'user_id':user,'message_id':mid+7,'text':'推荐三个3000元以内的手机','previous':{}})
            r=s['result'];ids=[p['productId'] for p in r['recommendations']]
            assert len(ids)==3
            assert_shopping_result(r,s['products'],ceiling=3000)
            prior={'requirements':r['requirements'],'ids':ids,'baseline':[{'price':p['price']['min']} for p in r['recommendations']]}
            s=await build_shopping_graph().ainvoke({'user_id':user,'message_id':mid+8,'text':'比较第一款和第二款手机','previous':prior})
            assert [p['productId'] for p in s['result']['comparison']]==ids[:2] and s['result']['toolsCalled']==['GET_PRODUCT_DETAIL']
            checks.append({'question':'三款手机召回后按序号比较前两款','status':'PASS','candidateIds':ids,'comparedIds':ids[:2]})
            s=await build_shopping_graph().ainvoke({'user_id':user,'message_id':mid+9,'text':'我想买一款轻薄、续航好的笔记本','previous':{}})
            r=s['result'];assert r['requirements']['category']=='笔记本' and 'SEARCH_PRODUCTS' in r['toolsCalled']
            assert r['status'] in {'SUCCESS','NO_MATCHING_SKU','NO_RESULTS'}
            assert_shopping_result(r,s.get('products',[]))
            checks.append({'question':'我想买一款轻薄、续航好的笔记本','status':r['status'],'requirements':r['requirements'],'tools':r['toolsCalled'],'productIds':[p['productId'] for p in r['recommendations']]})
            with patch.object(stream_service,'push_agent_status',AsyncMock()), patch.object(advice,'policy_advice',AsyncMock(return_value={'status':'NOT_CALLED','executionAllowed':False})):
                s=await build_supervisor_graph().ainvoke({'user_id':user,'message_id':mid,'text':'查询售后政策，另外推荐3000元以内的手机','context':{}})
                report=s['report'];assert set(report['results'])=={'shopping','aftersales'}
                assert all(v['status']=='SUCCESS' for v in report['results'].values())
                assert report['results']['aftersales']['data']['policy']['hits']
                checks.append({'question':'政策及商品复合任务','status':'PASS','agentStatuses':{k:v['status'] for k,v in report['results'].items()},'policyChunkIds':[h.get('chunkId') for h in report['results']['aftersales']['data']['policy']['hits']], 'mocked':['policy_model_advice','status_transport']})
        output['passed']=len(checks);output['failed']=0
    except Exception as exc:
        output['passed']=len(checks);output['failed']=1;output['failureType']=type(exc).__name__
        raise
    finally:
        keys=['mall:agent:shopping:'+user, 'mall:agent:shopping:'+user+':lock','mall:agent:shopping:'+user+':result:'+str(mid),'mall:agent:aftersales:supervisor:'+user]
        assert all(user in k for k in keys)
        await redis_service.client.delete(*keys)
        output['testNamespaceRemoved']=not any([await redis_service.client.exists(k) for k in keys])
        output['businessRequests']=calls
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        await redis_service.close()
        print(json.dumps({'passed':output['passed'],'failed':output['failed'],'output':str(OUT)}))

if __name__=='__main__':
    asyncio.run(main())
