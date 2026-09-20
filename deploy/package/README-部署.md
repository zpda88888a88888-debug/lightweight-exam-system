# 极轻量级客观题考试系统 — 离线部署包（Linux / ARM64）

面向**内网、无外网、无 npm、无 pip、无 Docker** 的 Linux ARM64 服务器。
一个压缩包拷进去，两条命令跑起来。

---

## 1. 服务器要求

| 项 | 要求 | 说明 |
|---|---|---|
| 架构 | aarch64 / arm64 | 本包内置的是 ARM64 预编译依赖 |
| 操作系统 | Ubuntu 20.04+ / Debian 11+ 等主流发行版 | 需要 glibc（manylinux 标准） |
| **Python** | **3.10 / 3.11 / 3.12** | 系统自带即可，不需要 pip、不需要 venv |
| **Node** | **16 或更高**（推荐 18+） | 只用内置模块，**不需要 npm install** |
| 内存 | ≥ 512 MB | |
| 磁盘 | ≥ 1 GB 可用 | 数据库 + 备份 |

包内**自带全部 Python 依赖**（含 aarch64 二进制扩展），安装过程**完全不联网**。

检查一下：

```bash
python3 -V     # 期望 3.10 ~ 3.12
node -v        # 期望 v16 及以上
```

---

## 2. 安装（三步）

```bash
# 1) 解压
tar -xzf exam-system-1.0.0-linux-arm64.tar.gz
cd exam-system-1.0.0-linux-arm64

# 2) 安装依赖 + 生成配置（不联网）
./install.sh

# 3) 自检并启动
./manage.sh doctor
./manage.sh start
```

安装脚本会：

- 自动识别 python3 版本，从 `backend/wheelhouse/cpXXX/` 挑选对应依赖；
- **默认用「解压安装」**：把 wheel 当 zip 解压到 `backend/vendor/`，
  因此**完全不依赖 pip / venv**，也不受 Ubuntu 的 PEP 668 限制；
- 生成 `exam.env`（权限 600），其中包含**随机生成的 TOKEN_SECRET 和管理员密码**，
  安装结束时会打印出来，请立即记录。

启动后访问：

- 考生端 `http://<服务器IP>:8080/`
- 管理端 `http://<服务器IP>:8080/admin.html`

---

## 3. 目录结构

```
exam-system-1.0.0-linux-arm64/
├── install.sh              一次性安装：依赖 + 配置
├── manage.sh               start / stop / restart / status / doctor / backup / logs
├── exam.env                运行配置（安装时生成，权限 600）
├── server/
│   ├── server.js           零依赖 Node 服务：静态托管 + /api 反向代理
│   └── dist/               前端构建产物（考生端 index.html / 管理端 admin.html）
├── backend/
│   ├── app/                后端源码（FastAPI）
│   ├── wheelhouse/         预置依赖
│   │   ├── cp310/          Python 3.10 的 ARM64 依赖
│   │   ├── cp311/          Python 3.11 的 ARM64 依赖
│   │   └── cp312/          Python 3.12 的 ARM64 依赖
│   ├── vendor/             安装时生成：实际加载的依赖
│   ├── requirements-deploy.txt
│   └── scripts/
│       ├── smoke_e2e.py      端到端冒烟脚本（验证部署是否正常）
│       └── seed_demo.py      演示数据播种（可选：快速演示给同事看）
├── 使用手册-考生.md        发给考生的使用说明（可直接打印/转发）
├── 使用手册-管理员.md      管理端完整操作说明（含考试当天检查清单）
├── 题库模板.md             让 AI 按格式批量出题（含指令模板与自检清单）
├── systemd/
│   └── install-systemd.sh  可选：注册为开机自启服务
├── data/                   SQLite 数据库与备份
├── logs/                   运行日志
└── run/                    PID 文件
```

> **为什么用 Node 而不是 Nginx？**
> 你已有 Node 环境，而 `server.js` 只用 Node 内置模块就完成了「托管静态文件 + 反向代理 `/api`」，
> 于是不必再装 Nginx，也不会引入需要编译的 npm 包。

---

## 4. 日常运维

```bash
./manage.sh status     # 查看进程与健康检查
./manage.sh restart    # 改完 exam.env 后重启
./manage.sh logs       # 实时跟踪日志
./manage.sh backup     # 手动备份数据库
```

### 配置（exam.env）

| 变量 | 默认 | 说明 |
|---|---|---|
| `PORT` | `8080` | 对外端口。改成 80 需要 root 权限 |
| `HOST` | `0.0.0.0` | 对外监听地址 |
| `BACKEND_PORT` | `8000` | 后端端口（仅监听 127.0.0.1，不对外） |
| `ADMIN_USERNAME` | `admin` | 超管账号 |
| `ADMIN_PASSWORD` | 安装时随机生成 | **上线前请改成你自己的强密码** |
| `TOKEN_SECRET` | 安装时随机生成 | token 签名密钥，泄露等于可伪造登录态；不要外传 |
| `EXAM_DB_PATH` | `./data/exam.db` | SQLite 文件位置 |

改完执行 `./manage.sh restart` 生效。

### 开机自启（强烈建议）

考试期间最怕进程挂掉。用 systemd 可以在崩溃后自动拉起、开机自动启动：

```bash
sudo ./systemd/install-systemd.sh
```

它会注册 `exam-backend` 和 `exam-web` 两个服务。
卸载：`sudo ./systemd/install-systemd.sh uninstall`。

---

## 5. 备份（重要）

```bash
./manage.sh backup     # 备份到 data/backups/，自动保留最近 7 天
```

**考试前务必手动备份一次。** 建议再用 crontab 每小时备份：

```bash
crontab -e
# 加入（路径按实际修改）：
0 * * * * cd /opt/exam-system-1.0.0-linux-arm64 && ./manage.sh backup >> logs/backup.log 2>&1
```

