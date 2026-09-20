#!/usr/bin/env bash
#
# 极轻量级客观题考试系统 — 进程管理脚本（无需 Docker / systemd）
#
#   ./manage.sh start     启动后端 + 内置 Web 服务器
#   ./manage.sh stop      停止
#   ./manage.sh restart   重启
#   ./manage.sh status    查看状态与健康检查
#   ./manage.sh doctor    部署环境自检（首次上线前请执行）
#   ./manage.sh backup    备份数据库到 data/backups/
#   ./manage.sh logs      跟踪日志（Ctrl+C 退出）

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

BACKEND_DIR="$BASE_DIR/backend"
VENDOR_DIR="$BACKEND_DIR/vendor"
SERVER_JS="$BASE_DIR/server/server.js"
RUN_DIR="$BASE_DIR/run"
LOG_DIR="$BASE_DIR/logs"

BACKEND_PID_FILE="$RUN_DIR/backend.pid"
WEB_PID_FILE="$RUN_DIR/web.pid"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$BASE_DIR/data"

# ---------------- 配置 ----------------
if [ -f "$BASE_DIR/exam.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$BASE_DIR/exam.env"
  set +a
else
  echo "[manage] 未找到 exam.env，请先执行 ./install.sh" >&2
  exit 1
fi

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
BACKEND_ORIGIN="${BACKEND_ORIGIN:-http://127.0.0.1:$BACKEND_PORT}"
ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-changeme}"
TOKEN_SECRET="${TOKEN_SECRET:-}"
EXAM_DB_PATH="${EXAM_DB_PATH:-./data/exam.db}"

