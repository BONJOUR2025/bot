import { useState, useMemo, useRef, useEffect } from 'react';
import {
  RefreshCw, Download, EyeOff, Eye, ChevronDown, Check,
  TrendingUp, TrendingDown, BarChart3, Trophy, Users, Target, Calendar,
} from 'lucide-react';
import {
  ComposedChart, Area, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Line,
  BarChart, PieChart, Pie, Cell,
} from 'recharts';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';

/* ── constants ───────────────────────────────────────────── */
function toLocalDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
const TODAY = toLocalDateStr(new Date());
const MONTHS_RU      = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const MONTHS_KEY_RU  = ['ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ','ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ'];
const DAY_NAMES      = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
const CHART_COLORS   = ['#6366f1','#22c55e','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6','#f97316','#a3e635'];

const EMP_NAMES = {
  '0102':'Вера','7272':'Арина','2404':'Эмиль','5984':'Полина',
  '3007':'Юля','2201':'Катя','2502':'Виктория','1996':'Вероника',
  '2106':'Валерия','1302':'Любовь','2104':'Алекс','0208':'Марина',
};

const CATEGORIES = [
  { key:'repair',    label:'Ремонт / Химчистка', color:'#6366f1' },
  { key:'cosmetics', label:'Косметика',           color:'#22c55e' },
  { key:'shoes',     label:'Обувь',               color:'#f59e0b' },
];
const LABEL_TO_KEY = Object.fromEntries(CATEGORIES.map((c) => [c.label, c.key]));

function toggleSet(setter, key) {
  setter((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });
}

/* ── helpers ─────────────────────────────────────────────── */
const fmtRub = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtK   = (v) => v == null ? '—'
  : v >= 1_000_000 ? `${(v/1_000_000).toFixed(1)} млн ₽`
  : v >= 1_000     ? `${(v/1_000).toFixed(0)}k ₽`
  : `${Math.round(v)} ₽`;
const fmtPct = (v) => v == null ? '—' : v.toFixed(1) + '%';

const empName = (code) => EMP_NAMES[code] || code;

function initials(name) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2).toUpperCase();
}

function getPeriodKey(dateStr, gran) {
  if (gran === 'day')   return dateStr;
  if (gran === 'month') return dateStr.slice(0, 7);
  const d   = new Date(dateStr);
  const day = d.getDay() || 7;
  d.setDate(d.getDate() + 4 - day);
  const jan1 = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil((((d - jan1) / 86400000) + 1) / 7);
  return `${d.getFullYear()}-W${String(week).padStart(2,'0')}`;
}

function getPeriodLabel(key, gran) {
  if (gran === 'day') { const [,m,d] = key.split('-'); return `${d}.${m}`; }
  if (gran === 'month') { const [y,m] = key.split('-'); return `${MONTHS_RU[+m-1]} ${y.slice(2)}`; }
  const [yearStr, wStr] = key.split('-W');
  const jan4 = new Date(+yearStr, 0, 4);
  const mon  = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (+wStr - 1) * 7);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  const f = (dt) => `${String(dt.getDate()).padStart(2,'0')}.${String(dt.getMonth()+1).padStart(2,'0')}`;
  return `${f(mon)}–${f(sun)}`;
}

const toMonthKey = (yyyymm) => { const [y,m] = yyyymm.split('-'); return `${MONTHS_KEY_RU[+m-1]}_${y}`; };

function getMonthsInRange(from, to) {
  const months = [];
  const cur = new Date((from || TODAY).slice(0,7) + '-01');
  const end = new Date((to   || TODAY).slice(0,7) + '-01');
  while (cur <= end) { months.push(cur.toISOString().slice(0,7)); cur.setMonth(cur.getMonth()+1); }
  return months;
}

function quickRange(key) {
  const n = new Date(); const y = n.getFullYear(), m = n.getMonth();
  if (key === 'month') return [toLocalDateStr(new Date(y, m, 1)), TODAY];
  if (key === 'prev')  return [toLocalDateStr(new Date(y, m-1, 1)), toLocalDateStr(new Date(y, m, 0))];
  if (key === 'q')     return [toLocalDateStr(new Date(y, Math.floor(m/3)*3, 1)), TODAY];
  if (key === 'year')  return [toLocalDateStr(new Date(y, 0, 1)), TODAY];
  return [TODAY, TODAY];
}

