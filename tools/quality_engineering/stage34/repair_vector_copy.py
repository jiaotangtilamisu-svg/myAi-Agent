"""Copy existing ES9 vectors into the SAME isolated 61 docs. No embeddings."""
import json
from .copy_policy import request, validate_vectors, RUN, p as PLAN
from .verify_es_readonly import canonical

def main():
    source='http://127.0.0.1:9200';guard='http://127.0.0.1:19200';index=PLAN['vectorIndex']
    assert index=='q34_'+PLAN['runId']+'_vectors'
    query={'size':100,'_source':{'exclude_vectors':False},'query':{'term':{'metadata.documentId.keyword':'f85d1c36-053a-430b-a05f-e9ce88810e99'}}}
    docs=request(source,'simlect_vectorstore/_search','POST',query)['hits']['hits'];validate_vectors(docs)
    copied=request(guard,index+'/_search','POST',query)['hits']['hits']
    assert {d['_id'] for d in docs}=={d['_id'] for d in copied}
    without_vectors=lambda rows:[{**d,'_source':{k:v for k,v in d['_source'].items() if k!='embedding'}} for d in rows]
    assert canonical(without_vectors(docs))==canonical(without_vectors(copied))
    backup=RUN/'policy-copy-before-vector-repair.json'
    if not backup.exists():backup.write_text(json.dumps(copied,ensure_ascii=False),encoding='utf8')
    changed=0
    if canonical(docs)!=canonical(copied):
        body=b''.join((json.dumps({'update':{'_index':index,'_id':d['_id']}})+'\n'+json.dumps({'doc':{'embedding':d['_source']['embedding']}})+'\n').encode() for d in docs)
        result=request(guard,'_bulk?refresh=true','POST',body)
        assert result.get('errors') is False;changed=len(docs)
    final=request(guard,index+'/_search','POST',query)['hits']['hits'];validate_vectors(final)
    check=request(source,'simlect_vectorstore/_search','POST',query)['hits']['hits']
    assert canonical(docs)==canonical(final)==canonical(check)
    record={'index':index,'copiedExistingVectors':changed,'chunks':61,'dimensions':1024,
            'formalSourceReadOnly':True,'formalSourceSHA256Before':canonical(docs),'formalSourceSHA256After':canonical(check),
            'isolatedSHA256':canonical(final),'textMetadataSHA256':canonical(without_vectors(docs)),
            'realEmbeddingCalls':0,'formalWrites':0,'newDocumentIds':0,'idempotent':True}
    (RUN/'policy-vector-copy-repair.json').write_text(json.dumps(record,indent=2),encoding='utf8');print(json.dumps(record))

if __name__=='__main__':main()
