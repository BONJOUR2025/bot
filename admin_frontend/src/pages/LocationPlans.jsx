import { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';

const MONTHS = [
  'ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ',
  'ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ',
];

function fmt(v) {
  if (!v && v !== 0) return '—';
  return Number(v).toLocaleString('ru');
}

function fmtInput(v) {
  if (!v && v !== 0) return '';
  return String(v);
}

// ── CodeManager ──────────────────────────────────────────────────
function CodeManager({ codes, onAdd, onUpdate, onDelete }) {
  const [adding, setAdding]   = useState(false);
  const [newCode, setNewCode] = useState({ code: '', name: '' });
  const [editing, setEditing] = useState(null);

  function handleAdd() {
    if (!newCode.code.trim() || !newCode.name.trim()) return;
    onAdd(newCode.code.trim(), newCode.name.trim(), codes.length);
    setNewCode({ code: '', name: '' });
    setAdding(false);
  }

  return (
    <div className="card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm text-[color:var(--color-foreground)]">Точки продаж</h3>
        <button
          onClick={() => setAdding(v => !v)}
          className="text-xs text-[color:var(--color-primary)] font-medium hover:underline"
        >
          {adding ? 'Отмена' : '+ Добавить'}
        </button>
      </div>

      {adding && (
        <div className="space-y-2 p-3 rounded-lg bg-[color:var(--color-muted)]/30 border border-[color:var(--color-border)]">
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Код (напр. «П»)</label>
            <input
              className="input w-full text-sm"
              value={newCode.code}
              onChange={e => setNewCode(v => ({ ...v, code: e.target.value }))}
              placeholder="П"
              maxLength={4}
              autoFocus
            />
          </div>
          <div>
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Название точки</label>
            <input
              className="input w-full text-sm"
              value={newCode.name}
              onChange={e => setNewCode(v => ({ ...v, name: e.target.value }))}
              placeholder="Пассаж"
              onKeyDown={e => e.key === 'Enter' && handleAdd()}
            />
          </div>
          <button onClick={handleAdd} className="btn btn-primary w-full text-sm">Добавить</button>
        </div>
      )}

      <div className="divide-y divide-[color:var(--color-border)]">
        {codes.map(c => (
          <div key={c.code} className="flex items-center gap-2 py-2">
            <span className="w-9 h-7 flex items-center justify-center rounded-lg bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold flex-shrink-0">
              {c.code}
            </span>
            {editing === c.code ? (
              <EditCodeRow
                code={c}
                onSave={(name) => { onUpdate(c.code, name); setEditing(null); }}
                onCancel={() => setEditing(null)}
              />
            ) : (
              <>
                <span className="flex-1 text-sm font-medium min-w-0 truncate">{c.name}</span>
                <button
                  onClick={() => setEditing(c.code)}
                  className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)] flex-shrink-0"
                >
                  Изм.
                </button>
                <button
                  onClick={() => onDelete(c.code)}
                  className="text-xs text-red-400 hover:text-red-600 flex-shrink-0"
                >
                  Удал.
                </button>
              </>
            )}
          </div>
        ))}
        {codes.length === 0 && (
          <p className="text-sm text-[color:var(--color-muted-foreground)] italic py-4 text-center">
            Нет точек
          </p>
        )}
      </div>

      {codes.length > 0 && (
        <div className="pt-1 border-t border-[color:var(--color-border)]">
          <p className="text-xs text-[color:var(--color-muted-foreground)] text-center">
            {codes.length} {codes.length === 1 ? 'точка' : codes.length < 5 ? 'точки' : 'точек'}
          </p>
        </div>
      )}
    </div>
  );
}