/* ── MultiSelect ─────────────────────────────────────────── */
function MultiSelect({ options, selected, onChange, placeholder = 'Все' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);
  const allSelected = selected.size === 0;
  const label = allSelected ? placeholder : options.filter((o) => selected.has(o.value)).map((o) => o.label).join(', ');
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="input w-full text-left flex items-center justify-between gap-2 text-sm">
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 top-full mt-1 w-full min-w-[180px] rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] shadow-xl overflow-hidden max-h-64 overflow-y-auto">
          <button type="button" onClick={() => onChange(new Set())}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors">
            <Check size={13} className={allSelected ? 'text-[color:var(--color-primary)]' : 'opacity-0'} />
            <span>{placeholder}</span>
          </button>
          <div className="border-t border-[color:var(--color-border)]" />
          {options.map((o) => {
            const sel = selected.has(o.value);
            return (
              <button key={o.value} type="button"
                onClick={() => { const next = new Set(selected); if (sel) next.delete(o.value); else next.add(o.value); onChange(next.size === options.length ? new Set() : next); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors">
                <Check size={13} className={sel ? 'text-[color:var(--color-primary)]' : 'opacity-0'} />
                <span className="truncate">{o.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ── Chart tooltip ───────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label, nameMap }) => {
  if (!active || !payload?.length) return null;
  const items = payload.filter((p) => p.dataKey !== '_ma');
  const ma    = payload.find((p)  => p.dataKey === '_ma');
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] p-3 text-sm shadow-xl max-w-[260px]">
      <div className="font-semibold mb-2">{label}</div>
      {items.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 leading-6">
          <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.fill || p.color }} />
          <span className="text-[color:var(--color-muted-foreground)] truncate flex-1">{nameMap?.[p.dataKey] || p.name}:</span>
          <span className="font-medium tabular-nums">{Math.round(p.value || 0).toLocaleString('ru-RU')} ₽</span>
        </div>
      ))}
      {ma && (
        <div className="border-t border-[color:var(--color-border)] mt-1.5 pt-1.5 text-xs text-[color:var(--color-muted-foreground)]">
          MA7: {Math.round(ma.value || 0).toLocaleString('ru-RU')} ₽
        </div>
      )}
    </div>
  );
};

/* ── KPI card with left-border accent ───────────────────── */
function KpiStat({ label, value, delta, sub, accent = '#6366f1', icon }) {
  const up = delta != null && delta > 0;
  const dn = delta != null && delta < 0;
  return (
    <div className="app-card p-4 flex gap-3" style={{ borderLeft: `3px solid ${accent}` }}>
      {icon && <div className="mt-0.5 shrink-0" style={{ color: accent }}>{icon}</div>}
      <div className="min-w-0 flex-1">
        <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] font-medium">{label}</div>
        <div className="text-xl sm:text-2xl font-bold tabular-nums mt-0.5 leading-tight" style={{ color: accent }}>{value}</div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          {delta != null && Math.abs(delta) >= 0.1 && (
            <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full ${up ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400' : 'bg-red-50 dark:bg-red-900/30 text-red-500 dark:text-red-400'}`}>
              {up ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
              {up ? '+' : ''}{delta.toFixed(1)}%
            </span>
          )}
          {sub && <span className="text-[11px] text-[color:var(--color-muted-foreground)]">{sub}</span>}
        </div>
      </div>
    </div>
  );
}

/* ── Donut label ─────────────────────────────────────────── */
const RADIAN = Math.PI / 180;
function DonutLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.06) return null;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

/* ── Employee avatar chip ────────────────────────────────── */
function EmpAvatar({ name, color, size = 32 }) {
  return (
    <div className="rounded-full flex items-center justify-center text-white font-bold shrink-0"
      style={{ width: size, height: size, background: color, fontSize: size * 0.34 }}>
      {initials(name)}
    </div>
  );
}

/* ── 3-color category breakdown bar ─────────────────────── */
function CatBar({ repair, cosmetics, shoes }) {
  const total = (repair||0) + (cosmetics||0) + (shoes||0);
  if (total === 0) return <div className="h-1.5 rounded-full bg-[color:var(--color-border)] w-full" />;
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden w-full gap-px">
      {repair    > 0 && <div style={{ flex: repair,    background: '#6366f1' }} />}
      {cosmetics > 0 && <div style={{ flex: cosmetics, background: '#22c55e' }} />}
      {shoes     > 0 && <div style={{ flex: shoes,     background: '#f59e0b' }} />}
    </div>
  );
}

