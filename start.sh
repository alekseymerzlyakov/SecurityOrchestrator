#!/usr/bin/env bash
# AISO — одна команда для запуска всего проекта
# Использование: ./start.sh
# Останов:       Ctrl+C (или закрыть окно)

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_PORT=8000
FRONTEND_PORT=5173

# Цвета
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   AISO — AI-Driven Security Orchestrator ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
echo ""

# 1. Убить старые процессы — по портам И по имени процесса
echo -e "${YELLOW}→ Останавливаем старые процессы...${NC}"

# Сначала мягко по PID-файлам если есть
[ -f "$PROJECT_DIR/data/backend.pid" ] && kill $(cat "$PROJECT_DIR/data/backend.pid") 2>/dev/null || true
[ -f "$PROJECT_DIR/data/frontend.pid" ] && kill $(cat "$PROJECT_DIR/data/frontend.pid") 2>/dev/null || true

# Затем жёстко — все uvicorn с нашим проектом
pkill -9 -f "uvicorn backend.main" 2>/dev/null || true

# Жёстко по портам (остатки)
lsof -ti:$BACKEND_PORT  | xargs kill -9 2>/dev/null || true
lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true

# Дать время OS освободить порты
sleep 1

# 2. Проверить что venv существует
if [ ! -d "$PROJECT_DIR/venv" ]; then
  echo -e "${RED}✗ venv не найден. Запустите сначала первоначальную установку:${NC}"
  echo "  python3 -m venv venv && source venv/bin/activate && pip install -r backend/requirements.txt"
  exit 1
fi

# 3. Проверить что node_modules существует
if [ ! -d "$PROJECT_DIR/frontend/node_modules" ]; then
  echo -e "${YELLOW}→ Устанавливаем npm зависимости...${NC}"
  cd "$PROJECT_DIR/frontend" && npm install --silent
  cd "$PROJECT_DIR"
fi

# 4. Запустить бэкенд в фоне
echo -e "${GREEN}→ Запускаем backend на http://localhost:$BACKEND_PORT ...${NC}"
source "$PROJECT_DIR/venv/bin/activate"
PYTHONPATH="$PROJECT_DIR" uvicorn backend.main:app \
  --host 0.0.0.0 --port $BACKEND_PORT \
  --log-level warning \
  > "$PROJECT_DIR/data/backend.log" 2>&1 &
BACKEND_PID=$!

# 5. Ждать пока бэкенд поднимется (до 15 сек)
echo -n "   Ожидание backend"
for i in $(seq 1 15); do
  if curl -s "http://localhost:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
    echo -e " ${GREEN}✓${NC}"
    break
  fi
  echo -n "."
  sleep 1
done

# 6. Запустить фронтенд в фоне
echo -e "${GREEN}→ Запускаем frontend на http://localhost:$FRONTEND_PORT ...${NC}"
cd "$PROJECT_DIR/frontend"
npm run dev -- --port $FRONTEND_PORT > "$PROJECT_DIR/data/frontend.log" 2>&1 &
FRONTEND_PID=$!
cd "$PROJECT_DIR"

sleep 2

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║            AISO запущен!                 ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  UI:       http://localhost:5173         ║${NC}"
echo -e "${GREEN}║  API:      http://localhost:8000         ║${NC}"
echo -e "${GREEN}║  API Docs: http://localhost:8000/docs    ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║  Логи: data/backend.log                  ║${NC}"
echo -e "${GREEN}║        data/frontend.log                 ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  Остановить: Ctrl+C                      ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# Открыть браузер (macOS)
if command -v open &> /dev/null; then
  sleep 1
  open "http://localhost:$FRONTEND_PORT"
fi

# 7. Ждать Ctrl+C и корректно завершить оба процесса
cleanup() {
  echo ""
  echo -e "${YELLOW}→ Останавливаем AISO...${NC}"
  kill $BACKEND_PID 2>/dev/null || true
  kill $FRONTEND_PID 2>/dev/null || true
  lsof -ti:$BACKEND_PORT | xargs kill -9 2>/dev/null || true
  lsof -ti:$FRONTEND_PORT | xargs kill -9 2>/dev/null || true
  echo -e "${GREEN}✓ Готово.${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

# Держать скрипт живым и показывать логи backend
tail -f "$PROJECT_DIR/data/backend.log" 2>/dev/null &
wait $BACKEND_PID
