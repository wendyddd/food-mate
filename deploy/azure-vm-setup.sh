#!/usr/bin/env bash
#
# Food Mate — Azure Ubuntu VM bootstrap script
# Run once as root or with sudo on an existing Ubuntu 22.04 VM.
#
# Usage:
#   sudo bash deploy/azure-vm-setup.sh
#   sudo FOODMATE_REPO_URL=https://github.com/YOU/food-mate.git bash deploy/azure-vm-setup.sh
#
# Prerequisites:
#   - Code is already at /opt/food-mate, or set FOODMATE_REPO_URL to clone automatically
#   - Afterwards, place .env secrets at /opt/food-mate/food-mate-api/.env
#

set -euo pipefail

APP_ROOT="${FOODMATE_APP_ROOT:-/opt/food-mate}"
APP_USER="${FOODMATE_APP_USER:-foodmate}"
REPO_URL="${FOODMATE_REPO_URL:-}"
NODE_MAJOR="${FOODMATE_NODE_MAJOR:-20}"
PYTHON_BIN=""

log() { echo "[foodmate-setup] $*"; }
die() { echo "[foodmate-setup][错误] $*" >&2; exit 1; }

require_root() {
  if [ "$(id -u)" -ne 0 ]; then
    die "请使用 root 或 sudo 运行本脚本"
  fi
}

# Install system packages, Node 20, Python 3.11, and Nginx
install_packages() {
  log "更新 apt 并安装基础包 ..."
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    ca-certificates curl gnupg git build-essential \
    nginx openssl ufw \
    python3.11 python3.11-venv python3.11-dev python3-pip

  if ! command -v node >/dev/null 2>&1 || ! node -v | grep -q "v${NODE_MAJOR}"; then
    log "安装 Node.js ${NODE_MAJOR} ..."
    curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash -
    apt-get install -y nodejs
  fi

  PYTHON_BIN="$(command -v python3.11)"
  log "Python: $($PYTHON_BIN --version)"
  log "Node: $(node -v) / npm $(npm -v)"
}

# Create the app user and directories
ensure_user_and_dirs() {
  if ! id "$APP_USER" >/dev/null 2>&1; then
    log "创建用户 $APP_USER ..."
    useradd --system --create-home --shell /bin/bash "$APP_USER"
  fi
  mkdir -p "$APP_ROOT" /var/log/foodmate /etc/ssl/foodmate
  chown -R "$APP_USER:$APP_USER" "$APP_ROOT" /var/log/foodmate
}

# Fetch code: skip clone if the tree already exists; otherwise clone FOODMATE_REPO_URL
fetch_code() {
  if [ -d "$APP_ROOT/food-mate-api" ] && [ -d "$APP_ROOT/food-mate-web" ]; then
    log "检测到已有代码：$APP_ROOT"
    return 0
  fi

  if [ -z "$REPO_URL" ]; then
    die "未找到 $APP_ROOT/food-mate-api。请先上传代码，或设置 FOODMATE_REPO_URL=git仓库地址"
  fi

  log "克隆仓库 $REPO_URL → $APP_ROOT ..."
  if [ -d "$APP_ROOT/.git" ]; then
    sudo -u "$APP_USER" git -C "$APP_ROOT" pull --ff-only
  else
    rm -rf "$APP_ROOT"
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_ROOT"
  fi
}

# Backend venv and dependencies
setup_api() {
  log "配置 Python 虚拟环境与后端依赖 ..."
  sudo -u "$APP_USER" "$PYTHON_BIN" -m venv "$APP_ROOT/venv"
  sudo -u "$APP_USER" "$APP_ROOT/venv/bin/pip" install --upgrade pip
  sudo -u "$APP_USER" "$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/food-mate-api/requirements.txt"

  if [ ! -f "$APP_ROOT/food-mate-api/.env" ]; then
    if [ -f "$APP_ROOT/food-mate-api/.env.example" ]; then
      cp "$APP_ROOT/food-mate-api/.env.example" "$APP_ROOT/food-mate-api/.env"
      chown "$APP_USER:$APP_USER" "$APP_ROOT/food-mate-api/.env"
      chmod 600 "$APP_ROOT/food-mate-api/.env"
      log "已生成 .env 模板，请编辑填入真实 API Key：$APP_ROOT/food-mate-api/.env"
    else
      log "警告：缺少 .env.example，请手动创建 $APP_ROOT/food-mate-api/.env"
    fi
  fi

  sync_proxy_master_key
}

# Return true if master_key is a placeholder (repo default; not for production auth)
is_placeholder_master_key() {
  case "${1:-}" in
    ""|sk-foodmate-local|sk-foodmate-change-me) return 0 ;;
    *) return 1 ;;
  esac
}

# Read general_settings.master_key from config.yaml
read_config_master_key() {
  grep -E '^[[:space:]]*master_key:' "$APP_ROOT/food-mate-api/config.yaml" 2>/dev/null \
    | head -1 \
    | sed -E 's/^[[:space:]]*master_key:[[:space:]]*//' \
    | tr -d "\"'"
}

# Read FOODMATE_PROXY_MASTER_KEY from .env (last occurrence, in case of duplicate lines)
read_env_master_key() {
  local envf="$APP_ROOT/food-mate-api/.env"
  if [ -f "$envf" ]; then
    grep '^FOODMATE_PROXY_MASTER_KEY=' "$envf" | tail -1 | cut -d= -f2-
  fi
}

