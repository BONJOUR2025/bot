import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import api from '../api';

export default function Vacations() {
  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    start_date: '',
    end_date: '',
    type: 'Отпуск',
    comment: '',
  };

  const [vacations, setVacations] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({
    employee: '',
    type: '',
    from: '',
    to: '',
    query: '',
  });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [todayCount, setTodayCount] = useState(0);
  const [monthView, setMonthView] = useState(() => {
    const d = new Date();
    d.setDate(1);
    return d;
  });

  function formatDateRange(start, end) {
    const opts = { day: '2-digit', month: '2-digit', year: 'numeric' };
    const s = new Date(start).toLocaleDateString('ru-RU', opts);
    const e = new Date(end).toLocaleDateString('ru-RU', opts);
    return `${s} – ${e}`;
  }

  useEffect(() => {
    loadEmployees();
    load();
  }, []);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/');
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    try {
      const params = {
        employee_id: filters.employee || undefined,
        type: filters.type || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('vacations/', { params });
      let list = res.data;
      if (filters.query) {
        const q = filters.query.toLowerCase();
        list = list.filter((v) => v.name.toLowerCase().includes(q));
      }
      list.sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
      setVacations(list);
      const activeRes = await api.get('vacations/active');
      setTodayCount(activeRes.data.length);
    } catch (err) {
      console.error(err);
    }
  }

  function duration(start, end) {
    const s = new Date(start);
    const e = new Date(end);
    return Math.round((e - s) / 86400000) + 1;
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(v) {
    setForm({ ...v });
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.start_date || !form.end_date) {
      alert('Заполните обязательные поля');
      return;
    }
    try {
      if (form.id) {
        await api.put(`vacations/${form.id}`, form);
      } else {
        await api.post('vacations/', form);
      }
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      console.error(err);
      alert('Ошибка сохранения');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`vacations/${id}`);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({ ...f, employee_id: emp.id, name: emp.full_name || emp.name }));
    }
  }

  const year = monthView.getFullYear();
  const month = monthView.getMonth();
  const daysCount = new Date(year, month + 1, 0).getDate();
  const days = Array.from({ length: daysCount }, (_, i) => i + 1);
  const empIds = [...new Set(vacations.map((v) => v.employee_id))];
  const todayStr = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold">Отпуска и больничные</h2>
      <div className="text-sm text-gray-600">Сегодня в отпуске — {todayCount} сотрудника</div>
      <div className="flex flex-wrap gap-2 items-end">
        <select
          className="border p-2"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="Отпуск">Отпуск</option>
          <option value="Больничный">Больничный</option>
        </select>
        <select
          className="border p-2"
          value={filters.employee}
          onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
        >
          <option value="">Сотрудник</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
        </select>
        <input
          type="date"
          className="border p-2"
          value={filters.from}
          onChange={(e) => setFilters({ ...filters, from: e.target.value })}
        />
        <input
          type="date"
          className="border p-2"
          value={filters.to}
          onChange={(e) => setFilters({ ...filters, to: e.target.value })}
        />
        <input
          className="border p-2 flex-grow"
          placeholder="Поиск по ФИО"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        <button className="btn" onClick={load}>
          Применить
        </button>
        <button className="btn ml-auto" onClick={startCreate}>
          <Plus size={16} /> Добавить запись
        </button>
      </div>

      <div className="overflow-auto border rounded shadow bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2 text-left">Сотрудник</th>
              <th className="p-2 text-left">Тип</th>
              <th className="p-2 text-left">Даты</th>
              <th className="p-2 text-left">Длительность</th>
              <th className="p-2 text-left">Комментарий</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {vacations.map((v) => (
              <tr key={v.id} className="hover:bg-gray-50">
                <td className="p-2">{v.name}</td>
                <td className="p-2">{v.type}</td>
                <td className="p-2">
                  {formatDateRange(v.start_date, v.end_date)}
                </td>
                <td className="p-2">{duration(v.start_date, v.end_date)} дней</td>
                <td className="p-2 whitespace-pre-wrap">{v.comment}</td>
                <td className="p-2 space-x-1 text-right">
                  <button
                    className="text-blue-600 hover:text-blue-800"
                    onClick={() => startEdit(v)}
                    title="Редактировать"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    className="text-gray-600 hover:text-gray-800"
                    onClick={() => remove(v.id)}
                    title="Удалить"
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {vacations.length === 0 && (
              <tr>
                <td colSpan="6" className="p-4 text-center text-gray-500">
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <button
            className="px-2"
            onClick={() =>
              setMonthView(
                (m) => new Date(m.getFullYear(), m.getMonth() - 1, 1)
              )
            }
          >
            ←
          </button>
          <span className="font-semibold">
            {monthView.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
          </span>
          <button
            className="px-2"
            onClick={() =>
              setMonthView(
                (m) => new Date(m.getFullYear(), m.getMonth() + 1, 1)
              )
            }
          >
            →
          </button>
        </div>
        <div className="overflow-auto border rounded shadow bg-white">
          <table className="min-w-full text-xs">
            <thead className="bg-gray-50">
              <tr>
                <th className="p-1 text-left sticky left-0 bg-gray-50 z-10">Сотрудник</th>
                {days.map((d) => (
                  <th key={d} className="p-1 w-6 text-center">
                    {d}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {empIds.map((eid) => {
                const emp = employees.find((e) => String(e.id) === String(eid));
                const name = emp ? emp.full_name || emp.name : '';
                return (
                  <tr key={eid} className="hover:bg-gray-50">
                    <th className="p-2 text-left sticky left-0 bg-white z-10">
                      {name}
                    </th>
                    {days.map((d) => {
                      const dateStr = new Date(year, month, d)
                        .toISOString()
                        .slice(0, 10);
                      const vac = vacations.find(
                        (v) =>
                          String(v.employee_id) === String(eid) &&
                          v.start_date <= dateStr &&
                          v.end_date >= dateStr
                      );
                      let cls = '';
                      let title = '';
                      if (vac) {
                        title = `${formatDateRange(vac.start_date, vac.end_date)}${
                          vac.comment ? ' ' + vac.comment : ''
                        }`;
                        if (vac.end_date < todayStr) cls = 'bg-gray-300';
                        else if (
                          vac.start_date <= todayStr &&
                          vac.end_date >= todayStr
                        )
                          cls = 'bg-yellow-200';
                        else cls = 'bg-green-200';
                      } else {
                        const dow = new Date(year, month, d).getDay();
                        if (dow === 0 || dow === 6) cls = 'bg-gray-50';
                      }
                      return (
                        <td key={d} className={`border p-1 ${cls}`} title={title} />
                      );
                    })}
                  </tr>
                );
              })}
              {empIds.length === 0 && (
                <tr>
                  <td colSpan={days.length + 1} className="p-4 text-center text-gray-500">
                    Нет данных
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white p-4 space-y-2 rounded shadow w-80">
            <h2 className="text-lg font-bold mb-2">
              {form.id ? 'Редактирование' : 'Новая запись'}
            </h2>
            <select
              className="border p-2 w-full"
              value={form.employee_id}
              onChange={(e) => handleSelect(e.target.value)}
            >
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name || e.name}
                </option>
              ))}
            </select>
            <select
              className="border p-2 w-full"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="Отпуск">Отпуск</option>
              <option value="Больничный">Больничный</option>
            </select>
            <input
              type="date"
              className="border p-2 w-full"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
            <input
              type="date"
              className="border p-2 w-full"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
            <textarea
              className="border p-2 w-full"
              placeholder="Комментарий"
              value={form.comment}
              onChange={(e) => setForm({ ...form, comment: e.target.value })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn bg-gray-300 text-gray-700 hover:bg-gray-400" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="btn" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
