import { useState, useEffect, useMemo, useRef } from 'react';
import { Pencil, Trash2, Plus, Bell, Search, X } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString('ru');
}

const emptyForm = {
  id: null,
  employee_id: '',
  employee_name: '',
  position: '',
  item_name: '',
  size: '',
  quantity: 1,
  issue_date: '',
  return_date: '',
  service_life: '',
};

export default function Assets() {
  const { toast } = useToast();
  const [list, setList]               = useState([]);
  const [employees, setEmployees]     = useState([]);
  const [itemOptions, setItemOptions] = useState([]);
  const [posOptions, setPosOptions]   = useState([]);
  const [sizeOptions, setSizeOptions] = useState([]);
  const [filters, setFilters]         = useState({ search: '', employee: '', dateFrom: '', dateTo: '' });
  const [form, setForm]               = useState({ ...emptyForm, issue_date: new Date().toISOString().slice(0, 10) });
  const [showForm, setShowForm]       = useState(false);
  const [selected, setSelected]       = useState(new Set());
  const [notifying, setNotifying]     = useState(new Set());
  const allCheckRef                   = useRef(null);

  useEffect(() => {
    loadEmployees();
    load();
    loadDictionary();
  }, []);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch {
      toast('Ошибка загрузки сотрудников', 'error');
    }
  }

  async function load() {
    try {
      const res = await api.get('assets/');
      setList(res.data);
      setItemOptions(prev =>
        Array.from(new Set([...prev, ...res.data.map(i => i.item_name).filter(Boolean)]))
      );
      setSizeOptions(prev =>
        Array.from(new Set([...prev, ...res.data.map(i => i.size).filter(Boolean)]))
      );
    } catch {
      toast('Ошибка загрузки имущества', 'error');
    }
  }

  async function loadDictionary() {
    try {
      const res = await api.get('dictionary/');
      setPosOptions(res.data.positions || []);
      setItemOptions(prev => Array.from(new Set([...prev, ...(res.data.asset_items || [])])));
      setSizeOptions(prev => Array.from(new Set([...prev, ...(res.data.asset_sizes || [])])));
    } catch {}
  }

  // --- Client-side filtering (reactive, no "Применить") ---
  const filtered = useMemo(() => list.filter(item => {
    if (filters.employee && String(item.employee_id) !== String(filters.employee)) return false;
    if (filters.search) {
      const q = filters.search.toLowerCase();
      if (!item.employee_name?.toLowerCase().includes(q) && !item.item_name?.toLowerCase().includes(q)) return false;
    }
    if (filters.dateFrom && (item.issue_date || '') < filters.dateFrom) return false;
    if (filters.dateTo  && (item.issue_date || '') > filters.dateTo)   return false;
    return true;
  }), [list, filters]);

  // Sync indeterminate state
  useEffect(() => {
    if (allCheckRef.current) {
      allCheckRef.current.indeterminate = selected.size > 0 && selected.size < filtered.length;
    }
  }, [selected, filtered]);

  // --- CRUD ---
  function startCreate() {
    setForm({ ...emptyForm, issue_date: new Date().toISOString().slice(0, 10) });
    setShowForm(true);
  }

  function startEdit(item) {
    setForm({
      ...item,
      service_life: item.service_life ?? '',
      return_date:  item.return_date  ?? '',
    });
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.employee_id || !form.item_name) {
      toast('Укажите сотрудника и наименование предмета', 'error');
      return;
    }
    try {
      const payload = {
        ...form,
        service_life: form.service_life !== '' ? Number(form.service_life) : null,
        return_date:  form.return_date  || null,
      };
      if (form.id) {
        await api.put(`assets/${form.id}`, payload);
        toast('Запись обновлена', 'success');
      } else {
        await api.post('assets/', payload);
        toast('Запись добавлена', 'success');
      }
      setShowForm(false);
      load();
    } catch {
      toast('Ошибка сохранения', 'error');
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`assets/${id}`);
      toast('Запись удалена', 'success');
      setSelected(prev => { const n = new Set(prev); n.delete(id); return n; });
      load();
    } catch {
      toast('Ошибка удаления', 'error');
    }
  }

  // --- Notifications ---
  async function notifyOne(id) {
    setNotifying(prev => new Set([...prev, id]));
    try {
      await api.post(`assets/${id}/notify`);
      toast('Уведомление отправлено', 'success');
      load();
    } catch (e) {
      const detail = e.response?.data?.detail;
      toast(detail === 'no_telegram' ? 'У сотрудника нет Telegram' : 'Ошибка отправки', 'error');
    } finally {
      setNotifying(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  }

  // --- Bulk ---
  async function bulkDelete() {
    if (!selected.size) return;
    if (!window.confirm(`Удалить ${selected.size} запис${selected.size === 1 ? 'ь' : 'и'}?`)) return;
    try {
      await api.post('assets/bulk/delete', { ids: [...selected] });
      toast(`Удалено: ${selected.size}`, 'success');
      setSelected(new Set());
      load();
    } catch {
      toast('Ошибка удаления', 'error');
    }
  }

  async function bulkNotify() {
    if (!selected.size) return;
    try {
      const res = await api.post('assets/bulk/notify', { ids: [...selected] });
      toast(`Отправлено: ${res.data.sent}, ошибок: ${res.data.failed}`, res.data.sent > 0 ? 'success' : 'error');
      load();
    } catch {
      toast('Ошибка рассылки', 'error');
    }
  }

  // --- Checkboxes ---
  function toggleRow(id) {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }

  function toggleAll() {
    setSelected(prev =>
      prev.size === filtered.length && filtered.length > 0
        ? new Set()
        : new Set(filtered.map(i => i.id))
    );
  }

  // --- Employee autofill ---
  function handleSelectEmployee(id) {
    const emp = employees.find(e => String(e.id) === String(id));
    if (emp) {
      setForm(f => ({
        ...f,
        employee_id:   emp.id,
        employee_name: emp.full_name || emp.name,
        position:      emp.position      || '',
        size:          emp.clothing_size || '',
      }));
    } else {
      setForm(f => ({ ...f, employee_id: id, employee_name: '' }));
    }
  }

  // --- Stats ---
  const stats = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return {
      total:     filtered.length,
      employees: new Set(filtered.map(i => i.employee_id)).size,
      overdue:   filtered.filter(i => i.return_date && i.return_date < today && !i.acked_at).length,
    };
  }, [filtered]);

  const hasFilters = filters.search || filters.employee || filters.dateFrom || filters.dateTo;

  return (
    <div className="space-y-4 max-w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h2 className="text-2xl font-semibold">Имущество сотрудников</h2>
        <button className="btn btn-primary flex items-center gap-2 sm:ml-auto w-fit" onClick={startCreate}>
          <Plus size={16} /> Добавить
        </button>
      </div>

      {/* Filters */}
      <div className="card p-3 flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] pointer-events-none" />
          <input
            className="input pl-8 w-52"
            placeholder="ФИО / предмет"
            value={filters.search}
            onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
          />
        </div>
        <select className="input" value={filters.employee} onChange={e => setFilters(f => ({ ...f, employee: e.target.value }))}>
          <option value="">Все сотрудники</option>
          {employees.map(e => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
        </select>
        <input
          type="date" className="input" title="Выдано с"
          value={filters.dateFrom}
          onChange={e => setFilters(f => ({ ...f, dateFrom: e.target.value }))}
        />
        <span className="text-[color:var(--color-muted-foreground)] text-sm">—</span>
        <input
          type="date" className="input" title="Выдано по"
          value={filters.dateTo}
          onChange={e => setFilters(f => ({ ...f, dateTo: e.target.value }))}
        />
        {hasFilters && (
          <button className="btn btn-secondary flex items-center gap-1 text-sm"
            onClick={() => setFilters({ search: '', employee: '', dateFrom: '', dateTo: '' })}>
            <X size={13} /> Сбросить
          </button>
        )}
      </div>

      {/* Bulk toolbar */}
      {selected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-[color:var(--color-border)] px-4 py-2.5 bg-[color:var(--color-muted)]/30">
          <span className="text-sm font-medium">Выбрано: {selected.size}</span>
          <button className="btn btn-secondary text-sm flex items-center gap-1.5" onClick={bulkNotify}>
            <Bell size={14} /> Уведомить
          </button>
          <button
            className="btn text-sm flex items-center gap-1.5 bg-red-50 text-red-600 border-red-200 hover:bg-red-100"
            onClick={bulkDelete}>
            <Trash2 size={14} /> Удалить
          </button>
          <button className="btn btn-secondary text-sm ml-auto" onClick={() => setSelected(new Set())}>
            Снять выбор
          </button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 text-xs text-[color:var(--color-muted-foreground)]">
              <th className="w-9 px-3 py-2.5">
                <input type="checkbox" ref={allCheckRef}
                  checked={filtered.length > 0 && selected.size === filtered.length}
                  onChange={toggleAll} />
              </th>
              <th className="text-left px-3 py-2.5">ФИО</th>
              <th className="text-left px-3 py-2.5 hidden md:table-cell">Должность</th>
              <th className="text-left px-3 py-2.5">Предмет</th>
              <th className="text-left px-3 py-2.5 hidden sm:table-cell">Размер</th>
              <th className="text-center px-3 py-2.5 hidden sm:table-cell">Кол-во</th>
              <th className="text-left px-3 py-2.5">Выдано</th>
              <th className="text-left px-3 py-2.5 hidden lg:table-cell">Возврат</th>
              <th className="text-left px-3 py-2.5 hidden xl:table-cell">Подтверждено</th>
              <th className="w-24 px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--color-border)]">
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="px-4 py-10 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
                  Нет данных
                </td>
              </tr>
            )}
            {filtered.map(item => (
              <tr key={item.id}
                className={selected.has(item.id)
                  ? 'bg-[color:var(--color-primary)]/5'
                  : 'hover:bg-[color:var(--color-muted)]/10'}>
                <td className="px-3 py-2">
                  <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleRow(item.id)} />
                </td>
                <td className="px-3 py-2 font-medium">{item.employee_name}</td>
                <td className="px-3 py-2 hidden md:table-cell text-[color:var(--color-muted-foreground)] text-xs">{item.position || '—'}</td>
                <td className="px-3 py-2">{item.item_name}</td>
                <td className="px-3 py-2 hidden sm:table-cell">{item.size || '—'}</td>
                <td className="px-3 py-2 text-center hidden sm:table-cell">{item.quantity}</td>
                <td className="px-3 py-2 whitespace-nowrap">{fmtDate(item.issue_date)}</td>
                <td className="px-3 py-2 hidden lg:table-cell whitespace-nowrap">{fmtDate(item.return_date)}</td>
                <td className="px-3 py-2 hidden xl:table-cell">
                  {item.acked_at
                    ? <span className="text-green-600 text-xs font-medium">✅ {item.acked_at}</span>
                    : item.notified_at
                      ? <span className="text-[color:var(--color-muted-foreground)] text-xs">📤 {item.notified_at}</span>
                      : <span className="text-[color:var(--color-muted-foreground)]">—</span>}
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center justify-end gap-0.5">
                    <button
                      title="Отправить уведомление в бот"
                      disabled={notifying.has(item.id)}
                      onClick={() => notifyOne(item.id)}
                      className={`p-1.5 rounded transition-colors ${
                        notifying.has(item.id)
                          ? 'opacity-40 cursor-not-allowed'
                          : 'text-blue-500 hover:text-blue-700 hover:bg-blue-50'
                      }`}>
                      <Bell size={14} />
                    </button>
                    <button
                      title="Редактировать"
                      onClick={() => startEdit(item)}
                      className="p-1.5 rounded text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] hover:bg-[color:var(--color-muted)] transition-colors">
                      <Pencil size={14} />
                    </button>
                    <button
                      title="Удалить"
                      onClick={() => remove(item.id)}
                      className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors">
                      <Trash2 size={14} />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Stats */}
      <div className="flex flex-wrap gap-4 text-sm text-[color:var(--color-muted-foreground)] px-1">
        <span>Записей: <b className="text-[color:var(--color-foreground)]">{stats.total}</b></span>
        <span>Сотрудников: <b className="text-[color:var(--color-foreground)]">{stats.employees}</b></span>
        {stats.overdue > 0 && (
          <span className="text-amber-600 font-medium">⚠️ Просрочено: {stats.overdue}</span>
        )}
      </div>

      {/* Modal */}
      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-xl">
            <h2 className="text-xl font-semibold mb-4">{form.id ? 'Редактировать запись' : 'Новая запись'}</h2>
            <div className="space-y-3">

              <div>
                <label className="text-sm font-medium">Сотрудник *</label>
                <select className="input mt-1 w-full" value={form.employee_id}
                  onChange={e => handleSelectEmployee(e.target.value)}>
                  <option value="">Выберите сотрудника</option>
                  {employees.map(e => (
                    <option key={e.id} value={e.id}>{e.full_name || e.name}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium">Должность</label>
                <input className="input mt-1 w-full" list="asset-positions"
                  placeholder="Должность" value={form.position}
                  onChange={e => setForm(f => ({ ...f, position: e.target.value }))} />
                <datalist id="asset-positions">
                  {posOptions.map(o => <option key={o} value={o} />)}
                </datalist>
              </div>

              <div>
                <label className="text-sm font-medium">Предмет *</label>
                <input className="input mt-1 w-full" list="asset-items"
                  placeholder="Например: Рабочая форма" value={form.item_name}
                  onChange={e => setForm(f => ({ ...f, item_name: e.target.value }))} />
                <datalist id="asset-items">
                  {itemOptions.map(o => <option key={o} value={o} />)}
                </datalist>
              </div>

              <div>
                <label className="text-sm font-medium">Размер</label>
                <input className="input mt-1 w-full" list="asset-sizes"
                  placeholder="Например: M или 42" value={form.size}
                  onChange={e => setForm(f => ({ ...f, size: e.target.value }))} />
                <datalist id="asset-sizes">
                  {sizeOptions.map(o => <option key={o} value={o} />)}
                </datalist>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Количество</label>
                  <input type="number" min={1} className="input mt-1 w-full"
                    value={form.quantity}
                    onChange={e => setForm(f => ({ ...f, quantity: Number(e.target.value) }))} />
                </div>
                <div>
                  <label className="text-sm font-medium">Срок службы (мес.)</label>
                  <input type="number" min={0} className="input mt-1 w-full"
                    placeholder="—" value={form.service_life}
                    onChange={e => setForm(f => ({ ...f, service_life: e.target.value }))} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-sm font-medium">Дата выдачи</label>
                  <input type="date" className="input mt-1 w-full"
                    value={form.issue_date}
                    onChange={e => setForm(f => ({ ...f, issue_date: e.target.value }))} />
                </div>
                <div>
                  <label className="text-sm font-medium">Дата возврата</label>
                  <input type="date" className="input mt-1 w-full"
                    value={form.return_date}
                    onChange={e => setForm(f => ({ ...f, return_date: e.target.value }))} />
                </div>
              </div>

            </div>
            <div className="flex justify-end gap-2 pt-4">
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={saveForm}>Сохранить</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
