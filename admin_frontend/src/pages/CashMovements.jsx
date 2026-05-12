import { useEffect, useState, useMemo, useCallback } from 'react';
import {
  Search, X, AlertTriangle, CheckCircle, Download,
  ChevronUp, ChevronDown, ChevronsUpDown,
  Tag, Settings, Plus, Trash2, Edit2, Check,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';

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

const DATE_PRESETS = [
  { label: 'Этот месяц',    from: () => isoMStart(0),  to: () => isoToday() },
  { label: 'Прошлый месяц', from: () => isoMStart(-1), to: () => isoMEnd(-1) },
  { label: 'Этот год',      from: () => isoYStart(),   to: () => isoToday() },
  { label: 'Всё время',     from: () => '',             to: () => '' },
];

// ── Sort icon ─────────────────────────────────────────────────────
function SortIcon({ field, sort }) {
  if (sort.field !== field) return <ChevronsUpDown size={13} className="opacity-30" />;
  return sort.dir === 'asc' ? <ChevronUp size={13} /> : <ChevronDown size={13} />;
}

// ── Category Manager modal ────────────────────────────────────────
function CategoryManager({ categories, onClose, onChanged }) {
  const { toast } = useToast();
  const [cats, setCats] = useState(categories);
  const [newCatName, setNewCatName] = useState('');
  const [editingCat, setEditingCat] = useState(null); // {name, newName, prefixes}
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
    <div className="modal-backdrop">
      <div className="modal-card max-w-2xl w-full max-h-[85vh] flex flex-col">
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
                    <button onClick={() => setEditingCat(null)} className="btn bg-gray-200 text-gray-700 hover:bg-gray-300">Отмена</button>
                  </div>
                  <div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Префиксы (начало BASIS):</div>
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
    <div className="modal-backdrop">
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
                Префикс для правила — записи с таким началом BASIS будут автоматически попадать в категорию
              </label>
              <input className="input w-full font-mono text-sm" value={addPrefix}
                onChange={(e) => setAddPrefix(e.target.value)} placeholder="Начало BASIS…" />
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={onClose}>Отмена</button>
          <button className="btn btn--primary" disabled={!selCat} onClick={handleSave}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────
export default function CashMovements() {
  const { toast } = useToast();
  const [rows, setRows]           = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading]     = useState(false);
  const [dateFrom, setDateFrom]   = useState(isoMStart(0));
  const [dateTo, setDateTo]       = useState(isoToday());
  const [query, setQuery]         = useState('');
  const [selDeps, setSelDeps]     = useState([]);
  const [selUsers, setSelUsers]   = useState([]);
  const [selCatFilters, setSelCatFilters] = useState([]);
  const [invalidOnly, setInvalidOnly]    = useState(false);
  const [sort, setSort]           = useState({ field: 'DK_DATE', dir: 'desc' });
  const [showBreakdown, setShowBreakdown] = useState(true);
  const [showCatManager, setShowCatManager] = useState(false);
  const [assignRecord, setAssignRecord]   = useState(null);
  const [selected, setSelected]   = useState(new Set()); // ID_KASSES_MOVE

  useEffect(() => {
    api.get('cash-moves/meta').then((r) => setCategories(r.data.categories || [])).catch(() => {});
    loadData(isoMStart(0), isoToday());
  }, []);

  async function loadData(from, to) {
    setLoading(true);
    setSelected(new Set());
    try {
      const params = {};
      if (from) params.date_from = from;
      if (to)   params.date_to   = to;
      const res = await api.get('cash-moves/', { params });
      setRows(res.data || []);
    } catch { toast('Ошибка загрузки данных', 'error'); }
    finally { setLoading(false); }
  }

  function applyPreset(p) {
    const from = p.from(), to = p.to();
    setDateFrom(from); setDateTo(to);
    loadData(from, to);
  }

  function handleApply() { loadData(dateFrom, dateTo); }

  function toggleSort(field) {
    setSort((prev) => prev.field === field ? { field, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { field, dir: 'asc' });
  }

  function toggleArr(setter, id) {
    setter((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  // row selection
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

  async function handleAssign({ record_id, category, add_prefix }) {
    try {
      await api.post('cash-moves/assign', { record_id, category, add_prefix });
      toast('Категория назначена', 'success');
      if (add_prefix) {
        const res = await api.get('cash-moves/meta');
        setCategories(res.data.categories || []);
      }
      // update local rows
      setRows((prev) => prev.map((r) =>
        String(r.ID_KASSES_MOVE) === String(record_id)
          ? { ...r, category, prefix_ok: true, manually_assigned: true }
          : r
      ));
    } catch { toast('Ошибка сохранения', 'error'); }
    setAssignRecord(null);
  }

  const catNames = useMemo(() => categories.map((c) => c.name), [categories]);

  const depOptions = useMemo(() => {
    const seen = new Map();
    rows.forEach((r) => { const k = String(r.DEP_SRC_ID ?? ''); if (!seen.has(k)) seen.set(k, r.dep_name); });
    return [...seen.entries()].map(([id, name]) => ({ id, name: name || id })).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
  }, [rows]);

  const userOptions = useMemo(() => {
    const seen = new Map();
    rows.forEach((r) => { const k = String(r.OWN_USR_ID ?? ''); if (!seen.has(k)) seen.set(k, r.user_name); });
    return [...seen.entries()].map(([id, name]) => ({ id, name: name || id })).sort((a, b) => (a.name || '').localeCompare(b.name || '', 'ru'));
  }, [rows]);

  const filtered = useMemo(() => {
    let out = rows;
    if (selDeps.length)       out = out.filter((r) => selDeps.includes(String(r.DEP_SRC_ID ?? '')));
    if (selUsers.length)      out = out.filter((r) => selUsers.includes(String(r.OWN_USR_ID ?? '')));
    if (selCatFilters.length) out = out.filter((r) => selCatFilters.includes(r.category ?? '__invalid__'));
    if (invalidOnly)          out = out.filter((r) => !r.prefix_ok);
    if (query.trim()) {
      const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
      out = out.filter((r) => { const b = (r.BASIS || '').toLowerCase(); return terms.every((t) => b.includes(t)); });
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
  }, [rows, selDeps, selUsers, selCatFilters, invalidOnly, query, sort]);

  const filteredIds = useMemo(() => filtered.map((r) => r.ID_KASSES_MOVE), [filtered]);
  const allChecked  = filteredIds.length > 0 && filteredIds.every((id) => selected.has(id));

  const breakdown = useMemo(() => {
    const map = {};
    for (const r of filtered) {
      const cat = r.category ?? '— без категории';
      if (!map[cat]) map[cat] = { count: 0, sum: 0 };
      map[cat].count++;
      map[cat].sum += Number(r.SUMM) || 0;
    }
    return Object.entries(map).sort((a, b) => b[1].sum - a[1].sum);
  }, [filtered]);

  const invalidCount  = useMemo(() => rows.filter((r) => !r.prefix_ok).length, [rows]);
  const totalSum      = useMemo(() => filtered.reduce((s, r) => s + (Number(r.SUMM)||0), 0), [filtered]);
  const selectedSum   = useMemo(() => filtered.filter((r) => selected.has(r.ID_KASSES_MOVE)).reduce((s, r) => s + (Number(r.SUMM)||0), 0), [filtered, selected]);
  const selectedCount = selected.size;

  function exportCsv() {
    const header = ['Дата','Филиал','Создатель','Категория','BASIS','Сумма','Ручное назначение'];
    const csvRows = filtered.map((r) => [
      fmtDate(r.DK_DATE), r.dep_name, r.user_name,
      r.category || '', r.BASIS || '', r.SUMM || 0, r.manually_assigned ? 'Да' : 'Нет',
    ]);
    const csv = [header, ...csvRows].map((row) => row.map((v) => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
    const blob = new Blob(['﻿'+csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: 'cash_moves.csv' }).click();
    URL.revokeObjectURL(url);
  }

  const thCls = 'px-3 py-3 text-xs font-semibold uppercase tracking-wide select-none cursor-pointer hover:text-[color:var(--color-primary)]';

  return (
    <div className="space-y-6 max-w-full pb-20">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">Кассовые перемещения</h2>
        <button onClick={() => setShowCatManager(true)}
          className="btn flex items-center gap-2 border border-[color:var(--color-border)]">
          <Settings size={15} /> Категории
        </button>
        <button onClick={exportCsv} disabled={loading || filtered.length === 0}
          className="btn flex items-center gap-2 bg-green-600 text-white hover:bg-green-700 disabled:opacity-50">
          <Download size={16} /> CSV
        </button>
      </div>

      {/* Filters */}
      <div className="app-card p-4 space-y-4">
        {/* Date presets */}
        <div className="flex flex-wrap gap-2">
          {DATE_PRESETS.map((p) => (
            <button key={p.label} onClick={() => applyPreset(p)}
              className="px-3 py-1 rounded-full text-xs font-medium border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
              {p.label}
            </button>
          ))}
        </div>

        {/* Date range */}
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата с</label>
            <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата по</label>
            <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <button onClick={handleApply} disabled={loading} className="btn btn--primary">Применить</button>
          {(dateFrom || dateTo) && (
            <button onClick={() => { setDateFrom(''); setDateTo(''); loadData('',''); }}
              className="btn bg-gray-200 text-gray-700 hover:bg-gray-300"><X size={14} /></button>
          )}
        </div>

        {/* BASIS search */}
        <div className="relative" style={{ maxWidth: 360 }}>
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input className="input w-full" style={{ paddingLeft: '2.25rem' }} placeholder="Поиск в BASIS (несколько слов через пробел)…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && <button onClick={() => setQuery('')} className="absolute right-3 top-1/2 -translate-y-1/2"><X size={14} /></button>}
        </div>

        {/* Category filter */}
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

        {/* Branch + user filters */}
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

        {/* Invalid only */}
        <label className="flex items-center gap-2 cursor-pointer w-fit">
          <input type="checkbox" className="w-4 h-4 rounded" checked={invalidOnly}
            onChange={(e) => setInvalidOnly(e.target.checked)} />
          <span className="text-sm">Только записи без категории</span>
          {invalidCount > 0 && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700">
              <AlertTriangle size={11} /> {invalidCount}
            </span>
          )}
        </label>
      </div>

      {/* Summary cards */}
      {!loading && rows.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Записей',       value: filtered.length },
            { label: 'Итого сумма',   value: fmtMoneyShort(totalSum), primary: true },
            { label: 'С категорией',  value: filtered.filter((r) => r.prefix_ok).length, green: true },
            { label: 'Без категории', value: filtered.filter((r) => !r.prefix_ok).length, red: true },
          ].map((s) => (
            <div key={s.label} className="app-card p-4 text-center">
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{s.label}</div>
              <div className={`text-lg font-semibold ${s.primary ? 'text-[color:var(--color-primary)]' : s.green ? 'text-green-600' : s.red ? 'text-red-600' : ''}`}>{s.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Category breakdown */}
      {!loading && breakdown.length > 0 && (
        <div className="app-card p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="font-medium text-sm">Разбивка по категориям</span>
            <button onClick={() => setShowBreakdown((v) => !v)}
              className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]">
              {showBreakdown ? 'Скрыть' : 'Показать'}
            </button>
          </div>
          {showBreakdown && (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-[color:var(--color-muted-foreground)] border-b border-[color:var(--color-border)]">
                    <th className="text-left pb-2 font-medium">Категория</th>
                    <th className="text-right pb-2 font-medium pr-6">Кол-во</th>
                    <th className="text-right pb-2 font-medium">Сумма</th>
                    <th className="text-right pb-2 pl-6 font-medium">Доля</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[color:var(--color-border)]">
                  {breakdown.map(([cat, { count, sum }]) => {
                    const share = totalSum > 0 ? (sum / totalSum) * 100 : 0;
                    const invalid = cat === '— без категории';
                    return (
                      <tr key={cat} className="hover:bg-[color:var(--color-bg-secondary)]">
                        <td className="py-1.5">
                          <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${invalid ? 'bg-red-100 text-red-700' : 'bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'}`}>
                            {cat}
                          </span>
                        </td>
                        <td className="py-1.5 text-right pr-6 text-[color:var(--color-muted-foreground)]">{count}</td>
                        <td className="py-1.5 text-right font-medium">{fmtMoneyShort(sum)}</td>
                        <td className="py-1.5 text-right pl-6">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                              <div className={`h-full rounded-full ${invalid ? 'bg-red-400' : 'bg-[color:var(--color-primary)]'}`} style={{ width: `${share}%` }} />
                            </div>
                            <span className="text-xs text-[color:var(--color-muted-foreground)] w-9 text-right">{share.toFixed(1)}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="app-card p-4"><SkeletonTable rows={10} cols={8} /></div>
      ) : filtered.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          {rows.length === 0 ? 'Нет данных' : 'Нет записей по заданным фильтрам'}
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
                <th className="px-3 py-3 w-8"></th>
                <th className={`${thCls} text-left`} onClick={() => toggleSort('DK_DATE')}>
                  <span className="inline-flex items-center gap-1">Дата <SortIcon field="DK_DATE" sort={sort} /></span>
                </th>
                <th className={`${thCls} text-left`} onClick={() => toggleSort('dep_name')}>
                  <span className="inline-flex items-center gap-1">Филиал <SortIcon field="dep_name" sort={sort} /></span>
                </th>
                <th className={`${thCls} text-left`} onClick={() => toggleSort('user_name')}>
                  <span className="inline-flex items-center gap-1">Создатель <SortIcon field="user_name" sort={sort} /></span>
                </th>
                <th className={`${thCls} text-left`} onClick={() => toggleSort('category')}>
                  <span className="inline-flex items-center gap-1">Категория <SortIcon field="category" sort={sort} /></span>
                </th>
                <th className={`${thCls} text-left`} onClick={() => toggleSort('BASIS')}>
                  <span className="inline-flex items-center gap-1">BASIS <SortIcon field="BASIS" sort={sort} /></span>
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
                    <td className="px-3 py-2.5 whitespace-nowrap">{fmtDate(row.DK_DATE)}</td>
                    <td className="px-3 py-2.5 whitespace-nowrap">{row.dep_name}</td>
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
                <td className="px-3 py-2.5" colSpan={7}>Итого: {filtered.length} записей</td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-primary)]">{fmtMoney(totalSum)}</td>
                <td className="px-3 py-2.5"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Floating selection bar */}
      {selectedCount > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 flex items-center gap-4 px-6 py-3 rounded-2xl shadow-2xl bg-[color:var(--color-sidebar)] text-[color:var(--color-sidebar-foreground)] border border-[color:var(--color-sidebar-border)]">
          <span className="text-sm font-medium">Выбрано: <span className="font-bold">{selectedCount}</span></span>
          <span className="w-px h-5 bg-[color:var(--color-sidebar-border)]" />
          <span className="text-sm">Сумма: <span className="font-bold text-[color:var(--color-sidebar-primary-foreground)]">{fmtMoney(selectedSum)}</span></span>
          <button onClick={() => setSelected(new Set())} className="ml-2 p-1 rounded-full hover:bg-white/10 transition-colors"><X size={16} /></button>
        </div>
      )}

      {/* Category Manager */}
      {showCatManager && (
        <CategoryManager
          categories={categories}
          onClose={() => setShowCatManager(false)}
          onChanged={(updated) => setCategories(updated)}
        />
      )}

      {/* Assign Modal */}
      {assignRecord && (
        <AssignModal
          record={assignRecord}
          categories={categories}
          onSave={handleAssign}
          onClose={() => setAssignRecord(null)}
        />
      )}
    </div>
  );
}
