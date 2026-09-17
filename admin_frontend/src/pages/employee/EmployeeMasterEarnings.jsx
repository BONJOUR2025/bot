import { useEffect, useMemo, useRef, useState } from 'react';
import { X } from 'lucide-react';
import api from '../../api.js';
import { masterErrorText, money, serviceTitle } from './masterFormat.js';

/** Заработок мастера — те же цифры, что «🔧 Мой заработок» в Telegram-боте
 *  (GET /api/masters/me/earnings → master_bot_service.get_earnings).
 *
 *  Страница отвечает на вопросы мастера в том порядке, в каком он их задаёт:
 *  сколько я заработал (одно крупное число) → сколько сегодня и вчера →
 *  сколько получу с учётом авансов → по каким дням и видам работ → какие
 *  именно услуги. «Сумма работ» (цена услуг для клиента) больше не стоит
 *  рядом с заработком: крупное чужое число рядом со своим сбивало с толку. */

// Только прогретые периоды: всё остальное ушло бы живым запросом в самый
// дорогой отчёт системы (см. master_bot_service).
const PERIODS = [
  { value: 'month', label: 'Этот месяц' },
  { value: 'prev_month', label: 'Прошлый' },
];

const MONTHS_IN = [
  'январе', 'феврале', 'марте', 'апреле', 'мае', 'июне',
  'июле', 'августе', 'сентябре', 'октябре', 'ноябре', 'декабре',
];
const MONTHS_GEN = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const DAY_MS = 24 * 60 * 60 * 1000;
const PAGE_SIZE = 30;

// Дни считаем в UTC от строки «ГГГГ-ММ-ДД»: так часовой пояс телефона не
// сдвигает услугу, выданную около полуночи, на соседний день.
function dayUtc(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}
const isoFromUtc = (ms) => new Date(ms).toISOString().slice(0, 10);
const dayOfMonth = (iso) => new Date(dayUtc(iso)).getUTCDate();

