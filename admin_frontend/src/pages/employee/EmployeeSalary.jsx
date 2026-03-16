import { useEffect, useState } from 'react';
import { useAuth } from '../../providers/AuthProvider.jsx';
import api from '../../api.js';

function fmt(n) {
  if (n == null || n === 0) return '—';
  return Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 0 }) + ' ₽';
}

function fmtNum(n) {
  return n != null ? String(n) : '—';
}

function fmtMoney(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('ru-RU', { minimumFractionDigits: 0 }) + ' ₽';
}

/** "ЯНВАРЬ 2025" → { month: "ЯНВАРЬ", year: 2025 } */
function parseSalaryMonth(str) {
  if (!str) return null;
  const parts = str.trim().split(/\s+/);
  if (parts.length === 2) {
    const year = parseInt(parts[1], 10);
    if (!isNaN(year)) return { month: parts[0].toUpperCase(), year };
  }
  return { month: str.toUpperCase(), year: null };
}

function PlanRow({ label, sales, plan, fulfillment }) {
  if (!plan && !sales) return null;
  const pct = fulfillment != null ? Math.round(fulfillment * 100) : null;
  const color =
    pct == null
      ? undefined
      : pct >= 100
      ? 'var(--color-success, #16a34a)'
      : pct >= 80
      ? 'var(--color-warning, #d97706)'
      : 'var(--color-error, #dc2626)';
  return (
    <div className="emp-salary-row emp-salary-plan-row">
      <span>{label}</span>
      <span style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
        {plan > 0 && (
          <span style={{ color: 'var(--muted-foreground)', fontSize: '0.85em' }}>
            {fmtMoney(sales)} / {fmtMoney(plan)}
          </span>
        )}
        {pct != null && (
          <span style={{ fontWeight: 600, minWidth: '2.5rem', textAlign: 'right', color }}>
            {pct}%
          </span>
        )}
      </span>
    </div>
  );
}

export default function EmployeeSalary() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [payroll, setPayroll] = useState(null);

  useEffect(() => {
    api.get('/salary/months').then((res) => {
      const list = res.data || [];
      setMonths(list);
      if (list.length > 0) setSelectedMonth(list[list.length - 1]);
    });
  }, []);

  useEffect(() => {
    if (!selectedMonth || !employeeId) return;
    setLoading(true);
    setError('');
    setPayroll(null);

    const parsed = parseSalaryMonth(selectedMonth);

    const salaryReq = api
      .get('/salary/', { params: { month: selectedMonth, employee_id: employeeId } })
      .then((res) => setRows(res.data || []))
      .catch(() => setError('Не удалось загрузить данные'));

    const payrollReq = parsed
      ? api
          .get('/payroll/my', {
            params: { month: parsed.month, ...(parsed.year ? { year: parsed.year } : {}) },
          })
          .then((res) => setPayroll(res.data))
          .catch(() => { /* payroll data is optional */ })
      : Promise.resolve();

    Promise.all([salaryReq, payrollReq]).finally(() => setLoading(false));
  }, [selectedMonth, employeeId]);

  const row = rows[0] || null;

  const hasPlans =
    payroll &&
    (payroll.repair_plan || payroll.cosmetics_plan || payroll.shoes_plan ||
     payroll.repair_sales || payroll.cosmetics_sales || payroll.shoes_sales);

  if (!employeeId) {
    return (
      <div className="emp-page">
        <h2 className="emp-page__title">Зарплата</h2>
        <p className="emp-page__empty">Аккаунт не привязан к сотруднику. Обратитесь к администратору.</p>
      </div>
    );
  }

  return (
    <div className="emp-page">
      <div className="emp-page__head">
        <h2 className="emp-page__title">Зарплата</h2>
        {months.length > 0 && (
          <select
            className="emp-select"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
          >
            {months.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        )}
      </div>

      {loading && <p className="emp-page__loading">Загрузка…</p>}
      {error && <p className="emp-page__error">{error}</p>}

      {!loading && !error && !row && (
        <p className="emp-page__empty">Данных за выбранный месяц нет</p>
      )}

      {hasPlans && (
        <div className="emp-salary-card">
          <section className="emp-salary-section">
            <div className="emp-salary-section__title">План продаж</div>
            <div className="emp-salary-grid">
              <PlanRow
                label="Ремонт"
                sales={payroll.repair_sales}
                plan={payroll.repair_plan}
                fulfillment={payroll.repair_fulfillment}
              />
              <PlanRow
                label="Косметика"
                sales={payroll.cosmetics_sales}
                plan={payroll.cosmetics_plan}
                fulfillment={payroll.cosmetics_fulfillment}
              />
              <PlanRow
                label="Обувь"
                sales={payroll.shoes_sales}
                plan={payroll.shoes_plan}
                fulfillment={payroll.shoes_fulfillment}
              />
            </div>
          </section>
        </div>
      )}

      {row && (
        <div className="emp-salary-card">
          <div className="emp-salary-card__month">{row.month}</div>

          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Смены</div>
            <div className="emp-salary-grid">
              <div className="emp-salary-row"><span>Основные</span><span>{fmtNum(row.shifts_main)}</span></div>
              {row.shifts_extra > 0 && <div className="emp-salary-row"><span>Дополнительные</span><span>{fmtNum(row.shifts_extra)}</span></div>}
              <div className="emp-salary-row emp-salary-row--sub"><span>Итого смен</span><span>{fmtNum(row.shifts_total)}</span></div>
            </div>
          </section>

          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Начисления</div>
            <div className="emp-salary-grid">
              {[
                ['Фиксированная ставка', row.salary_fixed],
                ['Ремонт', row.salary_repair],
                ['Косметика', row.salary_cosmetics],
                ['Обувь', row.salary_shoes],
                ['Аксессуары', row.salary_accessories],
                ['Ключи', row.salary_keys],
                ['Тапочки', row.salary_slippers],
                ['Мастерская', row.salary_workshop],
                ['Бонус', row.salary_bonus],
              ].filter(([, v]) => v).map(([label, val]) => (
                <div key={label} className="emp-salary-row">
                  <span>{label}</span>
                  <span>{fmt(val)}</span>
                </div>
              ))}
              <div className="emp-salary-row emp-salary-row--sub">
                <span>Всего начислено</span>
                <span>{fmt(row.salary_total)}</span>
              </div>
            </div>
          </section>

          <section className="emp-salary-section">
            <div className="emp-salary-section__title">Итог</div>
            <div className="emp-salary-grid">
              {row.deduction > 0 && (
                <div className="emp-salary-row emp-salary-row--neg"><span>Удержания / штрафы</span><span>−{fmt(row.deduction)}</span></div>
              )}
              {row.advance > 0 && (
                <div className="emp-salary-row"><span>Аванс выплачен</span><span>{fmt(row.advance)}</span></div>
              )}
              <div className="emp-salary-row emp-salary-row--total">
                <span>К выплате</span>
                <span>{fmt(row.final_amount)}</span>
              </div>
            </div>
          </section>

          {row.comment && (
            <div className="emp-salary-card__note">{row.comment}</div>
          )}
        </div>
      )}
    </div>
  );
}
