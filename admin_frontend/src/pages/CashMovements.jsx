import { useEffect, useState, useMemo } from 'react';
import { Search, X, AlertTriangle, CheckCircle, Download } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d) ? v : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

const fmtMoney = (v) => {
  if (v == null) return '—';
  return Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';
};

export default function CashMovements() {
  const { toast } = useToast();
  const [rows, setRows]         = useState([]);
  const [meta, setMeta]         = useState({ dep_map: {}, users_map: {}, valid_prefixes: [] });
  const [loading, setLoading]   = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo]     = useState('');
  const [query, setQuery]       = useState('');
  const [selDeps, setSelDeps]   = useState([]);
  const [selUsers, setSelUsers] = useState([]);
  const [invalidOnly, setInvalidOnly] = useState(false);

  useEffect(() => {
    api.get('cash-moves/meta').then((r) => setMeta(r.data)).catch(() => {});
    loadData();
  }, []);

  async function loadData(from = dateFrom, to = dateTo) {
    setLoading(true);
    try {
      const params = {};
      if (from) params.date_from = from;
      if (to)   params.date_to   = to;
      const res = await api.get('cash-moves/', { params });
      setRows(res.data || []);
    } catch {
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }

  function handleFilter() {
    loadData(dateFrom, dateTo);
  }

  const depOptions = useMemo(() => Object.entries(meta.dep_map).map(([id, name]) => ({ id, name })), [meta.dep_map]);
  const userOptions = useMemo(() => {
    const seen = new Set();
    return rows
      .filter((r) => { const k = String(r.OWN_USR_ID || ''); if (seen.has(k)) return false; seen.add(k); return true; })
      .map((r) => ({ id: String(r.OWN_USR_ID || ''), name: r.user_name }))
      .sort((a, b) => a.name.localeCompare(b.name, 'ru'));
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (selDeps.length)  out = out.filter((r) => selDeps.includes(String(r.DEP_SRC_ID || '')));
    if (selUsers.length) out = out.filter((r) => selUsers.includes(String(r.OWN_USR_ID || '')));
    if (query.trim())    out = out.filter((r) => (r.BASIS || '').toLowerCase().includes(query.toLowerCase()));
    if (invalidOnly)     out = out.filter((r) => !r.prefix_ok);
    return out;
  }, [rows, selDeps, selUsers, query, invalidOnly]);

  const invalidCount = useMemo(() => rows.filter((r) => !r.prefix_ok).length, [rows]);
  const totalSum     = useMemo(() => filtered.reduce((s, r) => s + (Number(r.SUMM) || 0), 0), [filtered]);

  function toggleDep(id) {
    setSelDeps((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }
  function toggleUser(id) {
    setSelUsers((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  function exportCsv() {
    const header = ['Дата', 'Филиал', 'Создатель', 'BASIS', 'Сумма', 'Префикс ОК'];
    const csvRows = filtered.map((r) => [
      fmtDate(r.DK_DATE),
      r.dep_name,
      r.user_name,
      r.BASIS || '',
      r.SUMM || 0,
      r.prefix_ok ? 'Да' : 'Нет',
    ]);
    const csv = [header, ...csvRows].map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'cash_moves.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6 max-w-full">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">Кассовые перемещения</h2>
        <button onClick={exportCsv} disabled={loading || filtered.length === 0}
          className="btn flex items-center gap-2 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
          <Download size={16} /> CSV
        </button>
      </div>

      {/* Filters */}
      <div className="app-card p-4 space-y-4">
        {/* Date range */}
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата с</label>
            <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата по</label>
            <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button onClick={handleFilter} disabled={loading} className="btn btn--primary">
            Применить
          </button>
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(''); setDateTo(''); loadData('', ''); }}
              className="btn bg-gray-200 text-gray-700 hover:bg-gray-300">
              <X size={14} />
            </button>
          )}
        </div>

        {/* BASIS search */}
        <div className="relative" style={{ maxWidth: 360 }}>
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input className="input w-full" style={{ paddingLeft: '2.25rem' }} placeholder="Поиск в BASIS…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]">
              <X size={14} />
            </button>
          )}
        </div>

        {/* Dep + user filters */}
        <div className="flex flex-wrap gap-6">
          {depOptions.length > 0 && (
            <div>
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Филиал</div>
              <div className="flex flex-wrap gap-1.5">
                {depOptions.map(({ id, name }) => (
                  <button key={id} onClick={() => toggleDep(id)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      selDeps.includes(id)
                        ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                        : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                    }`}>
                    {name}
                  </button>
                ))}
              </div>
            </div>
          )}
          {userOptions.length > 0 && (
            <div>
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Создатель</div>
              <div className="flex flex-wrap gap-1.5">
                {userOptions.map(({ id, name }) => (
                  <button key={id} onClick={() => toggleUser(id)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      selUsers.includes(id)
                        ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                        : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                    }`}>
                    {name}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Invalid only toggle */}
        <label className="flex items-center gap-2 cursor-pointer w-fit">
          <input type="checkbox" className="w-4 h-4 rounded" checked={invalidOnly}
            onChange={(e) => setInvalidOnly(e.target.checked)} />
          <span className="text-sm">Только записи с неверным/пустым BASIS</span>
          {invalidCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
              <AlertTriangle size={11} /> {invalidCount}
            </span>
          )}
        </label>
      </div>

      {/* Summary */}
      {!loading && rows.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="app-card p-4 text-center">
            <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Записей</div>
            <div className="text-lg font-semibold">{filtered.length}</div>
          </div>
          <div className="app-card p-4 text-center">
            <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Итого сумма</div>
            <div className="text-lg font-semibold text-[color:var(--color-primary)]">{fmtMoney(totalSum)}</div>
          </div>
          <div className="app-card p-4 text-center">
            <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Верный BASIS</div>
            <div className="text-lg font-semibold text-green-600">
              {filtered.filter((r) => r.prefix_ok).length}
            </div>
          </div>
          <div className="app-card p-4 text-center">
            <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Неверный BASIS</div>
            <div className="text-lg font-semibold text-red-600">
              {filtered.filter((r) => !r.prefix_ok).length}
            </div>
          </div>
        </div>
      )}

      {/* Valid prefixes hint */}
      {meta.valid_prefixes.length > 0 && (
        <div className="text-xs text-[color:var(--color-muted-foreground)]">
          <span className="font-medium">Допустимые префиксы BASIS: </span>
          {meta.valid_prefixes.join(', ')}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="app-card p-4"><SkeletonTable rows={10} cols={6} /></div>
      ) : filtered.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          {rows.length === 0 ? 'Нет данных' : 'Нет записей по заданным фильтрам'}
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
          <table className="min-w-max w-full text-sm divide-y divide-[color:var(--color-border)] bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
            <thead>
              <tr className="bg-[color:var(--color-table-header)]">
                <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide w-8"></th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">Дата</th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">Филиал</th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">Создатель</th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">BASIS</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Сумма</th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">ID</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {filtered.map((row, i) => (
                <tr key={row.ID_KASSES_MOVE ?? i}
                  className={`transition-colors hover:bg-[color:var(--color-table-row-hover)] ${
                    i % 2 !== 0 ? 'bg-[color:var(--color-table-row-alt)]' : ''
                  } ${!row.prefix_ok ? 'border-l-2 border-l-red-400' : ''}`}>
                  <td className="px-3 py-2.5 text-center">
                    {row.prefix_ok
                      ? <CheckCircle size={14} className="text-green-500 mx-auto" />
                      : <AlertTriangle size={14} className="text-red-500 mx-auto" title="Неверный BASIS" />}
                  </td>
                  <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(row.DK_DATE)}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">{row.dep_name}</td>
                  <td className="px-3 py-2.5 whitespace-nowrap">{row.user_name}</td>
                  <td className="px-3 py-2.5 font-mono text-xs max-w-xs truncate" title={row.BASIS}>{row.BASIS || '—'}</td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap font-medium">{fmtMoney(row.SUMM)}</td>
                  <td className="px-3 py-2.5 text-xs text-[color:var(--color-muted-foreground)] font-mono">{row.ID_KASSES_MOVE}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[color:var(--color-table-header)] font-semibold">
                <td className="px-3 py-2.5" colSpan={5}>Итого: {filtered.length} записей</td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-primary)]">{fmtMoney(totalSum)}</td>
                <td className="px-3 py-2.5"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </div>
  );
}
