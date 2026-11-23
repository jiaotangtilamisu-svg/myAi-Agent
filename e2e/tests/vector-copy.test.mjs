import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('ES9 source copy explicitly requests vectors and validates them before writing',()=>{
 const source=fs.readFileSync(new URL('../../tools/quality_engineering/stage34/copy_policy.py',import.meta.url),'utf8');
 assert.match(source,/'exclude_vectors':False/);
 assert.ok(source.indexOf('validate_vectors(docs)')<source.indexOf("request(guard,p['vectorIndex'],'PUT'"));
});
