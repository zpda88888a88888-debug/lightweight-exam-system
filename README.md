# 极轻量级客观题考试系统

内网、单机、低运维的客观题（单选 / 多选 / 判断）考试平台。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)
![Node](https://img.shields.io/badge/node-16%2B-brightgreen.svg)
![Vue](https://img.shields.io/badge/vue-3-42b883.svg)

**核心特征：考试过程中考生端与后端零交互。** 答案存浏览器 IndexedDB，交卷时一次性提交，
服务端统一判分，管理员导出成绩 CSV 后线下告知考生。

## 功能特性

**考生端**（手机）

- 手机号 + 邀请码登录，校验时间窗口与交卷状态
- 一页到底答题，顶部固定倒计时（统一截止时间，晚进不补时）
- 答案实时写入 IndexedDB，刷新 / 断网 / 浏览器崩溃均可恢复
- 答题卡显示已答未答、点击跳题
- 选项内容按考生独立乱序（防抄袭），但标号恒为 A、B、C、D
- 切屏记录次数与时间点；到点自动交卷
- 交卷失败自动重试 3 次（2s / 4s / 8s），仍失败给出手动「重试提交」，答案不丢

**管理端**（桌面）

- **考试管理**：按状态 / 选聘编号 / 名称 / 开考时间查询，建草稿、发布、归档
- **考生管理**：按考试场次导入名单、生成邀请码，查看看谁没来 / 谁在考试 / 谁已交卷
- **试卷管理**：只读查看每场考试抽中的题目与正确答案
- **题库管理**：增删改查、JSON 批量导入、CSV 导出、题目统计（上次被抽中 / 累计正确率）
- **成绩统计**：平均分、及格率、题目标错率图表，成绩 CSV 导出

**工程**

- 判分引擎分支覆盖率 100%，变异测试 M1–M10 全部被捕获
- 200 并发交卷压测通过
- 一键生成 Linux ARM64 离线部署包（目标服务器无需 pip / npm / Docker / 外网）

## 文档导航

| 文档 | 读者 | 内容 |
|---|---|---|
| [<small>考生使用手册</small>](<docs/使用手册-考生.md>) | 考生 | 登录、答题、交卷、常见问题 |
| [<small>管理员使用手册</small>](<docs/使用手册-管理员.md>) | 管理员 | 四个模块操作、关键规则、考试当天检查清单 |
| [<small>题库模板</small>](<docs/题库模板.md>) | 出题人 | 让 AI 按格式批量出题 |
| [<small>部署说明</small>](<deploy/package/README-部署.md>) | 运维 | 内网服务器离线部署 |
| [<small>规格说明</small>](<极轻量级客观题考试系统— 规格说明.md>) | 所有人 | 系统"要做什么" |
| [<small>技术架构</small>](<极轻量级客观题考试系统— 技术架构.md>) | 开发 | 数据模型、API、关键设计 |
| [<small>测试方案</small>](<极轻量级客观题考试系统 — 测试方案.md>) | 开发 | 测试策略与准出标准 |
| [<small>UI/UX 设计规范</small>](<docs/UI-UX-设计规范.md>) | 开发 | 界面、交互与文案规范 |
| [<small>变更记录</small>](<docs/变更记录.md>) | 所有人 | 每轮试用反馈的变更轨迹 |
| [<small>设计决策与规格偏差</small>](<docs/设计决策与规格偏差.md>) | 开发 | 口径澄清与实现取舍 |
| [<small>测试追溯矩阵</small>](<docs/测试追溯矩阵.md>) | 开发 / QA | 规格 → 测试逐条追溯 |
| [<small>第三方组件与许可证</small>](THIRD-PARTY-NOTICES.md) | 所有人 | 依赖许可证审计 |

---

## 1. 当前进度

| 部分 | 状态 | 说明 |
|---|---|---|
| **后端** | ✅ 已完成 | FastAPI + SQLModel + SQLite WAL，覆盖测试方案第 10 节阶段 1–7 |
| **后端测试套件** | ✅ 已完成 | **250** 个用例全部通过；判分引擎分支覆盖率 100%；变异测试 M1–M10 全部被捕获 |
| **前端（考生端 + 管理端）** | ✅ 已完成 | Vue3 + Vite + TS；**159** 个 Vitest 用例 + Playwright 浏览器 E2E 主干流程 |
| **离线部署包（Linux ARM64）** | ✅ 已完成 | 自带全部 aarch64 依赖，服务器无需 pip / npm / Docker / 外网；见 `deploy/package/README-部署.md` |
| Docker / Nginx 编排 | ⛔ 未做（不需要） | 部署包用零依赖 Node 服务器承担静态托管与反向代理，无需 Nginx；无 Docker 环境亦可运行 |

系统已可端到端跑通：管理员建题库 → 建考试 → 导入名单 → 生成邀请码 → 发布冻结 →
考生登录答题 → 交卷判分 → 统计与导出。

---

## 2. 快速开始（本机运行，无需 Docker）

### 2.1 一条命令试用（推荐先这样点一点）

```bash
./dev.sh
```

脚本会自动：装依赖（首次）→ 起后端 → **播种演示数据** → 起前端 → 打开浏览器。

不用手工建题建考试，起来就有东西可点：

| 入口 | 地址 | 账号 |
|---|---|---|
| 管理端 | http://localhost:5173/admin.html | `admin` / `admin123` |
| 考生端 | http://localhost:5173/ | 手机号 + 邀请码（脚本会打印） |

演示数据包含：10 道题（单选/多选/判断，两个标签）、1 场**正在进行**的考试、
8 名考生与邀请码、6 人已交卷（分数 100/75/65/60/20/10）、2 人缺考。
因此统计图表、成绩导出、及格线规则都有真实数据可看。

- 按 `Ctrl+C` 停止。
- 想换个身份重新答题：用打印出来的两名「缺考」考生，
  或执行 `./dev.sh --reset` 重建演示数据。
- SSH / 无界面环境：`./dev.sh --no-open`。

> 这是**开发/试用模式**（Vite 热更新 + 本地 venv）。
> 正式部署到内网服务器请用 `deploy/` 下的离线包，见 2.4。

### 2.2 手动分别启动后端

```bash
cd backend

# 1) 创建虚拟环境并安装依赖
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2) 启动服务（管理员账号密码从环境变量读取）
EXAM_DB_PATH=./data/exam.db \
ADMIN_USERNAME=admin \
ADMIN_PASSWORD=changeme \
TOKEN_SECRET=请替换为随机长字符串 \
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

访问 `http://127.0.0.1:8000/docs` 可看到自动生成的 API 文档。

### 2.3 手动分别启动前端

```bash
cd frontend
npm install
npm run dev
```

| 入口 | 地址 |
|---|---|
| 考生端 | http://localhost:5173/ |
| 管理端 | http://localhost:5173/admin.html |

> ⚠️ 请用 `localhost`：Vite 8 默认绑定 IPv6 localhost，`127.0.0.1` 会连不上。
> 开发服务器已把 `/api` 代理到 `127.0.0.1:8000`，无需处理 CORS。

### 2.4 内网服务器部署（离线包）

面向**内网、无外网、无 pip、无 npm、无 Docker** 的 Linux ARM64 服务器：

```bash
# 开发机构建离线包
./deploy/build.sh
# 产物：deploy/out/exam-system-1.0.0-linux-arm64.tar.gz

# —— 以下在目标服务器执行 ——
tar -xzf exam-system-1.0.0-linux-arm64.tar.gz
cd exam-system-1.0.0-linux-arm64
./install.sh          # 不联网，自带全部 aarch64 依赖
./manage.sh doctor    # 环境自检
./manage.sh start
```

服务器只需 **Python 3.10/3.11/3.12** 与 **Node 16+**（均为系统自带或已存在）。
完整说明见 `deploy/package/README-部署.md`。

### 2.5 冒烟验证

```bash
# 后端：对真实运行中的服务跑一遍主干流程（34 项断言）
cd backend && .venv/bin/python scripts/smoke_e2e.py --base-url http://127.0.0.1:8000

# 前端：浏览器端到端主干流程（自动拉起前后端）
cd frontend && npm run test:e2e

# 对已部署的实例跑同一条浏览器 E2E（不拉起任何服务）
cd frontend && E2E_BASE_URL=http://127.0.0.1:8080 ADMIN_PASSWORD=xxx npm run test:e2e
```

---

## 3. 运行测试

### 后端

```bash
cd backend

.venv/bin/python -m pytest tests/ -v                  # 全部用例（含 200 并发压测）
.venv/bin/python -m pytest tests/ -m "not slow"       # 跳过并发压测，快速回归
.venv/bin/python -m pytest tests/ --cov=app --cov-branch   # 覆盖率
.venv/bin/python scripts/mutation_check.py            # 变异测试 M1–M10，并生成报告
```

| 命令 | 用途 |
|---|---|
| `pytest tests/` | 250 个用例，约 18 秒 |
| `pytest tests/ -m "not slow"` | 跳过 200 并发压测 |
| `scripts/mutation_check.py` | 逐个注入 M1–M10 错误，验证测试确实能捕获 |
| `scripts/smoke_e2e.py` | 对真实后端服务做端到端冒烟 |

### 前端

```bash
cd frontend

npm run typecheck    # vue-tsc 类型检查
npm test             # Vitest 单元/组件测试（159 个用例）
npm run test:e2e     # Playwright 浏览器 E2E（主干流程）
npm run verify       # typecheck + 单测 + 构建
npm run build        # 生产构建 → dist/
```

---

## 4. 目录结构

```
os-online-test-project/
├── README.md                      # 本文件
├── LICENSE                        # MIT 许可证
├── THIRD-PARTY-NOTICES.md         # 第三方依赖许可证审计
├── docs/
│   ├── 测试追溯矩阵.md              # 规格 → 测试 的逐条追溯（准出 E7）
│   ├── UI-UX-设计规范.md            # 界面/交互/文案规范
│   ├── 变更记录.md                  # 每轮试用反馈带来的变更轨迹（CH-xxx）
│   ├── 使用手册-考生.md             # 给考生的使用说明（可直接转发/打印）
│   ├── 使用手册-管理员.md           # 给管理员的操作手册（含考试当天检查清单）
│   ├── 题库模板.md                  # 让 AI 按格式批量出题（含指令模板与自检清单）
│   └── 设计决策与规格偏差.md         # 口径澄清与实现取舍记录
├── 极轻量级客观题考试系统— 规格说明.md   # 输入资产（系统"要做什么"）
├── 极轻量级客观题考试系统— 技术架构.md   # 输入资产（数据模型与 API）
├── 极轻量级客观题考试系统 — 测试方案.md  # 输入资产（测试策略与准出）
├── backend/
│   ├── app/
│   │   ├── main.py            # 应用工厂、依赖注入、异常映射
│   │   ├── config.py          # 环境变量配置、状态常量、导出列定义
│   │   ├── clock.py           # 可注入时钟（禁用裸 datetime.now）
│   │   ├── db.py              # 引擎、WAL/busy_timeout、NullPool
│   │   ├── models.py          # SQLModel 七张表
│   │   ├── schemas.py         # 请求/响应模型（试卷字段集由类型固定）
│   │   ├── domain.py          # 考试状态机、时间窗口门禁
│   │   ├── scoring.py         # 判分引擎（纯函数）
│   │   ├── stats.py           # 及格线、标错率（纯函数）
│   │   ├── shuffling.py       # 选项乱序（确定性种子）
│   │   ├── security.py        # HMAC token、邀请码、密码校验
│   │   ├── services.py        # 组卷发布、交卷判分、名单、统计导出
│   │   ├── backup.py          # SQLite 备份/恢复/保留策略 + CLI
│   │   └── routers/
│   │       ├── candidate.py   # 考生端 API
│   │       └── admin.py       # 管理端 API
│   ├── tests/                 # pytest 套件（19 个测试文件 / 250 用例）
│   ├── scripts/
│   │   ├── mutation_check.py  # 变异测试执行器
│   │   └── smoke_e2e.py       # 端到端冒烟
│   ├── requirements.txt
│   ├── pytest.ini
│   └── mutation-report.md     # 变异测试报告（脚本生成）
└── frontend/
    ├── index.html             # 考生端入口
    ├── admin.html             # 管理端入口
    ├── vite.config.ts         # 构建 + Vitest 配置 + /api 代理
    ├── playwright.config.ts   # E2E 配置（自动拉起前后端）
    ├── e2e/main-flow.spec.ts  # 浏览器主干流程 E2E
    ├── tests/                 # Vitest 套件（13 个文件 / 159 用例）
    └── src/
        ├── api/client.ts      # 类型化 API 客户端
        ├── lib/               # 可独立测试的纯逻辑（时间/答案/存储/重试/切屏）
        ├── candidate/         # 考生端：登录 / 等待 / 答题 / 完成
        └── admin/             # 管理端：登录 / 考试 / 详情 / 题库
```

---

## 5. 接口一览

### 考生端

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/join` | 手机号 + 邀请码登录；返回 token 与考试信息 |
| POST | `/api/exams/{id}/attempts` | 创建 attempt（已存在则复用）；仅进行中 |
| GET | `/api/exams/{id}/paper` | 拉取试卷（**绝不含答案与解析**）；仅进行中 |
| POST | `/api/attempts/{id}/submit` | 一次性交卷，服务端事务内判分，幂等 |

### 管理端

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/admin/login` | 账号 + 密码（环境变量，单超管） |
| GET | `/api/admin/questions` | 题库列表（题型/标签/关键词筛选），含每题统计（上次抽中、累计正确率） |
| GET | `/api/admin/questions/export` | 导出题库 CSV（列定义见规格 7.4） |
| POST | `/api/admin/questions` | 单题新增 |
| PUT/DELETE | `/api/admin/questions/{id}` | 单题编辑 / 删除 |
| POST | `/api/admin/questions/import` | JSON 批量导入，按 `id` upsert |
| GET | `/api/admin/tags` | 题库标签及可用题数（组卷规则的封闭选项数据源） |
| GET | `/api/admin/exams` | 考试列表；支持 `status` / `recruitment_no` / `title` / `start_from` / `start_to` 查询 |
| POST | `/api/admin/exams` | 创建考试草稿 |
| PUT/DELETE | `/api/admin/exams/{id}` | 仅草稿可改 / 可删 |
| POST | `/api/admin/exams/{id}/publish` | 校验题量 → 随机抽题 → 生成快照 → 冻结 |
| POST | `/api/admin/exams/{id}/archive` | 归档 |
| GET | `/api/admin/exams/{id}/candidates` | 名单与邀请码 |
| POST | `/api/admin/exams/{id}/candidates/import` | CSV 导入（`手机号,姓名,身份证号`） |
| POST | `/api/admin/exams/{id}/candidates/generate` | 生成邀请码（全部覆盖，需 `confirm`） |
| GET | `/api/admin/exams/{id}/candidates/export` | 邀请码分发 CSV |
| GET | `/api/admin/exams/{id}/results` | 成绩列表 |
| GET | `/api/admin/exams/{id}/results/export` | 成绩 CSV（13 列，含缺考） |
| GET | `/api/admin/exams/{id}/stats` | 平均分 / 及格率 / 题目标错率 |
| GET | `/api/admin/exams/{id}/paper` | 试卷快照只读视图（含正确答案与分值，仅管理端） |

### 关键拒绝语义

| 场景 | HTTP | 提示 |
|---|---|---|
| 未开始 | 409 | 考试未开始 |
| 已结束 | 409 | 考试已结束 |
| 已交卷再次登录 | 409 | 你已交卷，考试结束 |
| 发布后修改（冻结） | 409 | 考试已发布，内容已冻结，不可修改 |
| 邀请码/手机号不匹配 | 403 | 手机号或邀请码错误 |
| 缺少或伪造 token | 401 | 缺少认证信息 / token 签名不匹配 |

---

## 6. 准出标准达成情况（测试方案第 7 节）

| 编号 | 标准 | 状态 | 证据 |
|---|---|---|---|
| E1 | 判分引擎分支覆盖率 100% | ✅ | `app/scoring.py` 39 语句 / 20 分支 / 0 未覆盖 |
| E2 | 所有 P0 模块不变量断言通过 | ✅ | 250 用例全绿，整体分支覆盖率 **91%** |
| E3 | 变异测试 M1–M10 全部被捕获 | ✅ | `scripts/mutation_check.py` → 10/10，报告见 `mutation-report.md` |
| E4 | 试卷接口契约测试通过 | ✅ | `tests/test_paper_contract.py`（递归字段检查 + 精确字段集） |
| E5 | 幂等测试通过（含并发） | ✅ | `tests/test_attempt_idempotency.py`（含 2 线程同 attempt 并发） |
| E6 | 200 并发交卷无数据丢失 | ✅ | `tests/test_concurrency.py`，200/200 成功、answers 恰好 200 行 |
| E7 | 追溯矩阵无空白项 | ✅ | `docs/测试追溯矩阵.md` |
| E8 | E2E 主干流程通过 | ✅ | Playwright 浏览器 E2E：`frontend/e2e/main-flow.spec.ts`（建题→发布→考生答题→刷新恢复→交卷→统计），自动拉起前后端 |
| E9 | 规格冲突项已澄清且测试与口径一致 | ✅ | R1 已确认按 upsert，见 `docs/设计决策与规格偏差.md` |
| E10 | 核心模块已 REFACTOR 且测试保持绿色 | ✅ | 见下节「重构记录」 |

### 重构记录（E10）

以下重构均在测试保护下完成，每次重构后全绿：

1. **并发交卷正确性**：压力测试暴露两次重复判分后，把「条件更新认领」+「锁内丢弃陈旧读快照」引入 `submit_attempt`，测试从 17 项扩展到覆盖并发场景。
2. **连接池改造**：200 并发压测暴露默认 QueuePool 容量不足（5+10 连接），改用 `NullPool`，压测耗时从 124 秒（含大量失败）降到 6 秒（全部成功）。
3. **快照冻结补强**：发现引用式快照会被题库改动穿透，新增 `_ensure_question_mutable` 守卫，使架构 9.6「修改题库不影响已发布考试」成立。
4. **统计分值读取**：移除模块级分值为缓存（会跨测试库串数据），改为在 `compute_stats` 内一次性构建映射。

---

## 7. 数据与运维

- 数据库文件默认 `backend/data/exam.db`，可用 `EXAM_DB_PATH` 覆盖。
- SQLite 开启 **WAL**、`busy_timeout=5000`、`synchronous=NORMAL`、`foreign_keys=ON`。
- 备份（架构 11：每小时一次、保留 7 天）：

```bash
# 手动备份（考试前必做）
.venv/bin/python -m app.backup --db data/exam.db --out data/backups

# 恢复（会先另存 .pre-restore 副本）
.venv/bin/python -m app.backup --db data/exam.db --restore data/backups/exam-YYYYMMDD-HHMMSS.db

# 每小时自动备份（crontab -e）
0 * * * * cd /path/to/backend && .venv/bin/python -m app.backup --db data/exam.db --out data/backups
```

### 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `ADMIN_USERNAME` | `admin` | 超管账号 |
| `ADMIN_PASSWORD` | `changeme` | 超管密码（**上线必须修改**） |
| `TOKEN_SECRET` | 开发占位值 | token 签名密钥（**上线必须改为随机长串**） |
| `EXAM_DB_PATH` | `./data/exam.db` | SQLite 文件路径 |
| `TOKEN_TTL_SECONDS` | `43200` | token 有效期 |
| `INVITE_CODE_DIGITS` | `6` | 邀请码位数 |

---

## 8. 后续可做（非阻塞）

1. **发布离线包 Release**：`deploy/out/*.tar.gz`（约 19 MB）未纳入版本库
   （构建产物不应进 git）。若需要在服务器上直接下载，可发一个 GitHub Release 挂上去。
2. **持续集成**：目前全套测试靠本地命令执行（见第 3 节），
   可加 GitHub Actions 在提交时自动跑 `pytest` / `vitest` / `vue-tsc` / E2E。
3. **前端优化**：管理端 bundle 因 ECharts 约 581 kB（gzip 196 kB）。
   管理端是桌面端，影响有限；若要优化可改为按需异步加载图表组件。
4. **监控与告警**：当前日志写本地文件，可按需接入内网日志收集。

---

## 9. 明确不做（与规格一致）

考生查分入口、发布成绩流程、设备锁、考试中答案保存接口、定时任务扫描状态、
Redis / MQ / 微服务 / K8s、图片音频题目、多机构多租户。

---

## 10. 许可证

本项目采用 **MIT License**，详见 [LICENSE](LICENSE)。

第三方依赖全部为宽松许可证（MIT / BSD / Apache-2.0 / ISC / MPL-2.0 等），
**不含任何 GPL / AGPL / LGPL 传染性许可**，因此采用 MIT 无冲突。
完整的依赖清单与审计结论见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。

> 仓库内 `规格说明`、`技术架构`、`测试方案` 三份文档为项目负责人提供的输入资产，
> 随本项目一同以 MIT 授权；若其中含第三方受版权保护内容，对外分发前请自行确认。
