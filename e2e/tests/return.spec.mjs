import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { command } from '../lib/session.mjs';
import { loadEnvironment } from '../lib/environment.mjs';

const env = loadEnvironment();
const fixtures = JSON.parse(fs.readFileSync(path.join(env.run, 'fixture-manifest.json'), 'utf8'));
const c = (op, role, args = {}) => command({ op, role, ...args });
const button = name => ({ role: 'button', name, nth: -1 });
const shot = name => c('screenshot', 'shop', { name });
function database(label) {
  execFileSync('E:/Python/python.exe', ['-m', 'tools.quality_engineering.stage34.browser_database', label], {
    cwd: env.root, env: { ...process.env, PYTHONPATH: env.root, PYTHONUTF8: '1' }, stdio: 'pipe'
  });
  return JSON.parse(fs.readFileSync(path.join(env.run, `browser-database-${label}.json`), 'utf8'));
}
async function send(text) {
  // Mobile/Safari keyboard handling deliberately restores readonly on blur.
  // A real user focuses the composer before typing; fill alone is not a click.
  await c('click', 'shop', { locator: { placeholder: '输入你想咨询的问题' } });
  await c('fill', 'shop', { locator: { placeholder: '输入你想咨询的问题' }, value: text });
  await c('click', 'shop', { locator: { role: 'button', name: '发送消息' } });
  await c('waitVisible', 'shop', { locator: { css: `.msg-group:last-child:has-text(${JSON.stringify(text)})` }, timeout: 90000 });
  await c('waitVisible', 'shop', { locator: { role: 'button', name: '发送消息' }, timeout: 90000 });
}
async function adminOperation(name, note) {
  if (note) await c('fill', 'admin', { locator: { placeholder: '填写审批理由或实际人工处理结果；不代表系统已执行退款' }, value: note });
  await c('click', 'admin', { locator: button(name) });
  await c('click', 'admin', { locator: { css: '.el-message-box__btns .el-button--primary' } });
}

