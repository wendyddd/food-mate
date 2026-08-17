#!/usr/bin/env bash
#
# 使用 Azure CLI 创建 Food Mate 所需资源（East Asia / B2s / Ubuntu 22.04）
#
# 前置（本机）:
#   1. 安装 Azure CLI: https://learn.microsoft.com/cli/azure/install-azure-cli
#   2. az login
#   3. az account show   # 确认已选中正确订阅
#
# 用法:
#   bash deploy/scripts/azure-create-vm.sh
#   FOODMATE_ADMIN_USER=azureuser bash deploy/scripts/azure-create-vm.sh
#

set -euo pipefail

RG="${FOODMATE_RG:-rg-foodmate}"
LOC="${FOODMATE_LOCATION:-eastasia}"
VM_NAME="${FOODMATE_VM_NAME:-vm-foodmate}"
VM_SIZE="${FOODMATE_VM_SIZE:-Standard_B2s}"
ADMIN_USER="${FOODMATE_ADMIN_USER:-azureuser}"
# 默认用本机 ~/.ssh/id_rsa.pub；可改 FOODMATE_SSH_KEY
SSH_KEY="${FOODMATE_SSH_KEY:-$HOME/.ssh/id_rsa.pub}"
NSG_NAME="${VM_NAME}-nsg"
PUBLIC_IP_NAME="${VM_NAME}-ip"

log() { echo "[azure-create-vm] $*"; }
die() { echo "[azure-create-vm][错误] $*" >&2; exit 1; }

command -v az >/dev/null 2>&1 || die "未安装 az CLI，请先安装 Azure CLI"
[ -f "$SSH_KEY" ] || die "找不到 SSH 公钥: $SSH_KEY（请先 ssh-keygen 或设置 FOODMATE_SSH_KEY）"

log "当前订阅:"
az account show --query "{name:name, id:id, state:state}" -o table

log "创建资源组 $RG @ $LOC ..."
az group create --name "$RG" --location "$LOC" -o table

log "创建虚拟机 $VM_NAME ($VM_SIZE) ..."
az vm create \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --image "Canonical:0001-com-ubuntu-server-jammy:22_04-lts-gen2:latest" \
  --size "$VM_SIZE" \
  --admin-username "$ADMIN_USER" \
  --ssh-key-values "$SSH_KEY" \
  --public-ip-sku Standard \
  --public-ip-address "$PUBLIC_IP_NAME" \
  --nsg "$NSG_NAME" \
  --os-disk-size-gb 64 \
  --storage-sku Premium_LRS \
  --output table

log "配置 NSG：开放 22 / 80 / 443，不开放 3000/8000/4000 ..."
az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG_NAME" \
  --name AllowSSH \
  --priority 1000 \
  --access Allow --protocol Tcp \
  --direction Inbound \
  --source-address-prefixes Internet \
  --destination-port-ranges 22 \
  -o none || true

az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG_NAME" \
  --name AllowHTTP \
  --priority 1010 \
  --access Allow --protocol Tcp \
  --direction Inbound \
  --source-address-prefixes Internet \
  --destination-port-ranges 80 \
  -o none || true

az network nsg rule create \
  --resource-group "$RG" \
  --nsg-name "$NSG_NAME" \
  --name AllowHTTPS \
  --priority 1020 \
  --access Allow --protocol Tcp \
  --direction Inbound \
  --source-address-prefixes Internet \
  --destination-port-ranges 443 \
  -o none || true

PUBLIC_IP="$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)"
log "公网 IP: $PUBLIC_IP"

cat <<EOF

========================================
 VM 已创建
========================================
 资源组: $RG
 虚拟机: $VM_NAME
 区域:   $LOC
 规格:   $VM_SIZE
 公网IP: $PUBLIC_IP
 SSH:    ssh ${ADMIN_USER}@${PUBLIC_IP}

 下一步:
 1) 把本仓库同步到 VM（任选其一）:
    rsync -avz --exclude node_modules --exclude .git --exclude venv \\
      ./ ${ADMIN_USER}@${PUBLIC_IP}:/tmp/food-mate/
    ssh ${ADMIN_USER}@${PUBLIC_IP} 'sudo mkdir -p /opt/food-mate && sudo rsync -a /tmp/food-mate/ /opt/food-mate/'

 2) 在 VM 上执行:
    ssh ${ADMIN_USER}@${PUBLIC_IP}
    sudo bash /opt/food-mate/deploy/azure-vm-setup.sh

 3) 编辑 /opt/food-mate/food-mate-api/.env 填入 API Key

 4) Cloudflare DNS: A @ / www → ${PUBLIC_IP}（橙云）
    详见 deploy/CLOUDFLARE_DNS.md
========================================
EOF
