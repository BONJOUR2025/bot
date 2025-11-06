import { useEffect, useState } from 'react';
import {
  CheckCircle,
  Download,
  Pencil,
  RefreshCw,
  Trash2,
  XCircle,
} from 'lucide-react';
import api from '../api';

const MAX_AMOUNT = 100000;
const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];

function Toast({ message, type = 'info', onClose }) {
  useEffect(() => {
    if (!message) return undefined;
    const id = setTimeout(onClose, 3000);
    return () => clearTimeout(id);
  }, [message, onClose]);
  if (!message) return null;
  const color = type === 'error' ? 'bg-red-600' : 'bg-green-600';
  return (
    <div
      className={`fixed top-4 right-4 ${color} text-white px-3 py-2 rounded shadow`}
    >
      {message}
    </div>
  );
}

function Summary({ list }) {
  const total = list.reduce((sum, p) => sum + Number(p.amount || 0), 0);
  const statusStats = list.reduce((acc, p) => {
    acc[p.status] = (acc[p.status] || 0) + 1;
    return acc;
  }, {});
  const typeStats = list.reduce((acc, p) => {
    acc[p.payout_type] = (acc[p.payout_type] || 0) + Number(p.amount || 0);
    return acc;
  }, {});
  const sumAll = Object.values(typeStats).reduce((s, v) => s + v, 0) || 1;
  return (
    <div className="space-y-3">
      <div>
        Всего: <strong>{list.length}</strong> заявок на сумму{' '}
        <strong>{total} ₽</strong>
      </div>
      <div className="flex flex-wrap gap-3 text-sm">
        {Object.entries(statusStats).map(([k, v]) => (
          <div key={k} className="bg-gray-100 px-2 py-1 rounded">
            {k}: {v}
          </div>
        ))}
      </div>
      <div className="space-y-1">
        {Object.entries(typeStats).map(([k, v]) => (
          <div key={k} className="flex items-center gap-2 text-sm">
            <div className="w-20">{k}</div>
            <div className="flex-1 h-2 bg-gray-200 rounded">
              <div
                className="h-2 bg-blue-500 rounded"
                style={{ width: `${(v / sumAll) * 100}%` }}
              />
            </div>
            <div className="w-16 text-right">{v}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatDateTime(value) {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) {
    const fixed = value.replace(' ', 'T');
    const dt = new Date(fixed);
    if (Number.isNaN(dt.getTime())) return value;
    return (
      dt.toLocaleDateString('ru-RU') +
      ' ' +
      dt.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    );
  }
  return (
    d.toLocaleDateString('ru-RU') +
    ' ' +
    d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  );
}

export default function Payouts() {
  const emptyForm = {
    id: null,
    user_id: '',
    name: '',
    phone: '',
    bank: '',
    amount: '',
    payout_type: 'Аванс',
    method: '💳 На карту',
    status: 'Ожидает',
    sync_to_bot: false,
    notify_user: true,
    note: '',
    show_note_in_bot: false,
  };

  const [payouts, setPayouts] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [useFullName, setUseFullName] = useState(true);
  const [filters, setFilters] = useState({
    query: '',
    type: '',
    status: '',
    method: '',
    from: '',
    to: '',
  });
  const [showEditor, setShowEditor] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [toast, setToast] = useState(null);
  const [toastType, setToastType] = useState('info');

  useEffect(() => {
    load();
    loadEmployees();
    window.refreshPage = load;
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
        payout_type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('payouts/', { params });
      let list = res.data;
      if (filters.query) {
        const q = filters.query.toLowerCase();
        list = list.filter((p) => p.name?.toLowerCase().includes(q));
      }
      setPayouts(list);
    } catch (err) {
      console.error(err);
    }
  }

  function resetFilters() {
    setFilters({ query: '', type: '', status: '', method: '', from: '', to: '' });
    load();
  }

  async function updateStatus(id, status) {
    try {
      let endpoint = '';
      switch (status) {
        case 'Одобрено':
          endpoint = `payouts/${id}/approve`;
          break;
        case 'Отклонено':
          endpoint = `payouts/${id}/reject`;
          break;
        case 'Выплачено':
          endpoint = `payouts/${id}/mark_paid`;
          break;
        default:
          return;
      }
      await api.post(endpoint);
      setToast('Статус обновлён');
      setToastType('info');
      load();
    } catch (err) {
      console.error(err);
      setToast('Ошибка запроса');
      setToastType('error');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить выплату?')) return;
    try {
      await api.delete(`payouts/${id}`);
      setToast('Выплата удалена');
      setToastType('info');
      load();
    } catch (err) {
      console.error(err);
      setToast('Ошибка удаления');
      setToastType('error');
    }
  }

  function openCreate() {
    setForm(emptyForm);
    setShowEditor(true);
  }

  function openEdit(p) {
    setForm({
      ...p,
      notify_user: true,
      note: p.note || '',
      show_note_in_bot: p.show_note_in_bot || false,
    });
    setShowEditor(true);
  }

  async function saveForm() {
    const amount = Number(form.amount || 0);
    if (!form.user_id || !amount || amount > MAX_AMOUNT) {
      setToast('Неверные данные');
      setToastType('error');
      return;
    }
    const payload = { ...form, amount };
    try {
      if (form.id) {
        await api.put(`payouts/${form.id}`, payload);
      } else {
        await api.post('payouts/', payload);
      }
      setShowEditor(false);
      setForm(emptyForm);
      setToast('Сохранено');
      setToastType('info');
      load();
    } catch (err) {
      console.error(err);
      setToast('Ошибка сохранения');
      setToastType('error');
    }
  }

  function handleSelect(id) {
    const emp = employees.find((e) => String(e.id) === String(id));
    if (emp) {
      setForm((f) => ({
        ...f,
        user_id: emp.id,
        name: useFullName ? emp.full_name || emp.name : emp.name || emp.full_name,
        phone: emp.phone || '',
        bank: emp.bank || emp.card_number || '',
      }));
    }
  }

  function exportPdf() {
    const q = new URLSearchParams({
      payout_type: filters.type,
      status: filters.status,
      method: filters.method,
      date_from: filters.from,
      date_to: filters.to,
    });
    window.open(`/api/payouts/export.pdf?${q.toString()}`, '_blank');
  }

  async function checkTelegram() {
    try {
      await api.get('payouts/unconfirmed');
      load();
      setToast('Заявки обновлены');
      setToastType('info');
    } catch (err) {
      console.error(err);
      setToast('Ошибка обновления');
      setToastType('error');
    }
  }

  const statusColor = (s) => {
    switch (s) {
      case 'Одобрено':
        return 'bg-green-100 text-green-800';
      case 'Отклонено':
        return 'bg-red-100 text-red-800';
      case 'Выплачено':
        return 'bg-blue-100 text-blue-800';
      default:
        return 'bg-yellow-100 text-yellow-800';
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <Toast message={toast} type={toastType} onClose={() => setToast(null)} />

      <h2 className="text-2xl font-semibold tracking-tight text-gray-800 flex items-center gap-2">
        Выплаты
        <button
          onClick={checkTelegram}
          title="Проверить бот"
          className="ml-2 text-blue-600 hover:text-blue-800"
        >
          <RefreshCw size={18} />
        </button>
      </h2>

      <div className="flex flex-wrap gap-2 items-end">
        <input
          className="border p-2 flex-grow"
          placeholder="Поиск по ФИО"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        <select
          className="border p-2"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="Аванс">Аванс</option>
          <option value="Зарплата">Зарплата</option>
        </select>
        <select
          className="border p-2"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Все статусы</option>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          className="border p-2"
          value={filters.method}
          onChange={(e) => setFilters({ ...filters, method: e.target.value })}
        >
          <option value="">Все способы</option>
          <option value="💳 На карту">На карту</option>
          <option value="🏦 Из кассы">Из кассы</option>
          <option value="🤝 Наличными">Наличными</option>
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
        <button className="btn bg-gray-300 text-gray-700 hover:bg-gray-400" onClick={resetFilters}>
          Сбросить
        </button>
        <button className="btn ml-auto" onClick={openCreate}>
          ➕ Новая
        </button>
      </div>

      <div className="overflow-auto border rounded shadow">
        <table className="min-w-full divide-y divide-gray-200 bg-white text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left">ФИО</th>
              <th className="px-4 py-2 text-left">Тип</th>
              <th className="px-4 py-2 text-left">Способ</th>
              <th className="px-4 py-2 text-left">Сумма</th>
              <th className="px-4 py-2 text-left">Статус</th>
              <th className="px-4 py-2 text-left">Дата</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {payouts.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50">
                <td className="px-4 py-2">{p.name}</td>
                <td className="px-4 py-2">{p.payout_type}</td>
                <td className="px-4 py-2">{p.method}</td>
                <td className="px-4 py-2 text-blue-800 font-medium">
                  {p.amount} ₽
                </td>
                <td className="px-4 py-2">
                  <span
                    className={`px-2 py-1 rounded text-xs ${statusColor(p.status)}`}
                  >
                    {p.status}
                  </span>
                </td>
                <td className="px-4 py-2 text-xs">{formatDateTime(p.timestamp)}</td>
                <td className="px-4 py-2 space-x-1 whitespace-nowrap">
                  <button
                    onClick={() => openEdit(p)}
                    className="text-blue-600 hover:text-blue-800"
                    title="Редактировать"
                  >
                    <Pencil size={16} />
                  </button>
                  {p.status === 'Ожидает' && (
                    <button
                      onClick={() => updateStatus(p.id, 'Одобрено')}
                      className="text-green-600 hover:text-green-800"
                      title="Одобрить"
                    >
                      <CheckCircle size={16} />
                    </button>
                  )}
                  {p.status === 'Ожидает' && (
                    <button
                      onClick={() => updateStatus(p.id, 'Отклонено')}
                      className="text-red-600 hover:text-red-800"
                      title="Отказать"
                    >
                      <XCircle size={16} />
                    </button>
                  )}
                  {p.status === 'Одобрено' && (
                    <button
                      onClick={() => updateStatus(p.id, 'Выплачено')}
                      className="text-indigo-600 hover:text-indigo-800"
                      title="Отметить выплаченным"
                    >
                      <Download size={16} />
                    </button>
                  )}
                  <button
                    onClick={() => remove(p.id)}
                    className="text-gray-500 hover:text-gray-800"
                    title="Удалить"
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
            {payouts.length === 0 && (
              <tr>
                <td
                  colSpan="7"
                  className="px-4 py-3 text-center text-gray-500 italic"
                >
                  Нет данных
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex gap-3 items-center">
        <button onClick={exportPdf} className="btn bg-green-600 hover:bg-green-700 flex items-center gap-1">
          <Download size={16} /> PDF
        </button>
      </div>

      <Summary list={payouts} />

      {showEditor && (
        <div className="modal-backdrop">
          <div className="modal-card max-w-lg">
            <h2 className="text-xl font-semibold">
              {form.id ? 'Редактирование' : 'Новая выплата'}
            </h2>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={useFullName}
                onChange={(e) => setUseFullName(e.target.checked)}
              />
              Использовать ФИО
            </label>
            <select
              className="modal-control"
              value={form.user_id}
              onChange={(e) => handleSelect(e.target.value)}
            >
              <option value="">Сотрудник</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {useFullName ? e.full_name || e.name : e.name || e.full_name}
                </option>
              ))}
            </select>
            <input
              className="modal-control"
              placeholder="Сумма"
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.payout_type}
              onChange={(e) => setForm({ ...form, payout_type: e.target.value })}
            >
              <option value="Аванс">Аванс</option>
              <option value="Зарплата">Зарплата</option>
            </select>
            <select
              className="modal-control"
              value={form.method}
              onChange={(e) => setForm({ ...form, method: e.target.value })}
            >
              <option value="💳 На карту">На карту</option>
              <option value="🏦 Из кассы">Из кассы</option>
              <option value="🤝 Наличными">Наличными</option>
            </select>
            {form.id && (
              <select
                className="modal-control"
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
              >
                {STATUS_OPTIONS.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            )}
            {form.id && (
              <label className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={form.notify_user}
                  onChange={(e) => setForm({ ...form, notify_user: e.target.checked })
                  }
                />
                Уведомить сотрудника
              </label>
            )}
            <textarea
              className="modal-control"
              placeholder="Примечание"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
            />
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={form.show_note_in_bot}
                onChange={(e) => setForm({ ...form, show_note_in_bot: e.target.checked })
                }
              />
              Показывать примечание в боте
            </label>
            <label className="flex items-center gap-1 text-sm">
              <input
                type="checkbox"
                checked={form.sync_to_bot}
                onChange={(e) => setForm({ ...form, sync_to_bot: e.target.checked })
                }
              />
              Отразить в боте
            </label>
            <div className="flex justify-end space-x-2 pt-2">
              <button
                className="btn bg-gray-200 text-gray-700 hover:bg-gray-300"
                onClick={() => {
                  setShowEditor(false);
                  setForm(emptyForm);
                }}
              >
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






