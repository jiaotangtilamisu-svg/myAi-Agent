import { defineConfig } from '@playwright/test';
import path from 'node:path';
import { loadEnvironment } from './lib/environment.mjs';
const env = loadEnvironment();
export default defineConfig({
  testDir: './tests', testMatch: '**/*.spec.mjs', workers: 1, fullyParallel: false,
  retries: 0, timeout: 300000, expect: { timeout: 15000 },
  outputDir: path.join(env.run, 'playwright-results'),
  reporter: [['list'], ['json', { outputFile: path.join(env.run, 'playwright-results.json') }],
    ['html', { outputFolder: path.join(env.run, 'playwright-report'), open: 'never' }]],
  // Business interaction uses the live project-owned session; no saved auth
  // state is imported/exported. Network traces are off to avoid persisting auth.
  use: { headless: false, trace: 'off', screenshot: 'off', video: 'off' },
  metadata: { shopBaseURL: env.shop, adminBaseURL: env.admin, isolationRun: env.plan.runId }
  ,projects: [
    { name: 'business', testIgnore: '**/recovery.spec.mjs' },
    { name: 'recovery', testMatch: '**/recovery.spec.mjs', dependencies: ['business'] }
  ]
});
