"""Bounded CC0 product-model sample; never creates sellable products, SKUs or stock."""
import argparse
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from .olist import canonical, digest
from .storage import apply_batch
from .cli import connect, verified_backup

CATEGORIES={'Q22645':('手机',100),'Q186819':('耳机',30)}
MAX_BYTES=1024*1024

def fetch_sample(directory, only=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for qid,(label,limit) in CATEGORIES.items():
        if only and qid!=only:continue
        file=directory/f'{qid}.json'
        if file.exists():continue
        query=f'''SELECT ?item ?itemLabel ?manufacturerLabel ?modified WHERE {{
 {{ SELECT DISTINCT ?item WHERE {{ ?item wdt:P31 wd:{qid} }} ORDER BY ?item LIMIT {limit} }}
 OPTIONAL {{ ?item wdt:P176 ?manufacturer }} OPTIONAL {{ ?item schema:dateModified ?modified }}
 SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh,en". }} }}'''
        url='https://query.wikidata.org/sparql?'+urllib.parse.urlencode({'query':query,'format':'json'})
        request=urllib.request.Request(url,headers={'User-Agent':'SimlectLocalDataset/31 (bounded non-commercial product research)','Accept':'application/sparql-results+json'})
        with urllib.request.urlopen(request,timeout=25) as response:
            if int(response.headers.get('Content-Length','0'))>MAX_BYTES:raise ValueError('DOWNLOAD_TOO_LARGE')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('DOWNLOAD_TOO_LARGE')
        data=json.loads(raw)
        if not isinstance(data.get('results',{}).get('bindings'),list):raise ValueError('INVALID_DATASET_RESPONSE')
        file.write_bytes(raw)
        file.with_suffix('.provenance.json').write_text(canonical({'url':url,'sha256':digest(raw.decode()),'bytes':len(raw),'collectedAt':datetime.now(timezone.utc).isoformat(),'license':'CC0-1.0','category':label}),encoding='utf8')


def inspect(directory):
    rows=[];seen=set();failures=[];bytes_read=0
    for qid,(category,limit) in CATEGORIES.items():
        file=Path(directory)/f'{qid}.json'
        if not file.exists():continue
        raw=file.read_bytes();bytes_read+=len(raw)
        if len(raw)>MAX_BYTES:raise ValueError('DOWNLOAD_TOO_LARGE')
        provenance=json.loads(file.with_suffix('.provenance.json').read_text(encoding='utf8'))
        if provenance['sha256']!=digest(raw.decode()) or provenance['license']!='CC0-1.0':raise ValueError('UNVERIFIED_SOURCE')
        count=0
        for row in json.loads(raw)['results']['bindings']:
            item=row.get('item',{}).get('value','');name=row.get('itemLabel',{}).get('value','')
            if not re.fullmatch(r'https?://www.wikidata.org/entity/Q[1-9]\d*',item) or not name or re.fullmatch('Q[0-9]+',name):
                failures.append('MISSING_ID_OR_LABEL');continue
            rid=item.rsplit('/',1)[-1]
            if rid in seen:continue
            if count>=limit:break
            seen.add(rid);count+=1
            payload={'sourceType':'PUBLIC_DATASET','sourceName':'Wikidata product models','sourceId':rid,
                'sourceUrl':'https://www.wikidata.org/wiki/'+rid,'sourceVersion':provenance['sha256'],
                'collectedAt':provenance['collectedAt'],'dataPeriod':row.get('modified',{}).get('value'),
                'license':'CC0-1.0','productName':name,'category':category,
                'brand':row.get('manufacturerLabel',{}).get('value'),
                'currentPrice':None,'historicalPrice':None,'originalCurrency':None,'stock':None,
                'stockStatus':'UNKNOWN','skus':None,'reviews':None,'purchasable':False}
            text=canonical(payload);rows.append(('public_product',rid,text,digest(text)))
    version=digest(canonical([(r[1],r[3]) for r in rows]))[:32]
    report={'dataset':'Wikidata product models','version':version,'sourceType':'PUBLIC_DATASET',
        'sourceUrl':'https://www.wikidata.org/','license':'CC0-1.0','currency':None,
        'fieldSources':{k:'PUBLIC_DATASET' for k in ('name','category','brand')},
        'batchId':'WD31_'+version,'status':'VALID' if 100<=len(rows)<=130 else 'INVALID',
        'products':len(rows),'reviews':0,'downloadBytes':bytes_read,'failures':failures,
        'purchasable':False,'historicalPriceKnown':0,'stockKnown':0}
    return report,rows


def rollback_batch(connection,batch,*,sqlite=False):
    if not re.fullmatch(r'(?:WD31|ABO31)_[a-f0-9]{32}',batch):raise ValueError('OWN_PUBLIC_BATCH_REQUIRED')
    db=getattr(connection,'db',b'');db=db.decode() if isinstance(db,bytes) else db
    if not sqlite and db!='simlect_data_governance':raise ValueError('ISOLATED_SCHEMA_REQUIRED')
    cur=connection.cursor();ph='?' if sqlite else '%s'
    try:
        cur.execute('SELECT dataset,status,report_json FROM etl_batch WHERE batch_id='+ph+('' if sqlite else ' FOR UPDATE'),(batch,))
        row=cur.fetchone()
        if not row or row[0] not in {'Wikidata product models','Amazon Berkeley Objects'}:raise ValueError('OWN_PUBLIC_BATCH_REQUIRED')
        audit=json.loads(row[2]);audit.setdefault('lifecycle',[]).append({'action':'SOFT_ROLLBACK','at':datetime.now(timezone.utc).isoformat()})
        cur.execute('UPDATE etl_batch SET status='+ph+',report_json='+ph+' WHERE batch_id='+ph,('ROLLED_BACK',canonical(audit),batch))
        connection.commit();return {'status':'ROLLED_BACK','deleted':0,'preservedForAudit':True}
    except Exception:connection.rollback();raise
    finally:cur.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path('data/public-catalogue/stage31'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--fetch',action='store_true');p.add_argument('--apply',action='store_true')
    p.add_argument('--rollback');p.add_argument('--backup-manifest',type=Path);p.add_argument('--env-file',type=Path,default=Path('Simlect-backend/Simlect-agent/.env'))
    a=p.parse_args()
    if a.fetch:fetch_sample(a.input)
    if a.apply or a.rollback:
        if not a.backup_manifest or 'simlect_data_governance' not in verified_backup(a.backup_manifest).get('schemas',[]):raise ValueError('GOVERNANCE_BACKUP_REQUIRED')
    if a.rollback:
        c=connect(a.env_file)
        try:result=rollback_batch(c,a.rollback)
        finally:c.close()
    else:
        result,rows=inspect(a.input)
        if a.apply:
            if result['status']!='VALID':raise ValueError('INVALID_SAMPLE_SIZE')
            c=connect(a.env_file)
            try:result['importResult']=apply_batch(c,result,rows)
            finally:c.close()
    a.output.write_text(canonical(result),encoding='utf8');print(canonical(result))

if __name__=='__main__':main()
