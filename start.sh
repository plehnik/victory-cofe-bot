#!/usr/bin/env bash
# Victory Coffee — запуск server + tunnel + bot
# 用法: bash start.sh
set -e
cd "$(dirname "$0")"

export PATH="$HOME/bin:$PATH"

echo "[1/3] 启动 FastAPI server (port 8080)..."
source venv/bin/activate
uvicorn server:app --port 8080 &
SERVER_PID=$!
echo "  server PID=$SERVER_PID"

echo "[2/3] 启动 Cloudflare Quick Tunnel..."
cloudflared tunnel --url http://localhost:8080 --protocol http2 --origin-ca-pool /etc/ssl/cert.pem > /tmp/tunnel.log 2>&1 &
TUNNEL_PID=$!
echo "  tunnel PID=$TUNNEL_PID"

echo "[3/3] 启动 Telegram бот..."
python bot.py &
BOT_PID=$!
echo "  bot PID=$BOT_PID"

echo ""
echo "等待 tunnel 就绪..."
sleep 6
TUNNEL_URL=$(grep -o 'https://[a-zA-Z0-9_-]\+\.trycloudflare\.com' /tmp/tunnel.log 2>/dev/null | tail -1 || true)
if [ -n "$TUNNEL_URL" ]; then
  echo "  ✅ WEBAPP_URL=$TUNNEL_URL"
  sed -i '' "s|WEBAPP_URL = .*|WEBAPP_URL = \"$TUNNEL_URL\"|" config.py
  echo "  → config.py обновлён"
fi

echo ""
echo "运行中: server=$SERVER_PID tunnel=$TUNNEL_PID bot=$BOT_PID"
echo "停止: kill $SERVER_PID $TUNNEL_PID $BOT_PID 或 Ctrl+C"
wait