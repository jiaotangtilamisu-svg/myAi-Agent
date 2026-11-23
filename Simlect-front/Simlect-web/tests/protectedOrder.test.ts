import test from 'node:test';
import assert from 'node:assert/strict';
import { loadProtectedOrder } from '../src/utils/protectedOrder.ts';

test('protected order reads keep successful data and legitimate empty state', async () => {
  const value = {orderId:'fixture-order'};
  assert.deepEqual(await loadProtectedOrder(async()=>value,'订单'),{data:value,error:''});
  assert.deepEqual(await loadProtectedOrder(async()=>null,'物流'),{data:null,error:''});
});
test('order permission failure is handled with no data and no rejected hook',async()=>{
  const result=await loadProtectedOrder(async()=>{throw {info:'订单不存在或无权查看'};},'订单');
  assert.deepEqual(result,{data:null,error:'订单不存在或无权查看'});
});
test('a service failure is not misrepresented as missing logistics',async()=>{
  const result=await loadProtectedOrder(async()=>{throw {response:{status:503},info:'private diagnostic'};},'物流');
  assert.deepEqual(result,{data:null,error:'物流查询暂时不可用，请稍后重试'});
});
test('timeout and unexpected values remain explicit failures',async()=>{
  assert.deepEqual(await loadProtectedOrder(async()=>{throw {code:'ETIMEDOUT'};},'订单'),{data:null,error:'订单查询超时，请稍后重试'});
  assert.deepEqual(await loadProtectedOrder(async()=>{throw null;},'订单'),{data:null,error:'订单查询暂时不可用，请稍后重试'});
});
