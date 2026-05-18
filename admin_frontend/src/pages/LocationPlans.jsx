import { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { ChevronDown, ChevronUp } from 'lucide-react';

const MONTHS = [
  'ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ',
  'ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ',
];

function fmt(v) {
  if (!v && v !== 0) return '';
  return Number(v).toLocaleString('ru');
}

function fmtInput(v) {
  if (!v && v !== 0) return '';
  return String(v);
}

// ── CodeManager ──────────────────────────────────────────────────
function CodeManager({ codes, onAdd, onUpdate, onDelete, embedded = false }) {
  const [adding, setAdding]   = useState(false);
  const [newCode, setNewCode] = useState({ code: '', name: '' });
  const [editing, setEditing] = useState(null);  // code string being edited

  function handleAdd() {
    if (!newCode.code.trim() || !newCode.name.trim()) return;
    onAdd(newCode.code.trim(), newCode.name.trim(), codes.length);
    setNewCode({ code: '', name: '' });
    setAdding(false);
  }

  return (
    <div className={embedded ? 'p-4 space-y-4' : 'card p-5 space-y-4'}>
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-sm">Точки (обозначения в расписании)</h3>
        <button onClick={() => setAdding(v => !v)} className="text-xs text-[color:var(--color-primary)] font-medium hover:underline">
          + Добавить
        </button>
      </div>

      {adding && (
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Код (напр. «П»)</label>
            <input
              className="input w-full text-sm"
              value={newCode.code}
              onChange={e => setNewCode(v => ({ ...v, code: e.target.value }))}
              placeholder="П"
              maxLength={4}
            />
          </div>
          <div className="flex-[3]">
            <label className="text-xs text-[color:var(--color-muted-foreground)] mb-1 block">Название</label>
            <input
              className="input w-full text-sm"
              value={newCode.name}
              onChange={e => setNewCode(v => ({ ...v, name: e.target.value }))}
              placeholder="Пассаж"
            />
          </div>
          <button onClick={handleAdd} className="btn btn-primary text-sm px-3">Добавить</button>
          <button onClick={() => setAdding(false)} className="btn btn-secondary text-sm px-3">Отмена</button>
        </div>
      )}

      <div className="divide-y divide-[color:var(--color-border)]">
        {codes.map(c => (
          <div key={c.code} className="flex items-center gap-3 py-2">
            <span className="w-10 h-8 flex items-center justify-center rounded-lg bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold flex-shrink-0">
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
                <span className="flex-1 text-sm font-medium">{c.name}</span>
                <button onClick={() => setEditing(c.code)} className="text-xs text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-primary)]">Изменить</button>
                <button onClick={() => onDelete(c.code)} className="text-xs text-red-400 hover:text-red-600">Удалить</button>
              </>
            )}
          </div>
        ))}
        {codes.length === 0 && (
          <p className="text-sm text-[color:var(--color-muted-foreground)] italic py-3 text-center">Нет точек</p>
        )}
      </div>
    </div>
  );
}

