# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

HR/payroll system for the BONJOUR business: a Telegram bot for employees/admins plus a FastAPI HTTP API with a React admin panel. Manages employees, advance payout requests, salaries, vacations, shift check-ins, recruitment (AI-assisted interviews via the Anthropic API), and more. The UI, code comments, and commit messages are predominantly in Russian — follow that convention.

The repo also hosts a second, mostly-independent subsystem bolted onto the same admin panel/API: 3D shoe-last fit matching (see [Shoe-last fitting subsystem](#shoe-last-fitting-3d-scan-subsystem) below). Most recent commit activity on `claude/init-wmebv3` is in this subsystem, not HR/payroll.

Note: the repo root contains live production data (`user.json`, `advance_requests.json`, `hr.db`, `ФОТ админы *.xlsx`, salary report PNGs). Do not edit these data files unless the task is explicitly about the data.

## Commands

### Backend (Python 3.11+)

```bash
pip install -r requirements.txt

# API server + Telegram bot webhook processing (bot starts if TELEGRAM_BOT_TOKEN is set)
uvicorn app.server:app --host 0.0.0.0 --port 8000

# Telegram bot only, polling mode (this process owns all scheduled jobs)
python -m app.main

# VK bot — mirrors the employee-facing Telegram scenarios (menu, salary/
# schedule viewing, personal cabinet, payout requests, shift check-in).
# Admin scenarios and the recruitment/LLM layer are deliberately NOT
# ported (see app/vk_main.py's module docstring for the current list and
# reasoning) — the web admin covers those.
python -m app.vk_main

# One-time JSON → SQLite migration (idempotent)
python -m scripts.migrate_json_to_db
```

### Tests

```bash
pytest tests/                                   # all tests
pytest tests/test_payout_service.py             # one file
pytest tests/test_payout_service.py::test_name  # one test
```

There is no pytest.ini/pyproject — run from the repo root. `tests/conftest.py` replaces the `telegram` package with the lightweight stub in `telegram_stub/` and stubs `fpdf`, so tests never touch the real Telegram library. It also provides `make_employee_dict`, `make_payout_dict`, etc. factories and `tmp_json` fixtures for building temporary JSON data files.

### Admin frontend (React 19 + Vite + Tailwind)

```bash
cd admin_frontend
npm install
npm run dev      # Vite dev server
npm run build    # outputs dist/, which FastAPI serves at /admin
npm run lint     # eslint

# Capacitor iOS wrapper
npm run cap:sync
npm run cap:open:ios
```

The frontend calls the API via axios with `baseURL: '/api'` and a Bearer token from localStorage (`admin_frontend/src/api.js`); 401 redirects to `/admin/login` or `/employee/login`. Vite `base` is `/admin/`.

## Architecture

### Three processes, shared state

The system runs as three separate long-lived processes that share the same data files and SQLite DB:

1. **Bot process** (`python -m app.main`) — Telegram polling. This is the ONLY process that registers scheduled jobs (morning briefing, reminders); it also runs `init_db()` on startup.
2. **API process** (`uvicorn app.server:app`) — FastAPI app built by `app/api/create_app()`. It builds the Telegram Application with `create_application(with_jobs=False)` — registering jobs here too would double every scheduled message.
3. **VK bot process** (`python -m app.vk_main`) — a `vkbottle`-based port of the employee-facing Telegram scenarios only (see Commands above). Uses VK's Bot Long Poll API, no public webhook needed.

SQLite (`hr.db`) runs in WAL mode with a busy timeout (`app/db/session.py`) specifically so both processes can read/write concurrently. `launcher.py` is a Tkinter GUI (built into a Windows EXE) that starts/stops both processes; production runs on Windows behind ngrok.

### Layering

```
app/api/       FastAPI routers — each module exposes a create_*_router() factory,
               all wired together in app/api/__init__.py:create_app()
app/services/  Business logic (payouts, salary, payroll, recruitment, AI, ...)
app/data/      Repositories — JSON-file-backed (via json_storage.py) and SQLAlchemy-backed
app/models/    SQLAlchemy models (hr.db)
app/schemas/   Pydantic request/response schemas
app/handlers/  Telegram handlers, split admin/ vs user/, plus recruitment flows
app/core/      Telegram Application factory (application.py) and ConversationHandler
               definitions (conversations.py)
```

### Hybrid storage

Older entities (employees, payouts, vacations, adjustments, incentives, messages) live in JSON files in the repo root, accessed through repositories built on `app/data/json_storage.py`. Newer entities (recruitment, assets, tasks, payment calendar, ...) are SQLAlchemy models in `hr.db`. `app/db/session.py:init_db()` does `create_all` plus hand-rolled column migrations — there is no Alembic. External data sources: Firebird DB (sales figures for salary calc), amoCRM (manager salary), Avito/HeadHunter APIs (recruitment), Anthropic API (`app/services/llm_client.py`, AI interviews and text checks), Web Push (custom `admin_frontend/public/sw.js` — do not add VitePWA, it conflicts).

### Configuration

`app/settings.py` defines a pydantic-settings `Settings` class; values come from env vars / `.env`, and `app/config.py` additionally merges a `config.json` from the repo root. Key vars: `TELEGRAM_BOT_TOKEN` (bot doesn't start when unset/"dummy"), `ADMIN_TOKEN`, `EXCEL_FILE`, `FIREBIRD_*`, `AMO_*`. amoCRM tokens auto-refresh and get written back to `.env`.

### Auth

Session/token auth is handled by `app/services/access_control_service.py` with roles/permissions from `access_control.json`. API routes get the current user via `app/api/dependencies.py:get_current_user`; device endpoints (visitor counters) authenticate with an API key instead of a session.

### Mobile apps

- `admin_frontend/ios/` — Capacitor wrapper around the web admin (app.bonjour.pw).
- `ios-native/` — a separate, fully native SwiftUI app (own Xcode project) that talks to the same API; it does not replace the Capacitor app.

### Shoe-last fitting (3D scan) subsystem

Separate feature, same repo/API/admin panel: given a 3D scan of a customer's foot and a library of shoe lasts (колодки), determine which lasts fit and explain where/why they don't. Not HR/payroll — it shares only the process, auth, and deployment machinery.

- **Entry points**: `app/api/scanner.py` (raw `.stl` parse/preview), `app/api/lasts.py` (last library CRUD + `/lasts/match` fit comparison). Both gated behind the `3d-scanner` permission.
- **Frontend**: `admin_frontend/src/pages/Scanner3D.jsx` and `LastLibrary.jsx` (+ shared `FootScanCard.jsx`).
- **Core services**: `app/services/{scm_parser_service,stl_parser_service}.py` (file format → point cloud/mesh), `last_fit_service.py` / `last_fit_hybrid_service.py` / `fit_pipeline.py` / `fit_clearance.py` / `fit_size_match.py` (comparison + verdicts), `mesh3d_service.py` / `mesh_visualization_service.py` (3D mesh + rendered overlays), plus registration/pose/landmark helpers (`heel_fixed_registration.py`, `last_pose_*.py`, `foot_landmarks.py`, `curvilinear_sections.py`, etc.).
- **Storage**: shoe lasts are a flat `lasts.json` (`app/data/last_repository.py`) with raw scan files in `static/uploads/lasts/` — no DB involvement; a foot scan submitted for matching is never persisted, only compared on the fly.
- **Dependencies unique to this subsystem**: `trimesh`, `scipy`, `networkx`, `shapely` (mesh validation/repair/sectioning) plus shared `numpy`/`matplotlib`.
- **Docs**: `docs/last_fit_system_overview.md` (pipeline + current architecture, in Russian) and `docs/last_fit_verdicts.md` (verdict/threshold details) are the maintained reference — read those instead of re-deriving the pipeline from source. Note the overview doc predates the `trimesh`/mesh-distance work reflected in `requirements.txt` and `mesh3d_service.py`/`mesh_visualization_service.py`, so treat its "no mesh library installed" claims as historical, not current.
- Related research artifacts (`.scm` format reverse-engineering, sample point clouds, measurement dumps) live in the **outer** `C:\deploy` directory, not in this repo — see that directory's `CLAUDE.md`.
- Tests: `tests/test_{fit_clearance,fit_pipeline,fit_size_match,last_bottom_profile,last_fit_hybrid_service,last_fit_regression,last_pose_measurements,last_pose_service,last_registration_service,last_working_orientation,mesh3d_service,mesh_visualization_service,stl_parser_service}.py`.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
