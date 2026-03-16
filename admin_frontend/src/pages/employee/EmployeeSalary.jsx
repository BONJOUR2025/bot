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

export default function EmployeeSalary() {
  const { user } = useAuth();
  const employeeId = user?.employee_id;

  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

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
    api
      .get('/salary/', { params: { month: selectedMonth, employee_id: employeeId } })
      .then((res) => setRows(res.data || []))
      .catch(() => setError('Не удалось загрузить данные'))
      .finally(() => setLoading(false));
  }, [selectedMonth, employeeId]);

  const row = rows[0] || null;

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
