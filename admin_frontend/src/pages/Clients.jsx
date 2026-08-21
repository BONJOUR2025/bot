import { useState } from 'react';
import { Search, Phone, RefreshCw, TrendingDown, Calendar, Wallet, ShoppingBag, Megaphone, ChevronDown, ChevronRight } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';
import OrderPhotos from '../components/OrderPhotos.jsx';

const fmtRub = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d) ? v : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

// Цвета берутся из токенов, а не задаются шестнадцатеричными литералами:
// раньше здесь стояли значения палитры брутализма (var(--color-primary), var(--color-success),
// var(--color-warning)) прямо во встроенных стилях, поэтому при смене темы они
// оставались прежними — переопределить их через CSS невозможно.
function KpiStat({ label, value, accent = 'var(--color-primary)', icon }) {
  return (
    <div className="ui-shell ui-shell--sm">
      <div className="ui-core border border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-4">
        <div className="flex gap-3">
          {icon && (
            <span
              className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full"
              style={{ color: accent, background: `color-mix(in oklab, ${accent} 14%, transparent)` }}
            >
              {icon}
            </span>
          )}
          <div className="min-w-0 flex-1">
            <div className="ui-label">{label}</div>
            <div className="ui-metric !text-[1.5rem] mt-1.5 text-[color:var(--color-text)]">
              {value}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function OrderRow({ contragentId, order }) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function toggle() {
    if (expanded) { setExpanded(false); return; }
    setExpanded(true);
    if (items || loading) return;
    setLoading(true); setError(null);
    try {
      const res = await api.get(`/clients/${contragentId}/orders/${encodeURIComponent(order.doc_num)}/items`);
      setItems(res.data || []);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки состава');
    } finally { setLoading(false); }
  }

  return (
    <div>
      <button
        type="button"
        onClick={toggle}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-[color:var(--color-muted)]/30 transition-colors text-left"
      >
        <div className="min-w-0 flex items-start gap-1.5">
          {expanded ? <ChevronDown size={14} className="mt-1 shrink-0 text-[color:var(--color-muted-foreground)]" /> : <ChevronRight size={14} className="mt-1 shrink-0 text-[color:var(--color-muted-foreground)]" />}
          <div className="min-w-0">
            <div className="font-medium">{order.doc_num}</div>
            <div className="text-xs text-[color:var(--color-muted-foreground)]">{fmtDate(order.date)}</div>
          </div>
        </div>
        <div className="font-semibold tabular-nums shrink-0">{fmtRub(order.amount)}</div>
      </button>

      {expanded && (
        <div className="px-4 pb-3 pl-9">
          {loading && <div className="text-xs text-[color:var(--color-muted-foreground)]">Загрузка…</div>}
          {error && <div className="text-xs text-red-500">{error}</div>}
          {!loading && !error && items?.length === 0 && (
            <div className="text-xs text-[color:var(--color-muted-foreground)]">Нет данных о составе заказа</div>
          )}
          {!loading && items?.length > 0 && (
            <ul className="space-y-1">
              {items.map((it, i) => (
                <li key={i} className="flex items-center justify-between gap-3 text-sm">
                  <span className="min-w-0 truncate">{it.name}{it.qty != null && it.qty !== 1 ? ` × ${it.qty}` : ''}</span>
                  <span className="tabular-nums text-[color:var(--color-muted-foreground)] shrink-0">{fmtRub(it.amount)}</span>
                </li>
              ))}
            </ul>
          )}
          <OrderPhotos contragentId={contragentId} docNum={order.doc_num} visible={expanded} />
        </div>
      )}
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
        <KpiStat label="LTV (всего потрачено)" value={fmtRub(profile.total_spent)} accent="var(--color-primary)" icon={<Wallet size={18} />} />
        <KpiStat label="Средний чек" value={fmtRub(profile.avg_check)} accent="var(--color-success)" icon={<ShoppingBag size={18} />} />
        <KpiStat label="Заказов" value={profile.order_count.toLocaleString('ru-RU')} accent="var(--color-warning)" icon={<Calendar size={18} />} />
        {profile.acquisition_channel && (
          <KpiStat label="Канал" value={profile.acquisition_channel} accent="var(--color-info)" icon={<Megaphone size={18} />} />
        )}
      </div>

      <div className="app-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
          <h3 className="font-semibold">История заказов</h3>
        </div>
        {profile.orders.length === 0 ? (
          <div className="py-6 text-center text-[color:var(--color-muted-foreground)] text-sm">Нет заказов</div>
        ) : (
          <div className="divide-y divide-[color:var(--color-border)]">
            {profile.orders.map((o) => (
              <OrderRow key={o.doc_num} contragentId={profile.contragent_id} order={o} />
            ))}
          </div>
        )}
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
        <span className="ui-eyebrow mb-3">
          {results?.length ? `Найдено: ${results.length}` : 'Поиск по базе клиентов'}
        </span>
        <h2 className="text-2xl font-bold">Клиенты</h2>
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
              placeholder="Имя, телефон или номер заказа…"
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
