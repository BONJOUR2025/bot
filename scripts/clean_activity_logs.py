"""Разовая чистка журнала активности (logs/users/).

    python -m scripts.clean_activity_logs <каталог бота>            # что будет сделано
    python -m scripts.clean_activity_logs <каталог бота> --apply    # сделать

Что делает:
1. Кладёт всю папку logs/users как есть в logs/archive/users_<дата>.zip —
   ничего не теряется, при надобности можно достать.
2. Удаляет файлы посторонних: людей, которых нет ни среди пользователей
   Telegram/VK-бота, ни среди учётных записей админки. Это личные переписки,
   попавшие в журнал через режим «Секретарь», плюс старые служебные
   (anonymous, admin).
3. Склеивает все файлы одного человека (подписи в боте и админке разные —
   было по 2–4 файла) в один «<id>_<имя>.log» по времени.
4. Переводит старые сырые строки «GET /api/... -> 200» в тот же вид, что
   пишет новый журнал (app/utils/activity.py): изменения — с разделом и
   адресом, служебное и чтение — прочь, кроме однозначных открытий страниц
   в кабинетах мастера, старшего мастера и менеджера (см. API_PAGE).

Процессы бота и API держат файлы открытыми — запускать с остановленными
bot-main, bot-vk и bot-app.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.utils import activity

LINE_START = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} ")
RAW_API = re.compile(r"^(?P<head>.* - INFO - \[(?P<who>[^\]]*)\]) (?P<method>[A-Z]+) (?P<path>/\S*) -> (?P<status>\d{3})$")
TS = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3}")

# Чтение API → какую страницу человек открыл. В истории нет заголовка
# X-Page, а по адресу страница понятна не всегда: дашборд, например, грузит
# те же адреса, что «Выплаты», «Задачи» и «Отпуска». Поэтому только
# однозначные — кабинеты мастера, старшего мастера и менеджера; остальное
# чтение из истории просто уходит, изменения остаются.
API_PAGE = (
    ("/api/masters/me/earnings", "/employee/earnings"),
    ("/api/masters/me/wip", "/employee/wip"),
    ("/api/masters/me/scan/lookup", "/employee/scan"),
    ("/api/managers/me/kpi", "/employee/kpi"),
    ("/api/salon/me/shifts", "/employee/schedule"),
    ("/api/salon/me/assets", "/employee/assets"),
    ("/api/workshop/overview", "/employee/workshop"),
    ("/api/payroll/my", "/employee/salary"),
)


def guess_page(path: str) -> str | None:
    for prefix, page in API_PAGE:
        if path == prefix or path.startswith(prefix + "/"):
            return page
    return None


def load_people(root: Path) -> dict[str, str]:
    """id → имя для всех, кто законно может быть в журнале."""
    people: dict[str, str] = {}

    def read(name):
        p = root / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    for uid, u in (read("bot_users.json") or {}).items():
        people[str(uid)] = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x) or u.get("username") or ""
    vk = read("vk_bot_users.json") or {}
    for uid, u in (vk.items() if isinstance(vk, dict) else []):
        name = " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x)
        people.setdefault(f"vk_{uid}", name)
        if u.get("employee_id"):
            people.setdefault(str(u["employee_id"]), name)
    emps = read("user.json") or {}
    for eid, e in (emps.items() if isinstance(emps, dict) else []):
        people[str(eid)] = e.get("name") or e.get("full_name") or people.get(str(eid), "")
    for u in (read("access_control.json") or {}).get("users", []):
        uid = str(u.get("id"))
        # Логин админки — то имя, под которым человека знают в панели.
        people[uid] = u.get("login") or people.get(uid) or ""
    return people


def owner_of(stem: str, ids: list[str]) -> str | None:
    for uid in ids:  # отсортированы по длине убыванием: «nb_1» раньше «nb»
        if stem == uid or stem.startswith(uid + "_"):
            return uid
    return None


def read_entries(path: Path) -> list[str]:
    """Записи файла; продолжения многострочных сообщений — к своей записи."""
    entries: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if LINE_START.match(line) or not entries:
            entries.append(line)
        else:
            entries[-1] += "\n" + line
    return entries


def convert(entries: list[str], key: str) -> list[str]:
    activity._last_open.clear()
    out = []
    for e in sorted(entries, key=lambda x: x[:23]):
        m = RAW_API.match(e)
        if not m:
            out.append(e)
            continue
        ts = TS.match(e)
        now = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S").timestamp() if ts else 0
        method, path, status = m["method"], m["path"], int(m["status"])
        page = guess_page(path) if method == "GET" and status < 400 else None
        for text in activity.entries(key, method, path, status, page, [], now=now):
            out.append(f"{m['head']} {text}")
    return out


# Подробности сканов в истории: middleware писал только «POST …/scan/confirm»,
# а номер заказа и итог есть в общем логе (logs/bot/app.log*) от master_scan.
SCAN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} - INFO - Скан: (?P<name>.+?) \(Агбис \d+\) "
    r"(?P<act>in|out), бирка (?P<bc>\d+), заказ (?P<doc>\S+) — (?P<out>.*)$")
LEAD_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{3} - INFO - Отметка старшего мастера (?P<name>.+?) за "
    r"(?P<master>.+?) \(Агбис \d+\): (?P<act>in|out|both), бирка (?P<bc>\d+), заказ (?P<doc>\S+) — (?P<out>.*)$")
ACT = {"in": "вход", "out": "выход", "both": "вход и выход"}


def _outcome(text: str) -> str:
    if text.startswith("ЗАПИСАН"):
        return "записан в Агбис"
    if text.startswith("пробно"):
        return "пробный режим, в Агбис не записан"
    if text.startswith("записано ничего"):
        return "не записано"
    if text.startswith("записано"):
        return "записано в Агбис"
    return text


def load_scans(root: Path) -> list[tuple[float, str, str, str]]:
    """(время, фамилия, адрес запроса, описание) из общего лога."""
    events = []
    for f in sorted((root / "logs" / "bot").glob("app.log*")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            m = SCAN_RE.match(line)
            if m:
                events.append((datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S").timestamp(),
                               m["name"].split()[0], "/api/masters/me/scan/confirm",
                               f"скан: {ACT[m['act']]}, заказ {m['doc']}, бирка {m['bc']} — {_outcome(m['out'])}"))
                continue
            m = LEAD_RE.match(line)
            if m:
                events.append((datetime.strptime(m["ts"], "%Y-%m-%d %H:%M:%S").timestamp(),
                               m["name"].split()[0], "/api/workshop/scan/confirm",
                               f"поставил {ACT[m['act']]} за мастера {m['master']}: заказ {m['doc']}, "
                               f"бирка {m['bc']} — {_outcome(m['out'])}"))
    return events


def enrich_scans(lines: list[str], label: str, scans: list) -> list[str]:
    surname = (label or "").split()[0] if label else ""
    if not surname:
        return lines
    mine = [e for e in scans if e[1] == surname]
    used: set[int] = set()
    out = []
    for line in lines:
        m = re.search(r"\((POST (/api/masters/me/scan/confirm|/api/workshop/scan/confirm))\)$", line)
        ts = TS.match(line)
        if m and ts:
            t = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
            best = None
            for i, e in enumerate(mine):
                if i not in used and e[2] == m.group(2) and -1 <= t - e[0] <= 10:
                    best = i
                    break
            head = line.split("] ", 1)[0] + "]"
            if best is not None:
                used.add(best)
                line = f"{head} {mine[best][3]}"
            elif "/workshop/" in m.group(2):
                line = f"{head} поставил отметку за мастера (подробности не сохранились)"
            else:
                line = f"{head} скан бирки (подробности не сохранились)"
        out.append(line)
    return out


def drop_refresh_opens(lines: list[str]) -> list[str]:
    """Экран скана после каждой бирки сам перезагружает заработок — в истории
    это выглядит как «открыл «Заработок»» через секунду после скана."""
    out: list[str] = []
    last_change = None
    for line in lines:
        ts = TS.match(line)
        t = datetime.strptime(ts.group(1), "%Y-%m-%d %H:%M:%S").timestamp() if ts else None
        text = line.split("] ", 1)[1] if "] " in line else ""
        if text.startswith("открыл") and t is not None and last_change is not None and 0 <= t - last_change <= 3:
            continue
        if not text.startswith("открыл") and t is not None:
            last_change = t
        out.append(line)
    return out


def safe(label: str) -> str:
    return re.sub(r"[^\w.-]+", "_", label).strip("_")


def main(root: Path, apply: bool) -> None:
    users_dir = root / "logs" / "users"
    files = sorted(p for p in users_dir.iterdir() if p.is_file() and ".log" in p.name)
    people = load_people(root)
    scans = load_scans(root)
    ids = sorted(people, key=len, reverse=True)

    groups: dict[str, list[Path]] = defaultdict(list)
    strangers: list[Path] = []
    for f in files:
        stem = f.name.split(".log")[0]
        uid = owner_of(stem, ids)
        (groups[uid].append(f) if uid else strangers.append(f))

    size = lambda ps: sum(p.stat().st_size for p in ps) // 1024
    print(f"Файлов: {len(files)}, {size(files)} КБ")
    print(f"Посторонние — удалить: {len(strangers)} ({size(strangers)} КБ)")
    for f in strangers:
        print("   -", f.name)

    plan = []
    for uid, fs in groups.items():
        label = safe(people.get(uid) or "") or safe(fs[0].name.split(".log")[0][len(uid):])
        target = users_dir / (f"{uid}_{label}.log" if label else f"{uid}.log")
        entries = [e for f in fs for e in read_entries(f)]
        new = [e for e in drop_refresh_opens(enrich_scans(convert(entries, uid), people.get(uid) or "", scans))
               if e.strip()]
        if not new:
            # Ничего, кроме служебных запросов, — пустой файл не нужен.
            plan.append((None, fs, new))
            print(f"{fs[0].name}: только служебное — удалить")
            continue
        plan.append((target, fs, new))
        print(f"{target.name}: {len(fs)} файл(а), {len(entries)} → {len(new)} записей")

    if not apply:
        print("\nСухой прогон. Запустите с --apply, чтобы применить.")
        return

    archive_dir = root / "logs" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive = archive_dir / f"users_{datetime.now():%Y-%m-%d_%H%M}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(f, f"users/{f.name}")
    print(f"\nАрхив: {archive} ({archive.stat().st_size // 1024} КБ)")

    for f in strangers:
        f.unlink()
    for target, fs, new in plan:
        if target is None:
            for f in fs:
                f.unlink()
            continue
        tmp = target.with_suffix(".tmp")
        tmp.write_text("\n".join(new) + ("\n" if new else ""), encoding="utf-8")
        for f in fs:
            f.unlink()
        tmp.rename(target)
    left = [p for p in users_dir.iterdir() if p.is_file()]
    print(f"Готово: {len(left)} файлов, {size(left)} КБ")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--apply" in sys.argv)
