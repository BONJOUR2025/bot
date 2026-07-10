import { useState } from 'react';
import { Search, Users, Phone, RefreshCw, TrendingDown, Calendar, Wallet, ShoppingBag, Megaphone } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';

const fmtRub = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d) ? v : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

function KpiStat({ label, value, accent, icon }) {
  return (
    <div className="app-card p-4" style={{ borderLeft: `3px solid ${accent}` }}>
      <div className="flex gap-3">
        {icon && <div className="mt-0.5 shrink-0" style={{ color: accent }}>{icon}</div>}
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] font-medium">{label}</div>
          <div className="text-xl sm:text-2xl font-bold tabular-nums mt-0.5 leading-tight" style={{ color: accent }}>{value}</div>
        </div>
      </div>
    </div>
  );
}

function ClientCard({ profile }) {
  return (
    <div className="space-y-4">
      <div className="app-card p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-semibold text-lg">{profile.name || '—'}</div>
          {profile.phone && (
            <div className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-1.5 mt-0.5">
              <Phone size={13} /> {profile.phone}
            </div>
          )}
        </div>
        <div className="text-xs text-[color:var(--color-muted-foreground)] text-right">
          <div>Первый заказ: {fmtDate(profile.first_order_date)}</div>
          <div>Последний заказ: {fmtDate(profile.last_order_date)}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <KpiStat label="LTV (всего потрачено)" value={fmtRub(profile.total_spent)} accent="#6366f1" icon={<Wallet size={18} />} />
        <KpiStat label="Средний чек" value={fmtRub(profile.avg_check)} accent="#22c55e" icon={<ShoppingBag size={18} />} />
        <KpiStat label="Заказов" value={profile.order_count.toLocaleString('ru-RU')} accent="#f59e0b" icon={<Calendar size={18} />} />
      </div>

      {profile.acquisition_channel && (
        <div className="app-card p-4 flex items-center gap-3" style={{ borderLeft: '3px solid #ec4899' }}>
          <div className="shrink-0" style={{ color: '#ec4899' }}><Megaphone size={18} /></div>
          <div className="min-w-0 flex-1">
            <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] font-medium">Откуда узнал о нас (опрос)</div>
            <div className="text-sm font-semibold mt-0.5">{profile.acquisition_channel}</div>
          </div>
        </div>
      )}

      <div className="app-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
          <h3 className="font-semibold">История заказов</h3>
        </div>
        <div className="p-3">
          <ResponsiveTable
            data={profile.orders}
            keyFn={(o) => o.doc_num}
            emptyText="Нет заказов"
            columns={[
              { label: '№ заказа', primary: true, render: (o) => (
                <div>
                  <div className="font-medium">{o.doc_num}</div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)]">{fmtDate(o.date)}</div>
                </div>
              )},
              { label: 'Сумма', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (o) => fmtRub(o.amount) },
            ]}
          />
        </div>
      </div>
    </div>
  );
}

