import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  RefreshCw, Image as ImageIcon, FileSpreadsheet, FileText, Calculator, Hammer, Users, Truck, Wallet, TrendingDown, UserRound,
  SlidersHorizontal, X, Check, Plus, Trash2, Building2, CalendarRange, Percent,
} from 'lucide-react';
import { PieChart, Pie, Cell } from 'recharts';
import { toPng } from 'html-to-image';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';

const REPORT_WIDTH = 1080;

// Scales the fixed-1080px report to fit narrow viewports via CSS transform —
// the report DOM itself stays at full size (unaffected, since html-to-image
// captures reportRef's own box, not this wrapper's transform), so PNG export
// fidelity is untouched while the on-screen view fits phones/tablets.
function ScaledReport({ children }) {
  const outerRef = useRef(null);
  const innerRef = useRef(null);
  const [scale, setScale] = useState(1);
  const [height, setHeight] = useState(null);

  useLayoutEffect(() => {
    const recompute = () => {
      const outerWidth = outerRef.current?.offsetWidth || REPORT_WIDTH;
      const naturalHeight = innerRef.current?.offsetHeight || 0;
      const next = Math.min(1, outerWidth / REPORT_WIDTH);
      setScale(next);
      setHeight(naturalHeight * next);
    };
    recompute();
    const ro = new ResizeObserver(recompute);
    if (outerRef.current) ro.observe(outerRef.current);
    if (innerRef.current) ro.observe(innerRef.current);
    return () => ro.disconnect();
  });

  return (
    <div ref={outerRef} style={{ width: '100%', height: height ?? undefined, overflow: 'hidden' }}>
      <div ref={innerRef} style={{ width: REPORT_WIDTH, transform: `scale(${scale})`, transformOrigin: 'top left' }}>
        {children}
      </div>
    </div>
  );
}

