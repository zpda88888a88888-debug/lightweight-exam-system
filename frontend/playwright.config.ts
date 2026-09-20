import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright 配置（测试方案第 10 阶段 8：E2E 主干流程，准出标准 E8）。
 *
 * 只保留一条主干流程，不追求分支覆盖（测试方案风险 R6）。
 *
 * 两种运行方式：
 *   1) 默认：自动拉起后端 + Vite 开发服务器（若已在运行则复用）。
 *   2) 指定 E2E_BASE_URL：对**已部署的运行实例**跑同一条主干流程
 *      （用于验证离线部署包，此时不再拉起任何服务）：
 *        E2E_BASE_URL=http://127.0.0.1:8080 ADMIN_PASSWORD=xxx npm run test:e2e
 */
const externalBaseUrl = process.env.E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: externalBaseUrl ?? 'http://localhost:5173',
    headless: true,
    actionTimeout: 15_000,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: externalBaseUrl
    ? undefined
    : [
        {
          command:
            'cd ../backend && EXAM_DB_PATH=/tmp/exam-e2e/exam.db ADMIN_USERNAME=admin ' +
            'ADMIN_PASSWORD=changeme TOKEN_SECRET=e2e-secret ' +
            '.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level warning',
          url: 'http://127.0.0.1:8000/api/health',
          reuseExistingServer: true,
          timeout: 120_000,
        },
        {
          command: 'npx vite --port 5173 --strictPort',
          url: 'http://localhost:5173/',
          reuseExistingServer: true,
          timeout: 120_000,
        },
      ],
})
