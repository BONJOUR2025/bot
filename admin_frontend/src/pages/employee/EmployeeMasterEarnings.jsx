import { useEffect, useState } from 'react';
import api from '../../api.js';
import { masterErrorText, money } from './masterFormat.js';

/** Заработок мастера — те же цифры, что «🔧 Мой заработок» в Telegram-боте
 *  (GET /api/masters/me/earnings → master_bot_service.get_earnings). */

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

function monthTitle(isoDate) {
  if (!isoDate) return '';
  const [y, m] = String(isoDate).split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export default function EmployeeMasterEarnings() {
  const [period, setPeriod] = useState('month');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');
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

      {loading && <p className="emp-page__loading">Загрузка…</p>}
      {!loading && error && <p className="emp-page__error">{error}</p>}

      {!loading && !error && r && (
        <div className="emp-salary-card">
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

          {r.services_count === 0 && (
            <div className="emp-salary-card__note">За этот период выданных работ пока нет.</div>
          )}

          {r.groups?.length > 0 && (
            <section className="emp-salary-section">
              <div className="emp-salary-section__title">По видам работ</div>
              <div className="emp-salary-grid">
                {r.groups.map((g) => (
                  <div key={g.group} className="emp-salary-row">
                    <span>{g.group} · {g.count} шт</span>
                    {/* У ученика процент справочный — показываем сумму работ, а не «начислено». */}
                    <span>{money(r.is_apprentice ? g.kredit : g.salary)}</span>
                  </div>
                ))}
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

          {r.to_pay < 0 && (
            <div className="emp-salary-card__note">
              Авансом получено на {money(-r.to_pay)} больше начисленного — разница учтётся при расчёте зарплаты.
            </div>
          )}
          {r.warnings_count > 0 && (
            <div className="emp-salary-card__note">
              Услуг с замечаниями: {r.warnings_count} — уточните у руководителя.
            </div>
          )}
          <div className="emp-salary-card__note">
            Цифры предварительные, посчитаны по сканам. Итоговая выплата может отличаться — премии, штрафы и
            корректировки считаются отдельно.
          </div>
        </div>
      )}
    </div>
  );
}
