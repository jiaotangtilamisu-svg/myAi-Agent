import test from 'node:test';
import assert from 'node:assert/strict';
import { caseGuidance,caseOperationError,caseTimelineNote,applicationDraft,applicationPayload } from '../src/utils/aftersalesCaseView.ts';
test('every state has an actionable consumer instruction',()=>{
 for(const s of ['AWAITING_USER','ADMIN_REVIEW','REJECTED','MANUAL_PENDING','IN_PROGRESS','PROCESSING_FAILED','RESOLVED','ARCHIVED']) assert.ok(caseGuidance(s).length>12);
 assert.match(caseGuidance('ADMIN_REVIEW'),/无需重复提交/);
 assert.match(caseGuidance('RESOLVED'),/不等于资金到账/);
 assert.match(caseGuidance('other'),/核实/);
});

test('editing draft preserves both evidence descriptions and requested type',()=>{
 const draft=applicationDraft({applicationReason:'屏幕损坏',applicationMaterials:['照片说明','沟通记录'],requestedType:'refund'});
 assert.deepEqual(JSON.parse(applicationPayload(draft.reason,draft.materials,draft.requestedType)),{reason:'屏幕损坏',materials:['照片说明','沟通记录'],requestedType:'refund'});
 for(const type of ['unsupported-type','REAL',''])assert.throws(()=>applicationPayload('原因',[],type));
 assert.throws(()=>applicationPayload('原因',['x'.repeat(351)],'refund'));
 assert.match(caseGuidance('CANCELLED'),/订单和资金未变更/);
});
test('refund timeout audit never implies settled funds',()=>{
 assert.match(caseTimelineNote({action:'TIMEOUT_MOCK_REFUND',note:'{"status":"UNKNOWN"}'}),/结果未知.*不代表真实资金/);
});
test('cancel is not an operation failure and raw error cannot leak',()=>{
 assert.equal(caseOperationError('cancel'),'');assert.equal(caseOperationError('close'),'');
 assert.match(caseOperationError({response:{status:409}}),/已被更新/);
 assert.ok(!caseOperationError({info:'internal-secret'}).includes('internal-secret'));
});

test('structured application and tracking audit is shown as consumer text',()=>{
 assert.equal(caseTimelineNote({action:'CONFIRM',note:JSON.stringify({reason:'屏幕损坏',materials:['说明'],orderStatus:2})}),'申请原因：屏幕损坏');
 assert.match(caseTimelineNote({action:'USER_RETURN_LOGISTICS',note:JSON.stringify({carrier:'TEST',trackingNo:'TEST12345'})}),/TEST12345/);
 assert.match(caseTimelineNote({action:'MOCK_REFUND',note:JSON.stringify({status:'SUCCEEDED'})}),/不代表真实资金到账/);
 assert.ok(!caseTimelineNote({action:'OTHER',note:'{"internal":"hidden"}'}).includes('internal'));
});
