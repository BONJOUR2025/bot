import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import api from '../../api.js';
import { money } from './masterFormat.js';

/** «Мой KPI» — кабинет менеджера по работе с клиентами
 *  (GET /api/managers/me/kpi → тот же расчёт, что страница «Менеджеры»).
 *
 *  Порядок экрана — вопросы менеджера: сколько получу сейчас → по какому
 *  показателю недобираю и сколько осталось до порога 79% → какие сделки
 *  засчитаны → премии, штрафы, авансы → прошлые начисления. Цифры
 *  пересчитываются из amoCRM не чаще раза в 10 минут: кнопка «Обновить»
 *  берёт свежие. */

const THRESHOLD = 0.79;

function periodOf(offset) {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

const PERIODS = [
  { value: periodOf(0), label: 'Этот месяц' },
  { value: periodOf(-1), label: 'Прошлый' },
];

function monthIn(iso) {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString('ru-RU', { month: 'long' });
}

function pct(x) {
  return `${Math.round((Number(x) || 0) * 100)}%`;
}

function duration(sec) {
  if (sec == null) return '—';
  if (sec < 60) return `${sec} с`;
  const m = Math.round(sec / 60);
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  return `${h} ч ${m % 60} мин`;
}

function errorText(err) {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  return 'Не удалось загрузить KPI. Попробуйте ещё раз.';
}

/** Полоса «факт / план»: отметка порога 79% и 100%. Шкала до 125%, чтобы
 *  перевыполнение было видно, а не упиралось в край. */
function Progress({ ratio }) {
  const scale = 1.25;
  const w = Math.min(Math.max(ratio, 0), scale) / scale * 100;
  const tone = ratio >= 1 ? 'is-good' : ratio >= THRESHOLD ? 'is-ok' : 'is-low';
  return (
    <div className="mk-progress" aria-hidden="true">
      <div className={`mk-progress__fill ${tone}`} style={{ width: `${w}%` }} />
      <span className="mk-progress__mark" style={{ left: `${(THRESHOLD / scale) * 100}%` }} title="Порог 79%" />
      <span className="mk-progress__mark mk-progress__mark--full" style={{ left: `${(1 / scale) * 100}%` }} title="План 100%" />
    </div>
  );
}

function Component({ title, c, factText, planText, note }) {
  const ratio = c.ratio || 0;
  let hint;
  if (c.leads_gate_failed) hint = `Мало новых заявок: ${c.new_leads} из ${c.min_leads} — компонент не начисляется.`;
  else if (ratio < THRESHOLD) hint = `До порога 79% не хватает ${pct(THRESHOLD - ratio)} — пока 0 ₽.`;
  else if (ratio < 1) hint = `До плана не хватает ${pct(1 - ratio)}.`;
  else hint = 'План выполнен — перевыполнение тоже оплачивается.';
  return (
    <section className="emp-payout-item mk-comp">
      <div className="emp-payout-item__top">
        <span className="mk-comp__title">{title}</span>
        <span className={`badge ${c.zeroed ? 'badge--neutral' : 'badge--success'}`}>{money(c.amount)} из {money(c.max)}</span>
      </div>
      <div className="mk-comp__fact">
        <b>{pct(ratio)}</b> плана · {factText} <span className="mk-muted">/ {planText}</span>
      </div>
      <Progress ratio={ratio} />
      <p className="mk-hint">{hint}</p>
      {note && <p className="mk-hint">{note}</p>}
    </section>
  );
}

export default function EmployeeManagerKpi() {
  const [period, setPeriod] = useState(PERIODS[0].value);
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showDeals, setShowDeals] = useState(false);

  const load = useCallback((refresh = false) => {
    setLoading(true);
    setError('');
    api.get('/managers/me/kpi', { params: { period, ...(refresh ? { refresh: 1 } : {}) } })
      .then((r) => setD(r.data))
      .catch((e) => { setD(null); setError(errorText(e)); })
      .finally(() => setLoading(false));
  }, [period]);

  useEffect(() => { load(); setShowDeals(false); }, [load]);

  const r = d?.result;
  const deals = d?.deals?.won || [];

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Мой KPI</h2>
        <div className="mk-head-actions">
          <div className="emp-earn-periods" role="group" aria-label="Период">
            {PERIODS.map((p) => (
              <button key={p.value} type="button" aria-pressed={period === p.value} onClick={() => setPeriod(p.value)}>
                {p.label}
              </button>
            ))}
          </div>
          <button type="button" className="icon-button" onClick={() => load(true)} disabled={loading} aria-label="Обновить из amoCRM">
            <RefreshCw size={18} className={loading ? 'emp-wip-spin' : ''} />
          </button>
        </div>
      </div>

      {loading && !d && <p className="emp-page__loading">Считаем по amoCRM… это может занять до минуты.</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {d && r && (
        <div className="mk" style={loading ? { opacity: 0.55 } : undefined} aria-busy={loading}>
          {!d.plan_set && (
            <p className="mk-warn">План на {monthIn(d.date_from)} ещё не заведён — цифры ниже считаются от нулевого плана. Напомните руководителю.</p>
          )}
          {d.metrics_error && <p className="mk-warn">{d.metrics_error}</p>}

          <section className="emp-salary-card emp-earn-hero">
            <div className="emp-earn-hero__label">К выплате за {monthIn(d.date_from)} на сегодня</div>
            <div className="emp-earn-hero__sum">{money(r.to_pay)}</div>
            <div className="emp-earn-hero__sub">
              Начислено {money(r.gross)}: оклад {money(r.oklad)} + KPI {money(r.kpi)}
              {r.bonuses ? ` + премии ${money(r.bonuses)}` : ''}
              {r.advances || r.penalties ? ` · удержано ${money(r.advances + r.penalties)} (авансы${r.penalties ? ' и штрафы' : ''})` : ''}
            </div>
            <div className="emp-earn-tiles">
              <div className="emp-earn-tile"><span>KPI сейчас</span><b>{money(r.kpi)}</b><small>цель {money(r.kpi_max)}</small></div>
              <div className="emp-earn-tile"><span>Выручка</span><b>{money(r.revenue.actual)}</b><small>план {money(r.revenue.plan)}</small></div>
              <div className="emp-earn-tile"><span>Ответ клиенту</span><b>{duration(d.response?.median_seconds)}</b><small>медиана, раб. время</small></div>
            </div>
          </section>

          <h3 className="ws-section__title">Из чего складывается KPI</h3>
          <div className="emp-list">
            <Component
              title={`Выручка · ${Math.round(r.weights.revenue * 100)}%`}
              c={r.revenue}
              factText={money(r.revenue.actual)}
              planText={money(r.revenue.plan)}
            />
            <Component
              title={`Конверсия ремонта · ${Math.round(r.weights.repair * 100)}%`}
              c={r.repair}
              factText={`${pct(r.repair.conv)} (${r.repair.target} из ${r.repair.total})`}
              planText={`план ${pct(r.repair.plan_conv)}`}
            />
            <Component
              title={`Конверсия пошива · ${Math.round(r.weights.sew * 100)}%`}
              c={r.sew}
              factText={`${pct(r.sew.conv)} (${r.sew.target} из ${r.sew.total})`}
              planText={`план ${pct(r.sew.plan_conv)}`}
              note={`Новых заявок на пошив: ${r.sew.new_leads} (нужно от ${r.sew.min_leads}).`}
            />
          </div>

          <h3 className="ws-section__title">Засчитанные сделки <span className="ws-count">{deals.length}</span></h3>
          {deals.length === 0 ? (
            <p className="emp-page__empty">Пока нет сделок, дошедших до заказа.</p>
          ) : (
            <div className="emp-list">
              {(showDeals ? deals : deals.slice(0, 5)).map((x) => (
                <div key={x.id} className="emp-payout-item">
                  <div className="emp-payout-item__top">
                    <span className="mk-deal">{x.name || `Сделка ${x.id}`}</span>
                    <span className="emp-payout-item__amount">{money(x.price)}</span>
                  </div>
                  <div className="emp-payout-item__details"><span>{x.date}</span></div>
                </div>
              ))}
              {deals.length > 5 && (
                <button type="button" className="btn btn--secondary" onClick={() => setShowDeals((v) => !v)}>
                  {showDeals ? 'Свернуть' : `Показать все ${deals.length}`}
                </button>
              )}
            </div>
          )}

          {(d.response?.slowest || []).some((x) => x.seconds == null || x.seconds > 3600) && (
            <>
              <h3 className="ws-section__title">Долгие ответы клиентам</h3>
              <p className="ws-hint">Заявки, на которые вы ответили позже часа (в рабочее время) или не ответили звонком и сообщением.</p>
              <div className="emp-list">
                {d.response.slowest.filter((x) => x.seconds == null || x.seconds > 3600).slice(0, 5).map((x) => (
                  <div key={x.id} className="emp-payout-item">
                    <div className="emp-payout-item__top">
                      <span className="mk-deal">{x.name || `Сделка ${x.id}`}</span>
                      <span className="badge badge--warning">{x.seconds == null ? 'нет ответа' : duration(x.seconds)}</span>
                    </div>
                    <div className="emp-payout-item__details"><span>заявка {x.received}{x.channel ? ` · ${x.channel}` : ''}</span></div>
                  </div>
                ))}
              </div>
            </>
          )}

          {(d.incentives.length > 0 || d.advances.count > 0) && (
            <>
              <h3 className="ws-section__title">Премии, штрафы и авансы</h3>
              <div className="emp-list">
                {d.incentives.map((i, n) => (
                  <div key={`i${n}`} className="emp-payout-item">
                    <div className="emp-payout-item__top">
                      <span>{i.type === 'bonus' ? 'Премия' : 'Штраф'}</span>
                      <span className={`emp-payout-item__amount ${i.type === 'bonus' ? 'mk-plus' : 'mk-minus'}`}>{i.type === 'bonus' ? '+' : '−'}{money(i.amount)}</span>
                    </div>
                    <div className="emp-payout-item__details"><span>{i.date}{i.reason ? ` · ${i.reason}` : ''}</span></div>
                  </div>
                ))}
                {d.advances.count > 0 && (
                  <div className="emp-payout-item">
                    <div className="emp-payout-item__top">
                      <span>Авансы с последней зарплаты</span>
                      <span className="emp-payout-item__amount mk-minus">−{money(d.advances.total)}</span>
                    </div>
                    <div className="emp-payout-item__details"><span>{d.advances.count} шт.</span></div>
                  </div>
                )}
              </div>
            </>
          )}

          {d.accruals.length > 0 && (
            <>
              <h3 className="ws-section__title">Начисления</h3>
              <div className="emp-list">
                {d.accruals.map((a) => (
                  <div key={a.id} className="emp-payout-item">
                    <div className="emp-payout-item__top">
                      <span>{a.period}</span>
                      <span className="emp-payout-item__amount">{money(a.to_pay)}</span>
                    </div>
                    <div className="emp-payout-item__details">
                      <span>начислено {money(a.gross)}</span>
                      <span className={`badge ${a.paid ? 'badge--success' : 'badge--neutral'}`}>{a.paid ? 'выплата создана' : 'начислено'}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          <p className="ws-updated">Данные amoCRM на {new Date(d.generated_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })}</p>
        </div>
      )}
    </div>
  );
}
