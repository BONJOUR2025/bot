import { useEffect, useState } from 'react';
import {
  CheckCircle,
  Download,
  Pencil,
  RefreshCw,
  Trash2,
  XCircle,
  LinkIcon,
  Unlink,
  Search,
  X,
  ExternalLink,
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

// ── Movement quick-view modal (from table link icon) ─────────────
function MovementQuickViewModal({ payout, onUnlink, onChangeMove, onClose }) {
  const { toast } = useToast();
  const [moveDetails, setMoveDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(true);
  const [unlinking, setUnlinking] = useState(false);

  useEffect(() => {
    if (!payout.cash_move_id) { setLoadingDetails(false); return; }
    api.get(`cash-moves/by-id/${payout.cash_move_id}`)
      .then((r) => setMoveDetails(r.data))
      .catch(() => setMoveDetails(null))
      .finally(() => setLoadingDetails(false));
  }, [payout.cash_move_id]);

  async function handleUnlink() {
    setUnlinking(true);
    try {
      await onUnlink();
      onClose();
    } catch { toast('Ошибка отвязки', 'error'); }
    finally { setUnlinking(false); }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-card max-w-sm w-full">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} className="text-green-500" /> Кассовое движение
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100"><X size={18} /></button>
        </div>
        {loadingDetails ? (
          <div className="flex items-center justify-center gap-2 py-4 text-gray-400 text-sm">
            <RefreshCw size={14} className="animate-spin" /> Загрузка…
          </div>
        ) : moveDetails ? (
          <div className="text-sm space-y-2">
            <div className="flex justify-between">
              <span className="text-gray-500">Дата</span>
              <span>{moveDetails.DK_DATE || '—'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Сумма</span>
              <span className="font-semibold text-blue-700">
                {Number(moveDetails.SUMM).toLocaleString('ru-RU')} ₽
              </span>
            </div>
            {moveDetails.dep_name && (
              <div className="flex justify-between">
                <span className="text-gray-500">Филиал</span>
                <span>{moveDetails.dep_name}</span>
              </div>
            )}
            {moveDetails.BASIS && (
              <div className="flex justify-between gap-4">
                <span className="text-gray-500 shrink-0">Основание</span>
                <span className="font-mono text-xs text-right truncate min-w-0">{moveDetails.BASIS}</span>
              </div>
            )}
          </div>
        ) : (
          <div className="text-sm text-gray-400">ID: {payout.cash_move_id}</div>
        )}
        <div className="flex justify-between mt-5">
          <button
            className="btn text-sm border border-red-200 text-red-500 hover:border-red-400 hover:text-red-700 disabled:opacity-50"
            onClick={handleUnlink}
            disabled={unlinking}
          >
            {unlinking
              ? <RefreshCw size={12} className="inline animate-spin mr-1" />
              : <Unlink size={13} className="inline mr-1" />}
            Отвязать
          </button>
          <div className="flex gap-2">
            <button className="btn text-sm" onClick={() => { onClose(); onChangeMove(); }}>Изменить</button>
            <button className="btn" onClick={onClose}>Закрыть</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Movement picker modal ─────────────────────────────────────────
function MovementPickerModal({ payout, onLink, onClose }) {
  const { toast } = useToast();
  const defaultFrom = () => {
    if (!payout?.timestamp) return '';
    const d = new Date(payout.timestamp.replace(' ', 'T'));
    if (isNaN(d)) return '';
    d.setDate(d.getDate() - 7);
    return d.toISOString().slice(0, 10);
  };
  const defaultTo = () => {
    if (!payout?.timestamp) return '';
    const d = new Date(payout.timestamp.replace(' ', 'T'));
    if (isNaN(d)) return '';
    d.setDate(d.getDate() + 7);
    return d.toISOString().slice(0, 10);
  };
  const [dateFrom, setDateFrom] = useState(defaultFrom);
  const [dateTo, setDateTo]     = useState(defaultTo);
  const [moves, setMoves]       = useState([]);
  const [loading, setLoading]   = useState(false);
  const [linking, setLinking]   = useState(null);

  async function loadMoves() {
    setLoading(true);
    try {
      const params = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo)   params.date_to   = dateTo;
      const res = await api.get('cash-moves/', { params });
      setMoves(Array.isArray(res.data) ? res.data : []);
    } catch { toast('Ошибка загрузки движений', 'error'); }
    finally { setLoading(false); }
  }

  useEffect(() => { loadMoves(); }, []);

  async function handleLink(moveId) {
    setLinking(moveId);
    try {
      await onLink(moveId);
      onClose();
    } catch { toast('Ошибка привязки', 'error'); }
    finally { setLinking(null); }
  }

  return (
    <div className="modal-backdrop" style={{ zIndex: 60 }}>
      <div className="modal-card max-w-2xl w-full max-h-[85vh] flex flex-col">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} /> Выбрать кассовое движение
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100"><X size={18} /></button>
        </div>

        <div className="flex gap-2 mb-3">
          <input type="date" className="input flex-1" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          <input type="date" className="input flex-1" value={dateTo}   onChange={(e) => setDateTo(e.target.value)} />
          <button className="btn btn--primary" onClick={loadMoves} disabled={loading}>
            {loading ? <RefreshCw size={14} className="animate-spin" /> : 'Найти'}
          </button>
        </div>

        {loading ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">Загрузка…</div>
        ) : moves.length === 0 ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 text-sm">Нет движений за период</div>
        ) : (
          <div className="overflow-auto flex-1">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-gray-50 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-3 py-2 text-left">Дата</th>
                  <th className="px-3 py-2 text-left">Филиал</th>
                  <th className="px-3 py-2 text-left">Основание</th>
                  <th className="px-3 py-2 text-right">Сумма</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {moves.map((m) => (
                  <tr key={m.ID_KASSES_MOVE} className={`hover:bg-gray-50 ${m.has_payout ? 'opacity-50' : ''}`}>
                    <td className="px-3 py-2 whitespace-nowrap">{m.DK_DATE}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{m.dep_name || '—'}</td>
                    <td className="px-3 py-2 font-mono text-xs max-w-xs truncate" title={m.BASIS}>{m.BASIS || '—'}</td>
                    <td className="px-3 py-2 text-right font-medium whitespace-nowrap">
                      {Number(m.SUMM).toLocaleString('ru-RU')} ₽
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        className="btn btn--primary text-xs px-2 py-1 disabled:opacity-50"
                        disabled={linking === m.ID_KASSES_MOVE}
                        onClick={() => handleLink(String(m.ID_KASSES_MOVE))}
                      >
                        {linking === m.ID_KASSES_MOVE
                          ? <RefreshCw size={12} className="animate-spin" />
                          : 'Привязать'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
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
  const [moveMatches, setMoveMatches] = useState({});
  const [moveMatchesLoading, setMoveMatchesLoading] = useState(false);
  const [findingMoves, setFindingMoves] = useState(new Set());
  const [bulkFinding, setBulkFinding] = useState(false);
  const [editingMoveDetails, setEditingMoveDetails] = useState(null);
  const [loadingMoveDetails, setLoadingMoveDetails] = useState(false);
  const [moveLinkPickerPayout, setMoveLinkPickerPayout] = useState(null);
  const [quickViewPayout, setQuickViewPayout] = useState(null);
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
      if (params.from_date || params.to_date) {
        loadMoveMatches(params.from_date, params.to_date);
      } else {
        // Build matches from cash_move_id stored on each payout (no Firebird query needed)
        const map = {};
        for (const p of list) {
          if (p.cash_move_id) {
            map[p.id] = { payout_id: p.id, matched: true, move_id: p.cash_move_id };
          }
        }
        setMoveMatches(map);
      }
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки выплат', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function loadMoveMatches(fromDate, toDate) {
    setMoveMatchesLoading(true);
    try {
      const params = {};
      if (fromDate) params.date_from = fromDate;
      if (toDate)   params.date_to   = toDate;
      const res = await api.get('cash-moves/match-payouts', { params });
      const map = {};
      for (const item of res.data || []) map[item.payout_id] = item;
      setMoveMatches(map);
    } catch {
      // Firebird may be unavailable — silently ignore
    } finally {
      setMoveMatchesLoading(false);
    }
  }

  async function findMoveForPayout(payoutId) {
    setFindingMoves((prev) => new Set([...prev, payoutId]));
    try {
      const res = await api.post(`payouts/${payoutId}/find-move`);
      setMoveMatches((prev) => ({ ...prev, [payoutId]: res.data }));
      if (res.data.matched) {
        setPayouts((prev) => prev.map((p) =>
          p.id === payoutId ? { ...p, cash_move_id: res.data.move_id } : p
        ));
        toast('Движение найдено и привязано', 'success');
      } else {
        toast('Совпадение не найдено', 'warning');
      }
    } catch {
      toast('Ошибка поиска движения', 'error');
    } finally {
      setFindingMoves((prev) => { const s = new Set(prev); s.delete(payoutId); return s; });
    }
  }

  async function bulkFindMoves() {
    if (selected.size === 0) return;
    setBulkFinding(true);
    try {
      const res = await api.post('payouts/bulk-find-moves', { ids: [...selected] });
      const updated = {};
      for (const item of res.data || []) updated[item.payout_id] = item;
      setMoveMatches((prev) => ({ ...prev, ...updated }));
      const found = (res.data || []).filter((r) => r.matched).length;
      toast(`Найдено движений: ${found} из ${selected.size}`, found > 0 ? 'success' : 'warning');
    } catch {
      toast('Ошибка поиска движений', 'error');
    } finally {
      setBulkFinding(false);
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
    setEditingMoveDetails(null);
    setMoveLinkPickerPayout(null);
    setShowEditor(true);
    if (p.cash_move_id) fetchMoveDetails(p.cash_move_id);
  }

  async function fetchMoveDetails(moveId) {
    setLoadingMoveDetails(true);
    try {
      const res = await api.get(`cash-moves/by-id/${moveId}`);
      setEditingMoveDetails(res.data);
    } catch {
      setEditingMoveDetails(null);
    } finally {
      setLoadingMoveDetails(false);
    }
  }

  async function unlinkMove(payoutId) {
    const res = await api.delete(`payouts/${payoutId}/move-link`);
    setPayouts((prev) => prev.map((p) => (p.id === payoutId ? res.data : p)));
    setForm((prev) => ({ ...prev, cash_move_id: null }));
    setEditingMoveDetails(null);
    setQuickViewPayout(null);
    setMoveMatches((prev) => ({ ...prev, [payoutId]: { payout_id: payoutId, matched: false, move_id: null } }));
    toast('Движение отвязано', 'success');
  }

  async function linkMove(payoutId, moveId) {
    try {
      const res = await api.post(`payouts/${payoutId}/link-move`, { move_id: moveId });
      setPayouts((prev) => prev.map((p) => (p.id === payoutId ? res.data : p)));
      setForm((prev) => ({ ...prev, cash_move_id: moveId }));
      setMoveMatches((prev) => ({ ...prev, [payoutId]: { payout_id: payoutId, matched: true, move_id: moveId } }));
      toast('Движение привязано', 'success');
      fetchMoveDetails(moveId);
    } catch {
      toast('Ошибка привязки', 'error');
    }
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
            className="btn text-sm px-3 py-1 flex items-center gap-1.5 disabled:opacity-50"
            onClick={bulkFindMoves}
            disabled={bulkFinding}
            title="Найти кассовые движения для выбранных выплат"
          >
            {bulkFinding
              ? <RefreshCw size={14} className="animate-spin" />
              : <Search size={14} />}
            Найти движения
          </button>
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
                <th className="px-2 py-2 w-8" title="Связь с кассовым движением"></th>
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
                  <td className="px-2 py-2 text-center">
                    {findingMoves.has(p.id) || (moveMatchesLoading && moveMatches[p.id] == null)
                      ? <RefreshCw size={13} className="mx-auto animate-spin text-gray-400" />
                      : moveMatches[p.id]?.matched
                        ? <button
                            onClick={() => setQuickViewPayout(p)}
                            title={`Движение привязано: ${moveMatches[p.id].move_id} — нажмите для просмотра`}
                            className="p-0.5 rounded hover:bg-green-100 transition-colors"
                          >
                            <LinkIcon size={14} className="mx-auto text-green-500" />
                          </button>
                        : moveMatches[p.id] != null
                          ? <button onClick={() => findMoveForPayout(p.id)} title="Кассовое движение не найдено — нажмите для повторного поиска">
                              <Unlink size={14} className="text-amber-400 hover:text-amber-600" />
                            </button>
                          : <button onClick={() => findMoveForPayout(p.id)} title="Найти кассовое движение">
                              <Search size={13} className="text-gray-300 hover:text-gray-500" />
                            </button>
                    }
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
                  <td colSpan="9" className="px-4 py-3 text-center text-gray-500 italic">Нет данных</td>
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
            {/* Linked movement block (edit mode only) */}
            {form.id && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium flex items-center gap-1.5">
                    <LinkIcon size={13} className={form.cash_move_id ? 'text-green-500' : 'text-gray-400'} />
                    Кассовое движение
                  </span>
                  <div className="flex items-center gap-2">
                    {form.cash_move_id && (
                      <button
                        className="text-xs text-red-500 hover:text-red-700 underline"
                        onClick={async () => {
                          try { await unlinkMove(form.id); }
                          catch { toast('Ошибка отвязки', 'error'); }
                        }}
                      >
                        Отвязать
                      </button>
                    )}
                    <button
                      className="text-xs text-blue-500 hover:text-blue-700 underline"
                      onClick={() => setMoveLinkPickerPayout({ id: form.id, timestamp: form.timestamp })}
                    >
                      {form.cash_move_id ? 'Изменить' : 'Привязать'}
                    </button>
                  </div>
                </div>
                {form.cash_move_id ? (
                  loadingMoveDetails ? (
                    <div className="text-xs text-gray-400 flex items-center gap-1">
                      <RefreshCw size={11} className="animate-spin" /> Загрузка…
                    </div>
                  ) : editingMoveDetails ? (
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Дата</span>
                        <span>{editingMoveDetails.DK_DATE || '—'}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Сумма</span>
                        <span className="font-semibold text-blue-700">
                          {Number(editingMoveDetails.SUMM).toLocaleString('ru-RU')} ₽
                        </span>
                      </div>
                      {editingMoveDetails.dep_name && (
                        <div className="flex justify-between">
                          <span className="text-gray-500">Филиал</span>
                          <span>{editingMoveDetails.dep_name}</span>
                        </div>
                      )}
                      {editingMoveDetails.BASIS && (
                        <div className="flex justify-between gap-4">
                          <span className="text-gray-500 shrink-0">Основание</span>
                          <span className="font-mono text-xs text-right truncate">{editingMoveDetails.BASIS}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="text-xs text-gray-400">ID: {form.cash_move_id}</div>
                  )
                ) : (
                  <div className="text-xs text-gray-400 italic">Движение не привязано</div>
                )}
              </div>
            )}

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

      {moveLinkPickerPayout && (
        <MovementPickerModal
          payout={moveLinkPickerPayout}
          onLink={(moveId) => linkMove(moveLinkPickerPayout.id, moveId)}
          onClose={() => setMoveLinkPickerPayout(null)}
        />
      )}

      {quickViewPayout && (
        <MovementQuickViewModal
          payout={quickViewPayout}
          onUnlink={() => unlinkMove(quickViewPayout.id)}
          onChangeMove={() => setMoveLinkPickerPayout({ id: quickViewPayout.id, timestamp: quickViewPayout.timestamp })}
          onClose={() => setQuickViewPayout(null)}
        />
      )}
    </div>
  );
}
