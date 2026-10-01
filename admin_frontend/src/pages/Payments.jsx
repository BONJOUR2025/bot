import { useEffect, useState } from 'react';
import { Banknote, CreditCard, Gift, RefreshCw, Undo2, Wallet } from 'lucide-react';
import api from '../api';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

/** Оплаты: деньги, пришедшие от клиентов за период (не выручка).
 *  Наличные, карта, безнал — сколько пришло; возвраты отдельно; бонусы и
 *  депозит — не деньги, показаны отдельно; итог — чистый плюс. Данные —
 *  GET /sales/payments (платежи по заказам Агбиса). */

function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function quickRange(key) {
  const n = new Date();
  const y = n.getFullYear();
  const m = n.getMonth();
  const today = ymd(n);
  if (key === 'yesterday') { const d = new Date(y, m, n.getDate() - 1); return [ymd(d), ymd(d)]; }
  if (key === 'week') return [ymd(new Date(y, m, n.getDate() - 6)), today];
  if (key === 'month') return [ymd(new Date(y, m, 1)), today];
  if (key === 'prev') return [ymd(new Date(y, m - 1, 1)), ymd(new Date(y, m, 0))];
  return [today, today];
}
const QUICK = [['today', 'Сегодня'], ['yesterday', 'Вчера'], ['week', '7 дней'], ['month', 'Этот месяц'], ['prev', 'Прошлый месяц']];

const rub = (v) => `${Math.round(Number(v) || 0).toLocaleString('ru-RU')} ₽`;
const minus = (v) => (v ? `−${rub(v)}` : '—');
const dash = (v) => (v ? rub(v) : '—');
function dayLabel(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' });
}

function Stat({ label, value, sub, icon: Icon, tone }) {
  return (
    <div className={`app-card pay-stat ${tone ? `pay-stat--${tone}` : ''}`}>
      <div className="pay-stat__k">{Icon && <Icon size={15} aria-hidden="true" />}{label}</div>
      <div className="pay-stat__v">{value}</div>
      {sub && <div className="pay-stat__s">{sub}</div>}
    </div>
  );
}

export default function Payments() {
  const [range, setRange] = useState(() => quickRange('today'));
  const [quick, setQuick] = useState('today');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async ([from, to] = range) => {
    setLoading(true);
    setError('');
    try {
      const r = await api.get('sales/payments', { params: { date_from: from, date_to: to } });
      setData(r.data);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError(typeof d === 'string' ? d : 'Не удалось загрузить оплаты');
    } finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(range); }, [range]);

  const kind = (key) => (data?.kinds || []).find((k) => k.key === key)?.amount || 0;
  const hasBank = kind('bank') > 0 || (data?.points || []).some((p) => p.bank);
  const deposit = kind('deposit');
  const multiDay = (data?.days || []).length > 1;

  const pointCols = [
    { label: 'Точка', primary: true, render: (p) => p.name },
    { label: 'Наличными', numeric: true, render: (p) => dash(p.cash) },
    { label: 'Картой', numeric: true, render: (p) => dash(p.card) },
    ...(hasBank ? [{ label: 'Безнал', numeric: true, render: (p) => dash(p.bank) }] : []),
    { label: 'Возвраты', numeric: true, render: (p) => <span className={p.refunds ? 'pay-neg' : ''}>{minus(p.refunds)}</span> },
    { label: 'Чистый плюс', numeric: true, render: (p) => <b>{rub(p.money)}</b> },
  ];
  const dayCols = [
    { label: 'День', primary: true, render: (d) => dayLabel(d.date) },
    { label: 'Наличными', numeric: true, render: (d) => dash(d.cash) },
    { label: 'Картой', numeric: true, render: (d) => dash(d.card) },
    ...(hasBank ? [{ label: 'Безнал', numeric: true, render: (d) => dash(d.bank) }] : []),
    { label: 'Бонусами', numeric: true, render: (d) => <span className="pay-muted">{dash(d.bonus)}</span> },
    { label: 'Возвраты', numeric: true, render: (d) => <span className={d.refunds ? 'pay-neg' : ''}>{minus(d.refunds)}</span> },
    { label: 'Чистый плюс', numeric: true, render: (d) => <b>{rub(d.money)}</b> },
  ];

  return (
    <div className="space-y-5">
      <TopProgressBar active={loading} />
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <span className="ui-eyebrow mb-3">Период · {range[0] === range[1] ? dayLabel(range[0]) : `${dayLabel(range[0])} — ${dayLabel(range[1])}`}</span>
          <h2 className="text-2xl font-bold">Оплаты</h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5 max-w-[70ch]">
            Деньги, которые пришли от клиентов: предоплаты, доплаты при выдаче, оплата товара. Не выручка.
            Чистый плюс — пришло деньгами минус возвраты; бонусы и депозит — не деньги и в него не входят.
          </p>
        </div>
        <button type="button" onClick={() => load()} disabled={loading} className="btn btn--primary btn--sm flex items-center gap-1.5">
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      <div className="app-card p-4 flex flex-wrap items-end gap-3">
        <div className="flex flex-wrap gap-1.5">
          {QUICK.map(([k, l]) => (
            <button key={k} type="button" onClick={() => { setQuick(k); setRange(quickRange(k)); }}
              className={`pay-chip ${quick === k ? 'is-on' : ''}`}>{l}</button>
          ))}
        </div>
        <label className="pay-date">с
          <input type="date" className="input" value={range[0]} max={range[1]}
            onChange={(e) => { setQuick(''); setRange([e.target.value, range[1]]); }} />
        </label>
        <label className="pay-date">по
          <input type="date" className="input" value={range[1]} min={range[0]}
            onChange={(e) => { setQuick(''); setRange([range[0], e.target.value]); }} />
        </label>
      </div>

      {error && <div className="rounded-lg border border-[color:var(--color-danger)] p-4 text-sm text-[color:var(--color-danger)]">{error}</div>}

      {data && (
        <>
          <div className="pay-stats">
            <Stat label="Наличными" value={rub(kind('cash'))} icon={Banknote} />
            <Stat label="Картой" value={rub(kind('card'))} icon={CreditCard}
              sub={hasBank ? `безнал по счёту ${rub(kind('bank'))}` : null} />
            <Stat label="Бонусами" value={rub(kind('bonus'))} icon={Gift} tone="muted"
              sub={deposit ? `не деньги · депозитом ${rub(deposit)}` : 'не деньги'} />
            <Stat label="Возвраты" value={minus(data.refunds) === '—' ? '0 ₽' : minus(data.refunds)} icon={Undo2} tone="neg" />
            <Stat label="Чистый плюс" value={rub(data.net ?? data.total)} icon={Wallet} tone="net"
              sub={`пришло ${rub(data.received ?? data.total)} − возвраты`} />
          </div>

          <div className="app-card overflow-hidden">
            <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
              <h3 className="font-semibold">По точкам</h3>
              <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">Точка — где приняли оплату, а не где принят заказ.</p>
            </div>
            <div className="p-3">
              <ResponsiveTable data={data.points} keyFn={(p) => p.name} columns={pointCols} emptyText="За период оплат не было" />
            </div>
          </div>

          {multiDay && (
            <div className="app-card overflow-hidden">
              <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                <h3 className="font-semibold">По дням</h3>
              </div>
              <div className="p-3">
                <ResponsiveTable data={data.days} keyFn={(d) => d.date} columns={dayCols} />
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