const MANAGER_POSITION = 'менеджер по работе с клиентами';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Math.round(Number(v)).toLocaleString('ru-RU')} ₽`);
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
const lastDay = (ym) => { const [y, m] = ym.split('-').map(Number); return new Date(y, m, 0).getDate(); };
const fmtDateRu = (iso) => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };

// ── Date range helpers ────────────────────────────────────────────────────────
// Дату берём ЛОКАЛЬНУЮ, а не через toISOString(): тот переводит в UTC, и
// полночь 1 сентября по Москве превращается в «31 августа». Из-за этого обе
// границы периода съезжали на день назад, «Этот месяц» показывал 31.08–29.09,
// а в отчёт затягивался лишний календарный месяц — с его окладами. То есть
// суммы были не просто сдвинуты, а завышены на целый месяц.
const isoDate = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const monthRange = (year, month0) => ({ from: isoDate(new Date(year, month0, 1)), to: isoDate(new Date(year, month0 + 1, 0)) });
const thisMonthRange = () => { const d = new Date(); return monthRange(d.getFullYear(), d.getMonth()); };
const quarterRange = (year, q) => ({ from: isoDate(new Date(year, q * 3, 1)), to: isoDate(new Date(year, q * 3 + 3, 0)) });
const thisQuarterRange = () => { const d = new Date(); return quarterRange(d.getFullYear(), Math.floor(d.getMonth() / 3)); };
const lastQuarterRange = () => {
  const d = new Date();
  let q = Math.floor(d.getMonth() / 3) - 1, y = d.getFullYear();
  if (q < 0) { q = 3; y -= 1; }
  return quarterRange(y, q);
};
const thisYearRange = () => { const d = new Date(); return { from: `${d.getFullYear()}-01-01`, to: isoDate(new Date(d.getFullYear(), 11, 31)) }; };

const DATE_PRESETS = [
  { key: 'this-month', label: 'Этот месяц', range: thisMonthRange },
  { key: 'this-quarter', label: 'Этот квартал', range: thisQuarterRange },
  { key: 'last-quarter', label: 'Прошлый квартал', range: lastQuarterRange },
  { key: 'this-year', label: 'Этот год', range: thisYearRange },
];

// Every "monthly" data source (admin payroll calc, manager/courier plans)
// is keyed by calendar month server-side — a custom range gets split into
// the months it touches, each loaded in full and merged per employee. If
// the range doesn't align to month boundaries, the oklad/plan for the
// first and last month is still counted in full (there's no daily pro-rated
// plan in the underlying data model).
// Запускает задачи пачками по `limit` штук вместо всех разом.
//
// Зачем. payroll/calculate ходит в Firebird и стоит 8–12 секунд на месяц. При
// выборе «Этот год» страница запускала все 12 сразу; браузер их выстраивал в
// очередь по 6, а сервер захлёбывался — проверено: после такой загрузки API не
// отвечал 20 секунд, то есть падала вся панель, а не только этот отчёт.
// Последовательно-по-двое выходит не медленнее, но никого не роняет.
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (true) {
      const i = next++;
      if (i >= items.length) return;
      out[i] = await fn(items[i], i);
    }
  });
  await Promise.all(workers);
  return out;
}

const MONTH_CONCURRENCY = 2;

function monthsInRange(dateFrom, dateTo) {
  const out = [];
  let [y, m] = dateFrom.split('-').map(Number);
  const [ty, tm] = dateTo.split('-').map(Number);
  while (y < ty || (y === ty && m <= tm)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return out;
}

function mergeRowsAcrossMonths(rowArrays) {
  // Key by employee_code (stable across months) when available — merging by
  // display name alone splits one person into two rows the moment their
  // name is spelled slightly differently between months (nickname vs full
  // name, a typo fix, etc.), which reads as a phantom duplicate employee.
  const map = new Map();
  for (const rows of rowArrays) {
    for (const r of rows) {
      const key = r.code || r.name;
      if (!map.has(key)) { map.set(key, { ...r }); continue; }
      const acc = map.get(key);
      for (const k of ['oklad', 'commission', 'bonuses', 'penalties', 'advances', 'gross', 'to_pay']) {
        acc[k] = (acc[k] || 0) + (r[k] || 0);
      }
    }
  }
  return [...map.values()].sort((a, b) => b.gross - a.gross);
}

const COLS = [
  { key: 'oklad', label: 'Оклад' },
  { key: 'commission', label: 'Комиссия / KPI' },
  { key: 'bonuses', label: 'Премии' },
  { key: 'penalties', label: 'Штрафы' },
  { key: 'advances', label: 'Авансы' },
  { key: 'gross', label: 'Начислено' },
];

const sumRows = (rows) => {
  const t = {};
  for (const c of COLS) t[c.key] = (rows || []).reduce((s, r) => s + (Number(r[c.key]) || 0), 0);
  return t;
};

// ── Per-category, per-month loaders (raw, one calendar month at a time) ──────

async function loadAdminsMonth(period, signal) {
  const [y, m] = period.split('-').map(Number);
  const monthName = MONTHS_RU[m - 1].toUpperCase();
  const res = await api.get('payroll/calculate', { params: { month: monthName, year: y }, signal });
  return (res.data?.rows || []).map((r) => ({
    code: r.employee_code || '',
    name: r.employee_name || r.employee_code || '—',
    oklad: r.base_salary || 0,
    commission: r.total_commission || 0,
    bonuses: (r.bonuses || 0) + (r.excel_bonus || 0),
    penalties: r.penalties || 0,
    advances: r.advances || 0,
    gross: r.total_gross ?? ((r.base_salary || 0) + (r.total_commission || 0) + (r.bonuses || 0) + (r.excel_bonus || 0)),
    to_pay: r.total_net ?? 0,
  })).filter((r) => r.gross || r.oklad || r.commission || r.advances);
}
async function loadAdmins(dateFrom, dateTo, signal) {
  const perMonth = await mapLimit(monthsInRange(dateFrom, dateTo), MONTH_CONCURRENCY, (period) => loadAdminsMonth(period, signal));
  return mergeRowsAcrossMonths(perMonth);
}

async function loadMastersRange(from, to, signal) {
  const res = await api.get('masters/works', { params: { date_from: from, date_to: to }, signal });
  const data = res.data;
  const services = Array.isArray(data) ? data : (data.services || []);
  const map = {};
  for (const r of services) {
    if (r.master_salary == null) continue;
    const name = r.out_description || '—';
    map[name] = (map[name] || 0) + (Number(r.master_salary) || 0);
  }
  return Object.entries(map)
    .map(([name, sal]) => ({ name, oklad: 0, commission: sal, bonuses: 0, penalties: 0, advances: 0, gross: sal, to_pay: sal }));
}

// masters/works принимает произвольный диапазон, но за год не успевает: сервер
// отвечает 504 «Запрос выполняется слишком долго», и в отчёте мастера
// оказывались нулями. Поэтому режем по календарным месяцам — с обрезкой по
// краям, чтобы 10–20 сентября остались 10–20 сентября, а не всем сентябрём.
async function loadMasters(dateFrom, dateTo, signal) {
  const periods = monthsInRange(dateFrom, dateTo);
  if (periods.length <= 1) return (await loadMastersRange(dateFrom, dateTo, signal)).sort((a, b) => b.gross - a.gross);
  const perMonth = await mapLimit(periods, MONTH_CONCURRENCY, (period) => {
    const monthFrom = `${period}-01`;
    const monthTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
    return loadMastersRange(monthFrom > dateFrom ? monthFrom : dateFrom, monthTo < dateTo ? monthTo : dateTo, signal);
  });
  return mergeRowsAcrossMonths(perMonth);
}

async function loadManagersMonth(period, rangeFrom, rangeTo, emp, signal) {
  const monthFrom = `${period}-01`;
  const monthTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const incFrom = monthFrom > rangeFrom ? monthFrom : rangeFrom;
  const incTo = monthTo < rangeTo ? monthTo : rangeTo;
  const managers = emp.filter((e) => e.status !== 'inactive' && (e.position || '').trim().toLowerCase() === MANAGER_POSITION);
  const rows = await Promise.all(managers.map(async (mgr) => {
    const plan = await api.get('manager-salary/plan', { params: { employee_code: mgr.id, period }, signal }).then((r) => r.data).catch(() => ({}));
    const adv = await api.get('manager-salary/advances', { params: { employee_id: mgr.id }, signal }).then((r) => r.data).catch(() => ({ total: 0 }));
    const inc = await api.get('incentives/', { params: { employee_id: mgr.id, date_from: incFrom, date_to: incTo }, signal }).then((r) => r.data).catch(() => []);
    const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    let met = null;
    if (mgr.amo_user_id) {
      met = await api.get('manager-salary/metrics', { params: { date_from: incFrom, date_to: incTo, amo_user_id: mgr.amo_user_id }, signal }).then((r) => r.data).catch(() => null);
    }
    const calc = await api.post('manager-salary/calc', {
      oklad: plan.oklad, kpi_max: plan.kpi_max,
      revenue_plan: plan.revenue_plan, revenue_actual: met?.revenue_actual || 0,
      repair_plan_conv: plan.repair_plan_conv, repair_target_deals: met?.repair_target_deals || 0, repair_total_deals: met?.repair_total_deals || 0,
      sew_plan_conv: plan.sew_plan_conv, sew_target_deals: met?.sew_target_deals || 0, sew_total_deals: met?.sew_total_deals || 0, sew_new_leads: met?.sew_new_leads || 0,
      advances: adv?.total || 0, bonuses, penalties,
    }, { signal }).then((r) => r.data).catch(() => null);
    if (!calc) return null;
    return {
      code: mgr.id, name: mgr.full_name || mgr.name, oklad: calc.oklad, commission: calc.kpi,
      bonuses: calc.bonuses, penalties: calc.penalties, advances: calc.advances,
      gross: calc.gross, to_pay: calc.to_pay,
    };
  }));
  return rows.filter(Boolean);
}
async function loadManagers(dateFrom, dateTo, signal) {
  // Справочник сотрудников от месяца не зависит — читаем один раз на
  // категорию. Раньше он запрашивался внутри каждого месяца, и за «год»
  // уходило 12 лишних одинаковых запросов на менеджеров и столько же на
  // курьеров.
  const emp = await api.get('employees/', { params: { archived: false }, signal }).then((r) => r.data || []);
  const perMonth = await mapLimit(monthsInRange(dateFrom, dateTo), MONTH_CONCURRENCY,
    (period) => loadManagersMonth(period, dateFrom, dateTo, emp, signal));
  return mergeRowsAcrossMonths(perMonth);
}

async function loadCouriersMonth(period, rangeFrom, rangeTo, emp, signal) {
  const monthFrom = `${period}-01`;
  const monthTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const incFrom = monthFrom > rangeFrom ? monthFrom : rangeFrom;
  const incTo = monthTo < rangeTo ? monthTo : rangeTo;
  const couriers = emp.filter((e) => e.status !== 'inactive' && (e.position || '').toLowerCase().includes('курьер'));
  const rows = await Promise.all(couriers.map(async (c) => {
    const plan = await api.get('courier-salary/plan', { params: { employee_code: c.id, period }, signal }).then((r) => r.data).catch(() => ({}));
    const adv = await api.get('courier-salary/advances', { params: { employee_id: c.id }, signal }).then((r) => r.data).catch(() => ({ total: 0 }));
    const inc = await api.get('incentives/', { params: { employee_id: c.id, date_from: incFrom, date_to: incTo }, signal }).then((r) => r.data).catch(() => []);
    const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const calc = await api.post('courier-salary/calc', { oklad: plan.oklad, advances: adv?.total || 0, bonuses, penalties }, { signal }).then((r) => r.data).catch(() => null);
    if (!calc) return null;
    return { code: c.id, name: c.full_name || c.name, oklad: calc.oklad, commission: 0, bonuses: calc.bonuses, penalties: calc.penalties, advances: calc.advances, gross: calc.gross, to_pay: calc.to_pay };
  }));
  return rows.filter(Boolean).filter((r) => r.gross || r.advances);
}
async function loadCouriers(dateFrom, dateTo, signal) {
  // Справочник сотрудников от месяца не зависит — читаем один раз на
  // категорию. Раньше он запрашивался внутри каждого месяца, и за «год»
  // уходило 12 лишних одинаковых запросов на менеджеров и столько же на
  // курьеров.
  const emp = await api.get('employees/', { params: { archived: false }, signal }).then((r) => r.data || []);
  const perMonth = await mapLimit(monthsInRange(dateFrom, dateTo), MONTH_CONCURRENCY,
    (period) => loadCouriersMonth(period, dateFrom, dateTo, emp, signal));
  return mergeRowsAcrossMonths(perMonth);
}

// ── ФОТ по салонам ───────────────────────────────────────────────────────────
// Отдельный разрез: сервер раскладывает те же оклады и комиссии по салонам, где
// прошли продажи. Считается это дороже обычного расчёта (месяц ≈ 9 секунд), а
// за год — полторы минуты, поэтому грузим не вместе с отчётом, а по кнопке.
// Население то же, что у «администраторов»: мастера, менеджеры и курьеры к
// салону не привязаны.
async function loadSalonsMonth(period, signal) {
  const [y, m] = period.split('-').map(Number);
  const monthName = MONTHS_RU[m - 1].toUpperCase();
  const res = await api.get('payroll/by-salon', { params: { month: monthName, year: y }, signal });
  return res.data?.salons || [];
}

const SALON_MONEY_FIELDS = ['oklad', 'bonuses', 'repair_commission', 'cosmetics_commission', 'shoes_commission', 'total'];

function mergeSalonsAcrossMonths(perMonth) {
  const map = new Map();
  for (const salons of perMonth || []) {
    for (const s of salons || []) {
      let acc = map.get(s.salon_id);
      if (!acc) {
        acc = { salon_id: s.salon_id, salon_name: s.salon_name, staff: new Map() };
        for (const f of SALON_MONEY_FIELDS) acc[f] = 0;
        map.set(s.salon_id, acc);
      }
      for (const f of SALON_MONEY_FIELDS) acc[f] += Number(s[f]) || 0;
      for (const e of s.employees || []) {
        const prev = acc.staff.get(e.employee_code) || 0;
        acc.staff.set(e.employee_code, prev + (Number(e.total) || 0));
      }
    }
  }
  return [...map.values()]
    .map((s) => ({
      ...s,
      commission: s.repair_commission + s.cosmetics_commission + s.shoes_commission,
      headcount: s.staff.size,
    }))
    .sort((a, b) => b.total - a.total);
}

const CATS = [
  { key: 'admins', title: 'Администраторы', icon: Calculator, color: 'var(--color-primary)', load: loadAdmins },
  { key: 'masters', title: 'Мастера', icon: Hammer, color: 'var(--color-warning)', load: loadMasters },
  { key: 'managers', title: 'Менеджеры', icon: Users, color: 'var(--color-success)', load: loadManagers },
  { key: 'couriers', title: 'Курьеры', icon: Truck, color: 'var(--color-danger)', load: loadCouriers },
];

// Accent colors — fixed, look good in both themes
const BRAND = 'var(--color-primary)', DANGER = 'var(--color-danger)';

// Light theme for PNG export
const LIGHT = {
  bg: '#ffffff', bg2: '#f8fafc', bg3: '#f1f5f9',
  ink: '#0f172a', muted: '#64748b', line: '#e2e8f0',
};

// Dark theme for app screen
const DARK = {
  bg: 'var(--color-surface)',
  bg2: 'var(--color-table-header-bg)',
  bg3: 'var(--color-control-bg)',
  ink: 'var(--color-text)',
  muted: 'var(--color-text-muted)',
  line: 'var(--color-border)',
};

const RTC = createContext(DARK);

// ── Settings persistence (browser-local, applies to every period) ────────────
const HIDDEN_CATS_KEY = 'payrollSummary.hiddenCategories';
const HIDDEN_EMPLOYEES_KEY = 'payrollSummary.hiddenEmployees';
const SHOW_BREAKDOWN_KEY = 'payrollSummary.showBreakdown';
const MANUAL_ROWS_KEY = 'payrollSummary.manualRows'; // { [rangeKey]: [row, ...] }

function loadSet(key) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}
function saveSet(key, set) {
  try { localStorage.setItem(key, JSON.stringify([...set])); } catch { /* noop */ }
}
function loadManualRows() {
  try {
    const raw = localStorage.getItem(MANUAL_ROWS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch { return {}; }
}
function saveManualRows(byRange) {
  try { localStorage.setItem(MANUAL_ROWS_KEY, JSON.stringify(byRange)); } catch { /* noop */ }
}
function loadBool(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : raw === '1';
  } catch { return fallback; }
}
function saveBool(key, value) {
  try { localStorage.setItem(key, value ? '1' : '0'); } catch { /* noop */ }
}

// ── Report sub-components (theme via RTC context) ────────────────────────────

function KpiCard({ icon, label, value, sub, color }) {
  const T = useContext(RTC);
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: T.line, background: T.bg2 }}>
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: T.muted }}>
        {icon}{label}
      </div>
      <div className="mt-1.5 text-[26px] font-bold leading-none tabular-nums" style={{ color: color || T.ink }}>{value}</div>
      {sub && <div className="mt-1.5 text-xs" style={{ color: T.muted }}>{sub}</div>}
    </div>
  );
}

function BarRow({ label, value, max, color, right }) {
  const T = useContext(RTC);
  const w = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-40 shrink-0 text-sm truncate" style={{ color: T.ink }}>{label}</div>
      <div className="flex-1 h-6 rounded-md overflow-hidden" style={{ background: T.bg3 }}>
        <div className="h-6 rounded-md flex items-center justify-end pr-2"
          style={{ width: `${w}%`, background: color, minWidth: value > 0 ? 40 : 0 }} />
      </div>
      <div className="w-28 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color: T.ink }}>{right}</div>
    </div>
  );
}

function Section({ title, hint, children }) {
  const T = useContext(RTC);
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <div className="h-4 w-1 rounded" style={{ background: BRAND }} />
        <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: T.ink }}>{title}</h3>
        {hint && <span className="text-xs" style={{ color: T.muted }}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

// ── Detailed loading progress panel ─────────────────────────────────────────

function PayrollProgress({ status, errors = {} }) {
  // Скрытые настройкой категории не считаются вовсе, поэтому и в знаменателе
  // их быть не должно: иначе «3 из 4» никогда не станет «4 из 4».
  const counted = CATS.filter((c) => status[c.key] !== 'skipped');
  const done = counted.filter((c) => status[c.key] === 'done' || status[c.key] === 'error').length;
  const total = counted.length;
  const barPct = total > 0 ? (done / total) * 100 : 0;

  return (
    <div className="app-card p-8 space-y-6">
      <div className="flex items-center gap-4">
        <div className="w-12 h-12 rounded-full flex items-center justify-center shrink-0"
          style={{ background: 'var(--color-primary-muted)' }}>
          <RefreshCw size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-base font-semibold text-[color:var(--color-text)]">Рассчитываю фонд оплаты труда…</div>
          <div className="text-sm text-[color:var(--color-text-muted)] mt-0.5">{done} из {total} категорий готово</div>
        </div>
        <div className="text-3xl font-extrabold tabular-nums shrink-0" style={{ color: 'var(--color-primary)' }}>
          {Math.round(barPct)}%
        </div>
      </div>

      {/* Animated bar */}
      <div className="h-2.5 rounded-full overflow-hidden" style={{ background: 'var(--color-control-bg)' }}>
        <div style={{
          height: '100%',
          width: `${barPct}%`,
          borderRadius: '9999px',
          background: 'var(--color-primary)',
          boxShadow: 'none',
          transition: 'width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
        }} />
      </div>

      {/* Шаги расчёта. Были четыре карточки, каждая со своей рамкой и
          заливкой всего поля: готовая категория весила столько же, сколько
          упавшая, хотя действия не требует. Теперь одна решётка, а состояние
          несёт общий прибор — тот же, что на остальных страницах. */}
      <div className="fui-lattice">
        {CATS.map((cat) => {
          const st = status[cat.key] || 'idle';
          const Icon = cat.icon;
          const tone = { loading: 'processing', done: 'success', error: 'error' }[st] || 'paused';
          // Голое «Ошибка» ничего не даёт: причина уже есть, её надо показать
          // здесь же, а не заставлять ждать таблицу.
          const reason = st === 'error' ? errors[cat.key] : '';
          const text = { loading: 'Загружаю', done: 'Готово', error: 'Ошибка', skipped: 'Скрыта' }[st] || 'Ожидание';
          return (
            <div key={cat.key} className="fui-cellstat" title={reason || undefined}>
              <span className="fui-cellstat__k">
                <Icon size={12} className="mr-1.5 inline-block align-[-1px]" style={{ color: cat.color }} />
                {cat.title}
                {reason && (
                  <span className="block mt-0.5 text-[11px] font-normal leading-snug break-words" style={{ color: 'var(--color-danger, #dc2626)' }}>
                    {reason}
                  </span>
                )}
              </span>
              <span className={`fui-status fui-status--always fui-status--${tone}`}>
                <span className="fui-status__t">{text}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Settings panel (screen-only chrome, not part of the PNG) ────────────────

function SettingsPanel({
  allEmployeeNames, hiddenCats, hiddenEmployees, showBreakdown,
  onToggleCat, onToggleEmployee, onShowAllEmployees, onSetShowBreakdown, onClose,
}) {
  const [empQuery, setEmpQuery] = useState('');
  const filteredNames = allEmployeeNames.filter((n) => n.toLowerCase().includes(empQuery.toLowerCase()));

  return (
    <div className="app-card p-5 space-y-5">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold flex items-center gap-2">
          <SlidersHorizontal size={15} className="text-[color:var(--color-primary)]" />
          Настройка отчёта
        </div>
        <button className="icon-button icon-button--ghost" onClick={onClose} aria-label="Закрыть"><X size={16} /></button>
      </div>

      {/* Categories */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-2">Должности / категории</div>
        <div className="flex flex-wrap gap-2">
          {CATS.map((c) => {
            const isHidden = hiddenCats.has(c.key);
            return (
              <button key={c.key} type="button" onClick={() => onToggleCat(c.key)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  isHidden
                    ? 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-bg-secondary)]'
                    : 'border-[color:var(--color-primary)] text-[color:var(--color-primary)] bg-[color:var(--color-primary-muted)]'
                }`}>
                {isHidden ? <X size={12} /> : <Check size={12} />}
                {c.title}
              </button>
            );
          })}
        </div>
      </div>

      {/* Detail level */}
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-2">Детализация таблицы</div>
        <div className="flex gap-2">
          <button type="button" onClick={() => onSetShowBreakdown(true)}
            className={`ui-chip ${showBreakdown? 'is-active' : ''}`}>
            Подробно (+ авансы)
          </button>
          <button type="button" onClick={() => onSetShowBreakdown(false)}
            className={`ui-chip ${!showBreakdown? 'is-active' : ''}`}>
            Кратко (оклад, KPI, премии, штрафы)
          </button>
        </div>
        <div className="text-[11px] text-[color:var(--color-muted-foreground)] mt-1.5">В обоих режимах видна структура зарплаты — «Кратко» просто скрывает авансы, если отчёт кому-то показываете.</div>
      </div>

      {/* Employees */}
      {allEmployeeNames.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="text-xs font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)]">Сотрудники ({allEmployeeNames.length - hiddenEmployees.size} из {allEmployeeNames.length})</div>
            <button className="text-xs text-[color:var(--color-primary)] hover:underline" onClick={onShowAllEmployees}>Показать всех</button>
          </div>
          <input className="input text-sm w-full mb-2" placeholder="Поиск по имени…" value={empQuery} onChange={(e) => setEmpQuery(e.target.value)} />
          <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto">
            {filteredNames.map((name) => {
              const isHidden = hiddenEmployees.has(name);
              return (
                <button key={name} type="button" onClick={() => onToggleEmployee(name)}
                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    isHidden
                      ? 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-bg-secondary)] line-through'
                      : 'border-[color:var(--color-border)] text-[color:var(--color-text)] bg-[color:var(--color-surface)]'
                  }`}>
                  {name}
                </button>
              );
            })}
            {filteredNames.length === 0 && <span className="text-xs text-[color:var(--color-muted-foreground)]">Никого не найдено</span>}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Inline "add employee" row, rendered directly inside a category's tbody ──

function AddRowForm({ visibleCols, onSubmit, onCancel }) {
  const [form, setForm] = useState({ name: '', oklad: '', commission: '', bonuses: '', penalties: '', advances: '' });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  function submit() {
    if (!form.name.trim()) return;
    onSubmit({
      name: form.name.trim(),
      oklad: Number(form.oklad) || 0,
      commission: Number(form.commission) || 0,
      bonuses: Number(form.bonuses) || 0,
      penalties: Number(form.penalties) || 0,
      advances: Number(form.advances) || 0,
    });
  }

  return (
    <tr style={{ background: 'var(--color-primary-muted)' }}>
      <td className="px-3 py-1.5">
        <input autoFocus className="input text-xs w-full" placeholder="Имя сотрудника" value={form.name} onChange={set('name')}
          onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onCancel(); }} />
      </td>
      {visibleCols.map((col) => (
        col.key === 'gross' || col.key === 'to_pay' ? (
          <td key={col.key} className="px-3 py-1.5" />
        ) : (
          <td key={col.key} className="px-3 py-1.5">
            <input type="number" className="input text-xs w-full text-right" placeholder="0" value={form[col.key]} onChange={set(col.key)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') onCancel(); }} />
          </td>
        )
      ))}
      <td className="px-2 py-1.5 text-right whitespace-nowrap">
        <button className="icon-button icon-button--ghost" onClick={submit} title="Добавить"><Check size={14} style={{ color: 'var(--color-success)' }} /></button>
        <button className="icon-button icon-button--ghost" onClick={onCancel} title="Отмена"><X size={14} /></button>
      </td>
    </tr>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function PayrollSummary() {
  const { toast } = useToast();
  const initialRange = thisMonthRange();
  const [dateFrom, setDateFrom] = useState(initialRange.from);
  const [dateTo, setDateTo] = useState(initialRange.to);
  const [activePreset, setActivePreset] = useState('this-month');
  const [data, setData] = useState(null);
  const [started, setStarted] = useState(false);
  const [exportKind, setExportKind] = useState(null); // 'png' | 'pdf' | 'xlsx' | null
  const [exporting, setExporting] = useState(false);
  const [catStatus, setCatStatus] = useState({});
  const [catErrors, setCatErrors] = useState({});
  const [generatedAt, setGeneratedAt] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [hiddenCats, setHiddenCats] = useState(() => loadSet(HIDDEN_CATS_KEY));
  const [hiddenEmployees, setHiddenEmployees] = useState(() => loadSet(HIDDEN_EMPLOYEES_KEY));
  const [showBreakdown, setShowBreakdown] = useState(() => loadBool(SHOW_BREAKDOWN_KEY, true));
  const [manualByRange, setManualByRange] = useState(loadManualRows);
  const [addingToCategory, setAddingToCategory] = useState(null);
  const reportRef = useRef(null);

  const rangeKey = `${dateFrom}_${dateTo}`;
  const periodLabel = `${fmtDateRu(dateFrom)} – ${fmtDateRu(dateTo)}`;
  // «Идёт расчёт» — это просто «хоть одна категория в работе». Отдельным
  // флагом это было дважды: догрузка раскрытой категории его бы не выставила.
  const loading = CATS.some((c) => catStatus[c.key] === 'loading');

  // T drives the on-screen theme: dark normally, light during PNG export
  const T = exporting ? LIGHT : DARK;

  // Каждая загрузка получает номер. Переключение периода запускает новую, но
  // старая продолжает висеть на сети ещё десятки секунд — и без этой проверки
  // её ответ приходит последним и затирает свежие цифры чужого периода.
  //
  // Номера мало: брошенные запросы всё равно доходят до Firebird и занимают
  // сервер. Проверено — расчёт по салонам за один месяц после переключения с
  // «года» шёл 65 секунд вместо девяти, потому что двенадцать никому не нужных
  // месяцев доедали очередь. Поэтому загрузка ещё и отменяется по-настоящему.
  const loadGen = useRef(0);
  const loadAbort = useRef(null);

  // Скрытая настройкой категория не должна считаться. Читаем набор через ref,
  // а не через зависимость useCallback: иначе галка в настройках меняла бы
  // саму функцию load, а эффект ниже перезапускал бы из-за этого весь расчёт.
  const hiddenCatsRef = useRef(hiddenCats);
  hiddenCatsRef.current = hiddenCats;

  // fresh — новый расчёт: отменяет предыдущий и очищает отчёт.
  // Иначе догружаем только то, что сейчас раскрыли в настройках, не трогая
  // уже посчитанное.
  const fetchCats = useCallback(async (keys, { fresh }) => {
    let gen, signal;
    if (fresh) {
      gen = ++loadGen.current;
      loadAbort.current?.abort();
      const ac = new AbortController();
      loadAbort.current = ac;
      signal = ac.signal;
      setCatErrors({});
      setData(keys.length ? null : {});
      setCatStatus(Object.fromEntries(CATS.map((c) => [c.key, keys.includes(c.key) ? 'loading' : 'skipped'])));
    } else {
      if (!keys.length) return;
      gen = loadGen.current;
      signal = loadAbort.current?.signal;
      setCatStatus((prev) => ({ ...prev, ...Object.fromEntries(keys.map((k) => [k, 'loading'])) }));
    }
    const mine = () => loadGen.current === gen;
    // Категории показываем по мере готовности, а не все разом в конце.
    // Мастера считаются секунды, администраторы за год — минуту: ждать
    // ради них пустой экран незачем, а «идёт расчёт» видно по панели
    // прогресса и по пометке у ещё не доехавших категорий.
    await Promise.all(CATS.filter((c) => keys.includes(c.key)).map(async (c) => {
      const result = await c.load(dateFrom, dateTo, signal)
        .then((rows) => ({ rows }))
        .catch((e) => ({ rows: [], error: e?.response?.data?.detail || e.message || 'ошибка' }));
      if (!mine()) return;
      setCatStatus((prev) => ({ ...prev, [c.key]: result.error ? 'error' : 'done' }));
      if (result.error) setCatErrors((prev) => ({ ...prev, [c.key]: result.error }));
      setData((prev) => ({ ...(prev || {}), [c.key]: result }));
      setGeneratedAt(new Date().toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
    }));
  }, [dateFrom, dateTo]);

  const load = useCallback(
    () => fetchCats(CATS.filter((c) => !hiddenCatsRef.current.has(c.key)).map((c) => c.key), { fresh: true }),
    [fetchCats],
  );

  // ФОТ по салонам грузится отдельно и по кнопке — он дороже всего отчёта.
  // Помесячные результаты копим в ref, чтобы «докат» после сбоя не считал
  // заново уже посчитанные месяцы.
  const [salons, setSalons] = useState(null);
  const [salonsState, setSalonsState] = useState({ status: 'idle', done: 0, total: 0, failed: [], error: '' });
  const salonsGen = useRef(0);
  const salonsAbort = useRef(null);
  const salonMonthsRef = useRef({}); // period -> rows[]

  useEffect(() => {
    salonsGen.current += 1;
    salonsAbort.current?.abort();
    salonMonthsRef.current = {};
    setSalons(null);
    setSalonsState({ status: 'idle', done: 0, total: 0, failed: [], error: '' });
  }, [dateFrom, dateTo]);

  // Считает переданные месяцы, по одному не роняя остальные. Один месяц —
  // это отдельный тяжёлый запрос к Firebird; под нагрузкой он изредка
  // выходит за серверный таймаут и отвечает 504. Раньше такой единичный сбой
  // ронял весь расчёт (Promise.all отклонялся) и выбрасывал 11 успешных
  // месяцев. Теперь ошибка месяца лишь помечает его к докату, а посчитанное
  // сразу показывается.
  const fetchSalonMonths = useCallback(async (periods, gen, signal) => {
    const failed = [];
    await mapLimit(periods, MONTH_CONCURRENCY, async (p) => {
      try {
        const rows = await loadSalonsMonth(p, signal);
        if (salonsGen.current !== gen) return;
        salonMonthsRef.current[p] = rows;
      } catch (e) {
        if (salonsGen.current !== gen) return;
        if (e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError') return; // сменили период — молча
        failed.push(p);
      } finally {
        if (salonsGen.current === gen) {
          setSalonsState((s) => ({ ...s, done: Object.keys(salonMonthsRef.current).length }));
        }
      }
    });
    return failed;
  }, []);

  const loadSalons = useCallback(async () => {
    const gen = ++salonsGen.current;
    salonsAbort.current?.abort();
    const ac = new AbortController();
    salonsAbort.current = ac;
    // Считаем только ещё не посчитанные месяцы (докат после сбоя не трогает
    // готовые), но упавшие пробуем заново.
    const all = monthsInRange(dateFrom, dateTo);
    const todo = all.filter((p) => !salonMonthsRef.current[p]);
    setSalonsState((s) => ({ ...s, status: 'loading', total: all.length, done: all.length - todo.length, failed: [], error: '' }));

    let failed = await fetchSalonMonths(todo, gen, ac.signal);
    if (salonsGen.current !== gen) return;
    // Один автоповтор упавших: контеншн на общем Firebird обычно преходящий.
    if (failed.length) {
      failed = await fetchSalonMonths(failed, gen, ac.signal);
      if (salonsGen.current !== gen) return;
    }

    const gotAny = Object.keys(salonMonthsRef.current).length > 0;
    setSalons(gotAny ? mergeSalonsAcrossMonths(Object.values(salonMonthsRef.current)) : null);
    setSalonsState((s) => ({
      ...s,
      status: failed.length ? (gotAny ? 'partial' : 'error') : 'done',
      failed,
      error: gotAny ? '' : 'сервер не ответил вовремя',
    }));
  }, [dateFrom, dateTo, fetchSalonMonths]);

  // Сам по себе отчёт не считается: расчёт идёт в базу салонов и стоит от
  // нескольких секунд за месяц до нескольких минут за год. Открытие страницы —
  // не повод его запускать; запускает кнопка, дальше смена периода.
  useEffect(() => { if (started) load(); }, [load, started]);

  // Категорию раскрыли в настройках уже после расчёта — досчитываем только её.
  useEffect(() => {
    if (!started || !data) return;
    const missing = CATS
      .filter((c) => !hiddenCats.has(c.key) && !data[c.key] && catStatus[c.key] !== 'loading')
      .map((c) => c.key);
    if (missing.length) fetchCats(missing, { fresh: false });
  }, [started, data, catStatus, hiddenCats, fetchCats]);
  // Уход со страницы тоже отменяет расчёт — иначе он доедет до Firebird уже
  // никому не нужным.
  const abortRefs = useRef([loadAbort, salonsAbort]);
  useEffect(() => {
    const refs = abortRefs.current;
    return () => refs.forEach((r) => r.current?.abort());
  }, []);
  useEffect(() => { saveSet(HIDDEN_CATS_KEY, hiddenCats); }, [hiddenCats]);
  useEffect(() => { saveSet(HIDDEN_EMPLOYEES_KEY, hiddenEmployees); }, [hiddenEmployees]);
  useEffect(() => { saveBool(SHOW_BREAKDOWN_KEY, showBreakdown); }, [showBreakdown]);
  useEffect(() => { saveManualRows(manualByRange); }, [manualByRange]);

  const manualRows = manualByRange[rangeKey] || [];

  function applyPreset(p) {
    setActivePreset(p.key);
    const { from, to } = p.range();
    setDateFrom(from); setDateTo(to);
    setStarted(true);
  }
  function applyCustomRange() {
    setActivePreset('custom');
    // Если даты не менялись, эффект не сработает — зовём расчёт напрямую.
    if (started) load(); else setStarted(true);
  }
  function refresh() {
    if (started) load(); else setStarted(true);
  }
  function addManualRow(category, row) {
    const withId = { ...row, id: `manual_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`, category };
    setManualByRange((prev) => ({ ...prev, [rangeKey]: [...(prev[rangeKey] || []), withId] }));
    setAddingToCategory(null);
  }
  function removeManualRow(id) {
    setManualByRange((prev) => ({ ...prev, [rangeKey]: (prev[rangeKey] || []).filter((r) => r.id !== id) }));
  }
  function toggleCat(key) {
    setHiddenCats((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  }
  function toggleEmployee(name) {
    setHiddenEmployees((prev) => { const next = new Set(prev); next.has(name) ? next.delete(name) : next.add(name); return next; });
  }

  // Derived: raw category rows + manual rows merged in, before visibility filtering
  const catsWithManual = useMemo(() => CATS.map((c) => ({
    ...c,
    rows: [...(data?.[c.key]?.rows || []), ...manualRows.filter((r) => r.category === c.key).map((r) => ({
      ...r,
      gross: r.oklad + r.commission + r.bonuses,
      to_pay: r.oklad + r.commission + r.bonuses - r.penalties - r.advances,
    }))],
    error: data?.[c.key]?.error,
  })), [data, manualRows]);

  const allEmployeeNames = useMemo(() => {
    const names = new Set();
    catsWithManual.forEach((c) => c.rows.forEach((r) => names.add(r.name)));
    return [...names].sort((a, b) => a.localeCompare(b, 'ru'));
  }, [catsWithManual]);

  // Visible = not-hidden category, not-hidden employee
  const cats = useMemo(() => catsWithManual
    .filter((c) => !hiddenCats.has(c.key))
    .map((c) => {
      const rows = c.rows.filter((r) => !hiddenEmployees.has(r.name));
      return { ...c, rows, totals: sumRows(rows) };
    }), [catsWithManual, hiddenCats, hiddenEmployees]);

  const tagged = cats.flatMap((c) => c.rows.map((r) => ({ ...r, catColor: c.color, catTitle: c.title })));
  const grand = sumRows(tagged);
  const headcount = tagged.length;
  const withholdings = grand.advances + grand.penalties;
  const donut = cats.filter((c) => c.totals.gross > 0).map((c) => ({ name: c.title, value: c.totals.gross, color: c.color }));
  const topEarners = [...tagged].sort((a, b) => b.gross - a.gross).slice(0, 6);
  const maxCat = Math.max(1, ...cats.map((c) => c.totals.gross));
  const maxTop = Math.max(1, ...topEarners.map((r) => r.gross));
  const comp = [
    { label: 'Оклад', value: grand.oklad, color: 'var(--color-primary)' },
    { label: 'Комиссия / KPI', value: grand.commission, color: 'var(--color-success)' },
    { label: 'Премии', value: grand.bonuses, color: 'var(--color-warning)' },
  ].filter((s) => s.value > 0);
  // "Кратко" = salary breakdown (oklad/KPI/premии/штрафы-if-any) minus авансы,
  // not just two totals — advances is the one column considered sensitive
  // enough to gate behind "Подробно".
  // ── Метрики для собственника ───────────────────────────────────────────────
  // Абсолютный ФОТ за произвольный период несравним сам с собой: квартал втрое
  // больше месяца просто потому, что месяцев три. Поэтому всё, что ниже,
  // приведено к «в месяц» и «на человека» — эти числа можно сравнивать между
  // периодами и между категориями.
  const monthsCount = useMemo(() => monthsInRange(dateFrom, dateTo).length, [dateFrom, dateTo]);
  const avgPerPerson = headcount ? grand.gross / headcount : 0;
  const avgPerMonth = monthsCount ? grand.gross / monthsCount : 0;
  const avgPerPersonMonth = headcount && monthsCount ? grand.gross / headcount / monthsCount : 0;
  const fixedShare = pct(grand.oklad, grand.gross);
  const variablePart = grand.commission + grand.bonuses;

  const salonMax = Math.max(1, ...(salons || []).map((s) => s.total));
  const salonTotal = (salons || []).reduce((s, x) => s + x.total, 0);
  // «В месяц» по салонам делим на реально посчитанные месяцы, а не на весь
  // диапазон: при частичном результате часть месяцев отсутствует.
  const salonMonths = Math.max(1, monthsCount - (salonsState.status === 'partial' ? salonsState.failed.length : 0));

  const visibleCols = showBreakdown
    ? COLS
    : COLS.filter((c) => c.key !== 'advances' && (c.key !== 'penalties' || grand.penalties > 0));

  const fileBase = `ФОТ_${dateFrom}_${dateTo}`;

  // Снимок отчёта в светлой теме. PNG и PDF рендерят одну и ту же картинку —
  // ту, что видно на экране, со всеми графиками; расходятся только контейнером.
  async function captureReport() {
    setExporting(true);
    setAddingToCategory(null);
    // Два кадра, чтобы React перерисовал светлую тему и убрал открытую форму
    // добавления строки до захвата.
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    try {
      const node = reportRef.current;
      const url = await toPng(node, { backgroundColor: '#ffffff', pixelRatio: 2, cacheBust: true, skipFonts: true });
      return { url, width: node.offsetWidth, height: node.offsetHeight };
    } finally {
      setExporting(false);
    }
  }

  async function downloadPng() {
    if (!reportRef.current || exportKind) return;
    setExportKind('png');
    try {
      const { url } = await captureReport();
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fileBase}.png`;
      a.click();
      toast('PNG сохранён', 'success');
    } catch (e) {
      console.error(e);
      toast('Ошибка генерации PNG', 'error');
    } finally {
      setExportKind(null);
    }
  }

  async function downloadPdf() {
    if (!reportRef.current || exportKind) return;
    setExportKind('pdf');
    try {
      const { url, width, height } = await captureReport();
      const { jsPDF } = await import('jspdf');
      const pdf = new jsPDF({ unit: 'pt', format: 'a4', compress: true });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const imgW = pageW;
      const imgH = (height / width) * pageW; // высота картинки в точках A4
      // Длинный отчёт нарезаем по страницам A4: одна и та же картинка рисуется
      // со сдвигом вверх на страницу — то, что не влезло, показывается на
      // следующей.
      let heightLeft = imgH;
      let position = 0;
      pdf.addImage(url, 'PNG', 0, position, imgW, imgH);
      heightLeft -= pageH;
      while (heightLeft > 0) {
        position -= pageH;
        pdf.addPage();
        pdf.addImage(url, 'PNG', 0, position, imgW, imgH);
        heightLeft -= pageH;
      }
      pdf.save(`${fileBase}.pdf`);
      toast('PDF сохранён', 'success');
    } catch (e) {
      console.error(e);
      toast('Ошибка генерации PDF', 'error');
    } finally {
      setExportKind(null);
    }
  }

  async function downloadXlsx() {
    if (exportKind) return;
    setExportKind('xlsx');
    try {
      const XLSX = await import('xlsx');
      const r0 = (v) => Math.round(Number(v) || 0);
      const wb = XLSX.utils.book_new();

      // Лист 1 — показатели
      const kpi = [
        ['Сводный отчёт по ФОТ'],
        ['Период', periodLabel],
        ['Категории', cats.map((c) => c.title).join(', ') || '—'],
        ['Сформировано', generatedAt || ''],
        [],
        ['ФОТ за период', r0(grand.gross)],
        ['ФОТ в месяц', r0(avgPerMonth)],
        ['Средняя ЗП за период (на чел.)', r0(avgPerPerson)],
        ['Средняя ЗП в месяц (на чел.)', r0(avgPerPersonMonth)],
        ['Постоянная часть (оклады), %', fixedShare],
        ['  оклады', r0(grand.oklad)],
        ['  переменная (комиссия+премии)', r0(variablePart)],
        ['Удержания (авансы+штрафы)', r0(withholdings)],
        ['  авансы', r0(grand.advances)],
        ['  штрафы', r0(grand.penalties)],
        ['Сотрудников', headcount],
        ['Месяцев в периоде', monthsCount],
      ];
      const wsKpi = XLSX.utils.aoa_to_sheet(kpi);
      wsKpi['!cols'] = [{ wch: 36 }, { wch: 18 }];
      XLSX.utils.book_append_sheet(wb, wsKpi, 'Показатели');

      // Лист 2 — по категориям
      const catHead = ['Категория', 'Человек', 'ФОТ за период', 'ФОТ в месяц', 'Средняя ЗП в месяц', 'Доля %'];
      const catRows = cats.map((c) => {
        const n = c.rows.length;
        return [
          c.title, n, r0(c.totals.gross), r0(monthsCount ? c.totals.gross / monthsCount : 0),
          n && monthsCount ? r0(c.totals.gross / n / monthsCount) : 0, pct(c.totals.gross, grand.gross),
        ];
      });
      catRows.push(['ВСЕГО', headcount, r0(grand.gross), r0(avgPerMonth), r0(avgPerPersonMonth), 100]);
      const wsCat = XLSX.utils.aoa_to_sheet([catHead, ...catRows]);
      wsCat['!cols'] = [{ wch: 18 }, { wch: 9 }, { wch: 15 }, { wch: 14 }, { wch: 18 }, { wch: 8 }];
      XLSX.utils.book_append_sheet(wb, wsCat, 'По категориям');

      // Лист 3 — по сотрудникам
      const empHead = ['Категория', 'Сотрудник', ...COLS.map((c) => c.label)];
      const empRows = [empHead];
      cats.forEach((c) => {
        c.rows.forEach((row) => {
          empRows.push([c.title, row.name, ...COLS.map((col) => r0(row[col.key]))]);
        });
        empRows.push(['', `Итого · ${c.title.toLowerCase()}`, ...COLS.map((col) => r0(c.totals[col.key]))]);
      });
      empRows.push(['', `ВСЕГО · ${headcount} чел.`, ...COLS.map((col) => r0(grand[col.key]))]);
      const wsEmp = XLSX.utils.aoa_to_sheet(empRows);
      wsEmp['!cols'] = [{ wch: 16 }, { wch: 26 }, ...COLS.map(() => ({ wch: 13 }))];
      XLSX.utils.book_append_sheet(wb, wsEmp, 'По сотрудникам');

      // Лист 4 — по салонам (если посчитан)
      if (salons && salons.length) {
        const salHead = ['Салон', 'Человек', 'Оклад', 'Комиссия', 'Премии', 'Итого', 'В месяц', 'Доля %'];
        const salRows = salons.map((s) => [
          s.salon_name, s.headcount || 0, r0(s.oklad), r0(s.commission), r0(s.bonuses),
          r0(s.total), r0(s.total / salonMonths), pct(s.total, salonTotal),
        ]);
        salRows.push([
          `ВСЕГО · ${salons.length} салонов`, '',
          r0(salons.reduce((a, s) => a + s.oklad, 0)),
          r0(salons.reduce((a, s) => a + s.commission, 0)),
          r0(salons.reduce((a, s) => a + s.bonuses, 0)),
          r0(salonTotal), r0(salonTotal / salonMonths), 100,
        ]);
        const wsSal = XLSX.utils.aoa_to_sheet([salHead, ...salRows]);
        wsSal['!cols'] = [{ wch: 22 }, { wch: 9 }, { wch: 13 }, { wch: 13 }, { wch: 13 }, { wch: 14 }, { wch: 13 }, { wch: 8 }];
        XLSX.utils.book_append_sheet(wb, wsSal, 'По салонам');
      }

      XLSX.writeFile(wb, `${fileBase}.xlsx`);
      toast('Excel сохранён', 'success');
    } catch (e) {
      console.error(e);
      toast('Ошибка генерации Excel', 'error');
    } finally {
      setExportKind(null);
    }
  }

  return (
    <div className="space-y-5 max-w-[1140px] mx-auto pb-12">
      {/* Top progress bar: shown while refreshing or generating PNG */}
      <TopProgressBar active={!!exportKind || (loading && !!data)} />

      {/* Controls */}
      <div className="ui-reveal flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          {/* Надзаголовок несёт выбранный период — то, от чего зависят все
              числа ниже. Иконка из заголовка убрана: она дублировала уже
              подсвеченный пункт меню и мешала крупному начертанию. */}
          <span className="ui-eyebrow mb-3">Зарплата · {periodLabel}</span>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
            Сводный отчёт по ФОТ
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-2 max-w-[56ch]">
            {CATS.filter((c) => !hiddenCats.has(c.key)).map((c) => c.title.toLowerCase()).join(', ') || 'все категории скрыты'} за период · настраиваемый PNG-отчёт
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          {DATE_PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => applyPreset(p)}
              aria-pressed={activePreset === p.key}
              className={`ui-chip ${activePreset === p.key ? 'is-active' : ''}`}
            >
              {p.label}
            </button>
          ))}
          <label className="block">
            <span className="block text-[10px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">С</span>
            <input type="date" className="input text-xs h-[30px] py-0" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </label>
          <label className="block">
            <span className="block text-[10px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">По</span>
            <input type="date" className="input text-xs h-[30px] py-0" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </label>
          <button
            className={`ui-chip ${activePreset === 'custom' ? 'is-active' : ''}`}
            aria-pressed={activePreset === 'custom'}
            onClick={applyCustomRange}
          >
            Применить период
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={() => setShowSettings((v) => !v)}>
            <SlidersHorizontal size={14} /> Настроить{(hiddenCats.size + hiddenEmployees.size) > 0 ? ` (${hiddenCats.size + hiddenEmployees.size})` : ''}
          </button>
          <button
            className={`btn ${started ? 'btn--secondary' : 'btn--primary'} flex items-center gap-1.5`}
            onClick={refresh}
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {started ? 'Обновить' : 'Сформировать'}
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={downloadXlsx} disabled={!!exportKind || loading || !data}>
            <FileSpreadsheet size={15} /> {exportKind === 'xlsx' ? 'Готовлю…' : 'Excel'}
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={downloadPdf} disabled={!!exportKind || loading || !data}>
            <FileText size={15} /> {exportKind === 'pdf' ? 'Готовлю…' : 'PDF'}
          </button>
          <button className="btn btn--primary flex items-center gap-1.5" onClick={downloadPng} disabled={!!exportKind || loading || !data}>
            <ImageIcon size={15} /> {exportKind === 'png' ? 'Готовлю…' : 'PNG'}
          </button>
        </div>
      </div>
      <div className="text-[11px] text-[color:var(--color-muted-foreground)] -mt-2">
        Оклады и планы месячные — период разбивается по затронутым календарным месяцам; если границы периода приходятся на середину месяца, оклад за этот месяц всё равно учитывается целиком.
      </div>

      {showSettings && (
        <SettingsPanel
          allEmployeeNames={allEmployeeNames}
          hiddenCats={hiddenCats}
          hiddenEmployees={hiddenEmployees}
          showBreakdown={showBreakdown}
          onToggleCat={toggleCat}
          onToggleEmployee={toggleEmployee}
          onShowAllEmployees={() => setHiddenEmployees(new Set())}
          onSetShowBreakdown={setShowBreakdown}
          onClose={() => setShowSettings(false)}
        />
      )}

      {/* До первого запуска — ничего не считаем и честно говорим почему */}
      {!started && (
        <div className="app-card p-8 flex flex-wrap items-center gap-6">
          <div className="w-12 h-12 rounded-full flex items-center justify-center shrink-0"
            style={{ background: 'var(--color-primary-muted)' }}>
            <Calculator size={20} style={{ color: 'var(--color-primary)' }} />
          </div>
          <div className="flex-1 min-w-[280px]">
            <div className="text-base font-semibold text-[color:var(--color-text)]">Отчёт ещё не посчитан</div>
            <p className="text-sm text-[color:var(--color-text-muted)] mt-1 max-w-[62ch]">
              Расчёт идёт в базу салонов и стоит от полуминуты за месяц до нескольких минут за год,
              поэтому он запускается кнопкой, а не сам при открытии страницы. Считаются только
              категории, включённые в настройках.
            </p>
            <div className="text-[11px] text-[color:var(--color-muted-foreground)] mt-2">
              Период: {periodLabel} · категорий к расчёту: {CATS.length - hiddenCats.size} из {CATS.length}
              {hiddenCats.size > 0 && ` (скрыты: ${CATS.filter((c) => hiddenCats.has(c.key)).map((c) => c.title.toLowerCase()).join(', ')})`}
            </div>
          </div>
          <div className="shrink-0">
            <button className="btn btn--primary flex items-center gap-1.5" onClick={() => setStarted(true)}>
              <Calculator size={15} /> Сформировать отчёт
            </button>
          </div>
        </div>
      )}

      {/* Панель прогресса держим всё время расчёта, а не только до первой
          готовой категории: отчёт ниже уже показывает то, что доехало. */}
      {loading && <PayrollProgress status={catStatus} errors={catErrors} />}

      {/* Report (shown once data is available, even while refreshing) */}
      {data && (
        <div className="rounded-2xl">
          <ScaledReport>
          <RTC.Provider value={T}>
            {/* ════ Captured report (fixed 1080px) ════ */}
            <div ref={reportRef} style={{ width: 1080, background: T.bg, color: T.ink }} className="fot-report overflow-hidden">
              {/* Reset the app's global dark table styling inside the report */}
              <style>{`.fot-report table,.fot-report thead,.fot-report tbody,.fot-report tfoot,.fot-report tr,.fot-report td,.fot-report th{background:transparent;border:0;color:inherit;box-shadow:none;}`}</style>

              {/* Header — flat brand color (was a purple gradient) */}
              <div className="px-10 pt-9 pb-8 text-white flex items-end justify-between"
                style={{ background: 'var(--color-primary)' }}>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">Сводный отчёт</div>
                  <div className="mt-1 text-[30px] font-extrabold leading-tight">Фонд оплаты труда</div>
                  <div className="mt-1 text-sm opacity-90">{periodLabel} · {cats.map((c) => c.title.toLowerCase()).join(', ') || 'нет активных категорий'}</div>
                </div>
                <div className="text-right">
                  <div className="text-[11px] font-semibold uppercase tracking-wide opacity-80">Итого начислено</div>
                  <div className="text-[40px] font-extrabold leading-none tabular-nums">{fmtMoney(grand.gross)}</div>
                  {loading && (
                    <div className="mt-1 text-[11px] font-semibold uppercase tracking-wide opacity-80">
                      расчёт не закончен · готово {CATS.filter((c) => catStatus[c.key] === 'done' || catStatus[c.key] === 'error').length} из {CATS.filter((c) => catStatus[c.key] !== 'skipped').length} категорий
                    </div>
                  )}
                </div>
              </div>

              <div className="px-10 py-8 space-y-8">
                {/* KPI cards */}
                <div className="grid grid-cols-3 gap-4">
                  <KpiCard icon={<Wallet size={13} />} label="ФОТ за период" value={fmtMoney(grand.gross)} sub={`средняя ${fmtMoney(headcount ? grand.gross / headcount : 0)} / чел.`} color={BRAND} />
                  <KpiCard icon={<UserRound size={13} />} label="Сотрудников" value={String(headcount)} sub={cats.map((c) => `${c.title.slice(0, 4).toLowerCase()}. ${c.rows.length}`).join(' · ') || '—'} />
                  <KpiCard icon={<TrendingDown size={13} />} label="Удержания" value={fmtMoney(withholdings)} sub={`авансы ${fmtMoney(grand.advances)} · штрафы ${fmtMoney(grand.penalties)}`} color={DANGER} />
                </div>

                {/* Метрики, приведённые к месяцу и человеку */}
                <Section
                  title="Ключевые метрики"
                  hint={monthsCount > 1 ? `период — ${monthsCount} мес., всё приведено к месяцу` : 'период — один месяц'}
                >
                  <div className="grid grid-cols-4 gap-4">
                    <KpiCard icon={<CalendarRange size={13} />} label="ФОТ в месяц"
                      value={fmtMoney(avgPerMonth)}
                      sub={monthsCount > 1 ? `в среднем за ${monthsCount} мес.` : 'за выбранный месяц'}
                      color={BRAND} />
                    <KpiCard icon={<UserRound size={13} />} label="Средняя ЗП за период"
                      value={fmtMoney(avgPerPerson)}
                      sub={`начислено на человека · ${headcount} чел.`} />
                    <KpiCard icon={<UserRound size={13} />} label="Средняя ЗП в месяц"
                      value={fmtMoney(avgPerPersonMonth)}
                      sub="на человека, в среднем за месяц" />
                    <KpiCard icon={<Percent size={13} />} label="Постоянная часть"
                      value={`${fixedShare}%`}
                      sub={`оклады ${fmtMoney(grand.oklad)} · переменная ${fmtMoney(variablePart)}`}
                      color={fixedShare >= 70 ? 'var(--color-warning)' : 'var(--color-success)'} />
                  </div>

                  {/* Те же средние по категориям: видно, какая из них дорожает */}
                  {cats.length > 0 && (
                    <div className="mt-4 rounded-xl border overflow-hidden" style={{ borderColor: T.line }}>
                      <table className="w-full text-[13px]">
                        <thead>
                          <tr style={{ background: T.bg2, color: T.muted }} className="text-[10px] uppercase tracking-wide">
                            <th className="text-left font-semibold px-3 py-2">Категория</th>
                            <th className="text-right font-semibold px-3 py-2">Человек</th>
                            <th className="text-right font-semibold px-3 py-2">ФОТ за период</th>
                            <th className="text-right font-semibold px-3 py-2">ФОТ в месяц</th>
                            <th className="text-right font-semibold px-3 py-2">Средняя ЗП в месяц</th>
                            <th className="text-right font-semibold px-3 py-2">Доля</th>
                          </tr>
                        </thead>
                        <tbody>
                          {cats.map((c) => {
                            const n = c.rows.length;
                            return (
                              <tr key={c.key} style={{ borderTop: `1px solid ${T.line}` }}>
                                <td className="px-3 py-1.5 font-medium" style={{ color: c.color }}>{c.title}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{n || '—'}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{fmtMoney(c.totals.gross)}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{fmtMoney(monthsCount ? c.totals.gross / monthsCount : 0)}</td>
                                <td className="px-3 py-1.5 text-right tabular-nums font-semibold" style={{ color: T.ink }}>
                                  {n && monthsCount ? fmtMoney(c.totals.gross / n / monthsCount) : '—'}
                                </td>
                                <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.muted }}>{pct(c.totals.gross, grand.gross)}%</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Section>

                {/* Charts row */}
                <div className="grid grid-cols-2 gap-6">
                  <Section title="Доля категорий в ФОТ">
                    <div className="flex items-center gap-5">
                      <div className="relative" style={{ width: 200, height: 200 }}>
                        {donut.length > 0 ? (
                          <PieChart width={200} height={200}>
                            <Pie data={donut} dataKey="value" innerRadius={66} outerRadius={96} paddingAngle={donut.length > 1 ? 2 : 0} stroke="none" startAngle={90} endAngle={-270} isAnimationActive={false}>
                              {donut.map((d) => <Cell key={d.name} fill={d.color} />)}
                            </Pie>
                          </PieChart>
                        ) : <div className="w-full h-full rounded-full" style={{ background: T.bg3 }} />}
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <div className="text-[10px] uppercase tracking-wide" style={{ color: T.muted }}>ФОТ</div>
                          <div className="text-base font-bold tabular-nums" style={{ color: T.ink }}>{fmtMoney(grand.gross)}</div>
                        </div>
                      </div>
                      <div className="flex-1 space-y-2.5">
                        {cats.map((c) => (
                          <div key={c.key} className="flex items-center gap-2.5">
                            <span className="h-3 w-3 rounded-sm shrink-0" style={{ background: c.color }} />
                            <span className="text-sm flex-1" style={{ color: T.ink }}>{c.title}</span>
                            <span className="text-sm font-semibold tabular-nums" style={{ color: T.ink }}>{fmtMoney(c.totals.gross)}</span>
                            <span className="w-10 text-right text-xs tabular-nums" style={{ color: T.muted }}>{pct(c.totals.gross, grand.gross)}%</span>
                          </div>
                        ))}
                        {cats.length === 0 && <div className="text-sm" style={{ color: T.muted }}>Все категории скрыты настройкой</div>}
                      </div>
                    </div>
                  </Section>

                  <Section title="ФОТ по категориям">
                    <div className="space-y-3 pt-1">
                      {cats.map((c) => (
                        <BarRow key={c.key} label={c.title} value={c.totals.gross} max={maxCat} color={c.color} right={fmtMoney(c.totals.gross)} />
                      ))}
                    </div>
                  </Section>
                </div>

                {/* Composition */}
                <Section title="Структура начислений" hint={`всего ${fmtMoney(grand.gross)}`}>
                  <div className="h-7 w-full rounded-lg overflow-hidden flex" style={{ background: T.bg3 }}>
                    {comp.map((s) => (
                      <div key={s.label} className="h-7 flex items-center justify-center text-[11px] font-semibold text-white"
                        style={{ width: `${pct(s.value, grand.gross)}%`, background: s.color }}>
                        {pct(s.value, grand.gross) >= 8 ? `${pct(s.value, grand.gross)}%` : ''}
                      </div>
                    ))}
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1">
                    {comp.map((s) => (
                      <div key={s.label} className="flex items-center gap-2 text-sm">
                        <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />
                        <span style={{ color: T.muted }}>{s.label}</span>
                        <span className="font-semibold tabular-nums" style={{ color: T.ink }}>{fmtMoney(s.value)}</span>
                      </div>
                    ))}
                    <div className="flex items-center gap-2 text-sm ml-auto">
                      <span style={{ color: T.muted }}>удержания</span>
                      <span className="font-semibold tabular-nums" style={{ color: DANGER }}>{fmtMoney(withholdings)}</span>
                    </div>
                  </div>
                </Section>

                {/* ФОТ по салонам — грузится по кнопке */}
                {(!exporting || salons) && (
                  <Section title="ФОТ по салонам" hint="администраторы · оклад и комиссия разнесены по месту продажи">
                    {salonsState.status === 'idle' && !exporting && (
                      <div className="flex items-center gap-3">
                        <button className="btn btn--secondary flex items-center gap-1.5" onClick={loadSalons}>
                          <Building2 size={14} /> Посчитать по салонам
                        </button>
                        <span className="text-xs" style={{ color: T.muted }}>
                          {monthsCount > 1
                            ? `${monthsCount} мес. — расчёт займёт около ${Math.round((monthsCount * 9) / MONTH_CONCURRENCY)} с`
                            : 'расчёт займёт около 9 секунд'}
                        </span>
                      </div>
                    )}
                    {salonsState.status === 'loading' && (
                      <div className="flex items-center gap-3 text-sm" style={{ color: T.muted }}>
                        <RefreshCw size={14} className="animate-spin" />
                        Считаю по салонам… {salonsState.done} из {salonsState.total} мес.
                      </div>
                    )}
                    {salonsState.status === 'error' && (
                      <div className="flex items-center gap-3">
                        <span className="text-sm" style={{ color: DANGER }}>Не удалось посчитать: {salonsState.error}. Firebird салонов бывает перегружен — попробуйте ещё раз.</span>
                        {!exporting && <button className="btn btn--secondary" onClick={loadSalons}>Повторить</button>}
                      </div>
                    )}
                    {/* Часть месяцев не посчиталась — показываем, что есть, и
                        предлагаем докатить только их, не пересчитывая готовые. */}
                    {salonsState.status === 'partial' && (
                      <div className="flex flex-wrap items-center gap-3 mb-3 rounded-lg px-3 py-2"
                        style={{ background: 'var(--color-warning-muted, rgba(234,179,8,0.12))' }}>
                        <span className="text-sm" style={{ color: 'var(--color-warning)' }}>
                          Не досчитались {salonsState.failed.length} мес. ({salonsState.failed.join(', ')}) — Firebird салонов был перегружен. Ниже — по {salonsState.total - salonsState.failed.length} из {salonsState.total} мес.
                        </span>
                        {!exporting && (
                          <button className="btn btn--secondary btn--sm" onClick={loadSalons}>
                            Досчитать {salonsState.failed.length} мес.
                          </button>
                        )}
                      </div>
                    )}
                    {salons && salons.length > 0 && (
                      <>
                        <div className="space-y-2.5 pt-1">
                          {salons.map((s) => (
                            <BarRow key={s.salon_id} label={s.salon_name} value={s.total} max={salonMax} color={BRAND} right={fmtMoney(s.total)} />
                          ))}
                        </div>
                        <div className="mt-4 rounded-xl border overflow-hidden" style={{ borderColor: T.line }}>
                          <table className="w-full text-[13px]">
                            <thead>
                              <tr style={{ background: T.bg2, color: T.muted }} className="text-[10px] uppercase tracking-wide">
                                <th className="text-left font-semibold px-3 py-2">Салон</th>
                                <th className="text-right font-semibold px-3 py-2">Человек</th>
                                <th className="text-right font-semibold px-3 py-2">Оклад</th>
                                <th className="text-right font-semibold px-3 py-2">Комиссия</th>
                                <th className="text-right font-semibold px-3 py-2">Премии</th>
                                <th className="text-right font-semibold px-3 py-2">Итого</th>
                                <th className="text-right font-semibold px-3 py-2">В месяц</th>
                                <th className="text-right font-semibold px-3 py-2">Доля</th>
                              </tr>
                            </thead>
                            <tbody>
                              {salons.map((s) => (
                                <tr key={s.salon_id} style={{ borderTop: `1px solid ${T.line}` }}>
                                  <td className="px-3 py-1.5 font-medium" style={{ color: T.ink }}>{s.salon_name}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{s.headcount || '—'}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{s.oklad ? fmtMoney(s.oklad) : '—'}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{s.commission ? fmtMoney(s.commission) : '—'}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{s.bonuses ? fmtMoney(s.bonuses) : '—'}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums font-semibold" style={{ color: BRAND }}>{fmtMoney(s.total)}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.ink }}>{fmtMoney(s.total / salonMonths)}</td>
                                  <td className="px-3 py-1.5 text-right tabular-nums" style={{ color: T.muted }}>{pct(s.total, salonTotal)}%</td>
                                </tr>
                              ))}
                            </tbody>
                            <tfoot>
                              <tr style={{ borderTop: `2px solid ${T.ink}`, background: T.bg2 }}>
                                <td className="px-3 py-2 font-extrabold" style={{ color: T.ink }}>ВСЕГО · {salons.length} салонов</td>
                                <td />
                                <td className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: T.ink }}>{fmtMoney(salons.reduce((a, s) => a + s.oklad, 0))}</td>
                                <td className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: T.ink }}>{fmtMoney(salons.reduce((a, s) => a + s.commission, 0))}</td>
                                <td className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: T.ink }}>{fmtMoney(salons.reduce((a, s) => a + s.bonuses, 0))}</td>
                                <td className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: BRAND }}>{fmtMoney(salonTotal)}</td>
                                <td className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: T.ink }}>{fmtMoney(salonTotal / salonMonths)}</td>
                                <td />
                              </tr>
                            </tfoot>
                          </table>
                        </div>
                      </>
                    )}
                    {salons && salons.length === 0 && (
                      <div className="text-sm" style={{ color: T.muted }}>За период нет начислений, привязанных к салонам.</div>
                    )}
                  </Section>
                )}

                {/* Top earners */}
                {topEarners.length > 0 && (
                  <Section title="Топ по начислению" hint="самые крупные начисления за период">
                    <div className="space-y-2.5 pt-1">
                      {topEarners.map((r, i) => (
                        <BarRow key={i} label={r.name} value={r.gross} max={maxTop} color={r.catColor} right={fmtMoney(r.gross)} />
                      ))}
                    </div>
                  </Section>
                )}

                {/* Breakdown table */}
                <Section title="Детализация по сотрудникам">
                  <div className="rounded-xl border overflow-hidden" style={{ borderColor: T.line }}>
                    <table className="w-full text-[13px] table-fixed">
                      <colgroup>
                        <col style={{ width: '20%' }} />
                        {visibleCols.map((c) => <col key={c.key} style={{ width: `${80 / visibleCols.length}%` }} />)}
                      </colgroup>
                      <thead>
                        <tr style={{ background: T.bg2, color: T.muted }} className="text-[10px] uppercase tracking-wide">
                          <th className="text-left font-semibold px-3 py-2">Сотрудник</th>
                          {visibleCols.map((c) => <th key={c.key} className="text-right font-semibold px-3 py-2">{c.label}</th>)}
                        </tr>
                      </thead>
                      {cats.map((c) => {
                        const Icon = c.icon;
                        return (
                          <tbody key={c.key}>
                            <tr style={{ background: T.bg, borderTop: `2px solid ${T.line}` }}>
                              <td colSpan={visibleCols.length + 1} className="px-3 py-1.5">
                                <div className="flex items-center justify-between">
                                  <span className="font-bold flex items-center gap-1.5" style={{ color: c.color }}>
                                    <Icon size={13} /> {c.title}
                                    <span className="text-[11px] font-normal" style={{ color: T.muted }}>· {c.rows.length}</span>
                                  </span>
                                  <div className="flex items-center gap-3">
                                    <span className="text-[12px]" style={{ color: T.muted }}>
                                      ФОТ <span className="font-bold" style={{ color: T.ink }}>{fmtMoney(c.totals.gross)}</span>
                                    </span>
                                    {!exporting && addingToCategory !== c.key && (
                                      <button className="text-[11px] font-medium flex items-center gap-1 hover:opacity-70" style={{ color: BRAND }}
                                        onClick={() => setAddingToCategory(c.key)}>
                                        <Plus size={12} /> Добавить
                                      </button>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                            {c.error && (
                              <tr><td colSpan={visibleCols.length + 1} className="px-3 py-2 text-[12px]" style={{ color: DANGER }}>Не удалось загрузить: {c.error}</td></tr>
                            )}
                            {c.rows.map((r, i) => (
                              <tr key={i} style={{ borderTop: `1px solid ${T.line}` }}>
                                <td className="px-3 py-1.5 font-medium break-words" style={{ color: T.ink }}>
                                  <span className="flex items-center gap-1.5">
                                    <span className="truncate">{r.name}</span>
                                    {r.id?.startsWith('manual_') && <span className="text-[10px] font-normal shrink-0" style={{ color: T.muted }}>· вручную</span>}
                                    {!exporting && r.id?.startsWith('manual_') && (
                                      <button className="shrink-0 hover:opacity-70" onClick={() => removeManualRow(r.id)} title="Удалить">
                                        <Trash2 size={12} style={{ color: DANGER }} />
                                      </button>
                                    )}
                                  </span>
                                </td>
                                {visibleCols.map((col) => (
                                  <td key={col.key} className="px-3 py-1.5 text-right tabular-nums"
                                    style={{ color: col.key === 'to_pay' ? BRAND : (col.key === 'penalties' || col.key === 'advances') && r[col.key] ? DANGER : T.ink, fontWeight: col.key === 'to_pay' ? 600 : 400 }}>
                                    {col.key === 'gross' || col.key === 'to_pay' ? fmtMoney(r[col.key]) : (r[col.key] ? fmtMoney(r[col.key]) : '—')}
                                  </td>
                                ))}
                              </tr>
                            ))}
                            {!c.error && c.rows.length === 0 && addingToCategory !== c.key && (
                              <tr><td colSpan={visibleCols.length + 1} className="px-3 py-2 text-[12px]" style={{ color: T.muted }}>
                                {catStatus[c.key] === 'loading' ? 'Считаю…' : 'Нет данных за период.'}
                              </td></tr>
                            )}
                            {!exporting && addingToCategory === c.key && (
                              <AddRowForm visibleCols={visibleCols} onCancel={() => setAddingToCategory(null)} onSubmit={(row) => addManualRow(c.key, row)} />
                            )}
                            {c.rows.length > 0 && (
                              <tr style={{ borderTop: `1px solid ${T.line}`, background: T.bg2 }}>
                                <td className="px-3 py-1.5 font-semibold" style={{ color: T.ink }}>Итого · {c.title.toLowerCase()}</td>
                                {visibleCols.map((col) => (
                                  <td key={col.key} className="px-3 py-1.5 text-right tabular-nums font-semibold" style={{ color: col.key === 'to_pay' ? BRAND : T.ink }}>{fmtMoney(c.totals[col.key])}</td>
                                ))}
                              </tr>
                            )}
                          </tbody>
                        );
                      })}
                      <tfoot>
                        <tr style={{ borderTop: `2px solid ${T.ink}` }}>
                          <td className="px-3 py-2 font-extrabold" style={{ color: T.ink }}>ВСЕГО · {headcount} чел.</td>
                          {visibleCols.map((c) => (
                            <td key={c.key} className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: c.key === 'gross' || c.key === 'to_pay' ? BRAND : T.ink }}>{fmtMoney(grand[c.key])}</td>
                          ))}
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </Section>
              </div>

              {/* Footer */}
              <div className="px-10 py-4 flex items-center justify-between text-[11px]" style={{ borderTop: `1px solid ${T.line}`, color: T.muted }}>
                <span>Сводный отчёт по фонду оплаты труда · {periodLabel}</span>
                <span>Сформировано {generatedAt}</span>
              </div>
            </div>
          </RTC.Provider>
          </ScaledReport>
        </div>
      )}
    </div>
  );
}
