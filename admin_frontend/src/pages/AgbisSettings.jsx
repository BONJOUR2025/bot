import { useState, useEffect, useMemo } from 'react';
import { Search, RefreshCw, SlidersHorizontal, GitCompareArrows, Monitor, ChevronDown, ChevronRight } from 'lucide-react';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import { StatCard } from '../components/ui/SalaryUI.jsx';

function formatValue(value) {
  if (value === null || value === undefined) return null;
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  if (value === '') return null;
  return String(value);
}

// Whether an option's effective value actually differs across computers —
// drives both the "только различающиеся" filter and the per-row accent.
function hasDiff(values, computerIds) {
  const seen = new Set();
  for (const id of computerIds) {
    seen.add(JSON.stringify(values[id]?.value ?? null));
    if (seen.size > 1) return true;
  }
  return false;
}

// Most common value for a row, so outlier cells (the odd PC out) can be
// highlighted instead of just showing raw values side by side.
function majorityValue(values, computerIds) {
  const counts = new Map();
  for (const id of computerIds) {
    const key = JSON.stringify(values[id]?.value ?? null);
    counts.set(key, (counts.get(key) || 0) + 1);
  }
  let best = null, bestCount = -1;
  for (const [key, count] of counts) {
    if (count > bestCount) { best = key; bestCount = count; }
  }
  return best;
}

function OptionRow({ option, computers }) {
  const majority = useMemo(() => majorityValue(option.values, computers.map((c) => c.id)), [option, computers]);
  const diff = useMemo(() => hasDiff(option.values, computers.map((c) => c.id)), [option, computers]);

  return (
    <tr className={diff ? 'bg-amber-50/60 dark:bg-amber-900/10' : ''}>
      <td className="sticky left-0 z-10 bg-[color:var(--color-card)] px-3 py-2 border-r border-[color:var(--color-border)] min-w-[260px] max-w-[320px]">
        <div className="text-sm font-medium truncate" title={option.short_descr || option.option_name}>
          {option.short_descr || option.option_name}
        </div>
        <div className="text-[10px] text-[color:var(--color-muted-foreground)] font-mono truncate">
          {option.option_name}
          {!option.short_descr && option.group && <span className="font-sans"> · {option.group}</span>}
        </div>
      </td>
      {computers.map((c) => {
        const cell = option.values[c.id] || {};
        const label = formatValue(cell.value);
        const isOutlier = diff && JSON.stringify(cell.value ?? null) !== majority;
        return (
          <td
            key={c.id}
            className={`px-3 py-2 text-xs text-center whitespace-nowrap ${isOutlier ? 'bg-amber-100 dark:bg-amber-900/30 font-semibold' : ''}`}
            title={cell.source === 'override' ? 'Переопределено на этом ПК' : cell.source === 'default' ? 'Значение по умолчанию' : ''}
          >
            {label === null ? (
              <span className="text-[color:var(--color-muted-foreground)]">—</span>
            ) : label === 'Да' ? (
              <span className="text-green-700 dark:text-green-400">{label}</span>
            ) : label === 'Нет' ? (
              <span className="text-[color:var(--color-muted-foreground)]">{label}</span>
            ) : (
              label
            )}
          </td>
        );
      })}
    </tr>
  );
}

