# Telegram Bot and API

This project provides a Telegram bot with a FastAPI based HTTP API. The server can be used to manage employees, payouts and other entities stored in local JSON files. If a valid Telegram token is provided the bot will automatically start when the FastAPI server is launched.

## Requirements

* Python 3.11+
* See `requirements.txt` for the list of Python packages

## Installation

### From source

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

### As an installable package

The repository ships a standard Python package declaration in `pyproject.toml`. You can install the bot directly from GitHub via pip:

```bash
pip install git+https://github.com/your-account/bot.git
```

The installation exposes two entry points:

* `telegram-salary-bot` – starts the Telegram bot in polling mode (equivalent to `python -m app.main`).
* `telegram-salary-bot-api` – launches the FastAPI application via Uvicorn (equivalent to `python -m app`).

To build distributable artifacts locally run:

```bash
python -m build
```

This command generates `.whl` and `.tar.gz` files under the `dist/` directory that can be published to PyPI or GitHub Packages. When targeting GitHub Packages make sure to:

1. Create a Personal Access Token with the `write:packages` and `read:packages` scopes.
2. Configure `~/.pypirc` with a section that points to the GitHub Packages upload endpoint and uses the generated token as the password. GitHub's documentation contains a ready-to-use template.
3. Upload the build using `twine upload --repository <section-name> dist/*`.

Once published, machines with access to the registry can install the package with:

```bash
pip install --extra-index-url https://pip.pkg.github.com/<OWNER> telegram-salary-bot
```

Replace `<OWNER>` with your GitHub username or organization.

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
