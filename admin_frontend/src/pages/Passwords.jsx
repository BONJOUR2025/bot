import { useEffect, useState } from 'react';
import {
  Plus,
  Pencil,
  Trash2,
  Star,
  Copy,
  Eye,
  EyeOff,
  Search,
  FolderPlus,
  Key,
  RefreshCw,
  ExternalLink,
  Settings2,
  X,
  Check,
  Grip,
} from 'lucide-react';
import api from '../api';
import Modal from '../components/Modal';

const DEFAULT_CATEGORY_COLORS = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316',
  '#eab308', '#22c55e', '#14b8a6', '#06b6d4', '#3b82f6',
];

const DEFAULT_CATEGORY_ICONS = ['🔐', '💼', '🏠', '💳', '🎮', '📱', '💻', '🌐', '📧', '🛒'];

export default function Passwords() {
  const emptyEntryForm = {
    id: null,
    title: '',
    username: '',
    password: '',
    url: '',
    category: '',
    notes: '',
    is_favorite: false,
  };

  const emptyCategoryForm = {
    id: null,
    name: '',
    icon: '🔐',
    color: '#6366f1',
  };

  const [entries, setEntries] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stats, setStats] = useState({});
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [entryForm, setEntryForm] = useState(emptyEntryForm);
  const [showEntryForm, setShowEntryForm] = useState(false);
  const [categoryForm, setCategoryForm] = useState(emptyCategoryForm);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [showCategoryManager, setShowCategoryManager] = useState(false);
  const [visiblePasswords, setVisiblePasswords] = useState(new Set());
  const [copiedId, setCopiedId] = useState(null);

  // Password generator state
  const [showGenerator, setShowGenerator] = useState(false);
  const [genLength, setGenLength] = useState(16);
  const [genUppercase, setGenUppercase] = useState(true);
  const [genLowercase, setGenLowercase] = useState(true);
  const [genDigits, setGenDigits] = useState(true);
  const [genSymbols, setGenSymbols] = useState(true);
  const [genExcludeAmbiguous, setGenExcludeAmbiguous] = useState(false);
  const [generatedPassword, setGeneratedPassword] = useState('');

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    loadEntries();
  }, [search, selectedCategory, favoritesOnly]);

  async function loadAll() {
    await Promise.all([loadEntries(), loadCategories(), loadStats()]);
  }

  async function loadEntries() {
    try {
      const params = {
        search: search || undefined,
        category: selectedCategory || undefined,
        favorites_only: favoritesOnly || undefined,
      };
      const res = await api.get('passwords/entries', { params });
      setEntries(res.data);
    } catch (err) {
      console.error('Failed to load entries:', err);
    }
  }

  async function loadCategories() {
    try {
      const res = await api.get('passwords/categories');
      setCategories(res.data);
    } catch (err) {
      console.error('Failed to load categories:', err);
    }
  }

  async function loadStats() {
    try {
      const res = await api.get('passwords/stats');
      setStats(res.data);
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }

  // Entry CRUD
  function startCreateEntry() {
    setEntryForm({ ...emptyEntryForm, category: selectedCategory });
    setShowEntryForm(true);
  }

  function startEditEntry(entry) {
    setEntryForm({ ...entry });
    setShowEntryForm(true);
  }

  async function saveEntry() {
    if (!entryForm.title.trim() || !entryForm.password) {
      alert('Заполните название и пароль');
      return;
    }
    try {
      if (entryForm.id) {
        await api.put(`passwords/entries/${entryForm.id}`, entryForm);
      } else {
        await api.post('passwords/entries', entryForm);
      }
      setShowEntryForm(false);
      setEntryForm(emptyEntryForm);
      loadAll();
    } catch (err) {
      console.error('Save error:', err);
      alert('Ошибка сохранения');
    }
  }

  async function deleteEntry(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`passwords/entries/${id}`);
      loadAll();
    } catch (err) {
      console.error('Delete error:', err);
    }
  }

  async function toggleFavorite(id) {
    try {
      await api.post(`passwords/entries/${id}/toggle-favorite`);
      loadAll();
    } catch (err) {
      console.error('Toggle favorite error:', err);
    }
  }

  // Category CRUD
  function startCreateCategory() {
    setCategoryForm({ ...emptyCategoryForm });
    setShowCategoryForm(true);
  }

  function startEditCategory(cat) {
    setCategoryForm({ ...cat });
    setShowCategoryForm(true);
  }

  async function saveCategory() {
    if (!categoryForm.name.trim()) {
      alert('Введите название категории');
      return;
    }
    try {
      if (categoryForm.id) {
        await api.put(`passwords/categories/${categoryForm.id}`, categoryForm);
      } else {
        await api.post('passwords/categories', categoryForm);
      }
      setShowCategoryForm(false);
      setCategoryForm(emptyCategoryForm);
      loadAll();
    } catch (err) {
      console.error('Save category error:', err);
      alert('Ошибка сохранения');
    }
  }

  async function deleteCategory(id, deleteEntries = false) {
    const message = deleteEntries
      ? 'Удалить категорию вместе со всеми записями?'
      : 'Удалить категорию? Записи будут перемещены в "Без категории".';
    if (!window.confirm(message)) return;
    try {
      await api.delete(`passwords/categories/${id}`, { params: { delete_entries: deleteEntries } });
      if (selectedCategory) {
        const cat = categories.find(c => c.id === id);
        if (cat && cat.name === selectedCategory) {
          setSelectedCategory('');
        }
      }
      loadAll();
    } catch (err) {
      console.error('Delete category error:', err);
    }
  }

  // Password visibility
  function togglePasswordVisibility(id) {
    setVisiblePasswords(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  // Copy to clipboard
  async function copyToClipboard(text, id) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  }

  // Password generator
  async function generatePassword() {
    try {
      const res = await api.post('passwords/generate', {
        length: genLength,
        use_uppercase: genUppercase,
        use_lowercase: genLowercase,
        use_digits: genDigits,
        use_symbols: genSymbols,
        exclude_ambiguous: genExcludeAmbiguous,
      });
      setGeneratedPassword(res.data.password);
    } catch (err) {
      console.error('Generate password error:', err);
    }
  }

  function useGeneratedPassword() {
    setEntryForm({ ...entryForm, password: generatedPassword });
    setShowGenerator(false);
    setGeneratedPassword('');
  }

  // Get category info
  function getCategoryInfo(name) {
    return categories.find(c => c.name === name);
  }

  // Group entries by category
  const entriesByCategory = {};
  for (const entry of entries) {
    const cat = entry.category || 'Без категории';
    if (!entriesByCategory[cat]) {
      entriesByCategory[cat] = [];
    }
    entriesByCategory[cat].push(entry);
  }

  const sortedCategoryNames = Object.keys(entriesByCategory).sort((a, b) => {
    if (a === 'Без категории') return 1;
    if (b === 'Без категории') return -1;
    const catA = getCategoryInfo(a);
    const catB = getCategoryInfo(b);
    return (catA?.order || 0) - (catB?.order || 0);
  });

  return (
    <div className="space-y-6 max-w-full mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h2 className="text-2xl font-semibold">Хранилище паролей</h2>
        <div className="flex gap-2">
          <button
            className="btn flex items-center gap-2"
            onClick={() => setShowCategoryManager(true)}
          >
            <Settings2 size={18} />
            Категории
          </button>
          <button className="btn btn--primary flex items-center gap-2" onClick={startCreateEntry}>
            <Plus size={18} />
            Добавить
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold">{stats.total_entries || 0}</div>
          <div className="text-sm text-gray-400">Всего записей</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-purple-400">{stats.total_categories || 0}</div>
          <div className="text-sm text-gray-400">Категорий</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-yellow-400">{stats.favorites_count || 0}</div>
          <div className="text-sm text-gray-400">Избранное</div>
        </div>
        <div className="bg-[var(--color-bg-secondary)] rounded-lg p-4 border border-[var(--color-border)]">
          <div className="text-2xl font-bold text-green-400">
            <Key size={24} />
          </div>
          <div className="text-sm text-gray-400">Защищено</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={18} />
          <input
            type="text"
            className="input-field w-full pl-10"
            placeholder="Поиск..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          className="input-field"
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
        >
          <option value="">Все категории</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.name}>
              {cat.icon} {cat.name}
            </option>
          ))}
          <option value="Без категории">Без категории</option>
        </select>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={favoritesOnly}
            onChange={(e) => setFavoritesOnly(e.target.checked)}
          />
          <Star size={16} className="text-yellow-400" />
          Избранное
        </label>
      </div>

      {/* Entries by category */}
      <div className="space-y-6">
        {sortedCategoryNames.map((catName) => {
          const catInfo = getCategoryInfo(catName);
          const catEntries = entriesByCategory[catName];

          return (
            <div key={catName} className="bg-[var(--color-bg-secondary)] rounded-lg border border-[var(--color-border)] overflow-hidden">
              <div
                className="px-4 py-3 border-b border-[var(--color-border)] flex items-center gap-2"
                style={{ borderLeftWidth: '4px', borderLeftColor: catInfo?.color || '#6b7280' }}
              >
                <span className="text-lg">{catInfo?.icon || '📁'}</span>
                <h3 className="font-medium">{catName}</h3>
                <span className="ml-auto text-sm text-gray-400">{catEntries.length}</span>
              </div>

              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-sm text-gray-400">
                    <th className="p-3 w-10"></th>
                    <th className="p-3">Название</th>
                    <th className="p-3 hidden md:table-cell">Логин</th>
                    <th className="p-3">Пароль</th>
                    <th className="p-3 hidden lg:table-cell">URL</th>
                    <th className="p-3 text-right">Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {catEntries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-[var(--color-border)] hover:bg-[var(--color-bg)]"
                    >
                      <td className="p-3">
                        <button
                          onClick={() => toggleFavorite(entry.id)}
                          className={`p-1 rounded ${entry.is_favorite ? 'text-yellow-400' : 'text-gray-500 hover:text-yellow-400'}`}
                        >
                          <Star size={16} fill={entry.is_favorite ? 'currentColor' : 'none'} />
                        </button>
                      </td>
                      <td className="p-3">
                        <div className="font-medium">{entry.title}</div>
                        {entry.notes && (
                          <div className="text-xs text-gray-400 truncate max-w-[200px]">{entry.notes}</div>
                        )}
                      </td>
                      <td className="p-3 hidden md:table-cell">
                        {entry.username && (
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-sm">{entry.username}</span>
                            <button
                              onClick={() => copyToClipboard(entry.username, `user-${entry.id}`)}
                              className="p-1 hover:bg-[var(--color-bg-secondary)] rounded"
                              title="Копировать"
                            >
                              {copiedId === `user-${entry.id}` ? (
                                <Check size={14} className="text-green-400" />
                              ) : (
                                <Copy size={14} className="text-gray-400" />
                              )}
                            </button>
                          </div>
                        )}
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm">
                            {visiblePasswords.has(entry.id) ? entry.password : '••••••••'}
                          </span>
                          <button
                            onClick={() => togglePasswordVisibility(entry.id)}
                            className="p-1 hover:bg-[var(--color-bg-secondary)] rounded"
                            title={visiblePasswords.has(entry.id) ? 'Скрыть' : 'Показать'}
                          >
                            {visiblePasswords.has(entry.id) ? (
                              <EyeOff size={14} className="text-gray-400" />
                            ) : (
                              <Eye size={14} className="text-gray-400" />
                            )}
                          </button>
                          <button
                            onClick={() => copyToClipboard(entry.password, `pass-${entry.id}`)}
                            className="p-1 hover:bg-[var(--color-bg-secondary)] rounded"
                            title="Копировать"
                          >
                            {copiedId === `pass-${entry.id}` ? (
                              <Check size={14} className="text-green-400" />
                            ) : (
                              <Copy size={14} className="text-gray-400" />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="p-3 hidden lg:table-cell">
                        {entry.url && (
                          <a
                            href={entry.url.startsWith('http') ? entry.url : `https://${entry.url}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-blue-400 hover:underline text-sm"
                          >
                            <ExternalLink size={14} />
                            <span className="truncate max-w-[150px]">{entry.url}</span>
                          </a>
                        )}
                      </td>
                      <td className="p-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => startEditEntry(entry)}
                            className="p-1.5 hover:bg-[var(--color-bg)] rounded"
                            title="Редактировать"
                          >
                            <Pencil size={16} />
                          </button>
                          <button
                            onClick={() => deleteEntry(entry.id)}
                            className="p-1.5 hover:bg-red-500/20 rounded"
                            title="Удалить"
                          >
                            <Trash2 size={16} className="text-red-400" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        })}

        {entries.length === 0 && (
          <div className="text-center py-12 text-gray-500">
            <Key size={48} className="mx-auto mb-4 opacity-50" />
            <p>Нет сохранённых паролей</p>
            <button className="btn btn--primary mt-4" onClick={startCreateEntry}>
              Добавить первый
            </button>
          </div>
        )}
      </div>

      {/* Entry Form Modal */}
      <Modal isOpen={showEntryForm}>
        <div className="modal-card" style={{ maxWidth: '32rem' }}>
            <h3 className="text-xl font-semibold mb-4">
              {entryForm.id ? 'Редактировать запись' : 'Новая запись'}
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Название *</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={entryForm.title}
                  onChange={(e) => setEntryForm({ ...entryForm, title: e.target.value })}
                  placeholder="Google, GitHub, Bank..."
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Логин / Email</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={entryForm.username || ''}
                  onChange={(e) => setEntryForm({ ...entryForm, username: e.target.value })}
                  placeholder="user@email.com"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Пароль *</label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    className="input-field flex-1 font-mono"
                    value={entryForm.password}
                    onChange={(e) => setEntryForm({ ...entryForm, password: e.target.value })}
                    placeholder="••••••••"
                  />
                  <button
                    type="button"
                    className="btn"
                    onClick={() => setShowGenerator(true)}
                    title="Сгенерировать"
                  >
                    <Key size={18} />
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">URL</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={entryForm.url || ''}
                  onChange={(e) => setEntryForm({ ...entryForm, url: e.target.value })}
                  placeholder="https://example.com"
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Категория</label>
                <div className="flex gap-2">
                  <select
                    className="input-field flex-1"
                    value={entryForm.category || ''}
                    onChange={(e) => setEntryForm({ ...entryForm, category: e.target.value })}
                  >
                    <option value="">Без категории</option>
                    {categories.map((cat) => (
                      <option key={cat.id} value={cat.name}>
                        {cat.icon} {cat.name}
                      </option>
                    ))}
                  </select>
                  <button type="button" className="btn" onClick={startCreateCategory}>
                    <FolderPlus size={18} />
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-1">Заметки</label>
                <textarea
                  className="input-field w-full"
                  rows={3}
                  value={entryForm.notes || ''}
                  onChange={(e) => setEntryForm({ ...entryForm, notes: e.target.value })}
                  placeholder="Дополнительная информация..."
                />
              </div>

              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={entryForm.is_favorite || false}
                  onChange={(e) => setEntryForm({ ...entryForm, is_favorite: e.target.checked })}
                />
                <Star size={16} className="text-yellow-400" />
                Добавить в избранное
              </label>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                className="btn"
                onClick={() => {
                  setShowEntryForm(false);
                  setEntryForm(emptyEntryForm);
                }}
              >
                Отмена
              </button>
              <button className="btn btn--primary" onClick={saveEntry}>
                {entryForm.id ? 'Сохранить' : 'Создать'}
              </button>
            </div>
          </div>
      </Modal>

      {/* Password Generator Modal */}
      <Modal isOpen={showGenerator}>
        <div className="modal-card" style={{ maxWidth: '28rem' }}>
            <h3 className="text-xl font-semibold mb-4">Генератор паролей</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Длина: {genLength}</label>
                <input
                  type="range"
                  min="8"
                  max="64"
                  value={genLength}
                  onChange={(e) => setGenLength(parseInt(e.target.value))}
                  className="w-full"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={genUppercase}
                    onChange={(e) => setGenUppercase(e.target.checked)}
                  />
                  A-Z
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={genLowercase}
                    onChange={(e) => setGenLowercase(e.target.checked)}
                  />
                  a-z
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={genDigits}
                    onChange={(e) => setGenDigits(e.target.checked)}
                  />
                  0-9
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={genSymbols}
                    onChange={(e) => setGenSymbols(e.target.checked)}
                  />
                  !@#$%
                </label>
              </div>

              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={genExcludeAmbiguous}
                  onChange={(e) => setGenExcludeAmbiguous(e.target.checked)}
                />
                Исключить похожие (0, O, l, 1, I)
              </label>

              <button
                className="btn w-full flex items-center justify-center gap-2"
                onClick={generatePassword}
              >
                <RefreshCw size={18} />
                Сгенерировать
              </button>

              {generatedPassword && (
                <div className="bg-[var(--color-bg)] p-3 rounded-lg">
                  <div className="flex items-center gap-2">
                    <code className="flex-1 font-mono text-lg break-all">{generatedPassword}</code>
                    <button
                      onClick={() => copyToClipboard(generatedPassword, 'generated')}
                      className="p-2 hover:bg-[var(--color-bg-secondary)] rounded"
                    >
                      {copiedId === 'generated' ? (
                        <Check size={18} className="text-green-400" />
                      ) : (
                        <Copy size={18} />
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                className="btn"
                onClick={() => {
                  setShowGenerator(false);
                  setGeneratedPassword('');
                }}
              >
                Закрыть
              </button>
              {generatedPassword && (
                <button className="btn btn--primary" onClick={useGeneratedPassword}>
                  Использовать
                </button>
              )}
            </div>
          </div>
      </Modal>

      {/* Category Form Modal */}
      <Modal isOpen={showCategoryForm}>
        <div className="modal-card" style={{ maxWidth: '28rem' }}>
            <h3 className="text-xl font-semibold mb-4">
              {categoryForm.id ? 'Редактировать категорию' : 'Новая категория'}
            </h3>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Название *</label>
                <input
                  type="text"
                  className="input-field w-full"
                  value={categoryForm.name}
                  onChange={(e) => setCategoryForm({ ...categoryForm, name: e.target.value })}
                  placeholder="Работа, Личное, Банки..."
                />
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Иконка</label>
                <div className="flex flex-wrap gap-2">
                  {DEFAULT_CATEGORY_ICONS.map((icon) => (
                    <button
                      key={icon}
                      type="button"
                      className={`w-10 h-10 rounded-lg text-xl flex items-center justify-center ${
                        categoryForm.icon === icon
                          ? 'bg-[var(--color-primary)] ring-2 ring-[var(--color-primary)]'
                          : 'bg-[var(--color-bg)] hover:bg-[var(--color-bg-secondary)]'
                      }`}
                      onClick={() => setCategoryForm({ ...categoryForm, icon })}
                    >
                      {icon}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-sm text-gray-400 mb-2">Цвет</label>
                <div className="flex flex-wrap gap-2">
                  {DEFAULT_CATEGORY_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      className={`w-8 h-8 rounded-full ${
                        categoryForm.color === color ? 'ring-2 ring-white ring-offset-2 ring-offset-[var(--color-bg-secondary)]' : ''
                      }`}
                      style={{ backgroundColor: color }}
                      onClick={() => setCategoryForm({ ...categoryForm, color })}
                    />
                  ))}
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button
                className="btn"
                onClick={() => {
                  setShowCategoryForm(false);
                  setCategoryForm(emptyCategoryForm);
                }}
              >
                Отмена
              </button>
              <button className="btn btn--primary" onClick={saveCategory}>
                {categoryForm.id ? 'Сохранить' : 'Создать'}
              </button>
            </div>
          </div>
      </Modal>

      {/* Category Manager Modal */}
      <Modal isOpen={showCategoryManager}>
        <div className="modal-card" style={{ maxWidth: '32rem' }}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-semibold">Управление категориями</h3>
              <button
                className="p-2 hover:bg-[var(--color-bg)] rounded"
                onClick={() => setShowCategoryManager(false)}
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-2 mb-4">
              {categories.map((cat) => (
                <div
                  key={cat.id}
                  className="flex items-center gap-3 p-3 bg-[var(--color-bg)] rounded-lg"
                >
                  <div
                    className="w-8 h-8 rounded flex items-center justify-center text-lg"
                    style={{ backgroundColor: cat.color + '20' }}
                  >
                    {cat.icon}
                  </div>
                  <span className="flex-1 font-medium">{cat.name}</span>
                  <span className="text-sm text-gray-400">
                    {stats.entries_by_category?.[cat.name] || 0}
                  </span>
                  <button
                    onClick={() => {
                      setShowCategoryManager(false);
                      startEditCategory(cat);
                    }}
                    className="p-1.5 hover:bg-[var(--color-bg-secondary)] rounded"
                  >
                    <Pencil size={16} />
                  </button>
                  <button
                    onClick={() => deleteCategory(cat.id, false)}
                    className="p-1.5 hover:bg-red-500/20 rounded"
                  >
                    <Trash2 size={16} className="text-red-400" />
                  </button>
                </div>
              ))}

              {categories.length === 0 && (
                <div className="text-center py-8 text-gray-500">
                  Нет категорий
                </div>
              )}
            </div>

            <button
              className="btn w-full flex items-center justify-center gap-2"
              onClick={() => {
                setShowCategoryManager(false);
                startCreateCategory();
              }}
            >
              <FolderPlus size={18} />
              Добавить категорию
            </button>
          </div>
      </Modal>
    </div>
  );
}
