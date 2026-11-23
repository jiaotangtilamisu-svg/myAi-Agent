import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { env, c, button, database, openChat, send, adminDetail, adminOperation, userDetail, createApplication } from '../lib/business.mjs';
const fixtures=JSON.parse(fs.readFileSync(path.join(env.run,'fixture-manifest.json'),'utf8'));
// Each branch reopens its page and uses its own recorded fixture. A failed
// assertion must not silently skip the remaining independent scenarios.

test('订单归属：A的真实浏览器不能读取B订单详情',async()=>{
 const target=fixtures.orders.find(row=>row.userId===env.plan.userB);
 await c('goto','shop',{path:'/order/'+target.orderId});
 const page=await c('waitText','shop',{text:'订单不存在或无权查看'});
 expect(page.text).not.toContain('QA34ITEM5');
 await c('screenshot','shop',{name:'12-order-ownership-denied'});
});

test('管理员驳回→本人补充→新方案确认，重复点击不重复提交',async()=>{
 const row=await createApplication('reject');
 expect(row.state).toBe('ADMIN_REVIEW');
 const baseline=database('reject-confirm-baseline');
 await adminDetail(row.caseId);
 await adminOperation('驳回方案','QUALITY34隔离审核驳回：申请材料不足，请补充包装和配件情况');
 await c('waitVisible','admin',{locator:button('归档')});
 await openChat(); await userDetail(row.caseId);
 await c('fill','shop',{locator:{placeholder:'请填写真实申请原因，供管理员审核'},value:'QUALITY34补充后重新申请：商品不想要，包装配件齐全，请人工核实'});
 await c('fill','shop',{locator:{placeholder:'可选：第二项证据说明'},value:'QUALITY34补充材料：测试验货记录，无真实个人信息'});
 await c('click','shop',{locator:button('保存补充材料并生成待确认方案')});
 await c('waitText','shop',{text:'方案草稿编号：'+row.caseId});
 const revised=database('reject-amended').cases.find(r=>r.caseId===row.caseId);
 expect(revised.state).toBe('AWAITING_USER'); expect(revised.planVersion).toBe(row.planVersion+1);
 await c('doubleClick','shop',{locator:button('确认方案并提交申请')});
 await c('click','shop',{locator:{css:'.el-message-box__btns .el-button--primary'}});
 await c('waitText','shop',{text:'申请编号：'+row.caseId});
 const after=database('reject-resubmitted');
 expect(after.cases.find(r=>r.caseId===row.caseId).state).toBe('ADMIN_REVIEW');
 expect(after.audit.filter(e=>e.caseId===row.caseId&&e.action==='CONFIRM')).toHaveLength(baseline.audit.filter(e=>e.caseId===row.caseId&&e.action==='CONFIRM').length+1);
 await c('screenshot','shop',{name:'13-rejected-amended-resubmitted'});
});

