import { useEffect, useState, useCallback } from 'react';
import {
  Plus, Pencil, Trash2, Check, RotateCcw, Calendar, Clock,
  Filter, LayoutGrid, List, AlertCircle, CheckCircle2, Circle,
  PlayCircle, ChevronLeft, ChevronRight, Settings2, FolderPlus, X,
  Bell, Loader2,
} from 'lucide-react';
import api from '../api';
import Modal from '../components/Modal';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { useToast } from '../providers/ToastProvider.jsx';

// ── Constants ────────────────────────────────────────────────────
const PRIORITIES = [
  { value: 'low',    label: 'Низкий',  dot: '#6b7280' },
  { value: 'medium', label: 'Средний', dot: '#3b82f6' },
  { value: 'high',   label: 'Высокий', dot: '#f97316' },
  { value: 'urgent', label: 'Срочный', dot: '#ef4444' },
];

const STATUSES = [
  { value: 'todo',        label: 'К выполнению', icon: Circle,       color: 'text-[color:var(--color-text-faint)]' },
  { value: 'in_progress', label: 'В работе',     icon: PlayCircle,   color: 'text-blue-400' },
  { value: 'done',        label: 'Выполнено',    icon: CheckCircle2, color: 'text-green-400' },
];

const DAY_NAMES   = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const MONTH_NAMES = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек'];

const DEFAULT_CAT_COLORS = [
  '#6366f1','#8b5cf6','#ec4899','#ef4444','#f97316',
  '#eab308','#22c55e','#14b8a6','#06b6d4','#3b82f6',
];
const DEFAULT_CAT_ICONS = ['📋','💼','🏠','🎯','🚀','💡','📚','🔧','💰','🎮'];

// ── Date helpers ──────────────────────────────────────────────────
function getMonday(date) {
  const d = new Date(date);
  const day = d.getDay();
  d.setDate(d.getDate() + (day === 0 ? -6 : 1 - day));
  d.setHours(0, 0, 0, 0);
  return d;
}
function addDays(date, n) {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}
function toISODate(d) { return d.toISOString().slice(0, 10); }

