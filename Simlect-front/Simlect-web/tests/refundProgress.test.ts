import test from 'node:test';
import assert from 'node:assert/strict';
import {caseFulfillmentGuidance} from '../src/utils/aftersalesCaseView.ts';
test('pending mock does not hide missing acceptance',()=>{
 assert.match(caseFulfillmentGuidance({state:'IN_PROGRESS',requestedType:'return_refund',fulfillment:{refundStatus:'PENDING',logisticsStatus:'REGISTERED'}}),/登记验收/);
});
test('pending is not failure or bank settlement and honors capability',()=>{
 const row={state:'IN_PROGRESS',requestedType:'return_refund',fulfillment:{refundStatus:'PENDING',acceptance:'ACCEPTED'}};
 assert.match(caseFulfillmentGuidance(row),/尚未执行，不是退款失败或资金到账/);
 assert.match(caseFulfillmentGuidance(row),/未启用或尚无法确认/);
 assert.match(caseFulfillmentGuidance({...row,capabilities:{mockRefundEnabled:true}}),/登记结果/);
});
