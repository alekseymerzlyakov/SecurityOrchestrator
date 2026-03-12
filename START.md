# AISO — AI-Driven Security Orchestrator
## Руководство по запуску

---

## Требования

- macOS (или Linux)
- Python 3.11+ (установлен через Homebrew: `brew install python`)
- Node.js 18+ с npm (`brew install node` или через nvm)
- Git

---

## Структура проекта

```
SecurityTesting/
├── backend/          # FastAPI сервер (Python)
│   ├── main.py       # Точка входа
│   ├── routers/      # API endpoints
│   ├── services/     # Логика: AI, сканеры, отчёты
│   └── models/       # ORM модели (SQLite)
├── frontend/         # React UI (Vite + Tailwind)
├── data/             # БД и отчёты (создаётся автоматически)
│   ├── aiso.db       # SQLite база
│   ├── reports/      # Сгенерированные HTML/PDF отчёты
│   └── .encryption_key  # Ключ шифрования API-ключей
├── venv/             # Python virtualenv
└── scripts/
    └── setup.sh      # Первоначальная установка
```

---

## Первый запуск (один раз)

```bash
cd /Users/alekseymerzlyakov/Tests/SecurityTesting

# 1. Создать virtualenv и установить зависимости
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# 2. Установить зависимости фронтенда
cd frontend && npm install && cd ..

# 3. Убедиться что инструменты установлены
brew install gitleaks trivy
pip install semgrep  # в venv
npm install -g retire eslint eslint-plugin-security eslint-plugin-no-unsanitized
```

---

## Обычный запуск (каждый раз)

Открыть **два терминала**:

### Терминал 1 — Бэкенд

```bash
cd /Users/alekseymerzlyakov/Tests/SecurityTesting
source venv/bin/activate
PYTHONPATH=/Users/alekseymerzlyakov/Tests/SecurityTesting \
  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Бэкенд запустится на **http://localhost:8000**
API документация: **http://localhost:8000/docs**

### Терминал 2 — Фронтенд

```bash
cd /Users/alekseymerzlyakov/Tests/SecurityTesting/frontend
npm run dev
```

Фронтенд запустится на **http://localhost:5173**

> Открыть в браузере: **http://localhost:5173**

---

## Полный сброс (если что-то сломалось)

```bash
cd /Users/alekseymerzlyakov/Tests/SecurityTesting

# Убить всё что висит на портах
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173 | xargs kill -9 2>/dev/null

# Удалить базу данных (все данные сбросятся!)
rm -f data/aiso.db

# Перезапустить бэкенд — БД создастся заново
source venv/bin/activate
PYTHONPATH=/Users/alekseymerzlyakov/Tests/SecurityTesting \
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

---

## Подключение Claude AI

### 1. Получить API ключ

