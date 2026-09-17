import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { masterErrorText, money } from './masterFormat.js';

/** Главный экран администратора точки: смена и выручка
 *  (GET /api/salon/me/point и /sales → salon_self_service).
 *
 *  Порядок — как вопросы на смене: открыта ли смена → сколько наторговали
 *  сегодня → как это выглядит на фоне месяца. Точку сервер берёт из карточки
 *  сотрудника, выбрать чужую нельзя. */

const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];

function timeText(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function dayNum(iso) {
  return Number(String(iso).slice(8, 10));
}

/** Выручка по дням месяца: столбик на день, сегодня — темнее. */
function SalesBars({ days }) {
  if (!days?.length) return null;
  const max = days.reduce((m, d) => Math.max(m, d.total), 0) || 1;
  const today = days[days.length - 1]?.day;
  return (
    <div className="salon-bars" role="img" aria-label="Выручка по дням месяца">
      {days.map((d) => (
        <div key={d.day} className="salon-bars__col" title={`${dayNum(d.day)} — ${money(d.total)}`}>
          <div
            className={`salon-bars__bar${d.day === today ? ' is-today' : ''}`}
            style={{ height: `${Math.max(3, Math.round((d.total / max) * 100))}%` }}
          />
          <span>{dayNum(d.day)}</span>
        </div>
      ))}
    </div>
  );
}

export default function SalonShift() {
  const [point, setPoint] = useState(null);
  const [sales, setSales] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([api.get('/salon/me/point'), api.get('/salon/me/sales')])
      .then(([p, s]) => {
        setPoint(p.data);
        setSales(s.data);
      })
      .catch((err) => setError(masterErrorText(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const shift = point?.shift;
  const now = new Date();

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">{point?.point?.name || 'Смена'}</h2>
        <button type="button" className="icon-button" onClick={load} disabled={loading} aria-label="Обновить">
          <RefreshCw size={18} />
        </button>
      </div>

      {loading && !point && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {point && !error && (
        <div className="emp-earn" style={loading ? { opacity: 0.5 } : undefined}>
          <section className={`emp-salary-card salon-shift${shift?.opened ? ' is-open' : ''}`}>
            <div className="salon-shift__label">
              Смена {WEEKDAYS[now.getDay()]}, {now.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}
            </div>
            {shift?.opened ? (
              <>
                <div className="salon-shift__state">Открыта в {timeText(shift.sent_at)}</div>
                <div className="salon-shift__sub">
                  {shift.delay_minutes > 0
                    ? `Опоздание ${shift.delay_minutes} мин${shift.penalty_amount ? ` · штраф ${money(shift.penalty_amount)}` : ''}`
                    : `Вовремя${shift.expected_open_time ? `, открытие в ${shift.expected_open_time}` : ''}`}
                </div>
              </>
            ) : (
              <>
                <div className="salon-shift__state salon-shift__state--wait">Ещё не открыта</div>
                <div className="salon-shift__sub">
                  {shift?.expected_open_time ? `Открытие в ${shift.expected_open_time}. ` : ''}
                  Отметьте открытие с фото в Telegram-боте — кнопка «Открыть салон».
                </div>
              </>
            )}
          </section>

          <section className="emp-salary-card emp-earn-hero">
            <div className="emp-earn-hero__label">Выручка сегодня</div>
            <div className="emp-earn-hero__sum">{money(sales?.today)}</div>
            <div className="emp-earn-hero__sub">
              {point.point.address || point.point.name}
            </div>
            <div className="emp-earn-tiles">
              <div className="emp-earn-tile">
                <span>Вчера</span>
                <b>{money(sales?.yesterday)}</b>
              </div>
              <div className="emp-earn-tile">
                <span>За месяц</span>
                <b>{money(sales?.month)}</b>
                <small>{sales?.month_days || 0} дн</small>
              </div>
              <div className="emp-earn-tile">
                <span>В день</span>
                <b>{money(sales?.avg_day)}</b>
                <small>в среднем</small>
              </div>
            </div>
          </section>

          {sales?.days?.length > 0 && (
            <section className="emp-salary-card emp-earn-block--card">
              <div className="emp-salary-section__title">По дням месяца</div>
              <SalesBars days={sales.days} />
            </section>
          )}

          <p className="emp-earn-note">
            Выручка считается так же, как в отчёте «Продажи» у руководителя: по номеру заказа вашей точки.
          </p>
        </div>
      )}
    </div>
  );
}
