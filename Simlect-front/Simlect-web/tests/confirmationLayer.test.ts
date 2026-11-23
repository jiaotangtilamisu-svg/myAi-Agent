import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('chat overlay leaves the standard confirmation layer above it', () => {
  const styles = fs.readFileSync(new URL('../src/styles/variables.scss', import.meta.url), 'utf8');
  const chat = Number(styles.match(/\$z-index-float-agent:\s*(\d+)/)?.[1]);
  assert.ok(chat > 1000, 'chat must remain above site navigation');
  assert.ok(chat < 2000, 'standard Element Plus confirmation must receive real pointer input');
});
