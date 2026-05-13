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
import { useAuth } from '../providers/AuthProvider.jsx';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';

const MAX_AMOUNT = 100000;
const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];
const MANAGE_DATES_PERMISSION = 'payouts-manage-dates';

const pad = (value) => String(value).padStart(2, '0');

function toInputTimestamp(value) {
  if (!value) return '';
  const source = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(source.getTime())) {
    if (typeof value === 'string') {
      const fallback = new Date(value.replace(' ', 'T'));
      if (!Number.isNaN(fallback.getTime())) {
        return toInputTimestamp(fallback);
      }
    }
    return '';
  }
  return (
    `${source.getFullYear()}-${pad(source.getMonth() + 1)}-${pad(source.getDate())}` +
    `T${pad(source.getHours())}:${pad(source.getMinutes())}:${pad(source.getSeconds())}`
  );
}

function toPayloadTimestamp(value) {
  if (!value) return undefined;
  if (!value.includes('T')) {
    return value;
  }
  const [datePart, timePart] = value.split('T');
  const [hours = '00', minutes = '00', seconds = '00'] = timePart.split(':');
  return `${datePart} ${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
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
  const { user } = useAuth();
  const { toast } = useToast();
  const { isMobile } = useViewport();
  const canManageDates = Boolean(
    user?.permissions?.includes('*') || user?.permissions?.includes(MANAGE_DATES_PERMISSION),
  );
  const emptyForm = {
    id: null,
    user_id: '',
    name: '',
    phone: '',
    card_number: '',
    bank: '',
    amount: '',
    payout_type: 'Аванс',
    method: '💳 На карту',
    status: 'Ожидает',
    sync_to_bot: false,
    notify_user: true,
    note: '',
    show_note_in_bot: false,
    timestamp: '',
    force_notify_cashier: false,
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
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    load();
    loadEmployees();
    window.refreshPage = load;
  }, []);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    setLoading(true);
    setSelected(new Set());
    try {
      const params = {
        payout_type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        from_date: filters.from || undefined,
        to_date: filters.to || undefined,
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
      toast('Ошибка загрузки выплат', 'error');
    } finally {
      setLoading(false);
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
      toast('Статус обновлён', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка обновления статуса', 'error');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить выплату?')) return;
    try {
      await api.delete(`payouts/${id}`);
      toast('Выплата удалена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка удаления', 'error');
    }
  }

  function toggleSelect(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === payouts.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(payouts.map((p) => p.id)));
    }
  }

  async function bulkDelete() {
    if (selected.size === 0) return;
    if (!window.confirm(`Удалить ${selected.size} выплат?`)) return;
    let deleted = 0;
    let failed = 0;
    for (const id of selected) {
      try {
        await api.delete(`payouts/${id}`);
        deleted++;
      } catch (err) {
        console.error(err);
        failed++;
      }
    }
    setSelected(new Set());
    if (failed > 0) {
      toast(`Удалено: ${deleted}, ошибок: ${failed}`, 'warning');
    } else {
      toast(`Удалено: ${deleted}`, 'success');
    }
    load();
  }

  async function bulkSetStatus(status) {
    if (selected.size === 0 || !status) return;
    try {
      const res = await api.post('payouts/bulk-status', { ids: [...selected], status });
      toast(`Статус «${status}» установлен: ${res.data.updated} выплат`, 'success');
      setSelected(new Set());
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка массового изменения статуса', 'error');
    }
  }

  function openCreate() {
    setForm({
      ...emptyForm,
      timestamp: canManageDates ? toInputTimestamp(new Date()) : '',
    });
    setShowEditor(true);
  }

  function openEdit(p) {
    setForm({
      ...emptyForm,
      ...p,
      timestamp: canManageDates ? toInputTimestamp(p.timestamp) : '',
      notify_user: true,
      note: p.note || '',
      show_note_in_bot: p.show_note_in_bot || false,
      force_notify_cashier: Boolean(p.force_notify_cashier),
    });
    setShowEditor(true);
  }

  async function saveForm() {
    const amount = Number(form.amount || 0);
    if (!form.user_id || !amount || amount > MAX_AMOUNT) {
      toast('Неверные данные', 'warning');
      return;
    }
    const payload = { ...form, amount };
    if (canManageDates && form.timestamp) {
      payload.timestamp = toPayloadTimestamp(form.timestamp);
    } else {
      delete payload.timestamp;
    }
    try {
      if (form.id) {
        await api.put(`payouts/${form.id}`, payload);
      } else {
        await api.post('payouts/', payload);
      }
      setShowEditor(false);
      setForm(emptyForm);
      toast('Выплата сохранена', 'success');
      load();
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения', 'error');
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
        card_number: emp.card_number || '',
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
      toast('Заявки обновлены', 'success');
    } catch (err) {
      console.error(err);
      toast('Ошибка обновления', 'error');
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
          className="border p-2 flex-grow rounded"
          placeholder="Поиск по ФИО"
          value={filters.query}
          onChange={(e) => setFilters({ ...filters, query: e.target.value })}
        />
        <select
          className="border p-2 rounded"
          value={filters.type}
          onChange={(e) => setFilters({ ...filters, type: e.target.value })}
        >
          <option value="">Все типы</option>
          <option value="Аванс">Аванс</option>
          <option value="Зарплата">Зарплата</option>
        </select>
        <select
          className="border p-2 rounded"
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
          className="border p-2 rounded"
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
          className="border p-2 rounded"
          value={filters.from}
          onChange={(e) => setFilters({ ...filters, from: e.target.value })}
        />
        <input
          type="date"
          className="border p-2 rounded"
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

      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 bg-blue-50 p-3 rounded border border-blue-200">
          <span className="text-sm text-blue-800 font-medium">
            Выбрано: <strong>{selected.size}</strong>
          </span>
          <div className="flex items-center gap-2">
            <select
              className="border border-blue-300 rounded px-2 py-1 text-sm bg-white"
              defaultValue=""
              onChange={(e) => { if (e.target.value) { bulkSetStatus(e.target.value); e.target.value = ''; } }}
            >
              <option value="" disabled>Установить статус…</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <button
            className="btn bg-red-600 hover:bg-red-700 text-white text-sm px-3 py-1"
            onClick={bulkDelete}
          >
            <Trash2 size={14} className="inline mr-1" />
            Удалить
          </button>
          <button
            className="text-sm text-gray-500 hover:text-gray-800 underline"
            onClick={() => setSelected(new Set())}
          >
            Снять выделение
          </button>
        </div>
      )}

      {loading ? (
        <div className="border rounded shadow bg-white p-4">
          <SkeletonTable rows={8} cols={7} />
        </div>
      ) : isMobile ? (
        <div className="space-y-3">
          {payouts.length === 0 && (
            <div className="py-6 text-center text-gray-500 text-sm italic">Нет данных</div>
          )}
          {payouts.map((p) => (
            <div key={p.id} className={`border rounded-xl bg-white shadow-sm overflow-hidden ${selected.has(p.id) ? 'ring-2 ring-blue-400' : ''}`}>
              <div className="px-4 py-3 border-b bg-gray-50 flex items-center justify-between">
                <label className="flex items-center gap-2 font-medium text-sm cursor-pointer">
                  <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSelect(p.id)} />
                  {p.name}
                </label>
                <span className={`px-2 py-0.5 rounded text-xs ${statusColor(p.status)}`}>{p.status}</span>
              </div>
              <div className="px-4 py-2 space-y-1.5 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Сумма</span>
                  <span className="font-semibold text-blue-800">{p.amount} ₽</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Тип / Способ</span>
                  <span>{p.payout_type} · {p.method}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Дата</span>
                  <span className="text-xs">{formatDateTime(p.timestamp)}</span>
                </div>
              </div>
              <div className="px-4 py-2 border-t flex justify-end gap-3">
                <button onClick={() => openEdit(p)} className="text-blue-600" title="Редактировать"><Pencil size={18} /></button>
                {p.status === 'Ожидает' && (
                  <button onClick={() => updateStatus(p.id, 'Одобрено')} className="text-green-600" title="Одобрить"><CheckCircle size={18} /></button>
                )}
                {p.status === 'Ожидает' && (
                  <button onClick={() => updateStatus(p.id, 'Отклонено')} className="text-red-600" title="Отказать"><XCircle size={18} /></button>
                )}
                {p.status === 'Одобрено' && (
                  <button onClick={() => updateStatus(p.id, 'Выплачено')} className="text-indigo-600" title="Отметить выплаченным"><Download size={18} /></button>
                )}
                <button onClick={() => remove(p.id)} className="text-gray-500" title="Удалить"><Trash2 size={18} /></button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-auto border rounded shadow">
          <table className="min-w-[1100px] divide-y divide-gray-200 bg-white text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-2 py-2 w-8">
                  <input
                    type="checkbox"
                    checked={payouts.length > 0 && selected.size === payouts.length}
                    onChange={toggleSelectAll}
                  />
                </th>
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
                <tr key={p.id} className={`hover:bg-gray-50 ${selected.has(p.id) ? 'bg-blue-50' : ''}`}>
                  <td className="px-2 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={() => toggleSelect(p.id)}
                    />
                  </td>
                  <td className="px-4 py-2">{p.name}</td>
                  <td className="px-4 py-2">{p.payout_type}</td>
                  <td className="px-4 py-2">{p.method}</td>
                  <td className="px-4 py-2 text-blue-800 font-medium">{p.amount} ₽</td>
                  <td className="px-4 py-2">
                    <span className={`px-2 py-1 rounded text-xs ${statusColor(p.status)}`}>{p.status}</span>
                  </td>
                  <td className="px-4 py-2 text-xs">{formatDateTime(p.timestamp)}</td>
                  <td className="px-4 py-2 space-x-1 whitespace-nowrap">
                    <button onClick={() => openEdit(p)} className="text-blue-600 hover:text-blue-800" title="Редактировать"><Pencil size={16} /></button>
                    {p.status === 'Ожидает' && (
                      <button onClick={() => updateStatus(p.id, 'Одобрено')} className="text-green-600 hover:text-green-800" title="Одобрить"><CheckCircle size={16} /></button>
                    )}
                    {p.status === 'Ожидает' && (
                      <button onClick={() => updateStatus(p.id, 'Отклонено')} className="text-red-600 hover:text-red-800" title="Отказать"><XCircle size={16} /></button>
                    )}
                    {p.status === 'Одобрено' && (
                      <button onClick={() => updateStatus(p.id, 'Выплачено')} className="text-indigo-600 hover:text-indigo-800" title="Отметить выплаченным"><Download size={16} /></button>
                    )}
                    <button onClick={() => remove(p.id)} className="text-gray-500 hover:text-gray-800" title="Удалить"><Trash2 size={16} /></button>
                  </td>
                </tr>
              ))}
              {payouts.length === 0 && (
                <tr>
                  <td colSpan="8" className="px-4 py-3 text-center text-gray-500 italic">Нет данных</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

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
            <div className="text-sm text-gray-600">
              Карта: <span className="font-medium">{form.card_number || '—'}</span>
            </div>
            <div className="text-sm text-gray-600">
              Банк: <span className="font-medium">{form.bank || '—'}</span>
            </div>
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
            {canManageDates && (
              <div className="w-full">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Дата выплаты
                </label>
                <input
                  type="datetime-local"
                  step="1"
                  className="modal-control"
                  value={form.timestamp}
                  onChange={(e) => setForm({ ...form, timestamp: e.target.value })}
                />
              </div>
            )}
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
                checked={form.force_notify_cashier}
                onChange={(e) =>
                  setForm({ ...form, force_notify_cashier: e.target.checked })
                }
              />
              Всегда уведомлять кассира
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
