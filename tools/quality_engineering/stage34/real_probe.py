"""One bounded real embedding batch for two synthetic products, test index only.

Never embeds the 61 law chunks again. No direct provider credentials or retries.
All paid traffic goes through the existing opt-in four/six-request guard.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[3]
RUN=Path(json.loads((ROOT/'.cache/stage34/active.json').read_text())['directory'])
PLAN=json.loads((RUN/'plan.json').read_text())

def main():
    output=RUN/'real-product-embedding.json'
    if output.exists():
        raise RuntimeError('REAL_PROBE_ALREADY_ATTEMPTED_NO_REPEAT')
    if (RUN/'api-stopped.json').exists() or not (RUN/'enable-real.json').exists():
        raise RuntimeError('REAL_PHASE_NOT_ENABLED')
    record={'kind':'REAL_PRODUCT_EMBEDDING','mock':False,'automaticRetries':0,'productIds':['DEMO34S1','DEMO34S2'],'policyChunksReembedded':0}
    output.write_text(json.dumps({**record,'status':'STARTED_NO_RETRY'}))
    settings=json.loads((RUN/'environment-private.json').read_text())['agent']
    # Service identity only; never a browser login token or user's credentials.
    with httpx.Client(timeout=25,trust_env=False,follow_redirects=False) as client:
        reply=client.post('http://127.0.0.1:18080/internal/product/agent/queryBatch',headers={'X-Internal-Token':settings['SIMLECT_INTERNAL_TOKEN']},json={'productIds':record['productIds']})
        reply.raise_for_status()
        payload=reply.json()
        assert payload.get('code')==200 and isinstance(payload.get('data'),list)
        products=payload['data']
        assert {p['productId'] for p in products}==set(record['productIds'])
        texts=[p['productName']+'；这是隔离测试商品，非真实商业库存。' for p in products]
        response=client.post('http://127.0.0.1:19200/embedding/v1/embeddings',headers={'Authorization':'Bearer quality34-local-proxy'},json={'model':'text-embedding-v4','input':texts,'dimensions':1024,'encoding_format':'float'})
        record['http']=response.status_code
        if response.status_code != 200:
            record['status']='FAILED_STOPPED';output.write_text(json.dumps(record,ensure_ascii=False,indent=2));return False
        body=response.json(); vectors=sorted(body['data'],key=lambda row:row['index'])
        assert len(vectors)==2
        for product,text,row in zip(products,texts,vectors):
            vector=row['embedding']
            assert len(vector)==1024 and all(type(v) in (int,float) and math.isfinite(v) for v in vector) and any(vector)
            doc={'content':text,'embedding':vector,'metadata':{'dataType':'product','productId':product['productId'],'source':'QUALITY34_SYNTHETIC','batchId':PLAN['runId']}}
            saved=client.put('http://127.0.0.1:19200/'+PLAN['vectorIndex']+'/_doc/quality34-product-'+product['productId'],json=doc,params={'refresh':'true'})
            saved.raise_for_status()
        record.update(status='SUCCESS',model=body.get('model','text-embedding-v4'),dimension=1024,vectorDocuments=2,usage=body.get('usage'),index=PLAN['vectorIndex'],sourceTextSHA256=hashlib.sha256('\n'.join(texts).encode()).hexdigest())
        output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
        print(json.dumps(record,ensure_ascii=False))
        return True

if __name__=='__main__':
    raise SystemExit(0 if main() else 1)
