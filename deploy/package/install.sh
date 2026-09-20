#!/usr/bin/env bash
#
# 极轻量级客观题考试系统 — 离线安装脚本
#
# 适用环境：内网 Linux（aarch64 / x86_64），无外网、无 npm、无 Docker。
# 本脚本**不联网**，全部依赖来自随包的 backend/wheelhouse/。
#
# 安装方式（默认自动选择）：
#   A. 解压安装（默认）：把 wheel 当作 zip 解压到 backend/vendor/，
#      只需 python3，不需要 pip / venv，也不受 PEP 668 限制。
#   B. pip 安装（可选）：python3 -m pip install --no-index --target vendor ...
#      仅当显式传入 --use-pip 时使用。
#
# 用法：
#   ./install.sh              # 安装依赖 + 初始化配置
#   ./install.sh --use-pip    # 强制走 pip 安装

set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE_DIR"

BACKEND_DIR="$BASE_DIR/backend"
VENDOR_DIR="$BACKEND_DIR/vendor"
WHEELHOUSE_DIR="$BACKEND_DIR/wheelhouse"
REQUIREMENTS="$BACKEND_DIR/requirements-deploy.txt"

USE_PIP=0
for arg in "$@"; do
  case "$arg" in
    --use-pip) USE_PIP=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[32m[install]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[install]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[install]\033[0m %s\n' "$*" >&2; exit 1; }

# --------------------------------------------------------------------------
# 1. 探测 Python
# --------------------------------------------------------------------------

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON="$(command -v "$candidate")"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  die "未找到 python3。后端需要 Python 3.10 / 3.11 / 3.12（Ubuntu 系统自带 python3）。"
fi

PY_VERSION="$("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
PY_TAG="cp$(printf '%s' "$PY_VERSION" | tr -d '.')"
ARCH="$("$PYTHON" -c 'import platform; print(platform.machine())')"

log "Python  : ${PYTHON}（${PY_VERSION}，架构 ${ARCH}）"

case "$PY_VERSION" in
  3.10|3.11|3.12) : ;;
  *) die "本安装包只内置了 Python 3.10 / 3.11 / 3.12 的 ARM64 依赖，检测到 ${PY_VERSION}。
       请在服务器上安装 python3.11（sudo apt install python3.11），
       或联系我们重新打包含该版本的安装包。" ;;
esac

WHEEL_DIR="$WHEELHOUSE_DIR/$PY_TAG"
[ -d "$WHEEL_DIR" ] || die "缺少依赖目录：$WHEEL_DIR"
WHEEL_COUNT="$(find "$WHEEL_DIR" -name '*.whl' | wc -l | tr -d ' ')"
[ "$WHEEL_COUNT" -gt 0 ] || die "$WHEEL_DIR 中没有 wheel 文件，安装包可能不完整。"
log "离线依赖: $WHEEL_COUNT 个 wheel（${PY_TAG}）"

# --------------------------------------------------------------------------
# 2. 安装依赖到 backend/vendor
# --------------------------------------------------------------------------

rm -rf "$VENDOR_DIR"
mkdir -p "$VENDOR_DIR"

if [ "$USE_PIP" -eq 1 ]; then
  if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
    die "指定了 --use-pip，但当前 Python 没有可用的 pip。请去掉该参数改用解压安装。"
  fi
  log "使用 pip 从本地 wheelhouse 安装（不联网）…"
  "$PYTHON" -m pip install \
    --no-index --find-links "$WHEEL_DIR" \
    --target "$VENDOR_DIR" --upgrade --no-warn-script-location \
    -r "$REQUIREMENTS"
else
  log "解压安装依赖到 backend/vendor（不需要 pip）…"
  "$PYTHON" - "$VENDOR_DIR" "$WHEEL_DIR" <<'PYEOF'
import pathlib
import sys
import zipfile

vendor = pathlib.Path(sys.argv[1])
wheel_dir = pathlib.Path(sys.argv[2])
wheels = sorted(wheel_dir.glob('*.whl'))
if not wheels:
    sys.exit('没有找到 wheel 文件')
