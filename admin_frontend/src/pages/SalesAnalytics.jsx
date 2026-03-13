import { useState, useMemo, useRef, useEffect } from 'react';
import { RefreshCw, Download, EyeOff, Eye, ChevronDown, Check, TrendingUp, TrendingDown } from 'lucide-react';
import {
  ComposedChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Line, BarChart,
} from 'recharts';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

/* ── constants ───────────────────────────────────────────── */
const TODAY = new Date().toISOString().slice(0, 10);
const MONTHS_RU = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const MONTHS_KEY_RU = ['ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ','ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ'];
const CHART_COLORS = ['#6366f1','#22c55e','#f59e0b','#ef4444','#3b82f6','#8b5cf6','#ec4899','#14b8a6','#f97316','#a3e635'];

/* ── helpers ─────────────────────────────────────────────── */
const fmtRub  = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtPct  = (v) => v == null ? '—' : v.toFixed(1) + '%';

function getPeriodKey(dateStr, gran) {
  if (gran === 'day')   return dateStr;
  if (gran === 'month') return dateStr.slice(0, 7);
  const d = new Date(dateStr);
  const day = d.getDay() || 7;
  d.setDate(d.getDate() + 4 - day);
  const jan1 = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil((((d - jan1) / 86400000) + 1) / 7);
  return `${d.getFullYear()}-W${String(week).padStart(2, '0')}`;
}

function getPeriodLabel(key, gran) {
  if (gran === 'day') {
    const [, m, d] = key.split('-');
    return `${d}.${m}`;
  }
  if (gran === 'month') {
    const [y, m] = key.split('-');
    return `${MONTHS_RU[+m - 1]} ${y.slice(2)}`;
  }
  const [yearStr, wStr] = key.split('-W');
  const jan4 = new Date(+yearStr, 0, 4);
  const mon  = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (+wStr - 1) * 7);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  const f = (dt) => `${String(dt.getDate()).padStart(2,'0')}.${String(dt.getMonth()+1).padStart(2,'0')}`;
  return `${f(mon)}–${f(sun)}`;
}

function shortName(desc) {
  const parts = (desc || '').trim().split(/\s+/).filter((p) => !/^\d{4}$/.test(p));
  if (!parts.length) return desc;
  if (parts.length === 1) return parts[0];
  return `${parts[0]} ${parts.slice(1).map((p) => p[0] + '.').join('')}`;
}

function toMonthKey(yyyymm) {
  const [y, m] = yyyymm.split('-');
  return `${MONTHS_KEY_RU[+m - 1]}_${y}`;
}

function getMonthsInRange(from, to) {
  const months = [];
  const cur = new Date((from || TODAY).slice(0, 7) + '-01');
  const end = new Date((to   || TODAY).slice(0, 7) + '-01');
  while (cur <= end) {
    months.push(cur.toISOString().slice(0, 7));
    cur.setMonth(cur.getMonth() + 1);
  }
  return months;
}

