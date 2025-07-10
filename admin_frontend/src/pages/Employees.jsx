import { useState, useEffect } from 'react';
import {
  UserPlus,
  Trash2,
  Pencil,
  Camera,
  FileDown,
} from 'lucide-react';
import api from '../api';
import UpcomingBirthdays from '../components/UpcomingBirthdays.jsx';

export default function Employees() {
  const emptyForm = {
    id: '',
    name: '',
    full_name: '',
    phone: '',
    card_number: '',
    bank: '',
    birthdate: '',
    note: '',
    status: 'active',
    position: '',
    is_admin: false,
    sync_to_bot: false,
    photo_file: null,
    photo_url: '',
  };

  const [employees, setEmployees] = useState([]);
  const [filterName, setFilterName] = useState('');
  const [filterPhone, setFilterPhone] = useState('');
  const [selected, setSelected] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const res = await api.get('employees/');
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  function formatDateRu(value) {
    if (!value) return '';
    return new Date(value).toLocaleDateString('ru-RU');
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(emp) {
    setForm({ ...emp, id: emp.id });
    setShowForm(true);
  }

  function toggleSelect(id, checked) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  }

  async function deleteSelected() {
    if (!selected.length) return;
    if (!window.confirm('Удалить выбранных сотрудников?')) return;
    for (const id of selected) {
      await api.delete(`employees/${id}`);
    }
    setSelected([]);
    load();
  }

  async function saveForm() {
    if (!form.name || !form.full_name || !form.phone) {
      alert('Заполните обязательные поля');
      return;
    }
    const payload = {
      name: form.name,
      full_name: form.full_name,
      phone: form.phone,
      card_number: form.card_number || '',
      bank: form.bank || '',
      birthdate: form.birthdate || null,
      note: form.note || '',
      status: form.status || 'active',
      position: form.position || '',
      is_admin: form.is_admin,
    };
    try {
      if (form.id) {
        await api.put(`employees/${form.id}`, payload);
      } else {
        payload.id = form.id || Date.now().toString();
        await api.post('employees/', payload);
      }
      if (form.photo_file) {
        const fd = new FormData();
        fd.append('file', form.photo_file);
        await api.post(`employees/${payload.id}/photo`, fd);
      }
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      console.error(err);
      alert('Ошибка при сохранении');
    }
  }

  function handleFile(e) {
    const file = e.target.files?.[0];
    if (file) {
      setForm((f) => ({ ...f, photo_file: file }));
    }
  }

  const filtered = employees.filter(
    (e) =>
      e.full_name.toLowerCase().includes(filterName.toLowerCase()) &&
      e.phone.toLowerCase().includes(filterPhone.toLowerCase())
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold">Сотрудники</h2>
      <UpcomingBirthdays />
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="border p-2 flex-grow"
          placeholder="Фильтр по ФИО"
          value={filterName}
          onChange={(e) => setFilterName(e.target.value)}
        />
        <input
          className="border p-2 flex-grow"
          placeholder="Фильтр по телефону"
          value={filterPhone}
          onChange={(e) => setFilterPhone(e.target.value)}
        />
        <button
          className="bg-blue-600 text-white px-4 py-2 rounded-xl flex items-center gap-1"
          onClick={startCreate}
        >
          <UserPlus size={16} /> Добавить сотрудника
        </button>
        <button
          className="bg-red-600 text-white px-4 py-2 rounded-xl flex items-center gap-1 disabled:opacity-50"
          disabled={!selected.length}
          onClick={deleteSelected}
        >
          <Trash2 size={16} /> Удалить выбранных
        </button>
      </div>
      <div className="overflow-auto border rounded shadow bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2"></th>
              <th className="p-2 text-left">ID</th>
              <th className="p-2 text-left">Фото</th>
              <th className="p-2 text-left">Имя</th>
              <th className="p-2 text-left">ФИО</th>
              <th className="p-2 text-left">Телефон</th>
              <th className="p-2 text-left">День рождения</th>
              <th className="p-2 text-left">Должность</th>
              <th className="p-2 text-left">Роль</th>
              <th className="p-2 text-left">Создан</th>
              <th className="p-2 text-left">История</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.map((e) => (
              <tr
                key={e.id}
                className={`${e.is_admin ? 'bg-orange-50' : ''} ${
                  e.status !== 'active' ? 'bg-neutral-100' : ''
                }`}
              >
                <td className="p-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(e.id)}
                    onChange={(ev) => toggleSelect(e.id, ev.target.checked)}
                  />
                </td>
                <td className="p-2">{e.id}</td>
                <td className="p-2">
                  {e.photo_url ? (
                    <img
                      src={e.photo_url}
                      alt=""
                      className="w-8 h-8 rounded-full object-cover cursor-pointer"
                      onClick={() => window.open(e.photo_url, '_blank')}
                    />
                  ) : (
                    <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                      <Camera size={14} className="text-gray-500" />
                    </div>
                  )}
                </td>
                <td className="p-2">{e.name}</td>
                <td className="p-2">{e.full_name}</td>
                <td className="p-2">{e.phone}</td>
                <td className="p-2">{formatDateRu(e.birthdate)}</td>
                <td className="p-2">{e.position}</td>
                <td className="p-2">{e.is_admin ? 'Админ' : 'Пользователь'}</td>
                <td className="p-2">{new Date(e.created_at).toLocaleDateString()}</td>
                <td className="p-2">
                  <a
                    href={`/admin/incentives?employee_id=${e.id}`}
                    className="text-blue-600 underline"
                  >
                    История
                  </a>
                </td>
                <td className="p-2 text-right">
                  <button className="text-blue-600" onClick={() => startEdit(e)}>
                    <Pencil size={16} />
                  </button>
                  <a
                    href={`/api/employees/${e.id}/profile.pdf`}
                    className="text-gray-600 ml-2"
                    title="Скачать PDF"
                  >
                    <FileDown size={16} />
                  </a>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan="11" className="p-4 text-center text-gray-500">
                  Нет сотрудников
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
              {form.id ? 'Редактирование' : 'Новый сотрудник'}
            </h2>
            <input
              className="border p-2 w-full"
              placeholder="Имя"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="border p-2 w-full"
              placeholder="ФИО"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <input
              className="border p-2 w-full"
              placeholder="Телефон"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
            <input
              className="border p-2 w-full"
              placeholder="Номер карты"
              value={form.card_number}
              onChange={(e) => setForm({ ...form, card_number: e.target.value })}
            />
            <input
              className="border p-2 w-full"
              placeholder="Банк"
              value={form.bank}
              onChange={(e) => setForm({ ...form, bank: e.target.value })}
            />
            <input
              className="border p-2 w-full"
              placeholder="Должность"
              value={form.position}
              onChange={(e) => setForm({ ...form, position: e.target.value })}
            />
            <input
              type="date"
              className="border p-2 w-full"
              value={form.birthdate}
              onChange={(e) => setForm({ ...form, birthdate: e.target.value })}
            />
            <textarea
              className="border p-2 w-full"
              placeholder="Заметка"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
            <select
              className="border p-2 w-full"
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
            >
              <option value="active">active</option>
              <option value="inactive">inactive</option>
            </select>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.sync_to_bot}
                onChange={(e) =>
                  setForm({ ...form, sync_to_bot: e.target.checked })
                }
              />
              Отразить в боте
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.is_admin}
                onChange={(e) => setForm({ ...form, is_admin: e.target.checked })}
              />
              Администратор
            </label>
            <input type="file" onChange={handleFile} />
            <div className="flex justify-end gap-2 pt-2">
              <button className="bg-gray-300 px-3 py-1 rounded-xl" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="bg-blue-600 text-white px-3 py-1 rounded-xl" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
