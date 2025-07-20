import { useEffect, useState } from 'react';
import { Pencil, Trash2, Plus } from 'lucide-react';
import api from '../api';

export default function Uniforms() {
  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    item: '',
    size: '',
    quantity: 1,
    issue_date: new Date().toISOString().slice(0, 10),
    return_date: '',
    comment: '',
  };

  const [list, setList] = useState([]);
  const [itemOptions, setItemOptions] = useState([]);
  const [sizeOptions, setSizeOptions] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [filters, setFilters] = useState({ employee: '' });
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
      const res = await api.get('uniforms/', { params });
      setList(res.data);
      setItemOptions(Array.from(new Set(res.data.map((i) => i.item).filter(Boolean))));
      setSizeOptions(Array.from(new Set(res.data.map((i) => i.size).filter(Boolean))));
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
    if (!form.employee_id || !form.item) {
      alert('Заполните обязательные поля');
      return;
    }
    try {
      if (form.id) {
        await api.put(`uniforms/${form.id}`, form);
      } else {
        await api.post('uniforms/', form);
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
      await api.delete(`uniforms/${id}`);
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
      <h2 className="text-2xl font-semibold">Фирменная одежда</h2>
      <div className="flex flex-wrap gap-2 items-end">
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
              <th className="p-2 text-left">Предмет</th>
              <th className="p-2 text-left">Размер</th>
              <th className="p-2 text-left">Кол-во</th>
              <th className="p-2 text-left">Выдано</th>
              <th className="p-2 text-left">Возврат</th>
              <th className="p-2 text-left">Комментарий</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {list.map((u) => (
              <tr key={u.id} className="hover:bg-gray-50">
                <td className="p-2">{u.name}</td>
                <td className="p-2">{u.item}</td>
                <td className="p-2">{u.size}</td>
                <td className="p-2">{u.quantity}</td>
                <td className="p-2">{u.issue_date}</td>
                <td className="p-2">{u.return_date || ''}</td>
                <td className="p-2 whitespace-pre-wrap">{u.comment}</td>
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
                <td colSpan="8" className="p-4 text-center text-gray-500">
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
            <h2 className="text-lg font-bold mb-2">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
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
            <input
              list="uniform-items"
              className="border p-2 w-full"
              placeholder="Предмет"
              value={form.item}
              onChange={(e) => setForm({ ...form, item: e.target.value })}
            />
            <datalist id="uniform-items">
              {itemOptions.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
            <input
              list="uniform-sizes"
              className="border p-2 w-full"
              placeholder="Размер"
              value={form.size}
              onChange={(e) => setForm({ ...form, size: e.target.value })}
            />
            <datalist id="uniform-sizes">
              {sizeOptions.map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
            <input
              type="number"
              className="border p-2 w-full"
              placeholder="Количество"
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: Number(e.target.value) })}
            />
            <input
              type="date"
              className="border p-2 w-full"
              value={form.issue_date}
              onChange={(e) => setForm({ ...form, issue_date: e.target.value })}
            />
            <input
              type="date"
              className="border p-2 w-full"
              value={form.return_date}
              onChange={(e) => setForm({ ...form, return_date: e.target.value })}
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
