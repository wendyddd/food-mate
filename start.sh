#!/usr/bin/env bash
#
# FoodMate 一键启动脚本
# 功能：检查运行环境，安装缺失依赖，并启动后端 API + 前端 Web
#

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$ROOT_DIR/food-mate-api"
WEB_DIR="$ROOT_DIR/food-mate-web"
LOG_DIR="$ROOT_DIR/logs"

PROXY_LOG="$LOG_DIR/food-mate-proxy.log"
API_LOG="$LOG_DIR/food-mate-api.log"
WEB_LOG="$LOG_DIR/food-mate-web.log"

API_PORT="${FOODMATE_API_PORT:-8000}"
WEB_PORT="${FOODMATE_WEB_PORT:-3000}"
PROXY_PORT="${PROXY_PORT:-4000}"

CONDA_ENV="${FOODMATE_CONDA_ENV:-/opt/miniconda3/envs/py311}"
PYTHON_BIN="$CONDA_ENV/bin/python"
PIP_BIN="$CONDA_ENV/bin/pip"
REQUIREMENTS="$API_DIR/requirements.txt"
STAMP_FILE="$API_DIR/.requirements.sha256"

PROXY_PID=""
API_PID=""
WEB_PID=""

log_info() {
  echo "[信息] $*"
}

log_warn() {
  echo "[警告] $*" >&2
}

log_error() {
  echo "[错误] $*" >&2
}

# 退出时清理所有子进程
cleanup() {
  local code="${1:-0}"
  echo ""
  log_info "正在停止服务 ..."

  if [ -n "$WEB_PID" ] && kill -0 "$WEB_PID" 2>/dev/null; then
    kill "$WEB_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
  fi

  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi

  if [ -n "$PROXY_PID" ] && kill -0 "$PROXY_PID" 2>/dev/null; then
    kill "$PROXY_PID" 2>/dev/null || true
    wait "$PROXY_PID" 2>/dev/null || true
  fi

  exit "$code"
}

trap 'cleanup 130' INT
trap 'cleanup 143' TERM

# 检查命令是否存在
require_command() {
  local cmd="$1"
  local hint="$2"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "未找到命令：${cmd}。${hint}"
    exit 1
  fi
}

# 检查端口是否被占用
check_port_free() {
  local port="$1"
  local port_label="${2:-未知服务}"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    log_error "端口 ${port} 已被占用（${port_label}）。请释放端口或设置环境变量修改端口。"
    lsof -nP -iTCP:"$port" -sTCP:LISTEN || true
    exit 1
  fi
}

# 校验 conda Python 环境并安装后端依赖（litellm 需要 Python >=3.10 且 <3.14）
setup_api_env() {
  if [ -n "${FOODMATE_PYTHON:-}" ]; then
    PYTHON_BIN="$FOODMATE_PYTHON"
    PIP_BIN="$(dirname "$PYTHON_BIN")/pip"
  fi

  if [ ! -x "$PYTHON_BIN" ]; then
    log_error "未找到 Python 解释器：$PYTHON_BIN"
    log_error "请确认 conda 环境存在，或设置 FOODMATE_PYTHON / FOODMATE_CONDA_ENV。"
    exit 1
  fi

  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 14) else 1)
PY
  then
    log_error "Python 版本不兼容（需要 >=3.10 且 <3.14）：$("$PYTHON_BIN" --version 2>&1)"
    exit 1
  fi

  log_info "使用 conda 环境：$CONDA_ENV"
  log_info "使用 Python：$("$PYTHON_BIN" --version 2>&1) ($PYTHON_BIN)"

  if [ ! -f "$REQUIREMENTS" ]; then
    log_error "缺少依赖文件：$REQUIREMENTS"
    exit 1
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    CURRENT_HASH="$(sha256sum "$REQUIREMENTS" | awk '{print $1}')"
  else
    CURRENT_HASH="$(shasum -a 256 "$REQUIREMENTS" | awk '{print $1}')"
  fi

  NEED_INSTALL=1
  if [ -f "$STAMP_FILE" ] && [ "$(cat "$STAMP_FILE")" = "$CURRENT_HASH" ]; then
    NEED_INSTALL=0
  fi

  if [ "$NEED_INSTALL" -eq 1 ]; then
    log_info "安装/更新后端依赖到 conda 环境 ..."
    "$PIP_BIN" install --upgrade pip
    "$PIP_BIN" install -r "$REQUIREMENTS"
    echo "$CURRENT_HASH" > "$STAMP_FILE"
  else
    log_info "后端依赖已就绪，跳过安装。"
  fi
}

