import { useEffect, useMemo, useState } from 'react';
import { Calendar } from 'lucide-react';
import api from '../api';

const pad = (value) => String(value).padStart(2, '0');

function ruDaysWord(n) {
  const abs = Math.abs(n) % 100;
  const last = abs % 10;
  if (abs > 10 && abs < 20) return 'дней';
  if (last === 1) return 'день';
  if (last >= 2 && last <= 4) return 'дня';
  return 'дней';
}

// birthdate приходит от API как 'YYYY-MM-DD' — разбираем строкой, а не
// через `new Date(...)`, чтобы не словить сдвиг на сутки от часового
// пояса при вычислении месяца/дня.
function parseISODate(value) {
  if (!value) return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  return { year: y, month: m, day: d };
}

// Ближайшее наступление дня рождения относительно `today`: в этом году,
// либо в следующем, если дата в этом году уже прошла.
function nextOccurrence(value, today) {
  const p = parseISODate(value);
  if (!p) return null;
  const todayMid = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  let occ = new Date(today.getFullYear(), p.month - 1, p.day);
  if (occ < todayMid) occ = new Date(today.getFullYear() + 1, p.month - 1, p.day);
  return occ;
}

function daysUntil(value, today) {
  const occ = nextOccurrence(value, today);
  if (!occ) return null;
  const todayMid = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((occ - todayMid) / 86400000);
}

// Уровень заполнения индикатора «близости» — 0..4 столбика, чем ближе
// дата, тем больше заполнено (по аналогии со шкалой уровня сигнала).
function proximityTier(days) {
  if (days <= 3) return 4;
  if (days <= 7) return 3;
  if (days <= 14) return 2;
  if (days <= 30) return 1;
  return 0;
}

export default function Birthdays() {
  const [list, setList] = useState([]);
  // Живые часы для ростер-телеметрии страницы — не декоративные, а
  // реальное текущее время, относительно которого считаются
  // «сегодня»/«в этом месяце» и близость дат ниже.
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  async function load() {
    try {
      const res = await api.get('birthdays/', { params: { days: 365 } });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function formatDateRu(value) {
    return new Date(value).toLocaleDateString('ru-RU', {
      day: 'numeric',
      month: 'long',
    });
  }

  // Реальные агрегаты по текущему списку/времени — сколько дней
  // рождения сегодня и сколько попадает на текущий календарный месяц
  // (по фактической дате рождения, а не по ближайшему наступлению).
  const { todayCount, monthCount } = useMemo(() => {
    let todays = 0;
    let inMonth = 0;
    for (const b of list) {
      const p = parseISODate(b.birthdate);
      if (!p) continue;
      if (p.month === now.getMonth() + 1) inMonth += 1;
      if (daysUntil(b.birthdate, now) === 0) todays += 1;
    }
    return { todayCount: todays, monthCount: inMonth };
  }, [list, now]);

  return (
    <div className="space-y-6 max-w-3xl mx-auto">
      <div>
        <span className="ui-eyebrow mb-3">
          {list.length ? `В списке: ${list.length}` : 'Список пуст'}
        </span>
        <h2 className="text-2xl font-semibold">Дни рождения сотрудников</h2>
      </div>

      {/* Ростер-телеметрия: живые часы + реальные счётчики «сегодня»/
          «в этом месяце», а не декоративные цифры. */}
      <div className="birthday-fui-strip">
        <span className="birthday-fui-strip__clock">
          {pad(now.getHours())}
          <span className="birthday-fui-strip__colon">:</span>
          {pad(now.getMinutes())}
          <span className="birthday-fui-strip__colon">:</span>
          {pad(now.getSeconds())}
        </span>
        <span className="sep">·</span>
        <span>
          СЕГОДНЯ: <b className={todayCount > 0 ? 'birthday-fui-today-count' : ''}>{todayCount}</b>
        </span>
        <span className="sep">·</span>
        <span>
          В ЭТОМ МЕСЯЦЕ: <b>{monthCount}</b>
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {list.map((b) => {
          const days = daysUntil(b.birthdate, now);
          const isToday = days === 0;
          const filled = days == null ? 0 : proximityTier(days);
          return (
            <div
              key={b.user_id}
              className="bg-[color:var(--color-surface)] rounded border shadow p-3 flex items-center justify-between"
            >
              <div className="flex flex-col">
                <span className="font-medium flex items-center gap-2">
                  {/* Тёплый пинг только на реальном совпадении даты —
                      день рождения именно сегодня, не «скоро». */}
                  {isToday && (
                    <span className="birthday-fui-pulse"><i /><i /><i /><b /></span>
                  )}
                  {b.full_name}
                </span>
                {b.phone && (
                  <span className="text-[color:var(--color-text-muted)] text-sm">{b.phone}</span>
                )}
              </div>
              <div className="flex items-center gap-3 text-sm">
                {isToday ? (
                  <span className="birthday-fui-today-tag">🎉 Сегодня</span>
                ) : days != null && (
                  <span
                    className="birthday-fui-proximity"
                    title={`Через ${days} ${ruDaysWord(days)}`}
                  >
                    {[1, 2, 3, 4].map((n) => (
                      <i key={n} className={n <= filled ? 'is-filled' : ''} />
                    ))}
                    <span className="birthday-fui-proximity__days">{days}д</span>
                  </span>
                )}
                <span className="flex items-center gap-1 text-[color:var(--color-text-muted)]">
                  <Calendar size={16} /> {formatDateRu(b.birthdate)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
