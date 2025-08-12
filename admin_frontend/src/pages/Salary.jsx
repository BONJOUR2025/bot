import { useState, useEffect } from 'react';
import api from '../api';

export default function Salary() {
  const [months, setMonths] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({ month: '', employee: '' });
  const [list, setList] = useState([]);

  useEffect(() => {
    loadMonths();
    loadEmployees();
  }, []);

  async function loadMonths() {
    try {
      const res = await api.get('salary/months');
      setMonths(res.data || []);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadEmployees() {
    try {
      const res = await api.get('employees/');
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadData() {
    if (!filters.month) return;
    try {
      const params = {
        month: filters.month,
        employee_id: filters.employee || undefined,
      };
      const res = await api.get('salary/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  const total = list.reduce((sum, r) => sum + Number(r.final_amount || 0), 0);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800">Расчёт зарплаты</h2>
      <div className="flex flex-wrap gap-2 items-end">
        <select
          className="border p-2"
          value={filters.month}
          onChange={(e) => setFilters({ ...filters, month: e.target.value })}
        >
          <option value="">Выберите месяц</option>
          {months.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
        </select>
        <select
          className="border p-2"
          value={filters.employee}
          onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
        >
          <option value="">Все сотрудники</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
        </select>
        <button className="btn" onClick={loadData}>
          Загрузить
        </button>
      </div>
      <div className="overflow-auto border rounded shadow">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left">Сотрудник</th>
              <th className="px-4 py-2 text-right">Смены</th>
              <th className="px-4 py-2 text-right">Начислено</th>
              <th className="px-4 py-2 text-right">Аванс</th>
              <th className="px-4 py-2 text-right">Удержание</th>
              <th className="px-4 py-2 text-right">Итого</th>
              <th className="px-4 py-2 text-left">Комментарий</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {list.map((r) => (
              <tr key={r.employee_id}>
                <td className="px-4 py-2">{r.name}</td>
                <td className="px-4 py-2 text-right">{r.shifts_total}</td>
                <td className="px-4 py-2 text-right">{r.salary_total}</td>
                <td className="px-4 py-2 text-right">{r.advance}</td>
                <td className="px-4 py-2 text-right">{r.deduction}</td>
                <td className="px-4 py-2 text-right font-medium">{r.final_amount}</td>
                <td className="px-4 py-2">{r.comment}</td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr>
                <td colSpan="7" className="px-4 py-3 text-center text-gray-500">
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
          {list.length > 0 && (
            <tfoot className="bg-gray-50">
              <tr>
                <td className="px-4 py-2 text-right font-semibold" colSpan="5">
                  Итого
                </td>
                <td className="px-4 py-2 text-right font-bold">{total}</td>
                <td></td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

