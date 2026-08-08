import { useState, useMemo, useEffect, useRef } from 'react';
import { ChevronLeft, ChevronRight, RefreshCw, Search } from 'lucide-react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';

const MONTHS_RU     = ['Январь','Февраль','Март','Апрель','Май','Июнь','Июль','Август','Сентябрь','Октябрь','Ноябрь','Декабрь'];
const MONTHS_RU_GEN = ['января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря'];

// Цвета точек — border-left + dot + chip
const POINT_STYLE = {
  'П':  { border: 'border-blue-400',   dot: 'bg-blue-500',   chip: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300' },
  'Ц':  { border: 'border-purple-400', dot: 'bg-purple-500', chip: 'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300' },
  'А':  { border: 'border-amber-400',  dot: 'bg-amber-500',  chip: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300' },
  'М':  { border: 'border-green-400',  dot: 'bg-green-500',  chip: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300' },
  'Р':  { border: 'border-orange-400', dot: 'bg-orange-500', chip: 'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300' },
  'Оз': { border: 'border-yellow-400', dot: 'bg-yellow-500', chip: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300' },
  'Ох': { border: 'border-teal-400',   dot: 'bg-teal-500',   chip: 'bg-teal-100 text-teal-800 dark:bg-teal-900/40 dark:text-teal-300' },
};

function PointChip({ code }) {
  const s = POINT_STYLE[code];
  if (!s) return <span className="text-xs text-[color:var(--color-muted-foreground)]">{code}</span>;
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-semibold leading-none ${s.chip}`}>
      {code}
    </span>
  );
}

export default function Schedule() {
  const { isMobile } = useViewport();
  const today      = new Date();
  const [year, setYear]   = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [search, setSearch] = useState('');
  const [data, setData]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const todayColRef = useRef(null);

  // Правка клетки. Коды тянем с сервера, а не из POINT_STYLE: там только
  // цвета, и новый салон в справочнике иначе не появился бы в списке.
  const [codes, setCodes] = useState([]);
  const [canEdit, setCanEdit] = useState(false);
  const [editing, setEditing] = useState(null);   // {emp, day}
  const [saving, setSaving] = useState(null);     // {emp, day}
  const [saveError, setSaveError] = useState(null);

  useEffect(() => {
    api.get('/schedule/codes')
      .then((r) => { setCodes(r.data || []); setCanEdit(true); })
      // 403 — обычный сотрудник: график показываем, правку прячем.
      .catch(() => setCanEdit(false));
  }, []);

  async function saveCell(emp, day, code) {
    setEditing(null);
    setSaving({ emp, day });
    setSaveError(null);
    try {
      await api.patch('/schedule/cell', { year, month, employee: emp, day, code });
      await load();
    } catch (e) {
      setSaveError(e.response?.data?.detail || e.message || 'Не удалось сохранить');
    } finally {
      setSaving(null);
    }
  }

  useEffect(() => { load(); }, [year, month]); // eslint-disable-line react-hooks/exhaustive-deps

  // Scroll to today's column after load
  useEffect(() => {
    if (data && todayColRef.current) {
      todayColRef.current.scrollIntoView({ inline: 'center', block: 'nearest', behavior: 'smooth' });
    }
  }, [data]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/schedule/month', { params: { year, month } });
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }

  function prevMonth() {
    if (month === 1) { setMonth(12); setYear(y => y - 1); }
    else setMonth(m => m - 1);
  }
  function nextMonth() {
    if (month === 12) { setMonth(1); setYear(y => y + 1); }
    else setMonth(m => m + 1);
  }

  const isCurrentMonth = year === today.getFullYear() && month === today.getMonth() + 1;
  const todayDay       = today.getDate();

  // Кто сегодня в какой точке
  const todayByPoint = useMemo(() => {
    if (!data || !isCurrentMonth) return null;
    const d = data.days.find(x => x.day === todayDay);
    if (!d) return null;
    const map = {};
    Object.entries(d.assignments).forEach(([emp, code]) => { map[code] = emp; });
    return map;
  }, [data, isCurrentMonth, todayDay]);

  // Сотрудники с учётом поиска
  const filteredEmps = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return q ? data.employees.filter(e => e.toLowerCase().includes(q)) : data.employees;
  }, [data, search]);

  // Количество сотрудников в точке в каждый день (для строки итогов)
  const dayPointCount = useMemo(() => {
    if (!data) return {};
    const result = {};
    data.days.forEach(d => {
      const counts = {};
      Object.values(d.assignments).forEach(code => { counts[code] = (counts[code] || 0) + 1; });
      result[d.day] = counts;
    });
    return result;
  }, [data]);

  return (
    <div className="space-y-5">
      <TopProgressBar active={loading} />
      {/* Шапка */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-2xl font-semibold">Расписание</h2>
        <div className="flex items-center gap-2">
          <button onClick={prevMonth} className="btn btn-outline p-2" aria-label="Предыдущий месяц">
            <ChevronLeft size={16} />
          </button>
          <span className="min-w-[170px] text-center text-lg font-semibold">
            {MONTHS_RU[month - 1]} {year}
          </span>
          <button onClick={nextMonth} className="btn btn-outline p-2" aria-label="Следующий месяц">
            <ChevronRight size={16} />
          </button>
          <button onClick={load} disabled={loading}
            className="btn btn--primary flex items-center gap-1.5 disabled:opacity-50">
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Кто сегодня где */}
      {isCurrentMonth && todayByPoint && data && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
            Сегодня — {todayDay} {MONTHS_RU_GEN[month - 1]}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {Object.entries(data.points).map(([code, name]) => {
              const s   = POINT_STYLE[code] || {};
              const emp = todayByPoint[code];
              return (
                <div key={code}
                  className={`app-card border-l-4 p-3 ${s.border || 'border-[color:var(--color-border)]'}`}>
                  <div className="mb-1 flex items-center gap-1.5">
                    <span className={`h-2 w-2 rounded-full ${s.dot || 'bg-gray-400'}`} />
                    <span className="text-xs font-semibold text-[color:var(--color-muted-foreground)]">
                      {name}
                    </span>
                  </div>
                  <div className={`text-sm font-medium ${emp ? '' : 'italic text-[color:var(--color-muted-foreground)]'}`}>
                    {emp || 'Не назначен'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Легенда точек */}
      {data && (
        <div className="flex flex-wrap gap-2">
          {Object.entries(data.points).map(([code, name]) => (
            <span key={code} className="flex items-center gap-1.5 text-sm">
              <PointChip code={code} />
              <span className="text-[color:var(--color-muted-foreground)]">{name}</span>
            </span>
          ))}
        </div>
      )}

      {saveError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300 flex items-start justify-between gap-3">
          <span>{saveError}</span>
          <button onClick={() => setSaveError(null)} className="opacity-60 leading-none">&times;</button>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Поиск + сетка */}
      {data && (
        <div className="app-card">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[color:var(--color-border)] p-4">
            <div className="flex items-center gap-2">
              <span className="font-semibold">График месяца</span>
              <span className="text-sm text-[color:var(--color-muted-foreground)]">
                {data.employees.length} сотрудников
              </span>
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
              <input
                className="input pl-8 text-sm"
                placeholder="Поиск сотрудника..."
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          </div>

          {isMobile ? (
            <div className="space-y-3 p-4">
              {filteredEmps.map(emp => {
                const assignments = data.days
                  .filter(d => d.assignments[emp])
                  .map(d => ({ day: d.day, weekday_short: d.weekday_short, code: d.assignments[emp], isToday: isCurrentMonth && d.day === todayDay, isWeekend: d.is_weekend }));
                const todayAssignment = assignments.find(a => a.isToday);
                return (
                  <div key={emp} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                    <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium">{emp}</div>
                    <div className="px-4 py-2 space-y-1.5 text-sm">
                      {todayAssignment && (
                        <div className="flex justify-between items-center">
                          <span className="text-[color:var(--color-text-muted)]">Сегодня</span>
                          <PointChip code={todayAssignment.code} />
                        </div>
                      )}
                      <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Смен в месяце</span><span>{assignments.length}</span></div>
                      {assignments.length > 0 && (
                        <div className="flex flex-wrap gap-1 pt-1">
                          {assignments.map(a => (
                            <span key={a.day} className={`text-xs px-1.5 py-0.5 rounded border ${a.isToday ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 font-semibold' : a.isWeekend ? 'border-red-200 bg-red-50' : 'border-[color:var(--color-border)]'}`}>
                              {a.day} <PointChip code={a.code} />
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="overflow-x-auto">
              {/* overflow-visible: the global `table { overflow: hidden }` rounded-corner
                  rule (globals.css) clips `position: sticky` descendants — the employee-name
                  column would render blank once the horizontal scroll brings a later day into
                  view. The scroll container (div.overflow-x-auto above) still clips normally. */}
              <table className="border-collapse text-xs overflow-visible">
                <thead>
                  {/* Строка: дни */}
                  <tr>
                    <th className="sticky left-0 z-20 min-w-[150px] border-b border-r border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] px-3 py-2 text-left text-[color:var(--color-muted-foreground)]">
                      Сотрудник
                    </th>
                    {data.days.map(d => {
                      const isToday   = isCurrentMonth && d.day === todayDay;
                      const isWeekend = d.is_weekend;
                      return (
                        <th
                          key={d.day}
                          ref={isToday ? todayColRef : null}
                          className={`min-w-[36px] border-b border-r border-[color:var(--color-border)] px-1 py-2 text-center font-semibold
                            ${isToday   ? 'bg-[color:var(--color-primary)] text-white'                    : ''}
                            ${isWeekend && !isToday ? 'bg-red-50 text-red-500 dark:bg-red-900/20 dark:text-red-400' : ''}
                            ${!isToday && !isWeekend ? 'bg-[color:var(--color-modal-bg)] text-[color:var(--color-muted-foreground)]' : ''}
                          `}
                        >
                          <div>{d.day}</div>
                          <div className="text-[10px] font-normal opacity-70">{d.weekday_short}</div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>

                <tbody>
                  {filteredEmps.map((emp, ri) => (
                    <tr key={emp}
                      className={ri % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}>
                      <td className="sticky left-0 z-10 border-b border-r border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] px-3 py-1.5 font-medium whitespace-nowrap"
                        style={{ background: ri % 2 === 1 ? 'var(--color-table-header-bg)' : 'var(--color-modal-bg)' }}>
                        {emp}
                      </td>
                      {data.days.map(d => {
                        const code      = d.assignments[emp] || '';
                        const isToday   = isCurrentMonth && d.day === todayDay;
                        const isWeekend = d.is_weekend;
                        const isEditing = editing && editing.emp === emp && editing.day === d.day;
                        const isSaving  = saving && saving.emp === emp && saving.day === d.day;
                        return (
                          <td key={d.day}
                            onClick={() => canEdit && !isSaving && setEditing({ emp, day: d.day })}
                            className={`border-b border-r border-[color:var(--color-border)] px-1 py-1.5 text-center
                              ${isToday   ? 'bg-[color:var(--color-primary)]/10' : ''}
                              ${isWeekend && !isToday ? 'bg-red-50/60 dark:bg-red-900/10' : ''}
                              ${canEdit && !isEditing ? 'cursor-pointer hover:bg-[color:var(--color-primary)]/10' : ''}
                            `}>
                            {isSaving ? (
                              <RefreshCw size={12} className="animate-spin mx-auto opacity-60" />
                            ) : isEditing ? (
                              <select
                                autoFocus
                                defaultValue={code}
                                onBlur={() => setEditing(null)}
                                onChange={(e) => saveCell(emp, d.day, e.target.value)}
                                onClick={(e) => e.stopPropagation()}
                                className="text-xs bg-transparent border border-[color:var(--color-primary)] rounded px-0.5 py-0.5"
                              >
                                <option value="">—</option>
                                {codes.map((c) => (
                                  <option key={c.code} value={c.code}>{c.code}</option>
                                ))}
                              </select>
                            ) : code ? <PointChip code={code} /> : (
                              <span className="text-[color:var(--color-muted-foreground)] opacity-30">—</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}

                  {/* Итоговая строка: количество в каждой точке */}
                  {data.employees.length > 0 && (
                    <tr className="border-t-2 border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 font-semibold">
                      <td className="sticky left-0 z-10 border-r border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 px-3 py-1.5 text-xs text-[color:var(--color-muted-foreground)]">
                        В точках
                      </td>
                      {data.days.map(d => {
                        const counts = dayPointCount[d.day] || {};
                        const isToday   = isCurrentMonth && d.day === todayDay;
                        const isWeekend = d.is_weekend;
                        return (
                          <td key={d.day}
                            className={`border-r border-[color:var(--color-border)] px-0.5 py-1 text-center
                              ${isToday ? 'bg-[color:var(--color-primary)]/10' : ''}
                              ${isWeekend && !isToday ? 'bg-red-50/60 dark:bg-red-900/10' : ''}
                            `}>
                            <div className="flex flex-col gap-0.5 items-center">
                              {Object.entries(counts).map(([code, cnt]) => (
                                <span key={code} className="flex items-center gap-0.5">
                                  <PointChip code={code} />
                                  {cnt > 1 && <span className="text-[10px] text-[color:var(--color-muted-foreground)]">×{cnt}</span>}
                                </span>
                              ))}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {filteredEmps.length === 0 && search && (
            <div className="p-6 text-center text-sm text-[color:var(--color-muted-foreground)]">
              Сотрудник «{search}» не найден
            </div>
          )}
        </div>
      )}

      {!data && !loading && !error && (
        <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">
          Загрузка расписания...
        </div>
      )}
    </div>
  );
}
