#!/usr/bin/env bash
#
# 构建离线部署包（在开发机上执行，需要联网下载 aarch64 依赖 + 具备 npm）。
#
#   ./deploy/build.sh
#
# 产物：deploy/out/exam-system-<版本>-linux-arm64.tar.gz
#
# 注意：本脚本只在开发机运行；目标服务器**不需要**联网、npm、pip、Docker。

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY_DIR="$REPO_DIR/deploy"
PKG_SRC="$DEPLOY_DIR/package"
OUT_DIR="$DEPLOY_DIR/out"
WHEEL_CACHE="$DEPLOY_DIR/.wheelcache"
REQ="$PKG_SRC/requirements-deploy.txt"

PYTHON_VERSIONS=("3.10" "3.11" "3.12")
PLATFORM_FLAGS=(--platform manylinux2014_aarch64 --platform manylinux_2_17_aarch64)

VERSION="1.0.0"
STAGE_NAME="exam-system-${VERSION}-linux-arm64"
STAGE_DIR="$OUT_DIR/$STAGE_NAME"

log()  { printf '\033[32m[build]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[build]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[build]\033[0m %s\n' "$*" >&2; exit 1; }

PIP="$REPO_DIR/backend/.venv/bin/pip"
[ -x "$PIP" ] || die "找不到 ${PIP}，请先在 backend/ 创建虚拟环境并安装依赖。"

# --------------------------------------------------------------------------
# 1. 构建前端（纯静态产物，服务器不需要 npm）
# --------------------------------------------------------------------------
log "构建前端…"
if [ -d "$REPO_DIR/frontend/node_modules" ]; then
  (cd "$REPO_DIR/frontend" && npm run build >/dev/null)
else
  die "frontend/node_modules 不存在，请先执行 cd frontend && npm install"
fi
[ -f "$REPO_DIR/frontend/dist/index.html" ] || die "前端构建产物缺失"
[ -f "$REPO_DIR/frontend/dist/admin.html" ] || die "前端构建产物缺少 admin.html（多入口构建失败？）"

# --------------------------------------------------------------------------
# 2. 下载各 Python 版本的 aarch64 依赖
# --------------------------------------------------------------------------
for PYV in "${PYTHON_VERSIONS[@]}"; do
  TAG="cp$(printf '%s' "$PYV" | tr -d '.')"
  DEST="$WHEEL_CACHE/$TAG"
  if [ -d "$DEST" ] && [ "$(find "$DEST" -name '*.whl' | wc -l | tr -d ' ')" -gt 0 ]; then
    log "复用已缓存的 $TAG 依赖（$(find "$DEST" -name '*.whl' | wc -l | tr -d ' ') 个）"
    continue
  fi
  log "下载 Python $PYV ($TAG) 的 aarch64 依赖…"
  rm -rf "$DEST"
  mkdir -p "$DEST"
  "$PIP" download --quiet --only-binary=:all: \
    "${PLATFORM_FLAGS[@]}" \
    --python-version "$PYV" --implementation cp \
    --dest "$DEST" -r "$REQ"
  log "  -> $(find "$DEST" -name '*.whl' | wc -l | tr -d ' ') 个 wheel"
done

# --------------------------------------------------------------------------
# 3. 组装目录结构
# --------------------------------------------------------------------------
log "组装 $STAGE_NAME …"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR"/{server,backend/wheelhouse,data/backups,logs,run,systemd}

# 3.1 部署脚本与文档
cp "$PKG_SRC/install.sh" "$PKG_SRC/manage.sh" "$STAGE_DIR/"
cp "$PKG_SRC/server.js" "$STAGE_DIR/server/"
cp "$PKG_SRC/requirements-deploy.txt" "$STAGE_DIR/backend/"
cp "$PKG_SRC/systemd/install-systemd.sh" "$STAGE_DIR/systemd/"
cp "$PKG_SRC/README-部署.md" "$STAGE_DIR/README-部署.md"
# 使用手册与题库模板：随包分发，方便现场直接查阅
cp "$REPO_DIR/docs/使用手册-考生.md" "$STAGE_DIR/使用手册-考生.md"
cp "$REPO_DIR/docs/使用手册-管理员.md" "$STAGE_DIR/使用手册-管理员.md"
cp "$REPO_DIR/docs/题库模板.md" "$STAGE_DIR/题库模板.md"
chmod +x "$STAGE_DIR/install.sh" "$STAGE_DIR/manage.sh" "$STAGE_DIR/systemd/install-systemd.sh"

if [ -x "$REPO_DIR/frontend/node_modules/.bin/vite" ]; then
  : # 前端已构建
fi

# 3.2 前端产物
cp -R "$REPO_DIR/frontend/dist/." "$STAGE_DIR/server/dist/"