function ChurningTab() {
  const [lookbackDays, setLookbackDays] = useState(365);
  const [minOrders, setMinOrders] = useState(3);
  const [clients, setClients] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const res = await api.get('/clients/churning', { params: { lookback_days: lookbackDays, min_orders: minOrders } });
      setClients(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally { setLoading(false); }
  }

  function exportCsv() {
    if (!clients?.length) return;
    const hdr = 'Имя;Телефон;Заказов;Потрачено;Обычный интервал (дн);Последний заказ;Не был дней';
    const body = clients.map((c) => [c.name, c.phone || '', c.order_count, c.total_spent, c.avg_gap_days, c.last_order_date, c.days_since_last_order].join(';')).join('\n');
    const blob = new Blob(['﻿' + hdr + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'churning_clients.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="app-card p-4 space-y-3">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Клиенты, у которых было минимум {minOrders} заказа за последние {lookbackDays} дн., но которые не появлялись
          дольше, чем обычно (в 2 раза дольше их среднего интервала между заказами, но не менее 45 дней).
          Только список — рассылки/автоотправки пока нет, звонить или писать нужно вручную.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Период анализа (дн.)</label>
            <input type="number" className="input w-28" value={lookbackDays} onChange={(e) => setLookbackDays(+e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Мин. заказов</label>
            <input type="number" className="input w-24" value={minOrders} onChange={(e) => setMinOrders(+e.target.value)} />
          </div>
          <button onClick={load} disabled={loading} className="btn btn--primary btn--sm flex items-center gap-1.5">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {clients ? 'Обновить' : 'Загрузить'}
          </button>
          {clients?.length > 0 && (
            <button onClick={exportCsv} className="btn btn--secondary btn--sm">CSV</button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {!loading && clients && (
        <div className="app-card overflow-hidden">
          <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
            <h3 className="font-semibold">Уходящие клиенты</h3>
            <span className="text-sm text-[color:var(--color-muted-foreground)]">{clients.length}</span>
          </div>
          <div className="p-3">
            <ResponsiveTable
              data={clients}
              keyFn={(c) => c.contragent_id}
              emptyText="Никто не подходит под критерии — хороший знак"
              columns={[
                { label: 'Клиент', primary: true, render: (c) => (
                  <div>
                    <div className="font-medium">{c.name || '—'}</div>
                    {c.phone && <div className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1"><Phone size={10} /> {c.phone}</div>}
                  </div>
                )},
                { label: 'Заказов', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (c) => c.order_count },
                { label: 'Потрачено', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (c) => fmtRub(c.total_spent) },
                { label: 'Обычно раз в', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (c) => `${c.avg_gap_days} дн.` },
                { label: 'Последний заказ', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap', render: (c) => fmtDate(c.last_order_date) },
                { label: 'Не был', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold text-red-500', render: (c) => `${c.days_since_last_order} дн.` },
              ]}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export default function Clients() {
  const [activeTab, setActiveTab] = useState('search');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [profile, setProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [error, setError] = useState(null);

  async function doSearch(e) {
    e?.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true); setError(null); setProfile(null);
    try {
      const res = await api.get('/clients/search', { params: { q: query.trim() } });
      setResults(res.data || []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка поиска');
    } finally { setSearching(false); }
  }

  async function selectClient(contragentId) {
    setLoadingProfile(true); setError(null);
    try {
      const res = await api.get(`/clients/${contragentId}`);
      setProfile(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки карточки');
    } finally { setLoadingProfile(false); }
  }

  const mainTabs = [
    { key: 'search',   label: 'Карточка клиента', icon: <Search size={15} /> },
    { key: 'churning', label: 'Уходящие клиенты', icon: <TrendingDown size={15} /> },
  ];

  return (
    <div className="space-y-5">
      <TopProgressBar active={searching || loadingProfile} />

      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Users size={22} className="text-[color:var(--color-primary)]" /> Клиенты
        </h2>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
          Карточка клиента и список тех, кто давно не появлялся (Агбис)
        </p>
      </div>

      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {activeTab === 'search' && (
        <div className="space-y-4">
          <form onSubmit={doSearch} className="app-card p-4 flex gap-2">
            <input
              className="input flex-1"
              placeholder="Имя или телефон клиента…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" className="btn btn--primary flex items-center gap-1.5" disabled={searching || query.trim().length < 2}>
              <Search size={14} /> {searching ? 'Ищу…' : 'Найти'}
            </button>
          </form>

          {results.length > 0 && !profile && (
            <div className="app-card overflow-hidden">
              <div className="divide-y divide-[color:var(--color-border)]">
                {results.map((r) => (
                  <button
                    key={r.contragent_id}
                    onClick={() => selectClient(r.contragent_id)}
                    className="w-full text-left px-4 py-3 flex items-center justify-between gap-3 hover:bg-[color:var(--color-muted)]/30 transition-colors"
                  >
                    <span className="font-medium">{r.name}</span>
                    {r.phone && <span className="text-sm text-[color:var(--color-muted-foreground)] flex items-center gap-1"><Phone size={12} /> {r.phone}</span>}
                  </button>
                ))}
              </div>
            </div>
          )}

          {loadingProfile && <SkeletonTable rows={6} />}
          {profile && !loadingProfile && (
            <>
              <button onClick={() => setProfile(null)} className="text-sm text-[color:var(--color-primary)] hover:underline">← назад к результатам поиска</button>
              <ClientCard profile={profile} />
            </>
          )}
        </div>
      )}

      {activeTab === 'churning' && <ChurningTab />}
    </div>
  );
}
