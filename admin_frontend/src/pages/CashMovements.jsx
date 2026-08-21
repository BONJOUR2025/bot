import { useEffect, useState, useMemo } from 'react';
import {
  Search, X, AlertTriangle, CheckCircle, Download, RefreshCw,
  ChevronUp, ChevronDown, ChevronsUpDown, ChevronRight,
  Tag, Settings, Plus, Trash2, Edit2, Check, Building2,
  LinkIcon, Unlink, BarChart3, TrendingUp, Wallet, ArrowUpDown,
  CalendarDays, Info,
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable, SkeletonStats } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs, StatCard } from '../components/ui/SalaryUI.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';
import KpiCard from '../components/ui/Kpi.jsx';
import { CHART_PALETTE as CHART_COLORS } from '../utils/chartPalette.js';

// ── Formatters ────────────────────────────────────────────────────
const fmtDate = (v) => {
  if (!v) return '—';
  const d = new Date(v);
  return isNaN(d) ? v : d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};
const fmtMoney = (v) =>
  v == null ? '—' : Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + ' ₽';
const fmtMoneyShort = (v) =>
  !v ? '—' : Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 0 }) + ' ₽';

// ── Date helpers ──────────────────────────────────────────────────
const isoToday    = ()          => new Date().toISOString().slice(0, 10);
const isoMStart   = (offset=0) => { const d=new Date(); d.setMonth(d.getMonth()+offset,1);   return d.toISOString().slice(0,10); };
const isoMEnd     = (offset=0) => { const d=new Date(); d.setMonth(d.getMonth()+offset+1,0); return d.toISOString().slice(0,10); };
const isoYStart   = ()          => `${new Date().getFullYear()}-01-01`;
const isoMinusDays = (iso, n)  => { const d=new Date(iso); d.setDate(d.getDate()-n);       return d.toISOString().slice(0,10); };

// Mirrors DAILY_BALANCE_MAX_DAYS in app/services/firebird_service.py. The
// server clamps regardless; this is only so the «Всё время» preset (which
// clears both dates) still sends a bounded range instead of nothing.
const DAILY_BALANCE_MAX_DAYS = 366;

const DATE_PRESETS = [
  { label: 'Этот месяц',    from: () => isoMStart(0),  to: () => isoToday() },
  { label: 'Прошлый месяц', from: () => isoMStart(-1), to: () => isoMEnd(-1) },
  { label: 'Этот год',      from: () => isoYStart(),   to: () => isoToday() },
  { label: 'Всё время',     from: () => '',             to: () => '' },
];

const DAY_NAMES    = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];

// ── Sort icon ─────────────────────────────────────────────────────
function SortIcon({ field, sort }) {
  if (sort.field !== field) return <ChevronsUpDown size={13} className="opacity-30" />;
  return sort.dir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />;
}

