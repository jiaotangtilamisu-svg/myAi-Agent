import fs from 'node:fs/promises';
import path from 'node:path';
import { command } from '../lib/session.mjs';
import { loadEnvironment } from '../lib/environment.mjs';
const env=loadEnvironment();
await command({op:'close'});
const deadline=Date.now()+300000; // Existing long videos may need time to finalize.
while(Date.now()<deadline){
 const state=JSON.parse(await fs.readFile(path.join(env.control,'status.json'),'utf8'));
 if(state.state==='CLOSED'){
  if(state.videos?.length!==2||state.videos.some(v=>v.sessionStartedAt!==state.startedAt))throw new Error('CURRENT_SESSION_VIDEO_PROOF_REQUIRED');
  for(const name of ['shop','admin']){
   const file=path.join(env.run,'browser-artifacts',name+'-business.webm');
   if((await fs.stat(file)).size<1000)throw new Error('BUSINESS_VIDEO_MISSING_OR_EMPTY');
  }
  console.log('Only project Chromium closed. Two business videos finalized.');process.exit(0);
 }
 await new Promise(resolve=>setTimeout(resolve,500));
}
throw new Error('VIDEO_FINALIZATION_TIMEOUT_NO_AUTOMATIC_RELAUNCH');
