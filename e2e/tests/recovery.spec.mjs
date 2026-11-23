import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { env, c, database, openChat, send, userDetail } from '../lib/business.mjs';
import { readLaunchJson } from '../../tools/quality_engineering/stage34/native-spec.mjs';

test('Agent重启与WebSocket断连后，历史证据和已归档案件可由页面恢复',async()=>{
 const primary=JSON.parse(fs.readFileSync(path.join(env.run,'browser-primary-return.json'),'utf8'));
 const prior=database('restart-baseline');
 expect(prior.messages.every(row=>row.status!==1)).toBe(true);
 const before=readLaunchJson(path.join(env.run,'agent-process.json'));
 const searchBefore=readLaunchJson(path.join(env.run,'search-process.json'));
 const argv=['-NoProfile','-ExecutionPolicy','Bypass','-File'];
 const launchLogs=path.join(env.run,'recovery-launch-'+Date.now());fs.mkdirSync(launchLogs);
 for(const action of ['stop','start']){
  const out=fs.openSync(path.join(launchLogs,action+'.stdout.log'),'a');
  const err=fs.openSync(path.join(launchLogs,action+'.stderr.log'),'a');
  try {
   // A long-lived grandchild can inherit Windows pipe handles. Use real log
   // files, so spawnSync waits for PowerShell itself rather than pipe EOF.
   execFileSync('powershell',[...argv,path.join(env.root,`tools/quality_engineering/stage34/${action}.ps1`),'-Service','agent'],{cwd:env.root,stdio:['ignore',out,err],timeout:180000});
  } finally {fs.closeSync(out);fs.closeSync(err);}
 }
 const current=readLaunchJson(path.join(env.run,'agent-process.json'));
 expect(current.PID).not.toBe(before.PID);expect(current.State).toBe('RESPONDING');
 expect(new Date(current.CreationDate).getTime()).toBeGreaterThan(new Date(before.CreationDate).getTime());
 const probe=JSON.parse(execFileSync('powershell',['-NoProfile','-Command',
  `$p=Get-CimInstance Win32_Process -Filter 'ProcessId=${searchBefore.PID}'; if(!$p){throw 'Isolated Search exited'}; $l=Get-NetTCPConnection -LocalPort 18108 -State Listen; if($l.OwningProcess -notcontains $p.ProcessId){throw 'Search listener changed'}; @{PID=$p.ProcessId;CreationDate=$p.CreationDate.ToString('o');CommandLine=$p.CommandLine}|ConvertTo-Json -Compress`
 ],{encoding:'utf8',stdio:'pipe',timeout:30000}).replace(/^\uFEFF/,''));
 expect(probe.PID).toBe(searchBefore.PID);
 expect(new Date(probe.CreationDate).getTime()).toBe(new Date(searchBefore.CreationDate).getTime());
 expect(probe.CommandLine).toBe(searchBefore.CommandLine);
 const searchHealth=await fetch('http://127.0.0.1:18108/actuator/health');
 expect(searchHealth.status).toBe(200);expect((await searchHealth.json()).status).toBe('UP');
 fs.writeFileSync(path.join(env.run,'browser-search-survival.json'),JSON.stringify({before:searchBefore,after:probe,health:'UP'},null,2));
 fs.writeFileSync(path.join(env.run,'browser-restart-comparison.json'),JSON.stringify({before,after:current},null,2));
 const requests=()=>fs.readFileSync(path.join(env.run,'egress.jsonl'),'utf8').trim().split('\n').filter(Boolean).map(row=>JSON.parse(row)).filter(row=>row.kind==='llm').length;
 const llmRequestsBefore=requests();
 await openChat('support');
 await c('waitText','shop',{text:prior.messages.at(-1).userMessage});
 const after=database('restart-recovered');
 for(const message of prior.messages){
  const saved=after.messages.find(row=>row.messageId===message.messageId);
  expect(saved).toEqual(message);
 }
 expect(after.cases.find(row=>row.caseId===primary.caseId).state).toBe('ARCHIVED');
 expect(after.audit.filter(row=>row.caseId===primary.caseId)).toEqual(prior.audit.filter(row=>row.caseId===primary.caseId));
 await send('查看售后申请进度');
 await userDetail(primary.caseId);
 // A long history exceeds the broker's diagnostic body excerpt. Assert the
 // actual current case region in the browser, not a truncated text transport.
 await c('waitVisible','shop',{locator:{css:`.msg-group:last-child section[aria-label="售后申请与处理进度"]:has-text("${primary.caseId}"):has-text("本地模拟退款：成功"):has-text("案件已归档"):has-text("不代表资金到账")`}});
 expect(requests()).toBe(llmRequestsBefore);
 await c('screenshot','shop',{name:'20-agent-restart-case-and-history-restored'});
 const errorsFile=path.join(env.run,'browser-artifacts/page-errors.jsonl');
 const errorsBefore=fs.existsSync(errorsFile)?fs.readFileSync(errorsFile,'utf8').trim().split('\n').filter(Boolean).length:0;
 const fixtures=readLaunchJson(path.join(env.run,'fixture-manifest.json'));
 await c('goto','shop',{path:'/order/'+fixtures.orders.find(row=>row.userId===env.plan.userB).orderId});
 await c('waitText','shop',{text:'订单不存在或无权查看'});
 const errorsAfter=fs.existsSync(errorsFile)?fs.readFileSync(errorsFile,'utf8').trim().split('\n').filter(Boolean).length:0;
 expect(errorsAfter).toBe(errorsBefore);
 fs.writeFileSync(path.join(env.run,'browser-order-error-handled.json'),JSON.stringify({denialDisplayed:true,pageErrorsBefore:errorsBefore,pageErrorsAfter:errorsAfter,unhandledRejectionsAdded:0},null,2));
});
