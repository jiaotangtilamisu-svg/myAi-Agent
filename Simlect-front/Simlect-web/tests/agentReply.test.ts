import test from 'node:test';
import assert from 'node:assert/strict';
import { reconcileReply } from '../src/utils/agentReply.ts';
import { mergeHistoryMessages } from '../src/utils/agentHistory.ts';

test('completed durable reply recovers a missed or early WebSocket DONE', () => {
  const item = { messageId: 15, assistantMessage: '', status: 1 };
  assert.equal(reconcileReply(item, { messageId: 15, assistantMessage: '真实回复', status: 2 }), true);
  assert.equal(item.assistantMessage, '真实回复');
  assert.equal(item.status, 2);
});
test('other message IDs cannot complete the active message', () => {
  const item = { messageId: 15, assistantMessage: '', status: 1 };
  assert.equal(reconcileReply(item, {messageId:14,assistantMessage:'other',status:2}), false);
  assert.equal(item.status, 1);
});
test('pending query does not overwrite an existing streamed partial', () => {
  const item = {messageId:15,assistantMessage:'partial',status:1};
  assert.equal(reconcileReply(item,{messageId:15,status:1,assistantMessage:''}),false);
  assert.equal(item.assistantMessage,'partial');
});
for (const status of [0, 2, 3]) test(`terminal state ${status} is recovered including failure text`, () => {
  const item = {messageId:15,assistantMessage:'',status:1};
  assert.equal(reconcileReply(item,{message_id:15,status,assistant_message:'服务暂时不可用',biz_type:'agent_error'}),true);
  assert.equal(item.status,status);
});
test('initial history response cannot discard a just-submitted message', () => {
  assert.deepEqual(mergeHistoryMessages([{messageId:1,status:2,assistantMessage:'old'}],[{messageId:15,status:1,assistantMessage:''}]).map(x=>x.messageId),[1,15]);
});
test('malformed result cannot imply completion from missing status', () => {
  const item = {messageId:15,status:1,assistantMessage:''};
  assert.equal(reconcileReply(item,{messageId:15,assistantMessage:'incomplete'}),false);
  assert.equal(item.status,1);
});
