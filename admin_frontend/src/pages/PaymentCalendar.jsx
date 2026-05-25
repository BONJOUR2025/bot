import { useEffect, useState, useCallback, useRef } from 'react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MONTH_NAMES = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];
const DAY_NAMES = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

function fmt(n) {
  return Number(n ?? 0).toLocaleString('ru-RU', { minimumFractionDigits: 0 });
}

function statusColor(status, dom, today, year, month) {
  if (status === 'paid') return 'bg-green-100 text-green-800 border-green-200';
  if (status === 'skipped') return 'bg-gray-100 text-gray-500 border-gray-200';
  const due = new Date(year, month, dom);
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (due < t) return 'bg-red-100 text-red-800 border-red-200';
  const diff = (due - t) / 86400000;
  if (diff <= 3) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  return 'bg-white text-gray-700 border-gray-200';
}

function dotColor(records, day) {
  const today = new Date();
  for (const r of records) {
    const dom = r.schedule?.day_of_month;
    if (dom !== day) continue;
    if (r.status === 'paid') return 'bg-green-500';
    if (r.status === 'skipped') return 'bg-gray-400';
    const due = new Date(today.getFullYear(), today.getMonth(), dom);
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (due < t) return 'bg-red-500';
    const diff = (due - t) / 86400000;
    if (diff <= 3) return 'bg-yellow-400';
    return 'bg-blue-400';
  }
  return null;
}

function buildCalendarWeeks(year, month) {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startDow = (firstDay.getDay() + 6) % 7;
  const weeks = [];
  let week = Array(startDow).fill(null);
  for (let d = 1; d <= lastDay.getDate(); d++) {
    week.push(d);
    if (week.length === 7) { weeks.push(week); week = []; }
  }
  if (week.length) weeks.push([...week, ...Array(7 - week.length).fill(null)]);
  return weeks;
}

// ── Objects multi-select with salons + custom input ───────────────────────────

