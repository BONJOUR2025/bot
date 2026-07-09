import { useState, useEffect, useMemo } from 'react';
import { Search, Users, UserCheck, UserX, ShieldCheck, Download, RefreshCw } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { StatCard } from '../components/ui/SalaryUI.jsx';

const STATUS_OPTIONS = [
  { key: 'all',      label: 'Все' },
  { key: 'active',   label: 'Активные' },
  { key: 'inactive', label: 'Неактивные' },
];

const FLAG_DEFS = [
  { key: 'is_courier',       label: 'Курьер' },
  { key: 'is_inkass',        label: 'Инкассатор' },
  { key: 'is_technologist',  label: 'Технолог' },
  { key: 'is_brigadier',     label: 'Бригадир' },
  { key: 'is_cabinet_user',  label: 'Кабинет' },
  { key: 'is_cabinet_admin', label: 'Админ кабинета' },
  { key: 'is_system',        label: 'Системный' },
];

export default function AgbisUsers() {
  const [rows, setRows]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [query, setQuery]     = useState('');
  const [status, setStatus]   = useState('active');
  const [roleFilter, setRoleFilter] = useState('');
  const [depFilter, setDepFilter]   = useState('');

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('agbis-users/');
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }

  const roleOptions = useMemo(() => {
    const seen = new Set();
    rows.forEach((r) => { if (r.role_name) seen.add(r.role_name); });
    return [...seen].sort((a, b) => a.localeCompare(b, 'ru'));
  }, [rows]);

  const depOptions = useMemo(() => {
    const seen = new Set();
    rows.forEach((r) => { if (r.dep_name) seen.add(r.dep_name); });
    return [...seen].sort((a, b) => a.localeCompare(b, 'ru'));
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (status === 'active')   out = out.filter((r) => r.is_working);
    if (status === 'inactive') out = out.filter((r) => !r.is_working);
    if (roleFilter) out = out.filter((r) => r.role_name === roleFilter);
    if (depFilter)  out = out.filter((r) => r.dep_name === depFilter);
    const q = query.trim().toLowerCase();
    if (q) {
      out = out.filter((r) =>
        (r.description || '').toLowerCase().includes(q) ||
        (r.phone || '').toLowerCase().includes(q) ||
        (r.mobile || '').toLowerCase().includes(q) ||
        (r.email || '').toLowerCase().includes(q) ||
        String(r.user_id).includes(q)
      );
    }
    return out;
  }, [rows, status, roleFilter, depFilter, query]);

  const activeCount   = rows.filter((r) => r.is_working).length;
  const inactiveCount = rows.length - activeCount;
  const adminCount    = rows.filter((r) => r.is_admin_role).length;

  function exportCsv() {
    const header = ['ID', 'ФИО', 'Активен', 'Роль', 'Подразделение', 'Телефон', 'Моб.', 'Email'];
    const csvRows = filtered.map((r) => [
      r.user_id, r.description, r.is_working ? 'Да' : 'Нет', r.role_name || '',
      r.dep_name || '', r.phone || '', r.mobile || '', r.email || '',
    ]);
    const csv = [header, ...csvRows].map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: 'agbis_users.csv' }).click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6 max-w-full pb-20">
      <TopProgressBar active={loading} />
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-2xl font-semibold tracking-tight flex-1 min-w-0">Пользователи АГБИС</h2>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={load} disabled={loading} className="btn flex items-center gap-1.5 border border-[color:var(--color-border)] px-2.5 py-1.5">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> <span className="hidden sm:inline">Обновить</span>
          </button>
          <button onClick={exportCsv} disabled={loading || filtered.length === 0}
            className="btn flex items-center gap-1.5 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 px-2.5 py-1.5">
            <Download size={15} /><span className="hidden sm:inline">CSV</span>
          </button>
        </div>
      </div>

      {error && <div className="app-card p-4 text-red-500 text-sm">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard icon={<Users size={18} />} label="Всего" value={rows.length} />
        <StatCard icon={<UserCheck size={18} />} label="Активные" value={activeCount} onClick={() => setStatus('active')} active={status === 'active'} />
        <StatCard icon={<UserX size={18} />} label="Неактивные" value={inactiveCount} onClick={() => setStatus('inactive')} active={status === 'inactive'} />
        <StatCard icon={<ShieldCheck size={18} />} label="Админ-роль" value={adminCount} />
      </div>

      <div className="app-card p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input
            className="input pl-8 w-full text-sm"
            placeholder="Поиск: ФИО, телефон, email, ID"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="flex gap-1 rounded-lg border border-[color:var(--color-border)] p-0.5">
          {STATUS_OPTIONS.map((o) => (
            <button
              key={o.key}
              onClick={() => setStatus(o.key)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${status === o.key ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-muted)]/50'}`}
            >
              {o.label}
            </button>
          ))}
        </div>
        <select className="input text-sm py-1.5 h-9" value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)}>
          <option value="">Все роли</option>
          {roleOptions.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select className="input text-sm py-1.5 h-9" value={depFilter} onChange={(e) => setDepFilter(e.target.value)}>
          <option value="">Все подразделения</option>
          {depOptions.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>

      {loading ? <SkeletonTable rows={8} /> : (
        <div className="app-card overflow-hidden">
          <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
            <h3 className="text-sm font-semibold">Пользователи ({filtered.length})</h3>
          </div>
          <div className="p-3">
            <ResponsiveTable
              data={filtered}
              keyFn={(r) => r.user_id}
              emptyText="Нет данных"
              columns={[
                { label: 'ID', render: (r) => <span className="text-[color:var(--color-muted-foreground)] tabular-nums">{r.user_id}</span> },
                { label: 'ФИО', primary: true, render: (r) => (
                  <div className="max-w-[220px] truncate" title={r.description}>{r.description || '—'}</div>
                )},
                { label: 'Статус', render: (r) => (
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${r.is_working ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' : 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]'}`}>
                    {r.is_working ? 'Активен' : 'Неактивен'}
                  </span>
                )},
                { label: 'Роль', render: (r) => (
                  <span className="flex items-center gap-1">
                    {r.role_name || '—'}
                    {r.is_admin_role && <ShieldCheck size={12} className="text-[color:var(--color-primary)]" />}
                  </span>
                )},
                { label: 'Подразделение', render: (r) => r.dep_name || '—' },
                { label: 'Телефон', render: (r) => r.phone || r.mobile || '—' },
                { label: 'Email', render: (r) => r.email || '—' },
                { label: 'Отметки', render: (r) => {
                  const active = FLAG_DEFS.filter((f) => r[f.key]);
                  if (!active.length) return '—';
                  return (
                    <div className="flex flex-wrap gap-1">
                      {active.map((f) => (
                        <span key={f.key} className="text-[10px] px-1.5 py-0.5 rounded bg-[color:var(--color-muted)]/50 text-[color:var(--color-muted-foreground)]">
                          {f.label}
                        </span>
                      ))}
                    </div>
                  );
                }},
              ]}
            />
          </div>
        </div>
      )}
    </div>
  );
}
