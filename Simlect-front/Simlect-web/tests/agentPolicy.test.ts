import test from 'node:test';
import assert from 'node:assert/strict';
import { parsePolicyAnswer, policyNotice, policySourceUrl } from '../src/utils/agentPolicy.ts';
import { applyTerminalReply, reconcileReply } from '../src/utils/agentReply.ts';
const payload={kind:'policy_answer',messageId:91,responseStatus:'DEGRADED',modelFailureCode:'MODEL_TIMEOUT',hits:[{chunkId:'chunk',documentId:'doc',documentName:'TEST ONLY',revision:7,section:'article',source:'fixture://source',text:'证据'.repeat(4000)}]};
test('large evidence survives WS and durable history without truncation',()=>{
 const item={messageId:91,status:1,assistantMessage:''};
 assert.equal(applyTerminalReply(item,{messageId:91,assistantMessage:'原文引用',bizData:JSON.stringify(payload)},1),true);
 const result=parsePolicyAnswer((item as any).bizData,91)!;
 assert.equal(result.hits[0]!.text,payload.hits[0]!.text);
 assert.equal(result.hits[0]!.chunkId,'chunk');assert.equal(result.hits[0]!.revision,7);
 assert.match(policyNotice(result),/超时/);
});
test('database failure is failed rather than complete and retains its code',()=>{
 const item={messageId:91,status:1,assistantMessage:''};
 applyTerminalReply(item,{messageId:91,errorCode:'DB_PERSISTENCE_FAILED',bizType:'agent_persistence_error',assistantMessage:'数据库保存失败'},2);
 assert.equal(item.status,4);assert.match(item.assistantMessage,/数据库/);
 assert.equal(reconcileReply(item,{messageId:91,status:4,errorCode:'DB_PERSISTENCE_FAILED',assistantMessage:'未保存'}),true);
});
test('wrong message cannot attach evidence',()=>assert.equal(parsePolicyAnswer(payload,92),null));
test('503 degradation differs from persistence error',()=>assert.match(policyNotice({...payload,modelFailureCode:'MODEL_UPSTREAM_UNAVAILABLE'}),/繁忙/));
test('source links reject script URLs',()=>{assert.equal(policySourceUrl('javascript:alert(1)'),undefined);assert.equal(policySourceUrl('https://example.invalid/law'),'https://example.invalid/law');});
