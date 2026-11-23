import fs from 'node:fs';

// Windows PowerShell 5 writes a UTF-8 BOM with Set-Content -Encoding utf8.
export function readLaunchJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
}