/* ── Employee leaderboard ────────────────────────────────── */
function Leaderboard({ empSummary, planTotals, activeCodes, onSelect }) {
  const maxTotal = empSummary.length > 0 ? empSummary[0].total : 1;
  const medals   = ['🥇', '🥈', '🥉'];
  return (
    <div className="app-card overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[color:var(--color-border)] flex items-center gap-2">
        <Trophy size={16} className="text-amber-500" />
        <h3 className="font-semibold">Рейтинг сотрудников</h3>
        <span className="ml-auto text-xs text-[color:var(--color-muted-foreground)]">{empSummary.length} чел.</span>
      </div>
      <div className="divide-y divide-[color:var(--color-border)]">
        {empSummary.map((e, i) => {
          const plan  = planTotals[e.code] || 0;
          const pct   = plan > 0 ? e.total / plan * 100 : null;
          const share = maxTotal > 0 ? e.total / maxTotal : 0;
          const color = CHART_COLORS[i % CHART_COLORS.length];
          const isActive = activeCodes?.has(e.code);
          return (
            <button
              key={e.code}
              type="button"
              onClick={() => onSelect?.(e.code)}
              className={`w-full text-left px-5 py-3 flex items-center gap-3 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-muted)]/30 cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <span className="w-7 text-center text-lg leading-none shrink-0">
                {medals[i] ?? <span className="text-sm font-semibold text-[color:var(--color-muted-foreground)]">{i+1}</span>}
              </span>
              <EmpAvatar name={empName(e.code)} color={color} size={36} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm truncate">{empName(e.code)}</span>
                  <span className="font-bold tabular-nums text-sm shrink-0" style={{ color }}>{fmtK(e.total)}</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: color }} />
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <CatBar repair={e.repair} cosmetics={e.cosmetics} shoes={e.shoes} />
                  {pct != null && (
                    <span className={`text-[10px] font-semibold shrink-0 ${pct >= 100 ? 'text-emerald-600' : pct >= 75 ? 'text-amber-500' : 'text-red-500'}`}>
                      {pct.toFixed(0)}% пл.
                    </span>
                  )}
                </div>
              </div>
              <div className="text-xs text-[color:var(--color-muted-foreground)] shrink-0 text-right hidden sm:block leading-5">
                <div>{e.activeDays} дн.</div>
                <div className="text-[10px]">{fmtK(e.activeDays > 0 ? e.total / e.activeDays : 0)}/дн</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Day-of-week heatmap bars ────────────────────────────── */
function DayHeatmap({ data }) {
  const maxAvg = Math.max(...data.map((d) => d.avg), 1);
  return (
    <div className="app-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Calendar size={15} className="text-[color:var(--color-muted-foreground)]" />
        <h3 className="font-semibold text-sm">По дням недели</h3>
        <span className="text-xs text-[color:var(--color-muted-foreground)]">ср. выручка за день</span>
      </div>
      <div className="flex items-end gap-2" style={{ height: 96 }}>
        {data.map((d, i) => {
          const h   = maxAvg > 0 ? Math.max((d.avg / maxAvg) * 100, d.count > 0 ? 5 : 0) : 0;
          const wkd = i >= 5;
          return (
            <div key={d.name} className="flex-1 flex flex-col items-center gap-1 group" title={`${d.name}: ${fmtK(d.avg)} / ${d.count} дн.`}>
              <div className="w-full flex items-end rounded-t-sm overflow-hidden" style={{ height: 72 }}>
                <div className="w-full rounded-t-md transition-all group-hover:opacity-70"
                  style={{
                    height: `${h}%`,
                    background: wkd
                      ? 'linear-gradient(to top, #f59e0b, #fcd34d)'
                      : 'linear-gradient(to top, #6366f1, #a5b4fc)',
                  }}
                />
              </div>
              <span className="text-[10px] font-semibold text-[color:var(--color-muted-foreground)]">{d.name}</span>
              <span className="text-[9px] tabular-nums text-[color:var(--color-text-primary)]">
                {d.count > 0 ? `${(d.avg/1000).toFixed(0)}k` : '—'}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 mt-3 text-[10px] text-[color:var(--color-muted-foreground)]">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:'linear-gradient(to top,#6366f1,#a5b4fc)'}} /> Будни</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:'linear-gradient(to top,#f59e0b,#fcd34d)'}} /> Выходные</span>
      </div>
    </div>
  );
}

/* ── Plan fulfillment horizontal gauge bars ──────────────── */
function PlanGauges({ empSummary, planTotals }) {
  const withPlan = empSummary.filter((e) => (planTotals[e.code] || 0) > 0);
  if (withPlan.length === 0) return null;
  return (
    <div className="app-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Target size={15} className="text-[color:var(--color-muted-foreground)]" />
        <h3 className="font-semibold text-sm">Выполнение плана</h3>
      </div>
      <div className="space-y-3">
        {withPlan.map((e, i) => {
          const plan = planTotals[e.code];
          const pct  = Math.min(e.total / plan * 100, 130);
          const done = e.total / plan * 100;
          const color = done >= 100 ? '#10b981' : done >= 75 ? '#f59e0b' : '#ef4444';
          return (
            <div key={e.code}>
              <div className="flex items-center justify-between mb-1 text-sm">
                <span className="font-medium truncate">{empName(e.code)}</span>
                <span className="font-bold tabular-nums text-xs" style={{ color }}>
                  {done.toFixed(0)}%
                  <span className="text-[color:var(--color-muted-foreground)] font-normal"> · {fmtK(e.total)} / {fmtK(plan)}</span>
                </span>
              </div>
              <div className="relative h-2 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                <div className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, background: color }} />
                {/* 100% marker */}
                <div className="absolute top-0 bottom-0 w-px bg-[color:var(--color-text-primary)]/30" style={{ left: `${100/130*100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── main component ──────────────────────────────────────── */
export default function SalesAnalytics() {
  const now = new Date();
  const monthStart = toLocalDateStr(new Date(now.getFullYear(), now.getMonth(), 1));

  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo,   setDateTo]   = useState(TODAY);
  const [gran,     setGran]     = useState('day');
  const [hideZero, setHideZero] = useState(false);
  const [showMA,   setShowMA]   = useState(false);
  const [showPlan, setShowPlan] = useState(false);
  const [chartMode, setChartMode] = useState('area');
  const [selectedEmployees,  setSelectedEmployees]  = useState(new Set());
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [activeTab, setActiveTab] = useState('overview');

  const [rows,     setRows]     = useState([]);
  const [prevRows, setPrevRows] = useState([]);
  const [plans,    setPlans]    = useState({});
  const [loading,  setLoading]  = useState(false);
  const [loaded,   setLoaded]   = useState(false);
  const [error,    setError]    = useState(null);

  const months = useMemo(() => getMonthsInRange(dateFrom, dateTo), [dateFrom, dateTo]);

  const activeCats = useMemo(() => {
    const all = CATEGORIES.map((c) => c.key);
    return selectedCategories.size === 0 ? all : all.filter((k) => selectedCategories.has(k));
  }, [selectedCategories]);

  async function load() {
    setLoading(true); setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const d0 = new Date(dateFrom || TODAY), d1 = new Date(dateTo || TODAY);
      const prevTo = new Date(d0); prevTo.setDate(prevTo.getDate() - 1);
      const prevFrom = new Date(+prevTo - (d1 - d0));
      const monthKeys = months.map(toMonthKey).join(',');
      const [mainRes, prevRes, plansRes] = await Promise.all([
        api.get('/sales/daily', { params }),
        api.get('/sales/daily', { params: { date_from: prevFrom.toISOString().slice(0,10), date_to: prevTo.toISOString().slice(0,10) } }),
        api.get('/sales/plans', { params: { month_keys: monthKeys } }),
      ]);
      setRows(mainRes.data); setPrevRows(prevRes.data); setPlans(plansRes.data); setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally { setLoading(false); }
  }

  const allEmployees = useMemo(() => {
    const map = {};
    rows.forEach((r) => { if (!map[r.code]) map[r.code] = { code: r.code, description: r.description, total: 0 }; map[r.code].total += r.total; });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  const employeeOptions = useMemo(() => allEmployees.map((e) => ({ value: e.code, label: empName(e.code) })), [allEmployees]);
  const categoryOptions = CATEGORIES.map((c) => ({ value: c.key, label: c.label }));

  const filteredRows  = useMemo(() => selectedEmployees.size ? rows.filter((r) => selectedEmployees.has(r.code)) : rows, [rows, selectedEmployees]);
  const prevFiltered  = useMemo(() => selectedEmployees.size ? prevRows.filter((r) => selectedEmployees.has(r.code)) : prevRows, [prevRows, selectedEmployees]);

  const employees = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => { if (!map[r.code]) map[r.code] = { code: r.code, total: 0 }; map[r.code].total += r.total; });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows]);

  const nameMap = useMemo(() => Object.fromEntries(employees.map((e) => [e.code, empName(e.code)])), [employees]);

  const { periods, cells, allPeriodsCount } = useMemo(() => {
    const c = {};
    filteredRows.forEach((r) => {
      const key = getPeriodKey(r.date, gran);
      if (!c[key]) c[key] = {};
      const val = activeCats.reduce((s, k) => s + (r[k] || 0), 0);
      c[key][r.code] = (c[key][r.code] || 0) + val;
    });
    const all    = Object.keys(c).sort();
    const nonZero = all.filter((p) => employees.reduce((s, e) => s + (c[p]?.[e.code] || 0), 0) > 0);
    return { periods: hideZero ? nonZero : all, cells: c, allPeriodsCount: all.length };
  }, [filteredRows, gran, hideZero, employees, activeCats]);

  const chartData = useMemo(() => {
    const data = periods.map((key) => {
      const entry = { period: key, label: getPeriodLabel(key, gran) };
      employees.forEach((e) => { entry[e.code] = cells[key]?.[e.code] || 0; });
      entry._total = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
      return entry;
    });
    data.forEach((d, i) => {
      const win = data.slice(Math.max(0, i - 6), i + 1);
      d._ma = win.reduce((s, x) => s + x._total, 0) / win.length;
    });
    return data;
  }, [periods, employees, cells, gran]);

  const empSummary = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, repair: 0, cosmetics: 0, shoes: 0, total: 0, activeDays: 0 };
      map[r.code].repair    += r.repair    || 0;
      map[r.code].cosmetics += r.cosmetics || 0;
      map[r.code].shoes     += r.shoes     || 0;
      const catVal = activeCats.reduce((s, k) => s + (r[k] || 0), 0);
      map[r.code].total += catVal;
      if (catVal > 0) map[r.code].activeDays++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows, activeCats]);

  const planTotals = useMemo(() => {
    const result = {};
    allEmployees.forEach((e) => {
      result[e.code] = months.reduce((sum, ym) => {
        const p = plans?.[toMonthKey(ym)]?.[e.code];
        return p ? sum + (p.repair_plan||0) + (p.cosmetics_plan||0) + (p.shoes_plan||0) : sum;
      }, 0);
    });
    return result;
  }, [months, plans, allEmployees]);

  const colTotals = useMemo(() => {
    const t = {};
    employees.forEach((e) => { t[e.code] = periods.reduce((s, p) => s + (cells[p]?.[e.code] || 0), 0); });
    t._grand = employees.reduce((s, e) => s + (t[e.code] || 0), 0);
    return t;
  }, [periods, employees, cells]);

  const kpi = useMemo(() => {
    const catKeys = CATEGORIES.map((c) => c.key);
    const cur = Object.fromEntries([...catKeys, 'total'].map((k) => [k, 0]));
    const prev = { ...cur };
    filteredRows.forEach((r) => { catKeys.forEach((k) => { cur[k] += r[k]||0; }); cur.total += activeCats.reduce((s,k) => s+(r[k]||0), 0); });
    prevFiltered.forEach((r) => { catKeys.forEach((k) => { prev[k] += r[k]||0; }); prev.total += activeCats.reduce((s,k) => s+(r[k]||0), 0); });
    const delta = (c, p) => p > 0 ? (c - p) / p * 100 : null;
    return {
      ...cur,
      dRepair:    delta(cur.repair,    prev.repair),
      dCosmetics: delta(cur.cosmetics, prev.cosmetics),
      dShoes:     delta(cur.shoes,     prev.shoes),
      dTotal:     delta(cur.total,     prev.total),
      activePeriods: allPeriodsCount,
      avgPerActive:  allPeriodsCount > 0 ? cur.total / allPeriodsCount : 0,
    };
  }, [filteredRows, prevFiltered, allPeriodsCount, activeCats]);

  const categoryLeaders = useMemo(() => {
    const leaders = {};
    CATEGORIES.forEach(({ key }) => {
      const totals = {};
      filteredRows.forEach((r) => { if ((r[key]||0) > 0) totals[r.code] = (totals[r.code]||0) + r[key]; });
      const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
      leaders[key] = sorted.length ? { code: sorted[0][0], amount: sorted[0][1] } : null;
    });
    return leaders;
  }, [filteredRows]);

  const dayData = useMemo(() => {
    const counts = Array(7).fill(0), totals = Array(7).fill(0);
    filteredRows.forEach((r) => {
      const dow = (new Date(r.date).getDay() + 6) % 7;
      totals[dow] += activeCats.reduce((s, k) => s + (r[k]||0), 0);
      counts[dow]++;
    });
    return DAY_NAMES.map((name, i) => ({ name, total: totals[i], avg: counts[i] > 0 ? totals[i]/counts[i] : 0, count: counts[i] }));
  }, [filteredRows, activeCats]);

  const donutData = useMemo(() => [
    { name: 'Ремонт / Химчистка', value: kpi.repair    || 0, color: '#6366f1' },
    { name: 'Косметика',           value: kpi.cosmetics || 0, color: '#22c55e' },
    { name: 'Обувь',               value: kpi.shoes     || 0, color: '#f59e0b' },
  ].filter((d) => d.value > 0), [kpi]);

  const periodLabel = gran === 'day' ? 'дн.' : gran === 'week' ? 'нед.' : 'мес.';

  function downloadCsv() {
    if (!filteredRows.length) return;
    const hdr  = 'Дата;Код;Имя;Ремонт/Химчистка;Косметика;Обувь;Итого';
    const body = filteredRows.map((r) => [r.date, r.code, r.description, r.repair, r.cosmetics, r.shoes||0, r.total].join(';')).join('\n');
    const blob = new Blob(['﻿' + hdr + '\n' + body], { type:'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = 'sales.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  const mainTabs = [
    { key: 'overview',   label: 'Обзор',        icon: <BarChart3 size={15} /> },
    { key: 'employees',  label: 'Сотрудники',   icon: <Users size={15} />, badge: employees.length || undefined },
    { key: 'details',    label: 'Сводная',       icon: <Target size={15} /> },
  ];

  return (
    <div className="space-y-5">
      <TopProgressBar active={loading} />

      {/* ── Header ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 size={22} className="text-[color:var(--color-primary)]" /> Аналитика продаж
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
            Выручка по сотрудникам и категориям — динамика, структура, рейтинги
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={downloadCsv} disabled={!filteredRows.length}
            className="btn btn--secondary btn--sm flex items-center gap-1.5 disabled:opacity-40">
            <Download size={14} /> CSV
          </button>
          <button onClick={load} disabled={loading}
            className="btn btn--primary btn--sm flex items-center gap-1.5">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loaded ? 'Обновить' : 'Загрузить'}
          </button>
        </div>
      </div>

      {/* ── Filters ───────────────────────────────────────── */}
      <div className="app-card p-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {[['month','Этот месяц'],['prev','Прошлый мес.'],['q','Квартал'],['year','Год']].map(([k, l]) => (
            <button key={k} onClick={() => { const [f,t] = quickRange(k); setDateFrom(f); setDateTo(t); }}
              className="px-3 py-1 rounded-full text-xs border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
              {l}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата от</label>
            <input type="date" className="input w-full" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата до</label>
            <input type="date" className="input w-full" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Группировка</label>
            <div className="flex rounded-lg border border-[color:var(--color-border)] overflow-hidden text-sm">
              {[['day','День'],['week','Нед.'],['month','Мес.']].map(([v, l]) => (
                <button key={v} onClick={() => setGran(v)}
                  className={`flex-1 py-1.5 transition-colors ${gran === v ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-muted)]'}`}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Сотрудники</label>
            <MultiSelect options={employeeOptions} selected={selectedEmployees} onChange={setSelectedEmployees} placeholder="Все сотрудники" />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Категории</label>
            <MultiSelect options={categoryOptions} selected={selectedCategories} onChange={setSelectedCategories} placeholder="Все категории" />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            [hideZero, () => setHideZero((v) => !v), hideZero ? <EyeOff size={12}/> : <Eye size={12}/>, 'Скрыть нули'],
            [showMA,   () => setShowMA((v)   => !v), null, 'MA7'],
            [showPlan, () => setShowPlan((v) => !v), null, 'Планы'],
            [chartMode !== 'area', () => setChartMode((m) => m === 'area' ? 'bar' : m === 'bar' ? 'line' : 'area'), null,
              chartMode === 'area' ? '▲ Область' : chartMode === 'bar' ? '▬ Столбцы' : '— Линии'],
          ].map(([active, fn, icon, lbl], i) => (
            <button key={i} onClick={fn}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${active
                ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'}`}>
              {icon}{lbl}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {!loaded && !loading && (
        <div className="app-card p-14 text-center">
          <BarChart3 size={44} className="mx-auto text-[color:var(--color-muted-foreground)] opacity-25 mb-3" />
          <p className="text-[color:var(--color-muted-foreground)]">Выберите период и нажмите <strong>Загрузить</strong></p>
        </div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {loaded && !loading && (
        <>
          {/* ── KPI row ─────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <KpiStat label="Итого выручка" value={fmtK(kpi.total)} delta={kpi.dTotal} accent="#6366f1"
              icon={<BarChart3 size={18} />} sub={`∅ ${fmtK(kpi.avgPerActive)} / ${periodLabel}`} />
            {CATEGORIES.map(({ key, label, color }) => {
              const leader    = categoryLeaders[key];
              const deltaKey  = `d${key.charAt(0).toUpperCase()}${key.slice(1)}`;
              return (
                <KpiStat key={key} label={label} value={fmtK(kpi[key])} delta={kpi[deltaKey]} accent={color}
                  sub={leader ? `👤 ${empName(leader.code)}` : undefined} />
              );
            })}
          </div>

          <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

          {/* ══ OVERVIEW tab ════════════════════════════════ */}
          {activeTab === 'overview' && (
            <div className="space-y-4">

              {/* Chart + Donut side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

                {chartData.length > 0 && (
                  <div className="app-card p-4 lg:col-span-2">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold">Динамика продаж</h3>
                      <span className="text-xs text-[color:var(--color-muted-foreground)]">{chartData.length} {periodLabel}</span>
                    </div>
                    <ResponsiveContainer width="100%" height={250}>
                      <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 50 }}>
                        <defs>
                          {employees.map((e, i) => (
                            <linearGradient key={e.code} id={`ag${i}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%"  stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.35} />
                              <stop offset="95%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.02} />
                            </linearGradient>
                          ))}
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#e5e7eb)" vertical={false} />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-40} textAnchor="end" height={60} interval="preserveStartEnd" />
                        <YAxis tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} tick={{ fontSize: 11 }} width={44} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip nameMap={nameMap} />} />
                        {employees.length > 1 && (
                          <Legend formatter={(code) => nameMap[code] || code} wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
                        )}
                        {employees.map((e, i) => {
                          const color = CHART_COLORS[i % CHART_COLORS.length];
                          if (chartMode === 'area')
                            return <Area key={e.code} dataKey={e.code} name={e.code} type="monotone" stroke={color} fill={`url(#ag${i})`} strokeWidth={2} dot={false} isAnimationActive={false} stackId="s" />;
                          if (chartMode === 'bar')
                            return <Bar  key={e.code} dataKey={e.code} name={e.code} fill={color} isAnimationActive={false} stackId="s" radius={i === employees.length - 1 ? [3,3,0,0] : 0} />;
                          return <Line key={e.code} dataKey={e.code} name={e.code} type="monotone" stroke={color} dot={false} strokeWidth={2} isAnimationActive={false} />;
                        })}
                        {showMA && <Line dataKey="_ma" name="_ma" type="monotone" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} legendType="none" />}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {donutData.length > 0 && (
                  <div className="app-card p-4">
                    <h3 className="font-semibold mb-1">Структура выручки</h3>
                    <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">{fmtK(kpi.total)} · {kpi.activePeriods} {periodLabel}</p>
                    <ResponsiveContainer width="100%" height={170}>
                      <PieChart>
                        <Pie data={donutData} cx="50%" cy="50%" innerRadius="45%" outerRadius="80%"
                          dataKey="value" labelLine={false} label={DonutLabel} isAnimationActive={false}
                          onClick={(entry) => toggleSet(setSelectedCategories, LABEL_TO_KEY[entry.name])}
                          cursor="pointer">
                          {donutData.map((entry, i) => (
                            <Cell key={i} fill={entry.color} opacity={selectedCategories.size && !selectedCategories.has(LABEL_TO_KEY[entry.name]) ? 0.35 : 1} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v, n) => [fmtRub(v), n]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="space-y-2 mt-1">
                      {donutData.map((d) => {
                        const pct = kpi.total > 0 ? d.value / kpi.total * 100 : 0;
                        const isActive = selectedCategories.has(LABEL_TO_KEY[d.name]);
                        return (
                          <button
                            key={d.name}
                            type="button"
                            onClick={() => toggleSet(setSelectedCategories, LABEL_TO_KEY[d.name])}
                            className={`flex items-center gap-2 text-xs w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
                          >
                            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                            <span className="flex-1 text-[color:var(--color-muted-foreground)] truncate">{d.name}</span>
                            <span className="font-semibold tabular-nums">{pct.toFixed(0)}%</span>
                            <span className="text-[color:var(--color-muted-foreground)] tabular-nums">{fmtK(d.value)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Day of week + top 3 leaders */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {dayData.some((d) => d.count > 0) && (
                  <div className="lg:col-span-2">
                    <DayHeatmap data={dayData} />
                  </div>
                )}

                {empSummary.length > 0 && (
                  <div className="app-card p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Trophy size={15} className="text-amber-500" />
                      <h3 className="font-semibold text-sm">Топ-3</h3>
                    </div>
                    <div className="space-y-3">
                      {empSummary.slice(0, 3).map((e, i) => {
                        const medals = ['🥇','🥈','🥉'];
                        const color  = CHART_COLORS[i % CHART_COLORS.length];
                        const share  = empSummary[0].total > 0 ? e.total / empSummary[0].total : 0;
                        return (
                          <div key={e.code} className="flex items-center gap-2.5">
                            <span className="text-lg leading-none">{medals[i]}</span>
                            <EmpAvatar name={empName(e.code)} color={color} size={32} />
                            <div className="flex-1 min-w-0">
                              <div className="flex justify-between text-sm font-semibold">
                                <span className="truncate">{empName(e.code)}</span>
                                <span style={{ color }}>{fmtK(e.total)}</span>
                              </div>
                              <div className="mt-1 h-1 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${share*100}%`, background: color }} />
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ══ EMPLOYEES tab ═══════════════════════════════ */}
          {activeTab === 'employees' && (
            <div className="space-y-4">
              {empSummary.length === 0 ? (
                <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
              ) : (
                <>
                  <Leaderboard empSummary={empSummary} planTotals={planTotals} activeCodes={selectedEmployees} onSelect={(code) => toggleSet(setSelectedEmployees, code)} />

                  {showPlan && <PlanGauges empSummary={empSummary} planTotals={planTotals} />}

                  {/* Stacked horizontal bar chart */}
                  <div className="app-card p-4">
                    <h3 className="font-semibold mb-3">Сравнение по категориям</h3>
                    <ResponsiveContainer width="100%" height={Math.max(180, empSummary.length * 52)}>
                      <BarChart data={empSummary.map((e) => ({ ...e, displayName: empName(e.code) }))}
                        layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#e5e7eb)" horizontal={false} />
                        <XAxis type="number" tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} tick={{ fontSize: 11 }} axisLine={false} />
                        <YAxis type="category" dataKey="displayName" tick={{ fontSize: 11 }} width={80} />
                        <Tooltip formatter={(v, n) => [fmtRub(v), n]} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        {CATEGORIES.map(({ key, label, color }) =>
                          activeCats.includes(key) && (
                            <Bar
                              key={key} dataKey={key} name={label} stackId="a" fill={color} isAnimationActive={false}
                              onClick={(entry) => toggleSet(setSelectedEmployees, entry.code)}
                              cursor="pointer"
                            />
                          )
                        )}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Employee detail table */}
                  <div className="app-card overflow-hidden">
                    <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                      <h3 className="font-semibold">Детализация</h3>
                    </div>
                    <div className="p-3">
                      <ResponsiveTable
                        data={empSummary}
                        keyFn={(e) => e.code}
                        emptyText="Нет данных"
                        columns={[
                          { label: 'Сотрудник', primary: true, render: (e) => (
                            <div className="flex items-center gap-2">
                              <EmpAvatar name={empName(e.code)} color={CHART_COLORS[empSummary.indexOf(e) % CHART_COLORS.length]} size={26} />
                              <span>{empName(e.code)}</span>
                            </div>
                          )},
                          ...CATEGORIES.map(({ key, label, color }) => ({
                            label, headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => <span style={{ color }}>{Math.round(e[key]||0).toLocaleString('ru-RU')}</span>,
                          })),
                          { label: 'Итого', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => <span className="font-bold text-[color:var(--color-primary)]">{Math.round(e.total).toLocaleString('ru-RU')}</span> },
                          ...(showPlan ? [
                            { label: 'План', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                              render: (e) => { const p = planTotals[e.code]||0; return p > 0 ? Math.round(p).toLocaleString('ru-RU') : '—'; } },
                            { label: '%', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                              render: (e) => { const p = planTotals[e.code]||0, pct = p > 0 ? e.total/p*100 : null;
                                return <span className={`font-semibold ${pct == null ? '' : pct >= 100 ? 'text-emerald-600' : pct >= 75 ? 'text-amber-500' : 'text-red-500'}`}>{fmtPct(pct)}</span>; } },
                          ] : []),
                          { label: 'Дней', key: 'activeDays', headerClass: 'text-right', cellClass: 'text-right tabular-nums' },
                          { label: 'Ср/день', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => Math.round(e.activeDays > 0 ? e.total/e.activeDays : 0).toLocaleString('ru-RU') },
                        ]}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ══ DETAILS tab ═════════════════════════════════ */}
          {activeTab === 'details' && (
            periods.length > 0 ? (
              <div className="app-card overflow-hidden">
                <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
                  <h3 className="font-semibold">Сводная таблица</h3>
                  <span className="text-sm text-[color:var(--color-muted-foreground)]">{periods.length} {periodLabel}</span>
                </div>
                <div className="p-3">
                  <ResponsiveTable
                    data={[
                      ...periods.map((key) => ({ key, isTotal: false, label: getPeriodLabel(key, gran), rowTotal: employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0) })),
                      { key: '_total', isTotal: true, label: 'Итого', rowTotal: colTotals._grand || 0 },
                    ]}
                    keyFn={(row) => row.key}
                    rowClass={(row) => row.isTotal ? 'border-t-2 border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 font-semibold' : ''}
                    emptyText="Нет данных"
                    columns={[
                      { label: 'Период', primary: true,
                        headerClass: 'sticky left-0 bg-[color:var(--color-modal-bg)]',
                        cellClass: 'sticky left-0 bg-inherit font-medium',
                        render: (row) => row.label },
                      ...employees.map((e, i) => ({
                        label: empName(e.code), headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                        render: (row) => {
                          if (row.isTotal) return <span className="font-bold" style={{ color: CHART_COLORS[i % CHART_COLORS.length] }}>{Math.round(colTotals[e.code]||0).toLocaleString('ru-RU')}</span>;
                          const v = cells[row.key]?.[e.code] || 0;
                          return <span className={v === 0 ? 'text-[color:var(--color-muted-foreground)]' : ''}>{v === 0 ? '—' : Math.round(v).toLocaleString('ru-RU')}</span>;
                        },
                      })),
                      { label: 'Итого', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                        render: (row) => <span className={`font-semibold ${row.isTotal ? 'text-[color:var(--color-primary)]' : ''}`}>{Math.round(row.rowTotal||0).toLocaleString('ru-RU')}</span> },
                    ]}
                  />
                </div>
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}
        </>
      )}
    </div>
  );
}
