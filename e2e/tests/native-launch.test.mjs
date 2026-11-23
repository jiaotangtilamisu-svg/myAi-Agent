import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readLaunchJson } from '../../tools/quality_engineering/stage34/native-spec.mjs';

test('Windows launch specification accepts UTF-8 with or without BOM', () => {
  const dir = fs.mkdtempSync(fileURLToPath(new URL('../../.cache/stage34/native-test-', import.meta.url)));
  const file = path.join(dir, 'spec.json');
  try {
    for (const prefix of ['', '\uFEFF']) {
      fs.writeFileSync(file, prefix + JSON.stringify({ args: ['-jar', '中文路径.jar'] }));
      assert.deepEqual(readLaunchJson(file), { args: ['-jar', '中文路径.jar'] });
    }
    fs.writeFileSync(file, '\uFEFF{"broken":');
    assert.throws(() => readLaunchJson(file), SyntaxError);
  } finally { fs.unlinkSync(file); fs.rmdirSync(dir); }
});
