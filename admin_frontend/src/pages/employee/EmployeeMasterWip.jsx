import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { PhotoViewer } from '../../components/OrderPhotos.jsx';
import { masterErrorText, money, serviceTitle } from './masterFormat.js';

/** Что на мастере висит — принятые и не сданные услуги
 *  (GET /api/masters/me/wip → master_bot_service.get_wip).
 *
 *  Сверху — горящие: обещанная клиенту дата уже прошла или наступает сегодня.
 *  Срок — тот же DATE_OUT заказа, по которому считаются просрочки. */

// Полный размер — через адрес кабинета мастера: он отдаёт только фото
// изделий из работ самого мастера.
const masterPhotoPath = (p) => `/masters/me/photos/${p.id}/full?md5=${encodeURIComponent(p.md5)}`;

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
export default function EmployeeMasterWip() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  // Просмотр фото изделия: { photos, index } или null.
  const [viewer, setViewer] = useState(null);

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
  const overdue = items.filter((it) => it.due_state === 'overdue').length;
  const dueToday = items.filter((it) => it.due_state === 'today').length;

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
          {(overdue > 0 || dueToday > 0) && (
            <div className="emp-wip-alert" role="status">
              {overdue > 0 && <b>Просрочено: {overdue}</b>}
              {dueToday > 0 && <span>Сдать сегодня: {dueToday}</span>}
            </div>
          )}
          <p className="emp-page__empty">
            {items.length} шт на {money(total)}. Сверху горящие по сроку и срочные, дальше — те, что ждут дольше всех.
          </p>
          <div className="emp-list">
            {items.map((it, idx) => {
              const due = dueBadge(it);
              let age = null;
              if (it.urgent) age = { cls: 'badge--error', label: 'Срочно' };
              else if (it.days != null && !due) {
                age = { cls: it.days >= 7 ? 'badge--warning' : 'badge--info', label: `${it.days} дн` };
              }
              const burning = it.due_state === 'overdue' || it.due_state === 'today';
              return (
                <div
                  key={`${it.doc_num}-${idx}`}
                  className={`emp-payout-item${burning ? ` emp-wip-item--${it.due_state}` : ''}`}
                >
                  <div className="emp-wip-row">
                    {it.photos?.[0]?.thumb ? (
                      <button
                        type="button"
                        className="emp-wip-photo"
                        onClick={() => setViewer({ photos: it.photos, index: 0 })}
                        aria-label={`Фото изделия, заказ ${it.doc_num}`}
                      >
                        <img src={it.photos[0].thumb} alt="" />
                        {it.photos.length > 1 && <span>{it.photos.length}</span>}
                      </button>
                    ) : (
                      <div className="emp-wip-photo emp-wip-photo--none" aria-hidden="true">нет фото</div>
                    )}
                    <div className="emp-wip-main">
                      <div className="emp-payout-item__top">
                        <span className="emp-payout-item__amount">{it.doc_num}</span>
                        <span className="emp-wip-badges">
                          {due && <span className={`badge ${due.cls}`}>{due.label}</span>}
                          {age && <span className={`badge ${age.cls}`}>{age.label}</span>}
                        </span>
                      </div>
                      <div className="emp-payout-item__details">
                        <span>{serviceTitle(it.name)}</span>
                        <span>{money(it.kredit)}</span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
          {viewer && (
            <PhotoViewer
              photos={viewer.photos}
              index={viewer.index}
              onIndex={(index) => setViewer((v) => (v ? { ...v, index } : v))}
              onClose={() => setViewer(null)}
              pathFor={masterPhotoPath}
            />
          )}
        </>
      )}
    </div>
  );
}