# Write master_key to .env (replace all duplicate lines, or append; ensure a trailing newline)
write_env_master_key() {
  local key="$1"
  local envf="$APP_ROOT/food-mate-api/.env"
  touch "$envf"
  if [ -s "$envf" ] && [ -n "$(tail -c1 "$envf")" ]; then
    printf '\n' >> "$envf"
  fi
  if grep -q '^FOODMATE_PROXY_MASTER_KEY=' "$envf"; then
    sed -i "s|^FOODMATE_PROXY_MASTER_KEY=.*|FOODMATE_PROXY_MASTER_KEY=${key}|" "$envf"
  else
    echo "FOODMATE_PROXY_MASTER_KEY=${key}" >> "$envf"
  fi
}

# Write master_key to config.yaml
write_config_master_key() {
  local key="$1"
  sed -i -E "s/^([[:space:]]*master_key:).*/\1 ${key}/" \
    "$APP_ROOT/food-mate-api/config.yaml"
}

# Align Proxy and API master_key so LiteLLM does not treat the request as a virtual key and report No connected db
sync_proxy_master_key() {
  local env_key config_key chosen
  env_key="$(read_env_master_key)"
  config_key="$(read_config_master_key)"

  if ! is_placeholder_master_key "$env_key"; then
    chosen="$env_key"
  elif ! is_placeholder_master_key "$config_key"; then
    chosen="$config_key"
  else
    chosen="sk-foodmate-$(openssl rand -hex 16)"
    log "生成新的 LiteLLM master_key"
  fi

  write_config_master_key "$chosen"
  write_env_master_key "$chosen"
  chown "$APP_USER:$APP_USER" "$APP_ROOT/food-mate-api/.env" 2>/dev/null || true
  chmod 600 "$APP_ROOT/food-mate-api/.env" 2>/dev/null || true
  log "已同步 LiteLLM master_key（config.yaml 与 .env 一致）"
}

# Frontend production build (no cross-port API; use relative path /api)
setup_web() {
  log "安装前端依赖并 build ..."
  cd "$APP_ROOT/food-mate-web"
  sudo -u "$APP_USER" npm ci || sudo -u "$APP_USER" npm install
  # Do not inject NEXT_PUBLIC_FOODMATE_API_PORT so API_BASE stays /api
  sudo -u "$APP_USER" env -u NEXT_PUBLIC_FOODMATE_API_PORT -u NEXT_PUBLIC_API_BASE \
    npm run build
}

# Install systemd units and Nginx
install_services() {
  log "安装 systemd unit ..."
  cp "$APP_ROOT/deploy/systemd/foodmate-proxy.service" /etc/systemd/system/
  cp "$APP_ROOT/deploy/systemd/foodmate-api.service" /etc/systemd/system/
  cp "$APP_ROOT/deploy/systemd/foodmate-web.service" /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable foodmate-proxy foodmate-api foodmate-web

  log "安装 Nginx 站点配置 ..."
  cp "$APP_ROOT/deploy/nginx/foodmates365.conf" /etc/nginx/sites-available/foodmates365.conf
  ln -sfn /etc/nginx/sites-available/foodmates365.conf /etc/nginx/sites-enabled/foodmates365.conf
  rm -f /etc/nginx/sites-enabled/default

  # If no Origin certificate exists, generate a self-signed placeholder (works with Cloudflare Full; use Origin Cert for Full strict)
  if [ ! -f /etc/ssl/foodmate/origin.pem ]; then
    log "生成自签 TLS 证书占位（建议之后换成 Cloudflare Origin Certificate）..."
    openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
      -keyout /etc/ssl/foodmate/origin.key \
      -out /etc/ssl/foodmate/origin.pem \
      -subj "/CN=foodmates365.com" \
      -addext "subjectAltName=DNS:foodmates365.com,DNS:www.foodmates365.com"
    chmod 600 /etc/ssl/foodmate/origin.key
  fi

  nginx -t
  systemctl enable nginx
  systemctl restart nginx

  log "配置 UFW：允许 OpenSSH / Nginx Full ..."
  ufw allow OpenSSH || true
  ufw allow "Nginx Full" || true
  ufw --force enable || true
}

start_app() {
  log "启动应用服务 ..."
  systemctl restart foodmate-proxy
  sleep 3
  systemctl restart foodmate-api
  sleep 2
  systemctl restart foodmate-web
  systemctl --no-pager --full status foodmate-proxy foodmate-api foodmate-web || true
}

print_next_steps() {
  cat <<EOF

========================================
 Food Mate VM 初始化完成
========================================
 代码目录: $APP_ROOT
 请务必完成:
 1) 编辑密钥: nano $APP_ROOT/food-mate-api/.env
 2) 重启 API:  systemctl restart foodmate-proxy foodmate-api
 3) Cloudflare DNS A 记录指向本机公网 IP（橙云代理）
 4) SSL/TLS 模式: Full（自签）或 Full (strict)+Origin Cert
 5) 冒烟: bash $APP_ROOT/deploy/scripts/smoke-test.sh

 本机健康检查:
   curl -fsS http://127.0.0.1:8000/api/health
   curl -kfsS https://127.0.0.1/api/health
========================================
EOF
}

main() {
  require_root
  install_packages
  ensure_user_and_dirs
  fetch_code
  setup_api
  setup_web
  install_services
  start_app
  print_next_steps
}

main "$@"
