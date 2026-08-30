#!/usr/bin/env bash

# FoodMate Agent start script. Creates or reuses a venv, installs deps if needed, then starts the app.

set -euo pipefail

# Switch to the script directory so relative paths work
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"
# Stamp file storing the requirements.txt hash, used to detect dependency changes
STAMP_FILE="$VENV_DIR/.requirements.sha256"

# Pick an available Python interpreter
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[错误] 未检测到 Python，请先安装 Python 3。"
    exit 1
fi

# 1. Create the virtualenv if it does not exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[信息] 未检测到虚拟环境，正在创建 $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate the virtualenv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 2. Hash the current requirements.txt
if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
else
    # macOS uses shasum by default
    CURRENT_HASH="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
fi

# 3. Install deps if the stamp is missing or the hash has changed
NEED_INSTALL=1
if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$CURRENT_HASH" ]; then
    NEED_INSTALL=0
fi

if [ "$NEED_INSTALL" -eq 1 ]; then
    echo "[信息] 检测到依赖未安装或已变更，正在安装环境依赖 ..."
    python -m pip install --upgrade pip
    python -m pip install -r "$REQUIREMENTS"
    echo "$CURRENT_HASH" > "$STAMP_FILE"
    echo "[信息] 依赖安装完成。"
else
    echo "[信息] 环境依赖已是最新，跳过安装。"
fi

# 4. Start the application
echo "[信息] 正在启动 FoodMate Agent ..."
exec python main.py
