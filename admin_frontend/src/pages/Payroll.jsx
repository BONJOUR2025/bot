import { useEffect, useState, useMemo } from 'react';
import {
  Download, Search, X, Settings, ChevronDown, ChevronUp, Percent,
  CheckSquare, Square, BadgeCheck,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';

const fmt = (v) => (v === null || v === undefined || v === 0 ? '—' : Number(v).toLocaleString('ru-RU'));
const fmtMoney = (v) => (v === null || v === undefined || v === 0 ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
const fmtRate = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`);

// ── Helpers ───────────────────────────────────────────────────────
function parseSelectedMonth(selectedMonth) {
  // selectedMonth is like "ЯНВАРЬ" (sheet name, no year)
  // We assume current year — server also defaults to current year
  if (!selectedMonth) return { month: '', year: new Date().getFullYear() };
  return { month: selectedMonth, year: new Date().getFullYear() };
}

function makeMonthKey(month, year) {
  return `${month.toUpperCase()}_${year}`;
}

// ── Summary bar ───────────────────────────────────────────────────
function SummaryBar({ rows }) {
  const totalNet        = rows.reduce((s, r) => s + (r.total_net || 0), 0);
  const totalSalary     = rows.reduce((s, r) => s + (r.base_salary || 0), 0);
  const totalCommission = rows.reduce((s, r) => s + (r.total_commission || 0), 0);
  const totalBonuses    = rows.reduce((s, r) => s + (r.bonuses || 0) + (r.excel_bonus || 0), 0);
  const totalAdvances   = rows.reduce((s, r) => s + (r.advances || 0), 0);
  const totalPenalties  = rows.reduce((s, r) => s + (r.penalties || 0), 0);
  const paidCount       = rows.filter((r) => r.settlement_paid).length;

  const stats = [
    { label: 'Сотрудников', value: rows.length },
    { label: 'Оклады',      value: fmtMoney(totalSalary) },
    { label: 'Комиссии',    value: fmtMoney(totalCommission) },
    { label: 'Премии',      value: fmtMoney(totalBonuses) },
    { label: 'Авансы',      value: fmtMoney(totalAdvances), accent: true },
    { label: 'Штрафы',      value: fmtMoney(totalPenalties), accent: true },
    { label: 'К выплате',   value: fmtMoney(totalNet) },
    { label: 'Расчёт выдан', value: `${paidCount} / ${rows.length}`, green: true },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
      {stats.map((s) => (
        <div key={s.label} className="app-card p-4 text-center">
          <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{s.label}</div>
          <div className={`text-base font-semibold ${
            s.accent ? 'text-[color:var(--color-danger)]' :
            s.green  ? 'text-[color:var(--color-success)]' :
            'text-[color:var(--color-text-primary)]'
          }`}>{s.value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Plan categories ───────────────────────────────────────────────
const PLAN_CATEGORIES = [
  { key: 'repair',    label: 'Ремонт' },
  { key: 'cosmetics', label: 'Косметика' },
  { key: 'shoes',     label: 'Обувь' },
];

function MultiCategorySelect({ label, description, value, onChange }) {
  const toggle = (key) => {
    const next = value.includes(key) ? value.filter((k) => k !== key) : [...value, key];
    onChange(next);
  };
  return (
    <div>
      <div className="text-sm font-medium mb-1">{label}</div>
      <div className="flex gap-3">
        {PLAN_CATEGORIES.map(({ key, label: catLabel }) => (
          <label key={key} className="flex items-center gap-1.5 cursor-pointer text-sm">
            <input type="checkbox" className="w-4 h-4 rounded"
              checked={value.includes(key)} onChange={() => toggle(key)} />
            {catLabel}
          </label>
        ))}
      </div>
      {description && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{description}</p>}
    </div>
  );
}

// ── Plan modal ────────────────────────────────────────────────────
function PlanModal({ employee, plans, onSave, onClose, monthKey }) {
  const existing = plans.find(
    (p) => p.employee_code === employee.employee_code && (p.month_key === monthKey || p.month_key === null || !p.month_key)
  );
  // prefer month-specific plan
  const monthSpecific = plans.find(
    (p) => p.employee_code === employee.employee_code && p.month_key === monthKey
  ) || existing;

  const [form, setForm] = useState({
    repair_plan:    monthSpecific?.repair_plan    || 0,
    cosmetics_plan: monthSpecific?.cosmetics_plan || 0,
    shoes_plan:     monthSpecific?.shoes_plan     || 0,
    ignore_kpi:     monthSpecific?.ignore_kpi     || false,
    force_max:      monthSpecific?.force_max      || [],
    force_min:      monthSpecific?.force_min      || [],
  });

  const handleSave = () => {
    onSave({
      employee_code:  employee.employee_code,
      employee_name:  employee.employee_name,
      month_key:      monthKey,         // always save with current month
      repair_plan:    parseFloat(form.repair_plan)    || 0,
      cosmetics_plan: parseFloat(form.cosmetics_plan) || 0,
      shoes_plan:     parseFloat(form.shoes_plan)     || 0,
      ignore_kpi:     form.ignore_kpi,
      force_max:      form.force_max,
      force_min:      form.force_min,
    });
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card max-w-md">
        <h3 className="text-lg font-semibold mb-1">
          План продаж: {employee.employee_name}
        </h3>
        {monthKey && (
          <p className="text-xs text-[color:var(--color-primary)] mb-4 font-medium">
            📅 {monthKey.replace('_', ' ')}
          </p>
        )}
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-4">
          Код: {employee.employee_code}
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">План по ремонту/химчистке</label>
            <input type="number" className="input w-full" placeholder="0"
              value={form.repair_plan}
              onChange={(e) => setForm({ ...form, repair_plan: e.target.value })} />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">≥80% плана → 2%, иначе 1%</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">План по косметике</label>
            <input type="number" className="input w-full" placeholder="0"
              value={form.cosmetics_plan}
              onChange={(e) => setForm({ ...form, cosmetics_plan: e.target.value })} />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">≥80% плана → 8%, иначе 5%</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">План по обуви</label>
            <input type="number" className="input w-full" placeholder="0"
              value={form.shoes_plan}
              onChange={(e) => setForm({ ...form, shoes_plan: e.target.value })} />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">≥80% плана → 5%, иначе 3%</p>
          </div>
          <div className="border-t border-[color:var(--color-border)] pt-4 space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <input type="checkbox" className="w-4 h-4 rounded"
                checked={form.ignore_kpi}
                onChange={(e) => setForm({ ...form, ignore_kpi: e.target.checked })} />
              <span className="text-sm font-medium">Не учитывать KPI</span>
            </label>
            <MultiCategorySelect label="Свести в максимум"
              description="Комиссия всегда по максимальной ставке"
              value={form.force_max}
              onChange={(v) => setForm({ ...form, force_max: v, force_min: form.force_min.filter((k) => !v.includes(k)) })} />
            <MultiCategorySelect label="Свести в минимум"
              description="Комиссия всегда по минимальной ставке"
              value={form.force_min}
              onChange={(v) => setForm({ ...form, force_min: v, force_max: form.force_max.filter((k) => !v.includes(k)) })} />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={onClose}>Отмена</button>
          <button className="btn btn--primary" onClick={handleSave}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}

// ── Fulfillment badge ─────────────────────────────────────────────
function FulfillmentBadge({ value, threshold = 0.8 }) {
  if (!value) return <span className="text-[color:var(--color-muted-foreground)]">—</span>;
  const pct = (value * 100).toFixed(0);
  const color = value >= threshold ? 'bg-green-100 text-green-800'
    : value >= threshold * 0.5     ? 'bg-yellow-100 text-yellow-800'
    :                                 'bg-red-100 text-red-800';
  return <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>{pct}%</span>;
}

// ── Expanded row ──────────────────────────────────────────────────
function ExpandedRow({ row }) {
  const [showOrders, setShowOrders] = useState(false);
  const orders = row.shoes_orders || [];

  return (
    <tr className="bg-[color:var(--color-bg-secondary)]">
      <td colSpan="100%" className="px-4 py-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          {/* Ремонт */}
          <div className="app-card p-3">
            <div className="font-medium mb-2">Ремонт / Химчистка</div>
            <div className="space-y-1 text-[color:var(--color-muted-foreground)]">
              <div className="flex justify-between"><span>Продажи:</span><span className="font-medium">{fmtMoney(row.repair_sales)}</span></div>
              <div className="flex justify-between"><span>План:</span><span>{fmtMoney(row.repair_plan)}</span></div>
              <div className="flex justify-between"><span>Выполнение:</span><FulfillmentBadge value={row.repair_fulfillment} /></div>
              {row.repair_plan > 0 && (
                <div className="flex justify-between">
                  <span>{row.repair_sales >= row.repair_plan ? 'Перевыполнен на:' : 'До плана:'}</span>
                  <span className={`font-medium ${row.repair_sales >= row.repair_plan ? 'text-green-600' : 'text-amber-600'}`}>
                    {fmtMoney(Math.abs(row.repair_plan - row.repair_sales))}
                  </span>
                </div>
              )}
              <div className="flex justify-between"><span>Ставка:</span><span>{fmtRate(row.repair_rate)}</span></div>
              <div className="flex justify-between border-t border-[color:var(--color-border)] pt-1 mt-1">
                <span>Комиссия:</span>
                <span className="font-semibold text-[color:var(--color-primary)]">{fmtMoney(row.repair_commission)}</span>
              </div>
            </div>
          </div>

          {/* Косметика */}
          <div className="app-card p-3">
            <div className="font-medium mb-2">Косметика</div>
            <div className="space-y-1 text-[color:var(--color-muted-foreground)]">
              <div className="flex justify-between"><span>Продажи:</span><span className="font-medium">{fmtMoney(row.cosmetics_sales)}</span></div>
              <div className="flex justify-between"><span>План:</span><span>{fmtMoney(row.cosmetics_plan)}</span></div>
              <div className="flex justify-between"><span>Выполнение:</span><FulfillmentBadge value={row.cosmetics_fulfillment} /></div>
              {row.cosmetics_plan > 0 && (
                <div className="flex justify-between">
                  <span>{row.cosmetics_sales >= row.cosmetics_plan ? 'Перевыполнен на:' : 'До плана:'}</span>
                  <span className={`font-medium ${row.cosmetics_sales >= row.cosmetics_plan ? 'text-green-600' : 'text-amber-600'}`}>
                    {fmtMoney(Math.abs(row.cosmetics_plan - row.cosmetics_sales))}
                  </span>
                </div>
              )}
              <div className="flex justify-between"><span>Ставка:</span><span>{fmtRate(row.cosmetics_rate)}</span></div>
              <div className="flex justify-between border-t border-[color:var(--color-border)] pt-1 mt-1">
                <span>Комиссия:</span>
                <span className="font-semibold text-[color:var(--color-primary)]">{fmtMoney(row.cosmetics_commission)}</span>
              </div>
            </div>
          </div>

          {/* Обувь + авансы */}
          <div className="space-y-3">
            <div className="app-card p-3">
              <div className="font-medium mb-2">Обувь</div>
              <div className="space-y-1 text-[color:var(--color-muted-foreground)]">
                <div className="flex justify-between"><span>Продажи:</span><span className="font-medium">{fmtMoney(row.shoes_sales)}</span></div>
                <div className="flex justify-between"><span>Ставка:</span><span>{fmtRate(row.shoes_rate)}</span></div>
                <div className="flex justify-between border-t border-[color:var(--color-border)] pt-1 mt-1">
                  <span>Комиссия:</span>
                  <button
                    className="font-semibold text-[color:var(--color-primary)] flex items-center gap-1 hover:underline"
                    onClick={(e) => { e.stopPropagation(); setShowOrders((v) => !v); }}>
                    {fmtMoney(row.shoes_commission)}
                    {orders.length > 0 && (showOrders ? <ChevronUp size={13} /> : <ChevronDown size={13} />)}
                  </button>
                </div>
                {showOrders && orders.length > 0 && (
                  <div className="mt-2 pt-2 border-t border-[color:var(--color-border)]">
                    <div className="text-xs font-medium mb-1">Заказы ({orders.length}):</div>
                    <div className="flex flex-col gap-0.5 max-h-32 overflow-y-auto">
                      {orders.map((num) => (
                        <span key={num} className="text-xs font-mono">{num}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Авансы за месяц */}
            {(row.advances_this_month > 0 || row.advances > 0) && (
              <div className="app-card p-3">
                <div className="font-medium mb-2 text-[color:var(--color-danger)]">Авансы</div>
                <div className="space-y-1 text-[color:var(--color-muted-foreground)]">
                  <div className="flex justify-between">
                    <span>За этот месяц:</span>
                    <span className="font-medium text-[color:var(--color-danger)]">{fmtMoney(row.advances_this_month)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>К вычету (с посл. ЗП):</span>
                    <span className="font-medium text-[color:var(--color-danger)]">{fmtMoney(row.advances)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────
export default function Payroll() {
  const { toast } = useToast();
  const [months, setMonths]           = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows]               = useState([]);
  const [plans, setPlans]             = useState([]);
  const [loading, setLoading]         = useState(false);
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [query, setQuery]             = useState('');
  const [expandedRows, setExpandedRows]   = useState(new Set());
  const [editingPlan, setEditingPlan] = useState(null);

  const { month: currentMonth, year: currentYear } = parseSelectedMonth(selectedMonth);
  const monthKey = selectedMonth ? makeMonthKey(selectedMonth, currentYear) : null;

  useEffect(() => { loadMonths(); }, []);
  useEffect(() => { if (selectedMonth) { loadPayroll(selectedMonth); loadPlans(selectedMonth); } else setRows([]); }, [selectedMonth]);

  async function loadMonths() {
    setLoadingMonths(true);
    try {
      const res = await api.get('payroll/months');
      const list = res.data || [];
      setMonths(list);
      if (list.length > 0) setSelectedMonth(list[0]);
    } catch { toast('Ошибка загрузки месяцев', 'error'); }
    finally { setLoadingMonths(false); }
  }

  async function loadPlans(month) {
    try {
      const res = await api.get('payroll/plans', {
        params: { month, year: currentYear },
      });
      setPlans(res.data || []);
    } catch (err) { console.error(err); }
  }

  async function loadPayroll(month) {
    setLoading(true);
    try {
      const res = await api.get('payroll/calculate', { params: { month } });
      setRows(res.data || []);
    } catch { toast('Ошибка загрузки данных', 'error'); }
    finally { setLoading(false); }
  }

  async function savePlan(planData) {
    try {
      await api.put('payroll/plans', planData);
      toast('План сохранён', 'success');
      setEditingPlan(null);
      loadPlans(selectedMonth);
      loadPayroll(selectedMonth);
    } catch { toast('Ошибка сохранения плана', 'error'); }
  }

  async function toggleSettlement(employeeCode, currentPaid) {
    try {
      await api.put(`payroll/settlements/${employeeCode}`, { paid: !currentPaid }, {
        params: { month: selectedMonth, year: currentYear },
      });
      // Optimistic update
      setRows((prev) =>
        prev.map((r) =>
          r.employee_code === employeeCode ? { ...r, settlement_paid: !currentPaid } : r
        )
      );
    } catch { toast('Ошибка сохранения', 'error'); }
  }

  function exportPdf() {
    if (!selectedMonth) return;
    window.open(`/api/salary/report?month=${selectedMonth}`, '_blank');
  }

  const toggleRow = (code) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  };

  const filtered = useMemo(() => {
    if (!query.trim()) return rows;
    const q = query.toLowerCase();
    return rows.filter((r) => r.employee_name?.toLowerCase().includes(q));
  }, [rows, query]);

  return (
    <div className="space-y-6 max-w-full">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">Расчёт зарплаты</h2>
        <button onClick={exportPdf} disabled={!selectedMonth || loading}
          className="btn btn--primary flex items-center gap-2 disabled:opacity-50">
          <Download size={16} />PDF отчёт
        </button>
      </div>

      {/* Controls */}
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
        {selectedMonth && (
          <span className="text-xs text-[color:var(--color-muted-foreground)] bg-[color:var(--color-bg-secondary)] px-3 py-1.5 rounded-full border border-[color:var(--color-border)]">
            Планы привязаны к: <span className="font-semibold text-[color:var(--color-primary)]">{monthKey}</span>
          </span>
        )}
        <div className="relative flex-1" style={{ minWidth: 200 }}>
          <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]" />
          <input className="input pl-9 w-full" placeholder="Поиск по ФИО…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {!loading && rows.length > 0 && <SummaryBar rows={filtered} />}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-[color:var(--color-muted-foreground)]">
        <div className="flex items-center gap-1"><Percent size={12} /><span>Ремонт: ≥80% → 2%, иначе 1%</span></div>
        <div className="flex items-center gap-1"><Percent size={12} /><span>Косметика: ≥80% → 8%, иначе 5%</span></div>
        <div className="flex items-center gap-1"><Percent size={12} /><span>Обувь: ≥80% → 5%, иначе 3%</span></div>
        <div className="flex items-center gap-1"><BadgeCheck size={12} className="text-green-500" /><span>Зарплата — отметить получение финального расчёта</span></div>
      </div>

      {/* Table */}
      {!selectedMonth && !loadingMonths ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          Выберите месяц для просмотра данных
        </div>
      ) : loading ? (
        <div className="app-card p-4"><SkeletonTable rows={8} cols={9} /></div>
      ) : filtered.length === 0 ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          {query ? 'Сотрудник не найден' : 'Нет данных за этот месяц'}
        </div>
      ) : (
        <div className="overflow-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
          <table className="min-w-max w-full text-sm divide-y divide-[color:var(--color-border)] bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
            <thead>
              <tr className="bg-[color:var(--color-table-header)]">
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide w-10"></th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide sticky left-0 bg-[color:var(--color-table-header)]">ФИО</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Оклад</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Комиссия</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Премии</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-danger)]">Авансы</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-danger)]">Штрафы</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-primary)]">К выплате</th>
                <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide text-green-600">Зарплата ✓</th>
                <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide">План</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {filtered.map((row, i) => (
                <>
                  <tr
                    key={row.employee_code}
                    className={`transition-colors hover:bg-[color:var(--color-table-row-hover)] cursor-pointer ${
                      row.settlement_paid ? 'bg-green-50/30' :
                      i % 2 === 0 ? '' : 'bg-[color:var(--color-table-row-alt)]'
                    }`}
                    onClick={() => toggleRow(row.employee_code)}
                  >
                    <td className="px-3 py-2.5 text-center">
                      {expandedRows.has(row.employee_code)
                        ? <ChevronUp size={16} className="text-[color:var(--color-muted-foreground)]" />
                        : <ChevronDown size={16} className="text-[color:var(--color-muted-foreground)]" />}
                    </td>
                    <td className="px-3 py-2.5 sticky left-0 bg-[color:var(--color-table-bg)] font-medium">
                      <div className="flex items-center gap-2">
                        {row.settlement_paid && <BadgeCheck size={14} className="text-green-500 shrink-0" />}
                        <div>
                          <div>{row.employee_name}</div>
                          <div className="text-xs text-[color:var(--color-muted-foreground)]">{row.employee_code}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">{fmtMoney(row.base_salary)}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {row.ignore_kpi
                        ? <span className="text-[color:var(--color-muted-foreground)]" title="KPI не учитывается">—</span>
                        : fmtMoney(row.total_commission)}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-green-600">
                      {(row.bonuses + row.excel_bonus) > 0 ? `+${fmtMoney(row.bonuses + row.excel_bonus)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-[color:var(--color-danger)]">
                      {row.advances > 0 ? (
                        <span title={`За этот месяц: ${row.advances_this_month?.toLocaleString('ru-RU') || 0} ₽`}>
                          -{fmtMoney(row.advances)}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-[color:var(--color-danger)]">
                      {row.penalties > 0 ? `-${fmtMoney(row.penalties)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap font-semibold text-[color:var(--color-primary)]">
                      {fmtMoney(row.total_net)}
                    </td>

                    {/* ── Зарплата ✓ ── */}
                    <td className="px-3 py-2.5 text-center" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => toggleSettlement(row.employee_code, row.settlement_paid)}
                        title={row.settlement_paid ? 'Расчёт выдан — нажмите для отмены' : 'Отметить как выданный'}
                        className={`p-1.5 rounded transition-colors ${
                          row.settlement_paid
                            ? 'text-green-500 hover:bg-green-100'
                            : 'text-[color:var(--color-muted-foreground)] hover:bg-[color:var(--color-bg-secondary)] hover:text-green-500'
                        }`}
                      >
                        {row.settlement_paid
                          ? <CheckSquare size={18} />
                          : <Square size={18} />}
                      </button>
                    </td>

                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingPlan(row); }}
                        className="p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]"
                        title="Настроить план"
                      >
                        <Settings size={16} />
                      </button>
                    </td>
                  </tr>
                  {expandedRows.has(row.employee_code) && <ExpandedRow key={`exp-${row.employee_code}`} row={row} />}
                </>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-[color:var(--color-table-header)] font-semibold">
                <td className="px-3 py-2.5"></td>
                <td className="px-3 py-2.5 sticky left-0 bg-[color:var(--color-table-header)]">
                  Итого: {filtered.length}
                </td>
                <td className="px-3 py-2.5 text-right">{fmtMoney(filtered.reduce((s, r) => s + r.base_salary, 0))}</td>
                <td className="px-3 py-2.5 text-right">{fmtMoney(filtered.reduce((s, r) => s + r.total_commission, 0))}</td>
                <td className="px-3 py-2.5 text-right text-green-600">
                  +{fmtMoney(filtered.reduce((s, r) => s + r.bonuses + r.excel_bonus, 0))}
                </td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-danger)]">
                  -{fmtMoney(filtered.reduce((s, r) => s + r.advances, 0))}
                </td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-danger)]">
                  -{fmtMoney(filtered.reduce((s, r) => s + r.penalties, 0))}
                </td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-primary)]">
                  {fmtMoney(filtered.reduce((s, r) => s + r.total_net, 0))}
                </td>
                <td className="px-3 py-2.5 text-center text-green-600">
                  {filtered.filter((r) => r.settlement_paid).length} / {filtered.length}
                </td>
                <td className="px-3 py-2.5"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Plan Modal */}
      {editingPlan && (
        <PlanModal
          employee={editingPlan}
          plans={plans}
          onSave={savePlan}
          onClose={() => setEditingPlan(null)}
          monthKey={monthKey}
        />
      )}
    </div>
  );
}
