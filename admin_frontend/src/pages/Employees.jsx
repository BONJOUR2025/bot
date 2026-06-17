import { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import {
  UserPlus,
  Trash2,
  Pencil,
  FileDown,
  Archive,
} from 'lucide-react';
import api from '../api';
import UpcomingBirthdays from '../components/UpcomingBirthdays.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { useToast } from '../providers/ToastProvider.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

function ExternalUserSelect({ value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(value || '');
  const [options, setOptions] = useState([]);
  const containerRef = useRef(null);

  useEffect(() => { setQuery(value || ''); }, [value]);

  useEffect(() => {
    function onOutside(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', onOutside);
    return () => document.removeEventListener('mousedown', onOutside);
  }, []);

  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      api.get('employees/external-users', { params: { search: query } })
        .then((res) => setOptions(res.data || []))
        .catch(() => setOptions([]));
    }, 300);
    return () => clearTimeout(t);
  }, [query, open]);

  function pick(option) {
    const code = String(option.user_id);
    onChange(code);
    setQuery(code);
    setOpen(false);
  }

  const matched = options.find((o) => String(o.user_id) === String(value));

  return (
    <div ref={containerRef} className="relative space-y-1">
      <input
        className="modal-control font-mono"
        placeholder="Поиск по базе ЗП или ID из Агбис..."
        value={query}
        onChange={(e) => { setQuery(e.target.value); onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
      />
      {matched && (
        <div className="text-xs text-gray-500">{matched.description}</div>
      )}
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {options.map((o) => (
            <button key={o.user_id} type="button" onClick={() => pick(o)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50">
              {o.description} <span className="text-xs text-gray-400">№{o.user_id}</span>
            </button>
          ))}
          {options.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-400">Совпадений не найдено — можно вписать ID вручную</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Employees() {
  const { toast } = useToast();
  const { isMobile } = useViewport();
  const navigate = useNavigate();
  const location = useLocation();

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
    external_code: '',
    status: 'active',
    position: '',
    is_admin: false,
    bot_user: false,
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
  const [loading, setLoading] = useState(true);
  const [confirmWarnings, setConfirmWarnings] = useState([]);

  useEffect(() => {
    load();
    loadPositions();
    loadCashierChats();
  }, []);

  useEffect(() => {
    const editId = location.state?.editId;
    if (editId && employees.length > 0) {
      const emp = employees.find((e) => e.id === editId);
      if (emp) startEdit(emp);
    }
  }, [location.state, employees]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки сотрудников', 'error');
    } finally {
      setLoading(false);
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
    const isBotUser = emp.bot_user ?? (!String(emp.id).startsWith('nb_') && !!emp.id);
    setForm({ ...emp, id: emp.id, id_original: emp.id, bot_user: isBotUser, payout_chat_key: emp.payout_chat_key || '' });
    setShowForm(true);
  }

  function toggleSelect(id, checked) {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  }

  async function deleteSelected() {
    if (!selected.length) return;
    if (!window.confirm('Удалить выбранных сотрудников?')) return;
    try {
      for (const id of selected) {
        await api.delete(`employees/${id}`);
      }
      setSelected([]);
      toast('Сотрудники удалены', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка при удалении', 'error');
    }
  }

  async function moveToArchive(id) {
    const employee = employees.find((e) => e.id === id);
    if (!employee) return;
    if (employee.status === 'active') {
      toast('Сначала измените статус на inactive', 'warning');
      return;
    }
    if (!window.confirm('Перенести сотрудника в архив?')) return;
    try {
      await api.post(`employees/${id}/archive`);
      setSelected((prev) => prev.filter((value) => value !== id));
      toast('Сотрудник перемещён в архив', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Не удалось переместить в архив', 'error');
    }
  }

  async function doSave() {
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
      external_code: form.external_code || '',
      status: form.status || 'active',
      position: form.position || '',
      is_admin: form.is_admin,
      bot_user: form.bot_user,
      payout_chat_key: form.payout_chat_key || null,
    };
    try {
      if (form.id_original) {
        await api.put(`employees/${form.id_original}`, { id: form.bot_user ? form.id : form.id_original, ...payload });
      } else {
        if (form.bot_user) payload.id = form.id || '';
        await api.post('employees/', payload);
      }
      if (form.photo_file) {
        const fd = new FormData();
        fd.append('file', form.photo_file);
        await api.post(`employees/${payload.id}/photo`, fd);
      }
      setShowForm(false);
      setForm(emptyForm);
      toast('Сотрудник сохранён', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка при сохранении', 'error');
    }
  }

  function saveForm() {
    if (!form.name || !form.full_name || !form.phone) {
      toast('Заполните обязательные поля', 'warning');
      return;
    }
    const warnings = [];
    if (!form.card_number) {
      warnings.push('Номер карты не заполнен.');
    } else {
      const phoneDigits = form.phone.replace(/\D/g, '');
      const cardDigits  = form.card_number.replace(/\D/g, '');
      if (phoneDigits && cardDigits && phoneDigits !== cardDigits) {
        warnings.push('Номер карты отличается от номера телефона.');
      }
    }
    if (warnings.length > 0) {
      setConfirmWarnings(warnings);
      return;
    }
    doSave();
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
      toast('PDF скачан', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка экспорта PDF', 'error');
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
      <p className="text-sm text-gray-500">
        Чтобы отправить сотрудника в архив, сначала переведите его в статус{' '}
        <span className="font-medium">inactive</span>.
      </p>

      {loading ? (
        <div className="border rounded shadow bg-white p-4">
          <SkeletonTable rows={8} cols={6} />
        </div>
      ) : isMobile ? (
        <div className="space-y-3">
          {sortedList.length === 0 && (
            <div className="py-6 text-center text-gray-500 text-sm">Нет сотрудников</div>
          )}
          {sortedList.map((e) => {
            const canArchive = e.status !== 'active';
            return (
              <div
                key={e.id}
                className={`border rounded-xl bg-white shadow-sm overflow-hidden cursor-pointer ${e.is_admin ? 'border-orange-200' : ''} ${e.status !== 'active' ? 'opacity-70' : ''}`}
                onClick={() => navigate(`/admin/employees/${e.id}`)}
              >
                <div className="px-4 py-3 border-b bg-gray-50 flex items-center gap-3">
                  <label className="flex items-center gap-2 cursor-pointer" onClick={(ev) => ev.stopPropagation()}>
                    <input type="checkbox" checked={selected.includes(e.id)} onChange={(ev) => toggleSelect(e.id, ev.target.checked)} />
                  </label>
                  {e.photo_url ? (
                    <img src={e.photo_url} alt="" className="w-9 h-9 rounded-full object-cover shrink-0" />
                  ) : (
                    <div className="w-9 h-9 rounded-full bg-gray-200 flex items-center justify-center shrink-0">
                      <span className="text-gray-400 text-xs">—</span>
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm truncate">{e.full_name}</div>
                    <div className="text-xs text-gray-500">{e.position}</div>
                  </div>
                  {e.is_admin && <span className="text-xs text-orange-600 font-medium shrink-0">Админ</span>}
                </div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Телефон</span>
                    <span>{e.phone}</span>
                  </div>
                  {e.birthdate && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">День рождения</span>
                      <span>{formatDateRu(e.birthdate)}</span>
                    </div>
                  )}
                </div>
                <div className="px-4 py-2 border-t flex justify-end gap-3" onClick={(ev) => ev.stopPropagation()}>
                  <button className="text-blue-600" onClick={() => startEdit(e)}><Pencil size={18} /></button>
                  <a href={`/api/employees/${e.id}/profile.pdf`} className="text-gray-600" title="PDF"><FileDown size={18} /></a>
                  <button
                    className={canArchive ? 'text-amber-600' : 'text-gray-300'}
                    onClick={() => { if (canArchive) moveToArchive(e.id); }}
                    disabled={!canArchive}
                    title={canArchive ? 'В архив' : 'Сначала переведите в inactive'}
                  >
                    <Archive size={18} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="overflow-auto border rounded shadow bg-white">
          <table className="min-w-[900px] text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="p-2"></th>
                <th className="p-2 text-left">Фото</th>
                <th className="p-2 text-left">Имя</th>
                <th className="p-2 text-left">ФИО</th>
                <th className="p-2 text-left">Телефон</th>
                <th className="p-2 text-left">День рождения</th>
                <th className="p-2 text-left">Должность</th>
                <th className="p-2 text-left">Роль</th>
                <th className="p-2 text-left">Создан</th>
                <th className="p-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {sortedList.map((e) => {
                const canArchive = e.status !== 'active';
                const archiveTitle = canArchive
                  ? 'Перенести в архив'
                  : 'Переведите сотрудника в статус inactive, чтобы архивировать';
                return (
                  <tr
                    key={e.id}
                    className={`cursor-pointer hover:bg-blue-50 transition-colors ${e.is_admin ? 'bg-orange-50 hover:bg-orange-100' : ''} ${
                      e.status !== 'active' ? 'opacity-60' : ''
                    }`}
                    onClick={() => navigate(`/admin/employees/${e.id}`)}
                  >
                  <td className="p-2" onClick={(ev) => ev.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.includes(e.id)}
                      onChange={(ev) => toggleSelect(e.id, ev.target.checked)}
                    />
                  </td>
                  <td className="p-2" onClick={(ev) => ev.stopPropagation()}>
                    {e.photo_url ? (
                      <img
                        src={e.photo_url}
                        alt="" className="w-8 h-8 rounded-full object-cover cursor-pointer"
                        onClick={() => window.open(e.photo_url, '_blank')}
                      />
                    ) : (
                      <div className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center">
                        <span className="text-gray-500 text-xs">—</span>
                      </div>
                    )}
                  </td>
                  <td className="p-2 font-medium">{e.name}</td>
                  <td className="p-2">{e.full_name}</td>
                  <td className="p-2">{e.phone}</td>
                  <td className="p-2">{formatDateRu(e.birthdate)}</td>
                  <td className="p-2">{e.position}</td>
                  <td className="p-2">{e.is_admin ? 'Админ' : 'Польз.'}</td>
                  <td className="p-2 text-gray-400 text-xs">{new Date(e.created_at).toLocaleDateString()}</td>
                  <td className="p-2 text-right" onClick={(ev) => ev.stopPropagation()}>
                    <button className="text-blue-600" onClick={() => startEdit(e)} title="Редактировать">
                      <Pencil size={16} />
                    </button>
                    <a
                      href={`/api/employees/${e.id}/profile.pdf`}
                      className="text-gray-600 ml-2"
                      title="Скачать PDF"
                    >
                      <FileDown size={16} />
                    </a>
                    <button
                      className={`ml-2 ${
                        canArchive
                          ? 'text-amber-600 hover:text-amber-800'
                          : 'cursor-not-allowed text-gray-400'
                      }`}
                      onClick={() => { if (canArchive) moveToArchive(e.id); }}
                      disabled={!canArchive}
                      title={archiveTitle}
                    >
                      <Archive size={16} className={!canArchive ? 'opacity-50' : ''} />
                    </button>
                  </td>
                </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan="10" className="p-4 text-center text-gray-500">
                    Нет сотрудников
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-lg overflow-y-auto max-h-[90vh]">
            <h2 className="text-xl font-semibold">
              {form.id_original ? 'Редактирование' : 'Новый сотрудник'}
            </h2>

            {/* Bot user toggle */}
            <label className="flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={form.bot_user}
                onChange={(e) => setForm({ ...form, bot_user: e.target.checked, id: e.target.checked ? form.id : '' })}
              />
              Пользователь бота
            </label>

            {form.bot_user && (
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Telegram ID</label>
                <input className="modal-control" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} />
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Имя *</label>
                <input className="modal-control" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">ФИО *</label>
                <input className="modal-control" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Телефон *</label>
                <input className="modal-control" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Номер карты</label>
                <input className="modal-control" value={form.card_number} onChange={(e) => setForm({ ...form, card_number: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Банк</label>
                <input className="modal-control" value={form.bank} onChange={(e) => setForm({ ...form, bank: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Размер формы</label>
                <input className="modal-control" value={form.clothing_size} onChange={(e) => setForm({ ...form, clothing_size: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Должность</label>
                <select className="modal-control" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })}>
                  <option value="">Не выбрано</option>
                  {positions.map((pos) => <option key={pos} value={pos}>{pos}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Место работы</label>
                <select className="modal-control" value={form.work_place} onChange={(e) => setForm({ ...form, work_place: e.target.value })}>
                  <option value="">Не выбрано</option>
                  {workPlaces.map((wp) => <option key={wp} value={wp}>{wp}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Дата рождения</label>
                <input type="date" className="modal-control" value={form.birthdate} onChange={(e) => setForm({ ...form, birthdate: e.target.value })} />
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Чат кассира</label>
                <select className="modal-control" value={form.payout_chat_key} onChange={(e) => setForm({ ...form, payout_chat_key: e.target.value })}>
                  <option value="">{cashierChats.length ? `По умолчанию — ${cashierChats[0].name}` : 'По умолчанию'}</option>
                  {cashierChats.map((chat) => <option key={chat.key} value={chat.key}>{chat.name} — {chat.chat_id}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Статус</label>
                <select className="modal-control" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                  <option value="active">Активный</option>
                  <option value="inactive">Неактивный</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Внешний код (ID в Агбис, для кассовых перемещений)</label>
              <ExternalUserSelect value={form.external_code} onChange={(v) => setForm({ ...form, external_code: v })} />
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Заметка</label>
              <textarea className="modal-control" rows={2} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            </div>

            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.sync_to_bot} onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })} />
                Отразить в боте
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={form.is_admin} onChange={(e) => setForm({ ...form, is_admin: e.target.checked })} />
                Администратор
              </label>
            </div>

            <div>
              <label className="block text-xs font-medium text-[color:var(--color-muted-foreground)] mb-1">Фото</label>
              <input type="file" onChange={handleFile} />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button className="btn" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn--primary" onClick={saveForm}>Сохранить</button>
            </div>
          </div>
        </div>
      )}

      {/* Confirm warnings dialog */}
      {confirmWarnings.length > 0 && (
        <div className="modal-backdrop" style={{ zIndex: 70 }}>
          <div className="modal-card max-w-sm w-full">
            <h3 className="text-base font-semibold">Предупреждение</h3>
            <ul className="text-sm space-y-1">
              {confirmWarnings.map((w, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">⚠</span> {w}
                </li>
              ))}
            </ul>
            <p className="text-sm text-[color:var(--color-muted-foreground)]">Всё равно сохранить?</p>
            <div className="flex justify-end gap-2 pt-1">
              <button className="btn" onClick={() => setConfirmWarnings([])}>Отмена</button>
              <button className="btn btn--primary" onClick={() => { setConfirmWarnings([]); doSave(); }}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