function EditCodeRow({ code, onSave, onCancel }) {
  const [name, setName] = useState(code.name);
  return (
    <div className="flex flex-1 items-center gap-2">
      <input className="input flex-1 text-sm" value={name} onChange={e => setName(e.target.value)} />
      <button onClick={() => onSave(name)} className="text-xs text-[color:var(--color-primary)] font-medium">Сохранить</button>
      <button onClick={onCancel} className="text-xs text-[color:var(--color-muted-foreground)]">Отмена</button>
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

  const colCls = 'text-right text-xs font-semibold text-[color:var(--color-muted-foreground)] px-3 py-2';
  const cellCls = 'px-2 py-1.5';

  return isMobile ? (
    <div className="space-y-3">
      {codes.length === 0 && (
        <div className="px-4 py-8 text-center text-sm text-[color:var(--color-muted-foreground)] italic card">
          Добавьте точки в левой панели
        </div>
      )}
      {codes.map((c) => {
        const p = plans[c.code] || {};
        return (
          <div key={c.code} className="border rounded-xl bg-white shadow-sm overflow-hidden">
            <div className="px-4 py-3 border-b bg-gray-50 text-sm font-medium flex items-center gap-2">
              <span className="w-7 h-6 flex items-center justify-center rounded bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold">{c.code}</span>
              {c.name}
            </div>
            <div className="px-4 py-2 space-y-1.5 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Ремонт / Химчистка, ₽</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className="input text-right w-32 text-sm"
                  value={fmtInput(p.repair_plan)}
                  onChange={e => handleChange(c.code, 'repair_plan', e.target.value)}
                  placeholder="0"
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Косметика, ₽</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className="input text-right w-32 text-sm"
                  value={fmtInput(p.cosmetics_plan)}
                  onChange={e => handleChange(c.code, 'cosmetics_plan', e.target.value)}
                  placeholder="0"
                />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-500">Обувь, ₽</span>
                <input
                  type="text"
                  inputMode="numeric"
                  className="input text-right w-32 text-sm"
                  value={fmtInput(p.shoes_plan)}
                  onChange={e => handleChange(c.code, 'shoes_plan', e.target.value)}
                  placeholder="0"
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  ) : (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30">
            <th className="text-left px-4 py-2.5 text-xs font-semibold text-[color:var(--color-muted-foreground)]">Точка</th>
            <th className={colCls}>Ремонт / Химчистка, ₽</th>
            <th className={colCls}>Косметика, ₽</th>
            <th className={colCls}>Обувь, ₽</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[color:var(--color-border)]">
          {codes.map((c, i) => {
            const p = plans[c.code] || {};
            return (
              <tr key={c.code} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/20' : ''}>
                <td className="px-4 py-2">
                  <div className="flex items-center gap-2">
                    <span className="w-7 h-6 flex items-center justify-center rounded bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold">{c.code}</span>
                    <span className="font-medium">{c.name}</span>
                  </div>
                </td>
                <td className={cellCls}>
                  <input
                    type="text"
                    inputMode="numeric"
                    className="input text-right w-full text-sm"
                    value={fmtInput(p.repair_plan)}
                    onChange={e => handleChange(c.code, 'repair_plan', e.target.value)}
                    placeholder="0"
                  />
                </td>
                <td className={cellCls}>
                  <input
                    type="text"
                    inputMode="numeric"
                    className="input text-right w-full text-sm"
                    value={fmtInput(p.cosmetics_plan)}
                    onChange={e => handleChange(c.code, 'cosmetics_plan', e.target.value)}
                    placeholder="0"
                  />
                </td>
                <td className={cellCls}>
                  <input
                    type="text"
                    inputMode="numeric"
                    className="input text-right w-full text-sm"
                    value={fmtInput(p.shoes_plan)}
                    onChange={e => handleChange(c.code, 'shoes_plan', e.target.value)}
                    placeholder="0"
                  />
                </td>
              </tr>
            );
          })}
          {codes.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-8 text-center text-sm text-[color:var(--color-muted-foreground)] italic">
                Добавьте точки в левой панели
              </td>
            </tr>
          )}
          {codes.length > 0 && (
            <tr className="bg-[color:var(--color-muted)]/40 font-semibold border-t-2 border-[color:var(--color-border)]">
              <td className="px-4 py-2 text-sm">Итого</td>
              <td className="px-3 py-2 text-right text-sm">{fmt(codes.reduce((s, c) => s + (plans[c.code]?.repair_plan || 0), 0))} ₽</td>
              <td className="px-3 py-2 text-right text-sm">{fmt(codes.reduce((s, c) => s + (plans[c.code]?.cosmetics_plan || 0), 0))} ₽</td>
              <td className="px-3 py-2 text-right text-sm">{fmt(codes.reduce((s, c) => s + (plans[c.code]?.shoes_plan || 0), 0))} ₽</td>
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
  const [plans, setPlans]   = useState({});  // {location_code: {repair_plan, cosmetics_plan, shoes_plan}}
  const [loading, setLoading] = useState(true);
  const [saving, setSaving]   = useState(false);
  const [saved, setSaved]     = useState(false);
  const [error, setError]     = useState(null);
  const [showInfo, setShowInfo] = useState(false);
  const [showCodes, setShowCodes] = useState(false);

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
    <div className={isMobile ? 'p-4 space-y-4' : 'p-6 space-y-6'}>
      {/* Header */}
      {isMobile ? (
        <div className="space-y-3">
          <h1 className="text-xl font-bold">Планы по точкам</h1>
          <div className="flex items-center justify-between">
            <button onClick={prevMonth} className="btn btn-secondary px-3 py-2 text-base">‹</button>
            <span className="font-semibold text-base">{month} {year}</span>
            <button onClick={nextMonth} className="btn btn-secondary px-3 py-2 text-base">›</button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-2xl font-bold">Планы по точкам</h1>
            <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
              Месячные планы продаж для каждой точки — используются для авторасчёта индивидуальных планов сотрудников
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={prevMonth} className="btn btn-secondary px-2.5">‹</button>
            <span className="min-w-[160px] text-center font-semibold text-base">
              {month} {year}
            </span>
            <button onClick={nextMonth} className="btn btn-secondary px-2.5">›</button>
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-600">
          {error}
        </div>
      )}

      {/* How it works */}
      {isMobile ? (
        <div className="rounded-xl bg-blue-50 border border-blue-200 text-sm text-blue-800">
          <button
            className="w-full flex items-center justify-between px-4 py-3 font-semibold"
            onClick={() => setShowInfo(v => !v)}
          >
            <span>Как работает авторасчёт</span>
            {showInfo ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          {showInfo && (
            <div className="px-4 pb-3 space-y-1 border-t border-blue-200">
              <p className="pt-2">Дневной план точки = Месячный план ÷ Кол-во дней в месяце</p>
              <p>Индивидуальный план = Σ (Дневной план × Смен на этой точке)</p>
              <p className="text-blue-600">Если задан ручной план — он имеет приоритет.</p>
            </div>
          )}
        </div>
      ) : (
        <div className="rounded-xl bg-blue-50 border border-blue-200 px-5 py-4 text-sm text-blue-800 space-y-1">
          <p className="font-semibold">Как работает авторасчёт плана сотрудника</p>
          <p>
            Дневной план точки = Месячный план точки ÷ Кол-во дней в месяце<br/>
            Индивидуальный план = Σ (Дневной план точки × Смен на этой точке)
          </p>
          <p className="text-blue-600">
            Если для сотрудника задан ручной план в «Расчёте зарплаты» — он имеет приоритет.
          </p>
        </div>
      )}

      {loading ? (
        <div className="text-center py-12 text-[color:var(--color-muted-foreground)]">Загрузка...</div>
      ) : isMobile ? (
        <div className="space-y-4">
          {/* Collapsible code manager on mobile */}
          <div className="card overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-3 text-sm font-semibold"
              onClick={() => setShowCodes(v => !v)}
            >
              <span>Точки ({codes.length})</span>
              {showCodes ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
            {showCodes && (
              <div className="border-t border-[color:var(--color-border)]">
                <CodeManager
                  codes={codes}
                  onAdd={handleAddCode}
                  onUpdate={handleUpdateCode}
                  onDelete={handleDeleteCode}
                  embedded
                />
              </div>
            )}
          </div>

          <PlansTable codes={codes} plans={plans} onChange={handlePlanChange} />

          <div className="flex items-center justify-between gap-3">
            {saved && <span className="text-sm text-emerald-600 font-medium">✓ Сохранено</span>}
            <button
              onClick={handleSave}
              disabled={saving || codes.length === 0}
              className="btn btn-primary flex-1"
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6 items-start">
          {/* Left: code manager */}
          <CodeManager
            codes={codes}
            onAdd={handleAddCode}
            onUpdate={handleUpdateCode}
            onDelete={handleDeleteCode}
          />

          {/* Right: plans table */}
          <div className="space-y-4">
            <PlansTable
              codes={codes}
              plans={plans}
              onChange={handlePlanChange}
            />

            <div className="flex items-center justify-end gap-3">
              {saved && (
                <span className="text-sm text-emerald-600 font-medium">✓ Сохранено</span>
              )}
              <button
                onClick={handleSave}
                disabled={saving || codes.length === 0}
                className="btn btn-primary min-w-[120px]"
              >
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
