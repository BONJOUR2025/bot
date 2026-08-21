import { useEffect, useState, useMemo } from 'react';
import { RefreshCw, Search, Download, ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

const CHANNELS = ['СМС', 'Push', 'MAX'];
const STATUSES = ['Доставлено', 'Не доставлено', 'В работе'];

const CHANNEL_COLORS = {
  'СМС':  'bg-blue-100 text-blue-700',
  'Push': 'bg-purple-100 text-purple-700',
  'MAX':  'bg-green-100 text-green-700',
  '—':    'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]',
};

const STATUS_COLORS = {
  'Доставлено':     'bg-green-100 text-green-700',
  'Не доставлено':  'bg-red-100 text-red-600',
  'В работе':       'bg-yellow-100 text-yellow-700',
};

function isoToday() {
  return new Date().toISOString().slice(0, 10);
}
function isoMStart() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
}
function fmtDateTime(v) {
  if (!v) return '—';
  const s = String(v).replace('T', ' ');
  return s.slice(0, 16);
}
function SortIcon({ field, sort }) {
  // Plain Unicode arrows (↕ especially) render as boxed emoji glyphs on iOS
  // instead of a thin text arrow — use vector icons like the other pages do.
  if (sort.field !== field) return <ChevronsUpDown size={13} className="opacity-30" />;
  return sort.dir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />;
}

