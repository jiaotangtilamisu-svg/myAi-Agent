import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { command } from './session.mjs';
import { loadEnvironment } from './environment.mjs';
export const env = loadEnvironment();
export const c = (op, role, args = {}) => command({ op, role, ...args });
export const button = name => ({ role: 'button', name, nth: -1 });
export function database(label) {
  execFileSync('E:/Python/python.exe', ['-m', 'tools.quality_engineering.stage34.browser_database', label], { cwd: env.root, env: { ...process.env, PYTHONPATH: env.root, PYTHONUTF8: '1' }, stdio: 'pipe' });
  return JSON.parse(fs.readFileSync(path.join(env.run, `browser-database-${label}.json`), 'utf8'));
}
export async function openChat(mode = 'support') {
  await c('goto', 'shop', { path: '/orders' });
  await c('waitText', 'shop', { text: 'QA34ITEM0' });
  await c('click', 'shop', { locator: { role: 'button', name: '智能客服', nth: 0 } });
  await c('select', 'shop', { locator: { role: 'combobox', name: '选择统一助手、售后客服或智能导购' }, value: mode });
}
export async function send(text) {
  await c('click', 'shop', { locator: { placeholder: '输入你想咨询的问题' } });
  await c('fill', 'shop', { locator: { placeholder: '输入你想咨询的问题' }, value: text });
  await c('click', 'shop', { locator: { role: 'button', name: '发送消息' } });
  await c('waitVisible', 'shop', { locator: { css: `.msg-group:last-child:has-text(${JSON.stringify(text)})` }, timeout: 90000 });
  return c('waitVisible', 'shop', { locator: { role: 'button', name: '发送消息' }, timeout: 90000 });
}
export async function adminDetail(caseId) {
  await c('reload', 'admin'); await c('waitText', 'admin', { text: caseId });
  await c('click', 'admin', { locator: { css: `.el-table__row:has-text("${caseId}") button` } });
  await c('waitText', 'admin', { text: '案件详情与审计' });
}
export async function adminOperation(name, note) {
  if (note) await c('fill', 'admin', { locator: { placeholder: '填写审批理由或实际人工处理结果；不代表系统已执行退款' }, value: note });
  await c('click', 'admin', { locator: button(name) });
  return c('click', 'admin', { locator: { css: '.el-message-box__btns .el-button--primary' } });
}
export async function userDetail(caseId) {
  await c('click', 'shop', { locator: button('查询我的售后申请') });
  await c('waitText', 'shop', { text: caseId });
  await c('click', 'shop', { locator: { css: `.msg-group:last-child [data-case-id="${caseId}"] button` } });
  return c('waitVisible', 'shop', { locator: { css: `.msg-group:last-child p:text-is("申请编号：${caseId}"),.msg-group:last-child p:text-is("方案草稿编号：${caseId}")` } });
}
export function reportOf(message) { const data = JSON.parse(message.bizData); return data.fullReport || data; }
export async function createApplication(label) {
  const fixtures=JSON.parse(fs.readFileSync(path.join(env.run,'fixture-manifest.json'),'utf8'));
  const order=fixtures.orders.find(row=>row.userId===env.plan.userA&&row.status===3);
  const before=database(label+'-before');
  await openChat();
  await send('我要退货；订单号：'+order.orderId+'；QUALITY34独立场景：'+label);
  await c('click','shop',{locator:button('生成待确认的售后方案')});
  await c('waitText','shop',{text:'方案草稿编号'});
  const created=database(label+'-draft');
  const row=created.cases.find(r=>!before.cases.some(old=>old.caseId===r.caseId));
  if(!row)throw new Error('Browser did not create a unique draft');
  await c('fill','shop',{locator:{placeholder:'请填写真实申请原因，供管理员审核'},value:'QUALITY34隔离测试：商品不想要，'+label+'，请人工核实'});
  await c('click','shop',{locator:button('确认方案并提交申请')});
  await c('click','shop',{locator:{css:'.el-message-box__btns .el-button--primary'}});
  await c('waitText','shop',{text:'申请编号：'+row.caseId});
  return database(label+'-submitted').cases.find(r=>r.caseId===row.caseId);
}
