"""Shared, on-disk cache of precomputed Firebird reports.

Why this exists, since the obvious fixes don't work here:

The Agbis database is Firebird 2.5 *Classic* — 18.8 GB, and every
connection gets its own private page cache of DefaultDbCachePages (512)
× 8 KB = 4 MB, which is discarded when that connection closes. So no
amount of query tuning on our side makes a repeated report cheap: the
only thing that keeps these reports fast is the Windows file cache, and
the box runs at ~2 GB free of 16 GB, so that gets evicted regularly.
Measured through the public URL, the same request lands anywhere between
0.5 s and 29 s depending purely on whether the pages happen to still be
in RAM.

Connection pooling is *not* the answer either — a fresh connect measures
18 ms, against the ~28 s spread we're trying to remove. What is left,
without touching the Agbis server itself, is to not make anyone wait for
the query at all: a separate process (app/warmer.py) computes these
reports on a schedule and stores the results here, and the API reads
them.

The cache is a table in hr.db rather than process memory because the
warmer and the API are different pm2 processes (bot-warmer / bot-app) —
see app/models/fdb_cache.py.

On a miss the API computes live, exactly as it did before this module
existed. Deliberately: stale figures are never served from here, so a
warmer that dies degrades the system back to its previous behaviour
instead of quietly showing yesterday's numbers. (The one place stale
data *is* still served is masters' existing timeout fallback, which is a
different condition — "Firebird is busy right now" — and is what stopped
the retry storm on 2026-07-28.)
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterator

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tier:
    """How fresh a report is kept.

    `refresh_s` is deliberately shorter than `ttl_s`: the warmer aims to
    replace an entry before it expires, so a normally-running warmer
    means readers essentially always hit. The gap between them is the
    slack that absorbs one skipped or slow warm cycle without users
    falling back to a live query.
    """

    name: str
    ttl_s: int
    refresh_s: int
    night_only: bool = False


TIERS: dict[str, Tier] = {
    # Cash registers: the balances report is reconciled against a physical
    # count of the drawer, so it is kept the freshest of everything here.
    "hot": Tier("hot", ttl_s=120, refresh_s=60),
    # The agreed target for the heavy screens: data no more than 5-10 min old.
    "frequent": Tier("frequent", ttl_s=600, refresh_s=300),
    "hourly": Tier("hourly", ttl_s=5400, refresh_s=3600),
    # Closed periods don't change; recompute them once, overnight, when the
    # Agbis server is idle.
    "nightly": Tier("nightly", ttl_s=172800, refresh_s=86400, night_only=True),
}

NIGHT_HOURS = range(2, 6)


@dataclass(frozen=True)
class Report:
    """A warmable report.

    `target` is resolved lazily rather than holding the callable: this
    module is imported by the API process at startup, and importing
    firebird_service eagerly would pull the fdb driver import with it.
    """

    name: str
    target: str
    tier: str


REPORTS: dict[str, Report] = {}


def _register(name: str, target: str, tier: str) -> None:
    REPORTS[name] = Report(name, target, tier)


# ── Registry ──────────────────────────────────────────────────────────
# Sales analytics: every panel of the "Аналитика продаж" page.
_register("sales.daily", "firebird:get_daily_sales", "frequent")
_register("sales.client_retention", "firebird:get_client_retention", "frequent")
_register("sales.margin", "firebird:get_margin_summary", "frequent")
_register("sales.turnaround", "firebird:get_turnaround_stats", "frequent")
_register("sales.receivables", "firebird:get_receivables", "frequent")
_register("sales.unclaimed", "firebird:get_unclaimed_orders", "frequent")
_register("sales.returns", "firebird:get_returns_summary", "frequent")
_register("sales.workplaces", "firebird:get_workplace_summary", "frequent")
_register("sales.departments", "firebird:get_department_comparison", "frequent")
_register("sales.top_products", "firebird:get_top_products", "frequent")
_register("salons.sclads", "firebird:get_sclads_list", "hourly")
# Masters: the single most expensive report on the system.
_register("masters.works", "masters:fetch_works", "frequent")
# Cash: cheap already, but included so every Firebird-backed screen behaves
# the same way. Kept in the hot tier — see TIERS.
_register("cash.balances", "firebird:get_cash_balances", "hot")
_register("cash.moves", "firebird:get_cash_moves", "hot")
_register("cash.daily_balances", "firebird:get_daily_cash_balances", "hot")
# Directories that change rarely but are on the critical path of several pages.
_register("employees.users_list", "firebird:get_users_list", "hourly")
_register("clients.churning", "firebird:get_churning_clients", "nightly")
_register("smses.list", "firebird:get_smses", "hourly")


def _resolve(target: str) -> Callable[..., Any]:
    kind, _, attr = target.partition(":")
    if kind == "firebird":
        from app.services.firebird_service import get_firebird_service

        return getattr(get_firebird_service(), attr)
    if kind == "masters":
        from app.services import masters_service

        return getattr(masters_service, attr)
    raise KeyError(f"Unknown report target: {target}")


# ── Argument encoding ─────────────────────────────────────────────────
# Args are stored positionally rather than by keyword so this stays
# indifferent to the parameter names of the service methods it calls —
# the cache key has to match byte-for-byte between the warmer and the
# reader, and positional encoding is the form both sides already have.

def _encode(value: Any) -> Any:
    if isinstance(value, date) and not isinstance(value, datetime):
        return {"__date__": value.isoformat()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and set(value) == {"__date__"}:
        return date.fromisoformat(value["__date__"])
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def encode_args(args: tuple | list) -> str:
    return json.dumps([_encode(a) for a in args], ensure_ascii=False, sort_keys=True)


def decode_args(args_json: str) -> list:
    return [_decode(a) for a in json.loads(args_json)]


def make_key(report: str, args: tuple | list) -> str:
    """Stable key for (report, args). Hashed so a key never grows with
    the argument list, and prefixed with the report name so the table
    stays readable when someone looks at it directly."""
    digest = hashlib.sha1(encode_args(args).encode("utf-8")).hexdigest()[:16]
    return f"{report}:{digest}"


# ── Storage ───────────────────────────────────────────────────────────

def _session():
    from app.db.session import SessionLocal

    return SessionLocal()


def _entry_model():
    from app.models.fdb_cache import FdbCacheEntry

    return FdbCacheEntry


def get(report: str, args: tuple | list = ()) -> tuple[Any, float] | None:
    """Cached value and its age in seconds, or None if absent or older
    than its tier's TTL."""
    spec = REPORTS.get(report)
    ttl = TIERS[spec.tier].ttl_s if spec else TIERS["frequent"].ttl_s
    row = _load(make_key(report, args))
    if row is None:
        return None
    value, age = row
    if age > ttl:
        return None
    return value, age


