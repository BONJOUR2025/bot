import { useState, useMemo } from 'react';
import { RefreshCw, Download, EyeOff, Eye } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, LineChart, Line,
} from 'recharts';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

/* ── helpers ─────────────────────────────────────────────── */
const fmtRub = (v) => (v == null ? '—' : v.toLocaleString('ru-RU') + ' ₽');
const MONTHS_RU = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];

function getPeriodKey(dateStr, gran) {
  if (gran === 'day') return dateStr;
  if (gran === 'month') return dateStr.slice(0, 7);
  // ISO week
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
  // week → Mon–Sun
  const [yearStr, wStr] = key.split('-W');
  const year = +yearStr;
  const week = +wStr;
  const jan4 = new Date(year, 0, 4);
  const mon = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (week - 1) * 7);
  const sun = new Date(mon);
  sun.setDate(mon.getDate() + 6);
  const f = (dt) => `${String(dt.getDate()).padStart(2,'0')}.${String(dt.getMonth()+1).padStart(2,'0')}`;
  return `${f(mon)}–${f(sun)}`;
}

function shortName(desc) {
  const parts = (desc || '').trim().split(/\s+/).filter((p) => !/^\d{4}$/.test(p));
  if (!parts.length) return desc;
  if (parts.length === 1) return parts[0];
  return `${parts[0]} ${parts.slice(1).map((p) => p[0] + '.').join('')}`;
}

const CHART_COLORS = [
  '#6366f1','#22c55e','#f59e0b','#ef4444','#3b82f6',
  '#8b5cf6','#ec4899','#14b8a6','#f97316','#a3e635',
];

function KpiCard({ label, value, sub }) {
  return (
    <div className="app-card p-4 text-center">
      <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{label}</div>
      <div className="text-xl font-semibold text-[color:var(--color-primary)]">{value}</div>
      {sub && <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">{sub}</div>}
    </div>
  );
}

const CustomTooltip = ({ active, payload, label, nameMap }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-card)] p-3 text-sm shadow-lg">
      <div className="font-medium mb-1">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="inline-block w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: p.fill || p.color }} />
          <span className="text-[color:var(--color-muted-foreground)]">{nameMap?.[p.dataKey] || p.name}:</span>
          <span className="font-medium">{(p.value || 0).toLocaleString('ru-RU')} ₽</span>
        </div>
      ))}
    </div>
  );
};

