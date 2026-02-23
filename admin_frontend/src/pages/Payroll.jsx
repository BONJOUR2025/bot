import { useEffect, useState, useMemo } from 'react';
import { Download, Search, X, Settings, ChevronDown, ChevronUp, Percent } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';

const fmt = (v) => {
  if (v === null || v === undefined || v === 0) return '—';
  return Number(v).toLocaleString('ru-RU');
};

const fmtMoney = (v) => {
  if (v === null || v === undefined || v === 0) return '—';
  return `${Number(v).toLocaleString('ru-RU')} ₽`;
};

const fmtPercent = (v) => {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(0)}%`;
};

const fmtRate = (v) => {
  if (v === null || v === undefined) return '—';
  return `${(v * 100).toFixed(0)}%`;
};

function SummaryBar({ rows }) {
  const totalNet = rows.reduce((s, r) => s + (r.total_net || 0), 0);
  const totalGross = rows.reduce((s, r) => s + (r.total_gross || 0), 0);
  const totalSalary = rows.reduce((s, r) => s + (r.base_salary || 0), 0);
  const totalCommission = rows.reduce((s, r) => s + (r.total_commission || 0), 0);
  const totalBonuses = rows.reduce((s, r) => s + (r.bonuses || 0) + (r.excel_bonus || 0), 0);
  const totalAdvances = rows.reduce((s, r) => s + (r.advances || 0), 0);
  const totalPenalties = rows.reduce((s, r) => s + (r.penalties || 0), 0);

  const stats = [
    { label: 'Сотрудников', value: rows.length, accent: false },
    { label: 'Оклады', value: fmtMoney(totalSalary), accent: false },
    { label: 'Комиссии', value: fmtMoney(totalCommission), accent: false },
    { label: 'Премии', value: fmtMoney(totalBonuses), accent: false },
    { label: 'Авансы', value: fmtMoney(totalAdvances), accent: true },
    { label: 'Штрафы', value: fmtMoney(totalPenalties), accent: true },
    { label: 'К выплате', value: fmtMoney(totalNet), accent: false },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
      {stats.map((s) => (
        <div key={s.label} className="app-card p-4 text-center">
          <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{s.label}</div>
          <div
            className={`text-base font-semibold ${
              s.accent ? 'text-[color:var(--color-danger)]' : 'text-[color:var(--color-text-primary)]'
            }`}
          >
            {s.value}
          </div>
        </div>
      ))}
    </div>
  );
}

const PLAN_CATEGORIES = [
  { key: 'repair', label: 'Ремонт' },
  { key: 'cosmetics', label: 'Косметика' },
  { key: 'shoes', label: 'Обувь' },
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
            <input
              type="checkbox"
              className="w-4 h-4 rounded border-gray-300"
              checked={value.includes(key)}
              onChange={() => toggle(key)}
            />
            {catLabel}
          </label>
        ))}
      </div>
      {description && (
        <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{description}</p>
      )}
    </div>
  );
}

function PlanModal({ employee, plans, onSave, onClose }) {
  const existing = plans.find((p) => p.employee_code === employee.employee_code);
  const [form, setForm] = useState({
    repair_plan: existing?.repair_plan || 0,
    cosmetics_plan: existing?.cosmetics_plan || 0,
    shoes_plan: existing?.shoes_plan || 0,
    ignore_kpi: existing?.ignore_kpi || false,
    force_max: existing?.force_max || [],
    force_min: existing?.force_min || [],
  });

  const handleSave = () => {
    onSave({
      employee_code: employee.employee_code,
      employee_name: employee.employee_name,
      repair_plan: parseFloat(form.repair_plan) || 0,
      cosmetics_plan: parseFloat(form.cosmetics_plan) || 0,
      shoes_plan: parseFloat(form.shoes_plan) || 0,
      ignore_kpi: form.ignore_kpi,
      force_max: form.force_max,
      force_min: form.force_min,
    });
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-card max-w-md">
        <h3 className="text-lg font-semibold mb-4">
          План продаж: {employee.employee_name}
        </h3>
        <p className="text-sm text-[color:var(--color-muted-foreground)] mb-4">
          Код: {employee.employee_code}
        </p>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">План по ремонту/химчистке</label>
            <input
              type="number"
              className="input w-full"
              placeholder="0"
              value={form.repair_plan}
              onChange={(e) => setForm({ ...form, repair_plan: e.target.value })}
            />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
              ≥80% плана → 2%, иначе 1%
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">План по косметике</label>
            <input
              type="number"
              className="input w-full"
              placeholder="0"
              value={form.cosmetics_plan}
              onChange={(e) => setForm({ ...form, cosmetics_plan: e.target.value })}
            />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
              ≥80% плана → 8%, иначе 5%
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium mb-1">План по обуви</label>
            <input
              type="number"
              className="input w-full"
              placeholder="0"
              value={form.shoes_plan}
              onChange={(e) => setForm({ ...form, shoes_plan: e.target.value })}
            />
            <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">
              ≥80% плана → 5%, иначе 3%
            </p>
          </div>

          <div className="border-t border-[color:var(--color-border)] pt-4 space-y-3">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                className="w-4 h-4 rounded border-gray-300 text-[color:var(--color-primary)] focus:ring-[color:var(--color-primary)]"
                checked={form.ignore_kpi}
                onChange={(e) => setForm({ ...form, ignore_kpi: e.target.checked })}
              />
              <span className="text-sm font-medium">Не учитывать KPI</span>
            </label>
            <p className="text-xs text-[color:var(--color-muted-foreground)] ml-7 -mt-2">
              Комиссии по всем категориям будут обнулены
            </p>

            <MultiCategorySelect
              label="Свести в максимум"
              description="Комиссия всегда по максимальной ставке (независимо от выполнения плана)"
              value={form.force_max}
              onChange={(v) => setForm({ ...form, force_max: v, force_min: form.force_min.filter((k) => !v.includes(k)) })}
            />

            <MultiCategorySelect
              label="Свести в минимум"
              description="Комиссия всегда по минимальной ставке (независимо от выполнения плана)"
              value={form.force_min}
              onChange={(v) => setForm({ ...form, force_min: v, force_max: form.force_max.filter((k) => !v.includes(k)) })}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button className="btn bg-gray-200 text-gray-700 hover:bg-gray-300" onClick={onClose}>
            Отмена
          </button>
          <button className="btn btn--primary" onClick={handleSave}>
            Сохранить
          </button>
        </div>
      </div>
    </div>
  );
}

function FulfillmentBadge({ value, threshold = 0.8 }) {
  if (value === null || value === undefined || value === 0) {
    return <span className="text-[color:var(--color-muted-foreground)]">—</span>;
  }
  const pct = (value * 100).toFixed(0);
  const color = value >= threshold
    ? 'bg-green-100 text-green-800'
    : value >= threshold * 0.5
    ? 'bg-yellow-100 text-yellow-800'
    : 'bg-red-100 text-red-800';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      {pct}%
    </span>
  );
}

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
              <div className="flex justify-between">
                <span>Продажи:</span>
                <span className="font-medium text-[color:var(--color-text-primary)]">{fmtMoney(row.repair_sales)}</span>
              </div>
              <div className="flex justify-between">
                <span>План:</span>
                <span>{fmtMoney(row.repair_plan)}</span>
              </div>
              <div className="flex justify-between">
                <span>Выполнение:</span>
                <FulfillmentBadge value={row.repair_fulfillment} />
              </div>
              {row.repair_plan > 0 && (
                <div className="flex justify-between">
                  <span>{row.repair_sales >= row.repair_plan ? 'Перевыполнен на:' : 'Осталось до выполнения:'}</span>
                  <span className={`font-medium ${row.repair_sales >= row.repair_plan ? 'text-green-600' : 'text-amber-600'}`}>
                    {fmtMoney(Math.abs(row.repair_plan - row.repair_sales))}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Ставка:</span>
                <span>{fmtRate(row.repair_rate)}</span>
              </div>
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
              <div className="flex justify-between">
                <span>Продажи:</span>
                <span className="font-medium text-[color:var(--color-text-primary)]">{fmtMoney(row.cosmetics_sales)}</span>
              </div>
              <div className="flex justify-between">
                <span>План:</span>
                <span>{fmtMoney(row.cosmetics_plan)}</span>
              </div>
              <div className="flex justify-between">
                <span>Выполнение:</span>
                <FulfillmentBadge value={row.cosmetics_fulfillment} />
              </div>
              {row.cosmetics_plan > 0 && (
                <div className="flex justify-between">
                  <span>{row.cosmetics_sales >= row.cosmetics_plan ? 'Перевыполнен на:' : 'Осталось до выполнения:'}</span>
                  <span className={`font-medium ${row.cosmetics_sales >= row.cosmetics_plan ? 'text-green-600' : 'text-amber-600'}`}>
                    {fmtMoney(Math.abs(row.cosmetics_plan - row.cosmetics_sales))}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span>Ставка:</span>
                <span>{fmtRate(row.cosmetics_rate)}</span>
              </div>
              <div className="flex justify-between border-t border-[color:var(--color-border)] pt-1 mt-1">
                <span>Комиссия:</span>
                <span className="font-semibold text-[color:var(--color-primary)]">{fmtMoney(row.cosmetics_commission)}</span>
              </div>
            </div>
          </div>

          {/* Обувь */}
          <div className="app-card p-3">
            <div className="font-medium mb-2">Обувь</div>
            <div className="space-y-1 text-[color:var(--color-muted-foreground)]">
              <div className="flex justify-between">
                <span>Продажи:</span>
                <span className="font-medium text-[color:var(--color-text-primary)]">{fmtMoney(row.shoes_sales)}</span>
              </div>
              <div className="flex justify-between">
                <span>План:</span>
                <span>{fmtMoney(row.shoes_plan)}</span>
              </div>
              <div className="flex justify-between">
                <span>Выполнение:</span>
                <FulfillmentBadge value={row.shoes_fulfillment} />
              </div>
              <div className="flex justify-between">
                <span>Ставка:</span>
                <span>{fmtRate(row.shoes_rate)}</span>
              </div>
              <div className="flex justify-between border-t border-[color:var(--color-border)] pt-1 mt-1">
                <span>Комиссия:</span>
                <button
                  className="font-semibold text-[color:var(--color-primary)] flex items-center gap-1 hover:underline"
                  onClick={(e) => { e.stopPropagation(); setShowOrders((v) => !v); }}
                  title={orders.length ? 'Показать заказы' : 'Нет заказов'}
                >
                  {fmtMoney(row.shoes_commission)}
                  {orders.length > 0 && (
                    showOrders ? <ChevronUp size={13} /> : <ChevronDown size={13} />
                  )}
                </button>
              </div>

              {showOrders && orders.length > 0 && (
                <div className="mt-2 pt-2 border-t border-[color:var(--color-border)]">
                  <div className="text-xs font-medium mb-1">
                    Заказы ({orders.length}):
                  </div>
                  <div className="flex flex-col gap-0.5 max-h-32 overflow-y-auto">
                    {orders.map((num) => (
                      <span
                        key={num}
                        className="text-xs font-mono text-[color:var(--color-text-primary)]"
                      >
                        {num}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </td>
    </tr>
  );
}

export default function Payroll() {
  const { toast } = useToast();
  const [months, setMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows] = useState([]);
  const [plans, setPlans] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [query, setQuery] = useState('');
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [editingPlan, setEditingPlan] = useState(null);

  useEffect(() => {
    loadMonths();
    loadPlans();
  }, []);

  useEffect(() => {
    if (selectedMonth) loadPayroll(selectedMonth);
    else setRows([]);
  }, [selectedMonth]);

  async function loadMonths() {
    setLoadingMonths(true);
    try {
      const res = await api.get('payroll/months');
      const list = res.data || [];
      setMonths(list);
      if (list.length > 0) setSelectedMonth(list[0]);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки месяцев', 'error');
    } finally {
      setLoadingMonths(false);
    }
  }

  async function loadPlans() {
    try {
      const res = await api.get('payroll/plans');
      setPlans(res.data || []);
    } catch (err) {
      console.error(err);
    }
  }

  async function loadPayroll(month) {
    setLoading(true);
    try {
      const res = await api.get('payroll/calculate', { params: { month } });
      setRows(res.data || []);
    } catch (err) {
      console.error(err);
      toast('Ошибка загрузки данных', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function savePlan(planData) {
    try {
      await api.put('payroll/plans', planData);
      toast('План сохранён', 'success');
      setEditingPlan(null);
      loadPlans();
      if (selectedMonth) loadPayroll(selectedMonth);
    } catch (err) {
      console.error(err);
      toast('Ошибка сохранения плана', 'error');
    }
  }

  function exportPdf() {
    if (!selectedMonth) return;
    // Using the old salary report endpoint for PDF
    window.open(`/api/salary/report?month=${selectedMonth}`, '_blank');
  }

  const toggleRow = (code) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
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
        <button
          onClick={exportPdf}
          disabled={!selectedMonth || loading}
          className="btn btn--primary flex items-center gap-2 disabled:opacity-50"
        >
          <Download size={16} />
          PDF отчёт
        </button>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {loadingMonths ? (
          <Skeleton style={{ width: 160, height: 38, borderRadius: 8 }} />
        ) : (
          <select
            className="input"
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="">Выберите месяц</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        )}

        <div className="relative flex-1" style={{ minWidth: 200 }}>
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)]"
          />
          <input
            className="input pl-9 w-full"
            placeholder="Поиск по ФИО…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {query && (
            <button
              onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Summary */}
      {!loading && rows.length > 0 && <SummaryBar rows={filtered} />}

      {/* Legend */}
      <div className="flex flex-wrap gap-4 text-xs text-[color:var(--color-muted-foreground)]">
        <div className="flex items-center gap-1">
          <Percent size={12} />
          <span>Ремонт: ≥80% → 2%, иначе 1%</span>
        </div>
        <div className="flex items-center gap-1">
          <Percent size={12} />
          <span>Косметика: ≥80% → 8%, иначе 5%</span>
        </div>
        <div className="flex items-center gap-1">
          <Percent size={12} />
          <span>Обувь: ≥80% → 5%, иначе 3%</span>
        </div>
      </div>

      {/* Table */}
      {!selectedMonth && !loadingMonths ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">
          Выберите месяц для просмотра данных
        </div>
      ) : loading ? (
        <div className="app-card p-4">
          <SkeletonTable rows={8} cols={8} />
        </div>
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
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide sticky left-0 bg-[color:var(--color-table-header)]">
                  ФИО
                </th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Оклад</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Комиссия</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Премии</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-danger)]">
                  Авансы
                </th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-danger)]">
                  Штрафы
                </th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-primary)]">
                  К выплате
                </th>
                <th className="px-3 py-3 text-center text-xs font-semibold uppercase tracking-wide">План</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[color:var(--color-border)]">
              {filtered.map((row, i) => (
                <>
                  <tr
                    key={row.employee_code}
                    className={`transition-colors hover:bg-[color:var(--color-table-row-hover)] cursor-pointer ${
                      i % 2 === 0 ? '' : 'bg-[color:var(--color-table-row-alt)]'
                    }`}
                    onClick={() => toggleRow(row.employee_code)}
                  >
                    <td className="px-3 py-2.5 text-center">
                      {expandedRows.has(row.employee_code) ? (
                        <ChevronUp size={16} className="text-[color:var(--color-muted-foreground)]" />
                      ) : (
                        <ChevronDown size={16} className="text-[color:var(--color-muted-foreground)]" />
                      )}
                    </td>
                    <td className="px-3 py-2.5 sticky left-0 bg-[color:var(--color-table-bg)] font-medium">
                      <div>{row.employee_name}</div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)]">
                        {row.employee_code}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">{fmtMoney(row.base_salary)}</td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      {row.ignore_kpi ? (
                        <span className="text-[color:var(--color-muted-foreground)]" title="KPI не учитывается">—</span>
                      ) : (
                        fmtMoney(row.total_commission)
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-green-600">
                      {(row.bonuses + row.excel_bonus) > 0 ? `+${fmtMoney(row.bonuses + row.excel_bonus)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-[color:var(--color-danger)]">
                      {row.advances > 0 ? `-${fmtMoney(row.advances)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-[color:var(--color-danger)]">
                      {row.penalties > 0 ? `-${fmtMoney(row.penalties)}` : '—'}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap font-semibold text-[color:var(--color-primary)]">
                      {fmtMoney(row.total_net)}
                    </td>
                    <td className="px-3 py-2.5 text-center">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setEditingPlan(row);
                        }}
                        className="p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]"
                        title="Настроить план"
                      >
                        <Settings size={16} />
                      </button>
                    </td>
                  </tr>
                  {expandedRows.has(row.employee_code) && <ExpandedRow row={row} />}
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
        />
      )}
    </div>
  );
}
