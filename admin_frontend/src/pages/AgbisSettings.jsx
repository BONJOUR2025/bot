import { useState, useEffect, useMemo } from 'react';
import { Search, RefreshCw, SlidersHorizontal, GitCompareArrows, Monitor, ChevronDown, ChevronRight, LayoutGrid, Rows3 } from 'lucide-react';
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
// drives the "только различающиеся" filter and the diff accents in both views.
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

function ValueTag({ value, source }) {
  const label = formatValue(value);
  const title = source === 'override' ? 'Переопределено на этом ПК' : source === 'default' ? 'Значение по умолчанию' : '';
  if (label === null) return <span className="text-xs text-[color:var(--color-muted-foreground)]" title={title}>—</span>;
  if (label === 'Да') return <span className="badge badge--success" title={title}>Да</span>;
  if (label === 'Нет') return <span className="text-xs text-[color:var(--color-muted-foreground)]" title={title}>Нет</span>;
  return <span className="text-sm font-mono text-[color:var(--color-text-primary)]" title={title}>{label}</span>;
}

function OptionLabel({ option }) {
  return (
    <div className="min-w-0">
      <div className="text-sm font-medium break-words">{option.short_descr || option.option_name}</div>
      <div className="text-[11px] text-[color:var(--color-muted-foreground)] font-mono break-words">
        {option.option_name}
        {!option.short_descr && option.group && <span className="font-sans"> · {option.group}</span>}
      </div>
    </div>
  );
}

// ── Режим «По компьютеру»: читается как обычный список настроек, а не таблица ──

