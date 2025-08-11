# Telegram Bot and API

This project provides a Telegram bot with a FastAPI based HTTP API. The server can be used to manage employees, payouts and other entities stored in local JSON files. If a valid Telegram token is provided the bot will automatically start when the FastAPI server is launched.

## Requirements

* Python 3.11+
* See `requirements.txt` for the list of Python packages

## Installation

1. Create a virtual environment and install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. (Optional) create a `.env` or `config.json` file in the project root to override the default settings defined in `app/settings.py`. Important options include:

- `TELEGRAM_BOT_TOKEN` – Telegram bot token
- `ADMIN_TOKEN` – token required for admin API calls
- `EXCEL_FILE` – path to the Excel workbook with salary/schedule data
- `USERS_FILE`, `ADVANCE_REQUESTS_FILE`, `VACATIONS_FILE`, `ADJUSTMENTS_FILE`,
  `BONUSES_PENALTIES_FILE` – paths to data JSON files
- `ADMIN_ID`, `ADMIN_CHAT_ID` – Telegram identifiers for the administrator

If no configuration is provided, default values will be used and the project will look for JSON files such as `user.json`, `advance_requests.json`, `vacations.json` and others located in the repository root.

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

## Data files

Several JSON files are used as a simple storage backend and are expected to be present in the project root:

- `user.json` – employee data
- `advance_requests.json` – advance payout requests
- `vacations.json` – vacation information
- `adjustments.json` – salary adjustments
- `bonuses_penalties.json` – incentive information
- `messages.json` – stored broadcast messages

Example files are provided and will be created automatically if missing.

