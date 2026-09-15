import { useEffect, useMemo, useRef, useState } from 'react';
import api from '../../api.js';
import { masterErrorText, money, serviceTitle } from './masterFormat.js';

/** Заработок мастера — те же цифры, что «🔧 Мой заработок» в Telegram-боте
 *  (GET /api/masters/me/earnings → master_bot_service.get_earnings), плюс
 *  подробности: выработка по дням, фильтр по видам работ и список услуг. */

// Только прогретые периоды: всё остальное ушло бы живым запросом в самый
// дорогой отчёт системы (см. master_bot_service).
const PERIODS = [
  { value: 'month', label: 'Текущий месяц' },
  { value: 'prev_month', label: 'Прошлый месяц' },
];

const MONTHS = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const MONTHS_GEN = [
  'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
  'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
];
const WEEKDAYS = ['вс', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб'];
const DAY_MS = 24 * 60 * 60 * 1000;
const PAGE_SIZE = 40;

// Дни считаем в UTC от строки «ГГГГ-ММ-ДД»: так часовой пояс телефона не
// сдвигает услугу, выданную около полуночи, на соседний день.
function dayUtc(iso) {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  return Date.UTC(y, m - 1, d);
}
const isoFromUtc = (ms) => new Date(ms).toISOString().slice(0, 10);
const dayOfMonth = (iso) => new Date(dayUtc(iso)).getUTCDate();

function monthTitle(isoDate) {
  if (!isoDate) return '';
  const [y, m] = String(isoDate).split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

function dayShort(iso) {
  const dt = new Date(dayUtc(iso));
  return `${dt.getUTCDate()} ${MONTHS_GEN[dt.getUTCMonth()]}`;
}

function dayTitle(iso) {
  if (!iso || iso === '—') return 'Без даты выдачи';
  const dt = new Date(dayUtc(iso));
  return `${dayShort(iso)}, ${WEEKDAYS[dt.getUTCDay()]}`;
}

function durationText(minutes) {
  if (minutes == null) return '';
  const m = Math.max(0, Math.round(Number(minutes)));
  if (m < 60) return `в работе ${m} мин`;
  if (m < 24 * 60) {
    const h = Math.floor(m / 60);
    const rest = m % 60;
    return `в работе ${h} ч${rest ? ` ${rest} мин` : ''}`;
  }
  return `в работе ${Math.round(m / (24 * 60))} дн`;
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

const CHART_H = 150;
const AXIS_H = 22;
const PAD_TOP = 22;
const PAD_LEFT = 46;
const PAD_RIGHT = 6;

/** Выработка по дням: один ряд, один цвет, подпись только у лучшего дня.
 *  Значение любого дня — по нажатию (подсказка), а без нажатия — в списке
 *  услуг ниже, где у каждого дня своя сумма. */
function DaysChart({ rows, metric, dateFrom, dateTo }) {
  const wrapRef = useRef(null);
  const [width, setWidth] = useState(320);
  const [active, setActive] = useState(null);

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

  const series = useMemo(() => {
    const byDay = new Map();
    for (const row of rows) {
      if (!row.day) continue;
      const slot = byDay.get(row.day) || { value: 0, count: 0 };
      slot.value += Number(row[metric]) || 0;
      slot.count += 1;
      byDay.set(row.day, slot);
    }
    const out = [];
    if (!dateFrom || !dateTo) return out;
    for (let t = dayUtc(dateFrom); t <= dayUtc(dateTo); t += DAY_MS) {
      const day = isoFromUtc(t);
      const slot = byDay.get(day);
      out.push({ day, value: slot ? slot.value : 0, count: slot ? slot.count : 0 });
    }
    return out;
  }, [rows, metric, dateFrom, dateTo]);

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
  const peak = maxV > 0 ? series.findIndex((s) => s.value === maxV) : -1;
  const last = series.length - 1;
  const labeled = new Set([last]);
  series.forEach((s, i) => {
    if ((dayOfMonth(s.day) - 1) % 7 === 0 && last - i >= 3) labeled.add(i);
  });
  const act = active != null ? series[active] : null;

  return (
    <div
      className="emp-earn-chart"
      ref={wrapRef}
      onPointerLeave={(e) => {
        if (e.pointerType === 'mouse') setActive(null);
      }}
    >
      <svg
        width={width}
        height={CHART_H + AXIS_H}
        viewBox={`0 0 ${width} ${CHART_H + AXIS_H}`}
        role="img"
        aria-label="Выработка по дням"
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
          return (
            <path
              key={s.day}
              className={`emp-earn-bar${act && active !== i ? ' is-dim' : ''}`}
              d={barPath(x, y, barW, PAD_TOP + plotH - y)}
            />
          );
        })}
        {[...labeled].map((i) => (
          <text key={`x-${i}`} x={cx(i)} y={CHART_H + 15} textAnchor="middle">
            {dayOfMonth(series[i].day)}
          </text>
        ))}
        {peak >= 0 && !act && (
          <text className="emp-earn-peak" x={clampX(cx(peak))} y={yOf(maxV) - 7} textAnchor="middle">
            {money(maxV)}
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
            tabIndex={0}
            aria-label={`${dayShort(s.day)}: ${money(s.value)}, услуг ${s.count}`}
            onPointerDown={() => setActive((current) => (current === i ? null : i))}
            onPointerEnter={(e) => {
              if (e.pointerType === 'mouse') setActive(i);
            }}
            onFocus={() => setActive(i)}
            onBlur={() => setActive(null)}
          />
        ))}
      </svg>
      {act && (
        <div className="emp-earn-tip" style={{ left: clampX(cx(active)), top: Math.max(yOf(act.value) - 8, 46) }}>
          <b>{money(act.value)}</b>
          <span>{dayShort(act.day)} · {act.count} шт</span>
        </div>
      )}
    </div>
  );
}

