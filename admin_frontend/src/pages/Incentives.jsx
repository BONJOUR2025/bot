import { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../api';

export default function Incentives() {
  const location = useLocation();
  const query = new URLSearchParams(location.search);

  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    type: 'bonus',
    amount: '',
    reason: '',
    date: new Date().toISOString().slice(0, 10),
    added_by: 'admin',
  };

  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({
    employee: query.get('employee_id') || '',
    type: query.get('type') || '',
    from: query.get('date_from') || '',
    to: query.get('date_to') || '',
  });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadEmployees();
  }, []);

  useEffect(() => {
    load();
  }, [filters]);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    const params = {
      employee_id: filters.employee || undefined,
      type: filters.type || undefined,
      date_from: filters.from || undefined,
      date_to: filters.to || undefined,
    };
    try {
      const res = await api.get('incentives/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function saveForm() {
    if (!form.employee_id || !form.amount || !form.date) return;
    const payload = { ...form, amount: Number(form.amount) };
    try {
      if (form.id) {
        await api.patch(`incentives/${form.id}`, payload);
      } else {
        await api.post('incentives/', payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`incentives/${id}`);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(item) {
    setForm({ ...item, amount: item.amount });
    setShowForm(true);
  }

  const rowColor = (type) => (type === 'bonus' ? 'bg-green-50' : 'bg-red-50');
  const typeLabel = (t) => (t === 'bonus' ? '💰 Премия' : '⚠️ Штраф');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-gray-800">Штрафы и премии</h2>
      <div className="flex flex-wrap gap-2 items-end">
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
        <select
          className="border p-2"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="bonus">Премия</option>
          <option value="penalty">Штраф</option>
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
        <button className="btn" onClick={load}>
          Применить
        </button>
        <button className="btn ml-auto" onClick={startCreate}>
          ➕ Добавить
        </button>
      </div>
      <div className="overflow-auto border rounded shadow">
        <table className="min-w-[1100px] divide-y divide-gray-200 bg-white text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left">Сотрудник</th>
              <th className="px-4 py-2 text-left">Дата</th>
              <th className="px-4 py-2 text-left">Тип</th>
              <th className="px-4 py-2 text-left">Сумма</th>
              <th className="px-4 py-2 text-left">Причина</th>
              <th className="px-4 py-2 text-left">Добавил</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {list.map((item) => (
              <tr key={item.id} className={rowColor(item.type)}>
                <td className="px-4 py-2">{item.name}</td>
                <td className="px-4 py-2">{item.date}</td>
                <td className="px-4 py-2 font-medium">
                  {typeLabel(item.type)}
                </td>
                <td className="px-4 py-2">{item.amount} ₽</td>
                <td className="px-4 py-2">{item.reason}</td>
                <td className="px-4 py-2">{item.added_by}</td>
                <td className="px-4 py-2 text-right">
                  <button className="text-blue-600 mr-1" onClick={() => startEdit(item)}>
                    ✏️
                  </button>
                  {!item.locked && (
                    <button className="text-red-600" onClick={() => remove(item.id)}>
                      🗑️
                    </button>
                  )}
                </td>
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
        </table>
      </div>

      {showForm && (
        <div className="modal-backdrop">
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => {
                const id = e.target.value;
                setForm((f) => ({
                  ...f,
                  employee_id: id,
                  name: employees.find((u) => String(u.id) === String(id))?.full_name || '',
                }));
              }}
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
              className="modal-control"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="bonus">Премия</option>
              <option value="penalty">Штраф</option>
            </select>
            <input
              className="modal-control"
              placeholder="Сумма"
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <textarea
              className="modal-control"
              placeholder="Причина"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={() => setShowForm(false)}>
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