备份文件请再复制一份到另一台机器或内网 NAS。

恢复（会先把现有库另存为 `.pre-restore`）：

```bash
PYTHONPATH=backend/vendor:backend python3 -m app.backup \
  --db data/exam.db --restore data/backups/exam-YYYYMMDD-HHMMSS.db
./manage.sh restart
```

---

## 6. 验证部署是否正常

```bash
# 应用自检
./manage.sh doctor

# 端到端冒烟：走完「建题 → 发布 → 考生答题 → 交卷 → 统计」主干流程
PYTHONPATH=backend/vendor:backend python3 backend/scripts/smoke_e2e.py \
  --base-url http://127.0.0.1:8080 --admin-password '<你的管理员密码>'
```

冒烟脚本只用 Python 标准库，不需要额外依赖。全部检查通过会输出
`冒烟通过：xx 项检查全部成功`。

> **提示**：冒烟脚本会在数据库里留下一条测试考试与 2 名测试考生（选聘编号带时间戳）。
> 建议在**部署完成后、正式导入名单前**执行；正式考试前可用 `./manage.sh backup`
> 备份，或删掉 `data/exam.db` 后重启以清空验证数据。

### 可选：灌入演示数据

如果只是想先给同事演示一遍（而不是正式考试），可以一条命令灌入演示数据：
10 道题、1 场**正在进行**的考试、8 名考生与邀请码、6 人已交卷的成绩：

```bash
PYTHONPATH=backend/vendor:backend python3 backend/scripts/seed_demo.py \
  --base-url http://127.0.0.1:8080 --admin-password '<你的管理员密码>'
```

脚本会打印每名考生的「手机号 + 邀请码」，可直接用来试考生端。
重复执行不会重复建数据；若已有演示考试过期，会自动用当前时间新建一场。

> ⚠️ 正式考试前请勿在生产库执行该脚本，或先确认不需要清空演示数据。

---

## 7. 升级

数据库与 `exam.env` 都在包外（`data/`、`exam.env`），升级不会动它们：

```bash
./manage.sh stop
cd ..
mv exam-system-1.0.0-linux-arm64 exam-system-1.0.0-linux-arm64.bak
tar -xzf exam-system-1.1.0-linux-arm64.tar.gz
cd exam-system-1.1.0-linux-arm64
cp ../exam-system-1.0.0-linux-arm64.bak/exam.env .
cp -R ../exam-system-1.0.0-linux-arm64.bak/data .
./install.sh && ./manage.sh start
```

---

## 8. 排障

| 现象 | 原因与处理 |
|---|---|
| `未找到 python3` | 安装 Python：`sudo apt install python3`（Ubuntu 自带） |
| `本安装包只内置了 3.10/3.11/3.12` | 服务器 Python 版本不匹配，装一个 3.11：`sudo apt install python3.11`，然后 `PYTHON=python3.11 ./install.sh` |
| 依赖自检失败 | 确认 Python 小版本与包匹配；把报错原文发给开发者 |
| `未找到 node` | 安装 Node（内网可用二进制压缩包解压后加入 PATH） |
| 启动后浏览器打不开 | `./manage.sh status` 看进程；`./manage.sh logs` 看报错；确认防火墙放行 8080 |
| 页面能开但接口报 502 | 后端没起来，看 `logs/backend.log` |
| 端口被占用 | 改 `exam.env` 的 `PORT`，`./manage.sh restart` |
| 想看更详细的请求日志 | `logs/backend.log` 记录了每个 API 请求 |

日志文件会持续增长，建议配置 logrotate 或定期清理 `logs/`。

---

## 9. 安全提醒

1. **务必修改 `exam.env` 里的 `ADMIN_PASSWORD`**（安装时虽已随机生成，
   但如果你把它贴到过聊天工具里，就等于泄露了）。
2. `exam.env` 含密钥，权限保持 600，不要提交到版本库。
3. 后端只监听 `127.0.0.1`，**不要**把它改成 `0.0.0.0`，否则绕过 Node 直连后端。
4. 内网也建议做访问控制：只允许考场网段访问 8080。
5. 试卷接口不会下发正确答案（已由后端契约测试保证），但仍应避免把管理员入口
   暴露给考生；如有条件，可用防火墙只放行管理网段访问 `/admin.html`。

---

## 10. 技术说明（为什么这样打包）

| 决策 | 原因 |
|---|---|
| 依赖随包分发（wheelhouse） | 服务器不能联网、不能 pip install；`pydantic-core`、`sqlalchemy` 是**编译好的 aarch64 原生扩展**，必须与目标平台匹配 |
| 默认「解压 wheel」而非 pip 安装 | 服务器上 pip 可能不存在（Ubuntu 24.04 默认无 pip），且 PEP 668 会拦截系统级安装。wheel 本质是 zip，解压 + `PYTHONPATH` 即可运行，**零工具依赖** |
| 用 `uvicorn` 而非 `uvicorn[standard]` | `[standard]` 会带入 uvloop / httptools / watchfiles 等编译扩展，在内网无编译环境下风险高；纯 Python 的 uvicorn 性能已足够（200 并发交卷已压测通过） |
| 一个发布版本带三份 Python 依赖 | 你的服务器 Python 版本未知，三份共约 19 MB，换来「拿起来就能装」 |
| Node 兼做静态服务与反向代理 | 你有 Node 且无需 npm；省掉 Nginx 安装与配置 |
| 前端 hash 路由 | 刷新任意页面都不会 404，静态服务器无需 rewrite 规则 |
| 后端保持 `--workers 1` | 交卷幂等依赖进程内 attempt 锁；单进程 + SQLite WAL 已通过 200 并发交卷压测 |
