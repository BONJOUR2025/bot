import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus, Clock } from 'lucide-react';
import api from '../api';

export default function Assets() {
  const emptyForm = {
    id: null,
    employee_id: '',
    employee_name: '',
    position: '',
    department: '',
    category: '',
    item_name: '',
    size: '',
    quantity: 1,
    issue_date: new Date().toISOString().slice(0, 10),
    return_date: '',
    service_life: '',
    status: 'issued',
    issuer: '',
  };

  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({ search: '', categories: [], dateFrom: '', dateTo: '' });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

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
      const params = { employee_id: filters.employee || undefined };
      const res = await api.get('assets/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(item) {
    setForm({ ...item });
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.item_name) {
      alert('Заполните обязательные поля');
      return;
    }
    try {
      if (form.id) {
        await api.put(`assets/${form.id}`, form);
      } else {
        await api.post('assets/', form);
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
      await api.delete(`assets/${id}`);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({ ...f, employee_id: emp.id, employee_name: emp.full_name || emp.name }));
    }
  }

  const categories = Array.from(new Set(list.map((i) => i.category)));

  const aggregated = {
    totalByCategory: {},
    employeesWithAssets: new Set(),
    needReplacement: 0,
    overdue: 0,
  };
  for (const item of list) {
    aggregated.totalByCategory[item.category] = (aggregated.totalByCategory[item.category] || 0) + item.quantity;
    aggregated.employeesWithAssets.add(item.employee_id);
    if (item.status === 'replace') aggregated.needReplacement += 1;
    if (item.status === 'overdue') aggregated.overdue += 1;
  }

  return (
    <div className="space-y-6 max-w-full mx-auto">
      <h2 className="text-2xl font-semibold">Имущество сотрудников</h2>
      <div className="flex flex-wrap gap-2 items-end">
        <input
          className="border p-2"
          placeholder="Поиск"
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
        />
        <select className="border p-2" value={filters.employee} onChange={(e) => setFilters({ ...filters, employee: e.target.value })}>
          <option value="">Сотрудник</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>
              {e.full_name || e.name}
            </option>
          ))}
        </select>
        <input type="date" className="border p-2" value={filters.dateFrom} onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })} />
        <input type="date" className="border p-2" value={filters.dateTo} onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })} />
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
              <th className="p-2 text-left">ФИО</th>
              <th className="p-2 text-left">Должность</th>
              <th className="p-2 text-left">Подразделение</th>
              <th className="p-2 text-left">Категория</th>
              <th className="p-2 text-left">Наименование</th>
              <th className="p-2 text-left">Размер</th>
              <th className="p-2 text-left">Кол-во</th>
              <th className="p-2 text-left">Выдано</th>
              <th className="p-2 text-left">Возврат</th>
              <th className="p-2 text-left">Срок службы</th>
              <th className="p-2 text-left">Статус</th>
              <th className="p-2 text-left">Ответственный</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="p-2">{u.employee_name}</td>
                <td className="p-2">{u.position}</td>
                <td className="p-2">{u.department}</td>
                <td className="p-2">{u.category}</td>
                <td className="p-2">{u.item_name}</td>
                <td className="p-2">{u.size}</td>
                <td className="p-2">{u.quantity}</td>
                <td className="p-2">{u.issue_date}</td>
                <td className="p-2">{u.return_date || ''}</td>
                <td className="p-2">{u.service_life || ''}</td>
                <td className="p-2">{u.status}</td>
                <td className="p-2">{u.issuer}</td>
                <td className="p-2 space-x-1 text-right">
                  <button className="text-blue-600" onClick={() => startEdit(u)}>
                    <Pencil size={16} />
                  </button>
                  <button className="text-gray-600" onClick={() => remove(u.id)}>
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr>
                <td colSpan="13" className="p-4 text-center text-gray-500">
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="border rounded p-3 space-y-2">
        <h3 className="font-semibold">Агрегированная информация</h3>
        <ul className="list-disc pl-4">
          {Object.entries(aggregated.totalByCategory).map(([k, v]) => (
            <li key={k}>
              {k}: {v}
            </li>
          ))}
          <li>Сотрудников с имуществом: {aggregated.employeesWithAssets.size}</li>
          <li>Требует замены: {aggregated.needReplacement}</li>
          <li>Просрочено: {aggregated.overdue}</li>
        </ul>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="bg-white p-4 space-y-2 rounded shadow w-96">
            <h2 className="text-lg font-bold mb-2">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
            <select className="border p-2 w-full" value={form.employee_id} onChange={(e) => handleSelect(e.target.value)}>
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name || e.name}
                </option>
              ))}
            </select>
            <input className="border p-2 w-full" placeholder="Должность" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} />
            <input className="border p-2 w-full" placeholder="Подразделение" value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} />
            <input className="border p-2 w-full" placeholder="Категория" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} />
            <input className="border p-2 w-full" placeholder="Предмет" value={form.item_name} onChange={(e) => setForm({ ...form, item_name: e.target.value })} />
            <input className="border p-2 w-full" placeholder="Размер" value={form.size} onChange={(e) => setForm({ ...form, size: e.target.value })} />
            <input type="number" className="border p-2 w-full" placeholder="Количество" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
            <input type="date" className="border p-2 w-full" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} />
            <input type="date" className="border p-2 w-full" value={form.return_date} onChange={(e) => setForm({ ...form, return_date: e.target.value })} />
            <input type="number" className="border p-2 w-full" placeholder="Срок службы (мес.)" value={form.service_life} onChange={(e) => setForm({ ...form, service_life: Number(e.target.value) })} />
            <input className="border p-2 w-full" placeholder="Статус" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} />
            <input className="border p-2 w-full" placeholder="Ответственный" value={form.issuer} onChange={(e) => setForm({ ...form, issuer: e.target.value })} />
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