# 统一转成绝对路径，避免依赖启动时的 cwd
case "$EXAM_DB_PATH" in
  /*) : ;;
  *) EXAM_DB_PATH="$BASE_DIR/${EXAM_DB_PATH#./}" ;;
esac

PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$(command -v "$candidate")"; break; fi
  done
fi

log()  { printf '\033[32m[manage]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[manage]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[manage]\033[0m %s\n' "$*" >&2; exit 1; }

read_pid() {
  local file="$1"
  [ -f "$file" ] || return 1
  local pid
  pid="$(cat "$file" 2>/dev/null || true)"
  [ -n "$pid" ] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  printf '%s' "$pid"
}

wait_for_http() {
  local url="$1" timeout="${2:-40}" i=0
  while [ "$i" -lt "$((timeout * 4))" ]; do
    if "$PYTHON" - "$url" <<'PYEOF' 2>/dev/null
import sys, urllib.request
try:
    with urllib.request.urlopen(sys.argv[1], timeout=2) as resp:
        sys.exit(0 if resp.status == 200 else 1)
except Exception:
    sys.exit(1)
PYEOF
    then
      return 0
    fi
    i=$((i + 1))
    sleep 0.25
  done
  return 1
}

# --------------------------------------------------------------------------
do_start() {
  command -v node >/dev/null 2>&1 || die "未找到 node，内置 Web 服务器需要 Node（建议 16+，已在 22 上验证）。"
  [ -d "$VENDOR_DIR" ] || die "未安装依赖，请先执行 ./install.sh"
  [ -x "$PYTHON" ] || die "未找到 python3"

  if PID="$(read_pid "$BACKEND_PID_FILE")"; then
    warn "后端已在运行（PID ${PID}），跳过启动"
  else
    log "启动后端（127.0.0.1:${BACKEND_PORT}，单进程）…"
    # 说明：必须保持 --workers 1。交卷幂等依赖进程内 attempt 锁，
    # 多进程会绕过该锁（数据库条件更新仍能兜底，但会增加无谓的重试）。
    PYTHONPATH="$VENDOR_DIR:$BACKEND_DIR" \
    EXAM_DB_PATH="$EXAM_DB_PATH" \
    ADMIN_USERNAME="$ADMIN_USERNAME" \
    ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    TOKEN_SECRET="$TOKEN_SECRET" \
    nohup "$PYTHON" -m uvicorn app.main:app \
      --host 127.0.0.1 --port "$BACKEND_PORT" --workers 1 \
      --log-level info \
      >> "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$BACKEND_PID_FILE"

    if wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/health" 40; then
      log "后端就绪（PID $(cat "$BACKEND_PID_FILE")）"
    else
      warn "后端 40 秒内未就绪，最近日志："
      tail -n 20 "$LOG_DIR/backend.log" >&2 || true
      die "后端启动失败"
    fi
  fi

  if PID="$(read_pid "$WEB_PID_FILE")"; then
    warn "Web 服务器已在运行（PID ${PID}），跳过启动"
  else
    log "启动内置 Web 服务器（$HOST:${PORT}）…"
    PORT="$PORT" HOST="$HOST" BACKEND_ORIGIN="$BACKEND_ORIGIN" \
    nohup node "$SERVER_JS" >> "$LOG_DIR/web.log" 2>&1 &
    echo $! > "$WEB_PID_FILE"

    if wait_for_http "http://127.0.0.1:$PORT/" 20; then
      log "Web 服务器就绪（PID $(cat "$WEB_PID_FILE")）"
    else
      warn "Web 服务器 20 秒内未就绪，最近日志："
      tail -n 20 "$LOG_DIR/web.log" >&2 || true
      die "Web 服务器启动失败"
    fi
  fi

  echo
  log "服务已启动："
  echo "    考生端  http://<服务器IP>:$PORT/"
  echo "    管理端  http://<服务器IP>:$PORT/admin.html"
  echo "    后端 API 只在 127.0.0.1:$BACKEND_PORT 监听，不直接对外"
}

do_stop() {
  local stopped=0

  if PID="$(read_pid "$WEB_PID_FILE")"; then
    log "停止 Web 服务器（PID ${PID}）"
    kill "$PID" 2>/dev/null || true
    stopped=1
  fi
  rm -f "$WEB_PID_FILE"

  if PID="$(read_pid "$BACKEND_PID_FILE")"; then
    log "停止后端（PID ${PID}）"
    kill "$PID" 2>/dev/null || true
    stopped=1
  fi
  rm -f "$BACKEND_PID_FILE"

  # 等待优雅退出
  local i=0
  while [ "$i" -lt 20 ]; do
    if ! pgrep -f "uvicorn app.main:app" >/dev/null 2>&1 && ! pgrep -f "server/server.js" >/dev/null 2>&1; then
      break
    fi
    i=$((i + 1))
    sleep 0.5
  done

  # 兜底强杀
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "server/server.js" 2>/dev/null || true

  if [ "$stopped" -eq 1 ]; then log "已停止"; else warn "没有正在运行的服务"; fi
}

do_status() {
  echo "安装目录：$BASE_DIR"
  echo "Python  ：$PYTHON ($("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo '不可用'))"
  echo "Node    ：$(node -v 2>/dev/null || echo '未安装')"
  echo "数据库  ：$EXAM_DB_PATH"
  echo

  if PID="$(read_pid "$BACKEND_PID_FILE")"; then
    if wait_for_http "http://127.0.0.1:$BACKEND_PORT/api/health" 3; then
      printf '后端    ：\033[32m运行中\033[0m（PID %s，健康检查通过）\n' "$PID"
    else
      printf '后端    ：\033[33m进程存在但健康检查失败\033[0m（PID %s）\n' "$PID"
    fi
  else
    printf '后端    ：\033[31m未运行\033[0m\n'
  fi

  if PID="$(read_pid "$WEB_PID_FILE")"; then
    printf 'Web     ：\033[32m运行中\033[0m（PID %s，http://%s:%s）\n' "$PID" "$HOST" "$PORT"
  else
    printf 'Web     ：\033[31m未运行\033[0m\n'
  fi

  if [ -f "$EXAM_DB_PATH" ]; then
    echo "数据库大小：$(du -h "$EXAM_DB_PATH" | cut -f1)"
  fi
}

do_doctor() {
  local problems=0
  echo "=== 部署环境自检 ==="

  if command -v node >/dev/null 2>&1; then
    echo "  [OK] Node $(node -v)"
  else
    echo "  [!!] 未找到 node"; problems=$((problems + 1))
  fi

  if [ -x "$PYTHON" ]; then
    echo "  [OK] Python $("$PYTHON" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"
  else
    echo "  [!!] 未找到 python3"; problems=$((problems + 1))
  fi

  if [ -d "$VENDOR_DIR" ]; then
    if PYTHONPATH="$VENDOR_DIR:$BACKEND_DIR" "$PYTHON" -c \
      'import fastapi, uvicorn, sqlmodel, pydantic_core; print("  [OK] 依赖可导入（fastapi %s）" % fastapi.__version__)' 2>/dev/null; then
      :
    else
      echo "  [!!] 依赖导入失败，请重新执行 ./install.sh"; problems=$((problems + 1))
    fi
  else
    echo "  [!!] backend/vendor 不存在，请先执行 ./install.sh"; problems=$((problems + 1))
  fi

  if [ -f "$SERVER_JS" ] && [ -d "$BASE_DIR/server/dist" ]; then
    echo "  [OK] 前端产物完整（server/dist）"
  else
    echo "  [!!] 缺少 server/dist 或 server.js"; problems=$((problems + 1))
  fi

  if [ -w "$BASE_DIR/data" ]; then
    echo "  [OK] data/ 可写"
  else
    echo "  [!!] data/ 不可写"; problems=$((problems + 1))
  fi

  if [ -n "$TOKEN_SECRET" ] && [ "$TOKEN_SECRET" != "dev-insecure-secret-change-me" ]; then
    echo "  [OK] TOKEN_SECRET 已设置"
  else
    echo "  [!!] TOKEN_SECRET 未设置或仍是默认值"; problems=$((problems + 1))
  fi

  if [ "$ADMIN_PASSWORD" = "changeme" ] || [ -z "$ADMIN_PASSWORD" ]; then
    echo "  [!!] ADMIN_PASSWORD 仍是默认值，请修改 exam.env"; problems=$((problems + 1))
  else
    echo "  [OK] ADMIN_PASSWORD 非默认值"
  fi

  if [ "$PORT" -lt 1024 ] 2>/dev/null; then
    echo "  [!!] PORT=$PORT 小于 1024，非 root 无法监听"; problems=$((problems + 1))
  else
    echo "  [OK] PORT=$PORT"
  fi

  local free_kb
  free_kb="$(df -Pk "$BASE_DIR" | awk 'NR==2 {print $4}')"
  if [ "${free_kb:-0}" -gt 1048576 ]; then
    echo "  [OK] 磁盘剩余 $((free_kb / 1024)) MB"
  else
    echo "  [!!] 磁盘剩余不足 1GB（$((free_kb / 1024)) MB），SQLite 与备份需要空间"
    problems=$((problems + 1))
  fi

  if command -v sqlite3 >/dev/null 2>&1; then
    echo "  [--] 检测到 sqlite3 命令行工具（可选，便于手工排查）"
  fi

  echo
  if [ "$problems" -eq 0 ]; then
    log "自检全部通过。"
  else
    warn "自检发现 $problems 个问题，请先处理。"
    exit 1
  fi
}

do_backup() {
  [ -d "$VENDOR_DIR" ] || die "未安装依赖，请先执行 ./install.sh"
  [ -f "$EXAM_DB_PATH" ] || die "数据库不存在：$EXAM_DB_PATH"
  log "备份数据库…"
  PYTHONPATH="$VENDOR_DIR:$BACKEND_DIR" "$PYTHON" -m app.backup \
    --db "$EXAM_DB_PATH" --out "$BASE_DIR/data/backups" --keep-days 7
}

do_logs() {
  log "跟踪日志（Ctrl+C 退出）…"
  touch "$LOG_DIR/backend.log" "$LOG_DIR/web.log"
  tail -n 30 -f "$LOG_DIR/backend.log" "$LOG_DIR/web.log"
}

case "${1:-}" in
  start)   do_start ;;
  stop)    do_stop ;;
  restart) do_stop; do_start ;;
  status)  do_status ;;
  doctor)  do_doctor ;;
  backup)  do_backup ;;
  logs)    do_logs ;;
  *)
    sed -n '3,12p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
