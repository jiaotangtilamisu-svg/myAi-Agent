import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { loadEnvironment } from './environment.mjs';
export async function command(input, timeout = 100000) {
  const { control } = loadEnvironment();
  const id = crypto.randomUUID();
  const file = path.join(control, `command-${id}.json`);
  await fs.mkdir(control, { recursive: true });
  await fs.writeFile(file + '.tmp', JSON.stringify(input)); await fs.rename(file + '.tmp', file);
  const start = Date.now(); const result = file.replace('command-', 'result-');
  while (Date.now() - start < timeout) {
    const raw = await fs.readFile(result, 'utf8').catch(() => null);
    if (raw) { const data = JSON.parse(raw); if (!data.ok) throw new Error(`${data.errorType}: ${data.message}`); return data.data; }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error('PROJECT_BROWSER_SESSION_NOT_RESPONDING_NO_AUTOMATIC_RESTART');
}
