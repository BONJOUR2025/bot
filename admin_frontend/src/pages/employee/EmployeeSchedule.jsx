import { useCallback, useEffect, useMemo, useState } from 'react';
import { CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../../api.js';

/** График смен сотрудника.
 *
 *  Один запрос на месяц (`/salon/me/shifts`): свои смены, кто ещё работает в
 *  эти дни и ссылка на файл календаря. Раньше экран спрашивал неделю семью
 *  запросами по дню, и каждый заново разбирал Excel с расписанием — открытие
 *  стоило около 25 секунд.
 *
 *  Вид — месяц целиком: сетка дней, где свои смены закрашены, а под ней
 *  ближайшие смены с точкой и часами. Неделю за неделей приходилось листать,
 *  чтобы просто увидеть, когда следующая смена. */

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const MONTHS_GEN = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];

function pad(n) {
  return String(n).padStart(2, '0');
}

function iso(year, month, day) {
  return `${year}-${pad(month)}-${pad(day)}`;
}

function todayIso() {
  const d = new Date();
  return iso(d.getFullYear(), d.getMonth() + 1, d.getDate());
}

// День недели считаем от «ГГГГ-ММ-ДД» в UTC: часовой пояс телефона не должен
// сдвигать колонку в сетке.
function weekdayIndex(isoDate) {
  const [y, m, d] = isoDate.split('-').map(Number);
  return (new Date(Date.UTC(y, m - 1, d)).getUTCDay() + 6) % 7;
}

function dayLabel(isoDate) {
  const [, m, d] = isoDate.split('-').map(Number);
  return `${d} ${MONTHS_GEN[m - 1]}, ${WEEKDAYS[weekdayIndex(isoDate)].toLowerCase()}`;
}

export default function EmployeeSchedule() {
  const now = new Date();
  const [view, setView] = useState({ year: now.getFullYear(), month: now.getMonth() + 1 });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [openDay, setOpenDay] = useState(null);

  const load = useCallback((year, month) => {
    setLoading(true);
    setError('');
    api
      .get('/salon/me/shifts', { params: { year, month } })
      .then((res) => setData(res.data))
      .catch((err) => {
        setData(null);
        setError(
          err?.response?.status === 404
            ? 'Вы не закреплены за точкой — попросите руководителя проставить её в вашей карточке.'
            : 'Не удалось загрузить график. Попробуйте ещё раз.',
        );
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load(view.year, view.month);
  }, [load, view]);

  const shiftByDay = useMemo(() => {
    const map = new Map();
    (data?.days || []).forEach((d) => map.set(d.date, d));
    return map;
  }, [data]);

  const today = todayIso();
  const daysInMonth = new Date(view.year, view.month, 0).getDate();
  const firstWeekday = weekdayIndex(iso(view.year, view.month, 1));
  const cells = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => iso(view.year, view.month, i + 1)),
  ];

  const upcoming = (data?.days || []).filter((d) => d.date >= today).slice(0, 6);
  const shown = openDay ? [shiftByDay.get(openDay)].filter(Boolean) : upcoming;

  const step = (delta) => {
    setOpenDay(null);
    setView(({ year, month }) => {
      const m = month + delta;
      if (m < 1) return { year: year - 1, month: 12 };
      if (m > 12) return { year: year + 1, month: 1 };
      return { year, month: m };
    });
  };

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">График</h2>
        <div className="emp-schedule-nav">
          <button type="button" className="icon-button" onClick={() => step(-1)} aria-label="Предыдущий месяц">
            <ChevronLeft size={18} />
          </button>
          <span className="emp-schedule-nav__label">{MONTHS[view.month - 1]} {view.year}</span>
          <button type="button" className="icon-button" onClick={() => step(1)} aria-label="Следующий месяц">
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {loading && !data && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {data && !error && (
        <div className="emp-sched" style={loading ? { opacity: 0.5 } : undefined}>
          {data.count > 0 && (
            <section className="emp-shifts-card">
              <div className="emp-shifts-card__text">
                <b>{data.count} смен в этом месяце</b>
                <span>
                  {data.next
                    ? `Ближайшая ${dayLabel(data.next.date)}, ${data.next.point}, с ${data.next.start}`
                    : 'Смены можно перенести в календарь телефона'}
                </span>
              </div>
              <a className="emp-shifts-card__btn" href={data.ics_url}>
                <CalendarPlus size={18} aria-hidden="true" />
                В календарь
              </a>
            </section>
          )}

          <section className="emp-salary-card emp-sched__month">
            <div className="emp-sched__grid">
              {WEEKDAYS.map((w) => <div key={w} className="emp-sched__wd">{w}</div>)}
              {cells.map((date, i) => {
                if (!date) return <div key={`gap-${i}`} className="emp-sched__cell emp-sched__cell--empty" />;
                const shift = shiftByDay.get(date);
                const classes = [
                  'emp-sched__cell',
                  shift ? 'is-shift' : '',
                  date === today ? 'is-today' : '',
                  openDay === date ? 'is-open' : '',
                ].filter(Boolean).join(' ');
                return (
                  <button
                    key={date}
                    type="button"
                    className={classes}
                    aria-pressed={openDay === date}
                    aria-label={`${dayLabel(date)}${shift ? `, смена ${shift.point}` : ''}`}
                    onClick={() => setOpenDay((cur) => (cur === date ? null : date))}
                  >
                    <span>{Number(date.slice(8))}</span>
                    {shift && <i aria-hidden="true" />}
                  </button>
                );
              })}
            </div>
            <div className="emp-sched__legend">
              <span><i className="is-shift" aria-hidden="true" /> моя смена</span>
              <span><i className="is-today" aria-hidden="true" /> сегодня</span>
              <span>нажмите на день, чтобы увидеть, кто работает</span>
            </div>
          </section>

          <section className="emp-sched__list">
            <div className="emp-salary-section__title">
              {openDay ? dayLabel(openDay) : 'Ближайшие смены'}
            </div>
            {shown.length === 0 && (
              <p className="emp-page__empty">
                {openDay ? 'В этот день у вас смены нет.' : 'Смен в этом месяце больше нет.'}
              </p>
            )}
            {shown.map((d) => (
              <div key={d.date} className="emp-salary-card emp-sched__row">
                <div className="emp-sched__row-day">
                  <b>{Number(d.date.slice(8))}</b>
                  <span>{WEEKDAYS[weekdayIndex(d.date)].toLowerCase()}</span>
                </div>
                <div className="emp-sched__row-main">
                  <div className="emp-sched__row-point">{d.point}</div>
                  <div className="emp-sched__row-time">с {d.start} до {d.end}</div>
                </div>
                {d.date === today && <span className="badge badge--info">сегодня</span>}
              </div>
            ))}

            {openDay && (data.roster?.[openDay] || []).length > 0 && (
              <div className="emp-salary-card emp-sched__roster">
                <div className="emp-salary-section__title">Кто работает</div>
                {data.roster[openDay].map((r, i) => (
                  <div key={`${r.point}-${i}`} className="emp-sched__roster-row">
                    <span>{r.point}</span>
                    <span>{r.employee}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
