import { useEffect, useState, useCallback } from 'react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MONTH_NAMES = [
  'Январь','Февраль','Март','Апрель','Май','Июнь',
  'Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь',
];
const DAY_NAMES = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];

const CATEGORIES = ['Связь','Аренда','ПО','Коммунальные','Налоги','Страхование','Прочее'];

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

// ── Schedule form modal ───────────────────────────────────────────────────────

function ScheduleModal({ initial, onSave, onClose }) {
  const [form, setForm] = useState(
    initial ?? {
      name: '', planned_amount: '', day_of_month: '', category: '',
      responsible_name: '', responsible_tg_id: '', notify_days_before: 3, note: '',
    }
  );
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-md">
        <div className="flex items-center justify-between p-4 border-b">
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
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
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
        <div className="p-4 border-t flex gap-2 justify-end">
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

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PaymentCalendar() {
  const { showToast } = useToast();
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth()); // 0-indexed
  const [records, setRecords] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [scheduleModal, setScheduleModal] = useState(null); // null | 'new' | {schedule obj}
  const [payModal, setPayModal] = useState(null);
  const [tab, setTab] = useState('calendar'); // 'calendar' | 'schedules'
  const [highlightDay, setHighlightDay] = useState(null);

  const yearMonth = `${year}-${String(month + 1).padStart(2, '0')}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [recRes, schRes] = await Promise.all([
        api.get(`/payment-calendar/month/${yearMonth}`),
        api.get('/payment-calendar/schedules'),
      ]);
      setRecords(recRes.data);
      setSchedules(schRes.data);
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
        {[['calendar','Календарь'],['schedules','Настройки']].map(([k,l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${tab === k ? 'bg-white shadow text-gray-800' : 'text-gray-500 hover:text-gray-700'}`}>
            {l}
          </button>
        ))}
      </div>

      {tab === 'calendar' && (
        <>
          {/* Month navigation */}
          <div className="flex items-center gap-4">
            <button onClick={prevMonth} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">‹</button>
            <h2 className="text-base font-semibold text-gray-800 min-w-[140px] text-center">
              {MONTH_NAMES[month]} {year}
            </h2>
            <button onClick={nextMonth} className="p-2 rounded-lg hover:bg-gray-100 text-gray-600">›</button>
          </div>

          {/* Stats bar */}
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

          {/* Calendar grid */}
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

          {/* Legend */}
          <div className="flex flex-wrap gap-3 text-xs text-gray-500">
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
                    <h3 className="text-sm font-semibold text-gray-500 mb-2">
                      {day} {MONTH_NAMES[month].toLowerCase()}
                    </h3>
                    <div className="space-y-2">
                      {byDay[day].map(r => {
                        const sc = r.schedule ?? {};
                        const cls = statusColor(r.status, day, today, year, month);
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
              {schedules.map(s => (
                <div key={s.id} className={`bg-white border rounded-xl p-4 flex items-center justify-between gap-3
                  ${!s.is_active ? 'opacity-50' : ''}`}>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-medium text-sm">{s.name}</span>
                      {s.category && (
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">{s.category}</span>
                      )}
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
              ))}
            </div>
          )}
        </div>
      )}

      {scheduleModal && (
        <ScheduleModal
          initial={scheduleModal === 'new' ? null : scheduleModal}
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