function ObjectsSelect({ value, onChange, salons }) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const containerRef = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (containerRef.current && !containerRef.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const selected = value || [];

  function toggle(name) {
    if (selected.includes(name)) onChange(selected.filter(v => v !== name));
    else onChange([...selected, name]);
  }

  function addCustom() {
    const trimmed = input.trim();
    if (!trimmed || selected.includes(trimmed)) { setInput(''); return; }
    onChange([...selected, trimmed]);
    setInput('');
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter') { e.preventDefault(); addCustom(); }
  }

  const filtered = salons.filter(s =>
    s.name.toLowerCase().includes(input.toLowerCase()) && !selected.includes(s.name)
  );

  return (
    <div ref={containerRef} className="relative">
      {/* Selected chips */}
      <div
        className="min-h-[38px] w-full border rounded-lg px-2 py-1.5 text-sm flex flex-wrap gap-1 cursor-text focus-within:ring-2 focus-within:ring-blue-500 bg-white"
        onClick={() => setOpen(true)}
      >
        {selected.map(v => (
          <span key={v} className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs">
            {v}
            <button
              type="button"
              onClick={e => { e.stopPropagation(); toggle(v); }}
              className="hover:text-blue-600 font-bold leading-none"
            >×</button>
          </span>
        ))}
        <input
          className="flex-1 min-w-[120px] outline-none bg-transparent text-sm"
          placeholder={selected.length === 0 ? 'Выберите или введите...' : ''}
          value={input}
          onChange={e => { setInput(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
        />
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {filtered.map(s => (
            <button
              key={s.id}
              type="button"
              onMouseDown={e => { e.preventDefault(); toggle(s.name); }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50"
            >
              {s.name}
            </button>
          ))}
          {input.trim() && !salons.some(s => s.name === input.trim()) && !selected.includes(input.trim()) && (
            <button
              type="button"
              onMouseDown={e => { e.preventDefault(); addCustom(); }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-green-50 text-green-700 border-t"
            >
              + Добавить «{input.trim()}»
            </button>
          )}
          {filtered.length === 0 && !input.trim() && (
            <div className="px-3 py-2 text-xs text-gray-400">Нет доступных салонов</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Schedule form modal ───────────────────────────────────────────────────────

function ScheduleModal({ initial, categories, salons, onSave, onClose }) {
  const [form, setForm] = useState(
    initial ?? {
      name: '', planned_amount: '', day_of_month: '', category: '',
      objects: [],
      responsible_name: '', responsible_tg_id: '', notify_days_before: 3, note: '',
    }
  );
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b sticky top-0 bg-white">
          <h2 className="font-semibold text-gray-800">
            {initial ? 'Редактировать платёж' : 'Новый платёж'}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Название *</label>
            <input className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.name} onChange={e => set('name', e.target.value)} placeholder="Интернет Ростелеком" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Сумма (₽) *</label>
              <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.planned_amount} onChange={e => set('planned_amount', e.target.value)} placeholder="5000" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">День месяца *</label>
              <input type="number" min={1} max={31} className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.day_of_month} onChange={e => set('day_of_month', e.target.value)} placeholder="10" />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Категория</label>
            <select className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.category} onChange={e => set('category', e.target.value)}>
              <option value="">— не указана —</option>
              {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Объект расхода</label>
            <ObjectsSelect
              value={form.objects}
              onChange={v => set('objects', v)}
              salons={salons}
            />
            <p className="text-[11px] text-gray-400 mt-1">Выберите салоны или введите произвольный текст</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Ответственный</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.responsible_name} onChange={e => set('responsible_name', e.target.value)} placeholder="Иванов И." />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">Telegram ID</label>
              <input className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={form.responsible_tg_id} onChange={e => set('responsible_tg_id', e.target.value)} placeholder="123456789" />
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Уведомить за (дней)</label>
            <input type="number" min={0} max={14} className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.notify_days_before} onChange={e => set('notify_days_before', +e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Примечание</label>
            <textarea rows={2} className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={form.note} onChange={e => set('note', e.target.value)} />
          </div>
        </div>
        <div className="p-4 border-t flex gap-2 justify-end sticky bottom-0 bg-white">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50">Отмена</button>
          <button onClick={() => onSave(form)}
            className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700">
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Pay modal ────────────────────────────────────────────────────────────────

function PayModal({ record, onPay, onClose }) {
  const planned = record.schedule?.planned_amount ?? 0;
  const [amount, setAmount] = useState(String(planned));
  const [comment, setComment] = useState('');

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-gray-800">Отметить как оплачено</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">✕</button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-gray-600">{record.schedule?.name}</p>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Фактическая сумма (₽)</label>
            <input type="number" className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={amount} onChange={e => setAmount(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">Комментарий</label>
            <input className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={comment} onChange={e => setComment(e.target.value)} placeholder="Необязательно" />
          </div>
        </div>
        <div className="p-4 border-t flex gap-2 justify-end">
          <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border border-gray-200 hover:bg-gray-50">Отмена</button>
          <button onClick={() => onPay(record.id, parseFloat(amount) || null, comment || null)}
            className="px-4 py-2 text-sm rounded-lg bg-green-600 text-white hover:bg-green-700">
            ✓ Оплачено
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Categories management panel ───────────────────────────────────────────────

function CategoriesPanel({ categories, onChanged }) {
  const { showToast } = useToast();
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editingName, setEditingName] = useState('');

  async function handleAdd() {
    const name = newName.trim();
    if (!name) return;
    try {
      await api.post('/payment-calendar/categories', { name });
      setNewName('');
      onChanged();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Ошибка', 'danger');
    }
  }

  async function handleSaveEdit(id) {
    const name = editingName.trim();
    if (!name) return;
    try {
      await api.patch(`/payment-calendar/categories/${id}`, { name });
      setEditingId(null);
      onChanged();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Ошибка', 'danger');
    }
  }

  async function handleDelete(id) {
    if (!confirm('Удалить категорию?')) return;
    try {
      await api.delete(`/payment-calendar/categories/${id}`);
      onChanged();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Ошибка', 'danger');
    }
  }

  return (
    <div className="bg-white border border-gray-100 rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-gray-700">Категории платежей</h3>
      <div className="space-y-1.5">
        {categories.map(cat => (
          <div key={cat.id} className="flex items-center gap-2">
            {editingId === cat.id ? (
              <>
                <input
                  autoFocus
                  className="flex-1 border rounded-lg px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  value={editingName}
                  onChange={e => setEditingName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveEdit(cat.id); if (e.key === 'Escape') setEditingId(null); }}
                />
                <button onClick={() => handleSaveEdit(cat.id)}
                  className="px-2 py-1 text-xs rounded-lg bg-blue-600 text-white hover:bg-blue-700">✓</button>
                <button onClick={() => setEditingId(null)}
                  className="px-2 py-1 text-xs rounded-lg border border-gray-200 hover:bg-gray-50">✕</button>
              </>
            ) : (
              <>
                <span className="flex-1 text-sm text-gray-700 px-2 py-1">{cat.name}</span>
                <button onClick={() => { setEditingId(cat.id); setEditingName(cat.name); }}
                  className="px-2 py-1 text-xs rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-500">✎</button>
                <button onClick={() => handleDelete(cat.id)}
                  className="px-2 py-1 text-xs rounded-lg border border-red-200 hover:bg-red-50 text-red-500">✕</button>
              </>
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-1 border-t">
        <input
          className="flex-1 border rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="Новая категория..."
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') handleAdd(); }}
        />
        <button onClick={handleAdd}
          className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700">
          + Добавить
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PaymentCalendar() {
  const { showToast } = useToast();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth());
  const [records, setRecords] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [categories, setCategories] = useState([]);
  const [salons, setSalons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scheduleModal, setScheduleModal] = useState(null);
  const [payModal, setPayModal] = useState(null);
  const [tab, setTab] = useState('calendar');
  const [highlightDay, setHighlightDay] = useState(null);

  const yearMonth = `${year}-${String(month + 1).padStart(2, '0')}`;

  const loadCategories = useCallback(async () => {
    try {
      const res = await api.get('/payment-calendar/categories');
      setCategories(res.data);
    } catch { /* ignore */ }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, schRes, catRes, salRes] = await Promise.all([
        api.get(`/payment-calendar/month/${yearMonth}`),
        api.get('/payment-calendar/schedules'),
        api.get('/payment-calendar/categories'),
        api.get('/salons/').catch(() => ({ data: [] })),
      ]);
      setRecords(recRes.data);
      setSchedules(schRes.data);
      setCategories(catRes.data);
      setSalons(salRes.data);
    } catch {
      showToast('Ошибка загрузки', 'danger');
    } finally {
      setLoading(false);
    }
  }, [yearMonth]);

  useEffect(() => { load(); }, [load]);

  function prevMonth() {
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
    setHighlightDay(null);
  }
  function nextMonth() {
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
    setHighlightDay(null);
  }

  const byDay = {};
  for (const r of records) {
    const dom = r.schedule?.day_of_month;
    if (!dom) continue;
    if (!byDay[dom]) byDay[dom] = [];
    byDay[dom].push(r);
  }
  const sortedDays = Object.keys(byDay).map(Number).sort((a, b) => a - b);

  const weeks = buildCalendarWeeks(year, month);

  const total = records.reduce((s, r) => s + (r.schedule?.planned_amount ?? 0), 0);
  const paidCount = records.filter(r => r.status === 'paid').length;
  const overdueCount = records.filter(r => {
    if (r.status !== 'pending') return false;
    const dom = r.schedule?.day_of_month;
    if (!dom) return false;
    const due = new Date(year, month, dom);
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    return due < t;
  }).length;

  async function handlePay(recordId, actualAmount, comment) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/pay`, { actual_amount: actualAmount, comment });
      setPayModal(null);
      showToast('Оплата отмечена', 'success');
      load();
    } catch { showToast('Ошибка', 'danger'); }
  }

  async function handleSkip(recordId) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/skip`);
      showToast('Платёж пропущен', 'success');
      load();
    } catch { showToast('Ошибка', 'danger'); }
  }

  async function handleReset(recordId) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/reset`);
      load();
    } catch { showToast('Ошибка', 'danger'); }
  }

  async function handleSaveSchedule(form) {
    try {
      const isEdit = scheduleModal !== 'new';
      const payload = {
        name: form.name,
        planned_amount: parseFloat(form.planned_amount) || 0,
        day_of_month: parseInt(form.day_of_month) || 1,
        category: form.category,
        objects: form.objects || [],
        responsible_name: form.responsible_name,
        responsible_tg_id: form.responsible_tg_id,
        notify_days_before: parseInt(form.notify_days_before) || 3,
        note: form.note,
      };
      if (isEdit) {
        await api.patch(`/payment-calendar/schedules/${form.id}`, payload);
        showToast('Платёж обновлён', 'success');
      } else {
        await api.post('/payment-calendar/schedules', payload);
        showToast('Платёж добавлен', 'success');
      }
      setScheduleModal(null);
      load();
    } catch (e) {
      showToast(e.response?.data?.detail || 'Ошибка', 'danger');
    }
  }

  async function handleDeleteSchedule(id) {
    if (!confirm('Удалить этот платёж?')) return;
    try {
      await api.delete(`/payment-calendar/schedules/${id}`);
      showToast('Удалено', 'success');
      load();
    } catch { showToast('Ошибка', 'danger'); }
  }

  async function handleToggleActive(sched) {
    try {
      await api.patch(`/payment-calendar/schedules/${sched.id}`, { is_active: !sched.is_active });
      load();
    } catch { showToast('Ошибка', 'danger'); }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-xl font-bold text-gray-800">Платежный календарь</h1>
        <button onClick={() => setScheduleModal('new')}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
          + Добавить платёж
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 p-1 rounded-lg w-fit">
        {[['calendar','Календарь'],['schedules','Расписание'],['settings','Настройки']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === k ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}>
            {l}
          </button>
        ))}
      </div>

      {/* ── Calendar tab ── */}
      {tab === 'calendar' && (
        <>
          <div className="flex items-center gap-4">
            <button onClick={prevMonth} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">‹</button>
            <h2 className="text-base font-semibold text-gray-800 min-w-[140px] text-center">
              {MONTH_NAMES[month]} {year}
            </h2>
            <button onClick={nextMonth} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">›</button>
          </div>

          {!loading && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Всего платежей', value: records.length, color: 'text-gray-800' },
                { label: 'Оплачено', value: paidCount, color: 'text-green-700' },
                { label: 'Просрочено', value: overdueCount, color: overdueCount > 0 ? 'text-red-700' : 'text-gray-400' },
                { label: 'Итого план', value: `${fmt(total)} ₽`, color: 'text-gray-800' },
              ].map(s => (
                <div key={s.label} className="bg-white border border-gray-100 rounded-xl p-3">
                  <p className="text-xs text-gray-500">{s.label}</p>
                  <p className={`text-xl font-bold ${s.color}`}>{s.value}</p>
                </div>
              ))}
            </div>
          )}

          <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
            <div className="grid grid-cols-7 bg-gray-50 border-b">
              {DAY_NAMES.map(d => (
                <div key={d} className="text-center text-xs font-medium text-gray-500 py-2">{d}</div>
              ))}
            </div>
            {loading ? (
              <div className="h-40 flex items-center justify-center text-gray-400 text-sm">Загрузка...</div>
            ) : (
              weeks.map((week, wi) => (
                <div key={wi} className="grid grid-cols-7 border-b last:border-b-0">
                  {week.map((day, di) => {
                    const dot = day ? dotColor(records.filter(r => r.schedule?.day_of_month === day), day) : null;
                    const isToday = day && year === today.getFullYear() && month === today.getMonth() && day === today.getDate();
                    const isHighlighted = day === highlightDay;
                    return (
                      <div key={di}
                        onClick={() => day && setHighlightDay(isHighlighted ? null : day)}
                        className={`min-h-[48px] sm:min-h-[60px] p-1.5 border-r last:border-r-0 flex flex-col items-center gap-1
                          ${day ? 'cursor-pointer hover:bg-blue-50' : ''}
                          ${isHighlighted ? 'bg-blue-50' : ''}
                          ${isToday ? 'bg-yellow-50' : ''}`}>
                        {day && (
                          <>
                            <span className={`text-xs font-medium w-6 h-6 flex items-center justify-center rounded-full
                              ${isToday ? 'bg-yellow-400 text-white' : 'text-gray-700'}`}>
                              {day}
                            </span>
                            {dot && <span className={`w-2 h-2 rounded-full ${dot}`} />}
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          <div className="flex flex-wrap gap-3 text-xs text-gray-500">
            {[['bg-green-500','Оплачено'],['bg-red-500','Просрочено'],['bg-yellow-400','Скоро (≤ 3 дней)'],['bg-blue-400','Предстоит'],['bg-gray-400','Пропущено']].map(([c,l]) => (
              <span key={l} className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-full ${c}`} />
                {l}
              </span>
            ))}
          </div>

          {!loading && (
            <div className="space-y-4">
              {sortedDays
                .filter(day => highlightDay === null || day === highlightDay)
                .map(day => (
                  <div key={day}>
                    <h3 className="text-sm font-semibold text-gray-500 mb-2">
                      {day} {MONTH_NAMES[month].toLowerCase()}
                    </h3>
                    <div className="space-y-2">
                      {byDay[day].map(r => {
                        const sc = r.schedule ?? {};
                        const cls = statusColor(r.status, day, today, year, month);
                        const objects = sc.objects || [];
                        return (
                          <div key={r.id} className={`border rounded-xl p-3 sm:p-4 ${cls}`}>
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-medium text-sm truncate">{sc.name}</span>
                                  {sc.category && (
                                    <span className="text-xs px-2 py-0.5 bg-white/60 rounded-full border border-current/20">
                                      {sc.category}
                                    </span>
                                  )}
                                  {objects.map(obj => (
                                    <span key={obj} className="text-xs px-2 py-0.5 bg-white/40 rounded-full border border-current/20">
                                      🏢 {obj}
                                    </span>
                                  ))}
                                </div>
                                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs opacity-75">
                                  <span>План: {fmt(sc.planned_amount)} ₽</span>
                                  {r.status === 'paid' && r.actual_amount != null && (
                                    <span>Факт: {fmt(r.actual_amount)} ₽</span>
                                  )}
                                  {sc.responsible_name && <span>👤 {sc.responsible_name}</span>}
                                  {r.paid_at && (
                                    <span>✓ {new Date(r.paid_at).toLocaleDateString('ru-RU')}</span>
                                  )}
                                  {r.comment && <span>💬 {r.comment}</span>}
                                </div>
                              </div>
                              <div className="flex items-center gap-1.5 shrink-0">
                                {r.status === 'pending' && (
                                  <>
                                    <button onClick={() => setPayModal(r)}
                                      className="px-2.5 py-1 text-xs rounded-lg bg-green-600 text-white hover:bg-green-700">
                                      Оплатить
                                    </button>
                                    <button onClick={() => handleSkip(r.id)}
                                      className="px-2.5 py-1 text-xs rounded-lg border border-current/30 hover:bg-white/40">
                                      Пропустить
                                    </button>
                                  </>
                                )}
                                {r.status !== 'pending' && (
                                  <button onClick={() => handleReset(r.id)}
                                    className="px-2.5 py-1 text-xs rounded-lg border border-current/30 hover:bg-white/40">
                                    Сбросить
                                  </button>
                                )}
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              {records.length === 0 && (
                <div className="text-center py-12 text-gray-400">
                  <p className="text-4xl mb-2">📅</p>
                  <p>Нет платежей за этот месяц</p>
                  <p className="text-sm mt-1">Добавьте регулярные платежи через кнопку выше</p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Schedules tab ── */}
      {tab === 'schedules' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-500">
            Список регулярных платежей. Каждый месяц для них автоматически создаются записи.
          </p>
          {schedules.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <p className="text-4xl mb-2">📋</p>
              <p>Нет платежей. Добавьте первый.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {schedules.map(s => {
                const objects = s.objects || [];
                return (
                  <div key={s.id} className={`bg-white border rounded-xl p-4 flex items-center justify-between gap-3
                    ${!s.is_active ? 'opacity-50' : ''}`}>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-sm">{s.name}</span>
                        {s.category && (
                          <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">{s.category}</span>
                        )}
                        {objects.map(obj => (
                          <span key={obj} className="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">🏢 {obj}</span>
                        ))}
                        {!s.is_active && (
                          <span className="text-xs px-2 py-0.5 bg-gray-200 text-gray-500 rounded-full">Неактивен</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-500 mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
                        <span>{fmt(s.planned_amount)} ₽</span>
                        <span>День: {s.day_of_month}</span>
                        {s.responsible_name && <span>👤 {s.responsible_name}</span>}
                        <span>Уведомить за {s.notify_days_before} д.</span>
                      </div>
                      {s.note && <p className="text-xs text-gray-400 mt-1 truncate">{s.note}</p>}
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <button onClick={() => handleToggleActive(s)}
                        className="px-2.5 py-1 text-xs rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600">
                        {s.is_active ? 'Откл' : 'Вкл'}
                      </button>
                      <button onClick={() => setScheduleModal(s)}
                        className="px-2.5 py-1 text-xs rounded-lg border border-gray-200 hover:bg-gray-50 text-gray-600">
                        ✎
                      </button>
                      <button onClick={() => handleDeleteSchedule(s.id)}
                        className="px-2.5 py-1 text-xs rounded-lg border border-red-200 hover:bg-red-50 text-red-600">
                        ✕
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Settings tab ── */}
      {tab === 'settings' && (
        <div className="space-y-4 max-w-md">
          <CategoriesPanel categories={categories} onChanged={loadCategories} />
        </div>
      )}

      {scheduleModal && (
        <ScheduleModal
          initial={scheduleModal === 'new' ? null : scheduleModal}
          categories={categories}
          salons={salons}
          onSave={handleSaveSchedule}
          onClose={() => setScheduleModal(null)}
        />
      )}
      {payModal && (
        <PayModal record={payModal} onPay={handlePay} onClose={() => setPayModal(null)} />
      )}
    </div>
  );
}
