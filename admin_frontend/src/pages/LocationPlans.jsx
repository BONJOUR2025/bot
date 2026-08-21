import { useState, useEffect, useCallback, useMemo } from 'react';
import api from '../api';
import { useViewport } from '../providers/ViewportProvider.jsx';
import { ChevronDown, ChevronUp, Info, Target, Building2, Users, BarChart3 } from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { StatCard, Tabs } from '../components/ui/SalaryUI.jsx';

const PLAN_COLORS = { repair_plan: 'var(--color-primary)', cosmetics_plan: 'var(--color-success)', shoes_plan: 'var(--color-warning)' };
const PLAN_LABELS = { repair_plan: 'Ремонт / Химчистка', cosmetics_plan: 'Косметика', shoes_plan: 'Обувь' };

function LocationPlansChart({ codes, plans }) {
  const data = codes.map((c) => ({
    name: c.name,
    repair_plan: plans[c.code]?.repair_plan || 0,
    cosmetics_plan: plans[c.code]?.cosmetics_plan || 0,
    shoes_plan: plans[c.code]?.shoes_plan || 0,
  })).filter((d) => d.repair_plan || d.cosmetics_plan || d.shoes_plan);
  if (!data.length) return null;
  return (
    <div className="app-card p-4">
      <div className="text-sm font-semibold mb-3 flex items-center gap-2">
        <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
        План продаж по точкам
      </div>
      <ResponsiveContainer width="100%" height={Math.max(140, data.length * 44)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
          <XAxis type="number" tickFormatter={fmt} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} tickLine={false} width={100} />
          <Tooltip formatter={(v, key) => [`${fmt(v)} ₽`, PLAN_LABELS[key]]} />
          <Legend formatter={(key) => PLAN_LABELS[key]} wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="repair_plan" name="repair_plan" stackId="a" fill={PLAN_COLORS.repair_plan} radius={[0, 0, 0, 0]} />
          <Bar dataKey="cosmetics_plan" name="cosmetics_plan" stackId="a" fill={PLAN_COLORS.cosmetics_plan} />
          <Bar dataKey="shoes_plan" name="shoes_plan" stackId="a" fill={PLAN_COLORS.shoes_plan} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

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
    <div className="app-card p-4 space-y-3">
      <h3 className="font-semibold text-sm flex items-center gap-1.5">
        <Building2 size={15} className="text-[color:var(--color-muted-foreground)]" /> Точки продаж
      </h3>

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
    <div className="space-y-4">
      <LocationPlansChart codes={codes} plans={plans} />
      <div className="app-card overflow-hidden">
      <div className="px-4 py-3 border-b border-[color:var(--color-border)] font-semibold text-sm">
        Планы по точкам
      </div>
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
    </div>
  );
}

const MANAGER_POSITION = 'менеджер по работе с клиентами';

