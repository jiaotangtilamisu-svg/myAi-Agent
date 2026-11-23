"""Actual ES checks using existing vector copies. NOT a new Embedding test."""
import hashlib
import json
import sys
from pathlib import Path
from .copy_policy import request, p as PLAN, RUN, ROOT

def canonical(rows):
    return hashlib.sha256(json.dumps(sorted([{'id':d['_id'],'source':d['_source']} for d in rows],key=lambda d:d['id']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def main():
    base='http://127.0.0.1:19200';index=PLAN['vectorIndex'];doc='f85d1c36-053a-430b-a05f-e9ce88810e99'
    query={'size':100,'_source':{'exclude_vectors':False},'query':{'term':{'metadata.documentId.keyword':doc}}}
    source=request('http://127.0.0.1:9200','simlect_vectorstore/_search','POST',query)['hits']['hits']
    copied=request(base,index+'/_search','POST',query)['hits']['hits']
    before=json.loads((RUN/'policy-copy.json').read_text())
    assert len(source)==len(copied)==61 and canonical(source)==canonical(copied)
    without_vectors=[{**d,'_source':{k:v for k,v in d['_source'].items() if k!='embedding'}} for d in source]
    assert canonical(without_vectors)==before['sourceSHA256']
    item=next(h for h in copied if '退货' in h['_source'].get('content',''))
    vector=item['_source']['embedding'];assert len(vector)==1024 and any(vector)
    dense=request(base,index+'/_search','POST',{'size':5,'knn':{'field':'embedding','query_vector':vector,'k':5,'num_candidates':10,'filter':{'term':{'metadata.documentId.keyword':doc}}}})['hits']['hits']
    assert dense[0]['_id']==item['_id'] and dense[0]['_score']>0.999
    lexical=request(base,index+'/_search','POST',{'size':10,'query':{'bool':{'filter':[{'term':{'metadata.documentId.keyword':doc}}],'must':[{'match_phrase':{'content':'退货'}}]}}})['hits']['hits']
    assert lexical and all('退货' in h['_source']['content'] for h in lexical)
    sys.path.insert(0,str(ROOT/'Simlect-backend/Simlect-agent'))
    from app.rag.rrf import rrf_merge
    merged=rrf_merge([h['_id'] for h in lexical],[h['_id'] for h in dense],10)
    assert merged and len(merged)==len(set(merged))
    result={'scope':'Actual isolated ES keyword/vector self-similarity + shared RRF; not semantic query embedding or Agent full hybrid acceptance',
            'realEmbeddingCalls':0,'reembeddedPolicyChunks':0,'officialVectors':61,'officialSHA256':canonical(source),'isolatedCopySHA256':canonical(copied),
            'dimension':len(vector),'selfSimilarityTopChunk':item['_source']['metadata']['chunkId'],'selfSimilarityScore':dense[0]['_score'],
            'keywordHits':len(lexical),'vectorHits':len(dense),'rrfUniqueResults':len(merged),'passed':True}
    (RUN/'es-readonly-proof.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
