// Project-owned Chromium only. Never attaches to Chrome, reads cookies, exports
// storageState, solves a CAPTCHA, disables browser security, or fabricates auth.
import fs from 'node:fs/promises';
import path from 'node:path';
import { chromium } from '@playwright/test';
import { loadEnvironment } from '../lib/environment.mjs';

const env = loadEnvironment();
const output = path.join(env.run, 'browser-artifacts');
await fs.mkdir(env.control, { recursive: true });
await fs.mkdir(output, { recursive: true });
const statusFile = path.join(env.control, 'status.json');
const status = { pid: process.pid, startedAt: new Date().toISOString(), state: 'STARTING', roles: {} };
const writeStatus = () => fs.writeFile(statusFile, JSON.stringify(status, null, 2));
const append = (file, row) => fs.appendFile(path.join(output, file), JSON.stringify({ at: new Date().toISOString(), ...row }) + '\n');
const credentials = JSON.parse(await fs.readFile(path.join(env.run, 'browser-fixtures-private.json'), 'utf8'));
const allowed = new Set([new URL(env.shop).origin, new URL(env.admin).origin]);
const roles = {};
const secrets = [credentials.userEmail, credentials.adminAccount, credentials.userPassword, credentials.adminPassword].filter(Boolean);
const safeText = (value) => secrets.reduce((text, secret) => text.replaceAll(secret, '[TEST_ACCOUNT]'), String(value));
for (const name of ['shop', 'admin']) {
  let context;
  try {
    // Native project-only profiles; never import/export auth or open a personal profile.
    context = await chromium.launchPersistentContext(path.join(env.run,'browser-profiles',name), {
      headless:false, ignoreDefaultArgs:['--no-sandbox'],
      viewport:{width:1440,height:1000}, locale:'zh-CN',
      recordVideo:{dir:path.join(output,'private-login-video'),size:{width:1440,height:1000}},
      serviceWorkers:'block'
    });
  } catch(error) {
    status.state='BROWSER_LAUNCH_BLOCKED';status.errorType=error.constructor.name;
    await writeStatus();console.error('BROWSER_LAUNCH_BLOCKED; no automatic launch retry.');
    for(const role of Object.values(roles))await role.context.close();
    process.exit(1);
  }
  status.browserVersion=context.browser().version();status.executablePath=chromium.executablePath();
  // No route.fulfill / fake responses. Prevent accidental navigation to formal
  // services or third-party sites from these writable test contexts.
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return (['data:', 'blob:'].includes(url.protocol) || allowed.has(url.origin)) ? route.continue() : route.abort('blockedbyclient');
  });
  const page = context.pages()[0] || await context.newPage();
  page.setDefaultTimeout(10000);
  roles[name] = { context, page, authenticated: false };
  const base = name === 'shop' ? env.shop : env.admin;
  await page.goto(new URL(name === 'shop' ? '/orders' : 'order/aftersalesCases', base).href, { waitUntil: 'domcontentloaded' });
  // Vue may redirect after DOMContentLoaded. Wait for a real login/protected UI.
  await page.getByPlaceholder(name === 'shop' ? '请输入邮箱' : '请输入账号', { exact:true })
    .or(page.getByText(name === 'shop' ? '我的订单' : '售后案件与人工处理',{exact:true}).first()).first().waitFor();
  const login=/\/login(?:\?|$)/.test(new URL(page.url()).pathname);
  if(login){
    await page.getByPlaceholder(name === 'shop' ? '请输入邮箱' : '请输入账号', { exact: true })
      .fill(name === 'shop' ? credentials.userEmail : credentials.adminAccount);
    await page.getByPlaceholder('请输入密码', { exact: true })
      .fill(name === 'shop' ? credentials.userPassword : credentials.adminPassword);
  }
  status.roles[name] = { state: login?'CAPTCHA_HANDOFF':'VERIFYING_PROJECT_SESSION', baseURL: base };
  await writeStatus();
}
status.state = 'CAPTCHA_HANDOFF'; await writeStatus();
console.log('Independent Chromium ready. Complete CAPTCHA and normal login in its two tabs. No credentials logged.');