// ── Component ─────────────────────────────────────────────────────
export default function Tasks() {
  const { toast } = useToast();
  const emptyForm = {
    id: null, title: '', description: '', due_date: '', due_time: '',
    priority: 'medium', status: 'todo', category: '', tags: [], reminder_minutes: null,
  };
  const emptyCatForm = { id: null, name: '', color: '#6366f1', icon: '📋' };

  const [tasks, setTasks]           = useState([]);
  const [stats, setStats]           = useState({});
  const [form, setForm]             = useState(emptyForm);
  const [showForm, setShowForm]     = useState(false);
  const [tagInput, setTagInput]     = useState('');

  const [viewMode, setViewMode]     = useState(() => localStorage.getItem('tasks_view_mode') || 'board');
  const [filters, setFilters]       = useState(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('tasks_filters'));
      if (saved) return saved;
    } catch {}
    return { status: '', priority: '', category: '', includeDone: true };
  });
  const [weekStart, setWeekStart]   = useState(() => getMonday(new Date()));
  const [loading, setLoading]       = useState(true);
  const [selected, setSelected]     = useState(new Set());
  const [dragOverCol, setDragOverCol] = useState(null);

  const [categories, setCategories]           = useState([]);
  const [showCatManager, setShowCatManager]   = useState(false);
  const [catForm, setCatForm]                 = useState(emptyCatForm);
  const [showCatForm, setShowCatForm]         = useState(false);

  // ── Data loading ──────────────────────────────────────────────
  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('tasks/', { params: {
        status:       filters.status   || undefined,
        priority:     filters.priority || undefined,
        category:     filters.category || undefined,
        include_done: filters.includeDone,
      }});
      setTasks(res.data);
    } catch (err) { console.error(err); toast('Ошибка загрузки задач', 'error'); }
    finally { setLoading(false); }
  }, [filters]);

  const loadStats      = async () => { try { setStats((await api.get('tasks/stats')).data);      } catch {} };
  const loadCategories = async () => { try { setCategories((await api.get('tasks/categories')).data); } catch {} };

  useEffect(() => { loadStats(); loadCategories(); }, []);
  useEffect(() => { loadTasks(); setSelected(new Set()); }, [filters]);
  useEffect(() => { localStorage.setItem('tasks_view_mode', viewMode); }, [viewMode]);
  useEffect(() => { localStorage.setItem('tasks_filters', JSON.stringify(filters)); }, [filters]);

  // ── Task CRUD ─────────────────────────────────────────────────
  function startCreate(preDate = '') {
    setForm({ ...emptyForm, due_date: preDate || new Date().toISOString().slice(0, 10) });
    setTagInput('');
    setShowForm(true);
  }
  function startEdit(task) {
    setForm({ ...task, due_date: task.due_date || '', due_time: task.due_time ? task.due_time.slice(0, 5) : '', tags: task.tags || [] });
    setTagInput('');
    setShowForm(true);
  }
  async function saveForm() {
    if (!form.title.trim()) { toast('Введите название задачи', 'warning'); return; }
    const isEdit = !!form.id;
    try {
      const payload = { ...form, due_time: form.due_time ? form.due_time + ':00' : null, tags: form.tags || [] };
      if (isEdit) await api.put(`tasks/${form.id}`, payload);
      else        await api.post('tasks/', payload);
      setShowForm(false); setForm(emptyForm);
      toast(isEdit ? 'Задача обновлена' : 'Задача создана', 'success');
      loadTasks(); loadStats();
    } catch { toast('Ошибка сохранения', 'error'); }
  }
  async function deleteTask(id) {
    if (!window.confirm('Удалить задачу?')) return;
    try {
      await api.delete(`tasks/${id}`);
      toast('Задача удалена', 'success');
      loadTasks(); loadStats();
    } catch { toast('Ошибка удаления', 'error'); }
  }
  async function completeTask(id) {
    try { await api.post(`tasks/${id}/complete`); loadTasks(); loadStats(); }
    catch { toast('Ошибка', 'error'); }
  }
  async function reopenTask(id) {
    try { await api.post(`tasks/${id}/reopen`); loadTasks(); loadStats(); }
    catch { toast('Ошибка', 'error'); }
  }
  async function updateStatus(id, status) {
    try { await api.put(`tasks/${id}`, { status }); loadTasks(); loadStats(); }
    catch { toast('Ошибка обновления статуса', 'error'); }
  }

  async function bulkComplete() {
    try {
      await Promise.all([...selected].map(id => api.post(`tasks/${id}/complete`)));
      toast('Задачи выполнены', 'success');
      setSelected(new Set());
      loadTasks(); loadStats();
    } catch { toast('Ошибка выполнения', 'error'); }
  }
  async function bulkDelete() {
    if (!window.confirm(`Удалить ${selected.size} задач?`)) return;
    try {
      await Promise.all([...selected].map(id => api.delete(`tasks/${id}`)));
      toast('Задачи удалены', 'success');
      setSelected(new Set());
      loadTasks(); loadStats();
    } catch { toast('Ошибка удаления', 'error'); }
  }
  function toggleSelect(id) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }
  function toggleSelectAll() {
    setSelected(prev => prev.size === tasks.length ? new Set() : new Set(tasks.map(t => t.id)));
  }

  function addTag() {
    const t = tagInput.trim();
    if (t && !form.tags.some(x => x.toLowerCase() === t.toLowerCase())) setForm({ ...form, tags: [...form.tags, t] });
    setTagInput('');
  }
  function removeTag(t) { setForm({ ...form, tags: form.tags.filter(x => x !== t) }); }

  // ── Category CRUD ─────────────────────────────────────────────
  function startCreateCat() { setCatForm({ ...emptyCatForm }); setShowCatForm(true); }
  function startEditCat(cat) { setCatForm({ ...cat }); setShowCatForm(true); }
  async function saveCat() {
    if (!catForm.name.trim()) { toast('Введите название', 'warning'); return; }
    const isEdit = !!catForm.id;
    try {
      if (isEdit) await api.put(`tasks/categories/${catForm.id}`, catForm);
      else        await api.post('tasks/categories', catForm);
      setShowCatForm(false); setCatForm(emptyCatForm);
      toast(isEdit ? 'Категория обновлена' : 'Категория создана', 'success');
      loadCategories();
    } catch { toast('Ошибка сохранения', 'error'); }
  }
  async function deleteCat(cat) {
    try {
      const res = await api.get('tasks/', { params: { category: cat.name, include_done: true } });
      const count = res.data.length;
      const msg = count > 0
        ? `Категория «${cat.name}» используется в ${count} задачах. Удалить категорию? Задачи останутся без категории.`
        : `Удалить категорию «${cat.name}»?`;
      if (!window.confirm(msg)) return;
    } catch {
      if (!window.confirm(`Удалить категорию «${cat.name}»?`)) return;
    }
    try {
      await api.delete(`tasks/categories/${cat.id}`);
      toast('Категория удалена', 'success');
      loadCategories(); loadTasks();
    } catch { toast('Ошибка удаления категории', 'error'); }
  }

  // ── Helpers ───────────────────────────────────────────────────
  const getPri = p => PRIORITIES.find(x => x.value === p) || PRIORITIES[1];
  const getCat = n => categories.find(c => c.name === n);
  const isOverdue  = t => t.status !== 'done' && t.due_date && t.due_date < todayISO;
  const isToday    = t => t.due_date === todayISO;

  const todayISO = new Date().toISOString().slice(0, 10);

  // board grouping
  const byStatus = {
    todo:        tasks.filter(t => t.status === 'todo'),
    in_progress: tasks.filter(t => t.status === 'in_progress'),
    done:        tasks.filter(t => t.status === 'done'),
  };

  // calendar
  const weekDays    = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const undated     = tasks.filter(t => !t.due_date);
  const tasksForDay = iso => tasks.filter(t => t.due_date === iso);

  function weekLabel() {
    const end = addDays(weekStart, 6);
    if (weekStart.getMonth() === end.getMonth())
      return `${weekStart.getDate()}–${end.getDate()} ${MONTH_NAMES[weekStart.getMonth()]} ${weekStart.getFullYear()}`;
    return `${weekStart.getDate()} ${MONTH_NAMES[weekStart.getMonth()]} – ${end.getDate()} ${MONTH_NAMES[end.getMonth()]} ${end.getFullYear()}`;
  }

  // ── Task card (shared by all views) ──────────────────────────
  function TaskCard({ task, compact = false, draggable = false }) {
    const pri = getPri(task.priority);
    const cat = getCat(task.category);
    const over = isOverdue(task);
    const tod  = isToday(task);
    const leftColor = cat?.color || (over ? '#ef4444' : tod ? '#eab308' : null);

    return (
      <div className={`bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] hover:border-[var(--color-primary)] transition-colors ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}
        draggable={draggable}
        onDragStart={draggable ? (e) => { e.dataTransfer.setData('text/plain', String(task.id)); e.dataTransfer.effectAllowed = 'move'; } : undefined}
        style={leftColor ? { borderLeftWidth: 3, borderLeftColor: leftColor } : {}}>
        <div className={compact ? 'p-2' : 'p-4'}>
          {/* Title row */}
          <div className="flex items-start gap-2 mb-1">
            <div className="w-2 h-2 rounded-full shrink-0 mt-1.5" style={{ backgroundColor: pri.dot }} title={pri.label} />
            <span className={`flex-1 font-medium text-sm leading-snug ${task.status === 'done' ? 'line-through text-[color:var(--color-text-muted)]' : ''}`}>
              {task.title}
            </span>
          </div>
          {/* Description */}
          {!compact && task.description && (
            <p className="text-xs text-[color:var(--color-text-faint)] mb-2 line-clamp-2 pl-4">{task.description}</p>
          )}
          {/* Tags + category */}
          {!compact && (task.tags?.length > 0 || cat) && (
            <div className="flex flex-wrap gap-1 mb-2 pl-4">
              {task.tags?.map(tag => <span key={tag} className="text-xs bg-[var(--color-bg)] px-1.5 py-0.5 rounded">{tag}</span>)}
              {cat && (
                <span className="text-xs px-1.5 py-0.5 rounded" style={{ background: cat.color + '22', color: cat.color }}>
                  {cat.icon} {cat.name}
                </span>
              )}
            </div>
          )}
          {/* Footer */}
          <div className="flex items-center justify-between text-xs text-[color:var(--color-text-faint)] pl-4">
            <div className="flex items-center gap-1">
              {task.due_date && !compact && (
                <span className={`flex items-center gap-0.5 ${over ? 'text-red-400' : tod ? 'text-yellow-400' : ''}`}>
                  <Calendar size={10} />{task.due_date}
                </span>
              )}
              {task.due_time && (
                <span className="flex items-center gap-0.5"><Clock size={10} />{task.due_time.slice(0, 5)}</span>
              )}
              {task.reminder_minutes != null && (
                <span title={`Напоминание за ${task.reminder_minutes} мин`}><Bell size={10} /></span>
              )}
              {compact && cat && (
                <span className="text-xs" style={{ color: cat.color }}>{cat.icon}</span>
              )}
            </div>
            <div className="flex items-center gap-0.5">
              {task.status !== 'done' ? (
                <button onClick={() => completeTask(task.id)} className="p-1 hover:bg-green-500/20 rounded" title="Выполнено">
                  <Check size={compact ? 11 : 13} className="text-green-400" />
                </button>
              ) : (
                <button onClick={() => reopenTask(task.id)} className="p-1 hover:bg-blue-500/20 rounded" title="Вернуть">
                  <RotateCcw size={compact ? 11 : 13} className="text-blue-400" />
                </button>
              )}
              <button onClick={() => startEdit(task)} className="p-1 hover:bg-[var(--color-bg)] rounded">
                <Pencil size={compact ? 11 : 13} />
              </button>
              <button onClick={() => deleteTask(task.id)} className="p-1 hover:bg-red-500/20 rounded">
                <Trash2 size={compact ? 11 : 13} className="text-red-400" />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Render ────────────────────────────────────────────────────
  return (
    <div className="space-y-5">

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <h2 className="text-2xl font-semibold">Задачи</h2>
        <div className="flex gap-2">
          <button className="btn flex items-center gap-2" onClick={() => setShowCatManager(true)}>
            <Settings2 size={16} />Категории
          </button>
          <button className="btn btn--primary flex items-center gap-2" onClick={() => startCreate()}>
            <Plus size={18} />Новая задача
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3 [&>:last-child]:col-span-2 md:[&>:last-child]:col-span-1">
        {[
          { l: 'Всего',      v: stats.total         || 0, c: '' },
          { l: 'К выполн.',  v: stats.todo          || 0, c: 'text-[color:var(--color-text-faint)]' },
          { l: 'В работе',   v: stats.in_progress   || 0, c: 'text-blue-400' },
          { l: 'Выполнено',  v: stats.done          || 0, c: 'text-green-400' },
          { l: 'Просрочено', v: stats.overdue       || 0, c: 'text-red-400' },
          { l: 'Сегодня',    v: stats.due_today     || 0, c: 'text-yellow-400' },
          { l: 'Неделя',     v: stats.due_this_week || 0, c: 'text-purple-400' },
        ].map(s => (
          <div key={s.l} className="bg-[var(--color-bg-secondary)] rounded-lg p-3 border border-[var(--color-border)]">
            <div className={`text-2xl font-bold ${s.c}`}>{s.v}</div>
            <div className="text-xs text-[color:var(--color-text-faint)]">{s.l}</div>
          </div>
        ))}
      </div>

      {/* Filters + view toggle */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 text-sm text-[color:var(--color-text-faint)]"><Filter size={15} />Фильтры:</div>
        <select className="input-field text-sm" value={filters.status}
          onChange={e => setFilters({ ...filters, status: e.target.value })}>
          <option value="">Все статусы</option>
          {STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
        <select className="input-field text-sm" value={filters.priority}
          onChange={e => setFilters({ ...filters, priority: e.target.value })}>
          <option value="">Все приоритеты</option>
          {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        <select className="input-field text-sm" value={filters.category}
          onChange={e => setFilters({ ...filters, category: e.target.value })}>
          <option value="">Все категории</option>
          {categories.map(c => <option key={c.id} value={c.name}>{c.icon} {c.name}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={filters.includeDone}
            onChange={e => setFilters({ ...filters, includeDone: e.target.checked })} />
          Выполненные
        </label>

        <div className="ml-auto flex items-center gap-1 bg-[var(--color-bg-secondary)] rounded-lg p-1">
          {[
            { mode: 'board',    Icon: LayoutGrid, title: 'Доска' },
            { mode: 'list',     Icon: List,       title: 'Список' },
            { mode: 'calendar', Icon: Calendar,   title: 'Ежедневник' },
          ].map(({ mode, Icon, title }) => (
            <button key={mode} title={title}
              className={`p-2 rounded ${viewMode === mode ? 'bg-[var(--color-primary)]' : 'hover:bg-[var(--color-bg)]'}`}
              onClick={() => setViewMode(mode)}>
              <Icon size={16} />
            </button>
          ))}
        </div>
      </div>

      {/* ── Loading ───────────────────────────────────────────── */}
      {loading && (
        <div className="flex items-center justify-center py-20 text-[color:var(--color-text-faint)]">
          <Loader2 className="animate-spin mr-2" size={20} /> Загрузка задач...
        </div>
      )}

      {/* ── Board ─────────────────────────────────────────────── */}
      {!loading && viewMode === 'board' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {STATUSES.map(st => {
            const Icon = st.icon;
            const col  = byStatus[st.value] || [];
            return (
              <div key={st.value}
                className={`bg-[var(--color-bg)] rounded-lg p-4 transition-colors ${dragOverCol === st.value ? 'ring-2 ring-[var(--color-primary)]' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOverCol(st.value); }}
                onDragLeave={() => setDragOverCol(prev => prev === st.value ? null : prev)}
                onDrop={e => {
                  e.preventDefault();
                  setDragOverCol(null);
                  const id = e.dataTransfer.getData('text/plain');
                  if (id) updateStatus(Number(id), st.value);
                }}>
                <div className={`flex items-center gap-2 mb-4 ${st.color}`}>
                  <Icon size={18} />
                  <h3 className="font-medium">{st.label}</h3>
                  <span className="ml-auto bg-[var(--color-bg-secondary)] px-2 py-0.5 rounded text-sm">{col.length}</span>
                </div>
                <div className="space-y-3">
                  {col.map(t => <TaskCard key={t.id} task={t} draggable />)}
                  {col.length === 0 && (
                    <div className="flex flex-col items-center gap-2 text-center text-[color:var(--color-text-muted)] py-8">
                      <Icon size={22} className="opacity-40" />
                      <span className="text-sm">Нет задач</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ── List ──────────────────────────────────────────────── */}
      {!loading && viewMode === 'list' && (
        <>
          {selected.size > 0 && (
            <div className="flex items-center gap-3 bg-[var(--color-primary-muted)] border border-[var(--color-primary)] rounded-lg px-4 py-2 mb-3">
              <span className="text-sm font-medium">Выбрано: {selected.size}</span>
              <button className="btn btn--sm flex items-center gap-1" onClick={bulkComplete}><Check size={14} />Выполнить</button>
              <button className="btn btn--sm flex items-center gap-1 text-red-400" onClick={bulkDelete}><Trash2 size={14} />Удалить</button>
              <button className="btn btn--sm ml-auto" onClick={() => setSelected(new Set())}>Отмена</button>
            </div>
          )}
        {tasks.length > 0 && (
          <label className="flex items-center gap-2 text-sm text-[color:var(--color-text-faint)] mb-2">
            <input type="checkbox" checked={selected.size === tasks.length && tasks.length > 0} onChange={toggleSelectAll} />
            Выбрать все
          </label>
        )}
        <div className="bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] overflow-hidden">
          <ResponsiveTable
            data={tasks}
            keyFn={task => task.id}
            rowClass={task => isOverdue(task) ? 'bg-red-500/5' : isToday(task) ? 'bg-yellow-500/5' : ''}
            emptyText="Нет задач"
            columns={[
              {
                label: 'Выбор',
                headerClass: 'w-8',
                render: task => (
                  <input type="checkbox" checked={selected.has(task.id)} onChange={() => toggleSelect(task.id)} />
                ),
              },
              {
                label: 'Задача',
                primary: true,
                render: task => {
                  const cat = getCat(task.category);
                  return (
                    <div className="flex items-center gap-2">
                      {cat && <span className="w-1 h-7 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />}
                      <div>
                        <div className={task.status === 'done' ? 'line-through text-[color:var(--color-text-muted)]' : ''}>{task.title}</div>
                        {task.description && <div className="text-xs text-[color:var(--color-text-faint)] truncate max-w-xs">{task.description}</div>}
                      </div>
                    </div>
                  );
                },
              },
              {
                label: 'Категория',
                headerClass: 'hidden md:table-cell',
                cellClass: 'hidden md:table-cell',
                render: task => {
                  const cat = getCat(task.category);
                  return cat ? (
                    <span className="text-xs px-2 py-0.5 rounded" style={{ background: cat.color + '22', color: cat.color }}>
                      {cat.icon} {cat.name}
                    </span>
                  ) : null;
                },
              },
              {
                label: 'Срок',
                render: task => {
                  const over = isOverdue(task);
                  const tod  = isToday(task);
                  return task.due_date ? (
                    <span className={over ? 'text-red-400' : tod ? 'text-yellow-400' : ''}>
                      {task.due_date}
                      {task.due_time && <span className="ml-1 text-[color:var(--color-text-faint)]">{task.due_time.slice(0, 5)}</span>}
                    </span>
                  ) : '—';
                },
              },
              {
                label: 'Приоритет',
                render: task => {
                  const pri = getPri(task.priority);
                  return (
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ backgroundColor: pri.dot }} />
                      <span className="text-sm hidden lg:inline">{pri.label}</span>
                    </div>
                  );
                },
              },
              {
                label: 'Статус',
                render: task => (
                  <select className="input-field text-sm py-1" value={task.status}
                    onChange={e => updateStatus(task.id, e.target.value)}>
                    {STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                ),
              },
              {
                label: 'Действия',
                isAction: true,
                render: task => (
                  <div className="flex items-center justify-end gap-1">
                    {task.status !== 'done' ? (
                      <button onClick={() => completeTask(task.id)} className="p-1.5 hover:bg-green-500/20 rounded">
                        <Check size={16} className="text-green-400" />
                      </button>
                    ) : (
                      <button onClick={() => reopenTask(task.id)} className="p-1.5 hover:bg-blue-500/20 rounded">
                        <RotateCcw size={16} className="text-blue-400" />
                      </button>
                    )}
                    <button onClick={() => startEdit(task)} className="p-1.5 hover:bg-[var(--color-bg)] rounded">
                      <Pencil size={16} />
                    </button>
                    <button onClick={() => deleteTask(task.id)} className="p-1.5 hover:bg-red-500/20 rounded">
                      <Trash2 size={16} className="text-red-400" />
                    </button>
                  </div>
                ),
              },
            ]}
          />
        </div>
        </>
      )}

      {/* ── Calendar / Diary ──────────────────────────────────── */}
      {!loading && viewMode === 'calendar' && (
        <div className="space-y-4">
          {/* Week nav */}
          <div className="flex items-center gap-2">
            <button className="btn" onClick={() => setWeekStart(d => addDays(d, -7))}>
              <ChevronLeft size={16} />
            </button>
            <div className="flex-1 text-center font-semibold">{weekLabel()}</div>
            <button className="btn" onClick={() => setWeekStart(d => addDays(d, 7))}>
              <ChevronRight size={16} />
            </button>
            <button className="btn btn--sm" onClick={() => setWeekStart(getMonday(new Date()))}>
              Сегодня
            </button>
          </div>

          {/* 7-day grid */}
          <div className="overflow-x-auto -mx-1 px-1">
          <div className="grid grid-cols-7 gap-1.5 min-w-[640px]">
            {weekDays.map((day, i) => {
              const iso       = toISODate(day);
              const isTodayDay = iso === todayISO;
              const dayTasks  = tasksForDay(iso);
              return (
                <div key={iso}
                  className={`rounded-lg border flex flex-col
                    ${isTodayDay
                      ? 'border-[var(--color-primary)] bg-[var(--color-primary-muted)]'
                      : 'border-[var(--color-border)] bg-[var(--color-bg-secondary)]'}`}>

                  {/* Day header */}
                  <div className={`px-1.5 py-2 text-center border-b
                    ${isTodayDay ? 'border-[var(--color-primary)]' : 'border-[var(--color-border)]'}`}>
                    <div className="text-xs text-[color:var(--color-text-faint)] uppercase tracking-wider leading-none">{DAY_NAMES[i]}</div>
                    <div className={`text-xl font-bold leading-tight mt-0.5
                      ${isTodayDay ? 'text-[var(--color-primary)]' : ''}`}>
                      {day.getDate()}
                    </div>
                    <div className="text-xs text-[color:var(--color-text-muted)]">{MONTH_NAMES[day.getMonth()]}</div>
                    {dayTasks.length > 0 && (
                      <div className="mt-1">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium
                          ${isTodayDay ? 'bg-[var(--color-primary)] text-white' : 'bg-[var(--color-bg)] text-[color:var(--color-text-faint)]'}`}>
                          {dayTasks.length}
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Tasks in this day */}
                  <div className="p-1 flex-1 space-y-1 overflow-y-auto" style={{ maxHeight: '60vh' }}>
                    {dayTasks.map(task => <TaskCard key={task.id} task={task} compact />)}
                  </div>

                  {/* Add button */}
                  <div className="p-1 border-t border-[var(--color-border)]">
                    <button
                      className="w-full text-xs text-[color:var(--color-text-muted)] hover:text-[var(--color-primary)]
                        hover:bg-[var(--color-primary-muted)] rounded py-1 flex items-center justify-center gap-0.5 transition-colors"
                      onClick={() => startCreate(iso)}>
                      <Plus size={11} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
          </div>

          {/* Undated tasks */}
          {undated.length > 0 && (
            <div className="bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] overflow-hidden">
              <div className="px-4 py-2.5 border-b border-[var(--color-border)] text-sm text-[color:var(--color-text-faint)] flex items-center gap-2">
                <AlertCircle size={14} />
                Без даты <span className="ml-1 bg-[var(--color-bg)] px-2 py-0.5 rounded-full text-xs">{undated.length}</span>
              </div>
              <div className="p-3 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
                {undated.map(task => <TaskCard key={task.id} task={task} />)}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Task form modal ────────────────────────────────────── */}
      <Modal isOpen={showForm} onClose={() => { setShowForm(false); setForm(emptyForm); }}>
        <div className="modal-card" style={{ maxWidth: '32rem' }}>
          <h3 className="text-xl font-semibold mb-4">
            {form.id ? 'Редактировать задачу' : 'Новая задача'}
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Название *</label>
              <input type="text" className="input-field w-full" placeholder="Что нужно сделать?"
                value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} />
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Описание</label>
              <textarea className="input-field w-full" rows={3} placeholder="Подробности..."
                value={form.description || ''} onChange={e => setForm({ ...form, description: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Дата</label>
                <input type="date" className="input-field w-full"
                  value={form.due_date || ''} onChange={e => setForm({ ...form, due_date: e.target.value })} />
              </div>
              <div>
                <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Время</label>
                <input type="time" className="input-field w-full"
                  value={form.due_time || ''} onChange={e => setForm({ ...form, due_time: e.target.value })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Приоритет</label>
                <select className="input-field w-full" value={form.priority}
                  onChange={e => setForm({ ...form, priority: e.target.value })}>
                  {PRIORITIES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Статус</label>
                <select className="input-field w-full" value={form.status}
                  onChange={e => setForm({ ...form, status: e.target.value })}>
                  {STATUSES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Категория</label>
              <div className="flex gap-2">
                <select className="input-field flex-1" value={form.category || ''}
                  onChange={e => setForm({ ...form, category: e.target.value })}>
                  <option value="">Без категории</option>
                  {categories.map(c => <option key={c.id} value={c.name}>{c.icon} {c.name}</option>)}
                </select>
                <button type="button" className="btn" title="Управление категориями"
                  onClick={() => setShowCatManager(true)}>
                  <Settings2 size={16} />
                </button>
              </div>
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Теги</label>
              <div className="flex gap-1 flex-wrap mb-2">
                {form.tags?.map(tag => (
                  <span key={tag} className="bg-[var(--color-bg)] px-2 py-0.5 rounded text-sm flex items-center gap-1">
                    {tag}
                    <button type="button" onClick={() => removeTag(tag)} className="text-[color:var(--color-text-faint)] hover:text-red-400">&times;</button>
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <input type="text" className="input-field flex-1" placeholder="Добавить тег..."
                  value={tagInput} onChange={e => setTagInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addTag())} />
                <button type="button" className="btn" onClick={addTag}><Plus size={16} /></button>
              </div>
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Напоминание</label>
              <select className="input-field w-full" value={form.reminder_minutes ?? ''}
                onChange={e => setForm({ ...form, reminder_minutes: e.target.value ? parseInt(e.target.value) : null })}>
                <option value="">Без напоминания</option>
                <option value="5">За 5 минут</option>
                <option value="15">За 15 минут</option>
                <option value="30">За 30 минут</option>
                <option value="60">За 1 час</option>
                <option value="1440">За 1 день</option>
              </select>
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button className="btn" onClick={() => { setShowForm(false); setForm(emptyForm); }}>Отмена</button>
            <button className="btn btn--primary" onClick={saveForm}>{form.id ? 'Сохранить' : 'Создать'}</button>
          </div>
        </div>
      </Modal>

      {/* ── Category manager modal ─────────────────────────────── */}
      <Modal isOpen={showCatManager} onClose={() => setShowCatManager(false)}>
        <div className="modal-card" style={{ maxWidth: '28rem' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-xl font-semibold">Категории задач</h3>
            <button className="p-2 hover:bg-[var(--color-bg)] rounded" onClick={() => setShowCatManager(false)}>
              <X size={20} />
            </button>
          </div>
          <div className="space-y-2 mb-4">
            {categories.map(cat => (
              <div key={cat.id} className="flex items-center gap-3 p-3 bg-[var(--color-bg)] rounded-lg">
                <div className="w-9 h-9 rounded-lg flex items-center justify-center text-lg shrink-0"
                  style={{ backgroundColor: cat.color + '22' }}>{cat.icon}</div>
                <span className="flex-1 font-medium">{cat.name}</span>
                <span className="w-4 h-4 rounded-full shrink-0" style={{ backgroundColor: cat.color }} />
                <button onClick={() => { setShowCatManager(false); startEditCat(cat); }}
                  className="p-1.5 hover:bg-[var(--color-bg-secondary)] rounded"><Pencil size={14} /></button>
                <button onClick={() => deleteCat(cat)} className="p-1.5 hover:bg-red-500/20 rounded">
                  <Trash2 size={14} className="text-red-400" /></button>
              </div>
            ))}
            {categories.length === 0 && <div className="text-center py-8 text-[color:var(--color-text-muted)]">Нет категорий</div>}
          </div>
          <button className="btn w-full flex items-center justify-center gap-2"
            onClick={() => { setShowCatManager(false); startCreateCat(); }}>
            <FolderPlus size={18} />Добавить категорию
          </button>
        </div>
      </Modal>

      {/* ── Category form modal ────────────────────────────────── */}
      <Modal isOpen={showCatForm} onClose={() => { setShowCatForm(false); setCatForm(emptyCatForm); }}>
        <div className="modal-card" style={{ maxWidth: '26rem' }}>
          <h3 className="text-xl font-semibold mb-4">
            {catForm.id ? 'Редактировать категорию' : 'Новая категория'}
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-1">Название *</label>
              <input type="text" className="input-field w-full" placeholder="Работа, Личное, Проект..."
                value={catForm.name} onChange={e => setCatForm({ ...catForm, name: e.target.value })} />
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-2">Иконка</label>
              <div className="flex flex-wrap gap-2">
                {DEFAULT_CAT_ICONS.map(icon => (
                  <button key={icon} type="button"
                    className={`w-10 h-10 rounded-lg text-xl flex items-center justify-center
                      ${catForm.icon === icon
                        ? 'bg-[var(--color-primary)] ring-2 ring-[var(--color-primary)]'
                        : 'bg-[var(--color-bg)] hover:bg-[var(--color-bg-secondary)]'}`}
                    onClick={() => setCatForm({ ...catForm, icon })}>{icon}</button>
                ))}
              </div>
            </div>
            <div>
              <label className="block text-sm text-[color:var(--color-text-faint)] mb-2">Цвет</label>
              <div className="flex flex-wrap gap-2">
                {DEFAULT_CAT_COLORS.map(color => (
                  <button key={color} type="button"
                    className={`w-8 h-8 rounded-full transition-transform
                      ${catForm.color === color ? 'ring-2 ring-white ring-offset-2 ring-offset-[var(--color-modal-bg)] scale-110' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => setCatForm({ ...catForm, color })} />
                ))}
              </div>
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-6">
            <button className="btn" onClick={() => { setShowCatForm(false); setCatForm(emptyCatForm); }}>Отмена</button>
            <button className="btn btn--primary" onClick={saveCat}>{catForm.id ? 'Сохранить' : 'Создать'}</button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
