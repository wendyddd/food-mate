#!/usr/bin/env bash

# FoodMate Agent 启动脚本。自动创建/复用虚拟环境，缺少依赖时先安装环境依赖，最后启动程序。

set -euo pipefail

# 切换到脚本所在目录，保证相对路径正确
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"
# 依赖安装完成标记文件，记录 requirements.txt 的哈希，用于判断依赖是否变更
STAMP_FILE="$VENV_DIR/.requirements.sha256"

# 选择可用的 Python 解释器
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[错误] 未检测到 Python，请先安装 Python 3。"
    exit 1
fi

# 1. 创建虚拟环境（若不存在）
if [ ! -d "$VENV_DIR" ]; then
    echo "[信息] 未检测到虚拟环境，正在创建 $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# 激活虚拟环境
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 2. 计算 requirements.txt 当前哈希
if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
else
    # macOS 默认使用 shasum
    CURRENT_HASH="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
fi

# 3. 判断是否需要安装依赖：标记文件不存在或哈希变化时安装
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

# 4. 启动程序
echo "[信息] 正在启动 FoodMate Agent ..."
exec python main.py