function ByComputerCategory({ category, computerId, allComputerIds, open, onToggle }) {
  const diffCount = useMemo(
    () => category.options.filter((o) => hasDiff(o.values, allComputerIds)).length,
    [category, allComputerIds]
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
          <span>{category.options.length}</span>
          {diffCount > 0 && (
            <span className="px-1.5 py-0.5 rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 font-medium">
              {diffCount} отличаются у кого-то
            </span>
          )}
        </div>
      </button>
      {open && (
        <div className="divide-y divide-[color:var(--color-border)] border-t border-[color:var(--color-border)]">
          {category.options.map((o) => {
            const cell = o.values[computerId] || {};
            const diff = hasDiff(o.values, allComputerIds);
            return (
              <div key={o.id} className={`flex items-center justify-between gap-4 px-4 py-2.5 ${diff ? 'bg-amber-50/50 dark:bg-amber-900/10' : ''}`}>
                <OptionLabel option={o} />
                <div className="shrink-0 flex items-center gap-2">
                  {diff && <GitCompareArrows size={12} className="text-amber-500" title="Значение отличается хотя бы на одном ПК" />}
                  <ValueTag value={cell.value} source={cell.source} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Режим «Сравнение»: таблица настройка × ПК, для поиска расхождений ──

function CompareRow({ option, computers }) {
  const ids = useMemo(() => computers.map((c) => c.id), [computers]);
  const majority = useMemo(() => majorityValue(option.values, ids), [option, ids]);
  const diff = useMemo(() => hasDiff(option.values, ids), [option, ids]);

  return (
    <tr className={diff ? 'bg-amber-50/40 dark:bg-amber-900/10' : ''}>
      <td className="sticky left-0 z-10 bg-[color:var(--color-card)] px-3 py-2 border-r border-[color:var(--color-border)] min-w-[280px] max-w-[420px] align-top">
        <OptionLabel option={option} />
      </td>
      {computers.map((c) => {
        const cell = option.values[c.id] || {};
        const isOutlier = diff && JSON.stringify(cell.value ?? null) !== majority;
        return (
          <td
            key={c.id}
            className={`px-3 py-2 text-xs text-center whitespace-nowrap ${isOutlier ? 'bg-amber-100 dark:bg-amber-900/30 font-semibold rounded' : ''}`}
          >
            <ValueTag value={cell.value} source={cell.source} />
          </td>
        );
      })}
    </tr>
  );
}

function CompareCategory({ category, computers, open, onToggle }) {
  const ids = useMemo(() => computers.map((c) => c.id), [computers]);
  const diffCount = useMemo(
    () => category.options.filter((o) => hasDiff(o.values, ids)).length,
    [category, ids]
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
                <th className="sticky left-0 z-10 bg-[color:var(--color-card)] px-3 py-2 text-left text-xs font-medium border-r border-[color:var(--color-border)] min-w-[280px] max-w-[420px]">
                  Настройка
                </th>
                {computers.map((c) => (
                  <th
                    key={c.id}
                    className="px-3 py-2 text-xs font-medium text-center whitespace-nowrap"
                    title={[c.db_name, c.hostname, c.ip].filter(Boolean).join(' · ')}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {category.options.map((o) => (
                <CompareRow key={o.id} option={o} computers={computers} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const MODES = [
  { key: 'byComputer', label: 'По компьютеру', icon: Rows3 },
  { key: 'compare',    label: 'Сравнение всех ПК', icon: LayoutGrid },
];

export default function AgbisSettings() {
  const [data, setData]       = useState({ computers: [], categories: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [query, setQuery]     = useState('');
  const [onlyDiff, setOnlyDiff] = useState(false);
  const [openCats, setOpenCats] = useState(() => new Set());
  const [mode, setMode] = useState('byComputer');
  const [computerId, setComputerId] = useState(null);

  useEffect(() => { load(); }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('agbis-settings/');
      const d = res.data && Array.isArray(res.data.categories) ? res.data : { computers: [], categories: [] };
      setData(d);
      if (d.computers.length > 0) setComputerId((prev) => prev ?? d.computers[0].id);
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    } finally {
      setLoading(false);
    }
  }

  const computers = data.computers;
  const computerIds = useMemo(() => computers.map((c) => c.id), [computers]);
  const selectedComputer = computers.find((c) => c.id === computerId) || null;

  const filteredCategories = useMemo(() => {
    const q = query.trim().toLowerCase();
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
          options = options.filter((o) => hasDiff(o.values, computerIds));
        }
        return { ...cat, options };
      })
      .filter((cat) => cat.options.length > 0);
  }, [data.categories, computerIds, query, onlyDiff]);

  const totalOptions = data.categories.reduce((sum, c) => sum + c.options.length, 0);
  const totalDiffs = useMemo(
    () => data.categories.reduce((sum, c) => sum + c.options.filter((o) => hasDiff(o.values, computerIds)).length, 0),
    [data.categories, computerIds]
  );

  function toggleCat(name) {
    setOpenCats((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name); else next.add(name);
      return next;
    });
  }

  function jumpToDiffs() {
    setMode('compare');
    setOnlyDiff(true);
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
        <StatCard icon={<GitCompareArrows size={18} />} label="Различаются между ПК" value={totalDiffs} onClick={jumpToDiffs} active={mode === 'compare' && onlyDiff} />
      </div>

      <div className="app-card p-4 flex flex-wrap gap-3 items-center">
        <div className="flex gap-1 rounded-lg border border-[color:var(--color-border)] p-0.5 shrink-0">
          {MODES.map((m) => (
            <button
              key={m.key}
              onClick={() => setMode(m.key)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${mode === m.key ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-muted)]/50'}`}
            >
              <m.icon size={13} /> {m.label}
            </button>
          ))}
        </div>

        {mode === 'byComputer' && (
          <select
            className="input text-sm py-1.5 h-9 min-w-[220px]"
            value={computerId ?? ''}
            onChange={(e) => setComputerId(Number(e.target.value))}
          >
            {computers.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        )}

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

      {mode === 'byComputer' && selectedComputer && (
        <div className="text-xs text-[color:var(--color-muted-foreground)] -mt-2 px-1">
          {[selectedComputer.db_name, selectedComputer.hostname, selectedComputer.ip].filter(Boolean).join(' · ')}
        </div>
      )}

      {loading ? <SkeletonTable rows={8} /> : filteredCategories.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)] text-sm">
          Ничего не найдено
        </div>
      ) : mode === 'byComputer' ? (
        <div className="space-y-3">
          {filteredCategories.map((cat) => (
            <ByComputerCategory
              key={cat.name}
              category={cat}
              computerId={computerId}
              allComputerIds={computerIds}
              open={openCats.has(cat.name) || query.trim().length > 0}
              onToggle={() => toggleCat(cat.name)}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {filteredCategories.map((cat) => (
            <CompareCategory
              key={cat.name}
              category={cat}
              computers={computers}
              open={openCats.has(cat.name) || query.trim().length > 0}
              onToggle={() => toggleCat(cat.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
