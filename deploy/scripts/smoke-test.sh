#!/usr/bin/env bash
#
# Food Mate deploy smoke test
#
# Usage:
#   bash deploy/scripts/smoke-test.sh
#   bash deploy/scripts/smoke-test.sh https://foodmates365.com
#   bash deploy/scripts/smoke-test.sh http://127.0.0.1:8000   # Hit the API directly (skip frontend pages)
#

set -uo pipefail

BASE="${1:-https://foodmates365.com}"
BASE="${BASE%/}"
CURL_OPTS=(-sS --max-time 30)
# Add -k for local self-signed HTTPS
if [[ "$BASE" == https://127.0.0.1* ]] || [[ "$BASE" == https://localhost* ]]; then
  CURL_OPTS+=(-k)
fi

pass=0
fail=0

ok() { echo "[通过] $*"; pass=$((pass + 1)); }
bad() { echo "[失败] $*"; fail=$((fail + 1)); }

# Treat as API-only when the host includes a non-80/443 port
is_api_only=0
if [[ "$BASE" =~ :[0-9]+$ ]]; then
  port="${BASE##*:}"
  if [[ "$port" != "80" && "$port" != "443" ]]; then
    is_api_only=1
  fi
fi

echo "目标: $BASE"
echo "----------------------------------------"

# 1) Health check
health_body="$(curl "${CURL_OPTS[@]}" -f "$BASE/api/health" 2>/dev/null || true)"
if [[ -n "$health_body" ]]; then
  ok "GET /api/health → $health_body"
else
  bad "健康检查失败（期望 /api/health）"
fi

# 2) Login page (site-root check; skip when hitting the API port directly)
if [[ "$is_api_only" -eq 1 ]]; then
  echo "[跳过] GET /login（当前为目标 API 端口）"
else
  code="$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' "$BASE/login" 2>/dev/null || echo "000")"
  if [[ "$code" == "200" ]]; then
    ok "GET /login → HTTP $code"
  else
    bad "GET /login → HTTP ${code}"
  fi
fi

# 3) Local listen hints
if command -v ss >/dev/null 2>&1; then
  if ss -lnt 2>/dev/null | grep -q ':8000'; then
    ok "本机 8000 在监听"
  else
    echo "[提示] 本机未见 8000（测远端域名时可忽略）"
  fi
  echo "[提示] 请在 Azure NSG 确认未对公网开放 3000/8000/4000"
fi

# 4) SSE/chat route reachable (401/403/422 is common when unauthenticated)
chat_code="$(curl "${CURL_OPTS[@]}" -o /dev/null -w '%{http_code}' \
  -X POST "$BASE/api/chat" \
  -H 'Content-Type: application/json' \
  -d '{"message":"ping","session_id":"smoke","stream":true}' 2>/dev/null || true)"
chat_code="${chat_code:-000}"
if [[ "$chat_code" == "401" || "$chat_code" == "403" || "$chat_code" == "422" || "$chat_code" == "200" ]]; then
  ok "POST /api/chat 路由可达（HTTP $chat_code）"
else
  bad "POST /api/chat 异常（HTTP ${chat_code}）"
fi

echo "----------------------------------------"
echo "通过: $pass  失败: $fail"
if [[ "$fail" -gt 0 ]]; then
  exit 1
fi
echo "冒烟基础项通过。请再在浏览器完成：登录 → 流式聊天 → 记忆读写 → 重启 VM 后数据仍在。"
exit 0
