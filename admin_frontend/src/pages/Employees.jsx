import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {
  UserPlus,
  Trash2,
  Pencil,
  FileDown,
  Archive,
} from 'lucide-react';
import api from '../api';
import UpcomingBirthdays from '../components/UpcomingBirthdays.jsx';

export default function Employees() {
  const emptyForm = {
    id: '',
    id_original: '',
    name: '',
    full_name: '',
    phone: '',
    card_number: '',
    bank: '',
    work_place: '',
    clothing_size: '',
    birthdate: '',
    note: '',
    status: 'active',
    position: '',
    is_admin: false,
    sync_to_bot: false,
    photo_file: null,
    photo_url: '',
    payout_chat_key: '',
    archived: false,
  };

  const [employees, setEmployees] = useState([]);
  const [positions, setPositions] = useState([]);
  const [workPlaces, setWorkPlaces] = useState([]);
  const [cashierChats, setCashierChats] = useState([]);
  const [filterName, setFilterName] = useState('');
  const [filterPhone, setFilterPhone] = useState('');
  const [sort, setSort] = useState('');
  const [selected, setSelected] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    load();
    loadPositions();
    loadCashierChats();
  }, []);

  async function load() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadCashierChats() {
    try {
      const res = await api.get('config/');
      const data = res.data || {};
      const rawChats = Array.isArray(data.card_dispatch_chats)
        ? data.card_dispatch_chats
        : [];
      const fallbackId = data.card_dispatch_chat_id;
      const normalized = rawChats
        .map((chat, idx) => {
          if (typeof chat !== 'object' || chat === null) return null;
          const chatId = Number(chat.chat_id ?? chat.id);
          if (!Number.isFinite(chatId)) return null;
          const key = String(chat.key ?? chat.id ?? `chat_${idx + 1}`);
          const name = String(chat.name ?? `Кассир ${idx + 1}`);
          return { key, name, chat_id: chatId };
        })
        .filter(Boolean);
      const fallbackNumber = Number(fallbackId);
      if (
        !normalized.length &&
        Number.isFinite(fallbackNumber) &&
        fallbackNumber !== 0
      ) {
        normalized.push({
          key: 'default',
          name: 'Основной кассир',
          chat_id: fallbackNumber,
        });
      }
      setCashierChats(normalized);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadPositions() {
    try {
      const res = await api.get('dictionary/');
      setPositions(res.data.positions || []);
      setWorkPlaces(res.data.work_places || []);
    } catch (err) {
      console.error(err);
    }
  }

  function resolveChatName(key) {
    if (!cashierChats.length) {
      return key ? key : '';
    }
    if (!key) {
      const first = cashierChats[0];
      return first ? `По умолчанию — ${first.name}` : 'По умолчанию';
    }
    const found = cashierChats.find((chat) => chat.key === key);
    if (found) {
      return found.name;
    }
    return key ? `Неизвестный чат (${key})` : '';
  }

  function formatDateRu(value) {
    if (!value) return '';
    return new Date(value).toLocaleDateString('ru-RU');
  }

  function startCreate() {
    setForm({ ...emptyForm, id_original: '' });
    setShowForm(true);
  }

  function startEdit(emp) {
    setForm({ ...emp, id: emp.id, id_original: emp.id, payout_chat_key: emp.payout_chat_key || '' });
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

  async function moveToArchive(id) {
    const employee = employees.find((e) => e.id === id);
    if (!employee) return;
    if (employee.status === 'active') {
      alert('Сначала измените статус на inactive, затем можно отправить в архив');
      return;
    }
    if (!window.confirm('Перенести сотрудника в архив?')) return;
    try {
      await api.post(`employees/${id}/archive`);
      setSelected((prev) => prev.filter((value) => value !== id));
      load();
    } catch (err) {
      console.error(err);
      alert('Не удалось переместить сотрудника в архив');
    }
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
      work_place: form.work_place || '',
      clothing_size: form.clothing_size || '',
      birthdate: form.birthdate || null,
      note: form.note || '',
      status: form.status || 'active',
      position: form.position || '',
      is_admin: form.is_admin,
      payout_chat_key: form.payout_chat_key || null,
    };
    try {
      if (form.id_original) {
        await api.put(`employees/${form.id_original}`, { id: form.id, ...payload });
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

  async function downloadPdf() {
    try {
      const res = await api.get('employees/export.pdf', { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'employees.pdf');
      document.body.appendChild(link);
      link.click();
    } catch (err) {
      console.error(err);
    }
  }

  const filtered = employees.filter(
    (e) =>
      e.full_name.toLowerCase().includes(filterName.toLowerCase()) &&
      e.phone.toLowerCase().includes(filterPhone.toLowerCase())
  );

  const sortedList = [...filtered];
  if (sort === 'name') {
    sortedList.sort((a, b) => a.full_name.localeCompare(b.full_name));
  } else if (sort === 'position') {
    sortedList.sort((a, b) => a.position.localeCompare(b.position));
  }

  return (
    <div className="space-y-6 max-w-full mx-auto">
      <h2 className="text-2xl font-semibold">Сотрудники</h2>
      <UpcomingBirthdays />
      <div className="flex flex-wrap gap-2 items-center">
        <input
          className="input flex-grow"
          placeholder="Фильтр по ФИО"
          value={filterName}
          onChange={(e) => setFilterName(e.target.value)}
        />
        <input
          className="input flex-grow"
          placeholder="Фильтр по телефону"
          value={filterPhone}
          onChange={(e) => setFilterPhone(e.target.value)}
        />
        <select
          className="input"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="">Без сортировки</option>
          <option value="name">По имени</option>
          <option value="position">По должности</option>
        </select>
        <button className="btn" onClick={downloadPdf}>
          <FileDown size={16} /> Экспорт PDF
        </button>
        <button className="btn" onClick={startCreate}>
          <UserPlus size={16} /> Добавить сотрудника
        </button>
        <button
          className="btn bg-red-600 hover:bg-red-700 disabled:opacity-50"
          disabled={!selected.length}
          onClick={deleteSelected}
        >
          <Trash2 size={16} /> Удалить выбранных
        </button>
        <Link
          className="btn bg-gray-100 text-gray-800 hover:bg-gray-200"
          to="/admin/archive"
        >
          <Archive size={16} /> Архив
        </Link>
      </div>
      <div className="overflow-auto border rounded shadow bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="p-2"></th>
              <th className="p-2 text-left">Фото</th>
              <th className="p-2 text-left">Имя</th>
              <th className="p-2 text-left">ФИО</th>
              <th className="p-2 text-left">Телефон</th>
              <th className="p-2 text-left">День рождения</th>
              <th className="p-2 text-left">Должность</th>
              <th className="p-2 text-left">Место</th>
              <th className="p-2 text-left">Размер</th>
              <th className="p-2 text-left">Чат кассира</th>
              <th className="p-2 text-left">Роль</th>
              <th className="p-2 text-left">Создан</th>
              <th className="p-2 text-left">История</th>
              <th className="p-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {sortedList.map((e) => (
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
                <td className="p-2">
                  {e.photo_url ? (
                    <img
                      src={e.photo_url}
                      alt="" className="w-8 h-8 rounded-full object-cover cursor-pointer"
                      onClick={() => window.open(e.photo_url, '_blank')}
                    />
                  ) : (
                    <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                      <span className="text-gray-500 text-xs">No photo</span>
                    </div>
                  )}
                </td>
                <td className="p-2">{e.name}</td>
                <td className="p-2">{e.full_name}</td>
                <td className="p-2">{e.phone}</td>
                <td className="p-2">{formatDateRu(e.birthdate)}</td>
                <td className="p-2">{e.position}</td>
                <td className="p-2">{e.work_place}</td>
                <td className="p-2">{e.clothing_size}</td>
                <td className="p-2">{resolveChatName(e.payout_chat_key)}</td>
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
                  {e.status !== 'active' && (
                    <button
                      className="text-amber-600 hover:text-amber-800 ml-2"
                      onClick={() => moveToArchive(e.id)}
                      title="Перенести в архив"
                    >
                      <Archive size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan="14" className="p-4 text-center text-gray-500">
                  Нет сотрудников
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="modal-backdrop">
          <div className="modal-card">
            <h2 className="text-xl font-semibold">
              {form.id ? 'Редактирование' : 'Новый сотрудник'}
            </h2>
            <input
              className="modal-control"
              placeholder="ID"
              value={form.id}
              onChange={(e) => setForm({ ...form, id: e.target.value })}
            />
            <input
              className="modal-control"
              placeholder="Имя"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
            <input
              className="modal-control"
              placeholder="ФИО"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <input
              className="modal-control"
              placeholder="Телефон"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
            <input
              className="modal-control"
              placeholder="Номер карты"
              value={form.card_number}
              onChange={(e) => setForm({ ...form, card_number: e.target.value })}
            />
            <input
              className="modal-control"
              placeholder="Банк"
              value={form.bank}
              onChange={(e) => setForm({ ...form, bank: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.position}
              onChange={(e) => setForm({ ...form, position: e.target.value })}
            >
              <option value="">Не выбрано</option>
              {positions.map((pos) => (
                <option key={pos} value={pos}>
                  {pos}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
              value={form.work_place}
              onChange={(e) => setForm({ ...form, work_place: e.target.value })}
            >
              <option value="">Не выбрано</option>
              {workPlaces.map((wp) => (
                <option key={wp} value={wp}>
                  {wp}
                </option>
              ))}
            </select>
            <input
              className="modal-control"
              placeholder="Размер формы"
              value={form.clothing_size}
              onChange={(e) => setForm({ ...form, clothing_size: e.target.value })}
            />
            <input
              type="date"
              className="modal-control"
              value={form.birthdate}
              onChange={(e) => setForm({ ...form, birthdate: e.target.value })}
            />
            <textarea
              className="modal-control"
              placeholder="Заметка"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.payout_chat_key}
              onChange={(e) => setForm({ ...form, payout_chat_key: e.target.value })}
            >
              <option value="">
                {cashierChats.length
                  ? `По умолчанию — ${cashierChats[0].name}`
                  : 'По умолчанию'}
              </option>
              {cashierChats.map((chat) => (
                <option key={chat.key} value={chat.key}>
                  {chat.name} — {chat.chat_id}
                </option>
              ))}
            </select>
            <select
              className="modal-control"
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
                onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })
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








