import { useEffect, useState, useMemo } from 'react';
import { Store, Users, ChevronDown, ChevronUp } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import { fmtMoney, Term, StatCard, Tabs, TONE_TEXT } from '../components/ui/SalaryUI.jsx';

const TABS = [
  { key: 'salons',    label: 'По салонам',    icon: <Store size={14} /> },
  { key: 'employees', label: 'По сотрудникам', icon: <Users size={14} /> },
];

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
          <span className="text-xs text-[color:var(--color-muted-foreground)] shrink-0">
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
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            <Term label="Оклад" value={salon.oklad} />
            <Term op="+" label="Ремонт" value={salon.repair_commission} />
            <Term op="+" label="Косметика" value={salon.cosmetics_commission} />
            <Term op="+" label="Обувь" value={salon.shoes_commission} />
            <Term op="=" label="Итого" value={salon.total} tone={TONE_TEXT.primary} strong />
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
          <span className="text-xs text-[color:var(--color-muted-foreground)] shrink-0">
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
            <div key={s.salon_id} className="py-2 text-sm space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className={`font-medium truncate ${s.salon_id === 'unallocated' ? 'text-[color:var(--color-muted-foreground)] italic' : ''}`}>{s.salon_name}</span>
                <span className="tabular-nums font-medium shrink-0">{fmtMoney(s.total)}</span>
              </div>
              <div className="flex flex-wrap gap-x-3 text-xs text-[color:var(--color-muted-foreground)]">
                <span>Оклад {fmtMoney(s.oklad)}</span>
                <span>Ремонт {fmtMoney(s.repair_commission)}</span>
                <span>Косметика {fmtMoney(s.cosmetics_commission)}</span>
                <span>Обувь {fmtMoney(s.shoes_commission)}</span>
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
            <div className="p-5 sm:p-6">
              <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                Расходы на ФОТ · {data.salons.length} {data.salons.length === 1 ? 'салон' : 'салонов'}
              </div>
              <div className="mt-1 text-4xl font-bold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">
                {fmtMoney(data.grand_total.total)}
              </div>
            </div>
            <div className="px-5 sm:px-6 py-4 border-t border-[color:var(--color-border)] flex flex-wrap items-center gap-x-4 gap-y-3">
              <Term label="Оклад" value={data.grand_total.oklad} />
              <Term op="+" label="Ремонт" value={data.grand_total.repair_commission} />
              <Term op="+" label="Косметика" value={data.grand_total.cosmetics_commission} />
              <Term op="+" label="Обувь" value={data.grand_total.shoes_commission} />
              <Term op="=" label="Итого" value={data.grand_total.total} tone={TONE_TEXT.primary} strong />
            </div>
          </section>

          {data.unknown_codes.length > 0 && (
            <div className="rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 p-3 text-sm text-amber-800 dark:text-amber-300">
              Не найдены точки графика для кодов: {data.unknown_codes.join(', ')}
            </div>
          )}

          <Tabs tabs={TABS} active={tab} onChange={setTab} />

          {tab === 'salons' && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <StatCard icon={<Store size={18} />} label="Салонов" value={data.salons.length} />
                <StatCard icon={<Users size={18} />} label="Сотрудников" value={employeeView.length} />
              </div>
              {data.salons.map((salon) => (
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