function CategorySection({ category, computers, open, onToggle }) {
  const diffCount = useMemo(
    () => category.options.filter((o) => hasDiff(o.values, computers.map((c) => c.id))).length,
    [category, computers]
  );

  return (
    <div className="app-card overflow-hidden">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between gap-2 px-4 py-3 text-left hover:bg-[color:var(--color-muted)]/30"
      >
        <div className="flex items-center gap-2 min-w-0">
          {open ? <ChevronDown size={16} className="shrink-0 text-[color:var(--color-muted-foreground)]" /> : <ChevronRight size={16} className="shrink-0 text-[color:var(--color-muted-foreground)]" />}
          <h3 className="text-sm font-semibold truncate">{category.name}</h3>
        </div>
        <div className="flex items-center gap-2 shrink-0 text-xs text-[color:var(--color-muted-foreground)]">
          <span>{category.options.length} настроек</span>
          {diffCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 font-medium">
              {diffCount} различаются
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className="overflow-x-auto border-t border-[color:var(--color-border)]">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="bg-[color:var(--color-muted)]/30">
                <th className="sticky left-0 z-10 bg-[color:var(--color-card)] px-3 py-2 text-left text-xs font-medium border-r border-[color:var(--color-border)] min-w-[260px]">
                  Настройка
                </th>
                {computers.map((c) => (
                  <th key={c.id} className="px-3 py-2 text-xs font-medium text-center whitespace-nowrap" title={c.db_name || ''}>
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {category.options.map((o) => (
                <OptionRow key={o.id} option={o} computers={computers} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function AgbisSettings() {
  const [data, setData]       = useState({ computers: [], categories: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [query, setQuery]     = useState('');
  const [onlyDiff, setOnlyDiff] = useState(false);
  const [openCats, setOpenCats] = useState(() => new Set());

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('agbis-settings/');
      setData(res.data && Array.isArray(res.data.categories) ? res.data : { computers: [], categories: [] });
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }

  const computers = data.computers;

  const filteredCategories = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ids = computers.map((c) => c.id);
    return data.categories
      .map((cat) => {
        let options = cat.options;
        if (q) {
          options = options.filter((o) =>
            (o.option_name || '').toLowerCase().includes(q) ||
            (o.short_descr || '').toLowerCase().includes(q)
          );
        }
        if (onlyDiff) {
          options = options.filter((o) => hasDiff(o.values, ids));
        }
        return { ...cat, options };
      })
      .filter((cat) => cat.options.length > 0);
  }, [data.categories, computers, query, onlyDiff]);

  const totalOptions = data.categories.reduce((sum, c) => sum + c.options.length, 0);
  const totalDiffs = useMemo(() => {
    const ids = computers.map((c) => c.id);
    return data.categories.reduce((sum, c) => sum + c.options.filter((o) => hasDiff(o.values, ids)).length, 0);
  }, [data.categories, computers]);

  function toggleCat(name) {
    setOpenCats((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  return (
    <div className="space-y-6 max-w-full pb-20">
      <TopProgressBar active={loading} />
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-2xl font-semibold tracking-tight flex-1 min-w-0">Настройки АГБИС</h2>
        <button onClick={load} disabled={loading} className="btn flex items-center gap-1.5 border border-[color:var(--color-border)] px-2.5 py-1.5">
          <RefreshCw size={15} className={loading ? 'animate-spin' : ''} /> <span className="hidden sm:inline">Обновить</span>
        </button>
      </div>

      {error && <div className="app-card p-4 text-red-500 text-sm">{error}</div>}

      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
        <StatCard icon={<Monitor size={18} />} label="Компьютеров" value={computers.length} />
        <StatCard icon={<SlidersHorizontal size={18} />} label="Всего настроек" value={totalOptions} />
        <StatCard icon={<GitCompareArrows size={18} />} label="Различаются между ПК" value={totalDiffs} onClick={() => setOnlyDiff(true)} active={onlyDiff} />
      </div>

      <div className="app-card p-4 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input
            className="input pl-8 w-full text-sm"
            placeholder="Поиск по названию настройки"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input type="checkbox" checked={onlyDiff} onChange={(e) => setOnlyDiff(e.target.checked)} />
          Только различающиеся между ПК
        </label>
      </div>

      {loading ? <SkeletonTable rows={8} /> : filteredCategories.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)] text-sm">
          Ничего не найдено
        </div>
      ) : (
        <div className="space-y-3">
          {filteredCategories.map((cat) => (
            <CategorySection
              key={cat.name}
              category={cat}
              computers={computers}
              open={openCats.has(cat.name) || (query.trim().length > 0)}
              onToggle={() => toggleCat(cat.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
