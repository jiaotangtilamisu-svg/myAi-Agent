"""Copy approved public vectors verbatim to a guarded test index, no embedding."""
import hashlib
import json
from .vector_contract import validate_vectors
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[3]
RUN=Path(json.loads((ROOT/'.cache/stage34/active.json').read_text())['directory'])
p=json.loads((RUN/'plan.json').read_text())


def request(base,path,method='GET',body=None):
    data=None if body is None else body if isinstance(body,bytes) else json.dumps(body).encode('utf8')
    req=urllib.request.Request(base+'/'+path,method=method,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.loads(response.read())


def main():
    source='http://127.0.0.1:9200'
    guard='http://127.0.0.1:19200'
    mapping=request(source,'simlect_vectorstore/_mapping')['simlect_vectorstore']['mappings']
    docs=request(source,'simlect_vectorstore/_search','POST',{'size':100,'_source':{'exclude_vectors':False},'query':{'term':{'metadata.documentId.keyword':'f85d1c36-053a-430b-a05f-e9ce88810e99'}}})['hits']['hits']
    validate_vectors(docs)  # ES9 excludes vectors from _source unless explicitly requested.
    canonical=lambda rows: hashlib.sha256(json.dumps(sorted([{'id':d['_id'],'source':d['_source']} for d in rows],key=lambda d:d['id']),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    request(guard,p['vectorIndex'],'PUT',{'mappings':mapping,'settings':{'number_of_shards':1,'number_of_replicas':0}})
    prodmap=request(source,'simlect-index/_mapping')['simlect-index']['mappings']
    request(guard,p['productIndex'],'PUT',{'mappings':prodmap,'settings':{'number_of_shards':1,'number_of_replicas':0}})
    body=b''.join((json.dumps({'index':{'_index':p['vectorIndex'],'_id':d['_id']}})+'\n'+json.dumps(d['_source'],ensure_ascii=False)+'\n').encode('utf8') for d in docs)
    result=request(guard,'_bulk?refresh=true','POST',body)
    assert result.get('errors') is False
    copied=request(guard,p['vectorIndex']+'/_search','POST',{'size':100,'_source':{'exclude_vectors':False},'query':{'match_all':{}}})['hits']['hits']
    validate_vectors(copied)
    assert len(copied)==61 and canonical(copied)==canonical(docs)
    (RUN/'policy-copy.json').write_text(json.dumps({'chunks':61,'sourceSHA256':canonical(docs),'copySHA256':canonical(copied),'realEmbeddingCalls':0,'sourceReadOnly':True,'index':p['vectorIndex']},indent=2),encoding='utf8')
    print('Copied 61 public law vectors verbatim; no embedding; SHA256 equal.')


if __name__=='__main__':
    main()
