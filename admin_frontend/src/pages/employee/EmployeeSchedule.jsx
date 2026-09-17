import { useEffect, useState } from 'react';
import { CalendarPlus, ChevronLeft, ChevronRight } from 'lucide-react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

function pad(n) {
  return String(n).padStart(2, '0');
}

function toIso(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function addDays(d, n) {
  const r = new Date(d);
  r.setDate(r.getDate() + n);
  return r;
}

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const MONTHS = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];

/** Смены месяца в календарь телефона.
 *
 *  Сервер отдаёт файл .ics по подписанной ссылке (у внешнего браузера сессии
 *  кабинета нет), телефон открывает его календарём: смена со своими часами и
 *  напоминанием за час. Кнопка молчит, если смен в этом месяце нет — незачем
 *  предлагать пустой файл. */
function ShiftsToCalendar({ month, year }) {
  const [state, setState] = useState(null);

  useEffect(() => {
    let alive = true;
    setState(null);
    api
      .get('/salon/me/shifts', { params: { year, month } })
      .then((res) => alive && setState(res.data))
      .catch(() => alive && setState({ count: 0, unavailable: true }));
    return () => {
      alive = false;
    };
  }, [month, year]);

  if (!state || state.unavailable || !state.count) return null;

  const next = state.next;
  return (
    <div className="emp-shifts-card">
      <div className="emp-shifts-card__text">
        <b>{state.count} смен в этом месяце</b>
        <span>
          {next
            ? `Ближайшая: ${new Date(next.date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })}, ${next.point}, с ${next.start}`
            : 'Смены можно перенести в календарь телефона'}
        </span>
      </div>
      <a className="emp-shifts-card__btn" href={state.ics_url}>
        <CalendarPlus size={18} aria-hidden="true" />
        В календарь
      </a>
    </div>
  );
}

export default function EmployeeSchedule() {
  const { user } = useAuth();
  const employeeName = user?.display_name || user?.login || '';

  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const [viewDate, setViewDate] = useState(today);
  const [scheduleCache, setScheduleCache] = useState({});
  const [loading, setLoading] = useState(false);

  // Get first day of week (Monday) for the displayed week
  const dayOfWeek = (viewDate.getDay() + 6) % 7; // 0=Mon
  const weekStart = addDays(viewDate, -dayOfWeek);

  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));

  const fetchDay = async (date) => {
    const key = toIso(date);
    if (scheduleCache[key] !== undefined) return;
    try {
      const res = await api.get('/schedule/by_day', { params: { date: key } });
      setScheduleCache((prev) => ({ ...prev, [key]: res.data || [] }));
    } catch {
      setScheduleCache((prev) => ({ ...prev, [key]: [] }));
    }
  };

  useEffect(() => {
    setLoading(true);
    Promise.all(weekDays.map(fetchDay)).finally(() => setLoading(false));
  }, [weekStart.toISOString()]);

  const prevWeek = () => setViewDate((d) => addDays(d, -7));
  const nextWeek = () => setViewDate((d) => addDays(d, 7));

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">График</h2>
        <div className="emp-schedule-nav">
          <button type="button" className="icon-button" onClick={prevWeek}>
            <ChevronLeft size={18} />
          </button>
          <span className="emp-schedule-nav__label">
            {MONTHS[weekStart.getMonth()]} {weekStart.getFullYear()}
          </span>
          <button type="button" className="icon-button" onClick={nextWeek}>
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      <ShiftsToCalendar month={weekStart.getMonth() + 1} year={weekStart.getFullYear()} />

      {loading && <p className="emp-page__loading">Загрузка…</p>}

      <div className="emp-schedule-week">
        {weekDays.map((day, i) => {
          const key = toIso(day);
          const points = scheduleCache[key] || [];
          const isToday = toIso(day) === toIso(today);

          // Check if this employee works on this day
          const myPoints = employeeName
            ? points.filter((p) =>
                p.employee?.toLowerCase().includes(employeeName.toLowerCase()) ||
                employeeName.toLowerCase().includes(p.employee?.toLowerCase())
              )
            : [];
          const works = myPoints.length > 0;

          return (
            <div
              key={key}
              className={`emp-schedule-day ${isToday ? 'emp-schedule-day--today' : ''} ${works ? 'emp-schedule-day--work' : ''}`}
            >
              <div className="emp-schedule-day__head">
                <span className="emp-schedule-day__wd">{WEEKDAYS[i]}</span>
                <span className="emp-schedule-day__date">{pad(day.getDate())}.{pad(day.getMonth() + 1)}</span>
              </div>
              <div className="emp-schedule-day__body">
                {works ? (
                  myPoints.map((p, idx) => (
                    <div key={idx} className="emp-schedule-day__point">{p.point}</div>
                  ))
                ) : (
                  <span className="emp-schedule-day__off">—</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="emp-schedule-legend">
        <span className="emp-schedule-legend__work">Рабочий день</span>
        <span className="emp-schedule-legend__today">Сегодня</span>
      </div>

      <div className="emp-schedule-all">
        <h3 className="emp-schedule-all__title">Расписание на неделю</h3>
        {weekDays.map((day) => {
          const key = toIso(day);
          const points = scheduleCache[key] || [];
          if (points.length === 0) return null;
          return (
            <div key={key} className="emp-schedule-table-row">
              <div className="emp-schedule-table-row__date">
                {pad(day.getDate())}.{pad(day.getMonth() + 1)} {WEEKDAYS[(day.getDay() + 6) % 7]}
              </div>
              <div className="emp-schedule-table-row__points">
                {points.map((p, i) => (
                  <div key={i} className="emp-schedule-point">
                    <span className="emp-schedule-point__loc">{p.point}</span>
                    <span className="emp-schedule-point__emp">{p.employee}</span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