test('真实浏览器：退货草稿→修改→本人确认→审核→物流→验收→模拟退款→归档', async () => {
  const initial = database('return-start');
  const order = fixtures.orders.find(row => row.userId === env.plan.userA && row.status === 3);
  expect(order).toBeTruthy();
  expect((await command({ op: 'status' })).state).toBe('READY');
  let caseId;
  await test.step('本人订单和详情由真实页面读取', async () => {
    await c('goto', 'shop', { path: '/orders' });
    await c('waitText', 'shop', { text: order.orderId });
    expect((await c('inspect', 'shop')).text).not.toContain(fixtures.orders.find(row => row.userId === env.plan.userB).orderId);
    await c('click', 'shop', { locator: { role: 'button', name: '订单详情', nth: 0 } });
    await c('waitText', 'shop', { text: 'QA34ITEM0' });
    await shot('02-order-item-sku');
    await c('click', 'shop', { locator: { role: 'button', name: '智能客服', nth: 0 } });
    await c('select', 'shop', { locator: { role: 'combobox', name: '选择统一助手、售后客服或智能导购' }, value: 'support' });
  });
  await test.step('自然语言退货与多订单澄清，不擅自选择订单', async () => {
    await send('我要退货');
    const page = await c('waitText', 'shop', { text: '订单号', timeout: 90000 });
    expect(page.text).toMatch(/订单号/);
    expect(database('clarification').cases.length).toBe(initial.cases.length);
    await shot('03-order-clarification');
  });
  await test.step('本人订单核实与真实已发布政策证据', async () => {
    await send(`订单号：${order.orderId}`);
    await c('waitVisible', 'shop', { locator: button('生成待确认的售后方案'), timeout: 90000 });
    const page = await c('click', 'shop', { locator: { css: '.msg-group:last-child summary:has-text("查看订单核实与完整政策依据")' } });
    expect(page.text).toContain(order.orderId);
    expect(page.text).toMatch(/消费者权益保护法实施条例/);
    expect(database('diagnosis').cases.length).toBe(initial.cases.length);
    await shot('04-policy-diagnosis');
  });
  await test.step('生成未正式提交的方案草稿并修改原因和材料', async () => {
    await c('click', 'shop', { locator: button('生成待确认的售后方案') });
    await c('waitText', 'shop', { text: '方案草稿编号' });
    const saved = database('draft');
    const draft = saved.cases.filter(row => !initial.cases.some(old => old.caseId === row.caseId));
    expect(draft).toHaveLength(1); caseId = draft[0].caseId;
    expect(draft[0]).toMatchObject({ userId: env.plan.userA, orderId: order.orderId, state: 'AWAITING_USER', planVersion: 1 });
    expect(saved.audit.filter(row => row.caseId === caseId).map(row => row.action)).toEqual(['CREATE']);
    await c('fill', 'shop', { locator: { placeholder: '请填写真实申请原因，供管理员审核' }, value: 'QUALITY34隔离测试：商品不想要，申请退货，等待人工核实适用条件' });
    await c('fill', 'shop', { locator: { placeholder: '可选：描述质量问题、照片证据或沟通凭证（不上传文件）' }, value: 'QUALITY34合成材料：包装与配件齐全，无真实个人信息' });
    await c('click', 'shop', { locator: button('保存原因、材料和类型修改') });
    await c('waitText', 'shop', { text: '方案 2' });
    const changed = database('amended');
    expect(changed.cases.find(row => row.caseId === caseId)).toMatchObject({ state: 'AWAITING_USER', planVersion: 2 });
    await shot('05-draft-amended');
  });
  await test.step('真实点击确认，正式提交唯一案件并刷新恢复', async () => {
    await c('click', 'shop', { locator: button('确认方案并提交申请') });
    await c('click', 'shop', { locator: { css: '.el-message-box__btns .el-button--primary' } });
    await c('waitText', 'shop', { text: '申请编号' });
    const saved = database('confirmed');
    expect(saved.cases.filter(row => row.caseId === caseId)).toHaveLength(1);
    expect(saved.cases.find(row => row.caseId === caseId).state).toBe('ADMIN_REVIEW');
    expect(saved.audit.filter(row => row.caseId === caseId && row.action === 'CONFIRM')).toHaveLength(1);
    await shot('06-user-submitted');
    await c('reload', 'shop');
    await c('waitText','shop',{text:'订单信息',timeout:90000});
    await c('click', 'shop', { locator: { role: 'button', name: '智能客服', nth: 0 } });
    await c('waitText', 'shop', { text: '订单号：' + order.orderId });
    await c('click', 'shop', { locator: { css: `.msg-group:last-child [data-case-id="${caseId}"] button` } });
    await c('waitText', 'shop', { text: '申请编号：' + caseId });
    await shot('07-refresh-restored');
  });
  await test.step('管理员真实页面审核通过并领取人工任务', async () => {
    await c('reload', 'admin'); await c('waitText', 'admin', { text: caseId });
    await c('click', 'admin', { locator: { css: `.el-table__row:has-text("${caseId}") button` } });
    await c('waitText', 'admin', { text: '案件详情与审计' });
    await adminOperation('批准进入人工处理', 'QUALITY34：测试管理员核对隔离订单、SKU、用户申请原因及政策；批准进入人工处理，不代表退款');
    await c('waitVisible', 'admin', { locator: button('领取人工任务') });
    await adminOperation('领取人工任务', 'QUALITY34：领取隔离退货处理任务');
    await c('waitText', 'admin', { text: '退货履约记录与模拟退款' });
    expect(database('approved').cases.find(row => row.caseId === caseId).state).toBe('IN_PROGRESS');
    await c('screenshot', 'admin', { name: '08-admin-approved' });
  });
  await test.step('用户真实填写隔离物流号，不伪装承运商实况', async () => {
    await c('click', 'shop', { locator: button('刷新当前申请进度') });
    await c('fill', 'shop', { locator: { placeholder: '退货物流公司' }, value: 'QUALITY34隔离测试物流（非真实承运商）' });
    await c('fill', 'shop', { locator: { placeholder: '实际退货运单号' }, value: 'QA34-RETURN-0001' });
    await c('click', 'shop', { locator: button('确认提交退货物流') });
    await c('click', 'shop', { locator: { css: '.el-message-box__btns .el-button--primary' } });
    await c('waitText', 'shop', { text: 'QA34-RETURN-0001' });
    const events = database('logistics').audit.filter(row => row.caseId === caseId && row.action === 'USER_RETURN_LOGISTICS');
    expect(events).toHaveLength(1); expect(JSON.parse(events[0].note).trackingNo).toBe('QA34-RETURN-0001');
    await shot('09-user-return-logistics');
  });
  await test.step('管理员验收、分步模拟退款和归档', async () => {
    // Close/reopen detail to re-read the actual user-created logistics/version.
    await c('click', 'admin', { locator: { role: 'button', name: '关闭此对话框' } });
    await c('click', 'admin', { locator: { css: `.el-table__row:has-text("${caseId}") button` } });
    await c('waitText', 'admin', { text: 'QA34-RETURN-0001' });
    // Reproduce the reported "confirm does nothing": validation must be
    // visible inside this dialog, and cannot append another logistics event.
    const beforeInvalid=database('acceptance-validation-before');
    await c('waitVisible','admin',{locator:{css:'button:disabled:has-text("更正退货物流（需说明）")'}});
    await c('click','admin',{locator:button('登记退货验收')});
    await c('waitVisible','admin',{locator:{css:'.el-dialog [role="alert"]:has-text("请填写核实意见")'}});
    expect(database('acceptance-validation-after').audit).toEqual(beforeInvalid.audit);
    await c('screenshot','admin',{name:'acceptance-error-visible-inside-dialog'});
    // Element Plus hides the native input; users operate its visible label.
    await c('click', 'admin', { locator: { text: '确认退货已收到' } });
    await c('click', 'admin', { locator: { text: '验收通过' } });
    await c('fill', 'admin', { locator: { placeholder: '可选：关联仓库验收记录或证据编号' }, value: 'QA34-ACCEPTANCE-001' });
    await adminOperation('登记退货验收', 'QUALITY34隔离验收：收到测试退货，材料已核实；非真实仓储验收');
    await c('waitText', 'admin', { text: 'ACCEPTED' });
    await adminOperation('准备待执行退款', 'QUALITY34：准备本地模拟退款');
    await c('waitVisible', 'admin', { locator: button('开始本地模拟（持久化处理中）') });
    await adminOperation('开始本地模拟（持久化处理中）', 'QUALITY34：仅隔离模拟，不调用支付渠道');
    await c('waitVisible', 'admin', { locator: button('登记模拟结果/人工核实结果') });
    await adminOperation('登记模拟结果/人工核实结果', 'QUALITY34：本地模拟成功，无资金到账');
    await c('waitText', 'admin', { text: 'SUCCEEDED' });
    await c('screenshot', 'admin', { name: '10-admin-mock-refund-succeeded' });
    await adminOperation('记录处理成功', 'QUALITY34：隔离退货验收与模拟结果已核实');
    await c('waitVisible', 'admin', { locator: button('归档') });
    await adminOperation('归档', 'QUALITY34：完成隔离案件归档');
    await c('waitText', 'admin', { text: '已归档' });
    await c('click', 'shop', { locator: button('刷新当前申请进度') });
    const page = await c('waitText', 'shop', { text: '本地模拟退款：成功' });
    expect(page.text).toContain('已归档'); expect(page.text).toContain('不代表资金到账');
    await shot('11-user-final-result');
    const final = database('return-final');
    expect(final.cases.find(row => row.caseId === caseId).state).toBe('ARCHIVED');
    const actions = final.audit.filter(row => row.caseId === caseId).map(row => row.action);
    expect(actions).toEqual(['CREATE','AMEND','CONFIRM','APPROVE','CLAIM','USER_RETURN_LOGISTICS','RETURN_ACCEPT','PREPARE_REFUND','START_MOCK_REFUND','COMPLETE_MOCK_REFUND','SUCCEED','ARCHIVE']);
    const versions = final.audit.filter(row => row.caseId === caseId).map(row => row.version);
    expect(versions).toEqual(Array.from({ length: versions.length }, (_, i) => i + 1));
    expect(final.tables['order.order_info']).toEqual(initial.tables['order.order_info']);
    expect(final.tables['order.order_item']).toEqual(initial.tables['order.order_item']);
    expect(final.tables['stock.sku_stock']).toEqual(initial.tables['stock.sku_stock']);
    fs.writeFileSync(path.join(env.run, 'browser-primary-return.json'), JSON.stringify({ caseId, orderId: order.orderId, actions, state: 'ARCHIVED', realFundsExecuted: false, evidence: 'Playwright page actions + isolated MySQL SELECT' }, null, 2));
  });
  await test.step('自然语言进程查询读取同一订单案件的实际退款结果',async()=>{
    const before=database('progress-query-before');
    await send(`订单${order.orderId}的退货进程`);
    await c('waitVisible','shop',{locator:{css:'.msg-group:last-child:has-text("本地模拟退款：成功")'},timeout:90000});
    const view=await c('inspect','shop');
    expect(view.text).toContain(caseId);
    expect(view.text).toContain('仅模拟，不代表资金到账');
    const after=database('progress-query-after');
    expect(after.cases).toEqual(before.cases);
    expect(after.audit).toEqual(before.audit);
    await shot('12-natural-language-refund-progress');
  });
});
