import { useState, useMemo } from 'react';
import { Search, RefreshCw, Download, ChevronUp, ChevronDown, ChevronsUpDown, AlertTriangle } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

const fmt    = (v) => (v == null ? '—' : v);
const fmtRub = (v) => (v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽');
const fmtMin = (v) => {
  if (v == null) return '—';
  if (v < 1) return '< 1м';
  const total = Math.round(v);
  const d = Math.floor(total / 1440);
  const h = Math.floor((total % 1440) / 60);
  const m = total % 60;
  if (d > 0) return `${d}д ${h}ч ${m}м`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
};
const fmtDt = (v) => {
  if (!v) return '—';
  try { return new Date(v).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return v; }
};

const STATUS_COLORS = {
  'Выполнено': 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  'В работе':  'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  'Прочее':    'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
};

const DURATION_OPTIONS = [
  { label: 'Любая', value: 'all' },
  { label: '< 5м',  value: 'lt5',    test: (v) => v != null && v < 5 },
  { label: '5–30м', value: '5to30',  test: (v) => v != null && v >= 5 && v < 30 },
  { label: '30–60м',value: '30to60', test: (v) => v != null && v >= 30 && v < 60 },
  { label: '> 1ч',  value: 'gt60',   test: (v) => v != null && v >= 60 },
  { label: 'Нет данных', value: 'null', test: (v) => v == null },
];

const WARNING_TYPES = [
  { key: 'warning_mismatch', label: 'Разные мастера' },
  { key: 'warning_too_fast', label: 'Слишком быстро' },
  { key: 'warning_no_in',    label: 'Нет входа' },
  { key: 'warning_multi',    label: 'Несколько сканов' },
];

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronsUpDown size={13} className="inline ml-1 opacity-30" />;
  return sortDir === 'asc'
    ? <ChevronUp size={13} className="inline ml-1 text-[color:var(--color-primary)]" />
    : <ChevronDown size={13} className="inline ml-1 text-[color:var(--color-primary)]" />;
}

function KpiCard({ label, value, accent }) {
  return (
    <div className="app-card p-4 text-center">
      <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{label}</div>
      <div className={`text-xl font-semibold ${accent ? 'text-[color:var(--color-primary)]' : 'text-[color:var(--color-text-primary)]'}`}>
        {value}
      </div>
    </div>
  );
}

