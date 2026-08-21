import { useEffect, useState, useCallback, useRef } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { CHART_PALETTE as CAT_COLORS } from '../utils/chartPalette.js';

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
  if (status === 'skipped') return 'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] border-[color:var(--color-border)]';
  const due = new Date(year, month, dom);
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  if (due < t) return 'bg-red-100 text-red-800 border-red-200';
  const diff = (due - t) / 86400000;
  if (diff <= 3) return 'bg-yellow-100 text-yellow-800 border-yellow-200';
  return 'bg-[color:var(--color-surface)] text-[color:var(--color-text)] border-[color:var(--color-border)]';
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
  // Monday-first; getDay() returns 0=Sun
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

// ── Objects multiselect ───────────────────────────────────────────────────────

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
    onChange(selected.includes(name) ? selected.filter(v => v !== name) : [...selected, name]);
  }

  function addCustom() {
    const trimmed = input.trim();
    if (!trimmed || selected.includes(trimmed)) { setInput(''); return; }
    onChange([...selected, trimmed]);
    setInput('');
  }

  const filtered = salons.filter(s => s.name.toLowerCase().includes(input.toLowerCase()) && !selected.includes(s.name));

  return (
    <div ref={containerRef} className="relative">
      <div className="min-h-[38px] w-full border rounded-lg px-2 py-1.5 text-sm flex flex-wrap gap-1 cursor-text focus-within:ring-2 focus-within:ring-[color:var(--color-primary)] bg-[color:var(--color-surface)]"
        onClick={() => setOpen(true)}>
        {selected.map(v => (
          <span key={v} className="flex items-center gap-1 px-2 py-0.5 bg-blue-100 text-blue-800 rounded-full text-xs">
            {v}
            <button type="button" onClick={e => { e.stopPropagation(); toggle(v); }} className="hover:text-blue-600 font-bold">×</button>
          </span>
        ))}
        <input className="flex-1 min-w-[120px] outline-none bg-transparent text-sm"
          placeholder={selected.length === 0 ? 'Выберите или введите...' : ''}
          value={input} onChange={e => { setInput(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom(); } }} />
      </div>
      {open && (
        <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[color:var(--color-surface)] border rounded-lg shadow-lg max-h-52 overflow-y-auto">
          {filtered.map(s => (
            <button key={s.id} type="button" onMouseDown={e => { e.preventDefault(); toggle(s.name); }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-blue-50">{s.name}</button>
          ))}
          {input.trim() && !salons.some(s => s.name === input.trim()) && !selected.includes(input.trim()) && (
            <button type="button" onMouseDown={e => { e.preventDefault(); addCustom(); }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-green-50 text-green-700 border-t">
              + Добавить «{input.trim()}»</button>
          )}
          {filtered.length === 0 && !input.trim() && (
            <div className="px-3 py-2 text-xs text-[color:var(--color-text-faint)]">Нет доступных салонов</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Categories panel ──────────────────────────────────────────────────────────

function CategoriesPanel({ categories, onChanged }) {
  const { toast } = useToast();
  const [newName, setNewName] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editingName, setEditingName] = useState('');

  async function handleAdd() {
    const name = newName.trim(); if (!name) return;
    try { await api.post('/payment-calendar/categories', { name }); setNewName(''); onChanged(); }
    catch (e) { toast(e.response?.data?.detail || 'Ошибка', 'danger'); }
  }
  async function handleSaveEdit(id) {
    const name = editingName.trim(); if (!name) return;
    try { await api.patch(`/payment-calendar/categories/${id}`, { name }); setEditingId(null); onChanged(); }
    catch (e) { toast(e.response?.data?.detail || 'Ошибка', 'danger'); }
  }
  async function handleDelete(id) {
    if (!confirm('Удалить категорию?')) return;
    try { await api.delete(`/payment-calendar/categories/${id}`); onChanged(); }
    catch (e) { toast(e.response?.data?.detail || 'Ошибка', 'danger'); }
  }

  return (
    <div className="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-xl p-4 space-y-3">
      <h3 className="text-sm font-semibold text-[color:var(--color-text)]">Категории платежей</h3>
      <div className="space-y-1.5">
        {categories.map(cat => (
          <div key={cat.id} className="flex items-center gap-2">
            {editingId === cat.id ? (
              <>
                <input autoFocus className="input flex-1 text-sm py-1"
                  value={editingName} onChange={e => setEditingName(e.target.value)}
                  onKeyDown={e => { if (e.key==='Enter') handleSaveEdit(cat.id); if (e.key==='Escape') setEditingId(null); }} />
                <button onClick={() => handleSaveEdit(cat.id)} className="px-2 py-1 text-xs rounded-lg bg-blue-600 text-white">✓</button>
                <button onClick={() => setEditingId(null)} className="px-2 py-1 text-xs rounded-lg border border-[color:var(--color-border)]">✕</button>
              </>
            ) : (
              <>
                <span className="flex-1 text-sm text-[color:var(--color-text)] px-2 py-1">{cat.name}</span>
                <button onClick={() => { setEditingId(cat.id); setEditingName(cat.name); }}
                  className="px-2 py-1 text-xs rounded-lg border border-[color:var(--color-border)] text-[color:var(--color-text-muted)]">✎</button>
                <button onClick={() => handleDelete(cat.id)}
                  className="px-2 py-1 text-xs rounded-lg border border-red-200 text-red-500">✕</button>
              </>
            )}
          </div>
        ))}
      </div>
      <div className="flex gap-2 pt-1 border-t">
        <input className="input flex-1 text-sm py-1.5"
          placeholder="Новая категория..." value={newName} onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key==='Enter') handleAdd(); }} />
        <button onClick={handleAdd} className="px-3 py-1.5 text-sm rounded-lg bg-blue-600 text-white">+ Добавить</button>
      </div>
    </div>
  );
}

// ── Schedule form modal ───────────────────────────────────────────────────────

function ScheduleModal({ initial, onSave, onClose, categories, salons }) {
  const [form, setForm] = useState(
    initial ?? {
      name: '', planned_amount: '', day_of_month: '', category: '',
      responsible_name: '', responsible_tg_id: '', notify_days_before: 3, note: '',
      objects: [], seller: '', pay_from: '',
    }
  );
  const [invoiceFile, setInvoiceFile] = useState(null);
  const [notifyCashier, setNotifyCashier] = useState(false);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-[color:var(--color-surface)] rounded-xl shadow-xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-[color:var(--color-text)]">
            {initial ? 'Редактировать платёж' : 'Новый платёж'}
          </h2>
          <button onClick={onClose} className="text-[color:var(--color-text-faint)] hover:text-[color:var(--color-text-muted)] text-xl">✕</button>
        </div>
        <div className="p-4 space-y-3">
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Название *</label>
            <input className="input text-sm"
              value={form.name} onChange={e => set('name', e.target.value)} placeholder="Интернет Ростелеком" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Сумма (₽) *</label>
              <input type="number" className="input text-sm"
                value={form.planned_amount} onChange={e => set('planned_amount', e.target.value)} placeholder="5000" />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">День месяца *</label>
              <input type="number" min={1} max={31} className="input text-sm"
                value={form.day_of_month} onChange={e => set('day_of_month', e.target.value)} placeholder="10" />
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Категория</label>
            <select className="input text-sm"
              value={form.category} onChange={e => set('category', e.target.value)}>
              <option value="">— не указана —</option>
              {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
            </select>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Объект расхода</label>
            <ObjectsSelect value={form.objects} onChange={v => set('objects', v)} salons={salons} />
            <p className="text-[11px] text-[color:var(--color-text-faint)] mt-1">Выберите салоны или введите произвольный текст</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Ответственный</label>
              <input className="input text-sm"
                value={form.responsible_name} onChange={e => set('responsible_name', e.target.value)} placeholder="Иванов И." />
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Telegram ID</label>
              <input className="input text-sm"
                value={form.responsible_tg_id} onChange={e => set('responsible_tg_id', e.target.value)} placeholder="123456789" />
            </div>
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Уведомить за (дней)</label>
            <input type="number" min={0} max={14} className="input text-sm"
              value={form.notify_days_before} onChange={e => set('notify_days_before', +e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Примечание</label>
            <textarea rows={2} className="input text-sm"
              value={form.note} onChange={e => set('note', e.target.value)} />
          </div>

          <div className="border-t pt-3 mt-1 space-y-3">
            <p className="text-xs font-medium text-[color:var(--color-text-muted)]">Отправка счёта кассиру</p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Продавец</label>
                <input className="input text-sm"
                  value={form.seller} onChange={e => set('seller', e.target.value)} placeholder="ООО «Ромашка»" />
              </div>
              <div>
                <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Платим от</label>
                <input className="input text-sm"
                  value={form.pay_from} onChange={e => set('pay_from', e.target.value)} placeholder="ИП Иванов / Салон на Ленина" />
              </div>
            </div>
            <div>
              <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Файл счёта</label>
              <input type="file" accept="image/*,application/pdf"
                className="w-full text-sm border rounded-lg px-3 py-2 file:mr-2 file:text-xs file:rounded file:border-0 file:bg-[color:var(--color-bg-subtle)] file:px-2 file:py-1"
                onChange={e => setInvoiceFile(e.target.files?.[0] || null)} />
              {!invoiceFile && form.invoice_file_url && (
                <a href={form.invoice_file_url} target="_blank" rel="noreferrer"
                  className="text-[11px] text-blue-600 hover:underline mt-1 inline-block">Текущий файл счёта</a>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm text-[color:var(--color-text)] cursor-pointer">
              <input type="checkbox" checked={notifyCashier} onChange={e => setNotifyCashier(e.target.checked)} />
              Отправить кассиру в Telegram
            </label>
          </div>
        </div>
        <div className="p-4 border-t flex gap-2 justify-end">
          <button onClick={onClose} className="btn btn--secondary">Отмена</button>
          <button onClick={() => onSave(form, { invoiceFile, notifyCashier })}
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
      <div className="bg-[color:var(--color-surface)] rounded-xl shadow-xl w-full max-w-sm">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-[color:var(--color-text)]">Отметить как оплачено</h2>
          <button onClick={onClose} className="text-[color:var(--color-text-faint)] hover:text-[color:var(--color-text-muted)] text-xl">✕</button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-sm text-[color:var(--color-text-muted)]">{record.schedule?.name}</p>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Фактическая сумма (₽)</label>
            <input type="number" className="input text-sm"
              value={amount} onChange={e => setAmount(e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-text-muted)] mb-1 block">Комментарий</label>
            <input className="input text-sm"
              value={comment} onChange={e => setComment(e.target.value)} placeholder="Необязательно" />
          </div>
        </div>
        <div className="p-4 border-t flex gap-2 justify-end">
          <button onClick={onClose} className="btn btn--secondary">Отмена</button>
          <button onClick={() => onPay(record.id, parseFloat(amount) || null, comment || null)}
            className="px-4 py-2 text-sm rounded-lg bg-green-600 text-white hover:bg-green-700">
            ✓ Оплачено
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Payment detail card ───────────────────────────────────────────────────────

function DetailModal({ schedule, record, onClose, onEdit }) {
  const url = schedule.invoice_file_url;
  const isPdf = url && url.toLowerCase().endsWith('.pdf');

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-[color:var(--color-surface)] rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="font-semibold text-[color:var(--color-text)]">{schedule.name}</h2>
          <button onClick={onClose} className="text-[color:var(--color-text-faint)] hover:text-[color:var(--color-text-muted)] text-xl">✕</button>
        </div>
        <div className="p-4 space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-2 text-[color:var(--color-text)]">
            <div><span className="text-[color:var(--color-text-faint)]">Сумма:</span> {fmt(schedule.planned_amount)} ₽</div>
            <div><span className="text-[color:var(--color-text-faint)]">День месяца:</span> {schedule.day_of_month}</div>
            {schedule.category && <div><span className="text-[color:var(--color-text-faint)]">Категория:</span> {schedule.category}</div>}
            {record && <div><span className="text-[color:var(--color-text-faint)]">Статус:</span> {record.status === 'paid' ? 'Оплачено' : record.status === 'skipped' ? 'Пропущено' : 'Ожидает'}</div>}
            {schedule.seller && <div><span className="text-[color:var(--color-text-faint)]">Продавец:</span> {schedule.seller}</div>}
            {schedule.pay_from && <div><span className="text-[color:var(--color-text-faint)]">Платим от:</span> {schedule.pay_from}</div>}
            {schedule.responsible_name && <div><span className="text-[color:var(--color-text-faint)]">Ответственный:</span> {schedule.responsible_name}</div>}
            {(schedule.objects || []).length > 0 && <div className="col-span-2"><span className="text-[color:var(--color-text-faint)]">Объекты:</span> {schedule.objects.join(', ')}</div>}
          </div>
          {schedule.note && <p className="text-[color:var(--color-text-muted)] text-xs border-t pt-2">{schedule.note}</p>}

          <div className="border-t pt-3">
            <p className="text-xs font-medium text-[color:var(--color-text-muted)] mb-2">Счёт</p>
            {url ? (
              <>
                {isPdf ? (
                  <iframe src={url} className="w-full h-72 border rounded-lg" title="Счёт" />
                ) : (
                  <img src={url} alt="Счёт" className="max-h-72 rounded-lg border mx-auto" />
                )}
                <a href={url} target="_blank" rel="noreferrer"
                  className="text-xs text-blue-600 hover:underline mt-2 inline-block">Открыть в новой вкладке</a>
              </>
            ) : (
              <p className="text-xs text-[color:var(--color-text-faint)] italic">Файл счёта не приложен</p>
            )}
          </div>
        </div>
        <div className="p-4 border-t flex gap-2 justify-end">
          <button onClick={onClose} className="btn btn--secondary">Закрыть</button>
          <button onClick={onEdit} className="px-4 py-2 text-sm rounded-lg bg-blue-600 text-white hover:bg-blue-700">Редактировать</button>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PaymentCalendar() {
  const { toast } = useToast();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed
  const [records, setRecords] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [categories, setCategories] = useState([]);
  const [salons, setSalons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scheduleModal, setScheduleModal] = useState(null); // null | 'new' | {schedule obj}
  const [payModal, setPayModal] = useState(null);
  const [detailItem, setDetailItem] = useState(null); // { schedule, record? }
  const [tab, setTab] = useState('calendar'); // 'calendar' | 'schedules' | 'settings'
  const [highlightDay, setHighlightDay] = useState(null);
  const [categoryFilter, setCategoryFilter] = useState(null);

  const yearMonth = `${year}-${String(month + 1).padStart(2, '0')}`;

  const loadCategories = useCallback(async () => {
    try {
      const res = await api.get('/payment-calendar/categories');
      setCategories(res.data);
    } catch { /* silent */ }
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
      toast('Ошибка загрузки', 'danger');
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

  // Group records by day
  const byDay = {};
  for (const r of records) {
    const dom = r.schedule?.day_of_month;
    if (!dom) continue;
    if (!byDay[dom]) byDay[dom] = [];
    byDay[dom].push(r);
  }
  const sortedDays = Object.keys(byDay).map(Number).sort((a, b) => a - b);

  const weeks = buildCalendarWeeks(year, month);

  // Stats
  const total = records.reduce((s, r) => s + (r.schedule?.planned_amount ?? 0), 0);
  const paid = records.filter(r => r.status === 'paid').reduce((s, r) => s + (r.actual_amount ?? r.schedule?.planned_amount ?? 0), 0);
  const paidCount = records.filter(r => r.status === 'paid').length;
  const overdueCount = records.filter(r => {
    if (r.status !== 'pending') return false;
    const dom = r.schedule?.day_of_month;
    if (!dom) return false;
    const due = new Date(year, month, dom);
    const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    return due < t;
  }).length;

  const categoryData = (() => {
    const map = {};
    for (const s of schedules) {
      if (!s.is_active) continue;
      const cat = s.category || 'Без категории';
      map[cat] = (map[cat] || 0) + (Number(s.planned_amount) || 0);
    }
    return Object.entries(map)
      .map(([name, value], i) => ({ name, value, color: CAT_COLORS[i % CAT_COLORS.length] }))
      .filter((d) => d.value > 0)
      .sort((a, b) => b.value - a.value);
  })();
  const categoryTotal = categoryData.reduce((s, d) => s + d.value, 0);

  function selectCategory(name) {
    setCategoryFilter((prev) => (prev === name ? null : name));
    setTab('schedules');
  }

  async function handlePay(recordId, actualAmount, comment) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/pay`, { actual_amount: actualAmount, comment });
      setPayModal(null);
      toast('Оплата отмечена', 'success');
      load();
    } catch { toast('Ошибка', 'danger'); }
  }

  async function handleSkip(recordId) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/skip`);
      toast('Платёж пропущен', 'success');
      load();
    } catch { toast('Ошибка', 'danger'); }
  }

  async function handleReset(recordId) {
    try {
      await api.post(`/payment-calendar/records/${recordId}/reset`);
      load();
    } catch { toast('Ошибка', 'danger'); }
  }

  async function handleSaveSchedule(form, { invoiceFile, notifyCashier } = {}) {
    const isEdit = scheduleModal !== 'new';
    let scheduleId = form.id;
    try {
      const payload = {
        name: form.name,
        planned_amount: parseFloat(form.planned_amount) || 0,
        day_of_month: parseInt(form.day_of_month) || 1,
        category: form.category,
        responsible_name: form.responsible_name,
        responsible_tg_id: form.responsible_tg_id,
        notify_days_before: parseInt(form.notify_days_before) || 3,
        note: form.note,
        objects: form.objects || [],
        seller: form.seller || '',
        pay_from: form.pay_from || '',
      };
      if (isEdit) {
        await api.patch(`/payment-calendar/schedules/${form.id}`, payload);
        toast('Платёж обновлён', 'success');
      } else {
        const res = await api.post('/payment-calendar/schedules', payload);
        scheduleId = res.data.id;
        toast('Платёж добавлен', 'success');
      }
    } catch (e) {
      toast(e.response?.data?.detail || 'Ошибка', 'danger');
      return;
    }

    // Close & refresh right away — attaching the file / notifying the cashier
    // happens in the background and must not block the list from updating.
    setScheduleModal(null);
    load();

    if (scheduleId && (invoiceFile || notifyCashier)) {
      try {
        const fd = new FormData();
        if (invoiceFile) fd.append('invoice', invoiceFile);
        fd.append('notify', notifyCashier ? 'true' : 'false');
        const res = await api.post(`/payment-calendar/schedules/${scheduleId}/send-to-cashier`, fd);
        if (notifyCashier) {
          toast(res.data.ok ? 'Счёт отправлен кассиру' : 'Не удалось отправить кассиру в Telegram', res.data.ok ? 'success' : 'danger');
        } else if (invoiceFile) {
          toast('Файл счёта приложен', 'success');
        }
        load();
      } catch (e) {
        toast(e.response?.data?.detail || 'Ошибка отправки кассиру', 'danger');
      }
    }
  }

  async function handleDeleteSchedule(id) {
    if (!confirm('Удалить этот платёж?')) return;
    try {
      await api.delete(`/payment-calendar/schedules/${id}`);
      toast('Удалено', 'success');
      load();
    } catch { toast('Ошибка', 'danger'); }
  }

  async function handleToggleActive(sched) {
    try {
      await api.patch(`/payment-calendar/schedules/${sched.id}`, { is_active: !sched.is_active });
      load();
    } catch { toast('Ошибка', 'danger'); }
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <span className="ui-eyebrow mb-3">
            {schedules.length ? `Регулярных платежей: ${schedules.length}` : 'Платежи не заведены'}
          </span>
          <h1 className="text-xl font-bold text-[color:var(--color-text)]">Платежный календарь</h1>
        </div>
        <button onClick={() => setScheduleModal('new')}
          className="flex items-center gap-1.5 px-3 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700">
          + Добавить платёж
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-[color:var(--color-bg-subtle)] p-1 rounded-lg w-fit">
        {[['calendar','Календарь'],['schedules','Платежи'],['settings','Настройки']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === k ? 'bg-[color:var(--color-surface)] shadow text-[color:var(--color-text)]' : 'text-[color:var(--color-text-muted)] hover:text-[color:var(--color-text)]'}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === 'calendar' && (
        <>
          {/* Month navigation */}
          <div className="flex items-center gap-4">
            <button onClick={prevMonth} className="p-2 rounded-lg hover:bg-[color:var(--color-control-bg-hover)] text-[color:var(--color-text-muted)]">‹</button>
            <h2 className="text-base font-semibold text-[color:var(--color-text)] min-w-[140px] text-center">
              {MONTH_NAMES[month]} {year}
            </h2>
            <button onClick={nextMonth} className="p-2 rounded-lg hover:bg-[color:var(--color-control-bg-hover)] text-[color:var(--color-text-muted)]">›</button>
          </div>

          {/* Stats bar */}
          {!loading && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                // Цвет только там, где он что-то значит. «Просрочено»
                // краснеет лишь когда просрочка есть — ноль не должен
                // выглядеть тревожно; «Оплачено» зелёное как факт.
                { label: 'Всего платежей', value: records.length, color: 'text-[color:var(--color-text)]' },
                { label: 'Оплачено', value: paidCount, color: 'text-[color:var(--color-success)]' },
                {
                  label: 'Просрочено',
                  value: overdueCount,
                  color: overdueCount > 0
                    ? 'text-[color:var(--color-danger)]'
                    : 'text-[color:var(--color-text-faint)]',
                },
                { label: 'Итого план', value: `${fmt(total)} ₽`, color: 'text-[color:var(--color-text)]' },
              ].map(s => (
                <div key={s.label} className="ui-shell ui-shell--sm">
                  <div className="ui-core border border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-4">
                    <p className="ui-label">{s.label}</p>
                    <p className={`ui-metric !text-[1.5rem] mt-1.5 ${s.color}`}>{s.value}</p>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Category breakdown — click a slice to jump to filtered payments */}
          {!loading && categoryData.length > 0 && (
            <div className="app-card p-5">
              <div className="text-sm font-semibold mb-4 flex items-center gap-2 text-[color:var(--color-text)]">
                Структура расходов по категориям
              </div>
              <div className="flex flex-col sm:flex-row gap-4 items-center">
                <div style={{ width: 150, height: 150, flexShrink: 0 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={categoryData} dataKey="value" nameKey="name" innerRadius="50%" outerRadius="80%"
                        paddingAngle={2} onClick={(entry) => selectCategory(entry.name)} cursor="pointer">
                        {categoryData.map((d) => <Cell key={d.name} fill={d.color} stroke="none" />)}
                      </Pie>
                      <Tooltip formatter={(v) => [`${fmt(v)} ₽`, 'Сумма']} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex-1 space-y-2 min-w-0 w-full">
                  {categoryData.map((d) => {
                    const pct = categoryTotal > 0 ? (d.value / categoryTotal) * 100 : 0;
                    return (
                      <button key={d.name} type="button" onClick={() => selectCategory(d.name)}
                        className="flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer">
                        <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-1">
                            <span className="text-xs truncate">{d.name}</span>
                            <span className="text-xs font-semibold shrink-0">{fmt(d.value)} ₽ ({pct.toFixed(0)}%)</span>
                          </div>
                          <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${pct}%`, background: d.color }} />
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Calendar grid */}
          <div className="bg-[color:var(--color-surface)] border border-[color:var(--color-border)] rounded-xl overflow-hidden">
            <div className="grid grid-cols-7 bg-[color:var(--color-bg-subtle)] border-b">
              {DAY_NAMES.map(d => (
                <div key={d} className="text-center text-xs font-medium text-[color:var(--color-text-muted)] py-2">{d}</div>
              ))}
            </div>
            {loading ? (
              <div className="h-40 flex items-center justify-center text-[color:var(--color-text-faint)] text-sm">Загрузка...</div>
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
                              ${isToday ? 'bg-yellow-400 text-white' : 'text-[color:var(--color-text)]'}`}>
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

          {/* Legend */}
          <div className="flex flex-wrap gap-3 text-xs text-[color:var(--color-text-muted)]">
            {[['bg-green-500','Оплачено'],['bg-red-500','Просрочено'],['bg-yellow-400','Скоро (≤ 3 дней)'],['bg-blue-400','Предстоит'],['bg-gray-400','Пропущено']].map(([c,l]) => (
              <span key={l} className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-full ${c}`} />
                {l}
              </span>
            ))}
          </div>

          {/* List */}
          {loading ? null : (
            <div className="space-y-4">
              {sortedDays
                .filter(day => highlightDay === null || day === highlightDay)
                .map(day => (
                  <div key={day}>
                    <h3 className="text-sm font-semibold text-[color:var(--color-text-muted)] mb-2">
                      {day} {MONTH_NAMES[month].toLowerCase()}
                    </h3>
                    <div className="space-y-2">
                      {byDay[day].map(r => {
                        const sc = r.schedule ?? {};
                        const cls = statusColor(r.status, day, today, year, month);
                        return (
                          <div key={r.id} onClick={() => setDetailItem({ schedule: sc, record: r })}
                            className={`border rounded-xl p-3 sm:p-4 cursor-pointer hover:brightness-95 transition-[filter] ${cls}`}>
                            <div className="flex items-start justify-between gap-2">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-medium text-sm truncate">{sc.name}</span>
                                  {sc.category && (
                                    <span className="text-xs px-2 py-0.5 bg-white/60 rounded-full border border-current/20">
                                      {sc.category}
                                    </span>
                                  )}
                                  {sc.invoice_file_url && (
                                    <span className="text-xs px-2 py-0.5 bg-white/60 rounded-full border border-current/20">📎</span>
                                  )}
                                  {(sc.objects || []).map(obj => (
                                    <span key={obj} className="text-xs px-2 py-0.5 bg-white/40 rounded-full border border-current/20">🏢 {obj}</span>
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
                              <div className="flex items-center gap-1.5 shrink-0" onClick={e => e.stopPropagation()}>
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
                <div className="text-center py-12 text-[color:var(--color-text-faint)]">
                  <p className="text-4xl mb-2">📅</p>
                  <p>Нет платежей за этот месяц</p>
                  <p className="text-sm mt-1">Добавьте регулярные платежи через кнопку выше</p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {tab === 'schedules' && (
        <div className="space-y-3">
          <p className="text-sm text-[color:var(--color-text-muted)]">
            Список регулярных платежей. Каждый месяц для них автоматически создаются записи.
          </p>
          {categoryFilter && (
            <div className="flex items-center gap-2 text-xs">
              <span className="text-[color:var(--color-muted-foreground)]">Фильтр по категории:</span>
              <button className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium" onClick={() => setCategoryFilter(null)}>
                {categoryFilter} ✕
              </button>
            </div>
          )}
          {(categoryFilter ? schedules.filter((s) => (s.category || 'Без категории') === categoryFilter) : schedules).length === 0 ? (
            <div className="text-center py-12 text-[color:var(--color-text-faint)]">
              <p className="text-4xl mb-2">📋</p>
              <p>Нет платежей. Добавьте первый.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {(categoryFilter ? schedules.filter((s) => (s.category || 'Без категории') === categoryFilter) : schedules).map(s => (
                <div key={s.id} onClick={() => setDetailItem({ schedule: s })}
                  className={`bg-[color:var(--color-surface)] border rounded-xl p-4 flex items-center justify-between gap-3 cursor-pointer hover:border-blue-200 hover:bg-blue-50/30 transition-colors
                  ${!s.is_active ? 'opacity-50' : ''}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">{s.name}</span>
                      {s.category && (
                        <span className="text-xs px-2 py-0.5 bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] rounded-full">{s.category}</span>
                      )}
                      {!s.is_active && (
                        <span className="text-xs px-2 py-0.5 bg-[color:var(--color-control-bg)] text-[color:var(--color-text-muted)] rounded-full">Неактивен</span>
                      )}
                      {s.invoice_file_url && (
                        <span className="text-xs px-2 py-0.5 bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)] rounded-full">📎</span>
                      )}
                      {(s.objects || []).map(obj => (
                        <span key={obj} className="text-xs px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full border border-blue-100">🏢 {obj}</span>
                      ))}
                    </div>
                    <div className="text-xs text-[color:var(--color-text-muted)] mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
                      <span>{fmt(s.planned_amount)} ₽</span>
                      <span>День: {s.day_of_month}</span>
                      {s.responsible_name && <span>👤 {s.responsible_name}</span>}
                      <span>Уведомить за {s.notify_days_before} д.</span>
                    </div>
                    {s.note && <p className="text-xs text-[color:var(--color-text-faint)] mt-1 truncate">{s.note}</p>}
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0" onClick={e => e.stopPropagation()}>
                    <button onClick={() => handleToggleActive(s)}
                      className="px-2.5 py-1 text-xs rounded-lg border border-[color:var(--color-border)] hover:bg-[color:var(--color-control-bg-hover)] text-[color:var(--color-text-muted)]">
                      {s.is_active ? 'Откл' : 'Вкл'}
                    </button>
                    <button onClick={() => setScheduleModal(s)}
                      className="px-2.5 py-1 text-xs rounded-lg border border-[color:var(--color-border)] hover:bg-[color:var(--color-control-bg-hover)] text-[color:var(--color-text-muted)]">
                      ✎
                    </button>
                    <button onClick={() => handleDeleteSchedule(s.id)}
                      className="px-2.5 py-1 text-xs rounded-lg border border-red-200 hover:bg-red-50 text-red-600">
                      ✕
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === 'settings' && (
        <div className="space-y-4 max-w-md">
          <CategoriesPanel categories={categories} onChanged={loadCategories} />
        </div>
      )}

      {scheduleModal && (
        <ScheduleModal
          initial={scheduleModal === 'new' ? null : scheduleModal}
          onSave={handleSaveSchedule}
          onClose={() => setScheduleModal(null)}
          categories={categories}
          salons={salons}
        />
      )}
      {payModal && (
        <PayModal record={payModal} onPay={handlePay} onClose={() => setPayModal(null)} />
      )}
      {detailItem && (
        <DetailModal
          schedule={detailItem.schedule}
          record={detailItem.record}
          onClose={() => setDetailItem(null)}
          onEdit={() => { setScheduleModal(detailItem.schedule); setDetailItem(null); }}
        />
      )}
    </div>
  );
}
