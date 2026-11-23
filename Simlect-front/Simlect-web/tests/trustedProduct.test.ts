import test from 'node:test';
import assert from 'node:assert/strict';
import { knownMoney, priceText, skuPrice, knownStock, stockText, purchasableSku } from '../src/utils/trustedProduct.ts';
test('unknown money does not become free while zero stays known',()=>{for(const v of [null,undefined,'',NaN,true,-1]){assert.equal(knownMoney(v),null);assert.equal(priceText(v),'价格未知')}assert.equal(priceText(0),'0.00')});
test('selected SKU missing price never borrows another SKU product minimum',()=>{assert.equal(skuPrice({propertyValueIds:'x',price:null},{minPrice:1}),null);assert.equal(skuPrice({propertyValueIds:'x',price:0},{minPrice:100}),0)});
test('known zero, absent stock and unavailable remain distinct',()=>{assert.equal(knownStock({stock:0,stockQueryStatus:'SUCCESS'}),0);assert.equal(knownStock({stock:null}),null);assert.equal(knownStock({stock:10,stockQueryStatus:'UNAVAILABLE'}),null);assert.equal(stockText({stock:null,stockQueryStatus:'UNAVAILABLE'}),'库存服务不可用')});
test('unknown facts block purchase guards; real free stock may pass',()=>{assert.equal(purchasableSku({propertyValueIds:'s',price:0,stock:2,stockQueryStatus:'SUCCESS'}),true);for(const v of [{price:null,stock:2},{price:1,stock:null},{price:1,stock:0}])assert.equal(purchasableSku({propertyValueIds:'s',...v}),false)});

test('non-numeric coercions cannot be displayed as prices',()=>{
 for(const value of [[],[0],['19.90'],{},new Date(0),'0x10','0b10','  '])assert.equal(knownMoney(value),null);
 assert.equal(knownMoney('19.90'),19.9);assert.equal(knownMoney(0),0);
});