# 3.3 后端源码（只带运行所需，排除测试与开发文件）
mkdir -p "$STAGE_DIR/backend/app/routers" "$STAGE_DIR/backend/scripts"
cp "$REPO_DIR/backend/app/"*.py "$STAGE_DIR/backend/app/"
cp "$REPO_DIR/backend/app/routers/"*.py "$STAGE_DIR/backend/app/routers/"
# 运维/演示脚本：都只用 Python 标准库，可直接在服务器上跑
cp "$REPO_DIR/backend/scripts/smoke_e2e.py" "$STAGE_DIR/backend/scripts/"
cp "$REPO_DIR/backend/scripts/seed_demo.py" "$STAGE_DIR/backend/scripts/"
find "$STAGE_DIR/backend" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# 3.4 各版本依赖
for PYV in "${PYTHON_VERSIONS[@]}"; do
  TAG="cp$(printf '%s' "$PYV" | tr -d '.')"
  cp -R "$WHEEL_CACHE/$TAG" "$STAGE_DIR/backend/wheelhouse/$TAG"
done

# 3.5 占位文件，保证空目录随包分发
printf '运行时数据目录（数据库、备份）\n' > "$STAGE_DIR/data/.keep"
printf '日志目录\n' > "$STAGE_DIR/logs/.keep"
printf 'PID 目录\n' > "$STAGE_DIR/run/.keep"

# 3.6 归一化权限
# 源文件可能是 600 创建的，若不处理会出现 -rwx--x--x 这种
# 「同组/其他人连读都不行」的权限，换用户运行或拷贝时会出问题。
find "$STAGE_DIR" -type d -exec chmod 755 {} +
find "$STAGE_DIR" -type f -exec chmod 644 {} +
chmod 755 "$STAGE_DIR/install.sh" "$STAGE_DIR/manage.sh" "$STAGE_DIR/systemd/install-systemd.sh"

# --------------------------------------------------------------------------
# 4. 校验
# --------------------------------------------------------------------------
log "校验包内容…"
[ -f "$STAGE_DIR/server/dist/index.html" ] || die "缺少考生端入口"
[ -f "$STAGE_DIR/server/dist/admin.html" ] || die "缺少管理端入口"
for PYV in "${PYTHON_VERSIONS[@]}"; do
  TAG="cp$(printf '%s' "$PYV" | tr -d '.')"
  COUNT="$(find "$STAGE_DIR/backend/wheelhouse/$TAG" -name '*.whl' | wc -l | tr -d ' ')"
  [ "$COUNT" -gt 0 ] || die "$TAG 依赖缺失"
  # 不允许出现非 aarch64 的原生二进制
  if ls "$STAGE_DIR/backend/wheelhouse/$TAG"/*.whl 2>/dev/null | grep -vE 'manylinux.*aarch64|none-any' | grep -q .; then
    die "$TAG 中混入了非 aarch64 wheel：$(ls "$STAGE_DIR/backend/wheelhouse/$TAG" | grep -vE 'manylinux.*aarch64|none-any')"
  fi
done

# shellcheck disable=SC2016
if grep -q $'\r' "$STAGE_DIR/manage.sh" 2>/dev/null; then
  die "manage.sh 含 CRLF 换行，Linux 下无法执行"
fi

# 防回归：$VAR 紧跟多字节字符时，某些 locale 下 bash 会把多字节首字节并入变量名，
# 直接导致 "unbound variable" 启动失败。必须写成 ${VAR}。
if ! "$REPO_DIR/backend/.venv/bin/python" - "$STAGE_DIR" <<'PYEOF'
import pathlib
import re
import sys

pattern = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)(?=[^\x00-\x7f])')
stage = pathlib.Path(sys.argv[1])
bad = []
seen = set()
for script in list(stage.glob('*.sh')) + list(stage.rglob('*.sh')):
    resolved = script.resolve()
    if resolved in seen:
        continue
    seen.add(resolved)
    for lineno, line in enumerate(script.read_text(encoding='utf-8').splitlines(), 1):
        if pattern.search(line):
            bad.append(f'{script.relative_to(stage)}:{lineno}: {line.strip()}')
if bad:
    print('以下变量未用 ${} 包裹，紧跟多字节字符会导致 bash unbound variable：')
    print('\n'.join(bad))
    sys.exit(1)
PYEOF
then
  die "shell 脚本未通过变量转义检查"
fi

# --------------------------------------------------------------------------
# 5. 打包
# --------------------------------------------------------------------------
log "打包 tar.gz …"
cd "$OUT_DIR"
rm -f "$STAGE_NAME.tar.gz"
tar -czf "$STAGE_NAME.tar.gz" "$STAGE_NAME"

SIZE="$(du -h "$STAGE_NAME.tar.gz" | cut -f1)"
SHA="$(shasum -a 256 "$STAGE_NAME.tar.gz" | cut -d' ' -f1)"

echo
log "构建完成"
echo "  文件：$OUT_DIR/$STAGE_NAME.tar.gz"
echo "  大小：$SIZE"
echo "  SHA256：$SHA"
echo
echo "传到服务器后："
echo "  tar -xzf $STAGE_NAME.tar.gz && cd $STAGE_NAME"
echo "  ./install.sh && ./manage.sh doctor && ./manage.sh start"
