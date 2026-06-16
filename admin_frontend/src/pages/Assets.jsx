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

const today = () => new Date().toISOString().slice(0, 10);

const emptyItemRow = () => ({
  item_name:    '',
  size:         '',
  quantity:     1,
  service_life: '',
  issue_date:   today(),
  return_date:  '',
});

const emptyEmployee = { employee_id: '', employee_name: '', position: '' };

export default function Assets() {
  const { toast } = useToast();

  const [list, setList]               = useState([]);
  const [employees, setEmployees]     = useState([]);
  const [itemOptions, setItemOptions] = useState([]);
  const [posOptions, setPosOptions]   = useState([]);
  const [sizeOptions, setSizeOptions] = useState([]);
  const [filters, setFilters]         = useState({ search: '', employee: '', dateFrom: '', dateTo: '' });

  // Modal state
  const [showForm, setShowForm]   = useState(false);
  const [editId, setEditId]       = useState(null);        // null = create mode
  const [formEmp, setFormEmp]     = useState(emptyEmployee);
  const [formItems, setFormItems] = useState([emptyItemRow()]);

  // Bulk / notify
  const [selected, setSelected]   = useState(new Set());
  const [notifying, setNotifying] = useState(new Set());
  const allCheckRef               = useRef(null);

  useEffect(() => {
    loadEmployees();
    load();
    loadDictionary();
  }, []);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch { toast('Ошибка загрузки сотрудников', 'error'); }
  }

  async function load() {
    try {
      const res = await api.get('assets/');
      setList(res.data);
      setItemOptions(prev =>
        Array.from(new Set([...prev, ...res.data.map(i => i.item_name).filter(Boolean)])));
      setSizeOptions(prev =>
        Array.from(new Set([...prev, ...res.data.map(i => i.size).filter(Boolean)])));
    } catch { toast('Ошибка загрузки имущества', 'error'); }
  }

  async function loadDictionary() {
    try {
      const res = await api.get('dictionary/');
      setPosOptions(res.data.positions || []);
      setItemOptions(prev => Array.from(new Set([...prev, ...(res.data.asset_items || [])])));
      setSizeOptions(prev => Array.from(new Set([...prev, ...(res.data.asset_sizes || [])])));
    } catch {}
  }

  // Reactive client-side filtering
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

  useEffect(() => {
    if (allCheckRef.current)
      allCheckRef.current.indeterminate = selected.size > 0 && selected.size < filtered.length;
  }, [selected, filtered]);

  // ---- Modal helpers ----
  function openCreate() {
    setEditId(null);
    setFormEmp(emptyEmployee);
    setFormItems([emptyItemRow()]);
    setShowForm(true);
  }

  function openEdit(item) {
    setEditId(item.id);
    setFormEmp({
      employee_id:   item.employee_id,
      employee_name: item.employee_name,
      position:      item.position || '',
    });
    setFormItems([{
      item_name:    item.item_name,
      size:         item.size         || '',
      quantity:     item.quantity     ?? 1,
      service_life: item.service_life ?? '',
      issue_date:   item.issue_date   || today(),
      return_date:  item.return_date  || '',
    }]);
    setShowForm(true);
  }

  function pickEmployee(id) {
    const emp = employees.find(e => String(e.id) === String(id));
    if (emp) {
      setFormEmp({
        employee_id:   emp.id,
        employee_name: emp.full_name || emp.name,
        position:      emp.position  || '',
      });
      // Pre-fill size on all rows from employee profile
      if (emp.clothing_size) {
        setFormItems(rows => rows.map(r => r.size ? r : { ...r, size: emp.clothing_size }));
      }
    } else {
      setFormEmp(e => ({ ...e, employee_id: id, employee_name: '' }));
    }
  }

  function setItemField(idx, field, value) {
    setFormItems(rows => rows.map((r, i) => i === idx ? { ...r, [field]: value } : r));
  }

  function addItemRow() { setFormItems(rows => [...rows, emptyItemRow()]); }
  function removeItemRow(idx) {
    setFormItems(rows => rows.length > 1 ? rows.filter((_, i) => i !== idx) : rows);
  }

  async function saveForm() {
    if (!formEmp.employee_id) { toast('Выберите сотрудника', 'error'); return; }
    if (formItems.some(r => !r.item_name.trim())) { toast('Заполните название предмета', 'error'); return; }

    const toPayload = r => ({
      employee_id:   formEmp.employee_id,
      employee_name: formEmp.employee_name,
      position:      formEmp.position,
      item_name:     r.item_name.trim(),
      size:          r.size.trim(),
      quantity:      Number(r.quantity) || 1,
      service_life:  r.service_life !== '' ? Number(r.service_life) : null,
      issue_date:    r.issue_date || today(),
      return_date:   r.return_date || null,
    });

    try {
      if (editId !== null) {
        await api.put(`assets/${editId}`, toPayload(formItems[0]));
        toast('Запись обновлена', 'success');
      } else {
        await api.post('assets/bulk/create', { items: formItems.map(toPayload) });
        toast(`Добавлено: ${formItems.length} предм.`, 'success');
      }
      setShowForm(false);
      load();
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  // ---- CRUD ----
  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`assets/${id}`);
      toast('Запись удалена', 'success');
      setSelected(prev => { const n = new Set(prev); n.delete(id); return n; });
      load();
    } catch { toast('Ошибка удаления', 'error'); }
  }

  // ---- Notify ----
  async function notifyOne(id) {
    setNotifying(prev => new Set([...prev, id]));
    try {
      await api.post(`assets/${id}/notify`);
      toast('Уведомление отправлено', 'success');
      load();
    } catch (e) {
      const d = e.response?.data?.detail;
      toast(d === 'no_telegram' ? 'У сотрудника нет Telegram' : 'Ошибка отправки', 'error');
    } finally {
      setNotifying(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  }

  // ---- Bulk ----
  async function bulkDelete() {
    if (!selected.size) return;
    if (!window.confirm(`Удалить ${selected.size} записей?`)) return;
    try {
      await api.post('assets/bulk/delete', { ids: [...selected] });
      toast(`Удалено: ${selected.size}`, 'success');
      setSelected(new Set());
      load();
    } catch { toast('Ошибка удаления', 'error'); }
  }

  async function bulkNotify() {
    if (!selected.size) return;
    try {
      const res = await api.post('assets/bulk/notify', { ids: [...selected] });
      toast(`Отправлено: ${res.data.sent}, ошибок: ${res.data.failed}`,
        res.data.sent > 0 ? 'success' : 'error');
      load();
    } catch { toast('Ошибка рассылки', 'error'); }
  }

  function toggleRow(id) {
    setSelected(prev => { const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function toggleAll() {
    setSelected(prev =>
      prev.size === filtered.length && filtered.length > 0
        ? new Set()
        : new Set(filtered.map(i => i.id)));
  }

  const stats = useMemo(() => {
    const t = today();
    return {
      total:     filtered.length,
      employees: new Set(filtered.map(i => i.employee_id)).size,
      overdue:   filtered.filter(i => i.return_date && i.return_date < t && !i.acked_at).length,
    };
  }, [filtered]);

  const hasFilters = filters.search || filters.employee || filters.dateFrom || filters.dateTo;

  return (
    <div className="space-y-4 max-w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <h2 className="text-2xl font-semibold">Имущество сотрудников</h2>
        <button className="btn btn-primary flex items-center gap-2 sm:ml-auto w-fit" onClick={openCreate}>
          <Plus size={16} /> Добавить
        </button>
      </div>

      {/* Filters */}
      <div className="card p-3 flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] pointer-events-none" />
          <input className="input pl-8 w-52" placeholder="ФИО / предмет"
            value={filters.search} onChange={e => setFilters(f => ({ ...f, search: e.target.value }))} />
        </div>
        <select className="input" value={filters.employee}
          onChange={e => setFilters(f => ({ ...f, employee: e.target.value }))}>
          <option value="">Все сотрудники</option>
          {employees.map(e => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
        </select>
        <input type="date" className="input" title="Выдано с"
          value={filters.dateFrom} onChange={e => setFilters(f => ({ ...f, dateFrom: e.target.value }))} />
        <span className="text-[color:var(--color-muted-foreground)] text-sm">—</span>
        <input type="date" className="input" title="Выдано по"
          value={filters.dateTo} onChange={e => setFilters(f => ({ ...f, dateTo: e.target.value }))} />
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
          <button className="btn text-sm flex items-center gap-1.5 bg-red-50 text-red-600 border-red-200 hover:bg-red-100"
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
              <th className="text-left px-3 py-2.5 hidden xl:table-cell">Статус</th>
              <th className="w-24 px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[color:var(--color-border)]">
            {filtered.length === 0 && (
              <tr><td colSpan={10} className="px-4 py-10 text-center text-sm text-[color:var(--color-muted-foreground)] italic">Нет данных</td></tr>
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
                    <button title="Уведомить в бот" disabled={notifying.has(item.id)}
                      onClick={() => notifyOne(item.id)}
                      className={`p-1.5 rounded transition-colors ${notifying.has(item.id) ? 'opacity-40 cursor-not-allowed' : 'text-blue-500 hover:text-blue-700 hover:bg-blue-50'}`}>
                      <Bell size={14} />
                    </button>
                    <button title="Редактировать" onClick={() => openEdit(item)}
                      className="p-1.5 rounded text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] hover:bg-[color:var(--color-muted)] transition-colors">
                      <Pencil size={14} />
                    </button>
                    <button title="Удалить" onClick={() => remove(item.id)}
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
        {stats.overdue > 0 && <span className="text-amber-600 font-medium">⚠️ Просрочено: {stats.overdue}</span>}
      </div>

      {/* Modal */}
      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-3xl w-full">
            <h2 className="text-xl font-semibold mb-4">
              {editId !== null ? 'Редактировать запись' : 'Выдать имущество'}
            </h2>

            {/* Employee row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-4">
              <div>
                <label className="text-sm font-medium">Сотрудник *</label>
                <select className="input mt-1 w-full" value={formEmp.employee_id}
                  onChange={e => pickEmployee(e.target.value)}>
                  <option value="">Выберите сотрудника</option>
                  {employees.map(e => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium">Должность</label>
                <input className="input mt-1 w-full" list="asset-positions"
                  placeholder="Должность" value={formEmp.position}
                  onChange={e => setFormEmp(f => ({ ...f, position: e.target.value }))} />
                <datalist id="asset-positions">{posOptions.map(o => <option key={o} value={o} />)}</datalist>
              </div>
            </div>

            {/* Items table */}
            <div className="border border-[color:var(--color-border)] rounded-lg overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-[color:var(--color-muted)]/30 text-xs text-[color:var(--color-muted-foreground)] border-b border-[color:var(--color-border)]">
                    <th className="text-left px-3 py-2">Предмет *</th>
                    <th className="text-left px-3 py-2 w-28">Размер</th>
                    <th className="text-center px-3 py-2 w-20">Кол-во</th>
                    <th className="text-center px-3 py-2 w-24">Срок, мес.</th>
                    <th className="text-left px-3 py-2 w-36">Дата выдачи</th>
                    <th className="text-left px-3 py-2 w-36">Дата возврата</th>
                    {editId === null && <th className="w-8 px-2 py-2"></th>}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--color-border)]">
                  {formItems.map((row, idx) => (
                    <tr key={idx}>
                      <td className="px-2 py-1.5">
                        <input className="input w-full text-sm" list="asset-items"
                          placeholder="Рабочая форма" value={row.item_name}
                          onChange={e => setItemField(idx, 'item_name', e.target.value)} />
                        <datalist id="asset-items">{itemOptions.map(o => <option key={o} value={o} />)}</datalist>
                      </td>
                      <td className="px-2 py-1.5">
                        <input className="input w-full text-sm" list="asset-sizes"
                          placeholder="M / 42" value={row.size}
                          onChange={e => setItemField(idx, 'size', e.target.value)} />
                        <datalist id="asset-sizes">{sizeOptions.map(o => <option key={o} value={o} />)}</datalist>
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="number" min={1} className="input w-full text-sm text-center"
                          value={row.quantity}
                          onChange={e => setItemField(idx, 'quantity', e.target.value)} />
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="number" min={0} className="input w-full text-sm text-center"
                          placeholder="—" value={row.service_life}
                          onChange={e => setItemField(idx, 'service_life', e.target.value)} />
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="date" className="input w-full text-sm"
                          value={row.issue_date}
                          onChange={e => setItemField(idx, 'issue_date', e.target.value)} />
                      </td>
                      <td className="px-2 py-1.5">
                        <input type="date" className="input w-full text-sm"
                          value={row.return_date}
                          onChange={e => setItemField(idx, 'return_date', e.target.value)} />
                      </td>
                      {editId === null && (
                        <td className="px-2 py-1.5 text-center">
                          <button onClick={() => removeItemRow(idx)} disabled={formItems.length === 1}
                            className="p-1 rounded text-red-400 hover:text-red-600 disabled:opacity-30">
                            <X size={14} />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {editId === null && (
              <button className="btn btn-secondary text-sm flex items-center gap-1.5 mt-2"
                onClick={addItemRow}>
                <Plus size={13} /> Добавить предмет
              </button>
            )}

            <div className="flex justify-end gap-2 pt-4">
              <button className="btn btn-secondary" onClick={() => setShowForm(false)}>Отмена</button>
              <button className="btn btn-primary" onClick={saveForm}>
                {editId !== null
                  ? 'Сохранить'
                  : `Выдать ${formItems.length > 1 ? `${formItems.length} предмета` : 'предмет'}`}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
