import test from 'node:test'
import assert from 'node:assert/strict'
import {availableCaseActions,caseCommand,fulfillmentNote,availableRefundActions,refundWorkflowGuide} from '../src/utils/caseManagement.mjs'
test('user confirmation cannot be performed by admin',()=>assert.deepEqual(availableCaseActions('AWAITING_USER'),[]))
test('review and manual retry are distinct',()=>{assert.deepEqual(availableCaseActions('ADMIN_REVIEW'),['approve','reject']);assert.deepEqual(availableCaseActions('PROCESSING_FAILED'),['retry'])})
test('commands carry expected version and idempotency key, never user role',()=>assert.deepEqual(caseCommand({caseId:'case',version:3,userId:'spoof'},'request',' reviewed '),{caseId:'case',expectedVersion:3,requestId:'request',note:'reviewed'}))
test('invalid and absent version fail closed',()=>{for(const version of [0,NaN,1.1,'1'])assert.throws(()=>caseCommand({caseId:'case',version},'request','note'))})
test('terminal states cannot execute work',()=>assert.deepEqual(availableCaseActions('ARCHIVED'),[]))

test('tracking only accepts return-refund with actual tracking',()=>{
 assert.throws(()=>fulfillmentNote('returnLogistics',{type:'refund'}));
 assert.throws(()=>fulfillmentNote('returnLogistics',{type:'return_refund',carrier:'Test',trackingNo:'bad'}));
 const p=JSON.parse(fulfillmentNote('returnLogistics',{type:'return_refund',carrier:'Test',trackingNo:'TEST12345'}));assert.equal(p.trackingNo,'TEST12345');
});
test('manual exception and mock failure require explanation, not real execution',()=>{
 assert.throws(()=>fulfillmentNote('returnProgress',{type:'return_refund',logisticsStatus:'EXCEPTION'}));
 assert.throws(()=>fulfillmentNote('simulateRefund',{type:'refund',simulateFailure:true}));
 const p=JSON.parse(fulfillmentNote('simulateRefund',{type:'refund',simulateFailure:true,result:'TEST failure',executionAllowed:true,refundId:'forged'}));assert.equal(p.simulateFailure,true);assert.equal(p.executionAllowed,undefined);assert.equal(p.refundId,undefined);
});

test('punctuation cannot masquerade as return tracking',()=>assert.throws(()=>fulfillmentNote('returnLogistics',{type:'return_refund',carrier:'TEST',trackingNo:'-----'})))
test('refund phase controls prevent blind timeout retry and early case success',()=>{
 assert.deepEqual(availableCaseActions('IN_PROGRESS',{requestedType:'refund',refundStatus:'NOT_EXECUTED'}),['fail']);
 assert.deepEqual(availableRefundActions({refundStatus:'UNKNOWN'}),['completeMockRefund']);
 assert.deepEqual(availableRefundActions({refundStatus:'SUCCEEDED'}),[]);
 assert.deepEqual(availableRefundActions({refundStatus:'FAILED'}),['prepareRefund']);
 assert.deepEqual(availableRefundActions({refundStatus:'PENDING',type:'return_refund',acceptance:'REJECTED'}),[]);
 assert.deepEqual(availableRefundActions({refundStatus:'PROCESSING'}),['completeMockRefund','timeoutMockRefund']);
 for(const status of ['PENDING','PROCESSING','UNKNOWN','FAILED'])assert.deepEqual(availableCaseActions('IN_PROGRESS',{refundStatus:status}),['fail']);
});
test('receipt and result registration require explicit evidence, never coercion',()=>{
 assert.throws(()=>fulfillmentNote('acceptReturn',{type:'return_refund',accepted:true,result:'TEST',received:false}));
 assert.throws(()=>fulfillmentNote('completeMockRefund',{type:'refund',simulateFailure:'false',result:'TEST'}));
 assert.throws(()=>fulfillmentNote('timeoutMockRefund',{type:'refund'}));
 const n=JSON.parse(fulfillmentNote('acceptReturn',{type:'return_refund',accepted:true,result:'TEST',received:true,condition:'INTACT',evidenceRefs:['TEST-warehouse-1']}));
 assert.equal(n.received,true);assert.deepEqual(n.evidenceRefs,['TEST-warehouse-1']);
});
test('prepared refund cannot hide a missing return acceptance',()=>{
 const g=refundWorkflowGuide({state:'IN_PROGRESS',requestedType:'return_refund',fulfillment:{logisticsStatus:'REGISTERED',refundStatus:'PENDING'}});
 assert.match(g.title,/验收/);assert.match(g.description,/重复登记物流不会完成验收/);
});
test('mock capability is explicit and cannot be inferred from pending status',()=>{
 const row={state:'IN_PROGRESS',requestedType:'return_refund',fulfillment:{logisticsStatus:'REGISTERED',acceptance:'ACCEPTED',refundStatus:'PENDING'}};
 assert.match(refundWorkflowGuide(row).title,/未启用/);
 assert.match(refundWorkflowGuide({...row,capabilities:{mockRefundEnabled:false}}).title,/未启用/);
 assert.match(refundWorkflowGuide({...row,capabilities:{mockRefundEnabled:true}}).title,/开始本地模拟/);
});
test('unknown refund and local success never claim bank settlement',()=>{
 assert.match(refundWorkflowGuide({state:'IN_PROGRESS',requestedType:'refund',fulfillment:{refundStatus:'UNKNOWN'}}).description,/不能盲目重试/);
 const g=refundWorkflowGuide({state:'IN_PROGRESS',requestedType:'refund',fulfillment:{refundStatus:'SUCCEEDED'}});
 assert.match(g.description,/不是支付渠道资金到账/);assert.match(g.description,/原订单/);
});
