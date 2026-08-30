#!/usr/bin/env bash
#
# Food Mate — one-click deploy from local machine to Azure VM
#
# Prerequisites:
#   1. az login already completed
#   2. Local ~/.ssh/id_rsa.pub exists
#   3. food-mate-api/.env is configured with API keys
#
# Usage:
#   bash deploy/scripts/deploy-all.sh
#   PUBLIC_IP=1.2.3.4 bash deploy/scripts/deploy-all.sh   # Skip VM creation; only update an existing machine
#

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RG="${FOODMATE_RG:-rg-foodmate}"
VM_NAME="${FOODMATE_VM_NAME:-vm-foodmate}"
ADMIN="${FOODMATE_ADMIN_USER:-azureuser}"
SSH_KEY="${FOODMATE_SSH_KEY:-$HOME/.ssh/id_rsa.pub}"
ENV_FILE="${FOODMATE_ENV_FILE:-$ROOT/food-mate-api/.env}"

log() { echo "[deploy-all] $*"; }
die() { echo "[deploy-all][错误] $*" >&2; exit 1; }

command -v rsync >/dev/null 2>&1 || die "未安装 rsync"
[ -f "$SSH_KEY" ] || die "找不到 SSH 公钥: $SSH_KEY"
[ -f "$ENV_FILE" ] || die "找不到 $ENV_FILE，请先配置 API Key"

# When PUBLIC_IP is set, deploy over SSH only; az CLI is not required
if [ -z "${PUBLIC_IP:-}" ]; then
  command -v az >/dev/null 2>&1 || die "未安装 az CLI"
  az account show >/dev/null 2>&1 || die "请先运行: az login，或设置 PUBLIC_IP=<公网IP> 跳过 az"
fi

# Resolve or create the VM public IP
resolve_public_ip() {
  if [ -n "${PUBLIC_IP:-}" ]; then
    log "使用指定公网 IP: $PUBLIC_IP"
    return 0
  fi
  if az vm show -d -g "$RG" -n "$VM_NAME" >/dev/null 2>&1; then
    PUBLIC_IP="$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)"
    log "已存在 VM，公网 IP: $PUBLIC_IP"
  else
    log "未找到 VM，开始创建 ..."
    bash "$ROOT/deploy/scripts/azure-create-vm.sh"
    PUBLIC_IP="$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)"
  fi
  [ -n "$PUBLIC_IP" ] || die "无法获取公网 IP"
}

# Wait until SSH is ready
wait_ssh() {
  log "等待 SSH 就绪 ($ADMIN@$PUBLIC_IP) ..."
  for i in $(seq 1 30); do
    if ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \
      -i "${SSH_KEY%.pub}" "${ADMIN}@${PUBLIC_IP}" "echo ok" >/dev/null 2>&1; then
      log "SSH 已连通"
      return 0
    fi
    sleep 10
  done
  die "SSH 连接超时"
}

# Sync code to the VM
sync_code() {
  log "同步代码到 VM ..."
  rsync -avz \
    --exclude node_modules --exclude .next --exclude __pycache__ \
    --exclude .git --exclude venv --exclude logs --exclude memory \
    --exclude .env --exclude .env.* \
    -e "ssh -o StrictHostKeyChecking=accept-new -i ${SSH_KEY%.pub}" \
    "$ROOT/" "${ADMIN}@${PUBLIC_IP}:/tmp/food-mate/"

  ssh -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "${ADMIN}@${PUBLIC_IP}" <<'REMOTE'
set -e
sudo mkdir -p /opt/food-mate
# The first rsync did not upload runtime files such as memory / .env; exclude them here too,
# otherwise --delete would wipe live memory or overwrite production secrets
sudo rsync -a --delete \
  --exclude node_modules --exclude .next --exclude __pycache__ \
  --exclude .git --exclude venv --exclude logs --exclude memory \
  --exclude .env --exclude .env.* \
  /tmp/food-mate/ /opt/food-mate/
REMOTE
}

# Run setup on the VM (idempotent)
run_setup() {
  log "在 VM 上执行 azure-vm-setup.sh ..."
  ssh -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "${ADMIN}@${PUBLIC_IP}" \
    "sudo bash /opt/food-mate/deploy/azure-vm-setup.sh"
}

# Upload local .env, then overwrite master_key from config.yaml so API/Proxy keys stay in sync
upload_env() {
  log "上传 .env ..."
  scp -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "$ENV_FILE" "${ADMIN}@${PUBLIC_IP}:/tmp/food-mate.env"

  ssh -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "${ADMIN}@${PUBLIC_IP}" <<'REMOTE'
set -e
TARGET=/opt/food-mate/food-mate-api/.env
CONFIG=/opt/food-mate/food-mate-api/config.yaml
sudo cp /tmp/food-mate.env "$TARGET"

# LiteLLM has no database: requests must use master_key from config.yaml, or it reports No connected db
MK=$(sudo grep -E '^[[:space:]]*master_key:' "$CONFIG" | head -1 \
  | sed -E 's/^[[:space:]]*master_key:[[:space:]]*//' | tr -d "\"'")
if [ -n "$MK" ]; then
  if sudo grep -q '^FOODMATE_PROXY_MASTER_KEY=' "$TARGET"; then
    sudo sed -i "s|^FOODMATE_PROXY_MASTER_KEY=.*|FOODMATE_PROXY_MASTER_KEY=${MK}|" "$TARGET"
  else
    if [ -s "$TARGET" ] && [ -n "$(sudo tail -c1 "$TARGET")" ]; then
      printf '\n' | sudo tee -a "$TARGET" >/dev/null
    fi
    echo "FOODMATE_PROXY_MASTER_KEY=${MK}" | sudo tee -a "$TARGET" >/dev/null
  fi
fi

sudo chown foodmate:foodmate "$TARGET"
sudo chmod 600 "$TARGET"
rm -f /tmp/food-mate.env
REMOTE
}

restart_services() {
  log "重启服务 ..."
  ssh -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "${ADMIN}@${PUBLIC_IP}" \
    "sudo systemctl restart foodmate-proxy foodmate-api foodmate-web nginx"
}

smoke_test() {
  log "冒烟测试 ..."
  ssh -o StrictHostKeyChecking=accept-new -i "${SSH_KEY%.pub}" \
    "${ADMIN}@${PUBLIC_IP}" \
    "bash /opt/food-mate/deploy/scripts/smoke-test.sh https://127.0.0.1" || true
}

main() {
  cd "$ROOT"
  resolve_public_ip
  wait_ssh
  sync_code
  run_setup
  upload_env
  restart_services
  smoke_test

  cat <<EOF

========================================
 部署完成
========================================
 公网 IP: $PUBLIC_IP
 SSH:     ssh ${ADMIN}@${PUBLIC_IP}

 若域名 foodmates365.com 尚未指向此 IP，请在 Cloudflare 添加 A 记录。
 详见 deploy/CLOUDFLARE_DNS.md

 浏览器访问: https://foodmates365.com
 或临时:     https://${PUBLIC_IP}（需 -k 忽略证书）
========================================
EOF
}

main "$@"
