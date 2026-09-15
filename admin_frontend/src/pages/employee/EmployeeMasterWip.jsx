import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { masterErrorText, money, serviceTitle } from './masterFormat.js';

/** Что на мастере висит — принятые и не сданные услуги
 *  (GET /api/masters/me/wip → master_bot_service.get_wip). */
export default function EmployeeMasterWip() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    api
      .get('/masters/me/wip')
      .then((res) => setItems(res.data?.items || []))
      .catch((err) => {
        setItems([]);
        setError(masterErrorText(err));
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const total = items.reduce((sum, it) => sum + (Number(it.kredit) || 0), 0);

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">В работе</h2>
        <button
          type="button"
          className="icon-button"
          onClick={load}
          disabled={loading}
          aria-label="Обновить"
        >
          <RefreshCw size={18} />
        </button>
      </div>

      {loading && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className="emp-page__empty">Незакрытых работ нет — всё сдано.</p>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <p className="emp-page__empty">
            {items.length} шт на {money(total)}. Сверху срочные, дальше — те, что ждут дольше всех.
          </p>
          <div className="emp-list">
            {items.map((it, idx) => {
              let badge = null;
              if (it.urgent) badge = { cls: 'badge--error', label: 'Срочно' };
              else if (it.days != null) {
                badge = { cls: it.days >= 7 ? 'badge--warning' : 'badge--info', label: `${it.days} дн` };
              }
              return (
                <div key={`${it.doc_num}-${idx}`} className="emp-payout-item">
                  <div className="emp-payout-item__top">
                    <span className="emp-payout-item__amount">{it.doc_num}</span>
                    {badge && <span className={`badge ${badge.cls}`}>{badge.label}</span>}
                  </div>
                  <div className="emp-payout-item__details">
                    <span>{serviceTitle(it.name)}</span>
                    <span>{money(it.kredit)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
