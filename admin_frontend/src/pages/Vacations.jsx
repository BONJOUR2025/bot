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
        <button className="bg-blue-600 text-white px-3 py-2 rounded" onClick={load}>
          Применить
        </button>
        <button className="bg-indigo-600 text-white px-3 py-2 rounded ml-auto" onClick={startCreate}>
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
                  {v.start_date} – {v.end_date}
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
              <button className="bg-gray-300 px-3 py-1 rounded" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="bg-blue-600 text-white px-3 py-1 rounded" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
