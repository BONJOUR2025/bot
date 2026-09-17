import { useCallback, useEffect, useState } from 'react';
import { Phone, RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { masterErrorText, money } from './masterFormat.js';

/** Заказы точки (GET /api/salon/me/orders → salon_self_service.orders).
 *
 *  Две стопки, потому что это две разные задачи: «Готовы» — позвонить клиенту,
 *  чтобы забрал; «В работе» — проследить за сроком. Готовый заказ с прошедшим
 *  сроком не просрочка мастерской, а вещь, за которой не пришли, поэтому у него
 *  своя подпись «ждёт N дней». */

const TABS = [
  { key: 'ready', label: 'Готовы к выдаче' },
  { key: 'work', label: 'В работе' },
];

function hhmm(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function dueBadge(it) {
  if (it.due_state === 'overdue') {
    return {
      cls: 'badge--error',
      label: it.overdue_days > 0 ? `Просрочен на ${it.overdue_days} дн` : `Просрочен с ${hhmm(it.due)}`,
    };
  }
  if (it.due_state === 'today') return { cls: 'badge--warning', label: `Сегодня до ${hhmm(it.due)}` };
  if (it.due_state === 'tomorrow') return { cls: 'badge--info', label: `Завтра до ${hhmm(it.due)}` };
  return null;
}

function waitBadge(days) {
  if (days == null) return null;
  if (days >= 30) return { cls: 'badge--error', label: `Ждёт ${days} дн` };
  if (days >= 7) return { cls: 'badge--warning', label: `Ждёт ${days} дн` };
  return { cls: 'badge--info', label: days > 0 ? `Ждёт ${days} дн` : 'Готов сегодня' };
}

function telHref(phone) {
  const digits = String(phone || '').replace(/\D/g, '');
  if (digits.length < 10) return null;
  return `tel:+${digits.length === 11 ? digits.replace(/^8/, '7') : digits}`;
}

export default function SalonOrders() {
  const [tab, setTab] = useState('ready');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    api
      .get('/salon/me/orders')
      .then((res) => setData(res.data))
      .catch((err) => {
        setData(null);
        setError(masterErrorText(err));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const counts = data?.counts || {};
  const items = data?.[tab] || [];

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Заказы</h2>
        <button type="button" className="icon-button" onClick={load} disabled={loading} aria-label="Обновить">
          <RefreshCw size={18} />
        </button>
      </div>

      {loading && !data && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {data && !error && (
        <div style={loading ? { opacity: 0.5 } : undefined}>
          <div className="emp-earn-periods salon-tabs" role="group" aria-label="Что показать">
            {TABS.map((t) => (
              <button key={t.key} type="button" aria-pressed={tab === t.key} onClick={() => setTab(t.key)}>
                {t.label} <b>{t.key === 'ready' ? counts.ready || 0 : counts.work || 0}</b>
              </button>
            ))}
          </div>

          {tab === 'work' && counts.overdue > 0 && (
            <div className="emp-wip-alert" role="status">
              <b>Просрочено: {counts.overdue}</b>
              {counts.today > 0 && <span>Сдать сегодня: {counts.today}</span>}
            </div>
          )}
          {tab === 'ready' && counts.ready > 0 && (
            <p className="emp-page__empty">
              Позвоните клиентам — сверху те, кто не забирает дольше всех.
            </p>
          )}

          {items.length === 0 && (
            <p className="emp-page__empty">
              {tab === 'ready' ? 'Готовых к выдаче заказов нет.' : 'В работе заказов нет.'}
            </p>
          )}

          <div className="emp-list">
            {items.map((it) => {
              const badge = tab === 'ready' ? waitBadge(it.waiting_days) : dueBadge(it);
              const burning = it.due_state === 'overdue' || it.due_state === 'today';
              const tel = telHref(it.phone);
              return (
                <div
                  key={it.doc_num}
                  className={`emp-payout-item${burning ? ` emp-wip-item--${it.due_state}` : ''}`}
                >
                  <div className="emp-payout-item__top">
                    <span className="emp-payout-item__amount">{it.doc_num}</span>
                    {badge && <span className={`badge ${badge.cls}`}>{badge.label}</span>}
                  </div>
                  <div className="emp-payout-item__details">
                    <span>{it.client}</span>
                    <span>{money(it.kredit)}</span>
                  </div>
                  <div className="salon-order__foot">
                    <span>
                      {it.due ? `срок ${new Date(it.due).toLocaleDateString('ru-RU')}` : 'срок не указан'}
                      {it.photos > 0 ? ` · ${it.photos} фото` : ''}
                    </span>
                    {tel && (
                      <a className="salon-order__call" href={tel}>
                        <Phone size={14} aria-hidden="true" />
                        Позвонить
                      </a>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
