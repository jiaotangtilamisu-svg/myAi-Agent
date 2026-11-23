from copy import deepcopy
from datetime import datetime,timezone
from unittest.mock import AsyncMock
import pytest
from app.services.catalogue_source import CatalogueSourceAdapter,SourceApproval

NOW=datetime(2026,1,1,tzinfo=timezone.utc)
def setup():
 row={'sourceRecordId':'p','productName':'TEST ONLY phone','version':'v1','observedAt':NOW.isoformat(),'status':'ON_SALE','fieldEvidence':{k:'fixture evidence' for k in ('name','price','sku','stock')},'skus':[{'sourceSkuId':'s','price':'12.00','stock':0,'stockQueryStatus':'SUCCESS','specifications':{'颜色':'白'}}]}
 source=AsyncMock();source.read_products.return_value=[row]
 adapter=CatalogueSourceAdapter(approval=SourceApproval('fixture supplier','test authorization','https://example.invalid/docs','CNY'),source=source,bindings={('p','s'):('existing','existing-sku')},now=lambda:NOW)
 return adapter,source,row

@pytest.mark.asyncio
async def test_unconfigured_source_is_blocked():assert (await CatalogueSourceAdapter().read(['p']))['queryStatus']=='BLOCKED'

@pytest.mark.asyncio
async def test_existing_sku_zero_and_field_provenance():
 a,s,row=setup();r=await a.read(['p']);p=r['products'][0]
 assert p['skus'][0]['stock']==0 and p['skus'][0]['sku_id']=='existing-sku'
 assert p['data_provenance']['field_sources']['name']=='LIVE_API'
 assert p['data_provenance']['field_evidence']==row['fieldEvidence']
 s.read_products.assert_awaited_once_with(('p',))

@pytest.mark.asyncio
@pytest.mark.parametrize('stock_status',['UNKNOWN','UNAVAILABLE'])
async def test_failed_or_unknown_stock_never_becomes_zero(stock_status):
 a,s,row=setup();row['skus'][0]['stockQueryStatus']=stock_status
 r=await a.read(['p']);assert r['products'][0]['skus'][0]['stock'] is None

@pytest.mark.asyncio
async def test_unknown_price_is_not_zero():
 a,s,row=setup();row['skus'][0]['price']=None
 assert (await a.read(['p']))['products'][0]['skus'][0]['price'] is None

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['name_evidence','stale','unbound','duplicate','cross_product','nan','wrong_product'])
async def test_invalid_supplier_data_fails_closed(change):
 a,s,row=setup()
 if change=='name_evidence':row['fieldEvidence'].pop('name')
 if change=='stale':row['observedAt']='2025-01-01T00:00:00+00:00'
 if change=='unbound':a.bindings={}
 if change=='duplicate':row['skus'].append(deepcopy(row['skus'][0]))
 if change=='cross_product':
  extra=deepcopy(row['skus'][0]);extra['sourceSkuId']='other';row['skus'].append(extra);a.bindings[('p','other')]=('different-product','sku2')
 if change=='nan':row['skus'][0]['price']='NaN'
 if change=='wrong_product':row['sourceRecordId']='not-requested'
 assert (await a.read(['p']))=={'queryStatus':'INVALID_RESPONSE','products':[]}

@pytest.mark.asyncio
async def test_service_error_is_not_no_product():
 a,s,row=setup();s.read_products.side_effect=RuntimeError('private provider payload')
 assert (await a.read(['p']))['queryStatus']=='SERVICE_ERROR'
 s.read_products.side_effect=None;s.read_products.return_value=[]
 assert (await a.read(['p']))['queryStatus']=='NOT_FOUND'

@pytest.mark.asyncio
@pytest.mark.parametrize('field',['version','specifications'])
async def test_missing_source_version_or_structured_spec_fails_closed(field):
 a,s,row=setup()
 if field=='version':row['version']=None
 else:row['skus'][0]['specifications']={'color':{'unverified':'raw JSON'}}
 assert (await a.read(['p']))['queryStatus']=='INVALID_RESPONSE'
