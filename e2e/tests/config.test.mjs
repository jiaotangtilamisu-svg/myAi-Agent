import { test } from 'node:test';
import assert from 'node:assert/strict';
import { validateAddress, loadEnvironment } from '../lib/environment.mjs';
test('writable browser tests reject production ports and arbitrary origins', () => {
  for (const url of ['http://127.0.0.1:6001', 'http://127.0.0.2:6002/admin/', 'https://simlect.com', 'http://127.0.0.2:16001@evil.invalid'])
    assert.throws(() => validateAddress(url, 16001));
});
test('only explicitly provisioned isolated URLs are accepted', () => {
  validateAddress('http://127.0.0.2:16001', 16001);
  validateAddress('http://127.0.0.2:16002/admin/', 16002);
  assert.throws(() => validateAddress('http://127.0.0.2:16001', 16002));
  assert.match(loadEnvironment().plan.databases.order, /^q34_[a-f0-9]{10}_order$/);
});
