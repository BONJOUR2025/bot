import { useState, useEffect, useMemo, useRef } from 'react';
import { Pencil, Trash2, Plus, Bell, Search, X, ChevronRight, Package, AlertTriangle, Tag } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import Modal from '../components/Modal.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s + 'T00:00:00');
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString('ru');
}

const today = () => new Date().toISOString().slice(0, 10);

function initials(name) {
  return (name || '').trim().split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join('');
}

const AVATAR_COLORS = [
  'bg-blue-100 text-blue-700', 'bg-violet-100 text-violet-700', 'bg-emerald-100 text-emerald-700',
  'bg-amber-100 text-amber-700', 'bg-rose-100 text-rose-700', 'bg-cyan-100 text-cyan-700',
  'bg-orange-100 text-orange-700', 'bg-fuchsia-100 text-fuchsia-700',
];

function avatarColor(seed) {
  let h = 0;
  for (const ch of String(seed || '')) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

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
  const employeesByPosition = useMemo(() => groupEmployeesByPosition(employees), [employees]);
  const [itemOptions, setItemOptions] = useState([]);
  const [posOptions, setPosOptions]   = useState([]);
  const [sizeOptions, setSizeOptions] = useState([]);
  const [filters, setFilters]         = useState({ search: '', employee: '', dateFrom: '', dateTo: '' });

  // Modal state
  const [showForm, setShowForm]   = useState(false);
  const [editId, setEditId]       = useState(null);        // null = create mode
  const [formEmp, setFormEmp]     = useState(emptyEmployee);
  const [formItems, setFormItems] = useState([emptyItemRow()]);

  // Bulk / notify (selection is by employee_id)
  const [selected, setSelected]   = useState(new Set());
  const [notifying, setNotifying] = useState(new Set());
  const allCheckRef               = useRef(null);

  // Detail card
  const [detailEmpId, setDetailEmpId] = useState(null);

  // Живые часы для телеметрической строки инвентарного учёта — тот же
  // паттерн, что и payout-fui-readout на «Выплатах».
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

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

  // Group filtered items by employee for the summary table
  const grouped = useMemo(() => {
    const map = new Map();
    for (const item of filtered) {
      const key = String(item.employee_id);
      if (!map.has(key)) {
        map.set(key, {
          employee_id:   item.employee_id,
          employee_name: item.employee_name,
          position:      item.position,
          items:         [],
        });
      }
      map.get(key).items.push(item);
    }
    const t = today();
    return Array.from(map.values()).map(g => {
      const totalQty   = g.items.reduce((s, i) => s + (Number(i.quantity) || 0), 0);
      const overdue     = g.items.filter(i => i.return_date && i.return_date < t && !i.acked_at).length;
      // «Критично просрочено» — тот же порог 30+ дней, что и aging-бакет
      // на «Дебиторке» (receivable-fui-agebar), здесь применён к
      // return_date не подтверждённых предметов.
      const criticalOverdue = g.items.filter(i =>
        i.return_date && !i.acked_at && (new Date(t) - new Date(i.return_date)) / 86400000 > 30
      ).length;
      const pendingAck  = g.items.filter(i => !i.acked_at).length;
      const lastIssue   = g.items.reduce((max, i) => (i.issue_date || '') > max ? (i.issue_date || '') : max, '');
      return { ...g, totalQty, overdue, criticalOverdue, pendingAck, lastIssue };
    }).sort((a, b) => (a.employee_name || '').localeCompare(b.employee_name || ''));
  }, [filtered]);

  const detailGroup = useMemo(
    () => grouped.find(g => String(g.employee_id) === String(detailEmpId)) || null,
    [grouped, detailEmpId]
  );

  useEffect(() => {
    if (allCheckRef.current)
      allCheckRef.current.indeterminate = selected.size > 0 && selected.size < grouped.length;
  }, [selected, grouped]);

  useEffect(() => {
    // Close the detail card if its employee no longer has any matching items (deleted / filtered out)
    if (detailEmpId !== null && !detailGroup) setDetailEmpId(null);
  }, [detailEmpId, detailGroup]);

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

  // ---- Bulk (operates on all asset items belonging to selected employees) ----
  function selectedItemIds() {
    return grouped.filter(g => selected.has(String(g.employee_id)))
      .flatMap(g => g.items.map(i => i.id));
  }

  async function bulkDelete() {
    const ids = selectedItemIds();
    if (!ids.length) return;
    if (!window.confirm(`Удалить ${ids.length} записей у ${selected.size} сотрудник(ов)?`)) return;
    try {
      await api.post('assets/bulk/delete', { ids });
      toast(`Удалено: ${ids.length}`, 'success');
      setSelected(new Set());
      load();
    } catch { toast('Ошибка удаления', 'error'); }
  }

  async function bulkNotify() {
    const ids = selectedItemIds();
    if (!ids.length) return;
    try {
      const res = await api.post('assets/bulk/notify', { ids });
      toast(`Отправлено: ${res.data.sent}, ошибок: ${res.data.failed}`,
        res.data.sent > 0 ? 'success' : 'error');
      load();
    } catch { toast('Ошибка рассылки', 'error'); }
  }

  function toggleRow(employeeId) {
    const key = String(employeeId);
    setSelected(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n; });
  }
  function toggleAll() {
    setSelected(prev =>
      prev.size === grouped.length && grouped.length > 0
        ? new Set()
        : new Set(grouped.map(g => String(g.employee_id))));
  }

  const stats = useMemo(() => {
    const t = today();
    return {
      total:     filtered.length,
      employees: new Set(filtered.map(i => i.employee_id)).size,
      overdue:   filtered.filter(i => i.return_date && i.return_date < t && !i.acked_at).length,
      pendingAck: filtered.filter(i => !i.acked_at).length,
      criticalOverdue: filtered.filter(i =>
        i.return_date && !i.acked_at && (new Date(t) - new Date(i.return_date)) / 86400000 > 30
      ).length,
    };
  }, [filtered]);

  const hasFilters = filters.search || filters.employee || filters.dateFrom || filters.dateTo;

  return (
    <div className="space-y-4 max-w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div>
          <span className="ui-eyebrow mb-3">{list.length ? `Единиц на руках: ${list.length}` : 'Ничего не выдано'}</span>
          <h2 className="text-2xl font-semibold">Имущество сотрудников</h2>
        </div>
        <button className="btn btn--primary flex items-center gap-2 sm:ml-auto w-fit" onClick={openCreate}>
          <Plus size={16} /> Добавить
        </button>
      </div>

      {/* Телеметрия инвентарного учёта — реальные агрегаты из stats
          (те же цифры, что и в блоке «Stats» ниже страницы), плюс живые
          часы. Не декоративные числа. */}
      <div className="asset-fui-readout">
        <span>УЧЁТ: <b>{stats.total}</b></span>
        <span className="sep">/</span>
        <span>СОТРУДНИКОВ: <b>{stats.employees}</b></span>
        <span className="sep">/</span>
        <span>НЕ ПОДТВ.: <b>{stats.pendingAck}</b></span>
        {stats.overdue > 0 && (
          <>
            <span className="sep">/</span>
            <span style={{ color: 'var(--color-warning)' }}>ПРОСРОЧЕНО: <b>{stats.overdue}</b></span>
          </>
        )}
        {stats.criticalOverdue > 0 && (
          <>
            <span className="sep">/</span>
            <span style={{ color: 'var(--color-danger)' }}>КРИТИЧНО 30+ ДН.: <b>{stats.criticalOverdue}</b></span>
          </>
        )}
        <span className="sep">/</span>
        <span>{now.toLocaleTimeString('ru-RU')}<span className="asset-fui-cursor">▮</span></span>
      </div>

      {/* Filters */}
      <div className="app-card p-3 flex flex-wrap gap-2 items-center">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] pointer-events-none" />
          <input className="input pl-8 w-52" placeholder="ФИО / предмет"
            value={filters.search} onChange={e => setFilters(f => ({ ...f, search: e.target.value }))} />
        </div>
        <select className="input" value={filters.employee}
          onChange={e => setFilters(f => ({ ...f, employee: e.target.value }))}>
          <option value="">Все сотрудники</option>
          {employeesByPosition.map(([position, list]) => (
            <optgroup key={position} label={position}>
              {list.map(e => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
            </optgroup>
          ))}
        </select>
        <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 sm:items-center w-full sm:w-auto">
          <input type="date" className="input w-full sm:w-auto" title="Выдано с"
            value={filters.dateFrom} onChange={e => setFilters(f => ({ ...f, dateFrom: e.target.value }))} />
          <span className="text-[color:var(--color-muted-foreground)] text-sm hidden sm:inline">—</span>
          <input type="date" className="input w-full sm:w-auto" title="Выдано по"
            value={filters.dateTo} onChange={e => setFilters(f => ({ ...f, dateTo: e.target.value }))} />
        </div>
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
          <span className="text-sm font-medium">Выбрано сотрудников: {selected.size}</span>
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

      {/* Table — one row per employee */}
      <div className="flex items-center gap-2 px-1 text-sm text-[color:var(--color-muted-foreground)]">
        <input type="checkbox" ref={allCheckRef}
          checked={grouped.length > 0 && selected.size === grouped.length}
          onChange={toggleAll} />
        <span>Выбрать всех</span>
      </div>
      <div className="app-card overflow-hidden">
        <ResponsiveTable
          data={grouped}
          keyFn={g => g.employee_id}
          emptyText="Имущество не заведено" emptyHint="Добавьте первую единицу — она появится и в карточке сотрудника."
          rowClass={g => selected.has(String(g.employee_id))
            ? 'bg-[color:var(--color-primary)]/5'
            : 'hover:bg-[color:var(--color-muted)]/10'}
          columns={[
            {
              label: '',
              headerClass: 'w-9',
              cellClass: 'w-9',
              render: g => (
                <input type="checkbox" checked={selected.has(String(g.employee_id))}
                  onChange={() => toggleRow(g.employee_id)} onClick={e => e.stopPropagation()} />
              ),
            },
            {
              label: 'Сотрудник',
              primary: true,
              render: g => (
                <div className="flex items-center gap-2.5 cursor-pointer" onClick={() => setDetailEmpId(g.employee_id)}>
                  <span className={`flex items-center justify-center w-8 h-8 rounded-full text-xs font-semibold shrink-0 ${avatarColor(g.employee_name)}`}>
                    {initials(g.employee_name) || '?'}
                  </span>
                  <span className="font-medium">{g.employee_name}</span>
                </div>
              ),
            },
            {
              label: 'Должность',
              mobileHide: true,
              headerClass: 'hidden md:table-cell',
              cellClass: 'hidden md:table-cell text-[color:var(--color-muted-foreground)] text-xs',
              render: g => g.position || '—',
            },
            {
              label: 'Предметов',
              headerClass: 'text-center',
              cellClass: 'text-center',
              render: g => (
                <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-[color:var(--color-muted)]">
                  <Package size={11} /> {g.items.length}
                </span>
              ),
            },
            {
              label: 'Кол-во',
              mobileHide: true,
              headerClass: 'hidden sm:table-cell text-center',
              cellClass: 'hidden sm:table-cell text-center',
              render: g => g.totalQty,
            },
            {
              label: 'Посл. выдача',
              mobileHide: true,
              headerClass: 'hidden lg:table-cell',
              cellClass: 'hidden lg:table-cell whitespace-nowrap text-[color:var(--color-muted-foreground)]',
              render: g => fmtDate(g.lastIssue),
            },
            {
              label: 'Статус',
              render: g => (
                <div className="flex items-center gap-1.5 flex-wrap">
                  {g.criticalOverdue > 0 && (
                    <span className="asset-fui-radar" title={`Просрочено более 30 дней: ${g.criticalOverdue}`}>
                      <i /><i /><i /><b />
                    </span>
                  )}
                  {g.overdue > 0 && (
                    <span className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
                      <AlertTriangle size={11} /> {g.overdue}
                    </span>
                  )}
                  {g.pendingAck > 0
                    ? <span className="text-xs text-[color:var(--color-muted-foreground)]">⏳ не подтвердил {g.pendingAck}</span>
                    : <span className="text-xs text-green-600 font-medium">✅ всё подтверждено</span>}
                </div>
              ),
            },
            {
              label: '',
              isAction: true,
              headerClass: 'w-10',
              cellClass: 'text-right',
              render: g => (
                <button onClick={() => setDetailEmpId(g.employee_id)} title="Подробнее"
                  className="p-1 rounded text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)]">
                  <ChevronRight size={16} />
                </button>
              ),
            },
          ]}
        />
      </div>

      {/* Stats */}
      <div className="flex flex-wrap gap-4 text-sm text-[color:var(--color-muted-foreground)] px-1">
        <span>Записей: <b className="text-[color:var(--color-foreground)]">{stats.total}</b></span>
        <span>Сотрудников: <b className="text-[color:var(--color-foreground)]">{stats.employees}</b></span>
        {stats.overdue > 0 && <span className="text-amber-600 font-medium">⚠️ Просрочено: {stats.overdue}</span>}
      </div>

      {/* Employee detail card */}
      <Modal isOpen={!!detailGroup} onClose={() => setDetailEmpId(null)}>
        {detailGroup && (
          <div className="modal-card w-full max-w-3xl sm:mx-4">
            <div className="flex items-start gap-3 mb-5 flex-wrap">
              <span className={`flex items-center justify-center w-12 h-12 rounded-full text-base font-semibold shrink-0 ${avatarColor(detailGroup.employee_name)}`}>
                {initials(detailGroup.employee_name) || '?'}
              </span>
              <div className="flex-1 min-w-[140px]">
                <h2 className="text-xl font-semibold">{detailGroup.employee_name}</h2>
                <p className="text-sm text-[color:var(--color-muted-foreground)]">{detailGroup.position || '—'}</p>
              </div>
              <button className="btn btn-secondary flex items-center gap-1.5 text-sm shrink-0"
                onClick={() => { const empId = detailGroup.employee_id; setDetailEmpId(null); openCreate(); pickEmployee(empId); }}>
                <Plus size={14} /> Выдать ещё
              </button>
              <button className="p-1.5 rounded text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-muted)] shrink-0"
                onClick={() => setDetailEmpId(null)}>
                <X size={18} />
              </button>
            </div>

            <div className="flex flex-wrap gap-4 text-sm mb-4 px-1">
              <span>Предметов: <b>{detailGroup.items.length}</b></span>
              <span>Кол-во всего: <b>{detailGroup.totalQty}</b></span>
              {detailGroup.overdue > 0 && (
                <span className="text-amber-600 font-medium flex items-center gap-1"><AlertTriangle size={13} /> Просрочено: {detailGroup.overdue}</span>
              )}
            </div>

            <div className="max-h-[55vh] overflow-y-auto">
              <ResponsiveTable
                data={detailGroup.items}
                keyFn={item => item.id}
                columns={[
                  {
                    label: 'Предмет',
                    primary: true,
                    render: item => (
                      <div>
                        <span className="font-medium">{item.item_name}</span>
                        {/* Инвентарная бирка — реальный id записи (assets.id из
                            hr.db), не выдуманный серийник. */}
                        <div className="asset-fui-tag">
                          <Tag size={9} /> AST-{String(item.id ?? 0).padStart(5, '0')}
                        </div>
                      </div>
                    ),
                  },
                  { label: 'Размер', mobileHide: true, headerClass: 'hidden sm:table-cell', cellClass: 'hidden sm:table-cell', render: item => item.size || '—' },
                  { label: 'Кол-во', headerClass: 'text-center', cellClass: 'text-center', render: item => item.quantity },
                  { label: 'Выдано', cellClass: 'whitespace-nowrap', render: item => fmtDate(item.issue_date) },
                  { label: 'Возврат', mobileHide: true, headerClass: 'hidden lg:table-cell', cellClass: 'hidden lg:table-cell whitespace-nowrap', render: item => fmtDate(item.return_date) },
                  {
                    label: 'Статус',
                    mobileHide: true,
                    headerClass: 'hidden md:table-cell',
                    cellClass: 'hidden md:table-cell',
                    render: item => {
                      const overdueDays = item.return_date && !item.acked_at
                        ? Math.floor((new Date(today()) - new Date(item.return_date)) / 86400000)
                        : 0;
                      return (
                        <div className="flex items-center gap-1.5">
                          {overdueDays > 30 && (
                            <span className="asset-fui-radar" title={`Просрочено ${overdueDays} дн.`}>
                              <i /><i /><i /><b />
                            </span>
                          )}
                          {item.acked_at
                            ? <span className="text-green-600 text-xs font-medium">✅ {item.acked_at}</span>
                            : item.notified_at
                              ? <span className="text-[color:var(--color-muted-foreground)] text-xs">📤 {item.notified_at}</span>
                              : <span className="text-[color:var(--color-muted-foreground)]">—</span>}
                        </div>
                      );
                    },
                  },
                  {
                    label: '',
                    isAction: true,
                    headerClass: 'w-24',
                    cellClass: 'text-right',
                    render: item => (
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
                    ),
                  },
                ]}
              />
            </div>

            <div className="flex justify-end pt-4">
              <button className="btn btn-secondary" onClick={() => setDetailEmpId(null)}>Закрыть</button>
            </div>
          </div>
        )}
      </Modal>

      {/* Create / edit modal */}
      <Modal isOpen={showForm} onClose={() => setShowForm(false)}>
        <div className="modal-card w-full max-w-4xl sm:mx-4">
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
                {employeesByPosition.map(([position, list]) => (
                  <optgroup key={position} label={position}>
                    {list.map(e => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
                  </optgroup>
                ))}
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
                  <th className="text-left px-3 py-2 min-w-[180px]">Предмет *</th>
                  <th className="text-left px-3 py-2 w-32">Размер</th>
                  <th className="text-center px-3 py-2 w-24">Кол-во</th>
                  <th className="text-center px-3 py-2 w-28">Срок, мес.</th>
                  <th className="text-left px-3 py-2 w-44">Дата выдачи</th>
                  <th className="text-left px-3 py-2 w-44">Дата возврата</th>
                  {editId === null && <th className="w-8 px-2 py-2"></th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-[color:var(--color-border)]">
                {formItems.map((row, idx) => (
                  <tr key={idx}>
                    <td className="px-2 py-2">
                      <input className="input w-full text-sm" list="asset-items"
                        placeholder="Рабочая форма" value={row.item_name}
                        onChange={e => setItemField(idx, 'item_name', e.target.value)} />
                      <datalist id="asset-items">{itemOptions.map(o => <option key={o} value={o} />)}</datalist>
                    </td>
                    <td className="px-2 py-2">
                      <input className="input w-full text-sm" list="asset-sizes"
                        placeholder="M / 42" value={row.size}
                        onChange={e => setItemField(idx, 'size', e.target.value)} />
                      <datalist id="asset-sizes">{sizeOptions.map(o => <option key={o} value={o} />)}</datalist>
                    </td>
                    <td className="px-2 py-2">
                      <input type="number" min={1} className="input w-full text-sm text-center"
                        value={row.quantity}
                        onChange={e => setItemField(idx, 'quantity', e.target.value)} />
                    </td>
                    <td className="px-2 py-2">
                      <input type="number" min={0} className="input w-full text-sm text-center"
                        placeholder="—" value={row.service_life}
                        onChange={e => setItemField(idx, 'service_life', e.target.value)} />
                    </td>
                    <td className="px-2 py-2">
                      <input type="date" className="input w-full text-sm"
                        value={row.issue_date}
                        onChange={e => setItemField(idx, 'issue_date', e.target.value)} />
                    </td>
                    <td className="px-2 py-2">
                      <input type="date" className="input w-full text-sm"
                        value={row.return_date}
                        onChange={e => setItemField(idx, 'return_date', e.target.value)} />
                    </td>
                    {editId === null && (
                      <td className="px-2 py-2 text-center">
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
            <button className="btn btn--primary" onClick={saveForm}>
              {editId !== null
                ? 'Сохранить'
                : `Выдать ${formItems.length > 1 ? `${formItems.length} предмета` : 'предмет'}`}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