for wheel in wheels:
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(vendor)
print(f'  已解压 {len(wheels)} 个 wheel -> {vendor}')
PYEOF
fi

# --------------------------------------------------------------------------
# 3. 依赖自检（在目标机器上真实验证能否 import）
# --------------------------------------------------------------------------

log "校验依赖可导入…"
if ! PYTHONPATH="$VENDOR_DIR:$BACKEND_DIR" "$PYTHON" - <<'PYEOF'
import sys

problems = []
try:
    import fastapi
    import pydantic
    import pydantic_core
    import sqlalchemy
    import sqlmodel
    import uvicorn
except Exception as exc:  # noqa: BLE001
    problems.append(f'{type(exc).__name__}: {exc}')

if problems:
    print('\n'.join(problems), file=sys.stderr)
    sys.exit(1)

print(
    '  fastapi %s | pydantic %s | sqlmodel %s | sqlalchemy %s | uvicorn %s'
    % (fastapi.__version__, pydantic.VERSION, sqlmodel.__version__,
       sqlalchemy.__version__, uvicorn.__version__)
)
PYEOF
then
  die "依赖自检失败。请把上面的报错信息发给开发者。
       常见原因：Python 小版本与依赖 ABI 不匹配（例如 3.11.x 用了 cp312 的包）。"
fi

# 顺带验证后端应用本身可以加载
if ! PYTHONPATH="$VENDOR_DIR:$BACKEND_DIR" "$PYTHON" -c \
  'from app.main import create_app; app = create_app(); print("  后端应用加载正常，路由数：%d" % len(app.routes))' >/dev/null 2>&1; then
  warn "后端应用加载告警（首次运行缺少配置时可能正常）。可用 manage.sh doctor 复查。"
fi

# --------------------------------------------------------------------------
# 4. 目录与配置
# --------------------------------------------------------------------------

mkdir -p "$BASE_DIR/data" "$BASE_DIR/data/backups" "$BASE_DIR/logs" "$BASE_DIR/run"
log "运行目录已就绪：data/ logs/ run/"

GENERATED_ADMIN_PASSWORD=""
if [ ! -f "$BASE_DIR/exam.env" ]; then
  TOKEN_SECRET="$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
  GENERATED_ADMIN_PASSWORD="$("$PYTHON" -c 'import secrets, string; print("".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14)))')"
  cat > "$BASE_DIR/exam.env" <<EOF
# 极轻量级客观题考试系统 — 运行配置
# 修改后需要 ./manage.sh restart 生效。此文件含敏感信息，请勿外传。

# ---- 对外服务 ----
PORT=8080
HOST=0.0.0.0
# Node 内置服务器转发 /api 的目标（后端只监听本机，不直接对外）
BACKEND_ORIGIN=http://127.0.0.1:8000
BACKEND_PORT=8000

# ---- 管理员账号（单超管）----
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$GENERATED_ADMIN_PASSWORD

# ---- 安全 ----
# token 签名密钥，泄露等于任何人都能伪造登录态
TOKEN_SECRET=$TOKEN_SECRET

# ---- 数据库 ----
EXAM_DB_PATH=./data/exam.db
EOF
  chmod 600 "$BASE_DIR/exam.env"
  log "已生成配置文件 exam.env（权限 600）"
else
  log "检测到已存在的 exam.env，保持不变"
fi

# --------------------------------------------------------------------------
# 5. 完成提示
# --------------------------------------------------------------------------

echo
log "安装完成。"
echo
if [ -n "$GENERATED_ADMIN_PASSWORD" ]; then
  echo "  管理员账号：admin"
  echo "  管理员密码：$GENERATED_ADMIN_PASSWORD"
  echo "  （已写入 exam.env，请立即记录并妥善保管）"
  echo
fi
echo "  启动： ./manage.sh start"
echo "  状态： ./manage.sh status"
echo "  自检： ./manage.sh doctor"
echo "  备份： ./manage.sh backup"
echo
echo "  考生端 http://<服务器IP>:8080/"
echo "  管理端 http://<服务器IP>:8080/admin.html"
echo
warn "上线前请务必确认：exam.env 中的 ADMIN_PASSWORD 已改为你自己的强密码。"
