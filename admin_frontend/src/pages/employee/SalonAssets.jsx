import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { masterErrorText } from './masterFormat.js';

/** Что числится за сотрудником: форма, инструмент, техника
 *  (GET /api/salon/me/assets → asset_repository). Список только для чтения:
 *  выдаёт и списывает имущество руководитель в панели. */

function dateText(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleDateString('ru-RU');
}

export default function SalonAssets() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    api
      .get('/salon/me/assets')
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

  const active = items.filter((it) => !it.return_date);
  const returned = items.filter((it) => it.return_date);

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Имущество</h2>
        <button type="button" className="icon-button" onClick={load} disabled={loading} aria-label="Обновить">
          <RefreshCw size={18} />
        </button>
      </div>

      {loading && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {!loading && !error && items.length === 0 && (
        <p className="emp-page__empty">За вами ничего не числится.</p>
      )}

      {active.length > 0 && (
        <>
          <p className="emp-page__empty">На руках: {active.length}</p>
          <div className="emp-list">
            {active.map((it) => (
              <div key={it.id} className="emp-payout-item">
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{it.name || 'Без названия'}</span>
                  {!it.acked && <span className="badge badge--warning">Не подтверждено</span>}
                </div>
                <div className="emp-payout-item__details">
                  <span>
                    {[it.size ? `размер ${it.size}` : null, it.quantity > 1 ? `${it.quantity} шт` : null]
                      .filter(Boolean)
                      .join(' · ') || 'выдано'}
                  </span>
                  <span>{dateText(it.issue_date) || ''}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {returned.length > 0 && (
        <>
          <p className="emp-page__empty" style={{ marginTop: '1rem' }}>Сдано: {returned.length}</p>
          <div className="emp-list">
            {returned.map((it) => (
              <div key={it.id} className="emp-payout-item">
                <div className="emp-payout-item__top">
                  <span className="emp-payout-item__amount">{it.name || 'Без названия'}</span>
                  <span className="badge badge--success">Сдано {dateText(it.return_date)}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
