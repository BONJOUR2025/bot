# Telegram Bot and API

This project provides a Telegram bot with a FastAPI based HTTP API. The server can be used to manage employees, payouts and other entities stored in local JSON files. If a valid Telegram token is provided the bot will automatically start when the FastAPI server is launched.

## Requirements

* Python 3.11+
* See `requirements.txt` for the list of Python packages

## Полная инструкция по запуску

### 1) Подготовка окружения

1. Убедитесь, что установлен Python 3.11+ и Node.js 18+.
2. Создайте виртуальное окружение и установите Python-зависимости:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Для работы десктопной оболочки pywebview понадобится системный backend WebKit/GTK (Linux) или WebView2 (Windows). На macOS зависимость ставится автоматически.
4. Если планируется собирать/редактировать админку, установите фронтенд-зависимости:

   ```bash
   cd admin_frontend
   npm install
   cd ..
   ```

### 2) Настройка конфигурации

Основные параметры читаются из `.env` или `config.json` в корне. Базовые значения заданы в `app/settings.py`, поэтому проект стартует и без ручной конфигурации. Ключевые опции:

- `TELEGRAM_BOT_TOKEN` – токен Telegram-бота; если пустой, бот не запускается, но API и админка работают.
- `ADMIN_TOKEN` – токен для защищённых API-эндпоинтов.
- `ADMIN_LOGIN`/`ADMIN_PASSWORD` – учётка для входа в админку (по умолчанию `admin`/`admin`).
- `EXCEL_FILE` – путь к Excel-файлу с расчётами.
- `USERS_FILE`, `ADVANCE_REQUESTS_FILE`, `VACATIONS_FILE`, `ADJUSTMENTS_FILE`, `BONUSES_PENALTIES_FILE`, `ASSETS_FILE` – пути к JSON-хранилищам данных.
- `ADMIN_ID`, `ADMIN_CHAT_ID` – идентификаторы администратора в Telegram.

Пример минимального `.env`:

```env
TELEGRAM_BOT_TOKEN=123:abc
ADMIN_TOKEN=supersecret
ADMIN_LOGIN=admin
ADMIN_PASSWORD=change_me
```

### 3) Подготовка данных

В корне репозитория должны находиться JSON-файлы с данными. Если их нет, сервис создаст пустые заготовки при первом запуске:

- `user.json` – сотрудники
- `advance_requests.json` – заявки на авансы
- `vacations.json` – отпуска
- `adjustments.json` – корректировки
- `bonuses_penalties.json` – премии и штрафы
- `assets.json` – имущество

### 4) Запуск FastAPI-сервера (с ботом)

1. Активируйте виртуальное окружение.
2. Запустите сервер:

   ```bash
   uvicorn app.server:app --host 0.0.0.0 --port 8000
   ```

3. Админка доступна на `http://127.0.0.1:8000/admin` (логин/пароль по умолчанию `admin`/`admin`).
4. Swagger UI с REST-эндпоинтами — `http://127.0.0.1:8000/docs`.
5. Если указан `TELEGRAM_BOT_TOKEN`, бот стартует автоматически вместе с API.

### 5) Десктопная оболочка (pywebview)

Для самостоятельного окна с встроенным API выполните:

```bash
python -m app.desktop --host 127.0.0.1 --port 8000
```

Параметры `--title` меняет заголовок окна, `--debug` включает devtools. Закрытие окна корректно останавливает Uvicorn.

### 6) Режим разработки админки

1. Поднимите бэкенд как описано выше.
2. В отдельном терминале запустите Vite c прокси на API:

   ```bash
   cd admin_frontend
   npm run dev -- --host --port 5173
   ```

3. Откройте `http://127.0.0.1:5173/admin/`. Все запросы `/api` и `/session` автоматически уходят на работающий бекенд `127.0.0.1:8000`.
4. После внесения правок пересоберите статические файлы, чтобы FastAPI отдавал актуальную версию:

   ```bash
   npm run build
   ```

Собранные файлы появляются в `admin_frontend/dist` и автоматически раздаются сервером по пути `/admin`.

### 7) Установка как пакета

Репозиторий содержит `pyproject.toml`, так что его можно поставить напрямую из git:

```bash
pip install git+https://github.com/your-account/bot.git
```

Будут доступны два CLI-скрипта:

- `telegram-salary-bot` — запуск бота в polling-режиме (аналог `python -m app.main`).
- `telegram-salary-bot-api` — запуск FastAPI через Uvicorn (аналог `python -m app`).

Для сборки wheel/tar.gz локально:

```bash
python -m build
```

Публикация на PyPI или GitHub Packages потребует настроенного `~/.pypirc` и `twine upload --repository <section-name> dist/*`.

## Running the FastAPI server

To launch the API together with the Telegram bot run:

```bash
uvicorn app.server:app --host 0.0.0.0 --port 8000
```

The server exposes a `/docs` endpoint with the interactive Swagger UI. When `TELEGRAM_BOT_TOKEN` is set the bot starts on startup and processes updates asynchronously.

## Running the Telegram bot only

For local testing you can start only the bot without the HTTP API:

```bash
python -m app.main
```

This command launches the bot and waits for commands in polling mode.

## Desktop shell (pywebview)

For a desktop-like experience with the React admin panel wrapped in a native window, install the optional `pywebview` dependency and run:

```bash
python -m app.desktop --host 127.0.0.1 --port 8000
```

The command starts the FastAPI application in the background and opens a `pywebview` window pointing at the `/admin` SPA. Use the `--debug` flag to enable the developer tools provided by `pywebview`.

## Data files

Several JSON files are used as a simple storage backend and are expected to be present in the project root:

- `user.json` – employee data
- `advance_requests.json` – advance payout requests
- `vacations.json` – vacation information
- `adjustments.json` – salary adjustments
- `bonuses_penalties.json` – incentive information
- `messages.json` – stored broadcast messages

Example files are provided and will be created automatically if missing.

# bot
