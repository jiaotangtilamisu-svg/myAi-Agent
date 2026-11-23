import test from 'node:test';
import assert from 'node:assert/strict';
import {transportErrorMessage as message} from '../src/utils/transportError.ts';
test('cart 503 is a service failure, not falsely described as local network failure',()=>assert.equal(message({config:{url:'/productCart/loadProductCart'},response:{status:503}}),'购物车服务暂不可用，请稍后重试'));
test('timeout names the affected service',()=>assert.equal(message({config:{url:'/search/loadHotKeywords'},code:'ECONNABORTED'}),'搜索服务请求超时，请稍后重试'));
test('gateway and offline failures are distinguished',()=>{assert.match(message({response:{status:502}}),/连接异常/);assert.match(message({code:'ERR_NETWORK'}),/无法连接服务器/)});
test('server details and request query credentials are never shown',()=>{const text=message({config:{url:'/api/agent/sendMessage?token=PRIVATE'},response:{status:500}});assert.match(text,/智能客服/);assert.ok(!text.includes('PRIVATE'))});
test('personal center coupon failure is identified',()=>assert.equal(message({config:{url:'/discountCoupon/loadUserCoupon'},response:{status:503}}),'优惠券服务暂不可用，请稍后重试'));
test('member and order requests identify the failing dependency',()=>{assert.match(message({config:{url:'/userMember/loadMemberCenter'},response:{status:503}}),/^会员服务/);assert.match(message({config:{url:'/order/getOrderCountInfo'},response:{status:503}}),/^订单服务/)});
