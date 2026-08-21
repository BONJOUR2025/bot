import { useEffect, useState, useMemo } from 'react';
import { Store, Users, ChevronDown, ChevronUp, Layers, BarChart3 } from 'lucide-react';
import {
  BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import { fmtMoney, StatCard, Tabs } from '../components/ui/SalaryUI.jsx';

const fmtRub = (v) => (v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽');

// Fixed hue order — never reassigned by value/rank, so a component keeps
// its color regardless of how big it is this month.
const CHART_COLORS = ['var(--color-primary)', 'var(--color-success)', 'var(--color-warning)', 'var(--color-text-muted)', 'var(--color-info)'];
const UNALLOCATED_COLOR = '#94a3b8';

const BREAKDOWN_FIELDS = [
  { key: 'oklad',                label: 'Оклад' },
  { key: 'bonuses',              label: 'Премии' },
  { key: 'repair_commission',    label: 'Ремонт' },
  { key: 'cosmetics_commission', label: 'Косметика' },
  { key: 'shoes_commission',     label: 'Обувь' },
];

const TABS = [
  { key: 'salons',    label: 'По салонам',     icon: <Store size={14} /> },
  { key: 'employees', label: 'По сотрудникам', icon: <Users size={14} /> },
];

// ── Инфографика: состав ФОТ ──────────────────────────────────────────
function BreakdownDonut({ totals, total }) {
  const [hover, setHover] = useState(null);
  const data = BREAKDOWN_FIELDS
    .map((f, i) => ({ ...f, value: totals[f.key] || 0, color: CHART_COLORS[i] }))
    .filter((d) => d.value > 0);

  if (data.length === 0) return null;

  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Layers size={15} className="text-[color:var(--color-primary)]" />
        Состав ФОТ
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 150, height: 150, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data} dataKey="value" nameKey="label"
                innerRadius="55%" outerRadius="85%" paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}
              >
                {data.map((d, i) => (
                  <Cell key={d.key} fill={d.color} opacity={hover === null || hover === i ? 1 : 0.4} stroke="none" />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [fmtRub(v), 'Сумма']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0 w-full">
          {data.map((d, i) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            return (
              <div key={d.key} className="rounded-md -mx-1 px-1 py-0.5">
                <div className="flex items-center gap-2">
                  <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="text-xs">{d.label}</span>
                      <span className="text-xs font-semibold shrink-0 tabular-nums">{fmtRub(d.value)} ({pct.toFixed(0)}%)</span>
                    </div>
                    <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${pct}%`, background: d.color, opacity: hover === null || hover === i ? 1 : 0.4 }} />
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Инфографика: топ салонов по ФОТ ──────────────────────────────────
function SalonBarChart({ salons }) {
  const data = salons.filter((s) => s.total > 0);
  if (data.length === 0) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
        Топ салонов по ФОТ
      </div>
      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 38)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="var(--color-border)" />
          <XAxis type="number" tickFormatter={fmtRub} tick={{ fontSize: 10, fill: 'var(--color-muted-foreground)' }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="salon_name" tick={{ fontSize: 11, fill: 'var(--color-muted-foreground)' }} tickLine={false} width={140} />
          <Tooltip formatter={(v) => [fmtRub(v), 'ФОТ']} />
          <Bar dataKey="total" radius={[0, 4, 4, 0]}>
            {data.map((s, i) => (
              <Cell key={s.salon_id} fill={s.salon_id === 'unallocated' ? UNALLOCATED_COLOR : CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── По салонам ──────────────────────────────────────────────────────
function SalonRow({ salon }) {
  const [open, setOpen] = useState(false);
  const isUnallocated = salon.salon_id === 'unallocated';
  return (
    <div className="app-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-[color:var(--color-bg-secondary)]/50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <Store size={16} className={isUnallocated ? 'text-[color:var(--color-muted-foreground)]' : 'text-[color:var(--color-primary)]'} />
          <span className={`font-medium truncate ${isUnallocated ? 'text-[color:var(--color-muted-foreground)] italic' : ''}`}>
            {salon.salon_name}
          </span>
          <span className="hidden sm:inline text-xs text-[color:var(--color-muted-foreground)] shrink-0">
            {salon.employees.length} {salon.employees.length === 1 ? 'сотрудник' : 'сотрудников'}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="font-semibold tabular-nums">{fmtMoney(salon.total)}</span>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[color:var(--color-border)] px-4 py-3 space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {BREAKDOWN_FIELDS.map((f, i) => (
              <div key={f.key} className="rounded-lg bg-[color:var(--color-bg-secondary)] px-2.5 py-1.5">
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: CHART_COLORS[i] }} />
                  {f.label}
                </div>
                <div className="text-sm font-semibold tabular-nums mt-0.5">{fmtMoney(salon[f.key])}</div>
              </div>
            ))}
          </div>
          <div className="divide-y divide-[color:var(--color-border)]">
            {salon.employees.map((e) => (
              <div key={e.employee_code} className="flex items-center justify-between gap-2 py-2 text-sm">
                <span className="truncate">{e.employee_name}</span>
                <span className="tabular-nums font-medium shrink-0">{fmtMoney(e.total)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── По сотрудникам ───────────────────────────────────────────────────
function EmployeeRow({ employee }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="app-card overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-[color:var(--color-bg-secondary)]/50 transition-colors"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-medium truncate">{employee.employee_name}</span>
          <span className="hidden sm:inline text-xs text-[color:var(--color-muted-foreground)] shrink-0">
            {employee.salons.length} {employee.salons.length === 1 ? 'салон' : 'салона(ов)'}
          </span>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <span className="font-semibold tabular-nums">{fmtMoney(employee.total)}</span>
          {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </button>

      {open && (
        <div className="border-t border-[color:var(--color-border)] px-4 py-3 divide-y divide-[color:var(--color-border)]">
          {employee.salons.map((s) => (
            <div key={s.salon_id} className="py-2 text-sm space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className={`font-medium truncate ${s.salon_id === 'unallocated' ? 'text-[color:var(--color-muted-foreground)] italic' : ''}`}>{s.salon_name}</span>
                <span className="tabular-nums font-medium shrink-0">{fmtMoney(s.total)}</span>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-[color:var(--color-muted-foreground)]">
                {BREAKDOWN_FIELDS.map((f) => (
                  <span key={f.key}>{f.label} {fmtMoney(s[f.key])}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function buildEmployeeView(salons) {
  const byEmployee = new Map();
  for (const salon of salons) {
    for (const emp of salon.employees) {
      let entry = byEmployee.get(emp.employee_code);
      if (!entry) {
        entry = { employee_code: emp.employee_code, employee_name: emp.employee_name, total: 0, salons: [] };
        byEmployee.set(emp.employee_code, entry);
      }
      entry.total += emp.total;
      entry.salons.push({
        salon_id: salon.salon_id,
        salon_name: salon.salon_name,
        oklad: emp.oklad,
        bonuses: emp.bonuses,
        repair_commission: emp.repair_commission,
        cosmetics_commission: emp.cosmetics_commission,
        shoes_commission: emp.shoes_commission,
        total: emp.total,
      });
    }
  }
  return [...byEmployee.values()].sort((a, b) => a.employee_name.localeCompare(b.employee_name, 'ru'));
}

// ── Main component ────────────────────────────────────────────────
export default function PayrollBySalon() {
  const { toast } = useToast();
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [tab, setTab] = useState('salons');

  useEffect(() => { loadMonths(); }, []);
  useEffect(() => {
    setData(null);
    if (selectedMonth) loadData(selectedMonth);
  }, [selectedMonth]);

  async function loadMonths() {
    setLoadingMonths(true);
    try {
      const res = await api.get('payroll/months');
      const list = res.data || [];
      setMonths(list);
      if (list.length > 0) setSelectedMonth(list[list.length - 1]);
    } catch { toast('Ошибка загрузки месяцев', 'error'); }
    finally { setLoadingMonths(false); }
  }

  async function loadData(month) {
    setLoading(true);
    try {
      const res = await api.get('payroll/by-salon', { params: { month } });
      setData(res.data);
    } catch {
      toast('Ошибка загрузки данных', 'error');
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  const employeeView = useMemo(() => (data ? buildEmployeeView(data.salons) : []), [data]);
  const sortedSalons = useMemo(
    () => (data ? [...data.salons].sort((a, b) => b.total - a.total) : []),
    [data]
  );

  return (
    <div className="space-y-6 max-w-full p-6">
      <TopProgressBar active={loading || loadingMonths} />

      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">ФОТ по салонам</h2>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {loadingMonths ? (
          <Skeleton style={{ width: 160, height: 38, borderRadius: 8 }} />
        ) : (
          <select className="input" value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)} style={{ minWidth: 160 }}>
            <option value="">Выберите месяц</option>
            {months.map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        )}
      </div>

      {!selectedMonth && !loadingMonths && (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
          Выберите месяц
        </div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {data && !loading && (
        <>
          {/* Hero: grand total */}
          <section className="app-card overflow-hidden">
            <div className="p-5 sm:p-6 flex flex-wrap items-end justify-between gap-4">
              <div>
                <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                  Расходы на ФОТ · {data.salons.length} {data.salons.length === 1 ? 'салон' : 'салонов'}
                </div>
                <div className="mt-1 text-4xl font-bold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">
                  {fmtMoney(data.grand_total.total)}
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                {BREAKDOWN_FIELDS.map((f, i) => (
                  <StatCard
                    key={f.key}
                    icon={<span className="w-2.5 h-2.5 rounded-full block" style={{ background: CHART_COLORS[i] }} />}
                    label={f.label}
                    value={fmtMoney(data.grand_total[f.key])}
                  />
                ))}
              </div>
            </div>
          </section>

          {data.unknown_codes.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 text-sm text-amber-800 dark:text-amber-300">
              Не найдены точки графика для кодов: {data.unknown_codes.join(', ')}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <BreakdownDonut totals={data.grand_total} total={data.grand_total.total} />
            <SalonBarChart salons={sortedSalons} />
          </div>

          <Tabs tabs={TABS} active={tab} onChange={setTab} />

          {tab === 'salons' && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard icon={<Store size={18} />} label="Салонов" value={data.salons.length} />
                <StatCard icon={<Users size={18} />} label="Сотрудников" value={employeeView.length} />
              </div>
              {sortedSalons.map((salon) => (
                <SalonRow key={salon.salon_id} salon={salon} />
              ))}
              {data.salons.length === 0 && (
                <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Нет данных за месяц</div>
              )}
            </div>
          )}

          {tab === 'employees' && (
            <div className="space-y-3">
              {employeeView.map((emp) => (
                <EmployeeRow key={emp.employee_code} employee={emp} />
              ))}
              {employeeView.length === 0 && (
                <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Нет данных за месяц</div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
