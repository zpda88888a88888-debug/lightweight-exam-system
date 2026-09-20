#!/usr/bin/env bash
#
# 本地试用：一条命令把前后端都跑起来，并预置演示数据。
#
#   ./dev.sh           启动（首次会自动装依赖、播种演示数据）
#   ./dev.sh --reset   清空演示数据库后重新播种（想重新答题时用）
#
# 停止：在本终端按 Ctrl+C
#
# 说明：这是**开发/试用模式**（前端走 Vite 热更新，后端走本地 venv）。
# 正式对内网服务器部署请用 deploy/ 下的离线包。

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
DEMO_DB="$BASE_DIR/data/demo.db"
ADMIN_USER="admin"
ADMIN_PASSWORD="admin123"
TOKEN_SECRET="local-demo-secret"
LOG_DIR="$BASE_DIR/logs"

RESET=0
NO_OPEN=0
for arg in "$@"; do
  case "$arg" in
    --reset) RESET=1 ;;
    --no-open) NO_OPEN=1 ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[32m[dev]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[dev]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

mkdir -p "$LOG_DIR" "$BASE_DIR/data"

# ---------------- 环境准备 ----------------
command -v node >/dev/null 2>&1 || die "未找到 node，请先安装 Node 16+。"
command -v python3 >/dev/null 2>&1 || die "未找到 python3。"

if [ ! -x "$BASE_DIR/backend/.venv/bin/python" ]; then
  log "首次运行：创建 Python 虚拟环境并安装依赖…"
  python3 -m venv "$BASE_DIR/backend/.venv"
  "$BASE_DIR/backend/.venv/bin/pip" install --quiet -r "$BASE_DIR/backend/requirements.txt"
fi

if [ ! -d "$BASE_DIR/frontend/node_modules" ]; then
  log "首次运行：安装前端依赖（npm install）…"
  (cd "$BASE_DIR/frontend" && npm install --no-audit --no-fund)
fi

if [ "$RESET" -eq 1 ]; then
  log "重置演示数据库：$DEMO_DB"
  rm -f "$DEMO_DB" "$DEMO_DB-wal" "$DEMO_DB-shm"
fi

# ---------------- 退出清理 ----------------
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  echo
  log "正在停止服务…"
  [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
  [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  log "已停止。"
}
trap cleanup EXIT INT TERM

# ---------------- 启动后端 ----------------
log "启动后端 http://127.0.0.1:$BACKEND_PORT …"
(
  cd "$BASE_DIR/backend"
  EXAM_DB_PATH="$DEMO_DB" \
  ADMIN_USERNAME="$ADMIN_USER" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  TOKEN_SECRET="$TOKEN_SECRET" \
  exec .venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port "$BACKEND_PORT" --log-level warning
) >> "$LOG_DIR/dev-backend.log" 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    warn "后端启动失败，日志末尾："
    tail -n 25 "$LOG_DIR/dev-backend.log" >&2 || true
    die "后端未能启动"
  fi
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1 \
  || die "后端健康检查超时，见 logs/dev-backend.log"
log "后端就绪"

# ---------------- 播种演示数据 ----------------
log "检查演示数据…"
SEED_LOG="$LOG_DIR/dev-seed.log"
if ! "$BASE_DIR/backend/.venv/bin/python" "$BASE_DIR/backend/scripts/seed_demo.py" \
      --base-url "http://127.0.0.1:$BACKEND_PORT" \
      --admin-user "$ADMIN_USER" --admin-password "$ADMIN_PASSWORD" > "$SEED_LOG" 2>&1; then
  warn "播种演示数据失败，日志：$SEED_LOG"
  tail -n 20 "$SEED_LOG" >&2 || true
  die "演示数据未能就绪"
fi
# 把播种结果的邀请码清单展示出来
sed -n '/演示数据就绪/,$p' "$SEED_LOG"

# ---------------- 启动前端 ----------------
log "启动前端 http://localhost:$FRONTEND_PORT …"
(
  cd "$BASE_DIR/frontend"
  exec npx vite --port "$FRONTEND_PORT" --strictPort
) >> "$LOG_DIR/dev-frontend.log" 2>&1 &
FRONTEND_PID=$!

for _ in $(seq 1 60); do
  if curl -fsS "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; then break; fi
  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    warn "前端启动失败，日志末尾："
    tail -n 25 "$LOG_DIR/dev-frontend.log" >&2 || true
    die "前端未能启动"
  fi
  sleep 0.5
done
log "前端就绪"

# ---------------- 打开浏览器 ----------------
ADMIN_URL="http://localhost:$FRONTEND_PORT/admin.html"
CANDIDATE_URL="http://localhost:$FRONTEND_PORT/"

echo
echo "======================================================================"
echo " 服务已启动（按 Ctrl+C 停止）"
echo "======================================================================"
echo "  管理端      $ADMIN_URL"
echo "  考生端      $CANDIDATE_URL"
echo
echo "  管理员账号  $ADMIN_USER / $ADMIN_PASSWORD"
echo
echo "  日志        logs/dev-backend.log  logs/dev-frontend.log"
echo "======================================================================"
echo

if [ "$NO_OPEN" -eq 1 ]; then
  :
elif command -v open >/dev/null 2>&1; then
  open "$ADMIN_URL" 2>/dev/null || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$ADMIN_URL" 2>/dev/null || true
else
  warn "未能自动打开浏览器，请手动访问上面的地址。"
fi

# 保持前台运行，直到用户 Ctrl+C
wait "$FRONTEND_PID"