export default function Smses() {
  const { toast } = useToast();
  const [rows, setRows]         = useState([]);
  const [loading, setLoading]   = useState(false);
  const [dateFrom, setDateFrom] = useState(isoMStart());
  const [dateTo, setDateTo]     = useState(isoToday());
  const [query, setQuery]       = useState('');
  const [selChannels, setSelChannels] = useState([]);
  const [selStatuses, setSelStatuses] = useState([]);
  const [sort, setSort]         = useState({ field: 'DTTM', dir: 'desc' });

  useEffect(() => { loadData(isoMStart(), isoToday()); }, []);

  async function loadData(from, to) {
    setLoading(true);
    try {
      const params = {};
      if (from) params.date_from = from;
      if (to)   params.date_to   = to;
      const res = await api.get('smses/', { params });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch {
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }

  function handleApply() { loadData(dateFrom, dateTo); }

  function toggleFilter(setter, val) {
    setter(prev => prev.includes(val) ? prev.filter(x => x !== val) : [...prev, val]);
  }

  function toggleSort(field) {
    setSort(prev => prev.field === field
      ? { field, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
      : { field, dir: 'desc' });
  }

  const safeRows = useMemo(() => Array.isArray(rows) ? rows : [], [rows]);

  const filtered = useMemo(() => {
    let out = safeRows;
    if (selChannels.length) out = out.filter(r => selChannels.includes(r.channel));
    if (selStatuses.length) out = out.filter(r => selStatuses.includes(r.OPER_STATUS));
    if (query.trim()) {
      const q = query.toLowerCase();
      out = out.filter(r =>
        (r.PHONE || '').includes(q) ||
        (r.TXT   || '').toLowerCase().includes(q)
      );
    }
    const mult = sort.dir === 'asc' ? 1 : -1;
    return [...out].sort((a, b) => {
      if (sort.field === 'DTTM')        return mult * (a.DTTM || '').localeCompare(b.DTTM || '');
      if (sort.field === 'PHONE')       return mult * (a.PHONE || '').localeCompare(b.PHONE || '');
      if (sort.field === 'OPER_STATUS') return mult * (a.OPER_STATUS || '').localeCompare(b.OPER_STATUS || '', 'ru');
      if (sort.field === 'channel')     return mult * (a.channel || '').localeCompare(b.channel || '', 'ru');
      return 0;
    });
  }, [safeRows, selChannels, selStatuses, query, sort]);

  const stats = useMemo(() => {
    const byChannel = {}, byStatus = {};
    for (const r of filtered) {
      byChannel[r.channel]     = (byChannel[r.channel]     || 0) + 1;
      byStatus[r.OPER_STATUS]  = (byStatus[r.OPER_STATUS]  || 0) + 1;
    }
    return { byChannel, byStatus };
  }, [filtered]);

  function exportCsv() {
    const header = ['ID', 'Дата/время', 'Телефон', 'Статус', 'Канал', 'Текст'];
    const csvRows = filtered.map(r => [
      r.ID, fmtDateTime(r.DTTM), r.PHONE || '', r.OPER_STATUS || '', r.channel,
      (r.TXT || '').replace(/\n/g, ' '),
    ]);
    const csv = [header, ...csvRows]
      .map(row => row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
      .join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: 'smses.csv' }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5 max-w-full pb-20">
      <TopProgressBar active={loading} />
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-0">
          <span className="ui-eyebrow mb-3">Период · {dateFrom} — {dateTo}</span>
          <h2 className="text-2xl font-semibold tracking-tight">СМС Агбис</h2>
        </div>
        <button onClick={exportCsv} disabled={loading || filtered.length === 0}
          className="btn flex items-center gap-2">
          <Download size={15} /> CSV
        </button>
        <button onClick={() => loadData(dateFrom, dateTo)} disabled={loading}
          className="btn flex items-center gap-2">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      {/* Filters */}
      <div className="app-card p-4 space-y-3">
        {/* Date range */}
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 sm:items-center">
          <input type="date" className="input w-full sm:w-auto" value={dateFrom}
            onChange={e => setDateFrom(e.target.value)} />
          <span className="text-[color:var(--color-muted-foreground)] text-sm hidden sm:inline">—</span>
          <input type="date" className="input w-full sm:w-auto" value={dateTo}
            onChange={e => setDateTo(e.target.value)} />
          <button onClick={handleApply} disabled={loading}
            className="btn btn--primary w-full sm:w-auto">Применить</button>
          <button onClick={() => { setDateFrom(''); setDateTo(''); loadData('', ''); }}
            disabled={loading} className="btn text-sm w-full sm:w-auto">Сбросить даты</button>
        </div>

        {/* Search */}
        <div className="relative max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input className="input pl-8 w-full" placeholder="Телефон или текст…"
            value={query} onChange={e => setQuery(e.target.value)} />
        </div>

        {/* Sort */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-[color:var(--color-muted-foreground)]">Сортировка:</span>
          {[
            { field: 'DTTM', label: 'Дата/время' },
            { field: 'PHONE', label: 'Телефон' },
            { field: 'OPER_STATUS', label: 'Статус' },
            { field: 'channel', label: 'Канал' },
          ].map(({ field, label }) => (
            <button key={field}
              onClick={() => toggleSort(field)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors inline-flex items-center gap-1 ${
                sort.field === field
                  ? 'bg-[color:var(--color-primary)] text-white border-transparent'
                  : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]'
              }`}>
              {label} <SortIcon field={field} sort={sort} />
            </button>
          ))}
        </div>

        {/* Channel filter */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-[color:var(--color-muted-foreground)]">Канал:</span>
          {CHANNELS.map(ch => (
            <button key={ch}
              onClick={() => toggleFilter(setSelChannels, ch)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                selChannels.includes(ch)
                  ? 'bg-[color:var(--color-primary)] text-white border-transparent'
                  : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]'
              }`}>
              {ch}
            </button>
          ))}
          {selChannels.length > 0 && (
            <button onClick={() => setSelChannels([])}
              className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]">
              сбросить
            </button>
          )}
        </div>

        {/* Status filter */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-xs text-[color:var(--color-muted-foreground)]">Статус:</span>
          {STATUSES.map(st => (
            <button key={st}
              onClick={() => toggleFilter(setSelStatuses, st)}
              className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                selStatuses.includes(st)
                  ? 'bg-[color:var(--color-primary)] text-white border-transparent'
                  : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]'
              }`}>
              {st}
            </button>
          ))}
          {selStatuses.length > 0 && (
            <button onClick={() => setSelStatuses([])}
              className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]">
              сбросить
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      {!loading && filtered.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="app-card p-4 text-center">
            <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Всего</div>
            <div className="text-lg font-semibold text-[color:var(--color-primary)]">{filtered.length}</div>
          </div>
          {Object.entries(stats.byChannel).sort((a, b) => b[1] - a[1]).map(([ch, cnt]) => (
            <div key={ch} className="app-card p-4 text-center">
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{ch}</div>
              <div className="text-lg font-semibold">{cnt}</div>
            </div>
          ))}
        </div>
      )}

      {/* Breakdown by status */}
      {!loading && filtered.length > 0 && (
        <div className="app-card p-4">
          <div className="text-sm font-medium mb-3">Разбивка по статусам</div>
          <div className="flex flex-wrap gap-3">
            {Object.entries(stats.byStatus).map(([st, cnt]) => {
              const share = filtered.length > 0 ? (cnt / filtered.length * 100).toFixed(1) : 0;
              return (
                <div key={st} className="flex items-center gap-2 text-sm">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[st] || 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]'}`}>{st}</span>
                  <span className="font-semibold">{cnt}</span>
                  <span className="text-xs text-[color:var(--color-muted-foreground)]">{share}%</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="app-card p-4"><SkeletonTable rows={10} cols={5} /></div>
      ) : filtered.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          {safeRows.length === 0 ? 'Нет данных' : 'Нет записей по заданным фильтрам'}
        </div>
      ) : (
        <ResponsiveTable
          data={filtered}
          keyFn={(row) => row.ID}
          emptyText="Нет данных"
          columns={[
            {
              label: 'Дата/время',
              render: (row) => <span className="font-mono text-xs">{fmtDateTime(row.DTTM)}</span>,
            },
            {
              label: 'Телефон',
              render: (row) => <span className="font-mono text-xs">{row.PHONE || '—'}</span>,
              primary: true,
            },
            {
              label: 'Статус',
              render: (row) => (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[row.OPER_STATUS] || 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]'}`}>
                  {row.OPER_STATUS || '—'}
                </span>
              ),
            },
            {
              label: 'Канал',
              render: (row) => (
                <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${CHANNEL_COLORS[row.channel] || ''}`}>
                  {row.channel}
                </span>
              ),
            },
            {
              label: 'Текст',
              render: (row) => (
                <span className="text-xs whitespace-pre-wrap break-words">{row.TXT || '—'}</span>
              ),
            },
          ]}
        />
      )}

      {!loading && filtered.length > 0 && (
        <div className="text-xs text-[color:var(--color-muted-foreground)] text-right">
          Показано {filtered.length} из {safeRows.length} записей
        </div>
      )}
    </div>
  );
}