function localIso(offsetDays = 0) {
  const d = new Date(Date.now() + offsetDays * DAY_MS);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function monthIn(isoDate) {
  if (!isoDate) return '';
  const [, m] = String(isoDate).split('-').map(Number);
  return MONTHS_IN[m - 1];
}

function dayShort(iso) {
  const dt = new Date(dayUtc(iso));
  return `${dt.getUTCDate()} ${MONTHS_GEN[dt.getUTCMonth()]}`;
}

function dayTitle(iso) {
  if (!iso || iso === '—') return 'Без даты выдачи';
  if (iso === localIso(0)) return `Сегодня, ${dayShort(iso)}`;
  if (iso === localIso(-1)) return `Вчера, ${dayShort(iso)}`;
  const dt = new Date(dayUtc(iso));
  return `${dayShort(iso)}, ${WEEKDAYS[dt.getUTCDay()]}`;
}

function countText(n) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return `${n} услуга`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${n} услуги`;
  return `${n} услуг`;
}

// Верх шкалы — «круглое» число, чтобы подписи сетки читались без усилия.
function niceCeil(v) {
  if (!(v > 0)) return 0;
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const k of [1, 2, 4, 5, 10]) {
    if (k * pow >= v) return k * pow;
  }
  return 10 * pow;
}

// Столбец со скруглённым верхом (4px) и прямым основанием.
function barPath(x, y, w, h) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
}

const CHART_H = 140;
const AXIS_H = 22;
const PAD_TOP = 22;
const PAD_LEFT = 46;
const PAD_RIGHT = 6;

/** Заработок по дням. Нажатие на столбец выбирает день — список услуг ниже
 *  оставляет только его; повторное нажатие снимает выбор. */
function DaysChart({ series, selectedDay, onSelectDay }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(320);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const update = () => setWidth(Math.max(240, Math.round(el.getBoundingClientRect().width)));
    update();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (series.length === 0) return null;

  const plotW = Math.max(40, width - PAD_LEFT - PAD_RIGHT);
  const plotH = CHART_H - PAD_TOP;
  const maxV = series.reduce((m, s) => Math.max(m, s.value), 0);
  const top = niceCeil(maxV);
  const ticks = top > 0 ? [0, top / 2, top] : [0];
  const slot = plotW / series.length;
  const barW = Math.max(2, Math.min(24, slot - 2));
  const yOf = (v) => PAD_TOP + plotH - (top ? (v / top) * plotH : 0);
  const cx = (i) => PAD_LEFT + i * slot + slot / 2;
  const clampX = (x) => Math.min(Math.max(x, 64), width - 64);
  const selected = selectedDay ? series.findIndex((s) => s.day === selectedDay) : -1;
  const peak = maxV > 0 ? series.findIndex((s) => s.value === maxV) : -1;
  const today = localIso(0);
  const last = series.length - 1;
  const labeled = new Set([last]);
  series.forEach((s, i) => {
    if ((dayOfMonth(s.day) - 1) % 7 === 0 && last - i >= 3) labeled.add(i);
  });
  const mark = selected >= 0 ? selected : peak;

  return (
    <div className="emp-earn-chart" ref={wrapRef}>
      <svg
        width={width}
        height={CHART_H + AXIS_H}
        viewBox={`0 0 ${width} ${CHART_H + AXIS_H}`}
        role="img"
        aria-label="Заработок по дням"
      >
        {ticks.map((v) => (
          <g key={v}>
            <line className="emp-earn-grid" x1={PAD_LEFT} x2={width - PAD_RIGHT} y1={yOf(v)} y2={yOf(v)} />
            <text x={PAD_LEFT - 6} y={yOf(v) + 3} textAnchor="end">
              {Math.round(v).toLocaleString('ru-RU')}
            </text>
          </g>
        ))}
        {series.map((s, i) => {
          if (s.value <= 0) return null;
          const y = yOf(s.value);
          const x = PAD_LEFT + i * slot + (slot - barW) / 2;
          const dim = selected >= 0 && selected !== i;
          return (
            <path
              key={s.day}
              className={`emp-earn-bar${dim ? ' is-dim' : ''}${s.day === today ? ' is-today' : ''}`}
              d={barPath(x, y, barW, PAD_TOP + plotH - y)}
            />
          );
        })}
        {[...labeled].map((i) => (
          <text key={`x-${i}`} x={cx(i)} y={CHART_H + 15} textAnchor="middle">
            {dayOfMonth(series[i].day)}
          </text>
        ))}
        {mark >= 0 && series[mark].value > 0 && (
          <text className="emp-earn-peak" x={clampX(cx(mark))} y={yOf(series[mark].value) - 7} textAnchor="middle">
            {money(series[mark].value)}
          </text>
        )}
        {series.map((s, i) => (
          <rect
            key={`hit-${s.day}`}
            className="emp-earn-bar-hit"
            x={PAD_LEFT + i * slot}
            y={PAD_TOP}
            width={slot}
            height={plotH}
            tabIndex={s.count ? 0 : -1}
            role="button"
            aria-pressed={selected === i}
            aria-label={`${dayShort(s.day)}: ${money(s.value)}, ${countText(s.count)}`}
            onClick={() => s.count && onSelectDay(selected === i ? null : s.day)}
            onKeyDown={(e) => {
              if ((e.key === 'Enter' || e.key === ' ') && s.count) {
                e.preventDefault();
                onSelectDay(selected === i ? null : s.day);
              }
            }}
          />
        ))}
      </svg>
    </div>
  );
}

export default function EmployeeMasterEarnings() {
  const [period, setPeriod] = useState('month');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [group, setGroup] = useState(null);
  const [day, setDay] = useState(null);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const listRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setGroup(null);
    setDay(null);
    setLimit(PAGE_SIZE);
    api
      .get('/masters/me/earnings', { params: { period } })
      .then((res) => {
        if (!cancelled) setReport(res.data);
      })
      .catch((err) => {
        if (cancelled) return;
        setReport(null);
        setError(masterErrorText(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [period]);

  const r = report;
  // У ученика процент справочный: в подробностях показываем сумму работ.
  const metric = r?.is_apprentice ? 'kredit' : 'salary';
  const all = useMemo(() => r?.services || [], [r]);

  const sumOf = (list) => list.reduce((acc, s) => acc + (Number(s[metric]) || 0), 0);

  const quick = useMemo(() => {
    const byDay = (iso) => all.filter((s) => s.day === iso);
    const workDays = new Set(all.map((s) => s.day).filter(Boolean));
    const total = all.reduce((acc, s) => acc + (Number(s[metric]) || 0), 0);
    return {
      today: byDay(localIso(0)),
      yesterday: byDay(localIso(-1)),
      workDays: workDays.size,
      perDay: workDays.size ? total / workDays.size : 0,
    };
  }, [all, metric]);

  const byGroup = useMemo(() => (group ? all.filter((s) => s.service_group === group) : all), [all, group]);

  const series = useMemo(() => {
    const totals = new Map();
    for (const row of byGroup) {
      if (!row.day) continue;
      const slot = totals.get(row.day) || { value: 0, count: 0 };
      slot.value += Number(row[metric]) || 0;
      slot.count += 1;
      totals.set(row.day, slot);
    }
    const out = [];
    if (!r?.date_from || !r?.date_to) return out;
    for (let t = dayUtc(r.date_from); t <= dayUtc(r.date_to); t += DAY_MS) {
      const iso = isoFromUtc(t);
      const slot = totals.get(iso);
      out.push({ day: iso, value: slot ? slot.value : 0, count: slot ? slot.count : 0 });
    }
    return out;
  }, [byGroup, metric, r]);

  const rows = useMemo(() => (day ? byGroup.filter((s) => s.day === day) : byGroup), [byGroup, day]);

  // Итоги дня — по всем услугам фильтра, а не только по показанным: иначе
  // день, разрезанный кнопкой «Показать ещё», показал бы неполную сумму.
  const dayTotals = useMemo(() => {
    const totals = new Map();
    for (const s of rows) {
      const key = s.day || '—';
      const t = totals.get(key) || { count: 0, value: 0 };
      t.count += 1;
      t.value += Number(s[metric]) || 0;
      totals.set(key, t);
    }
    return totals;
  }, [rows, metric]);

  const dayGroups = [];
  for (const s of rows.slice(0, limit)) {
    const key = s.day || '—';
    const lastGroup = dayGroups[dayGroups.length - 1];
    if (lastGroup && lastGroup.day === key) lastGroup.items.push(s);
    else dayGroups.push({ day: key, items: [s] });
  }

  const pickGroup = (name) => {
    setGroup((current) => (current === name ? null : name));
    setDay(null);
    setLimit(PAGE_SIZE);
  };

  const pickDay = (iso) => {
    setDay(iso);
    setLimit(PAGE_SIZE);
    if (iso) listRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const isCurrent = period === 'month';
  const headline = r?.is_apprentice ? r?.stipend : r?.accrued;

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Заработок</h2>
        <div className="emp-earn-periods" role="group" aria-label="Период">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              type="button"
              aria-pressed={period === p.value}
              onClick={() => setPeriod(p.value)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading && !r && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {r && !error && (
        // При смене периода прежняя сводка остаётся на месте приглушённой —
        // без мигания «Загрузкой» и прыжков страницы.
        <div className="emp-earn" style={loading ? { opacity: 0.5 } : undefined} aria-busy={loading}>
          <section className="emp-salary-card emp-earn-hero">
            <div className="emp-earn-hero__label">
              {r.is_apprentice ? 'Стипендия' : 'Заработано'} в {monthIn(r.date_from)}
            </div>
            <div className="emp-earn-hero__sum">{money(headline)}</div>
            <div className="emp-earn-hero__sub">
              {r.is_apprentice
                ? `${r.stipend_days} дн. обучения × ${money(r.day_rate)} · на проценте было бы ${money(r.accrued)}`
                : `${countText(r.services_count)} · ваш процент с работ на ${money(r.kredit)}`}
            </div>

            <div className="emp-earn-tiles">
              {isCurrent ? (
                <>
                  <div className="emp-earn-tile">
                    <span>Сегодня</span>
                    <b>{money(sumOf(quick.today))}</b>
                    <small>{countText(quick.today.length)}</small>
                  </div>
                  <div className="emp-earn-tile">
                    <span>Вчера</span>
                    <b>{money(sumOf(quick.yesterday))}</b>
                    <small>{countText(quick.yesterday.length)}</small>
                  </div>
                </>
              ) : (
                <div className="emp-earn-tile">
                  <span>Рабочих дней</span>
                  <b>{quick.workDays}</b>
                  <small>с выданными работами</small>
                </div>
              )}
              <div className="emp-earn-tile">
                <span>В среднем за день</span>
                <b>{money(quick.perDay)}</b>
                <small>по дням с работами</small>
              </div>
            </div>
          </section>

          <section className="emp-salary-card emp-earn-pay">
            <div className="emp-salary-row">
              <span>{r.is_apprentice ? 'Стипендия' : 'Заработано'}</span>
              <span>{money(headline)}</span>
            </div>
            <div className="emp-salary-row emp-salary-row--neg">
              <span>Уже получено авансами</span>
              <span>{r.advances > 0 ? `−${money(r.advances)}` : money(0)}</span>
            </div>
            <div className="emp-salary-row emp-salary-row--total">
              <span>Осталось получить</span>
              <span>{money(Math.max(0, r.to_pay))}</span>
            </div>
            <p className="emp-earn-note">Суммы предварительные — окончательный расчёт у руководителя.</p>
          </section>

          {r.services_count === 0 ? (
            <p className="emp-page__empty">За этот период выданных работ пока нет.</p>
          ) : (
            <>
              {r.groups?.length > 1 && (
                <section className="emp-earn-block">
                  <div className="emp-salary-section__title">Виды работ</div>
                  <div className="emp-earn-chips" role="group" aria-label="Вид работ">
                    {r.groups.map((g) => (
                      <button
                        key={g.group}
                        type="button"
                        className="emp-earn-chip"
                        aria-pressed={group === g.group}
                        onClick={() => pickGroup(g.group)}
                      >
                        <span>{g.group}</span>
                        <b>{money(r.is_apprentice ? g.kredit : g.salary)}</b>
                        <small>{g.count} шт</small>
                      </button>
                    ))}
                  </div>
                </section>
              )}

              <section className="emp-salary-card emp-earn-block emp-earn-block--card">
                <div className="emp-salary-section__title">
                  По дням{group ? ` · ${group}` : ''}
                </div>
                <DaysChart
                  key={`${period}-${group || 'all'}`}
                  series={series}
                  selectedDay={day}
                  onSelectDay={pickDay}
                />
                <p className="emp-earn-note">Нажмите на день, чтобы увидеть его услуги.</p>
              </section>

              <section className="emp-earn-block" ref={listRef}>
                <div className="emp-earn-list-head">
                  <div className="emp-salary-section__title">Услуги — {rows.length}</div>
                  {(day || group) && (
                    <div className="emp-earn-filters">
                      {group && (
                        <button type="button" className="emp-earn-filter" onClick={() => pickGroup(group)}>
                          {group} <X size={14} aria-hidden="true" />
                        </button>
                      )}
                      {day && (
                        <button type="button" className="emp-earn-filter" onClick={() => pickDay(null)}>
                          {dayShort(day)} <X size={14} aria-hidden="true" />
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {dayGroups.map((d) => {
                  const total = dayTotals.get(d.day);
                  return (
                    <div key={d.day} className="emp-salary-card emp-earn-day">
                      <div className="emp-earn-day__head">
                        <span>{dayTitle(d.day)}</span>
                        <b>{money(total.value)}</b>
                      </div>
                      {d.items.map((s, i) => (
                        <div key={`${s.doc_num}-${s.out_time}-${i}`} className="emp-earn-svc">
                          <div className="emp-earn-svc__main">
                            <div className="emp-earn-svc__title">{serviceTitle(s.name)}</div>
                            <div className="emp-earn-svc__meta">
                              заказ {s.doc_num}
                              {!group && s.service_group ? ` · ${s.service_group}` : ''}
                            </div>
                          </div>
                          <div className="emp-earn-svc__sum">
                            {r.is_apprentice ? (
                              <>
                                <b>{money(s.kredit)}</b>
                                <span>справочно {money(s.salary)}</span>
                              </>
                            ) : (
                              <>
                                <b>{money(s.salary)}</b>
                                <span>
                                  {s.rate ? `${Math.round(s.rate * 100)}% ` : ''}из {money(s.kredit)}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })}
                {rows.length > limit && (
                  <button
                    type="button"
                    className="btn btn--secondary emp-earn-more"
                    onClick={() => setLimit((current) => current + PAGE_SIZE)}
                  >
                    Показать ещё ({rows.length - limit})
                  </button>
                )}
              </section>
            </>
          )}
        </div>
      )}
    </div>
  );
}
