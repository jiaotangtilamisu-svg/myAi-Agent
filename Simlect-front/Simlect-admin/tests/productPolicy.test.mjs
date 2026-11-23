import test from 'node:test'
import assert from 'node:assert/strict'
import { firstCover, coverList, skuReadValues, displayAmount, displayStock } from '../src/utils/productDisplay.mjs'
import { availableActions, categories, utcValue } from '../src/utils/policyManagement.mjs'
test('null/empty covers select fallback; first nonempty image preserved',()=>{for(const v of [null,undefined,'',', '])assert.equal(firstCover(v),'');assert.equal(firstCover(', a.png,b.png'),'a.png')})
test('zero price is known; null/nonfinite price is unknown',()=>{assert.equal(displayAmount(0),'0.00');assert.equal(displayAmount(12.3),'12.30');for(const v of [null,undefined,NaN,Infinity,-1])assert.equal(displayAmount(v),'未知')})
test('zero, unknown and unavailable stocks remain distinct',()=>{assert.equal(displayStock(0,'SUCCESS'),'0');assert.equal(displayStock(null,'MISSING'),'库存未知');assert.equal(displayStock(null,'UNAVAILABLE'),'库存服务不可用')})
test('unreviewed drafts and pending documents cannot show publish',()=>{assert.deepEqual(availableActions({state:'DRAFT'}),['submit']);assert(!availableActions({state:'PENDING_REVIEW',approved:false}).includes('publish'));assert(availableActions({state:'PENDING_REVIEW',approved:true,reviewedRevision:2,revision:2}).includes('publish'))})
test('disabled documents preserve reversible enable; retired immutable',()=>{assert(availableActions({state:'DISABLED'}).includes('enable'));assert.deepEqual(availableActions({state:'RETIRED'}),[])})
test('policy classification separates industry and platform demo',()=>{assert.match(categories.INDUSTRY_REFERENCE,/非商城规则/);assert.match(categories.PLATFORM_DEMO,/演示/);assert.equal(utcValue('2026-01-01T08:00:00+08:00'),'2026-01-01T00:00:00.000Z')})
test('SKU regeneration preserves unknowns and outage state; real zeros retained',()=>{assert.deepEqual(coverList(null),[]);assert.deepEqual(coverList(' ,a,b'),['a','b']);const unknown=skuReadValues({price:null,stock:null,stockQueryStatus:'UNAVAILABLE'});assert.equal(unknown.price,null);assert.equal(unknown.stock,null);assert.equal(unknown.stockQueryStatus,'UNAVAILABLE');assert.equal(skuReadValues({price:0,stock:0}).stock,0)})