export default function EmployeeMasterEarnings() {
  const [period, setPeriod] = useState('month');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [group, setGroup] = useState(null);
  const [limit, setLimit] = useState(PAGE_SIZE);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
    setGroup(null);
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

  const rows = useMemo(() => {
    const all = r?.services || [];
    return group ? all.filter((s) => s.service_group === group) : all;
  }, [r, group]);

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

  const toggleGroup = (name) => {
    setGroup((current) => (current === name ? null : name));
    setLimit(PAGE_SIZE);
  };

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Заработок</h2>
        <select
          className="emp-select"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          aria-label="Период"
        >
          {PERIODS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
      </div>

      {loading && !r && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {r && !error && (
        // При смене периода прежняя сводка остаётся на месте приглушённой —
        // без мигания «Загрузкой» и прыжков страницы.
        <div className="emp-salary-card" style={loading ? { opacity: 0.5 } : undefined} aria-busy={loading}>
          <div className="emp-salary-card__month">{monthTitle(r.date_from)}</div>

          {r.is_apprentice ? (
            <>
              <section className="emp-salary-section">
                <div className="emp-salary-section__title">Стипендия — к выплате</div>
                <div className="emp-salary-grid">
                  <div className="emp-salary-row">
                    <span>Дней обучения</span>
                    <span>{r.stipend_days} × {money(r.day_rate)}</span>
                  </div>
                  <div className="emp-salary-row emp-salary-row--sub">
                    <span>Стипендия</span>
                    <span>{money(r.stipend)}</span>
                  </div>
                </div>
              </section>
              <section className="emp-salary-section">
                <div className="emp-salary-section__title">Справочно — если бы на проценте</div>
                <div className="emp-salary-grid">
                  <div className="emp-salary-row"><span>Услуг</span><span>{r.services_count}</span></div>
                  <div className="emp-salary-row"><span>Сумма работ</span><span>{money(r.kredit)}</span></div>
                  <div className="emp-salary-row emp-salary-row--sub">
                    <span>Было бы начислено</span>
                    <span>{money(r.accrued)}</span>
                  </div>
                </div>
              </section>
            </>
          ) : (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">Начислено</div>
              <div className="emp-salary-grid">
                <div className="emp-salary-row"><span>Услуг</span><span>{r.services_count}</span></div>
                <div className="emp-salary-row"><span>Сумма работ</span><span>{money(r.kredit)}</span></div>
                <div className="emp-salary-row emp-salary-row--sub">
                  <span>Начислено</span>
                  <span>{money(r.accrued)}</span>
                </div>
              </div>
            </section>
          )}

          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Итог</div>
            <div className="emp-salary-grid">
              {r.advances > 0 && (
                <div className="emp-salary-row emp-salary-row--neg">
                  <span>Авансы с последней зарплаты</span>
                  <span>−{money(r.advances)}</span>
                </div>
              )}
              <div className="emp-salary-row emp-salary-row--total">
                <span>К выплате сейчас</span>
                <span>{money(Math.max(0, r.to_pay))}</span>
              </div>
            </div>
          </section>

          {r.services_count === 0 && (
            <div className="emp-salary-card__note">За этот период выданных работ пока нет.</div>
          )}

          {r.groups?.length > 0 && (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">По видам работ</div>
              <div className="emp-earn-groups">
                {r.groups.map((g) => {
                  const on = group === g.group;
                  return (
                    <button
                      key={g.group}
                      type="button"
                      className="emp-earn-group"
                      aria-pressed={on}
                      onClick={() => toggleGroup(g.group)}
                    >
                      <span>{g.group} · {g.count} шт</span>
                      <span>{money(r.is_apprentice ? g.kredit : g.salary)}</span>
                    </button>
                  );
                })}
              </div>
              {group ? (
                <button type="button" className="emp-earn-reset" onClick={() => toggleGroup(group)}>
                  Показать все виды работ
                </button>
              ) : (
                <div className="emp-earn-hint">Нажмите на вид работ, чтобы оставить в графике и списке только его</div>
              )}
            </section>
          )}

          {rows.length > 0 && (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">
                По дням{group ? ` · ${group}` : ''}
              </div>
              <DaysChart
                key={`${period}-${group || 'all'}`}
                rows={rows}
                metric={metric}
                dateFrom={r.date_from}
                dateTo={r.date_to}
              />
            </section>
          )}

          {rows.length > 0 && (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">
                Услуги{group ? ` · ${group}` : ''} — {rows.length}
              </div>
              {dayGroups.map((d) => {
                const total = dayTotals.get(d.day);
                return (
                  <div key={d.day} className="emp-earn-day">
                    <div className="emp-earn-day__head">
                      <span>{dayTitle(d.day)}</span>
                      <span>{total.count} шт · {money(total.value)}</span>
                    </div>
                    {d.items.map((s, i) => (
                      <div key={`${s.doc_num}-${s.out_time}-${i}`} className="emp-earn-svc">
                        <div className="emp-earn-svc__main">
                          <div className="emp-earn-svc__title">{serviceTitle(s.name)}</div>
                          <div className="emp-earn-svc__meta">
                            {[s.doc_num, group ? null : s.service_group, durationText(s.duration_min)]
                              .filter(Boolean)
                              .join(' · ')}
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
                                {money(s.kredit)}
                                {s.rate ? ` · ${Math.round(s.rate * 100)}%` : ''}
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
          )}

          <div className="emp-salary-card__note">
            Показатели предварительные, уточните у руководителя.
          </div>
        </div>
      )}
    </div>
  );
}
