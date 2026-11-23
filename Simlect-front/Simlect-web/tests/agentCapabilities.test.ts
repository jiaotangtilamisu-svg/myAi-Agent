import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { AGENT_CAPABILITIES, quickQuestions } from '../src/utils/agentCapabilities.ts';

for (const mode of ['support', 'shopping', 'supervisor'] as const) {
  test(`${mode} exposes only mapped read capabilities and complete original text`, () => {
    const tips = quickQuestions(mode);
    assert.ok(tips.length > 0);
    assert.equal(new Set(tips).size, tips.length);
    for (const tip of tips) {
      const entry = AGENT_CAPABILITIES.find(c => c.text === tip)!;
      assert.ok(entry.tool);
      assert.ok((entry.modes as readonly string[]).includes(mode));
      assert.doesNotMatch(tip, /会员|签到|热销|收藏|支付|取消订单/);
    }
  });
}
test('quick click sends original text through common mode-aware sender', () => {
  const source = readFileSync(new URL('../src/views/agent/AgentSendPanel.vue', import.meta.url), 'utf8');
  const click = source.slice(source.indexOf('const applyTip ='), source.indexOf('const dispatchSend ='));
  assert.match(click, /input\.value = tip/);
  assert.match(click, /void sendMessage\(\)/);
  assert.match(source, /agentApi.sendMessage\(text, fromProduct, consultProductId, agentMode.value\)/);
});