/* ── main component ──────────────────────────────────────── */
export default function SalesAnalytics() {
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo]     = useState(today);
  const [gran, setGran]         = useState('day');   // day | week | month
  const [hideZero, setHideZero] = useState(false);
  const [chartMode, setChartMode] = useState('bar'); // bar | line
  const [rows, setRows]   = useState([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded]   = useState(false);
  const [error, setError]     = useState(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('/sales/daily', { params });
      setRows(res.data);
      setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }

  /* employees list sorted by total desc */
  const employees = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, description: r.description, total: 0 };
      map[r.code].total += r.total;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  /* code → short name map for charts */
  const nameMap = useMemo(() => {
    const m = {};
    employees.forEach((e) => { m[e.code] = shortName(e.description); });
    return m;
  }, [employees]);

  /* period → code → total (used for chart + pivot table) */
  const { periods, cells } = useMemo(() => {
    const cellsMap = {};
    rows.forEach((r) => {
      const key = getPeriodKey(r.date, gran);
      if (!cellsMap[key]) cellsMap[key] = {};
      cellsMap[key][r.code] = (cellsMap[key][r.code] || 0) + r.total;
    });
    let ps = Object.keys(cellsMap).sort();
    if (hideZero) {
      ps = ps.filter((p) => employees.reduce((s, e) => s + (cellsMap[p]?.[e.code] || 0), 0) > 0);
    }
    return { periods: ps, cells: cellsMap };
  }, [rows, gran, hideZero, employees]);

  /* chart data: [{label, code1: val, code2: val, ...}] */
  const chartData = useMemo(() =>
    periods.map((key) => {
      const entry = { period: key, label: getPeriodLabel(key, gran) };
      employees.forEach((e) => { entry[e.code] = cells[key]?.[e.code] || 0; });
      entry._total = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
      return entry;
    }),
  [periods, employees, cells, gran]);

  /* employee summary (horizontal bar) */
  const empSummary = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, name: r.description, repair: 0, cosmetics: 0, total: 0 };
      map[r.code].repair    += r.repair;
      map[r.code].cosmetics += r.cosmetics;
      map[r.code].total     += r.total;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  /* KPI */
  const kpi = useMemo(() => ({
    repair:    rows.reduce((s, r) => s + r.repair, 0),
    cosmetics: rows.reduce((s, r) => s + r.cosmetics, 0),
    total:     rows.reduce((s, r) => s + r.total, 0),
    top:       empSummary[0] ? shortName(empSummary[0].name) : '—',
    topVal:    empSummary[0]?.total ?? 0,
  }), [rows, empSummary]);

  /* CSV export (flat) */
  function downloadCsv() {
    if (!rows.length) return;
    const header = 'Дата;Код;Имя;Ремонт;Косметика;Итого';
    const body = rows.map((r) =>
      [r.date, r.code, r.description, r.repair, r.cosmetics, r.total].join(';')
    ).join('\n');
    const blob = new Blob(['\uFEFF' + header + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'sales_analytics.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  /* pivot table column totals */
  const colTotals = useMemo(() => {
    const t = {};
    employees.forEach((e) => {
      t[e.code] = periods.reduce((s, p) => s + (cells[p]?.[e.code] || 0), 0);
    });
    t._grand = employees.reduce((s, e) => s + (t[e.code] || 0), 0);
    return t;
  }, [periods, employees, cells]);

  const ChartComponent = chartMode === 'bar' ? BarChart : LineChart;
  const SeriesComponent = chartMode === 'bar' ? Bar : Line;
  const seriesProps = (code, color, i) =>
    chartMode === 'bar'
      ? { key: code, dataKey: code, stackId: 's', fill: color, isAnimationActive: false }
      : { key: code, dataKey: code, type: 'monotone', stroke: color, dot: false, strokeWidth: 2, isAnimationActive: false };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Аналитика продаж</h2>
        <div className="flex gap-2">
          <button onClick={downloadCsv} disabled={!rows.length}
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
              {[['day','День'],['week','Неделя'],['month','Месяц']].map(([v, l]) => (
                <button
                  key={v}
                  onClick={() => setGran(v)}
                  className={`flex-1 py-1.5 transition-colors ${gran === v
                    ? 'bg-[color:var(--color-primary)] text-[color:var(--color-primary-foreground)]'
                    : 'hover:bg-[color:var(--color-muted)]'}`}
                >{l}</button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Опции</label>
            <div className="flex gap-2">
              <button
                onClick={() => setHideZero((v) => !v)}
                className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm transition-colors flex-1 justify-center ${hideZero
                  ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                  : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'}`}
              >
                {hideZero ? <EyeOff size={14} /> : <Eye size={14} />}
                Нули
              </button>
              <button
                onClick={() => setChartMode((m) => m === 'bar' ? 'line' : 'bar')}
                className="rounded-lg border border-[color:var(--color-border)] px-3 py-1.5 text-sm hover:bg-[color:var(--color-muted)] transition-colors flex-1"
              >
                {chartMode === 'bar' ? 'Бар' : 'Линия'}
              </button>
            </div>
          </div>
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
          {/* KPI */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <KpiCard label="Ремонт" value={fmtRub(kpi.repair)} />
            <KpiCard label="Косметика" value={fmtRub(kpi.cosmetics)} />
            <KpiCard label="Итого" value={fmtRub(kpi.total)} />
            <KpiCard label="Лидер" value={kpi.top} sub={fmtRub(kpi.topVal)} />
          </div>

          {/* Timeline chart */}
          {chartData.length > 0 && (
            <div className="app-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold">Продажи по периодам</h3>
                <span className="text-xs text-[color:var(--color-muted-foreground)]">{chartData.length} периодов</span>
              </div>
              <ResponsiveContainer width="100%" height={300}>
                <ChartComponent data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 50 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    dataKey="label"
                    tick={{ fontSize: 11 }}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
                    tick={{ fontSize: 11 }}
                    width={48}
                  />
                  <Tooltip content={<CustomTooltip nameMap={nameMap} />} />
                  <Legend
                    formatter={(code) => nameMap[code] || code}
                    wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                  />
                  {employees.map((e, i) => {
                    const color = CHART_COLORS[i % CHART_COLORS.length];
                    const props = seriesProps(e.code, color, i);
                    return <SeriesComponent {...props} name={e.code} />;
                  })}
                </ChartComponent>
              </ResponsiveContainer>
            </div>
          )}

          {/* Employee comparison chart */}
          {empSummary.length > 0 && (
            <div className="app-card p-4">
              <h3 className="font-semibold mb-3">Сравнение сотрудников</h3>
              <ResponsiveContainer width="100%" height={Math.max(180, empSummary.length * 52)}>
                <BarChart
                  data={empSummary}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis
                    type="number"
                    tickFormatter={(v) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : v}
                    tick={{ fontSize: 11 }}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ fontSize: 11 }}
                    tickFormatter={shortName}
                    width={110}
                  />
                  <Tooltip
                    formatter={(v, name) => [v.toLocaleString('ru-RU') + ' ₽', name]}
                    labelFormatter={shortName}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="repair"    name="Ремонт"    stackId="a" fill="#6366f1" isAnimationActive={false} />
                  <Bar dataKey="cosmetics" name="Косметика" stackId="a" fill="#22c55e" isAnimationActive={false} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Pivot table: periods × employees */}
          {periods.length > 0 && (
            <div className="app-card">
              <div className="p-4 border-b border-[color:var(--color-border)] flex items-center justify-between">
                <h3 className="font-semibold">Сводная таблица</h3>
                <span className="text-sm text-[color:var(--color-muted-foreground)]">{periods.length} строк</span>
              </div>

              {/* Desktop table */}
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
                                {v === 0 ? '—' : v.toLocaleString('ru-RU')}
                              </td>
                            );
                          })}
                          <td className="px-3 py-2 text-right font-medium tabular-nums">
                            {rowTotal.toLocaleString('ru-RU')}
                          </td>
                        </tr>
                      );
                    })}
                    <tr className="border-t-2 border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 font-semibold">
                      <td className="px-4 py-2 sticky left-0 bg-inherit">Итого</td>
                      {employees.map((e) => (
                        <td key={e.code} className="px-3 py-2 text-right tabular-nums text-[color:var(--color-primary)]">
                          {(colTotals[e.code] || 0).toLocaleString('ru-RU')}
                        </td>
                      ))}
                      <td className="px-3 py-2 text-right tabular-nums text-[color:var(--color-primary)]">
                        {(colTotals._grand || 0).toLocaleString('ru-RU')}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Mobile cards */}
              <div className="sm:hidden divide-y divide-[color:var(--color-border)]">
                {periods.map((key) => {
                  const rowTotal = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
                  const active = employees.filter((e) => (cells[key]?.[e.code] || 0) > 0);
                  return (
                    <div key={key} className="p-3 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-sm">{getPeriodLabel(key, gran)}</span>
                        <span className="font-semibold text-[color:var(--color-primary)] text-sm tabular-nums">
                          {rowTotal.toLocaleString('ru-RU')} ₽
                        </span>
                      </div>
                      {active.length > 0 && (
                        <div className="space-y-0.5">
                          {active.map((e) => (
                            <div key={e.code} className="flex items-center justify-between text-xs text-[color:var(--color-muted-foreground)]">
                              <span>{shortName(e.description)}</span>
                              <span className="tabular-nums">{(cells[key][e.code]).toLocaleString('ru-RU')} ₽</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
                {/* Mobile totals */}
                <div className="p-3 bg-[color:var(--color-muted)]/30 font-semibold">
                  <div className="flex items-center justify-between text-sm">
                    <span>Итого</span>
                    <span className="text-[color:var(--color-primary)] tabular-nums">
                      {(colTotals._grand || 0).toLocaleString('ru-RU')} ₽
                    </span>
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {employees.map((e) => (colTotals[e.code] || 0) > 0 && (
                      <div key={e.code} className="flex items-center justify-between text-xs text-[color:var(--color-muted-foreground)]">
                        <span>{shortName(e.description)}</span>
                        <span className="tabular-nums">{(colTotals[e.code]).toLocaleString('ru-RU')} ₽</span>
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
