import test from 'node:test';import assert from 'node:assert/strict';
import {consumerProductCopy} from '../src/utils/consumerProductCopy.ts';
test('old product diagnostics are hidden without inventing stock or price',()=>{
 const out=consumerProductCopy('业务数据来源未登记\nSKU 8479ccd48da12bf8771c8538c16df615 透明：价格未知；库存未知。');
 assert.equal(out,'规格 透明：价格未知；库存未知。');
});
test('legal citations and genuine unknowns remain intact',()=>{
 const text='来源：消费者权益保护法第二十五条\n价格19.90元；库存0。\n该商品是否适用仍待核实。';
 assert.equal(consumerProductCopy(text),text);
});