// ── Mapping Manager (users / branches) ───────────────────────────
function MappingManager({ title, icon: Icon, endpoint, onClose, onChanged }) {
  const { toast } = useToast();
  const [entries, setEntries] = useState([]);
  const [newId, setNewId]     = useState('');
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName]   = useState('');

  useEffect(() => {
    api.get(`cash-moves/${endpoint}`).then((r) => setEntries(r.data || [])).catch(() => {});
  }, [endpoint]);

  async function upsert(id, name) {
    try {
      await api.post(`cash-moves/${endpoint}`, { id, name });
      const updated = entries.find((e) => e.id === id)
        ? entries.map((e) => e.id === id ? { id, name } : e)
        : [...entries, { id, name }];
      setEntries(updated);
      onChanged();
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  async function del(id) {
    try {
      await api.delete(`cash-moves/${endpoint}/${encodeURIComponent(id)}`);
      const updated = entries.filter((e) => e.id !== id);
      setEntries(updated);
      onChanged();
    } catch { toast('Ошибка удаления', 'error'); }
  }

  function addNew() {
    if (!newId.trim() || !newName.trim()) return;
    upsert(newId.trim(), newName.trim());
    setNewId(''); setNewName('');
  }

  function saveEdit(id) {
    if (!editName.trim()) return;
    upsert(id, editName.trim());
    setEditingId(null);
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-lg w-full max-h-[80vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2"><Icon size={18} /> {title}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-bg-secondary)]"><X size={18} /></button>
        </div>
        <div className="text-xs text-[color:var(--color-muted-foreground)] mb-3">
          ID берётся из Агбис. При добавлении нового пользователя/филиала в Агбис — добавьте здесь его ID и имя.
        </div>
        <div className="overflow-y-auto flex-1 divide-y divide-[color:var(--color-border)]">
          {entries.map((e) => (
            <div key={e.id} className="flex items-center gap-3 py-2">
              <span className="font-mono text-xs text-[color:var(--color-muted-foreground)] w-20 shrink-0">{e.id}</span>
              {editingId === e.id ? (
                <>
                  <input className="input flex-1 text-sm" value={editName}
                    onChange={(x) => setEditName(x.target.value)}
                    onKeyDown={(x) => x.key === 'Enter' && saveEdit(e.id)} />
                  <button onClick={() => saveEdit(e.id)} className="p-1.5 text-green-600 hover:bg-green-50 rounded"><Check size={14} /></button>
                  <button onClick={() => setEditingId(null)} className="p-1.5 text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-bg-secondary)] rounded"><X size={14} /></button>
                </>
              ) : (
                <>
                  <span className="flex-1 text-sm">{e.name}</span>
                  <button onClick={() => { setEditingId(e.id); setEditName(e.name); }} className="p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]"><Edit2 size={13} /></button>
                  <button onClick={() => del(e.id)} className="p-1.5 rounded hover:bg-red-50 text-[color:var(--color-muted-foreground)] hover:text-red-500"><Trash2 size={13} /></button>
                </>
              )}
            </div>
          ))}
        </div>
        <div className="pt-4 border-t border-[color:var(--color-border)] flex gap-2">
          <input className="input w-24 font-mono text-sm" placeholder="ID" value={newId} onChange={(e) => setNewId(e.target.value)} />
          <input className="input flex-1 text-sm" placeholder="Имя…" value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addNew()} />
          <button onClick={addNew} className="btn btn--primary"><Plus size={14} /></button>
        </div>
      </div>
    </div>
  );
}

// ── Category Manager modal ────────────────────────────────────────
function CategoryManager({ categories, onClose, onChanged }) {
  const { toast } = useToast();
  const [cats, setCats] = useState(categories);
  const [newCatName, setNewCatName] = useState('');
  const [editingCat, setEditingCat] = useState(null);
  const [newPrefix, setNewPrefix] = useState('');

  async function addCategory() {
    if (!newCatName.trim()) return;
    try {
      const res = await api.post('cash-moves/categories', { name: newCatName.trim().toUpperCase(), prefixes: [] });
      const updated = [...cats, res.data];
      setCats(updated);
      setNewCatName('');
      onChanged(updated);
    } catch { toast('Ошибка создания категории', 'error'); }
  }

  async function deleteCategory(name) {
    if (!confirm(`Удалить категорию «${name}»?`)) return;
    try {
      await api.delete(`cash-moves/categories/${encodeURIComponent(name)}`);
      const updated = cats.filter((c) => c.name !== name);
      setCats(updated);
      onChanged(updated);
    } catch { toast('Ошибка удаления', 'error'); }
  }

  function startEdit(cat) {
    setEditingCat({ name: cat.name, newName: cat.name, prefixes: [...cat.prefixes] });
    setNewPrefix('');
  }

  function addPrefixLocal() {
    if (!newPrefix.trim()) return;
    setEditingCat((e) => ({ ...e, prefixes: [...e.prefixes, newPrefix.trim()] }));
    setNewPrefix('');
  }

  function removePrefixLocal(p) {
    setEditingCat((e) => ({ ...e, prefixes: e.prefixes.filter((x) => x !== p) }));
  }

  async function saveEdit() {
    try {
      const body = {};
      if (editingCat.newName !== editingCat.name) body.new_name = editingCat.newName.trim().toUpperCase();
      body.prefixes = editingCat.prefixes;
      const res = await api.patch(`cash-moves/categories/${encodeURIComponent(editingCat.name)}`, body);
      const updated = cats.map((c) => c.name === editingCat.name ? res.data : c);
      setCats(updated);
      onChanged(updated);
      setEditingCat(null);
      toast('Сохранено', 'success');
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full max-h-[85vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold flex items-center gap-2"><Settings size={18} /> Управление категориями</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-bg-secondary)]"><X size={18} /></button>
        </div>
        <div className="overflow-y-auto flex-1 space-y-3 pr-1">
          {cats.map((cat) => (
            <div key={cat.name} className="app-card p-3">
              {editingCat?.name === cat.name ? (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <input className="input flex-1 font-medium" value={editingCat.newName}
                      onChange={(e) => setEditingCat((x) => ({ ...x, newName: e.target.value }))} />
                    <button onClick={saveEdit} className="btn btn--primary flex items-center gap-1"><Check size={14} /> Сохранить</button>
                    <button onClick={() => setEditingCat(null)} className="btn btn--secondary">Отмена</button>
                  </div>
                  <div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Префиксы (начало Основания):</div>
                    <div className="flex flex-wrap gap-1.5 mb-2">
                      {editingCat.prefixes.map((p) => (
                        <span key={p} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono bg-[color:var(--color-bg-secondary)] border border-[color:var(--color-border)]">
                          {p}
                          <button onClick={() => removePrefixLocal(p)} className="hover:text-red-500"><X size={10} /></button>
                        </span>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <input className="input flex-1 text-sm font-mono" placeholder="Новый префикс…" value={newPrefix}
                        onChange={(e) => setNewPrefix(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && addPrefixLocal()} />
                      <button onClick={addPrefixLocal} className="btn btn--primary"><Plus size={14} /></button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="font-medium mb-1">{cat.name}</div>
                    <div className="flex flex-wrap gap-1">
                      {cat.prefixes.length > 0
                        ? cat.prefixes.map((p) => (
                          <span key={p} className="px-2 py-0.5 rounded text-xs font-mono bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]">{p}</span>
                        ))
                        : <span className="text-xs text-[color:var(--color-muted-foreground)] italic">Нет префиксов</span>
                      }
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <button onClick={() => startEdit(cat)} className="p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]"><Edit2 size={14} /></button>
                    <button onClick={() => deleteCategory(cat.name)} className="p-1.5 rounded hover:bg-red-50 text-[color:var(--color-muted-foreground)] hover:text-red-500"><Trash2 size={14} /></button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="pt-4 border-t border-[color:var(--color-border)] flex gap-2">
          <input className="input flex-1" placeholder="Название новой категории…" value={newCatName}
            onChange={(e) => setNewCatName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addCategory()} />
          <button onClick={addCategory} className="btn btn--primary flex items-center gap-1"><Plus size={14} /> Добавить</button>
        </div>
      </div>
    </div>
  );
}

// ── Assign modal ──────────────────────────────────────────────────
function AssignModal({ record, categories, onSave, onClose }) {
  const [selCat, setSelCat] = useState('');
  const [addPrefix, setAddPrefix] = useState(record.BASIS ? record.BASIS.trim() : '');
  const [createRule, setCreateRule] = useState(true);

  function handleSave() {
    if (!selCat) return;
    onSave({
      record_id: String(record.ID_KASSES_MOVE),
      category: selCat,
      add_prefix: createRule && addPrefix.trim() ? addPrefix.trim() : null,
    });
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-md">
        <h3 className="text-base font-semibold mb-1 flex items-center gap-2"><Tag size={16} /> Назначить категорию</h3>
        <p className="text-xs text-[color:var(--color-muted-foreground)] mb-4 font-mono break-all">{record.BASIS || '—'}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Категория</label>
            <select className="input w-full" value={selCat} onChange={(e) => setSelCat(e.target.value)}>
              <option value="">Выберите категорию…</option>
              {categories.map((c) => <option key={c.name} value={c.name}>{c.name}</option>)}
            </select>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="w-4 h-4 rounded" checked={createRule}
              onChange={(e) => setCreateRule(e.target.checked)} />
            <span className="text-sm font-medium">Создать правило (добавить префикс)</span>
          </label>
          {createRule && (
            <div>
              <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">
                Префикс для правила — записи с таким началом Основания будут автоматически попадать в категорию
              </label>
              <input className="input w-full font-mono text-sm" value={addPrefix}
                onChange={(e) => setAddPrefix(e.target.value)} placeholder="Начало Основания…" />
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 mt-5">
          <button className="btn btn--secondary" onClick={onClose}>Отмена</button>
          <button className="btn btn--primary" disabled={!selCat} onClick={handleSave}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}

// ── Linked payout details modal ───────────────────────────────────
function LinkedPayoutModal({ payout, onUnlink, onClose }) {
  const { toast } = useToast();
  const [unlinking, setUnlinking] = useState(false);

  const statusColor = (s) => {
    if (s === 'Одобрено') return 'bg-green-100 text-green-800';
    if (s === 'Отклонено') return 'bg-red-100 text-red-800';
    if (s === 'Выплачено') return 'bg-blue-100 text-blue-800';
    return 'bg-yellow-100 text-yellow-800';
  };

  async function handleUnlink() {
    setUnlinking(true);
    try {
      await onUnlink();
      onClose();
    } catch { toast('Ошибка отвязки', 'error'); }
    finally { setUnlinking(false); }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-sm w-full">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} className="text-green-500" /> Привязанная выплата
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-bg-secondary)]"><X size={18} /></button>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Сотрудник</span>
            <span className="font-medium">{payout.name || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Сумма</span>
            <span className="font-semibold text-[color:var(--color-primary)]">
              {Number(payout.amount).toLocaleString('ru-RU')} ₽
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Тип</span>
            <span>{payout.payout_type || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Способ</span>
            <span>{payout.method || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Дата</span>
            <span>{payout.timestamp ? payout.timestamp.slice(0, 10) : '—'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[color:var(--color-muted-foreground)]">Статус</span>
            <span className={`px-2 py-0.5 rounded text-xs ${statusColor(payout.status)}`}>{payout.status}</span>
          </div>
        </div>
        <div className="flex justify-between mt-5">
          <button
            className="btn text-sm text-red-500 hover:text-red-700 border-red-200 hover:border-red-400 disabled:opacity-50"
            onClick={handleUnlink}
            disabled={unlinking}
          >
            {unlinking ? <RefreshCw size={13} className="animate-spin inline mr-1" /> : <Unlink size={13} className="inline mr-1" />}
            Отвязать
          </button>
          <button className="btn" onClick={onClose}>Закрыть</button>
        </div>
      </div>
    </div>
  );
}

// ── Create Payout from cash movement modal ────────────────────────
function CreatePayoutModal({ move, onClose, onCreated }) {
  const { toast } = useToast();
  const [tab, setTab]           = useState('create');
  const [employees, setEmployees] = useState([]);
  const employeesByPosition = useMemo(() => groupEmployeesByPosition(employees), [employees]);
  const [userId, setUserId]     = useState('');
  const [payoutType, setPayoutType] = useState('Зарплата');
  const [saving, setSaving]     = useState(false);
  const defaultFrom = move.DK_DATE ? (() => {
    const d = new Date(move.DK_DATE); d.setDate(d.getDate() - 7); return d.toISOString().slice(0, 10);
  })() : '';
  const defaultTo = move.DK_DATE ? (() => {
    const d = new Date(move.DK_DATE); d.setDate(d.getDate() + 7); return d.toISOString().slice(0, 10);
  })() : '';
  const [linkDateFrom, setLinkDateFrom] = useState(defaultFrom);
  const [linkDateTo, setLinkDateTo]     = useState(defaultTo);
  const [payoutsList, setPayoutsList]   = useState([]);
  const [loadingPayouts, setLoadingPayouts] = useState(false);
  const [linking, setLinking]           = useState(null);

  useEffect(() => {
    api.get('employees/').then((r) => setEmployees(r.data || [])).catch(() => {});
  }, []);

  async function loadPayouts() {
    setLoadingPayouts(true);
    try {
      const params = {};
      if (linkDateFrom) params.from_date = linkDateFrom;
      if (linkDateTo)   params.to_date   = linkDateTo;
      const res = await api.get('payouts/', { params });
      setPayoutsList(Array.isArray(res.data) ? res.data : []);
    } catch { toast('Ошибка загрузки выплат', 'error'); }
    finally { setLoadingPayouts(false); }
  }

  useEffect(() => { if (tab === 'link') loadPayouts(); }, [tab]);

  async function handleLinkExisting(payoutId) {
    setLinking(payoutId);
    try {
      const res = await api.post(`payouts/${payoutId}/link-move`, { move_id: String(move.ID_KASSES_MOVE) });
      toast('Движение привязано к выплате', 'success');
      onCreated(String(move.ID_KASSES_MOVE), res.data);
      onClose();
    } catch { toast('Ошибка привязки', 'error'); }
    finally { setLinking(null); }
  }

  async function handleSave() {
    if (!userId) { toast('Выберите сотрудника', 'error'); return; }
    const emp = employees.find((e) => String(e.id) === String(userId));
    if (!emp) { toast('Сотрудник не найден', 'error'); return; }
    setSaving(true);
    try {
      const res = await api.post('payouts/', {
        user_id: String(emp.id),
        name: emp.name || '',
        phone: emp.phone || '',
        card_number: emp.card_number || '',
        bank: emp.bank || '',
        amount: Number(move.SUMM) || 0,
        method: 'Из кассы',
        payout_type: payoutType,
        status: 'Выплачено',
        cash_move_id: String(move.ID_KASSES_MOVE),
        note: move.BASIS ? `Основание: ${move.BASIS}` : '',
        timestamp: move.DK_DATE ? move.DK_DATE + 'T00:00:00' : undefined,
      });
      toast('Выплата создана и привязана', 'success');
      onCreated(String(move.ID_KASSES_MOVE), res.data);
      onClose();
    } catch (e) {
      toast(e.response?.data?.detail || 'Ошибка создания выплаты', 'error');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-semibold flex items-center gap-2">
            <LinkIcon size={16} /> Привязать выплату к движению
          </h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-[color:var(--color-bg-secondary)]"><X size={18} /></button>
        </div>
        <div className="rounded-lg bg-[color:var(--color-bg-secondary)] border border-[color:var(--color-border)] p-3 mb-3 text-sm space-y-1 shrink-0">
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Дата</span>
            <span className="font-medium">{move.DK_DATE || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Филиал</span>
            <span className="font-medium">{move.dep_name || '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[color:var(--color-muted-foreground)]">Сумма</span>
            <span className="font-semibold text-[color:var(--color-primary)]">{Number(move.SUMM).toLocaleString('ru-RU')} ₽</span>
          </div>
          {move.BASIS && (
            <div className="flex justify-between gap-4">
              <span className="text-[color:var(--color-muted-foreground)] shrink-0">Основание</span>
              <span className="font-mono text-xs text-right truncate min-w-0">{move.BASIS}</span>
            </div>
          )}
        </div>
        <div className="flex rounded-lg border border-[color:var(--color-border)] overflow-hidden mb-3 shrink-0 text-sm font-medium">
          <button
            className={`flex-1 px-3 py-2 transition-colors ${tab === 'create' ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-bg-secondary)]'}`}
            onClick={() => setTab('create')}
          >
            Создать новую
          </button>
          <button
            className={`flex-1 px-3 py-2 transition-colors ${tab === 'link' ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-bg-secondary)]'}`}
            onClick={() => setTab('link')}
          >
            Привязать существующую
          </button>
        </div>
        {tab === 'create' ? (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium mb-1">Сотрудник *</label>
              <select className="input w-full" value={userId} onChange={(e) => setUserId(e.target.value)}>
                <option value="">Выберите сотрудника…</option>
                {employeesByPosition.map(([position, list]) => (
                  <optgroup key={position} label={position}>
                    {list.map((e) => (
                      <option key={e.id} value={e.id}>{e.name}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium mb-1">Тип выплаты</label>
              <select className="input w-full" value={payoutType} onChange={(e) => setPayoutType(e.target.value)}>
                {['Зарплата', 'Аванс', 'Премия', 'Другое'].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn" onClick={onClose}>Отмена</button>
              <button className="btn btn--primary flex items-center gap-1.5" onClick={handleSave} disabled={saving || !userId}>
                <LinkIcon size={14} /> {saving ? 'Создаю…' : 'Создать выплату'}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col flex-1 min-h-0">
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 mb-2 shrink-0">
              <input type="date" className="input w-full sm:w-auto sm:flex-1" value={linkDateFrom} onChange={(e) => setLinkDateFrom(e.target.value)} />
              <input type="date" className="input w-full sm:w-auto sm:flex-1" value={linkDateTo}   onChange={(e) => setLinkDateTo(e.target.value)} />
              <button className="btn btn--primary w-full sm:w-auto shrink-0" onClick={loadPayouts} disabled={loadingPayouts}>
                {loadingPayouts ? <RefreshCw size={13} className="animate-spin" /> : 'Найти'}
              </button>
            </div>
            {loadingPayouts ? (
              <div className="flex-1 flex items-center justify-center text-[color:var(--color-muted-foreground)] text-sm">Загрузка…</div>
            ) : payoutsList.length === 0 ? (
              <div className="flex-1 flex items-center justify-center text-[color:var(--color-muted-foreground)] text-sm">Нет выплат за период</div>
            ) : (
              <div className="overflow-auto flex-1">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-[color:var(--color-bg-secondary)] text-xs uppercase text-[color:var(--color-muted-foreground)]">
                    <tr>
                      <th className="px-3 py-2 text-left">Сотрудник</th>
                      <th className="px-3 py-2 text-left whitespace-nowrap">Тип</th>
                      <th className="px-3 py-2 text-right whitespace-nowrap">Сумма</th>
                      <th className="px-3 py-2 text-left whitespace-nowrap">Дата</th>
                      <th className="px-3 py-2"></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[color:var(--color-border)]">
                    {payoutsList.map((p) => (
                      <tr key={p.id} className={`hover:bg-[color:var(--color-bg-secondary)] ${p.cash_move_id ? 'opacity-50' : ''}`}>
                        <td className="px-3 py-2 max-w-[200px] truncate" title={p.name}>{p.name}</td>
                        <td className="px-3 py-2 whitespace-nowrap text-xs">{p.payout_type}</td>
                        <td className="px-3 py-2 text-right font-medium whitespace-nowrap">{Number(p.amount).toLocaleString('ru-RU')} ₽</td>
                        <td className="px-3 py-2 text-xs whitespace-nowrap">{p.timestamp ? p.timestamp.slice(0, 10) : '—'}</td>
                        <td className="px-3 py-2 text-right">
                          <button
                            className="btn btn--primary text-xs px-2 py-1 disabled:opacity-50"
                            disabled={linking === p.id}
                            onClick={() => handleLinkExisting(p.id)}
                          >
                            {linking === p.id ? <RefreshCw size={12} className="animate-spin" /> : 'Привязать'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="flex justify-end pt-2 shrink-0">
              <button className="btn" onClick={onClose}>Отмена</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Visualization components ──────────────────────────────────────

// Rendered on both the "Обзор" and "Остатки" tabs. It's one control, not
// two: the state lives in the page and both tabs read the same applied
// range, so switching tabs never silently changes the period you're
// looking at.
function DateRangeBar({ dateFrom, dateTo, setDateFrom, setDateTo, onApply, loading }) {
  return (
    <div className="flex flex-wrap gap-2 items-center">
      {DATE_PRESETS.map((p) => (
        <button key={p.label} onClick={() => onApply(p.from(), p.to())}
          className="px-3 py-1 rounded-full text-xs font-medium border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
          {p.label}
        </button>
      ))}
      <div className="flex items-center gap-2 ml-auto">
        <input type="date" className="input text-xs py-1 h-8" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        <span className="text-[color:var(--color-muted-foreground)] text-xs">—</span>
        <input type="date" className="input text-xs py-1 h-8" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        <button onClick={() => onApply(dateFrom, dateTo)} disabled={loading} className="btn btn--primary h-8 px-3 text-xs">Применить</button>
      </div>
    </div>
  );
}

// Cash-on-hand per register, from DOCS_KASSA (the full ledger) — not the
// same source as the "Движения" tab, which only covers DOC_KASSA_MOVES
// transfers between registers. This is a live snapshot, not affected by
// the page's date range.
function CashBalancesCard({ balances, loading }) {
  if (!loading && (!balances || balances.length === 0)) return null;

  return (
    <div className="app-card overflow-hidden">
      <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
        <h3 className="text-sm font-semibold flex items-center gap-2">
          <Wallet size={15} className="text-[color:var(--color-primary)]" />
          Остатки по кассам
        </h3>
        {/* Блок стоит выше выбора периода и от него не зависит — без
            этой оговорки остатки читаются как отфильтрованные, и цифра
            не сходится с показателями ниже. */}
        <p className="mt-0.5 text-xs text-[color:var(--color-text-faint)]">
          На текущий момент — не зависят от выбранного периода
        </p>
      </div>
      <div className="p-3">
        {loading ? <SkeletonTable rows={4} /> : (
          <ResponsiveTable
            data={balances}
            keyFn={(b) => b.kassa_id}
            emptyText="Движений за период нет" emptyHint="Попробуйте расширить даты или снять фильтры."
            columns={[
              { label: 'Касса', primary: true, render: (b) => b.name || b.kassa_id },
              { label: 'Остаток', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold',
                render: (b) => <span className={b.balance < 0 ? 'text-red-500' : ''}>{fmtMoney(b.balance)}</span> },
            ]}
          />
        )}
      </div>
    </div>
  );
}

// ── Daily opening/closing balances ────────────────────────────────

const fmtDayLabel = (iso) => {
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return `${d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit' })}, ${DAY_NAMES[d.getDay()]}`;
};
// Zero turnover renders muted rather than as "0,00 ₽" — a day of nothing
// should read as nothing at a glance, so the days that did move stand out.
const fmtTurnover = (v) =>
  !v ? <span className="text-[color:var(--color-muted-foreground)]">—</span> : fmtMoney(v);

// The documents behind one day. Инкассация is shown with its own badge
// because it's the one basis that moves cash sideways between registers
// rather than in or out of the business.
function DayEntries({ entries }) {
  if (!entries || entries.length === 0) {
    return (
      <div className="px-4 py-3 text-xs text-[color:var(--color-muted-foreground)]">
        За этот день в кассовой книге нет ни одной проводки.
      </div>
    );
  }
  return (
    <div className="divide-y divide-[color:var(--color-border)]">
      {entries.map((e) => {
        const inkass = e.basis_id === 93;
        const amount = e.debet || e.kredit;
        return (
          <div key={e.id} className="flex items-start gap-3 px-4 py-2 text-xs">
            <span className="tabular-nums text-[color:var(--color-muted-foreground)] w-10 shrink-0">{e.time || '—'}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className={`px-1.5 py-0.5 rounded-full font-medium ${
                  inkass ? 'bg-amber-100 text-amber-700' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                }`}>{e.basis_name || '—'}</span>
                {e.doc_num && <span className="font-mono text-[color:var(--color-muted-foreground)]">№{e.doc_num}</span>}
              </div>
              {e.basis_text && <div className="mt-0.5 break-words">{e.basis_text}</div>}
              {/* Направление перевода. Показывается только когда основание
                  пришло с документа перемещения и вытеснило его отсюда. */}
              {e.transfer_text && (
                <div className="mt-0.5 break-words text-[color:var(--color-muted-foreground)]">{e.transfer_text}</div>
              )}
            </div>
            <span className="text-[color:var(--color-muted-foreground)] shrink-0 hidden sm:inline max-w-[10rem] truncate">{e.user_name || '—'}</span>
            <span className={`tabular-nums font-medium shrink-0 ${e.debet ? 'text-green-600' : 'text-red-500'}`}>
              {e.debet ? '+' : '−'}{fmtMoney(amount)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DailyBalancesTable({ days, entriesByDate, expanded, onToggle, isMobile }) {
  if (isMobile) {
    return (
      <div className="space-y-3">
        {days.map((d) => {
          const open = expanded.has(d.date);
          return (
            <div key={d.date} className="border border-[color:var(--color-border)] rounded-[var(--ui-radius-card)] bg-[color:var(--color-table-bg)] overflow-hidden">
              <button type="button" onClick={() => onToggle(d.date)}
                className="w-full px-4 py-3 flex items-center justify-between gap-2 bg-[color:var(--color-table-header)] text-left">
                <span className="flex items-center gap-1.5 font-medium text-sm">
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                  {fmtDayLabel(d.date)}
                </span>
                <span className="tabular-nums font-semibold text-sm">{fmtMoney(d.closing)}</span>
              </button>
              <div className="px-4 py-2 space-y-1.5 text-sm">
                <div className="flex justify-between gap-2">
                  <span className="text-[color:var(--color-muted-foreground)]">На начало</span>
                  <span className="tabular-nums">{fmtMoney(d.opening)}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-[color:var(--color-muted-foreground)]">Приход</span>
                  <span className="tabular-nums text-green-600">{fmtTurnover(d.income)}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-[color:var(--color-muted-foreground)]">Расход</span>
                  <span className="tabular-nums text-red-500">{fmtTurnover(d.expense)}</span>
                </div>
                <div className="flex justify-between gap-2">
                  <span className="text-[color:var(--color-muted-foreground)]">Инкассация</span>
                  <span className="tabular-nums text-amber-600">{fmtTurnover(d.collection)}</span>
                </div>
              </div>
              {open && (
                <div className="border-t border-[color:var(--color-border)] bg-[color:var(--color-bg-secondary)]">
                  <DayEntries entries={entriesByDate.get(d.date)} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  const th = 'px-3 py-3 text-xs font-semibold uppercase tracking-wide';
  return (
    <div className="overflow-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
      <table className="min-w-max w-full text-sm bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
        <thead>
          <tr className="bg-[color:var(--color-table-header)]">
            <th className="px-3 py-3 w-8"></th>
            <th className={`${th} text-left`}>Дата</th>
            <th className={`${th} text-right`}>На начало</th>
            <th className={`${th} text-right`}>Приход</th>
            <th className={`${th} text-right`}>Расход</th>
            <th className={`${th} text-right`}>Инкассация</th>
            <th className={`${th} text-right`}>На конец</th>
          </tr>
        </thead>
        {days.map((d) => {
          const open = expanded.has(d.date);
          const quiet = d.entry_count === 0;
          return (
            <tbody key={d.date} className="border-t border-[color:var(--color-border)]">
              <tr
                onClick={() => onToggle(d.date)}
                className={`cursor-pointer hover:bg-[color:var(--color-bg-secondary)] ${open ? 'bg-[color:var(--color-bg-secondary)]' : ''}`}
              >
                <td className="px-3 py-2 text-[color:var(--color-muted-foreground)]">
                  {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                </td>
                <td className={`px-3 py-2 whitespace-nowrap ${quiet ? 'text-[color:var(--color-muted-foreground)]' : 'font-medium'}`}>
                  {fmtDayLabel(d.date)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{fmtMoney(d.opening)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-green-600">{fmtTurnover(d.income)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-red-500">{fmtTurnover(d.expense)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-amber-600">{fmtTurnover(d.collection)}</td>
                <td className="px-3 py-2 text-right tabular-nums font-semibold">{fmtMoney(d.closing)}</td>
              </tr>
              {open && (
                <tr>
                  <td colSpan={7} className="p-0 bg-[color:var(--color-bg-secondary)]">
                    <DayEntries entries={entriesByDate.get(d.date)} />
                  </td>
                </tr>
              )}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}


function CashDayHeatmap({ data, activeDay, onSelect }) {
  const max = Math.max(...data.map((d) => d.sum), 1);
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <ArrowUpDown size={15} className="text-[color:var(--color-primary)]" />
        Активность по дням недели
      </div>
      <div className="space-y-2.5">
        {data.map((d, i) => {
          const pct = max > 0 ? (d.sum / max) * 100 : 0;
          const isWeekend = d.day === 'Вс' || d.day === 'Сб';
          const isActive = activeDay === i;
          return (
            <button
              key={d.day}
              type="button"
              onClick={() => onSelect?.(i)}
              className={`flex items-center gap-3 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <div className="w-6 text-xs text-right text-[color:var(--color-muted-foreground)] shrink-0 font-medium">{d.day}</div>
              <div className="flex-1 h-6 rounded-lg bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div
                  className="h-full rounded-lg transition-all duration-500"
                  style={{ width: `${pct}%`, background: isWeekend ? 'var(--color-warning)' : 'var(--color-primary)', opacity: activeDay != null && !isActive ? 0.35 : 0.75 }}
                />
              </div>
              <div className="text-xs font-medium text-right shrink-0 whitespace-nowrap">{fmtMoneyShort(d.sum)}</div>
            </button>
          );
        })}
      </div>
      <div className="flex gap-4 mt-4 text-xs text-[color:var(--color-muted-foreground)]">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'var(--color-primary)' }} />
          Будни
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'var(--color-warning)' }} />
          Выходные
        </span>
      </div>
    </div>
  );
}

function BranchLeaderboard({ data, total, activeName, onSelect }) {
  const medals = ['🥇', '🥈', '🥉'];
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Building2 size={15} className="text-[color:var(--color-primary)]" />
        Рейтинг филиалов
      </div>
      <div className="space-y-4">
        {data.slice(0, 6).map(([name, { sum, count }], i) => {
          const pct = total > 0 ? (sum / total) * 100 : 0;
          const isActive = activeName === name;
          return (
            <button
              key={name}
              type="button"
              onClick={() => onSelect?.(name)}
              className={`block w-full text-left rounded-md -mx-1 px-1 py-1 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  {i < 3
                    ? <span className="text-base shrink-0">{medals[i]}</span>
                    : <span className="w-5 text-center text-xs font-bold text-[color:var(--color-muted-foreground)] shrink-0">{i + 1}</span>
                  }
                  <span className="text-sm font-medium truncate">{name}</span>
                </div>
                <div className="text-right shrink-0 ml-3">
                  <div className="text-sm font-bold text-[color:var(--color-primary)] whitespace-nowrap">{fmtMoneyShort(sum)}</div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)]">{count} зап.</div>
                </div>
              </div>
              <div className="h-1.5 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{ width: `${pct}%`, background: CHART_COLORS[i % CHART_COLORS.length] }}
                />
              </div>
            </button>
          );
        })}
        {data.length === 0 && (
          <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет данных</div>
        )}
      </div>
    </div>
  );
}

function CatDonut({ data, total, activeName, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
        Категории
        {activeName && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {activeName}</span>}
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 160, height: 160, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="sum"
                nameKey="name"
                innerRadius="50%"
                outerRadius="80%"
                paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onClick={(entry) => onSelect?.(entry.name)}
                cursor={onSelect ? 'pointer' : 'default'}
              >
                {data.map((entry, i) => (
                  <Cell
                    key={entry.name}
                    fill={CHART_COLORS[i % CHART_COLORS.length]}
                    opacity={activeName && activeName !== entry.name ? 0.35 : (hover === null || hover === i ? 1 : 0.4)}
                    stroke="none"
                  />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [fmtMoneyShort(v), 'Сумма']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0">
          {data.map((d, i) => {
            const pct = total > 0 ? (d.sum / total) * 100 : 0;
            const isActive = activeName === d.name;
            return (
              <button
                key={d.name}
                type="button"
                onClick={() => onSelect?.(d.name)}
                className={`flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
              >
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs">{d.name}</span>
                    <span className="text-xs font-semibold shrink-0">{pct.toFixed(1)}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: CHART_COLORS[i % CHART_COLORS.length] }} />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-xl p-3 text-sm">
      <div className="font-semibold mb-1 text-[color:var(--color-muted-foreground)]">{label}</div>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: p.color }} />
          <span>{fmtMoneyShort(p.value)}</span>
          <span className="text-[color:var(--color-muted-foreground)] text-xs">({p.payload.count} зап.)</span>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────
export default function CashMovements() {
  const { toast } = useToast();
  const { isMobile } = useViewport();
  const [rows, setRows]           = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]     = useState(false);
  const [dateFrom, setDateFrom]   = useState(isoMStart(0));
  const [dateTo, setDateTo]       = useState(isoToday());
  const [query, setQuery]         = useState('');
  const [searchOr, setSearchOr]   = useState(false);
  const [selDeps, setSelDeps]     = useState([]);
  const [selKassas, setSelKassas] = useState([]);
  const [selUsers, setSelUsers]   = useState([]);
  const [selCatFilters, setSelCatFilters] = useState([]);
  const [invalidOnly, setInvalidOnly]    = useState(false);
  const [sort, setSort]           = useState({ field: 'DK_DATE', dir: 'desc' });
  const [showCatManager, setShowCatManager] = useState(false);
  const [showBranchesManager, setShowBranchesManager] = useState(false);
  const [assignRecord, setAssignRecord]   = useState(null);
  const [createPayoutMove, setCreatePayoutMove] = useState(null);
  const [linkedPayoutRecord, setLinkedPayoutRecord] = useState(null);
  const [noPayoutOnly, setNoPayoutOnly]   = useState(false);
  const [selected, setSelected]   = useState(new Set());
  const [dayFilter, setDayFilter] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  // The range the loaded data actually corresponds to, as opposed to
  // whatever is currently typed into the date inputs — the "Остатки" tab
  // refetches off this so it doesn't fire a request per keystroke.
  const [appliedRange, setAppliedRange] = useState({ from: isoMStart(0), to: isoToday() });
  const [balances, setBalances]         = useState(null);
  const [balKassa, setBalKassa]         = useState(null);
  const [daily, setDaily]               = useState(null);
  const [dailyLoading, setDailyLoading] = useState(false);
  const [expandedDays, setExpandedDays] = useState(() => new Set());

  useEffect(() => {
    api.get('cash-moves/meta').then((r) => setCategories(r.data.categories || [])).catch(() => {});
    api.get('cash-moves/balances')
      .then((r) => setBalances(Array.isArray(r.data) ? r.data : []))
      .catch(() => setBalances([]));
    loadData(isoMStart(0), isoToday());
  }, []);

  async function loadData(from, to) {
    setLoading(true);
    setSelected(new Set());
    setAppliedRange({ from, to });
    try {
      const params = {};
      if (from) params.date_from = from;
      if (to)   params.date_to   = to;
      const res = await api.get('cash-moves/', { params });
      setRows(Array.isArray(res.data) ? res.data : []);
    } catch { toast('Ошибка загрузки данных', 'error'); }
    finally { setLoading(false); }
  }

  function applyRange(from, to) {
    setDateFrom(from); setDateTo(to);
    loadData(from, to);
  }
  function applyPreset(p) { applyRange(p.from(), p.to()); }
  function handleApply()  { applyRange(dateFrom, dateTo); }

  // Registers available in the daily report — the same six the balances
  // card shows, ordered by their numeric name prefix so the list doesn't
  // reshuffle as balances change.
  const registers = useMemo(
    () => [...(balances || [])].sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru')),
    [balances],
  );

  useEffect(() => {
    if (balKassa == null && registers.length) setBalKassa(registers[0].kassa_id);
  }, [registers, balKassa]);

  // «Всё время» clears both dates; the daily report needs a bounded range,
  // so fall back to the last DAILY_BALANCE_MAX_DAYS days and say so in the UI.
  const balTo   = appliedRange.to || isoToday();
  const balFrom = appliedRange.from || isoMinusDays(balTo, DAILY_BALANCE_MAX_DAYS - 1);

  useEffect(() => {
    if (activeTab !== 'balances' || balKassa == null) return undefined;
    let cancelled = false;
    setDailyLoading(true);
    api.get('cash-moves/daily-balances', { params: { kassa_id: balKassa, date_from: balFrom, date_to: balTo } })
      .then((r) => { if (!cancelled) { setDaily(r.data); setExpandedDays(new Set()); } })
      .catch(() => {
        if (cancelled) return;
        setDaily(null);
        toast('Не удалось загрузить остатки по кассе', 'error');
      })
      .finally(() => { if (!cancelled) setDailyLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, balKassa, balFrom, balTo]);

  const entriesByDate = useMemo(() => {
    const map = new Map();
    (daily?.entries || []).forEach((e) => {
      if (!map.has(e.date)) map.set(e.date, []);
      map.get(e.date).push(e);
    });
    return map;
  }, [daily]);

  function toggleDay(dateStr) {
    setExpandedDays((prev) => {
      const next = new Set(prev);
      next.has(dateStr) ? next.delete(dateStr) : next.add(dateStr);
      return next;
    });
  }

  function toggleSort(field) {
    setSort((prev) => prev.field === field ? { field, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { field, dir: 'asc' });
  }

  function toggleArr(setter, id) {
    setter((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  function toggleSelect(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function toggleSelectAll(ids) {
    setSelected((prev) => ids.every((id) => prev.has(id)) ? new Set() : new Set(ids));
  }

  function handlePayoutCreated(cashMoveId, payoutData) {
    setRows((prev) => prev.map((r) =>
      String(r.ID_KASSES_MOVE) === String(cashMoveId)
        ? { ...r, has_payout: true, linked_payout: payoutData || r.linked_payout }
        : r
    ));
  }

  async function handleUnlinkPayout(payoutId, cashMoveId) {
    const res = await api.delete(`payouts/${payoutId}/move-link`);
    setRows((prev) => prev.map((r) =>
      String(r.ID_KASSES_MOVE) === String(cashMoveId)
        ? { ...r, has_payout: false, linked_payout: null }
        : r
    ));
    return res;
  }

  async function handleAssign({ record_id, category, add_prefix }) {
    try {
      await api.post('cash-moves/assign', { record_id, category, add_prefix });
      toast('Категория назначена', 'success');
      if (add_prefix) {
        const res = await api.get('cash-moves/meta');
        setCategories(res.data.categories || []);
      }
      setRows((prev) => prev.map((r) =>
        String(r.ID_KASSES_MOVE) === String(record_id)
          ? { ...r, category, prefix_ok: true, manually_assigned: true }
          : r
      ));
    } catch { toast('Ошибка сохранения', 'error'); }
    setAssignRecord(null);
  }

  function exportCsv() {
    const header = ['Дата','Филиал','Откуда','Куда','Создатель','Категория','Основание','Сумма','Ручное назначение'];
    const csvRows = filtered.map((r) => [
      fmtDate(r.DK_DATE), r.dep_name, r.KASSA_KREDIT_NAME || '', r.KASSA_DEBET_NAME || '', r.user_name,
      r.category || '', r.BASIS || '', r.SUMM || 0, r.manually_assigned ? 'Да' : 'Нет',
    ]);
    const csv = [header, ...csvRows].map((row) => row.map((v) => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
    downloadCsv(csv, 'cash_moves.csv');
  }

  function downloadCsv(csv, filename) {
    const blob = new Blob(['﻿'+csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: filename }).click();
    URL.revokeObjectURL(url);
  }

  // The "Остатки" tab exports the day table it's showing, not the movement
  // list — same button, whatever is on screen.
  function exportBalancesCsv() {
    const header = ['Дата','На начало','Приход','Расход','Инкассация','На конец','Проводок'];
    const csvRows = (daily?.days || []).map((d) => [
      fmtDate(d.date), d.opening, d.income, d.expense, d.collection, d.closing, d.entry_count,
    ]);
    const csv = [header, ...csvRows].map((row) => row.map((v) => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
    const name = (daily?.kassa_name || balKassa || 'kassa').toString().replace(/[^\wА-Яа-яЁё-]+/g, '_');
    downloadCsv(csv, `cash_balances_${name}_${daily?.date_from}_${daily?.date_to}.csv`);
  }

  // ── Memos ──────────────────────────────────────────────────────
  const catNames = useMemo(() => (Array.isArray(categories) ? categories : []).map((c) => c.name), [categories]);
  const safeRows = useMemo(() => (Array.isArray(rows) ? rows : []), [rows]);

  const depOptions = useMemo(() => {
    const seen = new Map();
    safeRows.forEach((r) => { const k = String(r.DEP_SRC_ID ?? ''); if (!seen.has(k)) seen.set(k, r.dep_name); });
    return [...seen.entries()].map(([id, name]) => ({ id, name: name || id })).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
  }, [safeRows]);

  // Built from BOTH KASSA_KREDIT (source) and KASSA_DEBET (destination) —
  // "Филиал"/DEP_SRC_ID above only reliably tracks the salon side of a
  // normal инкассация out of a till; a reverse transfer (Основная →
  // salon, e.g. to top up/balance a till) doesn't show up there at all,
  // so this filter matches either side of the real register pair instead.
  const kassaOptions = useMemo(() => {
    const seen = new Map();
    safeRows.forEach((r) => {
      if (r.KASSA_KREDIT != null) seen.set(String(r.KASSA_KREDIT), r.KASSA_KREDIT_NAME);
      if (r.KASSA_DEBET != null) seen.set(String(r.KASSA_DEBET), r.KASSA_DEBET_NAME);
    });
    return [...seen.entries()].map(([id, name]) => ({ id, name: name || id })).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
  }, [safeRows]);

  const userOptions = useMemo(() => {
    const seen = new Map();
    safeRows.forEach((r) => { const k = String(r.OWN_USR_ID ?? ''); if (!seen.has(k)) seen.set(k, r.user_name); });
    return [...seen.entries()].map(([id, name]) => ({ id, name: name || id })).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
  }, [safeRows]);

  const filtered = useMemo(() => {
    let out = safeRows;
    if (selDeps.length)       out = out.filter((r) => selDeps.includes(String(r.DEP_SRC_ID ?? '')));
    if (selKassas.length)     out = out.filter((r) => selKassas.includes(String(r.KASSA_KREDIT ?? '')) || selKassas.includes(String(r.KASSA_DEBET ?? '')));
    if (selUsers.length)      out = out.filter((r) => selUsers.includes(String(r.OWN_USR_ID ?? '')));
    if (selCatFilters.length) out = out.filter((r) => selCatFilters.includes(r.category ?? '__invalid__'));
    if (invalidOnly)          out = out.filter((r) => !r.prefix_ok);
    if (noPayoutOnly)         out = out.filter((r) => !r.has_payout);
    if (dayFilter != null)    out = out.filter((r) => { const d = new Date(r.DK_DATE); return !isNaN(d) && d.getDay() === dayFilter; });
    if (query.trim()) {
      const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
      out = out.filter((r) => { const b = (r.BASIS || '').toLowerCase(); return searchOr ? terms.some((t) => b.includes(t)) : terms.every((t) => b.includes(t)); });
    }
    const mult = sort.dir === 'asc' ? 1 : -1;
    return [...out].sort((a, b) => {
      if (sort.field === 'DK_DATE')   return mult * (a.DK_DATE || '').localeCompare(b.DK_DATE || '');
      if (sort.field === 'SUMM')      return mult * ((Number(a.SUMM) || 0) - (Number(b.SUMM) || 0));
      if (sort.field === 'dep_name')  return mult * (a.dep_name  || '').localeCompare(b.dep_name  || '', 'ru');
      if (sort.field === 'user_name') return mult * (a.user_name || '').localeCompare(b.user_name || '', 'ru');
      if (sort.field === 'BASIS')     return mult * (a.BASIS     || '').localeCompare(b.BASIS     || '', 'ru');
      if (sort.field === 'category')  return mult * (a.category  || '').localeCompare(b.category  || '', 'ru');
      return 0;
    });
  }, [safeRows, selDeps, selKassas, selUsers, selCatFilters, invalidOnly, noPayoutOnly, dayFilter, query, searchOr, sort]);

  const filteredIds = useMemo(() => filtered.map((r) => r.ID_KASSES_MOVE), [filtered]);
  const allChecked  = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id));

  const breakdown = useMemo(() => {
    const map = Object.create(null);
    for (const r of filtered) {
      const cat = r.category ?? 'Без категории';
      if (!map[cat]) map[cat] = { count: 0, sum: 0 };
      map[cat].count++;
      map[cat].sum += Number(r.SUMM) || 0;
    }
    return Object.entries(Object.assign({}, map)).sort((a, b) => b[1].sum - a[1].sum);
  }, [filtered]);

  const salonBreakdown = useMemo(() => {
    const map = Object.create(null);
    for (const r of filtered) {
      const dep = r.dep_name || '— без филиала';
      if (!map[dep]) map[dep] = { count: 0, sum: 0 };
      map[dep].count++;
      map[dep].sum += Number(r.SUMM) || 0;
    }
    return Object.entries(Object.assign({}, map)).sort((a, b) => b[1].sum - a[1].sum);
  }, [filtered]);

  const timeData = useMemo(() => {
    const map = Object.create(null);
    filtered.forEach((r) => {
      const d = (r.DK_DATE || '').slice(0, 10);
      if (!d) return;
      if (!map[d]) map[d] = { date: d, sum: 0, count: 0 };
      map[d].sum += Number(r.SUMM) || 0;
      map[d].count++;
    });
    return Object.values(map)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((d) => ({ ...d, label: d.date.slice(5).replace('-', '.') }));
  }, [filtered]);

  const dayData = useMemo(() => {
    const map = Array.from({ length: 7 }, (_, i) => ({ day: DAY_NAMES[i], sum: 0, count: 0 }));
    filtered.forEach((r) => {
      if (!r.DK_DATE) return;
      const d = new Date(r.DK_DATE);
      if (!isNaN(d)) { map[d.getDay()].sum += Number(r.SUMM) || 0; map[d.getDay()].count++; }
    });
    return map;
  }, [filtered]);

  const donutData = useMemo(() => {
    const top  = breakdown.slice(0, 7);
    const rest = breakdown.slice(7);
    const data = top.map(([name, { sum }]) => ({ name, sum }));
    const restSum = rest.reduce((s, [, { sum }]) => s + sum, 0);
    if (restSum > 0) data.push({ name: 'Прочие', sum: restSum });
    return data;
  }, [breakdown]);

  const invalidCount  = useMemo(() => safeRows.filter((r) => !r.prefix_ok).length, [safeRows]);
  const noPayoutCount = useMemo(() => safeRows.filter((r) => !r.has_payout).length, [safeRows]);
  const totalSum      = useMemo(() => filtered.reduce((s, r) => s + (Number(r.SUMM)||0), 0), [filtered]);
  const withPayoutCnt = useMemo(() => filtered.filter((r) => r.has_payout).length, [filtered]);
  const selectedSum   = useMemo(() => filtered.filter((r) => selected.has(r.ID_KASSES_MOVE)).reduce((s, r) => s + (Number(r.SUMM)||0), 0), [filtered, selected]);
  const selectedCount = selected.size;

  // Chart-driven drill-down: clicking a chart segment applies the matching filter and jumps to the filtered list.
  function selectCategory(name) {
    setSelCatFilters((prev) => (prev.length === 1 && prev[0] === name ? [] : [name]));
    setActiveTab('movements');
  }
  function selectBranch(name) {
    const opt = depOptions.find((o) => o.name === name);
    if (!opt) return;
    setSelDeps((prev) => (prev.length === 1 && prev[0] === opt.id ? [] : [opt.id]));
    setActiveTab('movements');
  }
  function selectDay(i) {
    setDayFilter((prev) => (prev === i ? null : i));
    setActiveTab('movements');
  }
  const activeCategoryName = selCatFilters.length === 1 ? selCatFilters[0] : null;
  const activeBranchName = selDeps.length === 1 ? (depOptions.find((o) => o.id === selDeps[0])?.name ?? null) : null;

  const mainTabs = [
    { key: 'overview',   label: 'Обзор',    icon: <BarChart3 size={14} /> },
    { key: 'movements',  label: 'Движения', icon: <TrendingUp size={14} />, badge: filtered.length || undefined },
    { key: 'analytics',  label: 'Аналитика', icon: <Wallet size={14} /> },
    { key: 'balances',   label: 'Остатки',  icon: <CalendarDays size={14} /> },
  ];

  const onBalancesTab = activeTab === 'balances';
  const dailyDays = daily?.days || [];

  const thCls = 'px-3 py-3 text-xs font-semibold uppercase tracking-wide select-none cursor-pointer hover:text-[color:var(--color-primary)]';

  return (
    <div className="space-y-6 max-w-full pb-20">
      <TopProgressBar active={loading} />
      {/* Header */}
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex-1 min-w-0">
          <span className="ui-eyebrow mb-3">Период · {dateFrom} — {dateTo}</span>
          <h2 className="text-2xl font-semibold tracking-tight">Кассовые перемещения</h2>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={() => setShowBranchesManager(true)}
            className="btn flex items-center gap-1.5 border border-[color:var(--color-border)] px-2.5 py-1.5">
            <Building2 size={15} /><span className="hidden sm:inline">Филиалы</span>
          </button>
          <button onClick={() => setShowCatManager(true)}
            className="btn flex items-center gap-1.5 border border-[color:var(--color-border)] px-2.5 py-1.5">
            <Settings size={15} /><span className="hidden sm:inline">Категории</span>
          </button>
          <button
            onClick={onBalancesTab ? exportBalancesCsv : exportCsv}
            disabled={onBalancesTab ? (dailyLoading || dailyDays.length === 0) : (loading || filtered.length === 0)}
            className="btn flex items-center gap-1.5 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 px-2.5 py-1.5">
            <Download size={15} /><span className="hidden sm:inline">CSV</span>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {/* ── Обзор ─────────────────────────────────────────────── */}
      {activeTab === 'overview' && (
        <div className="space-y-5">
          {loading ? (
            // Заглушка держит сетку и высоту будущих карточек, поэтому
            // блок не подпрыгивает в момент появления данных — а
            // центрированный спиннер занимал одну строку вместо них.
            <SkeletonStats count={4} />
          ) : (
            <>
              <CashBalancesCard balances={balances} loading={balances === null} />

              {/* Date presets row */}
              <DateRangeBar
                dateFrom={dateFrom} dateTo={dateTo}
                setDateFrom={setDateFrom} setDateTo={setDateTo}
                onApply={applyRange} loading={loading}
              />

              {/* KPI hero */}
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard
                  label="Общая сумма"
                  value={fmtMoneyShort(totalSum)}
                  sub={`${filtered.length} записей`}
                  accent="var(--color-primary)"
                  icon={Wallet}
                />
                <KpiCard
                  label="С выплатой"
                  value={withPayoutCnt}
                  sub={filtered.length ? `${((withPayoutCnt/filtered.length)*100).toFixed(0)}% от всех` : '—'}
                  accent="var(--color-success)"
                  icon={CheckCircle}
                />
                <KpiCard
                  label="Без выплаты"
                  value={filtered.filter((r) => !r.has_payout).length}
                  sub="требуют привязки"
                  accent="var(--color-warning)"
                  icon={Unlink}
                />
                <KpiCard
                  label="Без категории"
                  value={filtered.filter((r) => !r.prefix_ok).length}
                  sub={invalidCount > 0 ? `всего в базе: ${invalidCount}` : 'всё размечено'}
                  accent="var(--color-danger)"
                  icon={AlertTriangle}
                />
              </div>

              {/* Area chart + Donut */}
              {timeData.length > 0 && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="app-card p-5 lg:col-span-2">
                    <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                      <TrendingUp size={15} className="text-[color:var(--color-primary)]" />
                      Динамика перемещений
                    </div>
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={timeData} margin={{ top: 5, right: 5, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="cashGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="var(--color-primary)" stopOpacity={0.35} />
                            <stop offset="95%" stopColor="var(--color-primary)" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                        <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} />
                        <YAxis tickFormatter={fmtMoneyShort} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} width={90} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area
                          type="monotone"
                          dataKey="sum"
                          stroke="var(--color-primary)"
                          strokeWidth={2}
                          fill="url(#cashGrad)"
                          dot={false}
                          activeDot={{ r: 4, strokeWidth: 0 }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                  <CatDonut data={donutData} total={totalSum} activeName={activeCategoryName} onSelect={selectCategory} />
                </div>
              )}

              {/* Branch leaderboard + Day heatmap */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <BranchLeaderboard data={salonBreakdown} total={totalSum} activeName={activeBranchName} onSelect={selectBranch} />
                <CashDayHeatmap data={dayData} activeDay={dayFilter} onSelect={selectDay} />
              </div>

              {/* Category bar chart */}
              {breakdown.length > 0 && (
                <div className="app-card p-5">
                  <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                    <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                    Суммы по категориям
                  </div>
                  <ResponsiveContainer width="100%" height={Math.max(150, breakdown.length * 36)}>
                    <BarChart
                      data={breakdown.map(([name, { sum, count }]) => ({ name, sum, count }))}
                      layout="vertical"
                      margin={{ top: 0, right: 12, bottom: 0, left: 0 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
                      <XAxis type="number" tickFormatter={fmtMoneyShort} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} />
                      <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} tickLine={false} width={130} />
                      <Tooltip formatter={(v, n, p) => [fmtMoneyShort(v), 'Сумма']} labelFormatter={(l) => l} />
                      <Bar dataKey="sum" radius={[0, 4, 4, 0]} onClick={(entry) => selectCategory(entry.name)} cursor="pointer">
                        {breakdown.map(([name], i) => (
                          <Cell key={name} fill={CHART_COLORS[i % CHART_COLORS.length]} opacity={activeCategoryName && activeCategoryName !== name ? 0.35 : 1} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Движения ──────────────────────────────────────────── */}
      {activeTab === 'movements' && (
        <div className="space-y-4">
          {dayFilter != null && (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-[color:var(--color-muted-foreground)]">Фильтр из графика:</span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                {DAY_NAMES[dayFilter]}
                <button onClick={() => setDayFilter(null)} className="hover:opacity-70"><X size={12} /></button>
              </span>
            </div>
          )}
          {/* Filters */}
          <div className="app-card p-4 space-y-4">
            <div className="flex flex-wrap gap-2">
              {DATE_PRESETS.map((p) => (
                <button key={p.label} onClick={() => applyPreset(p)}
                  className="px-3 py-1 rounded-full text-xs font-medium border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
                  {p.label}
                </button>
              ))}
            </div>
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3 sm:items-end">
              <div className="w-full sm:w-auto">
                <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата с</label>
                <input type="date" className="input w-full sm:w-auto" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div className="w-full sm:w-auto">
                <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата по</label>
                <input type="date" className="input w-full sm:w-auto" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <button onClick={handleApply} disabled={loading} className="btn btn--primary flex-1 sm:flex-initial">Применить</button>
                {(dateFrom || dateTo) && (
                  <button onClick={() => { setDateFrom(''); setDateTo(''); loadData('',''); }}
                    className="btn btn--secondary"><X size={14} /></button>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <div className="relative" style={{ maxWidth: 360, flex: 1 }}>
                <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
                <input className="input w-full" style={{ paddingLeft: '2.25rem' }} placeholder="Поиск по Основанию…"
                  value={query} onChange={(e) => setQuery(e.target.value)} />
                {query && <button onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2"><X size={14} /></button>}
              </div>
              <div className="flex items-center rounded-lg border border-[color:var(--color-border)] overflow-hidden text-xs font-medium shrink-0">
                <button onClick={() => setSearchOr(false)}
                  className={`px-2.5 py-1.5 transition-colors ${!searchOr ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-bg-secondary)]'}`}
                  title="Все слова должны встречаться">И</button>
                <button onClick={() => setSearchOr(true)}
                  className={`px-2.5 py-1.5 transition-colors ${searchOr ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-bg-secondary)]'}`}
                  title="Хотя бы одно слово">ИЛИ</button>
              </div>
            </div>
            {catNames.length > 0 && (
              <div>
                <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Категория</div>
                <div className="flex flex-wrap gap-1.5">
                  {catNames.map((name) => (
                    <button key={name} onClick={() => toggleArr(setSelCatFilters, name)}
                      className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                        selCatFilters.includes(name)
                          ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                          : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                      }`}>{name}</button>
                  ))}
                  <button onClick={() => toggleArr(setSelCatFilters, '__invalid__')}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      selCatFilters.includes('__invalid__')
                        ? 'bg-red-500 text-white border-red-500'
                        : 'border-[color:var(--color-border)] text-red-600 hover:border-red-400'
                    }`}>Без категории</button>
                  {selCatFilters.length > 0 && (
                    <button onClick={() => setSelCatFilters([])}
                      className="px-3 py-1 rounded-full text-xs border border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)] hover:border-[color:var(--color-danger)]">
                      <X size={11} className="inline" /> Сбросить
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-6">
              {depOptions.length > 0 && (
                <div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Филиал</div>
                  <div className="flex flex-wrap gap-1.5">
                    {depOptions.map(({ id, name }) => (
                      <button key={id} onClick={() => toggleArr(setSelDeps, id)}
                        className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                          selDeps.includes(id)
                            ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                            : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                        }`}>{name}</button>
                    ))}
                  </div>
                </div>
              )}
              {kassaOptions.length > 0 && (
                <div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
                    Касса
                    {selKassas.length > 0 && (
                      <button onClick={() => setSelKassas([])}
                        className="ml-2 text-[color:var(--color-primary)] hover:underline">
                        сбросить
                      </button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {kassaOptions.map(({ id, name }) => (
                      <button key={id} onClick={() => toggleArr(setSelKassas, id)}
                        className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                          selKassas.includes(id)
                            ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                            : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                        }`}>{name}</button>
                    ))}
                  </div>
                </div>
              )}
              {userOptions.length > 0 && (
                <div>
                  <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Создатель</div>
                  <div className="flex flex-wrap gap-1.5">
                    {userOptions.map(({ id, name }) => (
                      <button key={id} onClick={() => toggleArr(setSelUsers, id)}
                        className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                          selUsers.includes(id)
                            ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                            : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                        }`}>{name}</button>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-4">
              <label className="flex items-center gap-2 cursor-pointer w-fit">
                <input type="checkbox" className="w-4 h-4 rounded" checked={invalidOnly}
                  onChange={(e) => setInvalidOnly(e.target.checked)} />
                <span className="text-sm">Только без категории</span>
                {invalidCount > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
                    <AlertTriangle size={11} /> {invalidCount}
                  </span>
                )}
              </label>
              <label className="flex items-center gap-2 cursor-pointer w-fit">
                <input type="checkbox" className="w-4 h-4 rounded" checked={noPayoutOnly}
                  onChange={(e) => setNoPayoutOnly(e.target.checked)} />
                <span className="text-sm">Только без выплаты</span>
                {noPayoutCount > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
                    <Unlink size={11} /> {noPayoutCount}
                  </span>
                )}
              </label>
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div className="app-card p-4"><SkeletonTable rows={10} cols={8} /></div>
          ) : filtered.length === 0 ? (
            <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
              {safeRows.length === 0 ? 'Нет данных' : 'Нет записей по заданным фильтрам'}
            </div>
          ) : isMobile ? (
            <div className="space-y-3">
              {filtered.map((row) => (
                <div key={row.ID_KASSES_MOVE} className={`border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden ${!row.prefix_ok ? 'border-l-4 border-l-red-400' : row.manually_assigned ? 'border-l-4 border-l-amber-400' : 'border-[color:var(--color-border)]'}`}>
                  <div className="px-4 py-2.5 border-b bg-[color:var(--color-bg-secondary)] flex justify-between items-center gap-2">
                    <span className="text-sm font-medium text-[color:var(--color-muted-foreground)]">{fmtDate(row.DK_DATE)}</span>
                    <span className="text-base font-bold text-[color:var(--color-primary)]">{fmtMoney(row.SUMM)}</span>
                  </div>
                  <div className="px-4 py-3 space-y-2 text-sm">
                    <div className="flex justify-between gap-2">
                      <span className="text-[color:var(--color-muted-foreground)] shrink-0">Филиал</span>
                      <span className="text-right font-medium">{row.dep_name || '—'}</span>
                    </div>
                    <div className="flex justify-between gap-2">
                      <span className="text-[color:var(--color-muted-foreground)] shrink-0">Касса</span>
                      <span className="text-right font-medium">{row.KASSA_KREDIT_NAME || '—'} → {row.KASSA_DEBET_NAME || '—'}</span>
                    </div>
                    <div className="flex justify-between gap-2">
                      <span className="text-[color:var(--color-muted-foreground)] shrink-0">Создатель</span>
                      <span className="text-right">{row.user_name || '—'}</span>
                    </div>
                    <div className="flex justify-between items-center gap-2">
                      <span className="text-[color:var(--color-muted-foreground)] shrink-0">Категория</span>
                      {row.category ? (
                        <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                          row.manually_assigned ? 'bg-amber-100 text-amber-700' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                        }`}>{row.category}</span>
                      ) : (
                        <button onClick={() => setAssignRecord(row)}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-600 active:bg-red-200">
                          <Tag size={10} /> Назначить
                        </button>
                      )}
                    </div>
                    {row.BASIS && (
                      <div className="pt-1 border-t border-[color:var(--color-border)]">
                        <span className="text-xs text-[color:var(--color-muted-foreground)] block mb-0.5">Основание</span>
                        <span className="font-mono text-xs break-all leading-relaxed">{row.BASIS}</span>
                      </div>
                    )}
                  </div>
                  <div className="px-4 py-2 border-t border-[color:var(--color-border)] bg-[color:var(--color-bg-secondary)] flex items-center justify-between gap-2">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" className="w-4 h-4 rounded cursor-pointer"
                        checked={selected.has(row.ID_KASSES_MOVE)} onChange={() => toggleSelect(row.ID_KASSES_MOVE)} />
                    </label>
                    <div className="flex items-center gap-1">
                      {row.prefix_ok
                        ? <CheckCircle size={16} className={row.manually_assigned ? 'text-amber-500' : 'text-green-500'}
                            title={row.manually_assigned ? 'Назначено вручную' : 'Категория по правилу'} />
                        : <button onClick={() => setAssignRecord(row)} className="p-1.5 rounded-lg active:bg-red-100">
                            <AlertTriangle size={16} className="text-red-500" />
                          </button>
                      }
                      {row.has_payout
                        ? <button
                            onClick={() => row.linked_payout && setLinkedPayoutRecord({ move: row, payout: row.linked_payout })}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-100 text-green-700 active:bg-green-200">
                            <LinkIcon size={12} /> Выплата
                          </button>
                        : <button onClick={() => setCreatePayoutMove(row)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-100 text-amber-700 active:bg-amber-200">
                            <Unlink size={12} /> Привязать
                          </button>
                      }
                    </div>
                  </div>
                </div>
              ))}
              <div className="px-4 py-2.5 rounded-xl bg-[color:var(--color-table-header)] border border-[color:var(--color-border)] text-sm font-semibold flex justify-between">
                <span>Итого: {filtered.length} записей</span>
                <span className="text-[color:var(--color-primary)]">{fmtMoney(totalSum)}</span>
              </div>
            </div>
          ) : (
            <div className="overflow-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
              <table className="min-w-max w-full text-sm divide-y divide-[color:var(--color-border)] bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
                <thead>
                  <tr className="bg-[color:var(--color-table-header)]">
                    <th className="px-3 py-3 w-8">
                      <input type="checkbox" className="w-4 h-4 rounded cursor-pointer"
                        checked={allChecked} onChange={() => toggleSelectAll(filteredIds)} />
                    </th>
                    <th className="px-3 py-3 w-8" title="Статус категории"></th>
                    <th className="px-3 py-3 w-8" title="Привязанная выплата"></th>
                    <th className={`${thCls} text-left`} onClick={() => toggleSort('DK_DATE')}>
                      <span className="inline-flex items-center gap-1">Дата <SortIcon field="DK_DATE" sort={sort} /></span>
                    </th>
                    <th className={`${thCls} text-left`} onClick={() => toggleSort('dep_name')}>
                      <span className="inline-flex items-center gap-1">Филиал <SortIcon field="dep_name" sort={sort} /></span>
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">Касса</th>
                    <th className={`${thCls} text-left`} onClick={() => toggleSort('user_name')}>
                      <span className="inline-flex items-center gap-1">Создатель <SortIcon field="user_name" sort={sort} /></span>
                    </th>
                    <th className={`${thCls} text-left`} onClick={() => toggleSort('category')}>
                      <span className="inline-flex items-center gap-1">Категория <SortIcon field="category" sort={sort} /></span>
                    </th>
                    <th className={`${thCls} text-left`} onClick={() => toggleSort('BASIS')}>
                      <span className="inline-flex items-center gap-1">Основание <SortIcon field="BASIS" sort={sort} /></span>
                    </th>
                    <th className={`${thCls} text-right`} onClick={() => toggleSort('SUMM')}>
                      <span className="inline-flex items-center gap-1 justify-end">Сумма <SortIcon field="SUMM" sort={sort} /></span>
                    </th>
                    <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide">ID</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--color-border)]">
                  {filtered.map((row, i) => {
                    const isSelected = selected.has(row.ID_KASSES_MOVE);
                    return (
                      <tr key={row.ID_KASSES_MOVE ?? i}
                        className={`transition-colors hover:bg-[color:var(--color-table-row-hover)] ${
                          isSelected ? 'bg-[color:var(--color-primary)]/5' :
                          i % 2 !== 0 ? 'bg-[color:var(--color-table-row-alt)]' : ''
                        } ${!row.prefix_ok ? 'border-l-2 border-l-red-400' : row.manually_assigned ? 'border-l-2 border-l-amber-400' : ''}`}>
                        <td className="px-3 py-2.5">
                          <input type="checkbox" className="w-4 h-4 rounded cursor-pointer"
                            checked={isSelected} onChange={() => toggleSelect(row.ID_KASSES_MOVE)} />
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          {row.prefix_ok
                            ? <CheckCircle size={14} className={`mx-auto ${row.manually_assigned ? 'text-amber-500' : 'text-green-500'}`}
                                title={row.manually_assigned ? 'Назначено вручную' : 'Категория по правилу'} />
                            : <button onClick={() => setAssignRecord(row)} title="Назначить категорию"
                                className="p-0.5 rounded hover:bg-red-100 transition-colors">
                                <AlertTriangle size={14} className="text-red-500 mx-auto" />
                              </button>
                          }
                        </td>
                        <td className="px-3 py-2.5 text-center">
                          {row.has_payout
                            ? <button
                                onClick={() => row.linked_payout && setLinkedPayoutRecord({ move: row, payout: row.linked_payout })}
                                title="Выплата привязана"
                                className="p-0.5 rounded hover:bg-green-100 transition-colors">
                                <LinkIcon size={14} className="mx-auto text-green-500" />
                              </button>
                            : <button onClick={() => setCreatePayoutMove(row)}
                                title="Привязать выплату"
                                className="p-0.5 rounded hover:bg-amber-100 transition-colors">
                                <Unlink size={14} className="text-amber-500 mx-auto" />
                              </button>
                          }
                        </td>
                        <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(row.DK_DATE)}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap">{row.dep_name}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap text-xs">{row.KASSA_KREDIT_NAME || '—'} → {row.KASSA_DEBET_NAME || '—'}</td>
                        <td className="px-3 py-2.5 whitespace-nowrap">{row.user_name}</td>
                        <td className="px-3 py-2.5">
                          {row.category ? (
                            <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
                              row.manually_assigned
                                ? 'bg-amber-100 text-amber-700'
                                : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                            }`}>{row.category}</span>
                          ) : (
                            <button onClick={() => setAssignRecord(row)}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-600 hover:bg-red-200 transition-colors">
                              <Tag size={10} /> Назначить
                            </button>
                          )}
                        </td>
                        <td className="px-3 py-2.5 font-mono text-xs max-w-xs truncate" title={row.BASIS}>{row.BASIS || '—'}</td>
                        <td className="px-3 py-2.5 text-right whitespace-nowrap font-medium">{fmtMoney(row.SUMM)}</td>
                        <td className="px-3 py-2.5 text-xs text-[color:var(--color-muted-foreground)] font-mono">{row.ID_KASSES_MOVE}</td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot>
                  <tr className="bg-[color:var(--color-table-header)] font-semibold">
                    <td className="px-3 py-2.5" colSpan={9}>Итого: {filtered.length} записей</td>
                    <td className="px-3 py-2.5 text-right text-[color:var(--color-primary)]">{fmtMoney(totalSum)}</td>
                    <td className="px-3 py-2.5"></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Аналитика ─────────────────────────────────────────── */}
      {activeTab === 'analytics' && (
        <div className="space-y-4">
          {/* Category breakdown */}
          {!loading && breakdown.length > 0 && (
            <div className="app-card p-5">
              <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                Разбивка по категориям
              </div>
              <ResponsiveTable
                data={breakdown}
                keyFn={([cat]) => cat}
                emptyText="Движений за период нет" emptyHint="Попробуйте расширить даты или снять фильтры."
                columns={[
                  {
                    label: 'Категория',
                    primary: true,
                    render: ([cat]) => {
                      const invalid = cat === 'Без категории';
                      return (
                        <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${invalid ? 'bg-red-100 text-red-700' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'}`}>
                          {cat}
                        </span>
                      );
                    },
                  },
                  {
                    label: 'Кол-во',
                    render: ([, { count }]) => <span className="text-[color:var(--color-muted-foreground)]">{count}</span>,
                  },
                  {
                    label: 'Сумма',
                    render: ([, { sum }]) => <span className="font-medium">{fmtMoneyShort(sum)}</span>,
                  },
                  {
                    label: 'Доля',
                    render: ([cat, { sum }]) => {
                      const share = totalSum > 0 ? (sum / totalSum) * 100 : 0;
                      const invalid = cat === 'Без категории';
                      return (
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                            <div className={`h-full rounded-full ${invalid ? 'bg-red-400' : 'bg-[color:var(--color-primary)]'}`} style={{ width: `${share}%` }} />
                          </div>
                          <span className="text-xs text-[color:var(--color-muted-foreground)] w-9 text-right">{share.toFixed(1)}%</span>
                        </div>
                      );
                    },
                  },
                ]}
              />
            </div>
          )}

          {/* Salon breakdown */}
          {!loading && salonBreakdown.length > 0 && (
            <div className="app-card p-5">
              <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                <Building2 size={15} className="text-[color:var(--color-primary)]" />
                Разбивка по филиалам
              </div>
              <ResponsiveTable
                data={salonBreakdown}
                keyFn={([dep]) => dep}
                emptyText="Движений за период нет" emptyHint="Попробуйте расширить даты или снять фильтры."
                columns={[
                  {
                    label: 'Филиал',
                    primary: true,
                    render: ([dep]) => {
                      const unknown = dep === '— без филиала';
                      return (
                        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${unknown ? 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'}`}>
                          {dep}
                        </span>
                      );
                    },
                  },
                  {
                    label: 'Кол-во',
                    render: ([, { count }]) => <span className="text-[color:var(--color-muted-foreground)]">{count}</span>,
                  },
                  {
                    label: 'Сумма',
                    render: ([, { sum }]) => <span className="font-medium">{fmtMoneyShort(sum)}</span>,
                  },
                  {
                    label: 'Доля',
                    render: ([, { sum }]) => {
                      const share = totalSum > 0 ? (sum / totalSum) * 100 : 0;
                      return (
                        <div className="flex items-center justify-end gap-2">
                          <div className="w-16 h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                            <div className="h-full rounded-full bg-[color:var(--color-primary)]" style={{ width: `${share}%` }} />
                          </div>
                          <span className="text-xs text-[color:var(--color-muted-foreground)] w-9 text-right">{share.toFixed(1)}%</span>
                        </div>
                      );
                    },
                  },
                ]}
              />
            </div>
          )}

          {loading && (
            <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
              <RefreshCw size={24} className="animate-spin mx-auto mb-2" />
              Загрузка…
            </div>
          )}
        </div>
      )}

      {/* ── Остатки ───────────────────────────────────────────── */}
      {onBalancesTab && (
        <div className="space-y-4">
          {/* Register picker */}
          <div className="flex flex-wrap gap-2 items-center">
            {registers.map((r) => (
              <button key={r.kassa_id} onClick={() => setBalKassa(r.kassa_id)}
                className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                  balKassa === r.kassa_id
                    ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                    : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)]'
                }`}>
                {r.name}
              </button>
            ))}
            {registers.length === 0 && (
              <span className="text-xs text-[color:var(--color-muted-foreground)]">Список касс недоступен</span>
            )}
          </div>

          <DateRangeBar
            dateFrom={dateFrom} dateTo={dateTo}
            setDateFrom={setDateFrom} setDateTo={setDateTo}
            onApply={applyRange} loading={dailyLoading}
          />

          {(daily?.clamped || (!appliedRange.from && daily)) && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg text-xs bg-amber-50 text-amber-800 border border-amber-200">
              <Info size={14} className="shrink-0 mt-0.5" />
              <span>
                Период ограничен последними {DAILY_BALANCE_MAX_DAYS} днями: показано
                с {fmtDate(daily.date_from)} по {fmtDate(daily.date_to)}.
              </span>
            </div>
          )}

          {dailyLoading ? (
            <div className="app-card p-4"><SkeletonTable rows={8} /></div>
          ) : dailyDays.length === 0 ? (
            <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
              Нет данных за выбранный период.
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <KpiCard label="На начало периода" value={fmtMoneyShort(daily.opening)}
                  sub={fmtDate(daily.date_from)} accent="var(--color-text-muted)" icon={Wallet} />
                <KpiCard label="Приход за период"
                  value={fmtMoneyShort(dailyDays.reduce((s, d) => s + d.income, 0))}
                  sub="без инкассации" accent="var(--color-success)" icon={TrendingUp} />
                <KpiCard label="Инкассация за период"
                  value={fmtMoneyShort(dailyDays.reduce((s, d) => s + d.collection, 0))}
                  sub="сдано в «Основную»" accent="var(--color-warning)" icon={ArrowUpDown} />
                <KpiCard label="На конец периода" value={fmtMoneyShort(daily.closing)}
                  sub={fmtDate(daily.date_to)} accent="var(--color-primary)" icon={Wallet} />
              </div>

              <div className="text-xs text-[color:var(--color-muted-foreground)]">
                Нажмите на день, чтобы увидеть проводки. «Инкассация» показана нетто:
                отрицательное значение — пополнение кассы из «Основной».
              </div>

              <DailyBalancesTable
                days={dailyDays}
                entriesByDate={entriesByDate}
                expanded={expandedDays}
                onToggle={toggleDay}
                isMobile={isMobile}
              />
            </>
          )}
        </div>
      )}

      {/* Floating selection bar */}
      {selectedCount > 0 && (
        <div className="fixed bottom-[calc(1.5rem+env(safe-area-inset-bottom))] left-1/2 -translate-x-1/2 z-50 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 max-w-[calc(100vw-1rem)] px-5 py-3 rounded-2xl shadow-2xl bg-[color:var(--color-sidebar)] text-[color:var(--color-sidebar-foreground)] border border-[color:var(--color-sidebar-border)]">
          <span className="text-sm font-medium">Выбрано: <span className="font-bold">{selectedCount}</span></span>
          <span className="w-px h-5 bg-[color:var(--color-sidebar-border)]" />
          <span className="text-sm">Сумма: <span className="font-bold text-[color:var(--color-sidebar-primary-foreground)]">{fmtMoney(selectedSum)}</span></span>
          <button onClick={() => setSelected(new Set())} className="ml-2 p-1 rounded-full hover:bg-white/10 transition-colors"><X size={16} /></button>
        </div>
      )}

      {/* Modals */}
      {showBranchesManager && (
        <MappingManager
          title="Филиалы (ID → название)"
          icon={Building2}
          endpoint="branches"
          onClose={() => setShowBranchesManager(false)}
          onChanged={() => loadData(dateFrom, dateTo)}
        />
      )}
      {showCatManager && (
        <CategoryManager
          categories={categories}
          onClose={() => setShowCatManager(false)}
          onChanged={(updated) => setCategories(updated)}
        />
      )}
      {assignRecord && (
        <AssignModal
          record={assignRecord}
          categories={categories}
          onSave={handleAssign}
          onClose={() => setAssignRecord(null)}
        />
      )}
      {createPayoutMove && (
        <CreatePayoutModal
          move={createPayoutMove}
          onClose={() => setCreatePayoutMove(null)}
          onCreated={handlePayoutCreated}
        />
      )}
      {linkedPayoutRecord && (
        <LinkedPayoutModal
          payout={linkedPayoutRecord.payout}
          onUnlink={() => handleUnlinkPayout(linkedPayoutRecord.payout.id, linkedPayoutRecord.move.ID_KASSES_MOVE)}
          onClose={() => setLinkedPayoutRecord(null)}
        />
      )}
    </div>
  );
}
