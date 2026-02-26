import { useEffect, useState } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  Check,
  RotateCcw,
  Calendar,
  Clock,
  Flag,
  Tag,
  Filter,
  LayoutGrid,
  List,
  AlertCircle,
  CheckCircle2,
  Circle,
  PlayCircle,
} from 'lucide-react';
import api from '../api';
import Modal from '../components/Modal';

const PRIORITIES = [
  { value: 'low', label: 'Низкий', color: 'bg-gray-500' },
  { value: 'medium', label: 'Средний', color: 'bg-blue-500' },
  { value: 'high', label: 'Высокий', color: 'bg-orange-500' },
  { value: 'urgent', label: 'Срочный', color: 'bg-red-500' },
];

const STATUSES = [
  { value: 'todo', label: 'К выполнению', icon: Circle, color: 'text-gray-400' },
  { value: 'in_progress', label: 'В работе', icon: PlayCircle, color: 'text-blue-400' },
  { value: 'done', label: 'Выполнено', icon: CheckCircle2, color: 'text-green-400' },
];

export default function Tasks() {
  const emptyForm = {
    id: null,
    title: '',
    description: '',
    due_date: '',
    due_time: '',
    priority: 'medium',
    status: 'todo',
    category: '',
    tags: [],
    reminder_minutes: null,
  };

  const [tasks, setTasks] = useState([]);
  const [stats, setStats] = useState({});
  const [categories, setCategories] = useState([]);
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [viewMode, setViewMode] = useState('board'); // 'board' or 'list'
  const [filters, setFilters] = useState({
    status: '',
    priority: '',
    category: '',
    includeDone: true,
  });
  const [tagInput, setTagInput] = useState('');

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    loadTasks();
  }, [filters]);

  async function loadAll() {
    await Promise.all([loadTasks(), loadStats(), loadCategories()]);
  }

  async function loadTasks() {
    try {
      const params = {
        status: filters.status || undefined,
        priority: filters.priority || undefined,
        category: filters.category || undefined,
        include_done: filters.includeDone,
      };
      const res = await api.get('tasks/', { params });
      setTasks(res.data);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    }
  }

  async function loadStats() {
    try {
      const res = await api.get('tasks/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }

  async function loadCategories() {
    try {
      const res = await api.get('tasks/categories');
      setCategories(res.data);
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  }

  function startCreate() {
    setForm({ ...emptyForm, due_date: new Date().toISOString().slice(0, 10) });
    setTagInput('');
    setShowForm(true);
  }

  function startEdit(task) {
    setForm({
      ...task,
      due_date: task.due_date || '',
      due_time: task.due_time ? task.due_time.slice(0, 5) : '',
      tags: task.tags || [],
    });
    setTagInput('');
    setShowForm(true);
  }

  async function saveForm() {
    if (!form.title.trim()) {
      alert('Введите название задачи');
      return;
    }
    try {
      const payload = {
        ...form,
        due_time: form.due_time ? form.due_time + ':00' : null,
        tags: form.tags || [],
      };
      if (form.id) {
        await api.put(`tasks/${form.id}`, payload);
      } else {
        await api.post('tasks/', payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      loadAll();
    } catch (err) {
      console.error('Save error:', err);
      alert('Ошибка сохранения');
    }
  }

  async function deleteTask(id) {
    if (!window.confirm('Удалить задачу?')) return;
    try {
      await api.delete(`tasks/${id}`);
      loadAll();
    } catch (err) {
      console.error('Delete error:', err);
    }
  }

  async function completeTask(id) {
    try {
      await api.post(`tasks/${id}/complete`);
      loadAll();
    } catch (err) {
      console.error('Complete error:', err);
    }
  }

  async function reopenTask(id) {
    try {
      await api.post(`tasks/${id}/reopen`);
      loadAll();
    } catch (err) {
      console.error('Reopen error:', err);
    }
  }

  async function updateTaskStatus(id, status) {
    try {
      await api.put(`tasks/${id}`, { status });
      loadAll();
    } catch (err) {
      console.error('Status update error:', err);
    }
  }

  function addTag() {
    const tag = tagInput.trim();
    if (tag && !form.tags.includes(tag)) {
      setForm({ ...form, tags: [...form.tags, tag] });
    }
    setTagInput('');
  }

  function removeTag(tag) {
    setForm({ ...form, tags: form.tags.filter((t) => t !== tag) });
  }

  function getPriorityInfo(priority) {
    return PRIORITIES.find((p) => p.value === priority) || PRIORITIES[1];
  }

  function getStatusInfo(status) {
    return STATUSES.find((s) => s.value === status) || STATUSES[0];
  }

  function isOverdue(task) {
    if (task.status === 'done' || !task.due_date) return false;
    const today = new Date().toISOString().slice(0, 10);
    return task.due_date < today;
  }

  function isDueToday(task) {
    if (!task.due_date) return false;
    const today = new Date().toISOString().slice(0, 10);
    return task.due_date === today;
  }

  // Group tasks by status for board view
  const tasksByStatus = {
    todo: tasks.filter((t) => t.status === 'todo'),
    in_progress: tasks.filter((t) => t.status === 'in_progress'),
    done: tasks.filter((t) => t.status === 'done'),
  };

  const TaskCard = ({ task }) => {
    const priorityInfo = getPriorityInfo(task.priority);
    const statusInfo = getStatusInfo(task.status);
    const overdue = isOverdue(task);
    const dueToday = isDueToday(task);

    return (
      <div
        className={`bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)] hover:border-[var(--color-primary)] transition-colors ${
          overdue ? 'border-l-4 border-l-red-500' : dueToday ? 'border-l-4 border-l-yellow-500' : ''
        }`}
      >
        <div className="flex items-start justify-between gap-2 mb-2">
          <h4 className={`font-medium ${task.status === 'done' ? 'line-through text-gray-500' : ''}`}>
            {task.title}
          </h4>
          <div className={`w-2 h-2 rounded-full ${priorityInfo.color} shrink-0 mt-2`} title={priorityInfo.label} />
        </div>

        {task.description && (
          <p className="text-sm text-gray-400 mb-3 line-clamp-2">{task.description}</p>
        )}

        <div className="flex flex-wrap gap-1 mb-3">
          {task.tags?.map((tag) => (
            <span key={tag} className="text-xs bg-[var(--color-bg)] px-2 py-0.5 rounded">
              {tag}
            </span>
          ))}
          {task.category && (
            <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
              {task.category}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between text-xs text-gray-400">
          <div className="flex items-center gap-2">
            {task.due_date && (
              <span className={`flex items-center gap-1 ${overdue ? 'text-red-400' : dueToday ? 'text-yellow-400' : ''}`}>
                <Calendar size={12} />
                {task.due_date}
              </span>
            )}
            {task.due_time && (
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {task.due_time.slice(0, 5)}
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            {task.status !== 'done' ? (
              <button
                onClick={() => completeTask(task.id)}
                className="p-1 hover:bg-green-500/20 rounded"
                title="Выполнено"
              >
                <Check size={14} className="text-green-400" />
              </button>
            ) : (
              <button
                onClick={() => reopenTask(task.id)}
                className="p-1 hover:bg-blue-500/20 rounded"
                title="Вернуть в работу"
              >
                <RotateCcw size={14} className="text-blue-400" />
              </button>
            )}
            <button
              onClick={() => startEdit(task)}
              className="p-1 hover:bg-[var(--color-bg)] rounded"
              title="Редактировать"
            >
              <Pencil size={14} />
            </button>
            <button
              onClick={() => deleteTask(task.id)}
              className="p-1 hover:bg-red-500/20 rounded"
              title="Удалить"
            >
              <Trash2 size={14} className="text-red-400" />
            </button>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 max-w-full mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h2 className="text-2xl font-semibold">Задачи</h2>
        <button className="btn btn--primary flex items-center gap-2" onClick={startCreate}>
          <Plus size={18} />
          Новая задача
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold">{stats.total || 0}</div>
          <div className="text-sm text-gray-400">Всего</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-gray-400">{stats.todo || 0}</div>
          <div className="text-sm text-gray-400">К выполнению</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-blue-400">{stats.in_progress || 0}</div>
          <div className="text-sm text-gray-400">В работе</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-green-400">{stats.done || 0}</div>
          <div className="text-sm text-gray-400">Выполнено</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-red-400">{stats.overdue || 0}</div>
          <div className="text-sm text-gray-400">Просрочено</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-yellow-400">{stats.due_today || 0}</div>
          <div className="text-sm text-gray-400">На сегодня</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-purple-400">{stats.due_this_week || 0}</div>
          <div className="text-sm text-gray-400">На неделю</div>
        </div>
      </div>

      {/* Filters and View Toggle */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <Filter size={16} />
          Фильтры:
        </div>
        <select
          className="input-field text-sm"
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
        >
          <option value="">Все статусы</option>
          {STATUSES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <select
          className="input-field text-sm"
          value={filters.priority}
          onChange={(e) => setFilters({ ...filters, priority: e.target.value })}
        >
          <option value="">Все приоритеты</option>
          {PRIORITIES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <select
          className="input-field text-sm"
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
        >
          <option value="">Все категории</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.includeDone}
            onChange={(e) => setFilters({ ...filters, includeDone: e.target.checked })}
          />
          Показать выполненные
        </label>

        <div className="ml-auto flex items-center gap-1 bg-[var(--color-bg-secondary)] rounded-lg p-1">
          <button
            className={`p-2 rounded ${viewMode === 'board' ? 'bg-[var(--color-primary)]' : ''}`}
            onClick={() => setViewMode('board')}
            title="Доска"
          >
            <LayoutGrid size={16} />
          </button>
          <button
            className={`p-2 rounded ${viewMode === 'list' ? 'bg-[var(--color-primary)]' : ''}`}
            onClick={() => setViewMode('list')}
            title="Список"
          >
            <List size={16} />
          </button>
        </div>
      </div>

      {/* Board View */}
      {viewMode === 'board' && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {STATUSES.map((status) => {
            const StatusIcon = status.icon;
            const statusTasks = tasksByStatus[status.value] || [];
            return (
              <div key={status.value} className="bg-[var(--color-bg)] rounded-lg p-4">
                <div className={`flex items-center gap-2 mb-4 ${status.color}`}>
                  <StatusIcon size={18} />
                  <h3 className="font-medium">{status.label}</h3>
                  <span className="ml-auto bg-[var(--color-bg-secondary)] px-2 py-0.5 rounded text-sm">
                    {statusTasks.length}
                  </span>
                </div>
                <div className="space-y-3">
                  {statusTasks.map((task) => (
                    <TaskCard key={task.id} task={task} />
                  ))}
                  {statusTasks.length === 0 && (
                    <div className="text-center text-gray-500 py-8">Нет задач</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* List View */}
      {viewMode === 'list' && (
        <div className="bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left text-sm text-gray-400">
                <th className="p-3">Задача</th>
                <th className="p-3 hidden md:table-cell">Категория</th>
                <th className="p-3">Срок</th>
                <th className="p-3">Приоритет</th>
                <th className="p-3">Статус</th>
                <th className="p-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => {
                const priorityInfo = getPriorityInfo(task.priority);
                const statusInfo = getStatusInfo(task.status);
                const StatusIcon = statusInfo.icon;
                const overdue = isOverdue(task);
                const dueToday = isDueToday(task);

                return (
                  <tr
                    key={task.id}
                    className={`border-b border-[var(--color-border)] hover:bg-[var(--color-bg)] ${
                      overdue ? 'bg-red-500/5' : dueToday ? 'bg-yellow-500/5' : ''
                    }`}
                  >
                    <td className="p-3">
                      <div className={task.status === 'done' ? 'line-through text-gray-500' : ''}>
                        {task.title}
                      </div>
                      {task.description && (
                        <div className="text-xs text-gray-400 truncate max-w-xs">{task.description}</div>
                      )}
                    </td>
                    <td className="p-3 hidden md:table-cell">
                      {task.category && (
                        <span className="text-xs bg-purple-500/20 text-purple-300 px-2 py-0.5 rounded">
                          {task.category}
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      {task.due_date && (
                        <div className={`text-sm ${overdue ? 'text-red-400' : dueToday ? 'text-yellow-400' : ''}`}>
                          {task.due_date}
                          {task.due_time && <span className="ml-1 text-gray-400">{task.due_time.slice(0, 5)}</span>}
                        </div>
                      )}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${priorityInfo.color}`} />
                        <span className="text-sm hidden lg:inline">{priorityInfo.label}</span>
                      </div>
                    </td>
                    <td className="p-3">
                      <select
                        className="input-field text-sm py-1"
                        value={task.status}
                        onChange={(e) => updateTaskStatus(task.id, e.target.value)}
                      >
                        {STATUSES.map((s) => (
                          <option key={s.value} value={s.value}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="p-3">
                      <div className="flex items-center justify-end gap-1">
                        {task.status !== 'done' ? (
                          <button
                            onClick={() => completeTask(task.id)}
                            className="p-1.5 hover:bg-green-500/20 rounded"
                            title="Выполнено"
                          >
                            <Check size={16} className="text-green-400" />
                          </button>
                        ) : (
                          <button
                            onClick={() => reopenTask(task.id)}
                            className="p-1.5 hover:bg-blue-500/20 rounded"
                            title="Вернуть в работу"
                          >
                            <RotateCcw size={16} className="text-blue-400" />
                          </button>
                        )}
                        <button
                          onClick={() => startEdit(task)}
                          className="p-1.5 hover:bg-[var(--color-bg)] rounded"
                          title="Редактировать"
                        >
                          <Pencil size={16} />
                        </button>
                        <button
                          onClick={() => deleteTask(task.id)}
                          className="p-1.5 hover:bg-red-500/20 rounded"
                          title="Удалить"
                        >
                          <Trash2 size={16} className="text-red-400" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {tasks.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-gray-500">
                    Нет задач
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Create/Edit Modal */}
      <Modal isOpen={showForm}>
        <div className="modal-card" style={{ maxWidth: '32rem' }}>
            <h3 className="text-xl font-semibold mb-4">
              {form.id ? 'Редактировать задачу' : 'Новая задача'}
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Название *</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  placeholder="Что нужно сделать?"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Описание</label>
                <textarea
                  className="input-field w-full"
                  rows={3}
                  value={form.description || ''}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  placeholder="Подробности задачи..."
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Дата</label>
                  <input
                    type="date"
                    className="input-field w-full"
                    value={form.due_date || ''}
                    onChange={(e) => setForm({ ...form, due_date: e.target.value })}
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Время</label>
                  <input
                    type="time"
                    className="input-field w-full"
                    value={form.due_time || ''}
                    onChange={(e) => setForm({ ...form, due_time: e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Приоритет</label>
                  <select
                    className="input-field w-full"
                    value={form.priority}
                    onChange={(e) => setForm({ ...form, priority: e.target.value })}
                  >
                    {PRIORITIES.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Статус</label>
                  <select
                    className="input-field w-full"
                    value={form.status}
                    onChange={(e) => setForm({ ...form, status: e.target.value })}
                  >
                    {STATUSES.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Категория</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={form.category || ''}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                  placeholder="Работа, Личное, Проект..."
                  list="category-suggestions"
                />
                <datalist id="category-suggestions">
                  {categories.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Теги</label>
                <div className="flex gap-2 mb-2 flex-wrap">
                  {form.tags?.map((tag) => (
                    <span
                      key={tag}
                      className="bg-[var(--color-bg)] px-2 py-1 rounded text-sm flex items-center gap-1"
                    >
                      {tag}
                      <button
                        type="button"
                        onClick={() => removeTag(tag)}
                        className="text-gray-400 hover:text-red-400"
                      >
                        &times;
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="input-field flex-1"
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addTag())}
                    placeholder="Добавить тег..."
                  />
                  <button type="button" className="btn" onClick={addTag}>
                    <Plus size={16} />
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Напоминание (минут до срока)</label>
                <select
                  className="input-field w-full"
                  value={form.reminder_minutes ?? ''}
                  onChange={(e) =>
                    setForm({ ...form, reminder_minutes: e.target.value ? parseInt(e.target.value) : null })
                  }
                >
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
              <button
                className="btn"
                onClick={() => {
                  setShowForm(false);
                  setForm(emptyForm);
                }}
              >
                Отмена
              </button>
              <button className="btn btn--primary" onClick={saveForm}>
                {form.id ? 'Сохранить' : 'Создать'}
              </button>
            </div>
          </div>
      </Modal>
    </div>
  );
}
