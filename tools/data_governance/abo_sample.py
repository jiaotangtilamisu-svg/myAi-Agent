"""Normalize the bounded official ABO sample into existing isolated ETL contracts."""
import json,re,hashlib
from pathlib import Path
from .olist import canonical,digest

CATEGORIES={'CELLULAR_PHONE_CASE':'手机壳','DRINKING_CUP':'饮水杯','HEADPHONES':'耳机'}

def localized(values):
    if not isinstance(values,list):return None
    valid=[x for x in values if isinstance(x,dict) and isinstance(x.get('value'),str) and x['value'].strip()]
    return next((x['value'] for x in valid if x.get('language_tag')=='zh_CN'),None) or next((x['value'] for x in valid if str(x.get('language_tag','')).startswith('en')),None) or next((x['value'] for x in valid),None)

def inspect(directory):
    d=Path(directory);raw=(d/'sample.jsonl').read_bytes();meta=json.loads((d/'manifest.json').read_text(encoding='utf8'))
    if len(raw)>4*1024*1024 or meta['sampleSha256']!=hashlib.sha256(raw).hexdigest() or meta['license']!='CC-BY-4.0':raise ValueError('SAMPLE_INTEGRITY_FAILED')
    license_bytes=(d/'LICENSE-CC-BY-4.0.txt').read_bytes()
    if hashlib.sha256(license_bytes).hexdigest()!='419896aea50c15d6e40c5b4baf4bd346f78223b9a354c7357ad00262afdc08ec':raise ValueError('OFFICIAL_LICENSE_REQUIRED')
    records=[];seen=set();failures=[];counts={}
    for line in raw.decode('utf8').splitlines():
        x=json.loads(line);asin=x.get('item_id');domain=x.get('domain_name');name=localized(x.get('item_name'))
        types=[t.get('value') for t in x.get('product_type',[]) if isinstance(t,dict)]
        selected=[t for t in types if t in CATEGORIES]
        if not isinstance(asin,str) or not re.fullmatch('[A-Z0-9]{10}',asin) or not isinstance(domain,str) or not re.fullmatch(r'amazon\.[a-z.]+',domain) or not name or len(selected)!=1:
            failures.append('INVALID_ID_LABEL_OR_CATEGORY');continue
        if asin in seen:continue
        seen.add(asin);kind=selected[0];counts[kind]=counts.get(kind,0)+1
        payload={'sourceType':'PUBLIC_DATASET','sourceName':'Amazon Berkeley Objects','sourceId':asin,'sourceDomain':domain,
            'sourceUrl':'https://amazon-berkeley-objects.s3.amazonaws.com/index.html','originalListingUrl':'https://'+domain+'/dp/'+asin,
            'sourceVersion':meta['etag'],'collectedAt':meta['collectedAt'],'dataPeriod':None,'license':'CC-BY-4.0',
            'attribution':meta['attribution'],'productName':name,'category':CATEGORIES[kind],'originalProductType':kind,
            'brand':localized(x.get('brand')),'attributes':{k:localized(x.get(k)) for k in ('color','material','model_name')},
            'mainImageId':x.get('main_image_id'),'currentPrice':None,'historicalPrice':None,'originalCurrency':None,
            'stock':None,'stockStatus':'UNKNOWN','skus':None,'reviews':None,'purchasable':False}
        text=canonical(payload);records.append(('public_product',asin,text,digest(text)))
    version=digest(canonical([(x[1],x[3]) for x in records]))[:32]
    report={'dataset':'Amazon Berkeley Objects','version':version,'sourceType':'PUBLIC_DATASET','sourceUrl':'https://amazon-berkeley-objects.s3.amazonaws.com/index.html',
        'license':'CC-BY-4.0','currency':None,'fieldSources':{k:'PUBLIC_DATASET' for k in ('name','brand','category','attributes')},
        'batchId':'ABO31_'+version,'status':'VALID' if 100<=len(records)<=188 and len(counts)<=3 and not failures else 'INVALID',
        'products':len(records),'reviews':0,'categories':counts,'failures':failures,'rawSampleBytes':len(raw),
        'sourceCompressedBytesRead':meta['compressedBytesRead'],'purchasable':False,'priceKnown':0,'stockKnown':0,'attribution':meta['attribution']}
    return report,records

def main():
    import argparse
    from .cli import connect,verified_backup
    from .storage import apply_batch
    from .public_sample import rollback_batch
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,default=Path('data/public-catalogue/stage31/abo'));p.add_argument('--output',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--rollback');p.add_argument('--backup-manifest',type=Path);p.add_argument('--business-backup-manifest',type=Path)
    p.add_argument('--env-file',type=Path,default=Path('Simlect-backend/Simlect-agent/.env'));a=p.parse_args()
    if a.output.exists():raise ValueError('REPORT_EXISTS_PRESERVE_EVIDENCE')
    report,rows=inspect(a.input)
    if a.apply or a.rollback:
        if not a.backup_manifest or 'simlect_data_governance' not in verified_backup(a.backup_manifest).get('schemas',[]):raise ValueError('GOVERNANCE_BACKUP_REQUIRED')
        if not a.business_backup_manifest or not {'simlect_product','simlect_order','simlect_agent'}.issubset(verified_backup(a.business_backup_manifest).get('schemas',[])):raise ValueError('BUSINESS_BACKUP_REQUIRED')
        if report['status']!='VALID':raise ValueError('SAMPLE_QUALITY_FAILED')
        connection=connect(a.env_file)
        try:
            if a.rollback:report['importResult']=rollback_batch(connection,a.rollback)
            else:
                with connection.cursor() as c:
                    c.execute("SELECT source_name,original_id FROM source_record s JOIN etl_batch b ON s.batch_id=b.batch_id WHERE s.entity_type='public_product' AND b.status='COMMITTED'")
                    public=set(c.fetchall())|{('Amazon Berkeley Objects',r[1]) for r in rows}
                    c.execute('SELECT COUNT(*) FROM simlect_product.product_info');business=c.fetchone()[0]
                    if business+len(public)>200:raise ValueError('TOTAL_CATALOGUE_CAP_200')
                report['importResult']=apply_batch(connection,report,rows)
        finally:connection.close()
    a.output.write_text(canonical(report),encoding='utf8');print(canonical(report))

if __name__=='__main__':main()