# 初始化前端依赖
setup_web_env() {
  require_command node "请先安装 Node.js（建议 18+）。"
  require_command npm "请先安装 npm。"

  if [ ! -f "$WEB_DIR/package.json" ]; then
    log_error "未找到前端项目：$WEB_DIR/package.json"
    exit 1
  fi

  if [ ! -d "$WEB_DIR/node_modules" ]; then
    log_info "安装前端依赖 ..."
    (cd "$WEB_DIR" && npm install)
  else
    log_info "前端依赖已就绪，跳过安装。"
  fi
}

# 启动 LiteLLM Proxy（记忆提取/优化需要；失败时不阻断基础功能）
start_proxy() {
  if [ ! -f "$API_DIR/.env" ]; then
    log_warn "未找到 $API_DIR/.env，跳过 LiteLLM Proxy。记忆编辑可用，AI 提取/优化可能不可用。"
    return 0
  fi

  if lsof -nP -iTCP:"$PROXY_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    log_info "检测到 LiteLLM Proxy 已在端口 ${PROXY_PORT} 运行，直接复用。"
    return 0
  fi

  log_info "启动 LiteLLM Proxy, 端口 ${PROXY_PORT} ..."
  (
    cd "$API_DIR"
    "$PYTHON_BIN" - <<'PY'
from src.proxy import start_proxy
import time

start_proxy()
while True:
    time.sleep(3600)
PY
  ) >"$PROXY_LOG" 2>&1 &
  PROXY_PID=$!

  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${PROXY_PORT}/health/liveliness" >/dev/null 2>&1; then
      log_info "LiteLLM Proxy 已就绪：http://127.0.0.1:${PROXY_PORT}"
      return 0
    fi
    sleep 1
  done

  log_warn "LiteLLM Proxy 启动超时，记忆 AI 提取/优化可能不可用。日志：$PROXY_LOG"
  PROXY_PID=""
}

# 启动后端 FastAPI
start_api() {
  log_info "启动后端 API（端口 ${API_PORT}）..."
  (
    cd "$API_DIR"
    export FOODMATE_API_PORT="$API_PORT"
    exec "$PYTHON_BIN" api_server.py
  ) >"$API_LOG" 2>&1 &
  API_PID=$!

  local i
  for i in $(seq 1 20); do
    if curl -fsS "http://127.0.0.1:${API_PORT}/api/health" >/dev/null 2>&1; then
      log_info "后端 API 已就绪：http://127.0.0.1:${API_PORT}"
      return 0
    fi
    sleep 1
  done

  log_error "后端 API 启动失败，请查看日志：$API_LOG"
  exit 1
}

# 启动前端 Next.js
start_web() {
  log_info "启动前端 Web（端口 ${WEB_PORT}）..."
  (
    cd "$WEB_DIR"
    export NEXT_PUBLIC_FOODMATE_API_PORT="$API_PORT"
    exec npm run dev -- -p "$WEB_PORT"
  ) >"$WEB_LOG" 2>&1 &
  WEB_PID=$!

  local i
  for i in $(seq 1 30); do
    if curl -fsS "http://127.0.0.1:${WEB_PORT}" >/dev/null 2>&1; then
      log_info "前端 Web 已就绪：http://127.0.0.1:${WEB_PORT}/"
      return 0
    fi
    sleep 1
  done

  log_error "前端 Web 启动失败，请查看日志：$WEB_LOG"
  exit 1
}

main() {
  log_info "FoodMate 启动检查 ..."

  mkdir -p "$LOG_DIR"

  if [ ! -d "$API_DIR" ] || [ ! -d "$WEB_DIR" ]; then
    log_error "项目目录不完整，请确认 food-mate-api 与 food-mate-web 存在。"
    exit 1
  fi

  require_command curl "请安装 curl 以便进行健康检查。"
  require_command lsof "请安装 lsof 以便进行端口检查。"

  check_port_free "$API_PORT" "后端 API"
  check_port_free "$WEB_PORT" "前端 Web"

  setup_api_env
  setup_web_env

  start_proxy
  start_api
  start_web

  echo ""
  echo "========================================"
  echo " FoodMate 已启动"
  echo " - 登录页面: http://127.0.0.1:${WEB_PORT}/login"
  echo " - 聊天页面: http://127.0.0.1:${WEB_PORT}/{session}/"
  echo " - 记忆页面: http://127.0.0.1:${WEB_PORT}/{session}/memory"
  echo " - 后端 API: http://127.0.0.1:${API_PORT}/docs"
  echo " - Proxy 日志: $PROXY_LOG"
  echo " - API 日志: $API_LOG"
  echo " - Web 日志: $WEB_LOG"
  echo " 按 Ctrl+C 停止全部服务"
  echo "========================================"
  echo ""

  wait "$WEB_PID"
}

main "$@"