// ── Manager plans (оклад/KPI/выручка/конверсии) per manager+month ──
function ManagerPlansSection({ period }) {
  const [managers, setManagers] = useState([]);
  const [plans, setPlans] = useState({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get('employees/', { params: { archived: false } })
      .then((r) => setManagers((r.data || []).filter(
        (e) => (e.position || '').trim().toLowerCase() === MANAGER_POSITION && e.status !== 'inactive')))
      .catch(() => setManagers([]));
  }, []);

  useEffect(() => {
    api.get('manager-salary/plans', { params: { period } })
      .then((r) => setPlans(r.data || {}))
      .catch(() => setPlans({}));
    setSaved(false);
  }, [period]);

  const upd = (code, field, raw) => {
    const val = parseFloat(String(raw).replace(/\s/g, '')) || 0;
    setPlans((p) => ({ ...p, [code]: { ...(p[code] || {}), [field]: val } }));
    setSaved(false);
  };
  const cell = (code, field, pct) => {
    const p = plans[code] || {};
    const v = pct ? (p[field] != null ? Math.round(p[field] * 100) : '') : (p[field] ?? '');
    return (
      <input type="text" inputMode="numeric" className="input text-right w-full text-sm min-w-[90px]"
        value={v === 0 ? '0' : (v || '')} placeholder="0"
        onChange={(e) => upd(code, field, pct ? (parseFloat(e.target.value || 0) / 100) : e.target.value)} />
    );
  };

  async function save() {
    setSaving(true);
    try {
      await Promise.all(managers.map((m) => {
        const p = plans[m.id] || {};
        return api.put('manager-salary/plan', {
          employee_code: String(m.id), period,
          oklad: p.oklad || 0, kpi_max: p.kpi_max || 0,
          revenue_plan: p.revenue_plan || 0,
          repair_plan_conv: p.repair_plan_conv ?? 0.5,
          sew_plan_conv: p.sew_plan_conv ?? 0.25,
        });
      }));
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } finally { setSaving(false); }
  }

  const columns = [
    { label: 'Менеджер', primary: true, render: (m) => m.full_name || m.name },
    { label: 'Оклад, ₽', render: (m) => cell(m.id, 'oklad') },
    { label: 'KPI макс, ₽', render: (m) => cell(m.id, 'kpi_max') },
    { label: 'План выручки, ₽', render: (m) => cell(m.id, 'revenue_plan') },
    { label: 'Конв. ремонта, %', render: (m) => cell(m.id, 'repair_plan_conv', true) },
    { label: 'Конв. пошива, %', render: (m) => cell(m.id, 'sew_plan_conv', true) },
  ];

  return (
    <div className="app-card overflow-hidden">
      <div className="px-4 py-3 border-b border-[color:var(--color-border)] font-semibold text-sm">
        Планы менеджеров · {period}
      </div>
      <ResponsiveTable
        data={managers}
        keyFn={(m) => m.id}
        columns={columns}
        emptyText="Нет сотрудников с должностью «менеджер по работе с клиентами»"
      />
      {managers.length > 0 && (
        <div className="px-4 py-2.5 flex items-center justify-end gap-3 border-t border-[color:var(--color-border)]">
          {saved && <span className="text-sm text-[color:var(--color-success)] font-medium">✓ Сохранено</span>}
          <button onClick={save} disabled={saving} className="btn btn--primary min-w-[130px]">
            {saving ? 'Сохранение…' : 'Сохранить планы'}
          </button>
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
  const [tab, setTab] = useState('locations');

  const monthKey = `${month}_${year}`;
  const managerPeriod = `${year}-${String(MONTHS.indexOf(month) + 1).padStart(2, '0')}`;

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

  const totals = useMemo(() => ({
    repair: codes.reduce((s, c) => s + (plans[c.code]?.repair_plan || 0), 0),
    cosmetics: codes.reduce((s, c) => s + (plans[c.code]?.cosmetics_plan || 0), 0),
    shoes: codes.reduce((s, c) => s + (plans[c.code]?.shoes_plan || 0), 0),
  }), [codes, plans]);
  const totalPlan = totals.repair + totals.cosmetics + totals.shoes;

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

  const tabs = [
    { key: 'locations', label: 'Точки', icon: <Building2 size={15} /> },
    { key: 'managers', label: 'Менеджеры', icon: <Users size={15} /> },
  ];

  return (
    <div className="p-4 sm:p-6 space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0 flex items-center gap-2.5">
          <span className="hidden sm:flex h-10 w-10 rounded-xl bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] items-center justify-center shrink-0">
            <Target size={20} />
          </span>
          <div className="min-w-0">
            <span className="ui-eyebrow mb-3">{month ? `Месяц · ${month}` : 'Месяц не выбран'}</span>
            <h1 className="text-xl sm:text-2xl font-bold">Планы продаж</h1>
            {!isMobile && (
              <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
                Месячные планы по точкам и планы менеджеров (оклад, KPI, выручка, конверсии)
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <button onClick={prevMonth} className="btn btn--secondary w-9 h-9 flex items-center justify-center text-lg leading-none">‹</button>
          <span className="min-w-[140px] sm:min-w-[160px] text-center font-semibold text-sm sm:text-base px-1">
            {month} {year}
          </span>
          <button onClick={nextMonth} className="btn btn--secondary w-9 h-9 flex items-center justify-center text-lg leading-none">›</button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
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
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Загрузка…</div>
      ) : (
        <>
          {/* Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard icon={<Building2 size={18} />} label="Точек" value={codes.length} />
            <StatCard icon={<Target size={18} />} label="Ремонт / Химчистка" value={`${fmt(totals.repair)} ₽`} />
            <StatCard icon={<Target size={18} />} label="Косметика" value={`${fmt(totals.cosmetics)} ₽`} />
            <StatCard icon={<Target size={18} />} label="Обувь" value={`${fmt(totals.shoes)} ₽`} />
          </div>
          <div className="text-sm text-[color:var(--color-muted-foreground)] -mt-2">
            Суммарный план продаж за {month.toLowerCase()}: <span className="font-semibold text-[color:var(--color-text-primary)]">{fmt(totalPlan)} ₽</span>
          </div>

          <Tabs tabs={tabs} active={tab} onChange={setTab} />

          {tab === 'locations' && (
            <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-5 items-start">
              {/* Left: code list (read-only, derived from «Салоны») */}
              <CodeManager codes={codes} />

              {/* Right: plans table + save */}
              <div className="space-y-4">
                <PlansTable codes={codes} plans={plans} onChange={handlePlanChange} />

                <div className="flex items-center justify-end gap-3">
                  {saved && (
                    <span className="text-sm text-[color:var(--color-success)] font-medium">✓ Сохранено</span>
                  )}
                  <button
                    onClick={handleSave}
                    disabled={saving || codes.length === 0}
                    className={`btn btn--primary min-w-[130px] ${isMobile ? 'flex-1' : ''}`}
                  >
                    {saving ? 'Сохранение…' : 'Сохранить планы'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {tab === 'managers' && <ManagerPlansSection period={managerPeriod} />}
        </>
      )}
    </div>
  );
}
