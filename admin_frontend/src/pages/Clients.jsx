import { useState } from 'react';
import { Search, Phone, RefreshCw, TrendingDown, ChevronDown, ChevronRight } from 'lucide-react';
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
// Полная метка времени открытия досье — момент реального ответа
// /clients/{id}, а не декоративное значение.
const fmtStamp = (d) => {
  if (!d) return '—';
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' }) +
    ' ' + d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
};

// Риск оттока конкретного клиента — та же формула, что и во вкладке
// «Уходящие клиенты» ниже (ChurningTab / GET /clients/churning):
// клиент не появлялся дольше, чем вдвое больше его обычного интервала
// между заказами, но не менее 45 дней (тот же фиксированный минимум,
// что описан в подсказке ChurningTab). Считается из уже загруженной
// истории заказов профиля (profile.orders), без отдельного запроса.
// Нужно минимум 2 заказа, чтобы вообще был интервал для сравнения.
function computeChurnRisk(profile) {
  const dates = (profile?.orders || [])
    .map((o) => new Date(o.date))
    .filter((d) => !isNaN(d))
    .sort((a, b) => a - b);
  if (dates.length < 2) return null;
  let totalGapDays = 0;
  for (let i = 1; i < dates.length; i++) totalGapDays += (dates[i] - dates[i - 1]) / 86400000;
  const avgGapDays = totalGapDays / (dates.length - 1);
  const daysSinceLast = Math.floor((Date.now() - dates[dates.length - 1]) / 86400000);
  const threshold = Math.max(avgGapDays * 2, 45);
  return {
    avgGapDays: Math.round(avgGapDays),
    daysSinceLast,
    atRisk: daysSinceLast > threshold,
  };
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

function ClientCard({ profile, openedAt }) {
  const churn = computeChurnRisk(profile);
  return (
    <div className="space-y-4">
      {/* Досье одной поверхностью. Прежде те же данные лежали в трёх
          блоках, которые пересказывали друг друга: штамп печатал
          «ЗАКАЗОВ · LTV», под ним LTV и «Заказов» повторялись в
          KPI-карточках, а даты висели отдельным столбиком справа. */}
      <div className={`dossier client-fui-frame ${churn?.atRisk ? 'dossier--risk' : ''}`}>
        <span className="client-fui-corner-tr" />
        <span className="client-fui-corner-bl" />
        <span className="client-fui-scan" />

        <div className="dossier__head">
          <div className="min-w-0">
            <div className="dossier__name">
              <span className="truncate">{profile.name || '—'}</span>
              {churn?.atRisk && (
                <span
                  className="fui-status fui-status--always fui-status--error shrink-0"
                  title={`Не заказывал ${churn.daysSinceLast} дн.`}
                >
                  <span className="fui-status__t">Риск оттока</span>
                </span>
              )}
            </div>
            {profile.phone && (
              <span className="dossier__phone"><Phone size={12} /> {profile.phone}</span>
            )}
          </div>

          <div className="dossier__span">
            <div>Первый заказ <b>{fmtDate(profile.first_order_date)}</b></div>
            <div>Последний <b>{fmtDate(profile.last_order_date)}</b></div>
            {churn?.atRisk && (
              <div>Тишина <b>{churn.daysSinceLast} дн.</b> · обычно раз в {churn.avgGapDays}</div>
            )}
            {openedAt && <div>Досье открыто <b>{fmtStamp(openedAt)}</b></div>}
          </div>
        </div>

        <div className="dossier__reads">
          <div className="dossier__read dossier__read--lead">
            <span className="dossier__read-k">LTV</span>
            <span className="dossier__read-v">{fmtRub(profile.total_spent)}</span>
          </div>
          <div className="dossier__read">
            <span className="dossier__read-k">Средний чек</span>
            <span className="dossier__read-v">{fmtRub(profile.avg_check)}</span>
          </div>
          <div className="dossier__read">
            <span className="dossier__read-k">Заказов</span>
            <span className="dossier__read-v">{profile.order_count.toLocaleString('ru-RU')}</span>
          </div>
          {profile.acquisition_channel && (
            <div className="dossier__read">
              <span className="dossier__read-k">Канал</span>
              <span className="dossier__read-v" style={{ fontSize: '0.95rem' }}>{profile.acquisition_channel}</span>
            </div>
          )}
        </div>
      </div>

      <div className="app-card overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-[color:var(--color-border)] px-4 py-3">
          <h3 className="font-semibold">История заказов</h3>
          <span className="fui-readout">{profile.orders.length}</span>
        </div>
        {profile.orders.length === 0 ? (
          <div className="py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">Нет заказов</div>
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
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">{error}</div>
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
                { label: 'Заказов', numeric: true, render: (c) => c.order_count },
                { label: 'Потрачено', numeric: true, render: (c) => fmtRub(c.total_spent) },
                { label: 'Обычно раз в', numeric: true, render: (c) => `${c.avg_gap_days} дн.` },
                { label: 'Последний заказ', numeric: true, render: (c) => fmtDate(c.last_order_date) },
                // Не красное число в каждой строке: в этой таблице все
                // строки по определению в зоне риска, и сплошной красный
                // столбец не отличал тех, кого ещё можно вернуть, от
                // безнадёжных. Отличает длина полосы — во сколько раз
                // тишина превысила обычный интервал клиента.
                { label: 'Не был', numeric: true, render: (c) => {
                  // Шкала от порога (тишина = 2 обычных интервала) до
                  // четырёхкратного превышения: при линейной шкале от нуля
                  // почти все строки упирались в максимум и полоса
                  // переставала различать.
                  const over = c.avg_gap_days > 0 ? c.days_since_last_order / (c.avg_gap_days * 2) : 1;
                  const w = Math.min(100, Math.max(14, 22 + (over - 1) * 26));
                  return (
                    <span className="cli-lag">
                      <span className="cli-lag__v">{c.days_since_last_order} дн.</span>
                      <span className="cli-lag__t"><i style={{ width: `${w}%` }} /></span>
                    </span>
                  );
                } },
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
  // Момент, когда карточка клиента реально была открыта (ответ
  // /clients/{id} пришёл) — для FUI-штампа «ДОСЬЕ ОТКРЫТО», не
  // выдуманное значение.
  const [openedAt, setOpenedAt] = useState(null);

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
      setOpenedAt(new Date());
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
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">{error}</div>
      )}

      {activeTab === 'search' && (
        <div className="space-y-4">
          {/* Поиск одной строкой-прибором: поле и действие в одном
              корпусе. Раньше кнопка «Найти» растягивалась во всю ширину
              под полем и весила как основная операция страницы, хотя
              главный объект здесь — досье, которое она открывает. */}
          <form onSubmit={doSearch} className="cli-search">
            <Search size={15} className="shrink-0 text-[color:var(--color-text-faint)]" />
            <input
              className="cli-search__i"
              placeholder="Имя, телефон или номер заказа"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button
              type="submit"
              className="btn btn--primary btn--sm shrink-0"
              disabled={searching || query.trim().length < 2}
            >
              {searching ? 'Ищу…' : 'Найти'}
            </button>
          </form>

          {/* Вместо экрана, на котором ничего нет, — что именно ищет
              этот инструмент. */}
          {!results.length && !profile && !searching && (
            <div className="fui-datastate">
              <span className="fui-datastate__code">База готова</span>
              <span className="fui-datastate__rule" />
              <span className="fui-datastate__title">Найдите клиента</span>
              <span className="fui-datastate__text">
                Поиск идёт по имени, телефону и номеру заказа. В досье — LTV, средний чек, история заказов и риск оттока.
              </span>
            </div>
          )}

          {results.length > 0 && !profile && (
            <div className="app-card overflow-hidden">
              {results.map((r) => (
                <button
                  key={r.contragent_id}
                  onClick={() => selectClient(r.contragent_id)}
                  className="cli-hit fui-press"
                >
                  <span className="cli-hit__n">{r.name}</span>
                  {r.phone && <span className="cli-hit__p"><Phone size={11} /> {r.phone}</span>}
                </button>
              ))}
            </div>
          )}

          {loadingProfile && <SkeletonTable rows={6} />}
          {profile && !loadingProfile && (
            <>
              <button onClick={() => { setProfile(null); setOpenedAt(null); }} className="text-sm text-[color:var(--color-primary)] hover:underline">← назад к результатам поиска</button>
              <ClientCard profile={profile} openedAt={openedAt} />
            </>
          )}
        </div>
      )}

      {activeTab === 'churning' && <ChurningTab />}
    </div>
  );
}