function MastersSummaryTable({ rows, onMasterClick }) {
  const [tab, setTab] = useState('works');

  const byMaster = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      const name = r.description || '—';
      if (!map[name]) map[name] = { name, total: 0, done: 0, inWork: 0, warnings: 0, durations: [] };
      map[name].total++;
      if (r.status === 'Выполнено') {
        map[name].done++;
        if (r.duration_min != null) map[name].durations.push(r.duration_min);
      }
      if (r.status === 'В работе') map[name].inWork++;
      if (r.warnings?.length > 0) map[name].warnings++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  // Строго по ВЫХОДАМ: только услуги с OUT-сканом, мастер = out_description.
  const bySalaryMaster = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      if (r.master_salary == null) return;
      const name = r.out_description || '—';
      if (!map[name]) map[name] = { master: name, services_done: 0, total_kredit: 0, total_salary: 0, warnings_count: 0 };
      map[name].services_done++;
      map[name].total_kredit += Number(r.kredit) || 0;
      map[name].total_salary += Number(r.master_salary) || 0;
      if (r.warnings?.length > 0) map[name].warnings_count++;
    });
    return Object.values(map).sort((a, b) => b.total_salary - a.total_salary);
  }, [rows]);

  const median = (arr) => {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  };

  return (
    <div className="app-card overflow-x-auto">
      <div className="p-4 border-b border-[color:var(--color-border)] flex items-center gap-4">
        <h3 className="font-semibold">Сводка по мастерам</h3>
        <div className="flex gap-1 ml-auto">
          {['works', 'salary'].map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-3 py-1 rounded text-sm transition-colors ${tab === t ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-muted)]'}`}>
              {t === 'works' ? 'Работы' : 'Зарплата'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'works' && (
        <table className="w-full text-sm min-w-[540px]">
          <thead>
            <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
              <th className="px-4 py-2 text-left">Мастер</th>
              <th className="px-4 py-2 text-right">Всего</th>
              <th className="px-4 py-2 text-right">Выполнено</th>
              <th className="px-4 py-2 text-right">В работе</th>
              <th className="px-4 py-2 text-right">Медиана</th>
              <th className="px-4 py-2 text-right text-amber-600">Нарушений</th>
            </tr>
          </thead>
          <tbody>
            {byMaster.map((m, i) => (
              <tr key={m.name} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/30' : ''}>
                <td className="px-4 py-2 font-medium">
                  <button onClick={() => onMasterClick(m.name)}
                    className="text-left hover:text-[color:var(--color-primary)] hover:underline transition-colors">
                    {m.name}
                  </button>
                </td>
                <td className="px-4 py-2 text-right">{m.total}</td>
                <td className="px-4 py-2 text-right text-green-600">{m.done}</td>
                <td className="px-4 py-2 text-right text-yellow-600">{m.inWork}</td>
                <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtMin(median(m.durations))}</td>
                <td className="px-4 py-2 text-right">
                  {m.warnings > 0
                    ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><AlertTriangle size={12} />{m.warnings}</span>
                    : <span className="text-[color:var(--color-muted-foreground)]">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {tab === 'salary' && (
        <table className="w-full text-sm min-w-[540px]">
          <thead>
            <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
              <th className="px-4 py-2 text-left">Мастер</th>
              <th className="px-4 py-2 text-right">Учтено в ЗП</th>
              <th className="px-4 py-2 text-right">Сумма услуг</th>
              <th className="px-4 py-2 text-right text-[color:var(--color-primary)]">Зарплата</th>
              <th className="px-4 py-2 text-right text-amber-600">Нарушений</th>
            </tr>
          </thead>
          <tbody>
            {bySalaryMaster.map((m, i) => (
              <tr key={m.master} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/30' : ''}>
                <td className="px-4 py-2 font-medium">
                  <button onClick={() => onMasterClick(m.master)}
                    className="text-left hover:text-[color:var(--color-primary)] hover:underline transition-colors">
                    {m.master}
                  </button>
                </td>
                <td className="px-4 py-2 text-right">{m.services_done}</td>
                <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtRub(m.total_kredit)}</td>
                <td className="px-4 py-2 text-right font-semibold text-[color:var(--color-primary)]">{fmtRub(m.total_salary)}</td>
                <td className="px-4 py-2 text-right">
                  {m.warnings_count > 0
                    ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><AlertTriangle size={12} />{m.warnings_count}</span>
                    : <span className="text-[color:var(--color-muted-foreground)]">—</span>}
                </td>
              </tr>
            ))}
            {bySalaryMaster.length > 0 && (
              <tr className="border-t border-[color:var(--color-border)] font-semibold bg-[color:var(--color-muted)]/20">
                <td className="px-4 py-2">Итого</td>
                <td className="px-4 py-2 text-right">{bySalaryMaster.reduce((s, r) => s + r.services_done, 0)}</td>
                <td className="px-4 py-2 text-right">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_kredit || 0), 0))}</td>
                <td className="px-4 py-2 text-right text-[color:var(--color-primary)]">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_salary || 0), 0))}</td>
                <td className="px-4 py-2 text-right">{bySalaryMaster.reduce((s, r) => s + (r.warnings_count || 0), 0)}</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default function Masters() {
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo]     = useState(today);
  const [statusFilter, setStatusFilter]     = useState('Все');
  const [masterSearch, setMasterSearch]     = useState('');
  const [nameSearch, setNameSearch]         = useState('');
  const [codeSearch, setCodeSearch]         = useState('');
  const [docSearch, setDocSearch]           = useState('');
  const [durationFilter, setDurationFilter] = useState('all');
  const [categoryFilter, setCategoryFilter]       = useState(new Set());
  const [warningTypeFilter, setWarningTypeFilter] = useState(new Set());

  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  const [rows, setRows]                   = useState([]);
  const [salarySummary, setSalarySummary] = useState([]);
  const [loading, setLoading]             = useState(false);
  const [error, setError]                 = useState(null);
  const [loaded, setLoaded]               = useState(false);
  const [warningsOnly, setWarningsOnly]   = useState(false);

  const masterNames = useMemo(
    () => [...new Set(rows.map((r) => r.description).filter(Boolean))].sort(),
    [rows],
  );

  const categoryOptions = useMemo(
    () => [...new Set(rows.map((r) => r.top_parent_name).filter(Boolean))].sort(),
    [rows],
  );

  function toggleCategory(cat) {
    setCategoryFilter((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  function toggleWarningType(key) {
    setWarningTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('/masters/works', { params });
      const data = res.data;
      // Support both old (array) and new (object) response shape
      if (Array.isArray(data)) {
        setRows(data);
        setSalarySummary([]);
      } else {
        setRows(data.services || []);
        setSalarySummary(data.salary_summary || []);
      }
      setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }

  function toggleSort(col) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  const filtered = useMemo(() => {
    let r = rows;
    if (statusFilter !== 'Все') r = r.filter((x) => x.status === statusFilter);
    if (warningsOnly) r = r.filter((x) => x.warnings?.length > 0);
    if (warningTypeFilter.size > 0) r = r.filter((x) => [...warningTypeFilter].some((k) => x[k]));
    if (categoryFilter.size > 0) r = r.filter((x) => x.top_parent_name && categoryFilter.has(x.top_parent_name));
    if (masterSearch) r = r.filter((x) => (x.description || '') === masterSearch);
    if (nameSearch)   r = r.filter((x) => (x.name || '').toLowerCase().includes(nameSearch.toLowerCase()));
    if (docSearch)    r = r.filter((x) => (x.doc_num || '').toLowerCase().includes(docSearch.toLowerCase()));
    if (codeSearch) {
      const tokens = codeSearch.split(/[,;\s]+/).filter(Boolean);
      r = r.filter((x) => {
        const c = (x.code || '').toLowerCase();
        return tokens.some((t) => t.endsWith('.') ? c.startsWith(t.toLowerCase()) : c.includes(t.toLowerCase()));
      });
    }
    if (durationFilter !== 'all') {
      const opt = DURATION_OPTIONS.find((o) => o.value === durationFilter);
      if (opt) r = r.filter((x) => opt.test(x.duration_min));
    }
    return r;
  }, [rows, statusFilter, warningsOnly, warningTypeFilter, categoryFilter, masterSearch, nameSearch, docSearch, codeSearch, durationFilter]);

  const sorted = useMemo(() => {
    if (!sortCol) return filtered;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? '';
      const bv = b[sortCol] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv), 'ru') * dir;
    });
  }, [filtered, sortCol, sortDir]);

  const kpi = useMemo(() => {
    const orderMap = {};
    filtered.forEach((r) => {
      if (!r.doc_num) return;
      if (!orderMap[r.doc_num]) orderMap[r.doc_num] = [];
      orderMap[r.doc_num].push(r.status);
    });
    const orders = Object.values(orderMap);
    return {
      total:        filtered.length,
      done:         filtered.filter((x) => x.status === 'Выполнено').length,
      inWork:       filtered.filter((x) => x.status === 'В работе').length,
      warnings:     filtered.filter((x) => x.warnings?.length > 0).length,
      masters:      new Set(filtered.map((x) => x.description).filter(Boolean)).size,
      ordersTotal:  orders.length,
      ordersDone:   orders.filter((s) => s.every((v) => v === 'Выполнено')).length,
      ordersInWork: orders.filter((s) => s.some((v) => v === 'В работе')).length,
    };
  }, [filtered]);

  function downloadCsv() {
    if (!filtered.length) return;
    const cols = ['status', 'description', 'doc_num', 'code', 'name', 'service_group', 'in_time', 'out_time', 'duration_min', 'master_salary', 'warnings'];
    const header = cols.join(';');
    const body = filtered.map((r) => cols.map((c) => (r[c] ?? '')).join(';')).join('\n');
    const blob = new Blob(['\uFEFF' + header + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'masters_works.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  const SortTh = ({ col, children, className = '' }) => (
    <th
      className={`px-4 py-3 cursor-pointer select-none hover:text-[color:var(--color-text-primary)] transition-colors ${className}`}
      onClick={() => toggleSort(col)}
    >
      {children}
      <SortIcon col={col} sortCol={sortCol} sortDir={sortDir} />
    </th>
  );

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Работы мастеров</h2>
        <div className="flex gap-2">
          <button onClick={downloadCsv} disabled={!filtered.length}
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
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Статус</label>
            <select className="input w-full" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option>Все</option>
              <option>Выполнено</option>
              <option>В работе</option>
              <option>Прочее</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Мастер</label>
            {loaded && masterNames.length > 0 ? (
              <select className="input w-full" value={masterSearch} onChange={(e) => setMasterSearch(e.target.value)}>
                <option value="">Все мастера</option>
                {masterNames.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            ) : (
              <div className="relative">
                <Search size={14} style={{ position:'absolute', left:'10px', top:'50%', transform:'translateY(-50%)', pointerEvents:'none' }} className="text-[color:var(--color-muted-foreground)]" />
                <input className="input w-full" style={{ paddingLeft:'2rem' }} placeholder="Поиск..." value={masterSearch} onChange={(e) => setMasterSearch(e.target.value)} />
              </div>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Услуга</label>
            <input className="input w-full" placeholder="Название..." value={nameSearch} onChange={(e) => setNameSearch(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Заказ</label>
            <input className="input w-full" placeholder="Номер заказа..." value={docSearch} onChange={(e) => setDocSearch(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Код (через запятую, или с точкой)</label>
            <input className="input w-full" placeholder="2.17, 3." value={codeSearch} onChange={(e) => setCodeSearch(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Длительность</label>
            <select className="input w-full" value={durationFilter} onChange={(e) => setDurationFilter(e.target.value)}>
              {DURATION_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
        </div>
        {loaded && categoryOptions.length > 0 && (
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
              Категория услуги
              {categoryFilter.size > 0 && (
                <button onClick={() => setCategoryFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                  сбросить
                </button>
              )}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {categoryOptions.map((cat) => (
                <button
                  key={cat}
                  onClick={() => toggleCategory(cat)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    categoryFilter.has(cat)
                      ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                      : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                  }`}
                >
                  {cat}
                </button>
              ))}
            </div>
          </div>
        )}
        {loaded && (
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
              Тип нарушения
              {warningTypeFilter.size > 0 && (
                <button onClick={() => setWarningTypeFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                  сбросить
                </button>
              )}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {WARNING_TYPES.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => toggleWarningType(key)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    warningTypeFilter.has(key)
                      ? 'bg-amber-500 text-white border-amber-500'
                      : 'border-[color:var(--color-border)] hover:border-amber-400 hover:text-amber-600'
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
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

      {loading && <SkeletonTable rows={8} />}

      {loaded && !loading && (
        <>
          {/* KPI — услуги */}
          <div>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2 font-medium uppercase tracking-wide">Услуги</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              <KpiCard label="Всего услуг" value={kpi.total} />
              <KpiCard label="Выполнено" value={kpi.done} accent />
              <KpiCard label="В работе" value={kpi.inWork} />
              <KpiCard label="Мастеров" value={kpi.masters} />
              <div className="app-card p-4 text-center cursor-pointer hover:ring-2 ring-amber-400 transition-all"
                onClick={() => setWarningsOnly((v) => !v)}
                title="Кликните для фильтра по нарушениям"
                style={warningsOnly ? {outline: '2px solid #f59e0b'} : {}}>
                <div className="text-xs text-amber-600 mb-1 flex items-center justify-center gap-1">
                  <AlertTriangle size={11} /> Нарушений
                </div>
                <div className={`text-xl font-semibold ${kpi.warnings > 0 ? 'text-amber-600' : 'text-[color:var(--color-text-primary)]'}`}>
                  {kpi.warnings}
                </div>
                {warningsOnly && <div className="text-xs text-amber-500 mt-0.5">фильтр вкл.</div>}
              </div>
            </div>
          </div>

          {/* KPI — заказы */}
          <div>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2 font-medium uppercase tracking-wide">Заказы</p>
            <div className="grid grid-cols-3 gap-3">
              <KpiCard label="Всего заказов" value={kpi.ordersTotal} />
              <KpiCard label="Выполнено" value={kpi.ordersDone} accent />
              <KpiCard label="В работе" value={kpi.ordersInWork} />
            </div>
          </div>

          {/* Summary by masters */}
          <MastersSummaryTable rows={filtered} onMasterClick={(name) => setMasterSearch(name)} />

          {/* Full table */}
          <div className="app-card">
            <div className="p-4 border-b border-[color:var(--color-border)] flex items-center justify-between">
              <h3 className="font-semibold">Список услуг</h3>
              <span className="text-sm text-[color:var(--color-muted-foreground)]">{filtered.length} строк</span>
            </div>

            {/* Desktop table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-sm min-w-[700px]">
                <thead>
                  <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] text-xs uppercase tracking-wide">
                    <SortTh col="status" className="text-left">Статус</SortTh>
                    <th className="px-4 py-3 text-amber-600 text-xs uppercase tracking-wide"></th>
                    <SortTh col="description" className="text-left">Мастер</SortTh>
                    <SortTh col="doc_num" className="text-left">Заказ</SortTh>
                    <SortTh col="code" className="text-left">Код</SortTh>
                    <SortTh col="name" className="text-left">Услуга</SortTh>
                    <SortTh col="service_group" className="text-left">Группа</SortTh>
                    <SortTh col="in_time" className="text-right">Приём</SortTh>
                    <SortTh col="out_time" className="text-right">Выдача</SortTh>
                    <SortTh col="duration_min" className="text-right">Длит.</SortTh>
                    <SortTh col="master_salary" className="text-right">ЗП</SortTh>
                  </tr>
                </thead>
                <tbody>
                  {sorted.slice(0, 500).map((r, i) => (
                    <tr key={r.service_id ?? i}
                      className={`${r.warnings?.length > 0 ? 'bg-amber-50/60 dark:bg-amber-900/10' : i % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}`}>
                      <td className="px-4 py-2">
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[r.status] || STATUS_COLORS['Прочее']}`}>
                          {r.status}
                        </span>
                      </td>
                      <td className="px-2 py-2">
                        {r.warnings?.length > 0 && (
                          <span title={r.warnings.join('\n')} className="cursor-help">
                            <AlertTriangle size={14} className="text-amber-500" />
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-2 font-medium">{fmt(r.description)}</td>
                      <td className="px-4 py-2 text-[color:var(--color-muted-foreground)]">{fmt(r.doc_num)}</td>
                      <td className="px-4 py-2 font-mono text-xs">{fmt(r.code)}</td>
                      <td className="px-4 py-2">{fmt(r.name)}</td>
                      <td className="px-4 py-2 text-[color:var(--color-muted-foreground)]">{fmt(r.service_group)}</td>
                      <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtDt(r.in_time)}</td>
                      <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtDt(r.out_time)}</td>
                      <td className="px-4 py-2 text-right">{fmtMin(r.duration_min)}</td>
                      <td className="px-4 py-2 text-right font-medium text-[color:var(--color-primary)]">{fmtRub(r.master_salary)}</td>
                    </tr>
                  ))}
                  {filtered.length > 500 && (
                    <tr>
                      <td colSpan={11} className="px-4 py-3 text-center text-sm text-[color:var(--color-muted-foreground)]">
                        Показано первые 500 из {filtered.length}. Используйте фильтры или скачайте CSV.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="sm:hidden divide-y divide-[color:var(--color-border)]">
              {sorted.slice(0, 500).map((r, i) => (
                <div key={r.service_id ?? i} className={`p-3 space-y-1.5 ${r.warnings?.length > 0 ? 'bg-amber-50/50 dark:bg-amber-900/10' : ''}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[r.status] || STATUS_COLORS['Прочее']}`}>
                        {r.status}
                      </span>
                      {r.warnings?.length > 0 && (
                        <AlertTriangle size={13} className="text-amber-500" title={r.warnings.join('\n')} />
                      )}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-[color:var(--color-muted-foreground)]">
                      {r.master_salary != null && (
                        <span className="font-medium text-[color:var(--color-primary)]">{fmtRub(r.master_salary)}</span>
                      )}
                      <span>{fmtMin(r.duration_min)}</span>
                    </div>
                  </div>
                  <div className="font-medium text-sm">{fmt(r.description)}</div>
                  <div className="text-sm">{fmt(r.name)}</div>
                  {r.warnings?.length > 0 && (
                    <div className="space-y-0.5">
                      {r.warnings.map((w, wi) => (
                        <div key={wi} className="flex items-start gap-1 text-xs text-amber-700 dark:text-amber-400">
                          <AlertTriangle size={11} className="mt-0.5 shrink-0" />
                          <span>{w}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[color:var(--color-muted-foreground)]">
                    <span>Заказ: {fmt(r.doc_num)}</span>
                    <span>Код: {fmt(r.code)}</span>
                    {r.service_group && <span>{r.service_group}</span>}
                  </div>
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-[color:var(--color-muted-foreground)]">
                    {r.in_time && <span>Приём: {fmtDt(r.in_time)}</span>}
                    {r.out_time && <span>Выдача: {fmtDt(r.out_time)}</span>}
                  </div>
                </div>
              ))}
              {filtered.length > 500 && (
                <div className="px-4 py-3 text-center text-sm text-[color:var(--color-muted-foreground)]">
                  Показано первые 500 из {filtered.length}. Используйте фильтры или скачайте CSV.
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