function EditCodeRow({ code, onSave, onCancel }) {
  const [name, setName] = useState(code.name);
  return (
    <div className="flex flex-1 items-center gap-2 min-w-0">
      <input
        className="input flex-1 text-sm min-w-0"
        value={name}
        onChange={e => setName(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') onSave(name); if (e.key === 'Escape') onCancel(); }}
        autoFocus
      />
      <button onClick={() => onSave(name)} className="text-xs text-[color:var(--color-primary)] font-medium flex-shrink-0">OK</button>
      <button onClick={onCancel} className="text-xs text-[color:var(--color-muted-foreground)] flex-shrink-0">✕</button>
    </div>
  );
}

// ── Plans table ──────────────────────────────────────────────────
function PlansTable({ codes, plans, onChange }) {
  const { isMobile } = useViewport();

  function handleChange(code, field, raw) {
    const val = parseFloat(raw.replace(/\s/g, '')) || 0;
    onChange(code, field, val);
  }

  if (isMobile) {
    return (
      <div className="space-y-3">
        {codes.length === 0 && (
          <div className="card px-4 py-8 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
            Добавьте точки выше
          </div>
        )}
        {codes.map((c) => {
          const p = plans[c.code] || {};
          return (
            <div key={c.code} className="card overflow-hidden">
              <div className="px-4 py-3 border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/20 text-sm font-semibold flex items-center gap-2">
                <span className="w-7 h-6 flex items-center justify-center rounded bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold">
                  {c.code}
                </span>
                {c.name}
              </div>
              <div className="px-4 py-3 space-y-2 text-sm">
                {[
                  { field: 'repair_plan', label: 'Ремонт / Химчистка' },
                  { field: 'cosmetics_plan', label: 'Косметика' },
                  { field: 'shoes_plan', label: 'Обувь' },
                ].map(({ field, label }) => (
                  <div key={field} className="flex items-center justify-between gap-3">
                    <span className="text-[color:var(--color-muted-foreground)]">{label}</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      className="input text-right w-28 text-sm"
                      value={fmtInput(p[field])}
                      onChange={e => handleChange(c.code, field, e.target.value)}
                      placeholder="0"
                    />
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  const totalRepair = codes.reduce((s, c) => s + (plans[c.code]?.repair_plan || 0), 0);
  const totalCosmetics = codes.reduce((s, c) => s + (plans[c.code]?.cosmetics_plan || 0), 0);
  const totalShoes = codes.reduce((s, c) => s + (plans[c.code]?.shoes_plan || 0), 0);

  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30">
            <th className="text-left px-4 py-3 text-xs font-semibold text-[color:var(--color-muted-foreground)] w-[35%]">
              Точка
            </th>
            <th className="text-right px-3 py-3 text-xs font-semibold text-[color:var(--color-muted-foreground)] whitespace-nowrap">
              Ремонт / Химчистка, ₽
            </th>
            <th className="text-right px-3 py-3 text-xs font-semibold text-[color:var(--color-muted-foreground)] whitespace-nowrap">
              Косметика, ₽
            </th>
            <th className="text-right px-3 py-3 text-xs font-semibold text-[color:var(--color-muted-foreground)] whitespace-nowrap">
              Обувь, ₽
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--color-border)]">
          {codes.map((c, i) => {
            const p = plans[c.code] || {};
            return (
              <tr key={c.code} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/10' : ''}>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-6 flex items-center justify-center rounded bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold flex-shrink-0">
                      {c.code}
                    </span>
                    <span className="font-medium truncate">{c.name}</span>
                  </div>
                </td>
                {['repair_plan', 'cosmetics_plan', 'shoes_plan'].map(field => (
                  <td key={field} className="px-2 py-2">
                    <input
                      type="text"
                      inputMode="numeric"
                      className="input text-right w-full text-sm min-w-[90px]"
                      value={fmtInput(p[field])}
                      onChange={e => handleChange(c.code, field, e.target.value)}
                      placeholder="0"
                    />
                  </td>
                ))}
              </tr>
            );
          })}
          {codes.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-10 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
                Добавьте точки в панели слева
              </td>
            </tr>
          )}
          {codes.length > 0 && (
            <tr className="bg-[color:var(--color-muted)]/40 font-semibold border-t-2 border-[color:var(--color-border)]">
              <td className="px-4 py-2.5 text-sm">Итого</td>
              <td className="px-3 py-2.5 text-right text-sm">{fmt(totalRepair)} ₽</td>
              <td className="px-3 py-2.5 text-right text-sm">{fmt(totalCosmetics)} ₽</td>
              <td className="px-3 py-2.5 text-right text-sm">{fmt(totalShoes)} ₽</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────
export default function LocationPlans() {
  const now = new Date();
  const { isMobile } = useViewport();
  const [year, setYear]     = useState(now.getFullYear());
  const [month, setMonth]   = useState(MONTHS[now.getMonth()]);
  const [codes, setCodes]   = useState([]);
  const [plans, setPlans]   = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [error, setError]     = useState(null);
  const [showInfo, setShowInfo] = useState(false);

  const monthKey = `${month}_${year}`;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/location-plans/full', { params: { month_key: monthKey } });
      setCodes(res.data.codes || []);
      setPlans(res.data.plans || {});
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [monthKey]);

  useEffect(() => { load(); }, [load]);

  function handlePlanChange(locationCode, field, value) {
    setPlans(prev => ({
      ...prev,
      [locationCode]: {
        ...(prev[locationCode] || {}),
        [field]: value,
        location_code: locationCode,
        month_key: monthKey,
      },
    }));
    setSaved(false);
  }

  async function handleSave() {
    setSaving(true);
    setSaved(false);
    try {
      await Promise.all(
        codes.map(c => {
          const p = plans[c.code] || {};
          return api.put('/location-plans/plans', {
            location_code: c.code,
            month_key: monthKey,
            repair_plan: p.repair_plan || 0,
            cosmetics_plan: p.cosmetics_plan || 0,
            shoes_plan: p.shoes_plan || 0,
          });
        })
      );
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleAddCode(code, name, sortOrder) {
    try {
      await api.post('/location-plans/codes', { code, name, sort_order: sortOrder });
      await load();
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
    }
  }

  async function handleUpdateCode(code, name) {
    try {
      await api.patch(`/location-plans/codes/${encodeURIComponent(code)}`, { name });
      setCodes(prev => prev.map(c => c.code === code ? { ...c, name } : c));
    } catch (e) {
      setError(e.message);
    }
  }

  async function handleDeleteCode(code) {
    if (!window.confirm(`Удалить точку «${code}»? Все планы по этой точке также будут удалены.`)) return;
    try {
      await api.delete(`/location-plans/codes/${encodeURIComponent(code)}`);
      setCodes(prev => prev.filter(c => c.code !== code));
      setPlans(prev => { const n = { ...prev }; delete n[code]; return n; });
    } catch (e) {
      setError(e.message);
    }
  }

  function prevMonth() {
    const idx = MONTHS.indexOf(month);
    if (idx === 0) { setMonth(MONTHS[11]); setYear(y => y - 1); }
    else setMonth(MONTHS[idx - 1]);
  }

  function nextMonth() {
    const idx = MONTHS.indexOf(month);
    if (idx === 11) { setMonth(MONTHS[0]); setYear(y => y + 1); }
    else setMonth(MONTHS[idx + 1]);
  }

  return (
    <div className="p-4 sm:p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold">Планы по точкам</h1>
          {!isMobile && (
            <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
              Месячные планы продаж — используются для авторасчёта индивидуальных планов сотрудников
            </p>
          )}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={prevMonth} className="btn btn-secondary w-9 h-9 flex items-center justify-center text-lg leading-none">‹</button>
          <span className="min-w-[140px] sm:min-w-[160px] text-center font-semibold text-sm sm:text-base px-1">
            {month} {year}
          </span>
          <button onClick={nextMonth} className="btn btn-secondary w-9 h-9 flex items-center justify-center text-lg leading-none">›</button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* How it works — collapsible on all screen sizes */}
      <div className="rounded-xl bg-blue-50 border border-blue-200 text-sm text-blue-800 overflow-hidden">
        <button
          className="w-full flex items-center gap-2 px-4 py-3 text-left"
          onClick={() => setShowInfo(v => !v)}
        >
          <Info size={15} className="flex-shrink-0 text-blue-500" />
          <span className="font-semibold flex-1">Как работает авторасчёт плана</span>
          {showInfo ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
        </button>
        {showInfo && (
          <div className="px-4 pb-4 space-y-1.5 border-t border-blue-200 pt-3">
            <p>Дневной план точки = Месячный план точки ÷ Количество дней в месяце</p>
            <p>Индивидуальный план = Σ (Дневной план точки × Смен сотрудника на этой точке)</p>
            <p className="text-blue-600">Если для сотрудника задан ручной план в «Расчёте зарплаты» — он имеет приоритет.</p>
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-[color:var(--color-muted-foreground)]">Загрузка...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-5 items-start">
          {/* Left: code manager */}
          <CodeManager
            codes={codes}
            onAdd={handleAddCode}
            onUpdate={handleUpdateCode}
            onDelete={handleDeleteCode}
          />

          {/* Right: plans table + save */}
          <div className="space-y-4">
            <PlansTable codes={codes} plans={plans} onChange={handlePlanChange} />

            <div className="flex items-center justify-end gap-3">
              {saved && (
                <span className="text-sm text-emerald-600 font-medium">✓ Сохранено</span>
              )}
              <button
                onClick={handleSave}
                disabled={saving || codes.length === 0}
                className={`btn btn-primary min-w-[130px] ${isMobile ? 'flex-1' : ''}`}
              >
                {saving ? 'Сохранение...' : 'Сохранить планы'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