- Зайти на [console.anthropic.com](https://console.anthropic.com)
- **Settings → API Keys → Create Key**
- Скопировать ключ вида `sk-ant-api03-...`
- **Settings → Billing** — пополнить баланс (минимум $5)

### 2. Добавить провайдер в AISO

1. Открыть **http://localhost:5173/settings**
2. Вкладка **AI Providers** → "+ Add Provider"
   - Name: `Anthropic`
   - Type: `Anthropic`
   - API Key: `sk-ant-api03-...`
   - Save
3. Вкладка **AI Models** → "+ Add Model"

| Поле | Значение |
|---|---|
| Provider | Anthropic |
| Display Name | Claude Sonnet 4 |
| Model ID | `claude-sonnet-4-20250514` |
| Context Window | `200000` |
| Max Tokens/Run | `1000000` |
| Max Budget ($) | `10` |
| Input $/MTok | `3` |
| Output $/MTok | `15` |

### 3. Доступные модели Claude

| Model ID | Input $/MTok | Output $/MTok | Когда использовать |
|---|---|---|---|
| `claude-sonnet-4-20250514` | $3 | $15 | Основная рабочая лошадка |
| `claude-opus-4-20250514` | $15 | $75 | Максимальное качество |
| `claude-haiku-4-20250514` | $0.80 | $4 | Быстро и дёшево (Tier 2-3 файлы) |

> **Важно:** Claude Code CLI токен (`/login`) — это другое. Нужен именно API ключ с `console.anthropic.com`.

---

## Запуск сканирования

### Через UI (рекомендуется)

1. **Projects** → создать проект, указать путь к репозиторию
2. **Pipeline Builder** → выбрать проект, ветку, режим сканирования:
   - **Tools Only** — только статические инструменты (бесплатно, быстро)
   - **AI Only** — только AI анализ (платно, глубоко)
   - **Hybrid** — сначала инструменты, потом AI с учётом найденного
3. Нажать **Start Scan**
4. Перейти на **Live Monitor** для наблюдения в реальном времени

### Через API (для автоматизации)

```bash
# Создать проект
curl -X POST http://localhost:8000/api/projects/ \
  -H "Content-Type: application/json" \
  -d '{"name": "My App", "repo_path": "/path/to/repo"}'

# Запустить скан (только инструменты)
curl -X POST http://localhost:8000/api/scans/ \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": 1,
    "branch": "main",
    "mode": "tools_only",
    "pipeline_json": "[\"gitleaks\", \"semgrep\", \"trivy\", \"npm_audit\"]"
  }'

# Статус скана
curl http://localhost:8000/api/scans/1

# Findings
curl http://localhost:8000/api/findings/?scan_id=1
```

---

## Прогноз стоимости AI сканирования

Перед запуском AI сканирования можно получить прогноз — сколько токенов и денег потребует
полный анализ репозитория для каждой настроенной модели.

### Через API

```bash
curl -X POST http://localhost:8000/api/scans/estimate \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1}'
```

Пример ответа:
```json
{
  "total_files": 1686,
  "total_code_tokens": 3200000,
  "models": [
    {
      "model_name": "Claude Haiku 4",
      "estimated_total_cost_usd": 2.56,
      "estimated_chunks": 27,
      "within_budget": true
    },
    {
      "model_name": "Claude Sonnet 4",
      "estimated_total_cost_usd": 9.60,
      "within_budget": true
    },
    {
      "model_name": "Claude Opus 4",
      "estimated_total_cost_usd": 48.00,
      "within_budget": false
    }
  ]
}
```

### В отчёте

При генерации HTML или PDF отчёта таблица прогноза по всем моделям добавляется
автоматически в раздел **"AI Full-Scan Cost Forecast"**.

```bash
# Сгенерировать HTML отчёт с прогнозом
curl -X POST http://localhost:8000/api/reports/1/generate \
  -H "Content-Type: application/json" \
  -d '{"format": "html", "report_type": "executive"}'
```

Открыть файл из `data/reports/scan_1_executive.html`.

---

## Установленные инструменты

| Инструмент | Версия | Что находит | Команда установки |
|---|---|---|---|
| **Semgrep** | 1.152.0 | SAST: XSS, injection, плохие паттерны | `pip install semgrep` (в venv) |
| **Gitleaks** | 8.30.0 | Секреты и ключи в Git-истории | `brew install gitleaks` |
| **Trivy** | 0.69.1 | CVE в npm/yarn зависимостях | `brew install trivy` |
| **npm audit** | встроен | Уязвимости в npm пакетах | встроен в npm |
| **ESLint Security** | — | JS-специфичные проблемы безопасности | `npm install -g eslint eslint-plugin-security` |
| **RetireJS** | 5.4.2 | Уязвимые встроенные JS библиотеки | `npm install -g retire` |

---

## Страницы интерфейса

| URL | Страница | Описание |
|---|---|---|
| `/` | Dashboard | Общая статистика, последний скан, score |
| `/projects` | Projects | Управление проектами и репозиториями |
| `/pipeline` | Pipeline Builder | Настройка и запуск сканирования |
| `/monitor` | Live Monitor | Прогресс скана в реальном времени (WebSocket) |
| `/findings` | Findings | Все уязвимости с фильтрами |
| `/reports` | Reports | История сканов, генерация отчётов |
| `/settings` | Settings | AI провайдеры, модели, инструменты, Jira |
| `/prompts` | Prompts | Управление промптами для AI анализа |

---

## Порты и сервисы

| Сервис | URL | Описание |
|---|---|---|
| Frontend | http://localhost:5173 | React UI |
| Backend API | http://localhost:8000 | FastAPI |
| API Docs | http://localhost:8000/docs | Swagger UI |
| WebSocket | ws://localhost:8000/ws | Real-time прогресс |

---

## Известные особенности

**Trivy при первом запуске** скачивает БД уязвимостей (~30 MB). Если возникает ошибка
`docker-credential-desktop`, это лечится автоматически (бэкенд создаёт временный Docker config).
Если ошибка всё равно появляется — запустите Docker Desktop.

**Semgrep** установлен в virtualenv (`venv/bin/semgrep`), а не глобально.
Бэкенд находит его автоматически.

**API ключи** хранятся в SQLite в зашифрованном виде (Fernet).
Ключ шифрования: `data/.encryption_key`. Не удаляйте этот файл иначе ключи не расшифруются.

---

## 🚀 Запуск одной командой

```bash
cd /Users/alekseymerzlyakov/Tests/SecurityTesting && ./start.sh
```

Скрипт автоматически:
1. Освобождает порты 8000 и 5173
2. Запускает бэкенд (ждёт пока поднимется)
3. Запускает фронтенд
4. Открывает браузер на **http://localhost:5173**
5. Показывает логи бэкенда
6. При **Ctrl+C** корректно останавливает оба процесса

Логи пишутся в `data/backend.log` и `data/frontend.log`.
