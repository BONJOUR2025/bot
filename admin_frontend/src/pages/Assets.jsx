import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus, Clock } from 'lucide-react';
import api from '../api';

export default function Assets() {
  const emptyForm = {
    id: null,
    employee_id: '',
    employee_name: '',
    position: '',
    item_name: '',
    size: '',
    quantity: 1,
    issue_date: new Date().toISOString().slice(0, 10),
    return_date: '',
    service_life: '',
  };

  const [list, setList] = useState([]);
  const [itemOptions, setItemOptions] = useState([]);
  const [positionOptions, setPositionOptions] = useState([]);
  const [sizeOptions, setSizeOptions] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({ search: '', employee: '', dateFrom: '', dateTo: '' });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    loadEmployees();
    load();
    loadDictionary();
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
      setItemOptions(Array.from(new Set(res.data.map((i) => i.item_name).filter(Boolean))));
      setSizeOptions(Array.from(new Set(res.data.map((i) => i.size).filter(Boolean))));
      
    } catch (err) {
      console.error(err);
    }
  }

  async function loadDictionary() {
    try {
      const res = await api.get('dictionary/');
      setPositionOptions(res.data.positions || []);
      setItemOptions((prev) => Array.from(new Set([...(prev || []), ...((res.data.asset_items || []))])));
      setSizeOptions((prev) => Array.from(new Set([...(prev || []), ...((res.data.asset_sizes || []))])));
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
      setForm((f) => ({
        ...f,
        employee_id: emp.id,
        employee_name: emp.full_name || emp.name,
        position: emp.position || '',
        size: emp.clothing_size || '',
      }));
    }
  }

  const aggregated = {
    employeesWithAssets: new Set(),
  };
  for (const item of list) {
    aggregated.employeesWithAssets.add(item.employee_id);
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
        <input type="date" className="border p-2" value={filters?.dateFrom ?? ""} onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })} />
        <input type="date" className="border p-2" value={filters?.dateTo ?? ""} onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })} />
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
              <th className="p-2 text-left">ФИО</th>
              <th className="p-2 text-left">Должность</th>
              <th className="p-2 text-left">Наименование</th>
              <th className="p-2 text-left">Размер</th>
              <th className="p-2 text-left">Кол-во</th>
              <th className="p-2 text-left">Выдано</th>
              <th className="p-2 text-left">Возврат</th>
              <th className="p-2 text-left">Срок службы</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="p-2">{u.employee_name}</td>
                <td className="p-2">{u.position}</td>
                <td className="p-2">{u.item_name}</td>
                <td className="p-2">{u.size}</td>
                <td className="p-2">{u.quantity}</td>
                <td className="p-2">{u.issue_date}</td>
                <td className="p-2">{u.return_date || ''}</td>
                <td className="p-2">{u.service_life || ''}</td>
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
                <td colSpan="9" className="p-4 text-center text-gray-500">
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
          <li>Сотрудников с имуществом: {aggregated.employeesWithAssets.size}</li>
        </ul>
      </div>

      {showForm && (
        <div className="modal-backdrop">
          <div className="modal-card max-w-xl">
            <h2 className="text-xl font-semibold">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
            <select className="modal-control" value={form.employee_id} onChange={(e) => handleSelect(e.target.value)}>
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.full_name || e.name}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
              value={form.position}
              onChange={(e) => setForm({ ...form, position: e.target.value })}
            >
              <option value="">Должность</option>
              {positionOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
              value={form.item_name}
              onChange={(e) => setForm({ ...form, item_name: e.target.value })}
            >
              <option value="">Предмет</option>
              {itemOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
              value={form.size}
              onChange={(e) => setForm({ ...form, size: e.target.value })}
            >
              <option value="">Размер</option>
              {sizeOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
            <input type="number" className="modal-control" placeholder="Количество" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })} />
            <input type="date" className="modal-control" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} />
            <input type="date" className="modal-control" value={form.return_date} onChange={(e) => setForm({ ...form, return_date: e.target.value })} />
            <input type="number" className="modal-control" placeholder="Срок службы (мес.)" value={form.service_life} onChange={(e) => setForm({ ...form, service_life: Number(e.target.value) })} />
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











