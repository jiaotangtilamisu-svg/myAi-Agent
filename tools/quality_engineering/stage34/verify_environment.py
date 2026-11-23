"""Readiness gate based on actual service connections and enforced test namespaces."""
import asyncio
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.quality_engineering.stage34.isolation import mysql,docker
RUN=Path(json.loads((ROOT/'.cache/stage34/active.json').read_text())['directory'])
p=json.loads((RUN/'plan.json').read_text())
c=json.loads((RUN/'private.json').read_text())


def get(path,port=18080,body=None,headers=None,method=None):
    data=None if body is None else json.dumps(body).encode('utf8')
    req=urllib.request.Request('http://127.0.0.1:'+str(port)+path,data=data,headers={'Content-Type':'application/json',**(headers or {})},method=method)
    try:
        with urllib.request.urlopen(req,timeout=15) as response:return response.status,json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code,json.loads(exc.read())


def main():
    checks=[]
    for role in ['user','product','stock','order','search','admin','cart']:
        user=c['serviceDbUsers'][role]['user'];expected=p['databases'][role]
        rows=mysql("SELECT DISTINCT PROCESSLIST_DB FROM performance_schema.threads WHERE PROCESSLIST_USER='"+user+"' AND PROCESSLIST_DB IS NOT NULL;")
        assert rows==[expected],(role,'REAL_DATASOURCE_MISMATCH',rows)
        grants=mysql("SHOW GRANTS FOR '"+user+"'@'%';")
        assert all('simlect_' not in x for x in grants)
        attrs=mysql("SELECT DISTINCT a.ATTR_VALUE FROM performance_schema.session_connect_attrs a JOIN performance_schema.threads t ON a.PROCESSLIST_ID=t.PROCESSLIST_ID WHERE t.PROCESSLIST_USER='"+user+"' AND a.ATTR_NAME='quality34_service';")
        assert attrs==[role],(role,'JDBC_CONNECTION_ATTRIBUTE_MISSING',attrs)
        code,status=get('/actuator/health',p['ports'][role]);assert code==200 and status['status']=='UP'
        checks.append({'role':role,'database':expected,'principal':user,'actualConnectionAttribute':attrs,'health':'UP'})
    for role in ['gateway','mcp','agent','guard']:
        code,body=get('/quality34/health' if role=='guard' else '/health' if role in {'mcp','agent'} else '/actuator/health',p['ports'][role])
        assert code==200 and body['status'] in {'ok','UP'},(role,body.get('status'))
        if role=='agent':assert body.get('java_web') is True
        if role=='guard':assert not body['paidEnabled'] and all(v==0 for v in body['counts'].values())
        checks.append({'role':role,'health':body['status']})
    conns=docker(['exec','simlect-rabbitmq','rabbitmqctl','list_connections','user','vhost']).splitlines()
    actual=[s.split('\t') for s in conns if s.startswith(c['mqUser']+'\t')]
    assert len(actual)>=6 and all(row[1]==p['rabbitVhost'] for row in actual)
    permission=docker(['exec','simlect-rabbitmq','rabbitmqctl','list_user_permissions',c['mqUser']])
    assert p['rabbitVhost'] in permission
    assert docker(['exec',p['redisContainer'],'redis-cli','PING'])=='PONG'
    mounts=json.loads(docker(['inspect',p['redisContainer'],'--format','{{json .Mounts}}']))
    formal_mounts=json.loads(docker(['inspect','simlect-redis','--format','{{json .Mounts}}']))
    # Official Redis images declare VOLUME /data and create an anonymous volume.
    # It must be a new test-only volume, never a production mount or host bind.
    assert all(m['Type']=='volume' and all(m['Source']!=f['Source'] for f in formal_mounts) for m in mounts)
    # No application-level or anonymous fallback into DEFAULT_GROUP.
    for role in ['user','product','stock','order','search','admin','cart','gateway']:
        query=urllib.parse.urlencode({'serviceName':'simlect-'+role,'groupName':p['nacosGroup'],'namespaceId':''})
        url='http://127.0.0.1:8848/nacos/v1/ns/instance/list?'+query
        with urllib.request.urlopen(url,timeout=10) as response:hosts=json.loads(response.read())['hosts']
        active=[x for x in hosts if x.get('healthy') and x.get('enabled')]
        assert len(active)==1 and active[0]['port']==p['ports'][role],(role,'NACOS_GROUP_NOT_ISOLATED')
    # Verify dangerous defaults are refused by the proxy before an ES write.
    code,_=get('/simlect-index/_doc/QUALITY34_DENIED',19200,{},method='PUT')
    assert code==403
    headers={'X-Internal-Token':c['internalToken']}
    ids=mysql('SELECT product_id FROM `'+p['databases']['product']+'`.product_info ORDER BY product_id;')
    code,result=get('/internal/search/tool/refreshKeywordIndex',18108,{'productIds':ids},headers)
    assert code==200 and result.get('code')==200,result.get('info')
    # Public search form contract; product truth must come from this test DB.
    req=urllib.request.Request('http://127.0.0.1:18080/api/search/products',data=urllib.parse.urlencode({'keyWords':'苹果手机'}).encode())
    with urllib.request.urlopen(req,timeout=15) as response:result=json.loads(response.read())
    found={x['productId'] for x in result['data']['list']}
    assert found=={'DEMO34A1','DEMO34A2'},found
    code,facts=get('/internal/product/agent/queryBatch',18080,{'productIds':['DEMO34A1']},headers)
    assert code==200 and facts.get('code')==200
    item=facts['data']['products'][0]
    assert item['productId']=='DEMO34A1' and item['brandEvidence']['value']=='苹果'
    assert len(item['skus'])==2 and [s['stock'] for s in item['skus']]==[10,11]
    report={'isolated':True,'productionBusinessWrites':0,'realLlmCalls':0,'realEmbeddingCalls':0,'checks':checks,'rabbitConnections':len(actual),'nacosGroup':p['nacosGroup'],'redisContainer':p['redisContainer'],'redisTestOnlyVolumes':[m['Name'] for m in mounts],'productIndex':p['productIndex'],'vectorIndex':p['vectorIndex'],'testProductIds':sorted(found),'guardRefusedFormalWrite':True}
    (RUN/'isolation-verified.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print('Isolation gate passed:',len(checks),'service checks; actual DB/MQ/Nacos/index namespaces verified.')


if __name__=='__main__':main()
