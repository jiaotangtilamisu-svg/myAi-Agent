import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeExecution, parseSupervisor, phaseLabel, validExecution } from '../src/utils/agentExecution.ts';

test('execution progress does not duplicate an Agent or change business content', () => {
  let states = mergeExecution([], { agent: 'aftersales', status: 'RUNNING' });
  states = mergeExecution(states, { agent: 'shopping', status: 'RUNNING' });
  states = mergeExecution(states, { agent: 'aftersales', status: 'SUCCESS' });
  assert.equal(states.length, 2);
  assert.equal(states.find(v => v.agent === 'aftersales')?.status, 'SUCCESS');
});
test('unknown Agent/status rejected', () => {
  assert.equal(validExecution({ agent: 'refund_executor', status: 'SUCCESS' }), false);
  assert.deepEqual(mergeExecution([], { agent: 'shopping', status: 'PAID' }), []);
});
test('unified payload preserves zero price and unknown price separately', () => {
  const value = parseSupervisor(JSON.stringify({type:'SUPERVISOR_RESULT', intro:'facts',products:[{minPrice:null},{minPrice:0}],agents:[{agent:'shopping',status:'SUCCESS'}],status:'COMPLETE'}));
  assert.equal(value?.products[0].minPrice, null);
  assert.equal(value?.products[1].minPrice, 0);
});
test('old specialist messages are not consumed as Supervisor', () => {
  for (const type of ['PRODUCT_SEARCH_RESULT', 'ACTION_CONFIRM', 'query_order']) assert.equal(parseSupervisor(JSON.stringify({type, intro:'x',products:[],agents:[]})), null);
});
test('malformed JSON and injected status ignored', () => {
  assert.equal(parseSupervisor('broken'), null);
  assert.equal(parseSupervisor(JSON.stringify({type:'SUPERVISOR_RESULT',intro:'x',products:[],agents:[{agent:'admin',status:'APPROVED'}]})), null);
});
test('success label means query completion, never financial completion', () => {
  assert.equal(phaseLabel('SUCCESS'), '查询完成');
  assert.equal(phaseLabel('TIMEOUT'), '查询超时');
});
