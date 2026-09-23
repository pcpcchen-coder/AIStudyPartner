import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: './tests/browser', timeout: 30000, fullyParallel: false,
  use: { baseURL: 'http://127.0.0.1:8765', viewport: { width: 1440, height: 1100 },
    launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] } },
  webServer: { command: 'uv run uvicorn study_partner.app:app --host 127.0.0.1 --port 8765 --no-access-log',
    url: 'http://127.0.0.1:8765/api/config', reuseExistingServer: !process.env.CI },
});
