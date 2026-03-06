import { useState, useMemo } from 'react';
import { Search, RefreshCw, Download } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

const fmt = (v) => (v == null ? '—' : v);
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

function MastersSummaryTable({ rows }) {
  const byMaster = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      const name = r.description || '—';
      if (!map[name]) map[name] = { name, total: 0, done: 0, inWork: 0, durations: [] };
      map[name].total++;
      if (r.status === 'Выполнено') { map[name].done++; if (r.duration_min != null) map[name].durations.push(r.duration_min); }
      if (r.status === 'В работе') map[name].inWork++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  const median = (arr) => {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  };

  return (
    <div className="app-card overflow-x-auto">
      <div className="p-4 border-b border-[color:var(--color-border)]">
        <h3 className="font-semibold">Сводка по мастерам</h3>
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
            <th className="px-4 py-2 text-left">Мастер</th>
            <th className="px-4 py-2 text-right">Всего</th>
            <th className="px-4 py-2 text-right">Выполнено</th>
            <th className="px-4 py-2 text-right">В работе</th>
            <th className="px-4 py-2 text-right">Медиана, мин</th>
          </tr>
        </thead>
        <tbody>
          {byMaster.map((m, i) => (
            <tr key={m.name} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/30' : ''}>
              <td className="px-4 py-2 font-medium">{m.name}</td>
              <td className="px-4 py-2 text-right">{m.total}</td>
              <td className="px-4 py-2 text-right text-green-600">{m.done}</td>
              <td className="px-4 py-2 text-right text-yellow-600">{m.inWork}</td>
              <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">
                {fmtMin(median(m.durations))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Masters() {
  const today = new Date().toISOString().slice(0, 10);
  const monthAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);

  const [dateFrom, setDateFrom] = useState(monthAgo);
  const [dateTo, setDateTo]     = useState(today);
  const [statusFilter, setStatusFilter] = useState('Все');
  const [masterSearch, setMasterSearch] = useState('');
  const [nameSearch, setNameSearch]     = useState('');
  const [codeSearch, setCodeSearch]     = useState('');
  const [docSearch, setDocSearch]       = useState('');

  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [loaded, setLoaded]   = useState(false);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('/masters/works', { params });
      setRows(res.data);
      setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }

  const filtered = useMemo(() => {
    let r = rows;
    if (statusFilter !== 'Все') r = r.filter((x) => x.status === statusFilter);
    if (masterSearch) r = r.filter((x) => (x.description || '').toLowerCase().includes(masterSearch.toLowerCase()));
    if (nameSearch)   r = r.filter((x) => (x.name || '').toLowerCase().includes(nameSearch.toLowerCase()));
    if (docSearch)    r = r.filter((x) => (x.doc_num || '').toLowerCase().includes(docSearch.toLowerCase()));
    if (codeSearch) {
      const tokens = codeSearch.split(/[,;\s]+/).filter(Boolean);
      r = r.filter((x) => {
        const c = (x.code || '').toLowerCase();
        return tokens.some((t) => t.endsWith('.') ? c.startsWith(t.toLowerCase()) : c.includes(t.toLowerCase()));
      });
    }
    return r;
  }, [rows, statusFilter, masterSearch, nameSearch, docSearch, codeSearch]);

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
      masters:      new Set(filtered.map((x) => x.description).filter(Boolean)).size,
      ordersTotal:  orders.length,
      ordersDone:   orders.filter((s) => s.every((v) => v === 'Выполнено')).length,
      ordersInWork: orders.filter((s) => s.some((v) => v === 'В работе')).length,
    };
  }, [filtered]);

  function downloadCsv() {
    if (!filtered.length) return;
    const cols = ['status', 'description', 'doc_num', 'code', 'name', 'service_group', 'in_time', 'out_time', 'duration_min'];
    const header = cols.join(';');
    const body = filtered.map((r) => cols.map((c) => (r[c] ?? '')).join(';')).join('\n');
    const blob = new Blob(['\uFEFF' + header + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'masters_works.csv'; a.click();
    URL.revokeObjectURL(url);
  }

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
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
              <input className="input w-full pl-7" placeholder="Поиск..." value={masterSearch} onChange={(e) => setMasterSearch(e.target.value)} />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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

      {loading && <SkeletonTable rows={8} />}

      {loaded && !loading && (
        <>
          {/* KPI — услуги */}
          <div>
            <p className="text-xs text-[color:var(--color-muted-foreground)] mb-2 font-medium uppercase tracking-wide">Услуги</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <KpiCard label="Всего услуг" value={kpi.total} />
              <KpiCard label="Выполнено" value={kpi.done} accent />
              <KpiCard label="В работе" value={kpi.inWork} />
              <KpiCard label="Мастеров" value={kpi.masters} />
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
          <MastersSummaryTable rows={filtered} />

          {/* Full table */}
          <div className="app-card overflow-x-auto">
            <div className="p-4 border-b border-[color:var(--color-border)] flex items-center justify-between">
              <h3 className="font-semibold">Список услуг</h3>
              <span className="text-sm text-[color:var(--color-muted-foreground)]">{filtered.length} строк</span>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] text-xs uppercase tracking-wide">
                  <th className="px-4 py-3 text-left">Статус</th>
                  <th className="px-4 py-3 text-left">Мастер</th>
                  <th className="px-4 py-3 text-left">Заказ</th>
                  <th className="px-4 py-3 text-left">Код</th>
                  <th className="px-4 py-3 text-left">Услуга</th>
                  <th className="px-4 py-3 text-left">Группа</th>
                  <th className="px-4 py-3 text-right">Приём</th>
                  <th className="px-4 py-3 text-right">Выдача</th>
                  <th className="px-4 py-3 text-right">Длит.</th>
                </tr>
              </thead>
              <tbody>
                {filtered.slice(0, 500).map((r, i) => (
                  <tr key={r.service_id ?? i} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}>
                    <td className="px-4 py-2">
                      <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[r.status] || STATUS_COLORS['Прочее']}`}>
                        {r.status}
                      </span>
                    </td>
                    <td className="px-4 py-2 font-medium">{fmt(r.description)}</td>
                    <td className="px-4 py-2 text-[color:var(--color-muted-foreground)]">{fmt(r.doc_num)}</td>
                    <td className="px-4 py-2 font-mono text-xs">{fmt(r.code)}</td>
                    <td className="px-4 py-2">{fmt(r.name)}</td>
                    <td className="px-4 py-2 text-[color:var(--color-muted-foreground)]">{fmt(r.service_group)}</td>
                    <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtDt(r.in_time)}</td>
                    <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtDt(r.out_time)}</td>
                    <td className="px-4 py-2 text-right">{fmtMin(r.duration_min)}</td>
                  </tr>
                ))}
                {filtered.length > 500 && (
                  <tr>
                    <td colSpan={9} className="px-4 py-3 text-center text-sm text-[color:var(--color-muted-foreground)]">
                      Показано первые 500 из {filtered.length}. Используйте фильтры или скачайте CSV.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