/* ── MultiSelect ─────────────────────────────────────────── */
function MultiSelect({ options, selected, onChange, placeholder = 'Все' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const allSelected = selected.size === 0;
  const label = allSelected
    ? placeholder
    : options.filter((o) => selected.has(o.value)).map((o) => o.label).join(', ');

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="input w-full text-left flex items-center justify-between gap-2 text-sm"
      >
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute z-50 top-full mt-1 w-full min-w-[180px] rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-card)] shadow-xl overflow-hidden max-h-64 overflow-y-auto">
          <button
            type="button"
            onClick={() => onChange(new Set())}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors"
          >
            <Check size={13} className={allSelected ? 'text-[color:var(--color-primary)]' : 'opacity-0'} />
            <span>Все сотрудники</span>
          </button>
          <div className="border-t border-[color:var(--color-border)]" />
          {options.map((o) => {
            const sel = selected.has(o.value);
            return (
              <button
                key={o.value}
                type="button"
                onClick={() => {
                  const next = new Set(selected);
                  if (sel) next.delete(o.value); else next.add(o.value);
                  onChange(next.size === options.length ? new Set() : next);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors"
              >
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

/* ── KpiCard ─────────────────────────────────────────────── */
function KpiCard({ label, value, delta, sub }) {
  return (
    <div className="app-card p-4 text-center">
      <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{label}</div>
      <div className="text-lg font-semibold text-[color:var(--color-primary)] leading-tight">{value}</div>
      {delta != null && Math.abs(delta) >= 0.1 && (
        <div className={`flex items-center justify-center gap-0.5 text-xs mt-0.5 font-medium ${delta > 0 ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'}`}>
          {delta > 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
          {delta > 0 ? '+' : ''}{delta.toFixed(1)}%
        </div>
      )}
      {sub && <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">{sub}</div>}
    </div>
  );
}

/* ── Chart tooltip ───────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label, nameMap }) => {
  if (!active || !payload?.length) return null;
  const items = payload.filter((p) => p.dataKey !== '_ma');
  const ma    = payload.find((p)  => p.dataKey === '_ma');
  return (
    <div className="rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-3 text-sm shadow-lg max-w-[240px]">
      <div className="font-medium mb-1.5">{label}</div>
      {items.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 leading-5">
          <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: p.fill || p.color }} />
          <span className="text-[color:var(--color-muted-foreground)] truncate flex-1">{nameMap?.[p.dataKey] || p.name}:</span>
          <span className="font-medium tabular-nums">{Math.round(p.value || 0).toLocaleString('ru-RU')}</span>
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

/* ── main component ──────────────────────────────────────── */
export default function SalesAnalytics() {
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo,   setDateTo]   = useState(TODAY);
  const [gran,     setGran]     = useState('day');
  const [hideZero, setHideZero] = useState(false);
  const [showMA,   setShowMA]   = useState(false);
  const [showPlan, setShowPlan] = useState(false);
  const [chartMode, setChartMode] = useState('bar');
  const [selectedEmployees, setSelectedEmployees] = useState(new Set());

  const [rows,     setRows]     = useState([]);
  const [prevRows, setPrevRows] = useState([]);
  const [plans,    setPlans]    = useState({});
  const [loading,  setLoading]  = useState(false);
  const [loaded,   setLoaded]   = useState(false);
  const [error,    setError]    = useState(null);

  const months = useMemo(() => getMonthsInRange(dateFrom, dateTo), [dateFrom, dateTo]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;

      // Previous period (same duration, shifted back)
      const d0 = new Date(dateFrom || TODAY);
      const d1 = new Date(dateTo   || TODAY);
      const dur = d1 - d0;
      const prevTo   = new Date(d0); prevTo.setDate(prevTo.getDate() - 1);
      const prevFrom = new Date(+prevTo - dur);
      const prevParams = {
        date_from: prevFrom.toISOString().slice(0, 10),
        date_to:   prevTo.toISOString().slice(0, 10),
      };

      const monthKeys = months.map(toMonthKey).join(',');

      const [mainRes, prevRes, plansRes] = await Promise.all([
        api.get('/sales/daily', { params }),
        api.get('/sales/daily', { params: prevParams }),
        api.get('/sales/plans', { params: { month_keys: monthKeys } }),
      ]);

      setRows(mainRes.data);
      setPrevRows(prevRes.data);
      setPlans(plansRes.data);
      setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }

  /* all employees (for dropdown) */
  const allEmployees = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, description: r.description, total: 0 };
      map[r.code].total += r.total;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  const employeeOptions = useMemo(() =>
    allEmployees.map((e) => ({ value: e.code, label: shortName(e.description) })),
  [allEmployees]);

  /* filtered rows */
  const filteredRows = useMemo(() =>
    selectedEmployees.size ? rows.filter((r) => selectedEmployees.has(r.code)) : rows,
  [rows, selectedEmployees]);

  const prevFiltered = useMemo(() =>
    selectedEmployees.size ? prevRows.filter((r) => selectedEmployees.has(r.code)) : prevRows,
  [prevRows, selectedEmployees]);

  /* employees visible in filtered set */
  const employees = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, description: r.description, total: 0 };
      map[r.code].total += r.total;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows]);

  const nameMap = useMemo(() => {
    const m = {};
    employees.forEach((e) => { m[e.code] = shortName(e.description); });
    return m;
  }, [employees]);

  /* period grouping */
  const { periods, cells, allPeriodsCount } = useMemo(() => {
    const c = {};
    filteredRows.forEach((r) => {
      const key = getPeriodKey(r.date, gran);
      if (!c[key]) c[key] = {};
      c[key][r.code] = (c[key][r.code] || 0) + r.total;
    });
    const all = Object.keys(c).sort();
    const nonZero = all.filter((p) =>
      employees.reduce((s, e) => s + (c[p]?.[e.code] || 0), 0) > 0
    );
    return { periods: hideZero ? nonZero : all, cells: c, allPeriodsCount: all.length };
  }, [filteredRows, gran, hideZero, employees]);

  /* chart data with 7-period trailing MA */
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

  /* employee summary */
  const empSummary = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => {
      if (!map[r.code]) map[r.code] = {
        code: r.code, name: r.description,
        repair: 0, cosmetics: 0, shoes: 0, total: 0, activeDays: 0,
      };
      map[r.code].repair    += r.repair;
      map[r.code].cosmetics += r.cosmetics;
      map[r.code].shoes     += (r.shoes || 0);
      map[r.code].total     += r.total;
      if (r.total > 0) map[r.code].activeDays++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows]);

  /* plan totals per employee for the selected date range */
  const planTotals = useMemo(() => {
    const result = {};
    allEmployees.forEach((e) => {
      result[e.code] = months.reduce((sum, ym) => {
        const p = plans?.[toMonthKey(ym)]?.[e.code];
        return p ? sum + (p.repair_plan || 0) + (p.cosmetics_plan || 0) + (p.shoes_plan || 0) : sum;
      }, 0);
    });
    return result;
  }, [months, plans, allEmployees]);

  /* pivot column totals */
  const colTotals = useMemo(() => {
    const t = {};
    employees.forEach((e) => {
      t[e.code] = periods.reduce((s, p) => s + (cells[p]?.[e.code] || 0), 0);
    });
    t._grand = employees.reduce((s, e) => s + (t[e.code] || 0), 0);
    return t;
  }, [periods, employees, cells]);

  /* KPI with delta vs previous period */
  const kpi = useMemo(() => {
    const cur  = { repair: 0, cosmetics: 0, shoes: 0, total: 0 };
    const prev = { repair: 0, cosmetics: 0, shoes: 0, total: 0 };
    filteredRows.forEach((r) => { cur.repair += r.repair; cur.cosmetics += r.cosmetics; cur.shoes += (r.shoes||0); cur.total += r.total; });
    prevFiltered.forEach((r) => { prev.repair += r.repair; prev.cosmetics += r.cosmetics; prev.shoes += (r.shoes||0); prev.total += r.total; });
    const delta = (c, p) => p > 0 ? (c - p) / p * 100 : null;
    const avgPerActive = allPeriodsCount > 0 ? cur.total / allPeriodsCount : 0;
    return {
      repair: cur.repair, cosmetics: cur.cosmetics, shoes: cur.shoes, total: cur.total,
      dRepair: delta(cur.repair, prev.repair),
      dCosmetics: delta(cur.cosmetics, prev.cosmetics),
      dShoes: delta(cur.shoes, prev.shoes),
      dTotal: delta(cur.total, prev.total),
      activePeriods: allPeriodsCount,
      avgPerActive,
    };
  }, [filteredRows, prevFiltered, allPeriodsCount]);

  const periodLabel = gran === 'day' ? 'дн.' : gran === 'week' ? 'нед.' : 'мес.';

  function downloadCsv() {
    if (!filteredRows.length) return;
    const hdr = 'Дата;Код;Имя;Ремонт;Косметика;Обувь;Итого';
    const body = filteredRows.map((r) =>
      [r.date, r.code, r.description, r.repair, r.cosmetics, r.shoes || 0, r.total].join(';')
    ).join('\n');
    const blob = new Blob(['\uFEFF' + hdr + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'sales.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Аналитика продаж</h2>
        <div className="flex gap-2">
          <button onClick={downloadCsv} disabled={!filteredRows.length}
            className="btn btn-outline flex items-center gap-1.5 disabled:opacity-40">
            <Download size={15} /> CSV
          </button>
          <button onClick={load} disabled={loading}
            className="btn btn-primary flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            {loaded ? 'Обновить' : 'Загрузить'}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="app-card p-4 space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата от</label>
            <input type="date" className="input w-full" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата до</label>
            <input type="date" className="input w-full" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Группировка</label>
            <div className="flex rounded-lg border border-[color:var(--color-border)] overflow-hidden text-sm">
              {[['day','День'],['week','Нед.'],['month','Мес.']].map(([v, l]) => (
                <button key={v} onClick={() => setGran(v)}
                  className={`flex-1 py-1.5 transition-colors ${gran === v
                    ? 'bg-[color:var(--color-primary)] text-[color:var(--color-primary-foreground)]'
                    : 'hover:bg-[color:var(--color-muted)]'}`}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Сотрудники</label>
            <MultiSelect
              options={employeeOptions}
              selected={selectedEmployees}
              onChange={setSelectedEmployees}
              placeholder="Все сотрудники"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            [hideZero, () => setHideZero((v) => !v), hideZero ? <EyeOff size={13}/> : <Eye size={13}/>, 'Скрыть нули'],
            [showMA,   () => setShowMA((v) => !v),   null, 'MA7'],
            [showPlan, () => setShowPlan((v) => !v), null, 'План'],
            [chartMode === 'line', () => setChartMode((m) => m === 'bar' ? 'line' : 'bar'), null, chartMode === 'bar' ? 'Столбцы' : 'Линии'],
          ].map(([active, fn, icon, lbl], i) => (
            <button key={i} onClick={fn}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors ${active
                ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'}`}>
              {icon}{lbl}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {!loaded && !loading && (
        <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">
          Выберите период и нажмите <strong>Загрузить</strong>
        </div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {loaded && !loading && (
        <>
          {/* KPI — 6 cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <KpiCard label="Ремонт"     value={fmtRub(kpi.repair)}     delta={kpi.dRepair} />
            <KpiCard label="Косметика"  value={fmtRub(kpi.cosmetics)}  delta={kpi.dCosmetics} />
            <KpiCard label="Обувь"      value={fmtRub(kpi.shoes)}      delta={kpi.dShoes} />
            <KpiCard label="Итого"      value={fmtRub(kpi.total)}      delta={kpi.dTotal} />
            <KpiCard label={`Периодов с данными`} value={kpi.activePeriods}
              sub={`${periodLabel} за период`} />
            <KpiCard label={`Среднее / ${periodLabel}`} value={fmtRub(kpi.avgPerActive)} />
          </div>

          {/* Timeline chart */}
          {chartData.length > 0 && (
            <div className="app-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold">Продажи по периодам</h3>
                <span className="text-xs text-[color:var(--color-muted-foreground)]">{chartData.length} периодов</span>
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 50 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-45} textAnchor="end" height={60} interval="preserveStartEnd" />
                  <YAxis tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} tick={{ fontSize: 11 }} width={48} />
                  <Tooltip content={<ChartTooltip nameMap={nameMap} />} />
                  <Legend formatter={(code) => nameMap[code] || code} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
                  {employees.map((e, i) =>
                    chartMode === 'bar'
                      ? <Bar  key={e.code} dataKey={e.code} name={e.code} stackId="s" fill={CHART_COLORS[i % CHART_COLORS.length]} isAnimationActive={false} />
                      : <Line key={e.code} dataKey={e.code} name={e.code} type="monotone" stroke={CHART_COLORS[i % CHART_COLORS.length]} dot={false} strokeWidth={2} isAnimationActive={false} />
                  )}
                  {showMA && (
                    <Line dataKey="_ma" name="_ma" type="monotone" stroke="#94a3b8" strokeWidth={2}
                      strokeDasharray="5 3" dot={false} isAnimationActive={false} legendType="none" />
                  )}
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Employee comparison */}
          {empSummary.length > 0 && (
            <div className="app-card p-4">
              <h3 className="font-semibold mb-3">Сравнение сотрудников</h3>
              <ResponsiveContainer width="100%" height={Math.max(160, empSummary.length * 52)}>
                <BarChart data={empSummary} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border, #e5e7eb)" />
                  <XAxis type="number" tickFormatter={(v) => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} tickFormatter={shortName} width={110} />
                  <Tooltip formatter={(v, n) => [Math.round(v).toLocaleString('ru-RU') + ' ₽', n]} labelFormatter={shortName} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="repair"    name="Ремонт"    stackId="a" fill="#6366f1" isAnimationActive={false} />
                  <Bar dataKey="cosmetics" name="Косметика" stackId="a" fill="#22c55e" isAnimationActive={false} />
                  <Bar dataKey="shoes"     name="Обувь"     stackId="a" fill="#f59e0b" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Employee summary table */}
          {empSummary.length > 0 && (
            <div className="app-card">
              <div className="p-4 border-b border-[color:var(--color-border)]">
                <h3 className="font-semibold">Итоги по сотрудникам</h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm min-w-[520px]">
                  <thead>
                    <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] text-xs uppercase tracking-wide">
                      <th className="px-4 py-3 text-left">Сотрудник</th>
                      <th className="px-3 py-3 text-right">Ремонт</th>
                      <th className="px-3 py-3 text-right">Косметика</th>
                      <th className="px-3 py-3 text-right">Обувь</th>
                      <th className="px-3 py-3 text-right">Итого</th>
                      {showPlan && <th className="px-3 py-3 text-right">План</th>}
                      {showPlan && <th className="px-3 py-3 text-right">%</th>}
                      <th className="px-3 py-3 text-right">Дней</th>
                      <th className="px-3 py-3 text-right">Ср/день</th>
                    </tr>
                  </thead>
                  <tbody>
                    {empSummary.map((e, i) => {
                      const plan   = planTotals[e.code] || 0;
                      const pct    = plan > 0 ? e.total / plan * 100 : null;
                      const avgDay = e.activeDays > 0 ? e.total / e.activeDays : 0;
                      return (
                        <tr key={e.code} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}>
                          <td className="px-4 py-2 font-medium">{shortName(e.name)}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{Math.round(e.repair).toLocaleString('ru-RU')}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{Math.round(e.cosmetics).toLocaleString('ru-RU')}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{Math.round(e.shoes).toLocaleString('ru-RU')}</td>
                          <td className="px-3 py-2 text-right font-medium tabular-nums">{Math.round(e.total).toLocaleString('ru-RU')}</td>
                          {showPlan && (
                            <td className="px-3 py-2 text-right tabular-nums text-[color:var(--color-muted-foreground)]">
                              {plan > 0 ? Math.round(plan).toLocaleString('ru-RU') : '—'}
                            </td>
                          )}
                          {showPlan && (
                            <td className={`px-3 py-2 text-right tabular-nums font-medium ${pct == null ? '' : pct >= 100 ? 'text-green-600' : pct >= 75 ? 'text-yellow-600' : 'text-red-500'}`}>
                              {fmtPct(pct)}
                            </td>
                          )}
                          <td className="px-3 py-2 text-right tabular-nums text-[color:var(--color-muted-foreground)]">{e.activeDays}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{Math.round(avgDay).toLocaleString('ru-RU')}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Pivot table */}
          {periods.length > 0 && (
            <div className="app-card">
              <div className="p-4 border-b border-[color:var(--color-border)] flex items-center justify-between">
                <h3 className="font-semibold">Сводная таблица</h3>
                <span className="text-sm text-[color:var(--color-muted-foreground)]">{periods.length} строк</span>
              </div>

              {/* Desktop */}
              <div className="hidden sm:block overflow-x-auto">
                <table className="w-full text-sm" style={{ minWidth: `${Math.max(400, 120 + employees.length * 110)}px` }}>
                  <thead>
                    <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] text-xs uppercase tracking-wide">
                      <th className="px-4 py-3 text-left sticky left-0 bg-[color:var(--color-card)]">Период</th>
                      {employees.map((e) => (
                        <th key={e.code} className="px-3 py-3 text-right">{shortName(e.description)}</th>
                      ))}
                      <th className="px-3 py-3 text-right font-semibold">Итого</th>
                    </tr>
                  </thead>
                  <tbody>
                    {periods.map((key, i) => {
                      const rowTotal = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
                      return (
                        <tr key={key} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}>
                          <td className="px-4 py-2 font-medium sticky left-0 bg-inherit">{getPeriodLabel(key, gran)}</td>
                          {employees.map((e) => {
                            const v = cells[key]?.[e.code] || 0;
                            return (
                              <td key={e.code} className={`px-3 py-2 text-right tabular-nums ${v === 0 ? 'text-[color:var(--color-muted-foreground)]' : ''}`}>
                                {v === 0 ? '—' : Math.round(v).toLocaleString('ru-RU')}
                              </td>
                            );
                          })}
                          <td className="px-3 py-2 text-right font-medium tabular-nums">{Math.round(rowTotal).toLocaleString('ru-RU')}</td>
                        </tr>
                      );
                    })}
                    <tr className="border-t-2 border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 font-semibold">
                      <td className="px-4 py-2 sticky left-0 bg-inherit">Итого</td>
                      {employees.map((e) => (
                        <td key={e.code} className="px-3 py-2 text-right tabular-nums text-[color:var(--color-primary)]">
                          {Math.round(colTotals[e.code] || 0).toLocaleString('ru-RU')}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-right tabular-nums text-[color:var(--color-primary)]">
                        {Math.round(colTotals._grand || 0).toLocaleString('ru-RU')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Mobile cards */}
              <div className="sm:hidden divide-y divide-[color:var(--color-border)]">
                {periods.map((key) => {
                  const rowTotal = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
                  const active   = employees.filter((e) => (cells[key]?.[e.code] || 0) > 0);
                  return (
                    <div key={key} className="p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm">{getPeriodLabel(key, gran)}</span>
                        <span className="font-semibold text-[color:var(--color-primary)] text-sm tabular-nums">
                          {Math.round(rowTotal).toLocaleString('ru-RU')} ₽
                        </span>
                      </div>
                      {active.length > 0 && (
                        <div className="space-y-0.5">
                          {active.map((e) => (
                            <div key={e.code} className="flex items-center justify-between text-xs text-[color:var(--color-muted-foreground)]">
                              <span>{shortName(e.description)}</span>
                              <span className="tabular-nums">{Math.round(cells[key][e.code]).toLocaleString('ru-RU')} ₽</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                <div className="p-3 bg-[color:var(--color-muted)]/30 font-semibold">
                  <div className="flex items-center justify-between text-sm">
                    <span>Итого</span>
                    <span className="text-[color:var(--color-primary)] tabular-nums">
                      {Math.round(colTotals._grand || 0).toLocaleString('ru-RU')} ₽
                    </span>
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {employees.map((e) => (colTotals[e.code] || 0) > 0 && (
                      <div key={e.code} className="flex items-center justify-between text-xs text-[color:var(--color-muted-foreground)]">
                        <span>{shortName(e.description)}</span>
                        <span className="tabular-nums">{Math.round(colTotals[e.code]).toLocaleString('ru-RU')} ₽</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {rows.length === 0 && (
            <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">
              Нет данных за выбранный период
            </div>
          )}
        </>
      )}
    </div>
  );
}
