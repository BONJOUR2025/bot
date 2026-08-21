import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Wallet, RefreshCw, Image as ImageIcon, BarChart3, Building2, ArrowUpDown,
  SlidersHorizontal, TrendingUp, Tag, X, Check,
} from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import { toPng } from 'html-to-image';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';

const REPORT_WIDTH = 1080;
const HIDDEN_CATS_KEY = 'cashSummary.hiddenCategories';
const NO_CATEGORY = '__NONE__';
const NO_CATEGORY_LABEL = 'Без категории';

const CHART_COLORS = ['var(--color-primary)', 'var(--color-success)', 'var(--color-warning)', 'var(--color-danger)', 'var(--color-text-muted)', 'var(--color-info)', 'var(--color-warning)', 'var(--color-danger)'];
const DAY_NAMES = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

// Same scale-to-fit trick as PayrollSummary: the report DOM stays at full
// 1080px (so html-to-image captures it pixel-perfect), the wrapper just
// visually shrinks it to fit the viewport.
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

const fmtMoney = (v) => `${Math.round(Number(v) || 0).toLocaleString('ru-RU')} ₽`;
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);

const isoToday = () => new Date().toISOString().slice(0, 10);
const isoMStart = (offset = 0) => { const d = new Date(); d.setMonth(d.getMonth() + offset, 1); return d.toISOString().slice(0, 10); };
const isoMEnd = (offset = 0) => { const d = new Date(); d.setMonth(d.getMonth() + offset + 1, 0); return d.toISOString().slice(0, 10); };
const isoYStart = () => `${new Date().getFullYear()}-01-01`;

const DATE_PRESETS = [
  { key: 'this-month', label: 'Этот месяц', from: () => isoMStart(0), to: () => isoToday() },
  { key: 'last-month', label: 'Прошлый месяц', from: () => isoMStart(-1), to: () => isoMEnd(-1) },
  { key: 'this-year', label: 'Этот год', from: () => isoYStart(), to: () => isoToday() },
  { key: 'all', label: 'Всё время', from: () => '', to: () => '' },
];

// Light theme for PNG export; dark theme mirrors the app's own tokens on-screen.
const LIGHT = { bg: '#ffffff', bg2: '#f8fafc', bg3: '#f1f5f9', ink: '#0f172a', muted: '#64748b', line: '#e2e8f0' };
const DARK = {
  bg: 'var(--color-surface)', bg2: 'var(--color-table-header-bg)', bg3: 'var(--color-control-bg)',
  ink: 'var(--color-text)', muted: 'var(--color-text-muted)', line: 'var(--color-border)',
};
const BRAND = 'var(--color-primary)';
const RTC = createContext(DARK);

function loadHiddenCats() {
  try {
    const raw = localStorage.getItem(HIDDEN_CATS_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}
function saveHiddenCats(set) {
  try { localStorage.setItem(HIDDEN_CATS_KEY, JSON.stringify([...set])); } catch { /* noop */ }
}

// ── Report pieces (theme via RTC context) ────────────────────────────────────

function KpiCard({ icon: Icon, label, value, sub, color }) {
  const T = useContext(RTC);
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: T.line, background: T.bg2 }}>
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: T.muted }}>
        {Icon && <Icon size={13} />}{label}
      </div>
      <div className="mt-1.5 text-[26px] font-bold leading-none tabular-nums" style={{ color: color || T.ink }}>{value}</div>
      {sub && <div className="mt-1.5 text-xs" style={{ color: T.muted }}>{sub}</div>}
    </div>
  );
}

