# 前端（考生端 + 管理端）

Vue 3 + Vite + TypeScript。对接 `backend/` 已完成的 API。

- **考生端**：`index.html` → 面向手机，扫码/输邀请码进入。
- **管理端**：`admin.html` → 面向桌面，独立页面（架构要求「独立管理员页面」）。

---

## 1. 快速开始

```bash
cd frontend
npm install

# 终端 1：启动后端（默认 8000）
cd ../backend && EXAM_DB_PATH=./data/exam.db ADMIN_PASSWORD=changeme \
  .venv/bin/uvicorn app.main:app --port 8000

# 终端 2：启动前端开发服务器（5173，/api 自动代理到 8000）
cd frontend && npm run dev
```

| 入口 | 地址 |
|---|---|
| 考生端 | http://localhost:5173/ |
| 管理端 | http://localhost:5173/admin.html |

> ⚠️ 用 `localhost` 而不是 `127.0.0.1`：Vite 8 默认绑定 IPv6 的 localhost，
> 用 `127.0.0.1` 会连不上。

---

## 2. 构建与部署

```bash
npm run build      # 产物在 dist/
```

`dist/` 是纯静态文件，直接用任意静态服务器托管即可（Nginx / `vite preview`）。
**路由使用 hash 模式**（`#/exam`、`#/exams`），因此刷新任意页面都不会 404，
不需要服务器 rewrite 规则。

构建产物：

| 入口 | 体积（gzip） |
|---|---|
| 考生端 | ~14 kB + 共享 ~94 kB（约 42 kB gzip） |
| 管理端 | ~581 kB（约 196 kB gzip，主要是 ECharts） |

考生端刻意保持很小，因为它要在手机流量下打开。

---

## 3. 测试

```bash
npm run typecheck   # 类型检查（vue-tsc）
npm test            # Vitest 单元测试（159 个用例）
npm run test:e2e    # Playwright 浏览器 E2E（主干流程）
npm run verify      # typecheck + 单测 + 构建
```

### E2E 前置

Playwright 需要浏览器二进制：

```bash
npx playwright install chromium
```

若 `~/Library/Caches/ms-playwright` 不可写（例如受限环境），
可把浏览器装到可写目录：

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npx playwright install chromium
PLAYWRIGHT_BROWSERS_PATH=/tmp/pw-browsers npm run test:e2e
```

E2E 会自动拉起后端与前端开发服务器（`playwright.config.ts` 的 `webServer`），
若已在运行则复用；用时间戳生成唯一数据，可重复执行。

---

## 4. 目录结构

```
frontend/
├── index.html                 # 考生端入口
├── admin.html                 # 管理端入口
├── vite.config.ts             # 构建 + Vitest 配置 + /api 代理
├── playwright.config.ts       # E2E 配置（含 webServer 编排）
├── e2e/main-flow.spec.ts      # 主干流程 E2E
├── tests/                     # Vitest 单元/组件测试
└── src/
    ├── api/client.ts          # 类型化 API 客户端（与后端路由一一对应）
    ├── lib/                   # 可独立测试的纯逻辑
    │   ├── time.ts            # 服务端时间解析、倒计时、本地↔UTC 转换
    │   ├── answers.ts         # 选答语义、未答题计数、交卷载荷
    │   ├── answerStore.ts     # IndexedDB 答案持久化
    │   ├── retry.ts           # 提交失败重试（2s/4s/8s）
    │   ├── switchTracker.ts   # 切屏记录
    │   ├── questionTypes.ts   # 题型定义
    │   ├── examStatus.ts      # 考试状态展示映射
    │   └── download.ts        # 导出下载
    ├── styles/app.css
    ├── candidate/             # 考生端
    │   ├── main.ts            # 路由 + 守卫
    │   ├── session.ts         # 会话（localStorage）
    │   ├── views/             # 登录 / 等待 / 答题 / 完成
    │   └── components/AnswerSheet.vue
    └── admin/                 # 管理端
        ├── main.ts
        ├── session.ts
        ├── views/             # 登录 / 考试列表 / 考试详情 / 题库
        └── components/        # 题目表单 / ECharts 封装
```

---

## 5. 关键实现说明

这些点容易写错，已在 `docs/设计决策与规格偏差.md` 中记录理由：

1. **服务端时间是 naive UTC**：后端返回 `"2026-09-19T11:00:00"`（无 `Z`）。
   `new Date(...)` 会按本地时区解析，在东八区直接偏差 8 小时。
   所有解析都走 `lib/time.ts::parseServerTime`。
2. **提交给后端的时间必须去掉时区**：`lib/time.ts::localInputToServer` 把
   `datetime-local` 的本地时间转成 naive UTC，避免库里混入 aware datetime。
3. **答案不做防抖**：每次选择立即写 IndexedDB。
   防抖会留下「刚作答就刷新 → 答案丢失」的窗口（E2E 复现过）。
4. **恢复答案用合并而非覆盖**：IndexedDB 读取是异步的，
   若考生在读取完成前已作答，直接覆盖会丢掉这几秒的操作。
5. **刷新后自动重拉试卷**：`session.questions` 不持久化，
   进入 `/exam` 时若为空会自动 `getPaper`（服务端按考生种子生成，内容与刷新前一致）。
6. **切屏只在「变为隐藏」时计一次**：避免同一次切屏被多条事件重复计数。
7. **判断题选项不打乱**，单选/多选按考生种子（手机号+邀请码）确定性乱序，
   刷新后顺序不变。
