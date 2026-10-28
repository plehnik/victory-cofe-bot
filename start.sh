#!/usr/bin/env bash
# Victory Coffee — 启动脚本（server + tunnel）
# 用法: source venv/bin/activate && bash start.sh
set -e
cd "$(dirname "$0")"

export PATH="$HOME/bin:$PATH"

echo "[1/2] 启动 FastAPI server (port 8080)..."
source venv/bin/activate
uvicorn server:app --port 8080 &
SERVER_PID=$!
echo "  server PID=$SERVER_PID"

echo "[2/2] 启动 Cloudflare Quick Tunnel..."
cloudflared tunnel --url http://localhost:8080 --protocol http2 --origin-ca-pool /etc/ssl/cert.pem &
TUNNEL_PID=$!
echo "  tunnel PID=$TUNNEL_PID"

echo ""
echo "等待 tunnel 就绪..."
sleep 6
TUNNEL_URL=$(log show --last 20s --predicate 'process == "cloudflared"' --style compact 2>/dev/null \
  | grep -o 'https://[a-zA-Z0-9_-]\+\.trycloudflare\.com' | tail -1 || true)
if [ -z "$TUNNEL_URL" ]; then
  echo "  ⚠ 未检测到 tunnel URL，请手动查看上方输出"
else
  echo "  ✅ WEBAPP_URL=$TUNNEL_URL"
fi

echo ""
echo "运行中: server=$SERVER_PID tunnel=$TUNNEL_PID"
echo "停止: kill $SERVER_PID $TUNNEL_PID 或 Ctrl+C"
wait