def peek(report: str, args: tuple | list = ()) -> tuple[Any, float] | None:
    """Same as get() but ignoring the TTL — for the status panel, which
    needs to show how old an expired entry is rather than pretend it
    isn't there."""
    return _load(make_key(report, args))


def age_of(report: str, args: tuple | list = ()) -> float | None:
    """Age of a stored entry in seconds, without decompressing it.

    Both hot paths that only need the age — the warmer's is_due check and
    the status panel — run over the whole plan (70+ entries) on a short
    interval. Going through _load there would gunzip every value each
    time, several MB of pointless work per pass.
    """
    Entry = _entry_model()
    try:
        session = _session()
    except Exception as exc:
        logger.warning(f"fdb_cache: cannot open hr.db: {exc}")
        return None
    try:
        row = (
            session.query(Entry.computed_at)
            .filter(Entry.key == make_key(report, args))
            .one_or_none()
        )
        if row is None:
            return None
        return (datetime.now() - datetime.fromisoformat(row[0])).total_seconds()
    except Exception as exc:
        logger.warning(f"fdb_cache: age lookup failed for {report}: {exc}")
        return None
    finally:
        session.close()


def _load(key: str) -> tuple[Any, float] | None:
    Entry = _entry_model()
    try:
        session = _session()
    except Exception as exc:
        logger.warning(f"fdb_cache: cannot open hr.db: {exc}")
        return None
    try:
        row = session.query(Entry).filter(Entry.key == key).one_or_none()
        if row is None:
            return None
        try:
            value = json.loads(gzip.decompress(row.value_gz).decode("utf-8"))
        except Exception as exc:
            logger.warning(f"fdb_cache: corrupt entry {key}: {exc}")
            return None
        try:
            age = (datetime.now() - datetime.fromisoformat(row.computed_at)).total_seconds()
        except Exception:
            age = float("inf")
        return value, age
    except Exception as exc:
        logger.warning(f"fdb_cache: read failed for {key}: {exc}")
        return None
    finally:
        session.close()


