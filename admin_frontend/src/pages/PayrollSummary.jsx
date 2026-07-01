import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  BarChart2, RefreshCw, Image as ImageIcon, Calculator, Hammer, Users, Truck, Wallet, TrendingDown, UserRound,
  SlidersHorizontal, X, Check, Plus, Trash2,
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
const fmtShort = (v) => {
  v = Math.round(Number(v) || 0);
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} млн ₽`;
  if (Math.abs(v) >= 1e3) return `${Math.round(v / 1e3).toLocaleString('ru-RU')} тыс ₽`;
  return `${v} ₽`;
};
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
const lastDay = (ym) => { const [y, m] = ym.split('-').map(Number); return new Date(y, m, 0).getDate(); };
const fmtDateRu = (iso) => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };

// ── Date range helpers ────────────────────────────────────────────────────────
const isoDate = (d) => d.toISOString().slice(0, 10);
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
  const map = new Map();
  for (const rows of rowArrays) {
    for (const r of rows) {
      if (!map.has(r.name)) { map.set(r.name, { ...r }); continue; }
      const acc = map.get(r.name);
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
  { key: 'to_pay', label: 'К выплате' },
];

const sumRows = (rows) => {
  const t = {};
  for (const c of COLS) t[c.key] = (rows || []).reduce((s, r) => s + (Number(r[c.key]) || 0), 0);
  return t;
};

// ── Per-category, per-month loaders (raw, one calendar month at a time) ──────

async function loadAdminsMonth(period) {
  const [y, m] = period.split('-').map(Number);
  const monthName = MONTHS_RU[m - 1].toUpperCase();
  const res = await api.get('payroll/calculate', { params: { month: monthName, year: y } });
  return (res.data?.rows || []).map((r) => ({
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
async function loadAdmins(dateFrom, dateTo) {
  const perMonth = await Promise.all(monthsInRange(dateFrom, dateTo).map(loadAdminsMonth));
  return mergeRowsAcrossMonths(perMonth);
}

// masters/works already accepts an arbitrary date range server-side —
// no month-splitting needed here.
async function loadMasters(dateFrom, dateTo) {
  const res = await api.get('masters/works', { params: { date_from: dateFrom, date_to: dateTo } });
  const data = res.data;
  const services = Array.isArray(data) ? data : (data.services || []);
  const map = {};
  for (const r of services) {
    if (r.master_salary == null) continue;
    const name = r.out_description || '—';
    map[name] = (map[name] || 0) + (Number(r.master_salary) || 0);
  }
  return Object.entries(map)
    .map(([name, sal]) => ({ name, oklad: 0, commission: sal, bonuses: 0, penalties: 0, advances: 0, gross: sal, to_pay: sal }))
    .sort((a, b) => b.gross - a.gross);
}

async function loadManagersMonth(period, rangeFrom, rangeTo) {
  const monthFrom = `${period}-01`;
  const monthTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const incFrom = monthFrom > rangeFrom ? monthFrom : rangeFrom;
  const incTo = monthTo < rangeTo ? monthTo : rangeTo;
  const emp = await api.get('employees/', { params: { archived: false } }).then((r) => r.data || []);
  const managers = emp.filter((e) => e.status !== 'inactive' && (e.position || '').trim().toLowerCase() === MANAGER_POSITION);
  const rows = await Promise.all(managers.map(async (mgr) => {
    const plan = await api.get('manager-salary/plan', { params: { employee_code: mgr.id, period } }).then((r) => r.data).catch(() => ({}));
    const adv = await api.get('manager-salary/advances', { params: { employee_id: mgr.id } }).then((r) => r.data).catch(() => ({ total: 0 }));
    const inc = await api.get('incentives/', { params: { employee_id: mgr.id, date_from: incFrom, date_to: incTo } }).then((r) => r.data).catch(() => []);
    const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    let met = null;
    if (mgr.amo_user_id) {
      met = await api.get('manager-salary/metrics', { params: { date_from: incFrom, date_to: incTo, amo_user_id: mgr.amo_user_id } }).then((r) => r.data).catch(() => null);
    }
    const calc = await api.post('manager-salary/calc', {
      oklad: plan.oklad, kpi_max: plan.kpi_max,
      revenue_plan: plan.revenue_plan, revenue_actual: met?.revenue_actual || 0,
      repair_plan_conv: plan.repair_plan_conv, repair_target_deals: met?.repair_target_deals || 0, repair_total_deals: met?.repair_total_deals || 0,
      sew_plan_conv: plan.sew_plan_conv, sew_target_deals: met?.sew_target_deals || 0, sew_total_deals: met?.sew_total_deals || 0, sew_new_leads: met?.sew_new_leads || 0,
      advances: adv?.total || 0, bonuses, penalties,
    }).then((r) => r.data).catch(() => null);
    if (!calc) return null;
    return {
      name: mgr.full_name || mgr.name, oklad: calc.oklad, commission: calc.kpi,
      bonuses: calc.bonuses, penalties: calc.penalties, advances: calc.advances,
      gross: calc.gross, to_pay: calc.to_pay,
    };
  }));
  return rows.filter(Boolean);
}
async function loadManagers(dateFrom, dateTo) {
  const perMonth = await Promise.all(monthsInRange(dateFrom, dateTo).map((period) => loadManagersMonth(period, dateFrom, dateTo)));
  return mergeRowsAcrossMonths(perMonth);
}

async function loadCouriersMonth(period, rangeFrom, rangeTo) {
  const monthFrom = `${period}-01`;
  const monthTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const incFrom = monthFrom > rangeFrom ? monthFrom : rangeFrom;
  const incTo = monthTo < rangeTo ? monthTo : rangeTo;
  const emp = await api.get('employees/', { params: { archived: false } }).then((r) => r.data || []);
  const couriers = emp.filter((e) => e.status !== 'inactive' && (e.position || '').toLowerCase().includes('курьер'));
  const rows = await Promise.all(couriers.map(async (c) => {
    const plan = await api.get('courier-salary/plan', { params: { employee_code: c.id, period } }).then((r) => r.data).catch(() => ({}));
    const adv = await api.get('courier-salary/advances', { params: { employee_id: c.id } }).then((r) => r.data).catch(() => ({ total: 0 }));
    const inc = await api.get('incentives/', { params: { employee_id: c.id, date_from: incFrom, date_to: incTo } }).then((r) => r.data).catch(() => []);
    const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const calc = await api.post('courier-salary/calc', { oklad: plan.oklad, advances: adv?.total || 0, bonuses, penalties }).then((r) => r.data).catch(() => null);
    if (!calc) return null;
    return { name: c.full_name || c.name, oklad: calc.oklad, commission: 0, bonuses: calc.bonuses, penalties: calc.penalties, advances: calc.advances, gross: calc.gross, to_pay: calc.to_pay };
  }));
  return rows.filter(Boolean).filter((r) => r.gross || r.advances);
}
async function loadCouriers(dateFrom, dateTo) {
  const perMonth = await Promise.all(monthsInRange(dateFrom, dateTo).map((period) => loadCouriersMonth(period, dateFrom, dateTo)));
  return mergeRowsAcrossMonths(perMonth);
}

const CATS = [
  { key: 'admins', title: 'Администраторы', icon: Calculator, color: '#6366f1', load: loadAdmins },
  { key: 'masters', title: 'Мастера', icon: Hammer, color: '#f59e0b', load: loadMasters },
  { key: 'managers', title: 'Менеджеры', icon: Users, color: '#10b981', load: loadManagers },
  { key: 'couriers', title: 'Курьеры', icon: Truck, color: '#ec4899', load: loadCouriers },
];

// Accent colors — fixed, look good in both themes
const BRAND = '#6366f1', DANGER = '#ef4444';

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

function PayrollProgress({ status }) {
  const done = CATS.filter((c) => status[c.key] === 'done' || status[c.key] === 'error').length;
  const total = CATS.length;
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
          background: 'linear-gradient(90deg, #6366f1 0%, #8b5cf6 55%, #a78bfa 100%)',
          boxShadow: '0 0 12px rgba(99,102,241,0.5)',
          transition: 'width 0.45s cubic-bezier(0.4, 0, 0.2, 1)',
        }} />
      </div>

      {/* Per-category step cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {CATS.map((cat) => {
          const st = status[cat.key] || 'idle';
          const Icon = cat.icon;
          const isLoading = st === 'loading';
          const isDone = st === 'done';
          const isError = st === 'error';
          return (
            <div key={cat.key}
              className="rounded-xl p-3.5 flex items-center gap-2.5 transition-all duration-300"
              style={{
                background: isLoading ? 'var(--color-primary-muted)' : isDone ? 'rgba(16,185,129,0.08)' : 'var(--color-surface)',
                border: `1px solid ${isLoading ? 'rgba(99,102,241,0.5)' : isDone ? 'rgba(16,185,129,0.3)' : isError ? 'rgba(239,68,68,0.3)' : 'var(--color-border)'}`,
              }}>
              {isLoading
                ? <RefreshCw size={15} className="animate-spin shrink-0" style={{ color: 'var(--color-primary)' }} />
                : <Icon size={15} style={{ color: isDone ? '#10b981' : isError ? '#ef4444' : cat.color, flexShrink: 0 }} />
              }
              <div className="min-w-0">
                <div className="text-xs font-semibold truncate text-[color:var(--color-text)]">{cat.title}</div>
                <div className="text-[10px] mt-0.5" style={{
                  color: isDone ? '#10b981' : isError ? '#ef4444' : isLoading ? 'var(--color-primary)' : 'var(--color-text-faint)',
                }}>
                  {isDone ? '✓ Готово' : isError ? '✗ Ошибка' : isLoading ? 'Загружаю…' : 'Ожидание'}
                </div>
              </div>
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
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${showBreakdown ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]' : 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]'}`}>
            Подробно (+ авансы)
          </button>
          <button type="button" onClick={() => onSetShowBreakdown(false)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${!showBreakdown ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]' : 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]'}`}>
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
  const [loading, setLoading] = useState(false);
  const [pnging, setPnging] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [catStatus, setCatStatus] = useState({});
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

  // T drives the on-screen theme: dark normally, light during PNG export
  const T = exporting ? LIGHT : DARK;

  const load = useCallback(async () => {
    setLoading(true);
    setCatStatus({});
    try {
      const results = await Promise.all(CATS.map(async (c) => {
        setCatStatus((prev) => ({ ...prev, [c.key]: 'loading' }));
        const result = await c.load(dateFrom, dateTo)
          .then((rows) => ({ rows }))
          .catch((e) => ({ rows: [], error: e?.response?.data?.detail || e.message || 'ошибка' }));
        setCatStatus((prev) => ({ ...prev, [c.key]: result.error ? 'error' : 'done' }));
        return result;
      }));
      const next = {};
      CATS.forEach((c, i) => { next[c.key] = results[i]; });
      setData(next);
      setGeneratedAt(new Date().toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
    } finally { setLoading(false); }
  }, [dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { saveSet(HIDDEN_CATS_KEY, hiddenCats); }, [hiddenCats]);
  useEffect(() => { saveSet(HIDDEN_EMPLOYEES_KEY, hiddenEmployees); }, [hiddenEmployees]);
  useEffect(() => { saveBool(SHOW_BREAKDOWN_KEY, showBreakdown); }, [showBreakdown]);
  useEffect(() => { saveManualRows(manualByRange); }, [manualByRange]);

  const manualRows = manualByRange[rangeKey] || [];

  function applyPreset(p) {
    setActivePreset(p.key);
    const { from, to } = p.range();
    setDateFrom(from); setDateTo(to);
  }
  function applyCustomRange() {
    setActivePreset('custom');
    load();
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
  const topEarners = [...tagged].sort((a, b) => b.to_pay - a.to_pay).slice(0, 6);
  const maxCat = Math.max(1, ...cats.map((c) => c.totals.gross));
  const maxTop = Math.max(1, ...topEarners.map((r) => r.to_pay));
  const comp = [
    { label: 'Оклад', value: grand.oklad, color: '#6366f1' },
    { label: 'Комиссия / KPI', value: grand.commission, color: '#10b981' },
    { label: 'Премии', value: grand.bonuses, color: '#f59e0b' },
  ].filter((s) => s.value > 0);
  // "Кратко" = salary breakdown (oklad/KPI/premии/штрафы-if-any) minus авансы,
  // not just two totals — advances is the one column considered sensitive
  // enough to gate behind "Подробно".
  const visibleCols = showBreakdown
    ? COLS
    : COLS.filter((c) => c.key !== 'advances' && (c.key !== 'penalties' || grand.penalties > 0));

  async function downloadPng() {
    if (!reportRef.current) return;
    setPnging(true);
    setExporting(true);
    setAddingToCategory(null);
    // Two animation frames so React re-renders with the light LIGHT theme (and
    // without any open inline add-row form) before capture
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    try {
      const url = await toPng(reportRef.current, { backgroundColor: '#ffffff', pixelRatio: 2, cacheBust: true, skipFonts: true });
      const a = document.createElement('a');
      a.href = url;
      a.download = `ФОТ_${dateFrom}_${dateTo}.png`;
      a.click();
      toast('PNG сохранён', 'success');
    } catch (e) {
      console.error(e);
      toast('Ошибка генерации PNG', 'error');
    } finally {
      setExporting(false);
      setPnging(false);
    }
  }

  return (
    <div className="space-y-5 max-w-[1140px] mx-auto pb-12">
      {/* Top progress bar: shown while refreshing or generating PNG */}
      <TopProgressBar active={pnging || (loading && !!data)} />

      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
            <BarChart2 size={24} /> Сводный отчёт по ФОТ
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Администраторы, мастера, менеджеры и курьеры за период · настраиваемый PNG-отчёт</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          {DATE_PRESETS.map((p) => (
            <button key={p.key} onClick={() => applyPreset(p)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${activePreset === p.key ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]' : 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text)]'}`}>
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
          <button className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${activePreset === 'custom' ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]' : 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text)]'}`}
            onClick={applyCustomRange}>
            Применить период
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={() => setShowSettings((v) => !v)}>
            <SlidersHorizontal size={14} /> Настроить{(hiddenCats.size + hiddenEmployees.size) > 0 ? ` (${hiddenCats.size + hiddenEmployees.size})` : ''}
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
          </button>
          <button className="btn btn--primary flex items-center gap-1.5" onClick={downloadPng} disabled={pnging || loading || !data}>
            <ImageIcon size={15} /> {pnging ? 'Генерирую…' : 'Скачать PNG'}
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

      {/* Initial load: detailed progress panel */}
      {loading && !data && <PayrollProgress status={catStatus} />}

      {/* Report (shown once data is available, even while refreshing) */}
      {data && (
        <div className="rounded-2xl">
          <ScaledReport>
          <RTC.Provider value={T}>
            {/* ════ Captured report (fixed 1080px) ════ */}
            <div ref={reportRef} style={{ width: 1080, background: T.bg, color: T.ink }} className="fot-report overflow-hidden">
              {/* Reset the app's global dark table styling inside the report */}
              <style>{`.fot-report table,.fot-report thead,.fot-report tbody,.fot-report tfoot,.fot-report tr,.fot-report td,.fot-report th{background:transparent;border:0;color:inherit;box-shadow:none;}`}</style>

              {/* Header — always purple gradient */}
              <div className="px-10 pt-9 pb-8 text-white flex items-end justify-between"
                style={{ background: 'linear-gradient(110deg,#4f46e5 0%,#7c3aed 55%,#9333ea 100%)' }}>
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">Сводный отчёт</div>
                  <div className="mt-1 text-[30px] font-extrabold leading-tight">Фонд оплаты труда</div>
                  <div className="mt-1 text-sm opacity-90">{periodLabel} · {cats.map((c) => c.title.toLowerCase()).join(', ') || 'нет активных категорий'}</div>
                </div>
                <div className="text-right">
                  <div className="text-[11px] font-semibold uppercase tracking-wide opacity-80">Итого начислено</div>
                  <div className="text-[40px] font-extrabold leading-none tabular-nums">{fmtMoney(grand.gross)}</div>
                  <div className="mt-1 text-sm opacity-90">к выплате {fmtMoney(grand.to_pay)}</div>
                </div>
              </div>

              <div className="px-10 py-8 space-y-8">
                {/* KPI cards */}
                <div className="grid grid-cols-4 gap-4">
                  <KpiCard icon={<Wallet size={13} />} label="ФОТ за период" value={fmtMoney(grand.gross)} sub={`средняя ${fmtShort(headcount ? grand.gross / headcount : 0)} / чел.`} color={BRAND} />
                  <KpiCard icon={<Wallet size={13} />} label="К выплате" value={fmtMoney(grand.to_pay)} sub={`${pct(grand.to_pay, grand.gross)}% от начисленного`} color="#10b981" />
                  <KpiCard icon={<UserRound size={13} />} label="Сотрудников" value={String(headcount)} sub={cats.map((c) => `${c.title.slice(0, 4).toLowerCase()}. ${c.rows.length}`).join(' · ') || '—'} />
                  <KpiCard icon={<TrendingDown size={13} />} label="Удержания" value={fmtMoney(withholdings)} sub={`авансы ${fmtShort(grand.advances)} · штрафы ${fmtShort(grand.penalties)}`} color={DANGER} />
                </div>

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
                          <div className="text-base font-bold tabular-nums" style={{ color: T.ink }}>{fmtShort(grand.gross)}</div>
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
                      <span style={{ color: T.muted }}>− удержания</span>
                      <span className="font-semibold tabular-nums" style={{ color: DANGER }}>{fmtMoney(withholdings)}</span>
                      <span style={{ color: T.muted }}>= к выплате</span>
                      <span className="font-bold tabular-nums" style={{ color: '#10b981' }}>{fmtMoney(grand.to_pay)}</span>
                    </div>
                  </div>
                </Section>

                {/* Top earners */}
                {topEarners.length > 0 && (
                  <Section title="Топ по выплате" hint="самые крупные выплаты за период">
                    <div className="space-y-2.5 pt-1">
                      {topEarners.map((r, i) => (
                        <BarRow key={i} label={r.name} value={r.to_pay} max={maxTop} color={r.catColor} right={fmtMoney(r.to_pay)} />
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
                              <tr><td colSpan={visibleCols.length + 1} className="px-3 py-2 text-[12px]" style={{ color: T.muted }}>Нет данных за период.</td></tr>
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
