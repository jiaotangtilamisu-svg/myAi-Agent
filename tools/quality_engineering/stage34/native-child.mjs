// A normal detached Windows child process, not a job/security bypass.
// No CREATE_BREAKAWAY flags, privilege changes, or automatic service restarts.
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { readLaunchJson } from './native-spec.mjs';
const file=path.resolve(process.argv[2]);
const root=path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/,'$1')),'../../..');
const active=readLaunchJson(path.join(root,'.cache/stage34/active.json'));
const run=path.resolve(active.directory);
if(!file.startsWith(run+path.sep))throw new Error('Launch specification must belong to active test run');
const spec=readLaunchJson(file);
if(spec.executable!=='E:/JDK17/bin/java.exe'||!path.resolve(spec.cwd).startsWith(path.join(run,'build')+path.sep))throw new Error('Only copied-build isolated Java is supported');
const out=fs.openSync(path.join(spec.logs,'stdout.log'),'a');
const err=fs.openSync(path.join(spec.logs,'stderr.log'),'a');
const startedAt=new Date().toISOString();
const child=spawn(spec.executable,spec.args,{cwd:spec.cwd,env:process.env,detached:true,windowsHide:true,stdio:['ignore',out,err]});
const record={pid:child.pid,parentPid:process.pid,startedAt,detached:true,windowsHide:true,securityToken:'unchanged',autoRestart:false};
const target=path.join(spec.logs,'native-process.json');
fs.writeFileSync(target,JSON.stringify(record,null,2));
child.on('exit',(code,signal)=>fs.writeFileSync(target,JSON.stringify({...record,exitedAt:new Date().toISOString(),exitCode:code,exitHex:code===null?null:'0x'+(code>>>0).toString(16).padStart(8,'0'),signal},null,2)));
child.on('error',error=>{fs.writeFileSync(target,JSON.stringify({...record,errorType:error.constructor.name},null,2));process.exitCode=1;});
