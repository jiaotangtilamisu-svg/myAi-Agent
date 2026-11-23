import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export function loadEnvironment() {
  const active = JSON.parse(fs.readFileSync(path.join(root, '.cache/stage34/active.json'), 'utf8'));
  const run = path.resolve(active.directory);
  if (!run.startsWith(path.join(root, '.cache/stage34') + path.sep)) throw new Error('INVALID_TEST_DIRECTORY');
  const plan = JSON.parse(fs.readFileSync(path.join(run, 'plan.json'), 'utf8'));
  const shop = process.env.E2E_SHOP_BASE_URL || `http://127.0.0.2:${plan.ports.web}`;
  const admin = process.env.E2E_ADMIN_BASE_URL || `http://127.0.0.2:${plan.ports['admin-ui']}/admin/`;
  validateAddress(shop, plan.ports.web);
  validateAddress(admin, plan.ports['admin-ui']);
  if (!/^q34_[a-f0-9]{10}$/.test(plan.rabbitVhost) || !fs.existsSync(path.join(run, 'isolation-verified.json'))) {
    throw new Error('PREVIOUS_ISOLATION_GATE_REQUIRED');
  }
  return { root, run, plan, shop, admin, control: path.join(run, 'browser-control') };
}
export function validateAddress(value, port) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.2' || Number(url.port) !== port ||
      ![16001, 16002].includes(port) || url.username || url.password || url.search || url.hash) {
    throw new Error('FORMAL_OR_UNRECOGNIZED_BROWSER_ADDRESS_REJECTED');
  }
}
