#!/usr/bin/env bash
#
# 可选：把考试系统注册为 systemd 服务（开机自启 + 崩溃自动拉起）。
#
# 考试期间最怕进程挂掉，强烈建议用 systemd 而不是手工 ./manage.sh start。
#
# 用法（需要 root）：
#   sudo ./systemd/install-systemd.sh
#   sudo ./systemd/install-systemd.sh uninstall
#
# 卸载只移除 unit 文件，不动数据库与配置。

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="/etc/systemd/system"
ACTION="${1:-install}"

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root 权限，请用 sudo 执行。" >&2
  exit 1
fi

remove_units() {
  systemctl stop exam-web.service 2>/dev/null || true
  systemctl stop exam-backend.service 2>/dev/null || true
  systemctl disable exam-web.service 2>/dev/null || true
  systemctl disable exam-backend.service 2>/dev/null || true
  rm -f "$UNIT_DIR/exam-web.service" "$UNIT_DIR/exam-backend.service"
  systemctl daemon-reload
  echo "已移除 systemd 服务（数据库与 exam.env 未改动）。"
}

if [ "$ACTION" = "uninstall" ]; then
  remove_units
  exit 0
fi

if [ ! -f "$BASE_DIR/exam.env" ]; then
  echo "未找到 $BASE_DIR/exam.env，请先执行 ./install.sh" >&2
  exit 1
fi

PYTHON="$(command -v python3 || command -v python || true)"
NODE="$(command -v node || true)"
[ -n "$PYTHON" ] || { echo "未找到 python3" >&2; exit 1; }
[ -n "$NODE" ] || { echo "未找到 node" >&2; exit 1; }

echo "安装目录：$BASE_DIR"
echo "python  ：$PYTHON"
echo "node    ：$NODE"

# ---- 后端 ----
cat > "$UNIT_DIR/exam-backend.service" <<EOF
[Unit]
Description=客观题考试系统 - 后端 API (FastAPI)
After=network.target

[Service]
Type=simple
WorkingDirectory=$BASE_DIR/backend
EnvironmentFile=$BASE_DIR/exam.env
Environment=PYTHONPATH=$BASE_DIR/backend/vendor:$BASE_DIR/backend
Environment=EXAM_DB_PATH=$BASE_DIR/data/exam.db
ExecStart=$PYTHON -m uvicorn app.main:app --host 127.0.0.1 --port \${BACKEND_PORT} --workers 1
Restart=always
RestartSec=3
StandardOutput=append:$BASE_DIR/logs/backend.log
StandardError=append:$BASE_DIR/logs/backend.log

[Install]
WantedBy=multi-user.target
EOF

# ---- Web（静态 + 反向代理）----
cat > "$UNIT_DIR/exam-web.service" <<EOF
[Unit]
Description=客观题考试系统 - Web 服务器 (Node 静态 + /api 代理)
After=network.target exam-backend.service
Wants=exam-backend.service

[Service]
Type=simple
WorkingDirectory=$BASE_DIR/server
EnvironmentFile=$BASE_DIR/exam.env
ExecStart=$NODE $BASE_DIR/server/server.js
Restart=always
RestartSec=3
StandardOutput=append:$BASE_DIR/logs/web.log
StandardError=append:$BASE_DIR/logs/web.log

[Install]
WantedBy=multi-user.target
EOF

mkdir -p "$BASE_DIR/logs" "$BASE_DIR/data"

systemctl daemon-reload
systemctl enable exam-backend.service exam-web.service
systemctl restart exam-backend.service
sleep 2
systemctl restart exam-web.service

echo
echo "已注册并启动："
echo "  systemctl status exam-backend"
echo "  systemctl status exam-web"
echo
echo "查看日志： journalctl -u exam-web -f"
echo "停止：     sudo systemctl stop exam-web exam-backend"
echo

# 顺带停掉 manage.sh 启动的裸进程，避免端口冲突
if [ -f "$BASE_DIR/run/backend.pid" ] || [ -f "$BASE_DIR/run/web.pid" ]; then
  echo "注意：检测到 manage.sh 启动的进程，正在停止以避免端口冲突…"
  (cd "$BASE_DIR" && ./manage.sh stop) || true
fi

echo "完成后请访问 http://<服务器IP>:$(grep -E '^PORT=' "$BASE_DIR/exam.env" | cut -d= -f2)/"
