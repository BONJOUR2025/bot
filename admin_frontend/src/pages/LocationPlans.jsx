import { useState, useEffect, useCallback } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { ChevronDown, ChevronUp, Info } from 'lucide-react';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

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

// ── CodeManager (read-only — codes come from «Салоны») ───────────
function CodeManager({ codes }) {
  return (
    <div className="card p-4 space-y-3">
      <h3 className="font-semibold text-sm text-[color:var(--color-foreground)]">Точки продаж</h3>

      <p className="text-xs text-[color:var(--color-muted-foreground)]">
        Список формируется из активных салонов с заполненным кодом. Чтобы добавить
        точку или изменить код/название — откройте страницу «Салоны».
      </p>

      <div className="divide-y divide-[color:var(--color-border)]">
        {codes.map(c => (
          <div key={c.code} className="flex items-center gap-2 py-2">
            <span className="w-9 h-7 flex items-center justify-center rounded-lg bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold flex-shrink-0">
              {c.code}
            </span>
            <span className="flex-1 text-sm font-medium min-w-0 truncate">{c.name}</span>
          </div>
        ))}
        {codes.length === 0 && (
          <p className="text-sm text-[color:var(--color-muted-foreground)] italic py-4 text-center">
            Нет активных салонов с кодом
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

// ── Plans table ──────────────────────────────────────────────────
function PlansTable({ codes, plans, onChange }) {
  function handleChange(code, field, raw) {
    const val = parseFloat(raw.replace(/\s/g, '')) || 0;
    onChange(code, field, val);
  }

  const totalRepair = codes.reduce((s, c) => s + (plans[c.code]?.repair_plan || 0), 0);
  const totalCosmetics = codes.reduce((s, c) => s + (plans[c.code]?.cosmetics_plan || 0), 0);
  const totalShoes = codes.reduce((s, c) => s + (plans[c.code]?.shoes_plan || 0), 0);

  const renderInput = (c, field) => {
    const p = plans[c.code] || {};
    return (
      <input
        type="text"
        inputMode="numeric"
        className="input text-right w-full text-sm min-w-[90px]"
        value={fmtInput(p[field])}
        onChange={e => handleChange(c.code, field, e.target.value)}
        placeholder="0"
      />
    );
  };

  const columns = [
    {
      label: 'Точка',
      primary: true,
      render: (c) => (
        <div className="flex items-center gap-2">
          <span className="w-7 h-6 flex items-center justify-center rounded bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-bold flex-shrink-0">
            {c.code}
          </span>
          <span className="font-medium truncate">{c.name}</span>
        </div>
      ),
    },
    { label: 'Ремонт / Химчистка, ₽', render: (c) => renderInput(c, 'repair_plan') },
    { label: 'Косметика, ₽', render: (c) => renderInput(c, 'cosmetics_plan') },
    { label: 'Обувь, ₽', render: (c) => renderInput(c, 'shoes_plan') },
  ];

  return (
    <div className="card overflow-hidden">
      <ResponsiveTable
        data={codes}
        keyFn={(c) => c.code}
        columns={columns}
        emptyText="Нет активных салонов с кодом — задайте код салону на странице «Салоны»"
      />
      {codes.length > 0 && (
        <div className="px-4 py-2.5 bg-[color:var(--color-muted)]/40 font-semibold border-t-2 border-[color:var(--color-border)] flex flex-wrap items-center justify-between gap-2 text-sm">
          <span>Итого</span>
          <div className="flex flex-wrap gap-4">
            <span>Ремонт / Химчистка: {fmt(totalRepair)} ₽</span>
            <span>Косметика: {fmt(totalCosmetics)} ₽</span>
            <span>Обувь: {fmt(totalShoes)} ₽</span>
          </div>
        </div>
      )}
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
          {/* Left: code list (read-only, derived from «Салоны») */}
          <CodeManager codes={codes} />

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