test('模拟退款失败、原退款号重试、UNKNOWN不成功、人工核实后恢复',async()=>{
 const row=await createApplication('refund-failure');
 expect(row.state).toBe('ADMIN_REVIEW');
 await adminDetail(row.caseId);
 await adminOperation('批准进入人工处理','QUALITY34：独立失败分支审核通过');
 await c('waitVisible','admin',{locator:button('领取人工任务')});
 await adminOperation('领取人工任务','QUALITY34：领取独立失败分支人工任务');
 await c('click','shop',{locator:button('刷新当前申请进度')});
 await c('fill','shop',{locator:{placeholder:'退货物流公司'},value:'QUALITY34测试物流（非真实承运商）'});
 await c('fill','shop',{locator:{placeholder:'实际退货运单号'},value:'QA34-FAILURE-0002'});
 await c('click','shop',{locator:button('确认提交退货物流')});
 await c('click','shop',{locator:{css:'.el-message-box__btns .el-button--primary'}});
 await c('waitText','shop',{text:'QA34-FAILURE-0002'});
 await adminDetail(row.caseId);
 await c('click','admin',{locator:{text:'确认退货已收到'}});
 await c('click','admin',{locator:{text:'验收通过'}});
 await adminOperation('登记退货验收','QUALITY34：测试验收记录完整，非真实仓储验收');
 await c('waitText','admin',{text:'ACCEPTED'});
 await adminOperation('准备待执行退款','QUALITY34：准备第一次模拟尝试');
 await c('waitVisible','admin',{locator:button('开始本地模拟（持久化处理中）')});
 await adminOperation('开始本地模拟（持久化处理中）','QUALITY34：模拟第一次尝试');
 await c('click','admin',{locator:{text:'模拟渠道失败（需填写失败原因，仅隔离环境启用）'}});
 await adminOperation('登记模拟结果/人工核实结果','QUALITY34故障注入：模拟渠道失败，不是实际支付渠道');
 await c('waitText','admin',{text:'FAILED'});
 const failed=database('refund-failed');
 const failEvent=failed.audit.filter(e=>e.caseId===row.caseId&&e.action==='COMPLETE_MOCK_REFUND').at(-1);
 expect(JSON.parse(failEvent.note).status).toBe('FAILED'); const refundId=JSON.parse(failEvent.note).refundId;
 await c('click','admin',{locator:{text:'模拟渠道失败（需填写失败原因，仅隔离环境启用）'}});
 await adminOperation('准备待执行退款','QUALITY34：按原模拟单重试');
 await c('waitVisible','admin',{locator:button('开始本地模拟（持久化处理中）')});
 await adminOperation('开始本地模拟（持久化处理中）','QUALITY34：模拟第二次尝试');
 await c('waitVisible','admin',{locator:button('记录模拟超时（结果未知）')});
 await adminOperation('记录模拟超时（结果未知）','QUALITY34故障注入：模拟回执超时，结果尚未知');
 await c('waitText','admin',{text:'UNKNOWN'});
 const unknown=database('refund-unknown');
 const current=unknown.audit.filter(e=>e.caseId===row.caseId&&e.action==='TIMEOUT_MOCK_REFUND').at(-1);
 expect(JSON.parse(current.note)).toMatchObject({status:'UNKNOWN',refundId,executionAllowed:false});
 await adminOperation('登记模拟结果/人工核实结果','QUALITY34：没有勾选人工核实，必须拒绝');
 await c('waitText','admin',{text:'操作未完成'});
 expect(database('refund-unknown-denied').audit.filter(e=>e.caseId===row.caseId)).toHaveLength(unknown.audit.filter(e=>e.caseId===row.caseId).length);
 await c('click','admin',{locator:{text:'已人工核实超时结果'}});
 await adminOperation('登记模拟结果/人工核实结果','QUALITY34：人工核实测试模拟状态，确认模拟成功；未触发真实资金');
 await c('waitVisible','admin',{locator:button('记录处理成功')});
 const final=database('refund-reconciled');
 const result=JSON.parse(final.audit.filter(e=>e.caseId===row.caseId&&e.action==='COMPLETE_MOCK_REFUND').at(-1).note);
 expect(result).toMatchObject({status:'SUCCEEDED',refundId,attempt:2,executionAllowed:false,manualReconciliation:true});
 await c('screenshot','admin',{name:'14-refund-retry-same-id-reconciled'});
});

test('没有商城自有政策证据时不编造终身退款承诺',async()=>{
 await openChat(); await send('商城承诺终身无条件退款吗？请仅查询商城自有规则，不要提交申请');
 const data=database('no-platform-policy'); const message=data.messages.at(-1);
 expect(message.status).toBe(2); expect(message.aiMessage).toMatch(/无法|未确认|未收录|不能/);
 expect(message.aiMessage).not.toMatch(/商城承诺.*终身.*退款/);
 await c('screenshot','shop',{name:'15-no-unverified-shop-promise'});
});