def put(report: str, args: tuple | list, value: Any, duration_ms: int = 0) -> None:
    spec = REPORTS.get(report)
    tier = spec.tier if spec else "frequent"
    key = make_key(report, args)
    try:
        raw = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
    except Exception as exc:
        logger.warning(f"fdb_cache: {report} is not serialisable, not caching: {exc}")
        return
    blob = gzip.compress(raw, compresslevel=6)
    Entry = _entry_model()
    try:
        session = _session()
    except Exception as exc:
        logger.warning(f"fdb_cache: cannot open hr.db: {exc}")
        return
    try:
        row = session.query(Entry).filter(Entry.key == key).one_or_none()
        if row is None:
            row = Entry(key=key, report=report)
            session.add(row)
        row.args_json = encode_args(args)
        row.tier = tier
        row.value_gz = blob
        row.computed_at = datetime.now().isoformat(timespec="seconds")
        row.duration_ms = int(duration_ms)
        row.size_bytes = len(raw)
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning(f"fdb_cache: write failed for {key}: {exc}")
    finally:
        session.close()


def compute(report: str, args: tuple | list = ()) -> Any:
    """Run the report for real and store the result. Blocking — callers in
    the API must go through run_with_timeout."""
    fn = _resolve(REPORTS[report].target)
    started = datetime.now()
    value = fn(*args)
    duration_ms = (datetime.now() - started).total_seconds() * 1000
    put(report, args, value, int(duration_ms))
    return value


def get_or_compute(report: str, args: tuple | list = ()) -> Any:
    """Cached value if it's within its tier's TTL, otherwise compute it
    live (and cache it, so the next reader doesn't repeat the wait).

    Blocking. This is what API handlers call, inside run_with_timeout.
    """
    hit = get(report, args)
    if hit is not None:
        return hit[0]
    return compute(report, args)


# ── Warm plan ─────────────────────────────────────────────────────────

def _period(name: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if name == "today":
        return today, today
    if name == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if name == "week":
        return today - timedelta(days=6), today
    if name == "month":
        return today.replace(day=1), today
    if name == "prev_month":
        last = today.replace(day=1) - timedelta(days=1)
        return last.replace(day=1), last
    if name == "quarter":
        return today - timedelta(days=89), today
    raise KeyError(name)


# Which periods each tier warms. "today"/"month" are what the pages open
# on; the rest are the presets a user reaches for next.
TIER_PERIODS: dict[str, tuple[str, ...]] = {
    "frequent": ("today", "month"),
    "hourly": ("yesterday", "week"),
    "nightly": ("prev_month", "quarter"),
}

# Reports taking (date_from, date_to) plus trailing optional filters we
# warm unfiltered — a filtered view stays a live query, since the filter
# space is unbounded.
_RANGE_REPORTS: dict[str, tuple] = {
    "sales.daily": (None,),
    "sales.client_retention": (None,),
    "sales.margin": (None,),
    "sales.turnaround": (None, None, None),
    "sales.receivables": (),
    "sales.returns": (None, None),
    "sales.workplaces": (None,),
    "sales.departments": (None, None, None),
    "masters.works": (),
    "cash.moves": (),
}


def warm_plan(now: datetime | None = None) -> Iterator[tuple[str, tuple, str]]:
    """(report, args, tier) for everything the warmer should keep hot.

    Yields the hot tier first so that, if a cycle runs long, the reports
    with the tightest freshness promise are the ones that already ran.
    """
    now = now or datetime.now()
    today = now.date()

    # hot — cash
    yield ("cash.balances", (), "hot")
    month_from, month_to = _period("month", today)
    from app.services.firebird_service import CASH_BALANCE_KASSA_IDS

    for kassa_id in CASH_BALANCE_KASSA_IDS:
        yield ("cash.daily_balances", (kassa_id, month_from, month_to), "hot")

    for tier, periods in TIER_PERIODS.items():
        for period in periods:
            df, dt = _period(period, today)
            for report, extra in _RANGE_REPORTS.items():
                if REPORTS[report].tier == "hot":
                    # Cash reports follow the cash tier, not the period tiers.
                    continue
                yield (report, (df, dt, *extra), tier)
            yield ("sales.top_products", (df, dt, 20, None, None, None), tier)

    yield ("cash.moves", (month_from, month_to), "hot")

    # Parameterless / non-range directories. The argument values here are
    # the endpoints' own defaults — a warmed key is only ever hit if it
    # matches what the page actually sends, so these have to track the
    # Query(default=...) declarations in app/api/, not look reasonable.
    yield ("salons.sclads", (), "hourly")
    yield ("sales.unclaimed", (90,), "frequent")
    yield ("employees.users_list", ("",), "hourly")
    yield ("smses.list", (month_from, month_to), "hourly")
    yield ("clients.churning", (365, 3), "nightly")


def is_due(report: str, args: tuple | list, tier: str, now: datetime | None = None) -> bool:
    """Whether the warmer should recompute this entry now."""
    spec = TIERS[tier]
    if spec.night_only and (now or datetime.now()).hour not in NIGHT_HOURS:
        return False
    age = age_of(report, args)
    if age is None:
        return True
    return age >= spec.refresh_s
