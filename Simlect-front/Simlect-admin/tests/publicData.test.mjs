import test from 'node:test';import assert from 'node:assert/strict';
import {priceRangeLabel,displayStock} from '../src/utils/productDisplay.mjs';
test('mobile price does not turn missing data into zero',()=>{assert.equal(priceRangeLabel({minPrice:null,maxPrice:null}),'价格未知');assert.equal(priceRangeLabel({minPrice:0,maxPrice:0}),'¥0.00')});
test('mobile real range is retained',()=>assert.equal(priceRangeLabel({minPrice:12.3,maxPrice:22.3}),'¥12.30~22.30'));
test('failed stock is not displayed as real zero',()=>assert.equal(displayStock(0,'UNAVAILABLE'),'库存服务不可用'));