function Section({ title, hint, icon: Icon, children }) {
  const T = useContext(RTC);
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <div className="h-4 w-1 rounded" style={{ background: BRAND }} />
        <h3 className="text-sm font-bold uppercase tracking-wide flex items-center gap-1.5" style={{ color: T.ink }}>
          {Icon && <Icon size={13} />}{title}
        </h3>
        {hint && <span className="text-xs" style={{ color: T.muted }}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

function CatDonut({ data, total }) {
  const T = useContext(RTC);
  if (!data.length) return <div className="text-sm py-8 text-center" style={{ color: T.muted }}>Нет данных</div>;
  return (
    <div className="flex flex-col sm:flex-row gap-5 items-center">
      <div style={{ width: 190, height: 190, flexShrink: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={data} dataKey="sum" nameKey="name" innerRadius={62} outerRadius={92} paddingAngle={data.length > 1 ? 2 : 0} stroke="none" isAnimationActive={false}>
              {data.map((d, i) => <Cell key={d.name} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex-1 space-y-2.5 min-w-0 w-full">
        {data.map((d, i) => (
          <div key={d.name} className="flex items-center gap-2.5">
            <span className="h-3 w-3 rounded-sm shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
            <span className="text-sm flex-1 truncate" style={{ color: T.ink }}>{d.name}</span>
            <span className="text-sm font-semibold tabular-nums shrink-0" style={{ color: T.ink }}>{fmtMoney(d.sum)}</span>
            <span className="w-10 text-right text-xs tabular-nums shrink-0" style={{ color: T.muted }}>{pct(d.sum, total)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function BarRow({ label, value, max, color, right }) {
  const T = useContext(RTC);
  const w = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-36 shrink-0 text-sm truncate" style={{ color: T.ink }}>{label}</div>
      <div className="flex-1 h-6 rounded-md overflow-hidden" style={{ background: T.bg3 }}>
        <div className="h-6 rounded-md" style={{ width: `${w}%`, background: color, minWidth: value > 0 ? 6 : 0 }} />
      </div>
      <div className="w-28 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color: T.ink }}>{right}</div>
    </div>
  );
}

// ── Detailed loading progress panel ───────────────────────────────────────────

function LoadingPanel() {
  return (
    <div className="app-card p-8 flex items-center gap-4">
      <div className="w-12 h-12 rounded-full flex items-center justify-center shrink-0" style={{ background: 'var(--color-primary-muted)' }}>
        <RefreshCw size={20} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
      </div>
      <div>
        <div className="text-base font-semibold text-[color:var(--color-text)]">Считаю кассовые перемещения…</div>
        <div className="text-sm text-[color:var(--color-text-muted)] mt-0.5">Загружаю записи и категории за период</div>
      </div>
    </div>
  );
}

// ── Category visibility settings (screen-only chrome, not part of the PNG) ──

function CategorySettings({ categories, hasUncategorized, hidden, onToggle, onShowAll, onHideAll, onClose }) {
  const allNames = [...categories.map((c) => c.name), ...(hasUncategorized ? [NO_CATEGORY] : [])];
  return (
    <div className="app-card p-5 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold flex items-center gap-2">
          <SlidersHorizontal size={15} className="text-[color:var(--color-primary)]" />
          Какие категории показывать в отчёте
        </div>
        <button className="icon-button icon-button--ghost" onClick={onClose} aria-label="Закрыть"><X size={16} /></button>
      </div>
      <div className="flex gap-2 text-xs">
        <button className="btn btn--secondary btn--sm" onClick={onShowAll}>Показать все</button>
        <button className="btn btn--secondary btn--sm" onClick={onHideAll}>Скрыть все</button>
      </div>
      <div className="flex flex-wrap gap-2">
        {allNames.map((name) => {
          const isHidden = hidden.has(name);
          const label = name === NO_CATEGORY ? NO_CATEGORY_LABEL : name;
          return (
            <button
              key={name}
              type="button"
              onClick={() => onToggle(name)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                isHidden
                  ? 'border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] bg-[color:var(--color-bg-secondary)]'
                  : 'border-[color:var(--color-primary)] text-[color:var(--color-primary)] bg-[color:var(--color-primary-muted)]'
              }`}
            >
              {isHidden ? <X size={12} /> : <Check size={12} />}
              {label}
            </button>
          );
        })}
        {allNames.length === 0 && (
          <span className="text-xs text-[color:var(--color-muted-foreground)]">Категорий пока нет — они появятся после загрузки данных.</span>
        )}
      </div>
      <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Настройка сохраняется в браузере и применяется ко всем расчётам отчёта — скрытые категории полностью исключаются из сумм и графиков.</div>
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-xl p-3 text-sm">
      <div className="font-semibold mb-1 text-[color:var(--color-muted-foreground)]">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.stroke || p.fill }} />
          <span>{fmtMoney(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function CashSummary() {
  const { toast } = useToast();
  const [dateFrom, setDateFrom] = useState(isoMStart(0));
  const [dateTo, setDateTo] = useState(isoToday());
  const [activePreset, setActivePreset] = useState('this-month');
  const [rows, setRows] = useState(null);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pnging, setPnging] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [hidden, setHidden] = useState(loadHiddenCats);
  const [generatedAt, setGeneratedAt] = useState('');
  const reportRef = useRef(null);

  const T = exporting ? LIGHT : DARK;
  const periodLabel = activePreset === 'all' ? 'за всё время' : `${dateFrom || '…'} – ${dateTo || '…'}`;

  const load = useCallback(async (from = dateFrom, to = dateTo) => {
    setLoading(true);
    try {
      const params = {};
      if (from) params.date_from = from;
      if (to) params.date_to = to;
      const [movesRes, metaRes] = await Promise.all([
        api.get('cash-moves/', { params }),
        api.get('cash-moves/meta'),
      ]);
      setRows(Array.isArray(movesRes.data) ? movesRes.data : []);
      setCategories(metaRes.data?.categories || []);
      setGeneratedAt(new Date().toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
    } catch {
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }, [dateFrom, dateTo, toast]);

  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { saveHiddenCats(hidden); }, [hidden]);

  function applyPreset(p) {
    setActivePreset(p.key);
    const from = p.from(), to = p.to();
    setDateFrom(from); setDateTo(to);
    load(from, to);
  }

  function applyCustomRange() {
    setActivePreset('custom');
    load(dateFrom, dateTo);
  }

  function toggleCategory(name) {
    setHidden((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });
  }

  const hasUncategorized = useMemo(() => (rows || []).some((r) => !r.category), [rows]);

  const visibleRows = useMemo(() => {
    if (!rows) return [];
    return rows.filter((r) => !hidden.has(r.category || NO_CATEGORY));
  }, [rows, hidden]);

  const totalRows = rows?.length ?? 0;
  const totalSum = useMemo(() => visibleRows.reduce((s, r) => s + (Number(r.SUMM) || 0), 0), [visibleRows]);

  const catBreakdown = useMemo(() => {
    const map = Object.create(null);
    for (const r of visibleRows) {
      const cat = r.category || NO_CATEGORY_LABEL;
      if (!map[cat]) map[cat] = { count: 0, sum: 0 };
      map[cat].count++;
      map[cat].sum += Number(r.SUMM) || 0;
    }
    return Object.entries(map).sort((a, b) => b[1].sum - a[1].sum);
  }, [visibleRows]);

  const donutData = useMemo(() => {
    const top = catBreakdown.slice(0, 7);
    const rest = catBreakdown.slice(7);
    const data = top.map(([name, { sum }]) => ({ name, sum }));
    const restSum = rest.reduce((s, [, { sum }]) => s + sum, 0);
    if (restSum > 0) data.push({ name: 'Прочие', sum: restSum });
    return data;
  }, [catBreakdown]);

  const branchBreakdown = useMemo(() => {
    const map = Object.create(null);
    for (const r of visibleRows) {
      const dep = r.dep_name || '— без филиала';
      if (!map[dep]) map[dep] = { count: 0, sum: 0 };
      map[dep].count++;
      map[dep].sum += Number(r.SUMM) || 0;
    }
    return Object.entries(map).sort((a, b) => b[1].sum - a[1].sum).slice(0, 8);
  }, [visibleRows]);
  const maxBranch = Math.max(1, ...branchBreakdown.map(([, v]) => v.sum));

  const dayData = useMemo(() => {
    const map = Array.from({ length: 7 }, (_, i) => ({ day: DAY_NAMES[i], sum: 0, count: 0 }));
    visibleRows.forEach((r) => {
      if (!r.DK_DATE) return;
      const d = new Date(r.DK_DATE);
      if (!isNaN(d)) { map[d.getDay()].sum += Number(r.SUMM) || 0; map[d.getDay()].count++; }
    });
    return map;
  }, [visibleRows]);
  const maxDay = Math.max(1, ...dayData.map((d) => d.sum));

  const timeData = useMemo(() => {
    const map = Object.create(null);
    visibleRows.forEach((r) => {
      const d = (r.DK_DATE || '').slice(0, 10);
      if (!d) return;
      if (!map[d]) map[d] = { date: d, sum: 0 };
      map[d].sum += Number(r.SUMM) || 0;
    });
    return Object.values(map).sort((a, b) => a.date.localeCompare(b.date)).map((d) => ({ ...d, label: d.date.slice(5).replace('-', '.') }));
  }, [visibleRows]);

  const hiddenCount = totalRows - visibleRows.length;
  const hiddenSum = useMemo(() => {
    if (!rows) return 0;
    return rows.filter((r) => hidden.has(r.category || NO_CATEGORY)).reduce((s, r) => s + (Number(r.SUMM) || 0), 0);
  }, [rows, hidden]);

  async function downloadPng() {
    if (!reportRef.current) return;
    setPnging(true);
    setExporting(true);
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    try {
      const url = await toPng(reportRef.current, { backgroundColor: '#ffffff', pixelRatio: 2, cacheBust: true, skipFonts: true });
      const a = document.createElement('a');
      a.href = url;
      a.download = `Касса_${dateFrom || 'all'}_${dateTo || 'all'}.png`;
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
      <TopProgressBar active={pnging || (loading && rows !== null)} />

      {/* Controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="ui-eyebrow mb-3">Период · {dateFrom} — {dateTo}</span>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
            Сводный отчёт по кассе
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Кассовые перемещения по категориям и филиалам · настраиваемый PNG-отчёт</p>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          {DATE_PRESETS.map((p) => (
            <button key={p.key} onClick={() => applyPreset(p)}
              className={`ui-chip ${activePreset === p.key? 'is-active' : ''}`}>
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
          <button className={`ui-chip ${activePreset === 'custom'? 'is-active' : ''}`}
            onClick={applyCustomRange}>
            Применить период
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={() => setShowSettings((v) => !v)}>
            <SlidersHorizontal size={14} /> Категории{hidden.size > 0 ? ` (${hidden.size} скрыто)` : ''}
          </button>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={() => load()} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
          </button>
          <button className="btn btn--primary flex items-center gap-1.5" onClick={downloadPng} disabled={pnging || loading || !rows}>
            <ImageIcon size={15} /> {pnging ? 'Генерирую…' : 'Скачать PNG'}
          </button>
        </div>
      </div>

      {showSettings && (
        <CategorySettings
          categories={categories}
          hasUncategorized={hasUncategorized}
          hidden={hidden}
          onToggle={toggleCategory}
          onShowAll={() => setHidden(new Set())}
          onHideAll={() => setHidden(new Set([...categories.map((c) => c.name), ...(hasUncategorized ? [NO_CATEGORY] : [])]))}
          onClose={() => setShowSettings(false)}
        />
      )}

      {loading && rows === null && <LoadingPanel />}

      {rows !== null && (
        <div className="overflow-x-auto rounded-2xl">
          <ScaledReport>
            <RTC.Provider value={T}>
              <div ref={reportRef} style={{ width: REPORT_WIDTH, background: T.bg, color: T.ink }} className="cash-summary-report overflow-hidden">
                <style>{`.cash-summary-report table,.cash-summary-report thead,.cash-summary-report tbody,.cash-summary-report tr,.cash-summary-report td,.cash-summary-report th{background:transparent;border:0;color:inherit;box-shadow:none;}`}</style>

                {/* Header */}
                <div className="px-10 pt-9 pb-8 text-white flex items-end justify-between"
                  style={{ background: 'var(--color-primary)' }}>
                  <div>
                    <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">Сводный отчёт</div>
                    <div className="mt-1 text-[30px] font-extrabold leading-tight">Кассовые перемещения</div>
                    <div className="mt-1 text-sm opacity-90">{periodLabel}{hidden.size > 0 ? ` · ${hidden.size} категорий скрыто` : ''}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] font-semibold uppercase tracking-wide opacity-80">Итого по отчёту</div>
                    <div className="text-[40px] font-extrabold leading-none tabular-nums">{fmtMoney(totalSum)}</div>
                    <div className="mt-1 text-sm opacity-90">{visibleRows.length} записей</div>
                  </div>
                </div>

                <div className="px-10 py-8 space-y-8">
                  {/* KPI cards */}
                  <div className="grid grid-cols-4 gap-4">
                    <KpiCard icon={Wallet} label="Итого по отчёту" value={fmtMoney(totalSum)} sub={`${visibleRows.length} из ${totalRows} записей`} color={BRAND} />
                    <KpiCard icon={Tag} label="Категорий показано" value={String(catBreakdown.length)} sub={`из ${categories.length + (hasUncategorized ? 1 : 0)} всего`} />
                    <KpiCard icon={Building2} label="Филиалов" value={String(branchBreakdown.length)} sub="с движениями за период" />
                    <KpiCard icon={SlidersHorizontal} label="Скрыто настройкой" value={fmtMoney(hiddenSum)} sub={`${hiddenCount} записей исключено`} color={hiddenCount ? 'var(--color-danger)' : undefined} />
                  </div>

                  {/* Trend */}
                  {timeData.length > 1 && (
                    <Section title="Динамика по дням" icon={TrendingUp}>
                      <ResponsiveContainer width="100%" height={220}>
                        <AreaChart data={timeData}>
                          <defs>
                            <linearGradient id="cashSummaryGrad" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="0%" stopColor={BRAND} stopOpacity={0.35} />
                              <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" stroke={T.line} vertical={false} />
                          <XAxis dataKey="label" tick={{ fontSize: 11, fill: T.muted }} axisLine={false} tickLine={false} />
                          <YAxis tick={{ fontSize: 11, fill: T.muted }} axisLine={false} tickLine={false} tickFormatter={fmtMoney} width={90} />
                          <Tooltip content={<CustomTooltip />} />
                          <Area type="monotone" dataKey="sum" stroke={BRAND} strokeWidth={2} fill="url(#cashSummaryGrad)" isAnimationActive={false} />
                        </AreaChart>
                      </ResponsiveContainer>
                    </Section>
                  )}

                  {/* Categories + Branches */}
                  <div className="grid grid-cols-2 gap-6">
                    <Section title="По категориям" icon={BarChart3}>
                      <CatDonut data={donutData} total={totalSum} />
                    </Section>
                    <Section title="По филиалам" icon={Building2}>
                      <div className="space-y-3 pt-1">
                        {branchBreakdown.map(([name, { sum }]) => (
                          <BarRow key={name} label={name} value={sum} max={maxBranch} color={BRAND} right={fmtMoney(sum)} />
                        ))}
                        {branchBreakdown.length === 0 && <div className="text-sm py-4 text-center" style={{ color: T.muted }}>Нет данных</div>}
                      </div>
                    </Section>
                  </div>

                  {/* Day of week */}
                  <Section title="Активность по дням недели" icon={ArrowUpDown}>
                    <div className="space-y-2.5">
                      {dayData.map((d) => (
                        <BarRow key={d.day} label={d.day} value={d.sum} max={maxDay} color={(d.day === 'Вс' || d.day === 'Сб') ? 'var(--color-warning)' : BRAND} right={fmtMoney(d.sum)} />
                      ))}
                    </div>
                  </Section>
                </div>

                {/* Footer */}
                <div className="px-10 py-4 flex items-center justify-between text-[11px]" style={{ borderTop: `1px solid ${T.line}`, color: T.muted }}>
                  <span>Сводный отчёт по кассовым перемещениям · {periodLabel}</span>
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