function locator(page, spec) {
  let value;
  if (spec.role) value = page.getByRole(spec.role, { name: spec.name, exact: spec.exact ?? true });
  else if (spec.placeholder) value = page.getByPlaceholder(spec.placeholder, { exact: spec.exact ?? true });
  else if (spec.text) value = page.getByText(spec.text, { exact: spec.exact ?? true });
  else if (spec.css) value = page.locator(spec.css);
  else throw new Error('LOCATOR_REQUIRED');
  return spec.nth === undefined ? value : value.nth(spec.nth);
}
async function observeAuth(name) {
  const role = roles[name];
  if (role.authenticated || /\/login(?:\?|$)/.test(new URL(role.page.url()).pathname)) return;
  // Verify a real protected page via normal browser navigation, without reading
  // cookies / localStorage / Token. Its own auth guards decide access.
  const next = await role.context.newPage();
  await next.goto(new URL(name === 'shop' ? '/orders' : 'order/aftersalesCases', name === 'shop' ? env.shop : env.admin).href);
  if (/\/login(?:\?|$)/.test(new URL(next.url()).pathname)) { await next.close(); return; }
  await next.getByText(name === 'shop' ? '我的订单' : '售后案件与人工处理', { exact: true }).first().waitFor();
  const loginVideo = role.page.video();
  await role.page.close();
  // Login video is intentionally discarded: account fields must not enter the
  // evidence bundle. All business pages still have Playwright video recording.
  if (loginVideo) await loginVideo.delete();
  role.page = next; role.authenticated = true;
  role.page.on('response', response => {
    const url = new URL(response.url());
    if (/\/(api|admin-api)\//.test(url.pathname)) void append('http-metadata.jsonl', { role: name, method: response.request().method(), path: url.pathname, http: response.status() });
  });
  role.page.on('pageerror', error => void append('page-errors.jsonl', { role: name, errorType: error.name, message: safeText(error.message).slice(0, 400) }));
  status.roles[name] = { state: 'AUTHENTICATED_PROTECTED_PAGE', baseURL: name === 'shop' ? env.shop : env.admin };
  await role.page.screenshot({ path: path.join(output, `${name}-authenticated.png`), fullPage: false });
  await writeStatus();
}
async function execute(command) {
  if (command.op === 'status') return status;
  if (command.op === 'close') { status.state = 'CLOSING'; await writeStatus(); return { closing: true }; }
  const role = roles[command.role];
  if (!role || !role.authenticated) throw new Error('MANUAL_NORMAL_LOGIN_REQUIRED');
  const page = role.page;
  if (command.op === 'goto') {
    const target = new URL(command.path, command.role === 'shop' ? env.shop : env.admin);
    if (!allowed.has(target.origin)) throw new Error('NON_ISOLATED_NAVIGATION_REJECTED');
    await page.goto(target.href, { waitUntil: 'domcontentloaded' });
  } else if (command.op === 'click') await locator(page, command.locator).click();
  else if (command.op === 'doubleClick') await locator(page, command.locator).dblclick();
  else if (command.op === 'fill') await locator(page, command.locator).fill(command.value);
  else if (command.op === 'select') await locator(page, command.locator).selectOption(command.value);
  else if (command.op === 'check') await locator(page, command.locator).setChecked(command.value !== false);
  else if (command.op === 'reload') await page.reload({ waitUntil: 'domcontentloaded' });
  else if (command.op === 'waitVisible') await locator(page, command.locator).waitFor({ state: 'visible', timeout: Math.min(command.timeout || 10000, 90000) });
  else if (command.op === 'waitText') await page.getByText(command.text, { exact: false }).first().waitFor({ timeout: Math.min(command.timeout || 10000, 90000) });
  else if (command.op === 'screenshot') {
    if (!/^[a-zA-Z0-9_-]+$/.test(command.name)) throw new Error('INVALID_SCREENSHOT_NAME');
    await page.screenshot({ path: path.join(output, `${command.name}.png`), fullPage: command.fullPage ?? false });
  } else if (command.op !== 'inspect') throw new Error('UNKNOWN_BROWSER_OPERATION');
  return { url: page.url(), text: safeText(await page.locator('body').innerText()).slice(0, 22000),
    inputs: await page.locator('input,textarea,select,button').evaluateAll(elements => elements.filter(e => e.getBoundingClientRect().width > 0).map(e => ({ tag: e.tagName, type: e.type, placeholder: e.getAttribute('placeholder'), label: e.getAttribute('aria-label'), text: e.tagName === 'BUTTON' ? e.innerText : undefined })).slice(-100)) };
}
await roles.shop.page.bringToFront();
let closing = false;
try {
  while (!closing && Object.values(roles).every(role=>role.context.browser()?.isConnected())) {
    for (const name of Object.keys(roles)) {
      try { await observeAuth(name); } catch (error) { status.roles[name].errorType = error.constructor.name; await writeStatus(); }
    }
    if (Object.values(roles).every(r => r.authenticated)) { status.state = 'READY'; await writeStatus(); }
    const files = (await fs.readdir(env.control)).filter(n => /^command-[a-f0-9-]+\.json$/.test(n)).sort();
    for (const file of files) {
      const input = path.join(env.control, file);
      const resultFile = input.replace('command-', 'result-');
      if (await fs.stat(resultFile).catch(() => null)) continue;
      const command = JSON.parse(await fs.readFile(input, 'utf8'));
      let result;
      try { result = { ok: true, data: await execute(command) }; }
      catch (error) { result = { ok: false, errorType: error.constructor.name, message: safeText(error.message).slice(0, 1200) }; }
      await fs.writeFile(resultFile, JSON.stringify(result, null, 2));
      if (command.op === 'close') closing = true;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
} finally {
  status.videos=[];
  for (const [name, role] of Object.entries(roles)) {
    const video = role.authenticated ? role.page.video() : null;
    // Persistent context.close also closes its browser protocol. Resolve the
    // local recording path beforehand, then copy the finalized file directly.
    const videoPath=video?await video.path():null;
    status.closeStage='CLOSING_CONTEXT:'+name;await writeStatus();
    await role.context.close();
    if (video) {
      const target=path.join(output, `${name}-business.webm`);
      await fs.copyFile(videoPath,target);
      status.videos.push({role:name,file:target,bytes:(await fs.stat(target)).size,sessionStartedAt:status.startedAt});
    }
  }
  status.state = 'CLOSED'; status.endedAt = new Date().toISOString(); await writeStatus();
}
