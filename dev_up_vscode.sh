#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/Users/anastasiiagolovkova/Desktop/footballistikaweb"
WEB_DIR="$PROJECT_DIR/web"
PORT=8000
OUT_FILE="$PROJECT_DIR/ngrok_current.txt"

echo "🚀 Footballistika VSCode launcher (plain)"
echo "Project: $PROJECT_DIR"
echo "Web dir: $WEB_DIR"
echo

# 1) Відкрити VS Code (якщо закрито)
if ! pgrep -x "Code" >/dev/null 2>&1; then
  code "$PROJECT_DIR"
  sleep 2
fi

# 2) Терміал №1 у VS Code — http.server
osascript <<EOF
tell application "System Events"
  tell process "Code"
    set frontmost to true
    keystroke "p" using {command down, shift down}
    delay 0.5
    keystroke "> Create New Integrated Terminal"
    key code 36
    delay 1
    keystroke "cd '$WEB_DIR'; python3 -m http.server $PORT"
    key code 36
  end tell
end tell
EOF

# 3) Терміал №2 у VS Code — ngrok
osascript <<EOF
tell application "System Events"
  tell process "Code"
    set frontmost to true
    keystroke "p" using {command down, shift down}
    delay 0.5
    keystroke "> Create New Integrated Terminal"
    key code 36
    delay 1
    keystroke "cd '$PROJECT_DIR'; ngrok http $PORT"
    key code 36
  end tell
end tell
EOF

# 4) Чекаємо підняття локального API ngrok (http://127.0.0.1:4040)
echo -n "⏳ Чекаю ngrok API"
for i in {1..120}; do       # до ~30 секунд
  if curl -sf http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
    echo " — ок"
    break
  fi
  echo -n "."
  sleep 0.25
done
if ! curl -sf http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
  echo -e "\n❌ ngrok API не відповідає. Перевір термінал з ngrok."
  exit 1
fi

# 5) Беремо https-домен і пишемо в TXT (без редагування .env)
NGROK_DOMAIN=$(
  curl -s http://127.0.0.1:4040/api/tunnels \
  | /usr/bin/python3 - <<'PY'
import sys,json
try:
    t=json.load(sys.stdin).get("tunnels",[])
    https=[x["public_url"] for x in t if x.get("public_url","").startswith("https://")]
    if https: print(https[0].split("https://",1)[1])
except Exception: pass
PY
)

if [ -z "${NGROK_DOMAIN:-}" ]; then
  echo "❌ Не вдалося отримати https-домен з ngrok."
  exit 1
fi

echo "https://${NGROK_DOMAIN}/" > "$OUT_FILE"
echo "📝 Записав поточний URL у: $OUT_FILE"
echo "👉 ${OUT_FILE} містить: https://${NGROK_DOMAIN}/"

echo
echo "✅ Далі твої ручні кроки:"
echo "  1) У BotFather → /setdomain → ${NGROK_DOMAIN}"
echo "  2) В .env онови рядок WEBAPP_URL на: https://${NGROK_DOMAIN}/"
echo "  3) Запусти бота у VS Code: python3 bot.py, потім /start у чаті"
echo
