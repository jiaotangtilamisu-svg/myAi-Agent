import test from 'node:test';
import assert from 'node:assert/strict';
import {uniquePolicyHits,parsePolicyAnswer} from '../src/utils/agentPolicy.ts';
import {productOriginLabel} from '../src/utils/dataProvenance.ts';
import {applicationPayload} from '../src/utils/aftersalesCaseView.ts';
import {quickQuestions} from '../src/utils/agentCapabilities.ts';

test('policy duplicate chunks are collapsed but continuation text is preserved',()=>{
 const h={documentId:'fixture',revision:1,chunkId:'one',section:'第二条',source:'fixture://policy',documentName:'TEST',text:'第一段条款'};
 const rows=uniquePolicyHits([h,{...h},{...h,chunkId:'two'},{...h,chunkId:'three',text:'第二段条款'}]);
 assert.deepEqual(rows.map(r=>r.chunkId),['one','three']);
 assert.equal(rows[1].text,'第二段条款');
 assert.equal(parsePolicyAnswer({kind:'policy_answer',hits:[h,{...h,text:'冲突条款'}]},1),null);
});
test('consumer provenance distinguishes local catalogue and public facts without internal enum leakage',()=>{
 assert.match(productOriginLabel({dataClass:'LOCAL_STORE'}),/本地配置/);
 assert.match(productOriginLabel({dataClass:'LOCAL_STORE',dataProvenance:{sourceType:'PUBLIC_DATASET'}}),/不代表来源商家实时/);
 assert.equal(productOriginLabel({dataClass:'UNKNOWN'}),'商品资料来源待核实');
});
test('manual exchange proposal is not a refund execution instruction',()=>{
 const p=JSON.parse(applicationPayload('尺码不合适',['证据编号 TEST'],'exchange'));
 assert.equal(p.requestedType,'exchange');assert.equal(p.executionAllowed,undefined);
});
test('all modes retain usable questions and support has explicit return and progress entrances',()=>{
 for(const mode of ['support','shopping','supervisor'] as const)assert.ok(quickQuestions(mode).length>=3);
 assert.ok(quickQuestions('support').includes('我要退货'));
 assert.ok(quickQuestions('support').includes('查看售后申请进度'));
 assert.ok(quickQuestions('supervisor').includes('推荐5000元以上的三星手机'));
});
import {readCasesOnce} from '../src/utils/caseReads.ts';
test('case history reads coalesce by user only, and do not cache results',async()=>{
 let calls=0;const read=async()=>{calls++;return ['current'];};
 await Promise.all([readCasesOnce('A',read),readCasesOnce('A',read),readCasesOnce('B',read)]);
 assert.equal(calls,2);
 await readCasesOnce('A',read);assert.equal(calls,3);
});
test('failed case reads can be retried without stale success',async()=>{
 await assert.rejects(readCasesOnce('FAIL',async()=>{throw new Error('503')}));
 assert.deepEqual(await readCasesOnce('FAIL',async()=>['fresh']),['fresh']);
});
