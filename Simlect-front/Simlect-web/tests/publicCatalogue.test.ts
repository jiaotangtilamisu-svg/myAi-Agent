import test from 'node:test';import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {historicalPriceLabel,publicSourceUrl,syntheticDemoPrice} from '../src/utils/publicCatalogue.ts';
test('unknown price never becomes zero',()=>{assert.equal(historicalPriceLabel(null,'CNY'),'历史价格未知');assert.equal(historicalPriceLabel('','USD'),'历史价格未知')});
test('USD history is not yuan and real zero is preserved',()=>{assert.equal(historicalPriceLabel('10','USD'),'USD 10.00（历史采集，非当前售价）');assert.match(historicalPriceLabel(0,'USD'),/0.00/)});
test('invalid source cannot create javascript or credential link',()=>{assert.equal(publicSourceUrl('javascript:alert(1)'),undefined);assert.equal(publicSourceUrl('https://secret:password@example.com'),undefined)});
test('synthetic demonstration price is stable and never mutates source facts',()=>{const p={sourceType:'PUBLIC_DATASET',sourceName:'Amazon Berkeley Objects',sourceId:'B0853X2F4M',originalProductType:'CELLULAR_PHONE_CASE',currentPrice:null,purchasable:false};const value=syntheticDemoPrice(p);assert.ok([19.9,29.9,39.9].includes(value!));assert.equal(syntheticDemoPrice(p),value);assert.equal(p.currentPrice,null);assert.equal(p.purchasable,false)});
test('test price cannot be injected into non-ABO records',()=>assert.equal(syntheticDemoPrice({sourceType:'LIVE_API',sourceName:'supplier',sourceId:'x'}),null));
test('all 100 saved synthetic prices match the page calculation and remain non-commercial',()=>{
  const base=new URL('../../../data/public-catalogue/stage31/abo/',import.meta.url);
  const rows=readFileSync(new URL('sample.jsonl',base),'utf8').trim().split('\n').map(line=>JSON.parse(line));
  const saved=JSON.parse(readFileSync(new URL('test-prices.json',base),'utf8')).prices;
  assert.equal(saved.length,100);assert.equal(new Set(saved.map((row:any)=>row.sourceId)).size,100);
  for(const row of rows){
    const id=row.item_id;
    const price=saved.find((entry:any)=>entry.sourceId===id);
    assert.ok(price,`missing synthetic price for ${id}`);
    const type=Array.isArray(row.product_type)?row.product_type[0].value:row.product_type;
    assert.equal(syntheticDemoPrice({sourceType:'PUBLIC_DATASET',sourceName:'Amazon Berkeley Objects',sourceId:id,originalProductType:type}),price.testPriceCents/100);
    assert.equal(price.sourceType,'SYNTHETIC');assert.equal(price.purchasable,false);assert.equal(price.currency,'CNY');
  }
});
