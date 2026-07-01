import { useEffect, useState, useMemo, useCallback, useRef } from 'react';
import {
  Download, Search, X, Settings, ChevronDown, ChevronUp, Percent,
  CheckSquare, Square, BadgeCheck, AlertTriangle, MessageSquare,
  History, FileSpreadsheet, TrendingUp, TrendingDown, Minus, Trophy, PieChart as PieChartIcon,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import Skeleton from '../components/ui/Skeleton.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';

const fmt = (v) => (v === null || v === undefined || v === 0 ? '—' : Number(v).toLocaleString('ru-RU'));
const fmtMoney = (v) => (v === null || v === undefined || v === 0 ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
const fmtRate = (v) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(0)}%`);
// Gross pay (начислено до удержаний): prefer the server-computed value, fall
// back to summing the parts for older rows that predate the field.
const grossOf = (r) => r.total_gross ?? (r.base_salary + r.total_commission + r.bonuses + r.excel_bonus);

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

// ── Anomaly detection ─────────────────────────────────────────────
function getAnomalyFlags(row) {
  const flags = [];
  const gross = row.total_gross || (row.base_salary + row.total_commission + row.bonuses + row.excel_bonus);
  if (gross > 0 && row.penalties / gross > 0.2)
    flags.push('Удержания > 20% от начисления');
  if (row.repair_plan > 0 && row.repair_fulfillment != null && row.repair_fulfillment < 0.5)
    flags.push('Выполнение ремонта < 50%');
  if (row.cosmetics_plan > 0 && row.cosmetics_fulfillment != null && row.cosmetics_fulfillment < 0.5)
    flags.push('Выполнение косметики < 50%');
  if (row.force_max?.length > 0)
    flags.push(`Force MAX: ${row.force_max.join(', ')}`);
  if (row.force_min?.length > 0)
    flags.push(`Force MIN: ${row.force_min.join(', ')}`);
  return flags;
}

// ── Trend badge ───────────────────────────────────────────────────
function TrendBadge({ current, prev }) {
  if (prev == null || prev === 0) return null;
  const delta = ((current - prev) / prev) * 100;
  if (Math.abs(delta) < 2) return <Minus size={13} className="text-[color:var(--color-text-faint)]" title={`Пред. месяц: ${Math.round(prev).toLocaleString('ru-RU')} ₽`} />;
  if (delta > 0) return (
    <span title={`Пред. месяц: ${Math.round(prev).toLocaleString('ru-RU')} ₽ (+${delta.toFixed(1)}%)`}>
      <TrendingUp size={13} className="text-green-500" />
    </span>
  );
  return (
    <span title={`Пред. месяц: ${Math.round(prev).toLocaleString('ru-RU')} ₽ (${delta.toFixed(1)}%)`}>
      <TrendingDown size={13} className="text-red-500" />
    </span>
  );
}

// ── Comment modal ─────────────────────────────────────────────────
function CommentModal({ employee, currentComment, onSave, onClose }) {
  const [text, setText] = useState(currentComment || '');
  return (
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal-card max-w-sm">
        <h3 className="text-base font-semibold mb-3">
          Комментарий: {employee.employee_name}
        </h3>
        <textarea
          className="input w-full h-28 resize-none text-sm"
          placeholder="Заметка к выплате…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div className="flex justify-end gap-2 mt-3">
          <button className="btn btn--secondary" onClick={onClose}>Отмена</button>
          <button className="btn btn--primary" onClick={() => onSave(text)}>Сохранить</button>
        </div>
      </div>
    </div>
  );
}

// ── Summary bar ───────────────────────────────────────────────────
function SummaryBar({ rows }) {
  const totalNet        = rows.reduce((s, r) => s + (r.total_net || 0), 0);
  const totalGross       = rows.reduce((s, r) => s + (r.total_gross ?? (r.base_salary + r.total_commission + r.bonuses + r.excel_bonus)), 0);
  const totalSalary     = rows.reduce((s, r) => s + (r.base_salary || 0), 0);
  const totalCommission = rows.reduce((s, r) => s + (r.total_commission || 0), 0);
  const totalBonuses    = rows.reduce((s, r) => s + (r.bonuses || 0) + (r.excel_bonus || 0), 0);
  const totalAdvances   = rows.reduce((s, r) => s + (r.advances || 0), 0);
  const totalPenalties  = rows.reduce((s, r) => s + (r.penalties || 0), 0);
  const paidCount       = rows.filter((r) => r.settlement_paid).length;

  // Two deliberate rows: the headline figures (счёт, фонды, итог к выплате)
  // on top, the component breakdown below — instead of one long cramped strip.
  const rowTop = [
    { label: 'Сотрудников', value: rows.length },
    { label: 'ФОТ',         value: fmtMoney(totalGross), strong: true },
    { label: 'К выплате',   value: fmtMoney(totalNet), primary: true },
    { label: 'Расчёт выдан', value: `${paidCount} / ${rows.length}`, green: true },
  ];
  const rowBottom = [
    { label: 'Оклады',    value: fmtMoney(totalSalary) },
    { label: 'Комиссии',  value: fmtMoney(totalCommission) },
    { label: 'Премии',    value: fmtMoney(totalBonuses), green: true },
    { label: 'Авансы',    value: fmtMoney(totalAdvances), accent: true },
    { label: 'Штрафы',    value: fmtMoney(totalPenalties), accent: true },
  ];

  const Card = (s) => (
    <div key={s.label} className="app-card px-4 py-3 flex flex-col gap-1">
      <div className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{s.label}</div>
      <div className={`font-semibold ${s.strong || s.primary ? 'text-xl' : 'text-lg'} ${
        s.accent   ? 'text-[color:var(--color-danger)]' :
        s.green    ? 'text-[color:var(--color-success)]' :
        s.primary  ? 'text-[color:var(--color-primary)]' :
        'text-[color:var(--color-text-primary)]'
      }`}>{s.value}</div>
    </div>
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{rowTop.map(Card)}</div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{rowBottom.map(Card)}</div>
    </div>
  );
}

// ── Composition donut + top earners (click-to-filter by name) ─────
const COMP_COLORS = ['#6366f1', '#10b981', '#f59e0b'];

function CompositionAndLeaders({ rows, query, onSelectEmployee }) {
  const totalSalary     = rows.reduce((s, r) => s + (r.base_salary || 0), 0);
  const totalCommission = rows.reduce((s, r) => s + (r.total_commission || 0), 0);
  const totalBonuses    = rows.reduce((s, r) => s + (r.bonuses || 0) + (r.excel_bonus || 0), 0);
  const compData = [
    { name: 'Оклады', value: totalSalary, color: COMP_COLORS[0] },
    { name: 'Комиссии', value: totalCommission, color: COMP_COLORS[1] },
    { name: 'Премии', value: totalBonuses, color: COMP_COLORS[2] },
  ].filter((d) => d.value > 0);
  const compTotal = totalSalary + totalCommission + totalBonuses;

  const leaders = [...rows]
    .sort((a, b) => grossOf(b) - grossOf(a))
    .slice(0, 6);
  const medals = ['🥇', '🥈', '🥉'];

  if (!rows.length) return null;

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="app-card p-5">
        <div className="text-sm font-semibold mb-4 flex items-center gap-2">
          <PieChartIcon size={15} className="text-[color:var(--color-primary)]" />
          Структура начислений
        </div>
        {compData.length === 0 ? (
          <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-8">Нет данных</div>
        ) : (
          <div className="flex flex-col sm:flex-row gap-4 items-center">
            <div style={{ width: 150, height: 150, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={compData} dataKey="value" nameKey="name" innerRadius="50%" outerRadius="80%" paddingAngle={2}>
                    {compData.map((d) => <Cell key={d.name} fill={d.color} stroke="none" />)}
                  </Pie>
                  <Tooltip formatter={(v) => [fmtMoney(v), 'Сумма']} />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2 min-w-0 w-full">
              {compData.map((d) => {
                const pct = compTotal > 0 ? (d.value / compTotal) * 100 : 0;
                return (
                  <div key={d.name} className="flex items-center gap-2">
                    <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1">
                        <span className="text-xs truncate">{d.name}</span>
                        <span className="text-xs font-semibold shrink-0">{fmtMoney(d.value)} ({pct.toFixed(0)}%)</span>
                      </div>
                      <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: d.color }} />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <div className="app-card p-5">
        <div className="text-sm font-semibold mb-4 flex items-center gap-2">
          <Trophy size={15} className="text-[color:var(--color-primary)]" />
          Топ по начислению
          {query && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {query}</span>}
        </div>
        <div className="space-y-3">
          {leaders.map((r, i) => {
            const isActive = query === r.employee_name;
            return (
              <button key={r.employee_code} type="button" onClick={() => onSelectEmployee(isActive ? '' : r.employee_name)}
                className={`w-full text-left rounded-md -mx-1 px-1 py-1 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    {i < 3 ? <span className="text-base shrink-0">{medals[i]}</span> : <span className="w-5 text-center text-xs font-bold text-[color:var(--color-muted-foreground)] shrink-0">{i + 1}</span>}
                    <span className="text-sm font-medium truncate">{r.employee_name}</span>
                  </div>
                  <span className="text-sm font-bold text-[color:var(--color-primary)] shrink-0 ml-2">{fmtMoney(grossOf(r))}</span>
                </div>
              </button>
            );
          })}
          {leaders.length === 0 && <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет данных</div>}
        </div>
      </div>
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
    <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && onClose()}>
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
          <button className="btn btn--secondary" onClick={onClose}>Отмена</button>
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

// ── Plan progress rows ────────────────────────────────────────────
function PlanProgressRows({ sales, plan }) {
  if (!plan || plan <= 0) return null;
  const t80  = plan * 0.8;
  const until80  = t80  - sales;
  const until100 = plan - sales;
  const over     = sales - plan;
  return (
    <>
      {until80 > 0 ? (
        <div className="flex justify-between gap-3">
          <span className="text-[color:var(--color-muted-foreground)]">До 80%</span>
          <span className="font-medium text-red-500">−{fmtMoney(until80)}</span>
        </div>
      ) : (
        <div className="flex justify-between gap-3">
          <span className="text-green-600 font-medium">✓ 80% выполнен</span>
          <span className="text-green-600 text-xs">{fmtMoney(sales - t80)} сверх</span>
        </div>
      )}
      {until100 > 0 ? (
        <div className="flex justify-between gap-3">
          <span className="text-[color:var(--color-muted-foreground)]">До 100%</span>
          <span className="font-medium text-amber-500">−{fmtMoney(until100)}</span>
        </div>
      ) : (
        <>
          <div className="flex justify-between gap-3">
            <span className="text-green-600 font-medium">✓ 100% выполнен</span>
            <span></span>
          </div>
          <div className="flex justify-between gap-3">
            <span className="text-[color:var(--color-muted-foreground)]">Перевыполнение</span>
            <span className="font-medium text-green-600">+{fmtMoney(over)}</span>
          </div>
        </>
      )}
    </>
  );
}

// ── Compact detail panel + row (used across the expanded breakdown) ───
// Purpose-built instead of <div className="app-card">, whose grid `gap:1rem`
// pushed a loose gap between every panel title and its body.
function DetailCard({ title, titleClass, children }) {
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-table-bg)] p-3 shadow-sm">
      <div className={`text-[11px] font-semibold uppercase tracking-wide mb-2 pb-1.5 border-b border-[color:var(--color-border)] ${titleClass || 'text-[color:var(--color-text-primary)]'}`}>
        {title}
      </div>
      <div className="space-y-1.5 text-sm">{children}</div>
    </div>
  );
}

// Label muted, value dark — keeps figures scannable. `value` may be a node
// (badge, button); pass `valueClass` to recolour the value text.
function DetailRow({ label, value, valueClass }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-[color:var(--color-muted-foreground)]">{label}</span>
      <span className={valueClass || 'font-medium text-[color:var(--color-text-primary)]'}>{value}</span>
    </div>
  );
}

// The panel's bottom-line total — divider above, accent value.
function CommissionRow({ value }) {
  return (
    <div className="flex justify-between gap-3 border-t border-[color:var(--color-border)] pt-1.5 mt-0.5">
      <span className="text-[color:var(--color-muted-foreground)]">Комиссия</span>
      <span className="font-semibold text-[color:var(--color-primary)]">{value}</span>
    </div>
  );
}

// ── Expanded content (shared between table row and mobile card) ───
function ExpandedContent({ row }) {
  const [showOrders, setShowOrders] = useState(false);
  const orders = row.shoes_orders || [];
  const shiftEntries = Object.entries(row.shifts_by_point || {}).sort((a, b) => b[1] - a[1]);
  const totalShifts = shiftEntries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="space-y-4 text-sm">
      {/* Salary breakdown */}
      {(row.main_rate > 0 || row.extra_rate > 0 || shiftEntries.length > 0) && (
        <DetailCard title="Оклад — расчёт по сменам">
          {row.main_rate > 0 && (
            <DetailRow
              label="Осн. ставка (1–15 смен)"
              value={<><span className="text-[color:var(--color-muted-foreground)] font-normal">{fmtMoney(row.main_rate)}/смену × {row.main_shifts || 0} = </span>{fmtMoney((row.main_rate || 0) * (row.main_shifts || 0))}</>}
            />
          )}
          {row.extra_rate > 0 && row.extra_shifts > 0 && (
            <DetailRow
              label="Доп. ставка (от 16-й смены)"
              value={<><span className="text-[color:var(--color-muted-foreground)] font-normal">{fmtMoney(row.extra_rate)}/смену × {row.extra_shifts} = </span>{fmtMoney((row.extra_rate || 0) * (row.extra_shifts || 0))}</>}
            />
          )}
          {shiftEntries.length > 0 && (
            <div className="pt-1.5 mt-0.5 border-t border-[color:var(--color-border)]">
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1.5">Смены по точкам ({totalShifts} всего)</div>
              <div className="flex flex-wrap gap-1.5">
                {shiftEntries.map(([code, cnt]) => (
                  <span key={code} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-xs font-medium">
                    {code} <span className="font-bold">{cnt}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </DetailCard>
      )}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-start">
      {/* Ремонт */}
      <DetailCard title="Ремонт / Химчистка">
        <DetailRow label="Продажи" value={fmtMoney(row.repair_sales)} />
        <DetailRow label="План" value={fmtMoney(row.repair_plan)} valueClass="text-[color:var(--color-muted-foreground)]" />
        <DetailRow label="Выполнение" value={<FulfillmentBadge value={row.repair_fulfillment} />} valueClass="" />
        <PlanProgressRows sales={row.repair_sales} plan={row.repair_plan} />
        <DetailRow label="Ставка" value={fmtRate(row.repair_rate)} valueClass="text-[color:var(--color-muted-foreground)]" />
        <CommissionRow value={fmtMoney(row.repair_commission)} />
      </DetailCard>

      {/* Косметика */}
      <DetailCard title="Косметика">
        <DetailRow label="Продажи" value={fmtMoney(row.cosmetics_sales)} />
        <DetailRow label="План" value={fmtMoney(row.cosmetics_plan)} valueClass="text-[color:var(--color-muted-foreground)]" />
        <DetailRow label="Выполнение" value={<FulfillmentBadge value={row.cosmetics_fulfillment} />} valueClass="" />
        <PlanProgressRows sales={row.cosmetics_sales} plan={row.cosmetics_plan} />
        <DetailRow label="Ставка" value={fmtRate(row.cosmetics_rate)} valueClass="text-[color:var(--color-muted-foreground)]" />
        <CommissionRow value={fmtMoney(row.cosmetics_commission)} />
      </DetailCard>

      {/* Обувь + авансы */}
      <div className="space-y-4">
        <DetailCard title="Обувь">
          <DetailRow label="Продажи" value={fmtMoney(row.shoes_sales)} />
          <DetailRow label="Ставка" value={fmtRate(row.shoes_rate)} valueClass="text-[color:var(--color-muted-foreground)]" />
          <CommissionRow value={
            <button
              className="font-semibold text-[color:var(--color-primary)] flex items-center gap-1 hover:underline"
              onClick={(e) => { e.stopPropagation(); setShowOrders((v) => !v); }}>
              {fmtMoney(row.shoes_commission)}
              {orders.length > 0 && (showOrders ? <ChevronUp size={13} /> : <ChevronDown size={13} />)}
            </button>
          } />
          {showOrders && orders.length > 0 && (
            <div className="pt-1.5 mt-0.5 border-t border-[color:var(--color-border)]">
              <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">Заказы ({orders.length})</div>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 max-h-32 overflow-y-auto">
                {orders.map((num) => (
                  <span key={num} className="text-xs font-mono text-[color:var(--color-text-primary)]">{num}</span>
                ))}
              </div>
            </div>
          )}
        </DetailCard>

        {(row.bonuses > 0 || row.excel_bonus > 0) && (
          <DetailCard title="Премии" titleClass="text-[color:var(--color-success)]">
            {row.bonuses > 0 && (
              <DetailRow label="Премия" value={`+${fmtMoney(row.bonuses)}`} valueClass="font-medium text-[color:var(--color-success)]" />
            )}
            {row.excel_bonus > 0 && (
              <DetailRow label="Премия (Excel)" value={`+${fmtMoney(row.excel_bonus)}`} valueClass="font-medium text-[color:var(--color-success)]" />
            )}
          </DetailCard>
        )}

        {(row.advances_this_month > 0 || row.advances > 0) && (
          <DetailCard title="Авансы" titleClass="text-[color:var(--color-danger)]">
            <DetailRow label="За этот месяц" value={fmtMoney(row.advances_this_month)} valueClass="font-medium text-[color:var(--color-danger)]" />
            <DetailRow label="К вычету (с посл. ЗП)" value={fmtMoney(row.advances)} valueClass="font-medium text-[color:var(--color-danger)]" />
          </DetailCard>
        )}

        {row.penalties > 0 && (
          <DetailCard title="Штрафы" titleClass="text-[color:var(--color-danger)]">
            <DetailRow label="Сумма" value={`-${fmtMoney(row.penalties)}`} valueClass="font-medium text-[color:var(--color-danger)]" />
          </DetailCard>
        )}
      </div>
    </div>
  </div>
  );
}

// ── Expanded row (table version) ──────────────────────────────────
function ExpandedRow({ row, comment }) {
  const flags = getAnomalyFlags(row);
  return (
    <tr className="bg-[color:var(--color-bg-secondary)]">
      <td colSpan="100%" className="px-4 py-4">
        {flags.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {flags.map((f) => (
              <span key={f} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
                <AlertTriangle size={11} />
                {f}
              </span>
            ))}
          </div>
        )}
        {comment && (
          <div className="mb-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-200 text-sm text-indigo-800">
            <MessageSquare size={14} className="mt-0.5 shrink-0" />
            <span>{comment}</span>
          </div>
        )}
        <ExpandedContent row={row} />
      </td>
    </tr>
  );
}

// ── Main component ────────────────────────────────────────────────
export default function Payroll() {
  const { toast } = useToast();
  const { isMobile } = useViewport();
  const [months, setMonths]           = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [rows, setRows]               = useState([]);
  const [unknownCodes, setUnknownCodes] = useState([]);
  const [prevRows, setPrevRows]       = useState([]);
  const [plans, setPlans]             = useState([]);
  const [loading, setLoading]         = useState(false);
  const [loadingMonths, setLoadingMonths] = useState(true);
  const [query, setQuery]             = useState('');
  const [expandedRows, setExpandedRows]   = useState(new Set());
  const [editingPlan, setEditingPlan] = useState(null);
  const [comments, setComments]       = useState({});
  const [editingComment, setEditingComment] = useState(null);
  const [auditLog, setAuditLog]       = useState([]);
  const [showAudit, setShowAudit]     = useState(false);

  const { month: currentMonth, year: currentYear } = parseSelectedMonth(selectedMonth);
  const monthKey = selectedMonth ? makeMonthKey(selectedMonth, currentYear) : null;
  const payrollReqId = useRef(0);

  useEffect(() => { loadMonths(); }, []);
  useEffect(() => {
    setRows([]);
    setUnknownCodes([]);
    if (selectedMonth) {
      loadPayroll(selectedMonth);
      loadPlans(selectedMonth);
      loadComments(selectedMonth);
      loadAudit(selectedMonth);
      loadPrevMonthRows(selectedMonth);
    }
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

  async function loadPlans(month) {
    try {
      const res = await api.get('payroll/plans', {
        params: { month, year: currentYear },
      });
      setPlans(res.data || []);
    } catch (err) { console.error(err); toast('Ошибка загрузки планов', 'error'); }
  }

  async function loadComments(month) {
    try {
      const res = await api.get('payroll/comments', { params: { month, year: currentYear } });
      setComments(res.data || {});
    } catch { /* silent */ }
  }

  async function loadAudit(month) {
    try {
      const res = await api.get('payroll/audit', { params: { month, year: currentYear, limit: 50 } });
      setAuditLog(res.data || []);
    } catch { /* silent */ }
  }

  async function loadPrevMonthRows(month) {
    try {
      const MONTHS_KEY_RU = ['ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ','ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ'];
      const idx = MONTHS_KEY_RU.indexOf(month.toUpperCase());
      if (idx < 0) { setPrevRows([]); return; }
      const prevIdx = idx === 0 ? 11 : idx - 1;
      const prevMonth = MONTHS_KEY_RU[prevIdx];
      const prevYear = idx === 0 ? currentYear - 1 : currentYear;
      const res = await api.get('payroll/calculate', { params: { month: prevMonth, year: prevYear } });
      setPrevRows(res.data?.rows || res.data || []);
    } catch { setPrevRows([]); }
  }

  async function saveComment(employeeCode, text) {
    try {
      await api.put(`payroll/comments/${employeeCode}`, { comment: text }, {
        params: { month: selectedMonth, year: currentYear },
      });
      setComments((prev) => ({ ...prev, [employeeCode]: text }));
      toast('Комментарий сохранён', 'success');
    } catch { toast('Ошибка сохранения комментария', 'error'); }
    setEditingComment(null);
  }

  async function postAuditEntry(action, row, details = {}) {
    try {
      await api.post('payroll/audit', {
        action,
        employee_code: row.employee_code,
        employee_name: row.employee_name,
        month_key: monthKey,
        details,
      });
      loadAudit(selectedMonth);
    } catch { /* silent */ }
  }

  async function loadPayroll(month) {
    const reqId = ++payrollReqId.current;
    setLoading(true);
    try {
      const res = await api.get('payroll/calculate', { params: { month } });
      if (reqId !== payrollReqId.current) return;
      setRows(res.data?.rows || res.data || []);
      setUnknownCodes(res.data?.unknown_codes || []);
    } catch {
      if (reqId === payrollReqId.current) toast('Ошибка загрузки данных', 'error');
    } finally {
      if (reqId === payrollReqId.current) setLoading(false);
    }
  }

  async function savePlan(planData) {
    try {
      await api.put('payroll/plans', planData);
      toast('План сохранён', 'success');
      const prevPlan = plans.find((p) => p.employee_code === planData.employee_code);
      postAuditEntry('Изменение плана', { employee_code: planData.employee_code, employee_name: planData.employee_name }, {
        before: prevPlan ? { repair_plan: prevPlan.repair_plan, cosmetics_plan: prevPlan.cosmetics_plan, shoes_plan: prevPlan.shoes_plan, force_max: prevPlan.force_max, force_min: prevPlan.force_min, ignore_kpi: prevPlan.ignore_kpi } : null,
        after: { repair_plan: planData.repair_plan, cosmetics_plan: planData.cosmetics_plan, shoes_plan: planData.shoes_plan, force_max: planData.force_max, force_min: planData.force_min, ignore_kpi: planData.ignore_kpi },
      });
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
      const row = rows.find((r) => r.employee_code === employeeCode);
      if (row) {
        postAuditEntry(!currentPaid ? 'Выплата отмечена' : 'Выплата отменена', row, { paid: !currentPaid });
      }
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

  function exportExcel() {
    if (!selectedMonth) return;
    window.open(`/api/payroll/export/excel?month=${selectedMonth}&year=${currentYear}`, '_blank');
  }

  const prevRowsMap = useMemo(() => {
    const m = {};
    for (const r of prevRows) m[r.employee_code] = r;
    return m;
  }, [prevRows]);

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
      <TopProgressBar active={loading || loadingMonths} />
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-2xl font-semibold tracking-tight flex-1">Расчёт зарплаты</h2>
        <button onClick={exportPdf} disabled={!selectedMonth || loading}
          className="btn btn--primary flex items-center gap-2 disabled:opacity-50">
          <Download size={16} />PDF
        </button>
        <button onClick={exportExcel} disabled={!selectedMonth || loading}
          className="btn flex items-center gap-2 disabled:opacity-50 bg-green-600 text-white hover:bg-green-700">
          <FileSpreadsheet size={16} />Excel
        </button>
        <button onClick={() => setShowAudit((v) => !v)} disabled={!selectedMonth}
          className={`btn flex items-center gap-2 disabled:opacity-50 ${showAudit ? 'bg-indigo-100 text-indigo-700 border border-indigo-300' : ''}`}>
          <History size={16} />Журнал
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
          <input className="input w-full" style={{ paddingLeft: '2.25rem' }} placeholder="Поиск по ФИО…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
          {query && (
            <button onClick={() => setQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]">
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Unknown location codes warning */}
      {unknownCodes.length > 0 && (
        <div className="flex items-start gap-3 px-4 py-3 rounded-xl border border-amber-300 bg-amber-50 text-amber-800 text-sm">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
          <div>
            <span className="font-semibold">Неизвестные коды точек в расписании: </span>
            <span className="font-mono">{unknownCodes.join(', ')}</span>
            <span className="ml-2 text-xs opacity-75">— смены по этим точкам не учитываются в авто-плане. Добавьте коды в «Планы по точкам».</span>
          </div>
        </div>
      )}

      {/* Summary */}
      {!loading && rows.length > 0 && <SummaryBar rows={filtered} />}

      {!loading && rows.length > 0 && (
        <CompositionAndLeaders rows={filtered} query={query} onSelectEmployee={setQuery} />
      )}

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
      ) : isMobile ? (
        <div className="space-y-3">
          {filtered.map((row) => (
            <div
              key={row.employee_code}
              className={`border rounded-xl overflow-hidden shadow-sm bg-[color:var(--color-table-bg)] ${row.settlement_paid ? 'border-green-300' : 'border-[color:var(--color-border)]'}`}
            >
              {/* Card header — identity only */}
              <div
                className="px-4 py-3 flex items-center justify-between gap-2 cursor-pointer bg-[color:var(--color-table-header)]"
                onClick={() => toggleRow(row.employee_code)}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="grid place-items-center w-9 h-9 shrink-0 rounded-full bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)] text-sm font-semibold">
                    {(row.employee_name || '?').trim().charAt(0).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      {row.settlement_paid && <BadgeCheck size={15} className="text-green-500 shrink-0" />}
                      {getAnomalyFlags(row).length > 0 && (
                        <span title={getAnomalyFlags(row).join('\n')}>
                          <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                        </span>
                      )}
                      <span className="font-medium text-sm truncate">{row.employee_name}</span>
                    </div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)] truncate">{row.employee_code}</div>
                  </div>
                </div>
                <div className="shrink-0 text-[color:var(--color-muted-foreground)]">
                  {expandedRows.has(row.employee_code) ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                </div>
              </div>

              {/* Headline figures — gross vs. net, side by side */}
              <div className="grid grid-cols-2 divide-x divide-[color:var(--color-border)] border-b border-[color:var(--color-border)]">
                <div className="px-4 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-0.5">Общая ЗП</div>
                  <div className="flex items-center gap-1.5 text-lg font-semibold">
                    <TrendBadge current={row.total_gross} prev={prevRowsMap[row.employee_code]?.total_gross} />
                    {fmtMoney(grossOf(row))}
                  </div>
                </div>
                <div className="px-4 py-3">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-0.5">К выплате</div>
                  <div className="text-lg font-semibold text-[color:var(--color-primary)]">{fmtMoney(row.total_net)}</div>
                </div>
              </div>

              {/* Breakdown — one figure per row, easy to read top-to-bottom */}
              <div className="px-4 text-sm divide-y divide-[color:var(--color-border)] border-b border-[color:var(--color-border)]">
                <div className="flex items-center justify-between py-2">
                  <span className="text-[color:var(--color-muted-foreground)]">Оклад</span>
                  <span>{fmtMoney(row.base_salary)}</span>
                </div>
                <div className="flex items-center justify-between py-2">
                  <span className="text-[color:var(--color-muted-foreground)]">Комиссия</span>
                  <span className="flex items-center gap-1.5">
                    {!row.ignore_kpi && <TrendBadge current={row.total_commission} prev={prevRowsMap[row.employee_code]?.total_commission} />}
                    {row.ignore_kpi ? '—' : fmtMoney(row.total_commission)}
                  </span>
                </div>
                {(row.bonuses + row.excel_bonus) > 0 && (
                  <div className="flex items-center justify-between py-2">
                    <span className="text-[color:var(--color-muted-foreground)]">Премии</span>
                    <span className="text-green-600">+{fmtMoney(row.bonuses + row.excel_bonus)}</span>
                  </div>
                )}
                {row.advances > 0 && (
                  <div className="flex items-center justify-between py-2">
                    <span className="text-[color:var(--color-muted-foreground)]">Авансы</span>
                    <span className="text-[color:var(--color-danger)]">-{fmtMoney(row.advances)}</span>
                  </div>
                )}
                {row.penalties > 0 && (
                  <div className="flex items-center justify-between py-2">
                    <span className="text-[color:var(--color-muted-foreground)]">Штрафы</span>
                    <span className="text-[color:var(--color-danger)]">-{fmtMoney(row.penalties)}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="px-4 py-2 flex justify-end gap-3">
                <button
                  onClick={() => toggleSettlement(row.employee_code, row.settlement_paid)}
                  title={row.settlement_paid ? 'Расчёт выдан — нажмите для отмены' : 'Отметить как выданный'}
                  className={`p-1.5 rounded transition-colors ${row.settlement_paid ? 'text-green-500' : 'text-[color:var(--color-muted-foreground)]'}`}
                >
                  {row.settlement_paid ? <CheckSquare size={20} /> : <Square size={20} />}
                </button>
                <button
                  onClick={() => setEditingPlan(row)}
                  className="p-1.5 rounded text-[color:var(--color-muted-foreground)]"
                  title="Настроить план"
                >
                  <Settings size={18} />
                </button>
                <button
                  onClick={() => setEditingComment(row)}
                  className={`p-1.5 rounded transition-colors ${comments[row.employee_code] ? 'text-indigo-500' : 'text-[color:var(--color-muted-foreground)]'}`}
                  title="Комментарий"
                >
                  <MessageSquare size={18} />
                </button>
              </div>

              {/* Expanded detail */}
              {expandedRows.has(row.employee_code) && (
                <div className="px-4 py-4 border-t border-[color:var(--color-border)] bg-[color:var(--color-bg-secondary)]">
                  {getAnomalyFlags(row).length > 0 && (
                    <div className="mb-3 flex flex-wrap gap-2">
                      {getAnomalyFlags(row).map((f) => (
                        <span key={f} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800">
                          <AlertTriangle size={11} />{f}
                        </span>
                      ))}
                    </div>
                  )}
                  {comments[row.employee_code] && (
                    <div className="mb-3 flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-200 text-sm text-indigo-800">
                      <MessageSquare size={13} className="mt-0.5 shrink-0" />
                      <span>{comments[row.employee_code]}</span>
                    </div>
                  )}
                  <ExpandedContent row={row} />
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-[color:var(--color-border)] shadow-sm">
          <table className="min-w-max w-full text-sm divide-y divide-[color:var(--color-border)] bg-[color:var(--color-table-bg)] text-[color:var(--color-table-text)]">
            <thead>
              <tr className="bg-[color:var(--color-table-header)]">
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide w-10"></th>
                <th className="px-3 py-3 text-left text-xs font-semibold uppercase tracking-wide sticky left-0 bg-[color:var(--color-table-header)]">ФИО</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Оклад</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Комиссия</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide">Общая зп</th>
                <th className="px-3 py-3 text-right text-xs font-semibold uppercase tracking-wide text-[color:var(--color-danger)]">Авансы</th>
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
                        {getAnomalyFlags(row).length > 0 && (
                          <span title={getAnomalyFlags(row).join('\n')}>
                            <AlertTriangle size={14} className="text-amber-500 shrink-0" />
                          </span>
                        )}
                        {comments[row.employee_code] && (
                          <span title={comments[row.employee_code]}>
                            <MessageSquare size={13} className="text-indigo-400 shrink-0" />
                          </span>
                        )}
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
                        : (
                          <div className="flex items-center justify-end gap-1.5">
                            <TrendBadge current={row.total_commission} prev={prevRowsMap[row.employee_code]?.total_commission} />
                            {fmtMoney(row.total_commission)}
                          </div>
                        )}
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5">
                        <TrendBadge current={row.total_gross} prev={prevRowsMap[row.employee_code]?.total_gross} />
                        {fmtMoney(grossOf(row))}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-right whitespace-nowrap text-[color:var(--color-danger)]">
                      {row.advances > 0 ? (
                        <span title={`За этот месяц: ${row.advances_this_month?.toLocaleString('ru-RU') || 0} ₽`}>
                          -{fmtMoney(row.advances)}
                        </span>
                      ) : '—'}
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
                      <div className="flex items-center justify-center gap-1">
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditingPlan(row); }}
                          className="p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-text-primary)]"
                          title="Настроить план"
                        >
                          <Settings size={16} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditingComment(row); }}
                          className={`p-1.5 rounded hover:bg-[color:var(--color-bg-secondary)] transition-colors ${comments[row.employee_code] ? 'text-indigo-500' : 'text-[color:var(--color-muted-foreground)]'}`}
                          title={comments[row.employee_code] ? `Комментарий: ${comments[row.employee_code]}` : 'Добавить комментарий'}
                        >
                          <MessageSquare size={15} />
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedRows.has(row.employee_code) && <ExpandedRow key={`exp-${row.employee_code}`} row={row} comment={comments[row.employee_code]} />}
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
                <td className="px-3 py-2.5 text-right">
                  {fmtMoney(filtered.reduce((s, r) => s + grossOf(r), 0))}
                </td>
                <td className="px-3 py-2.5 text-right text-[color:var(--color-danger)]">
                  -{fmtMoney(filtered.reduce((s, r) => s + r.advances, 0))}
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

      {/* Audit log panel */}
      {showAudit && (
        <div className="app-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold flex items-center gap-2"><History size={16} />Журнал изменений{selectedMonth && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">— {monthKey}</span>}</h3>
            <button onClick={() => loadAudit(selectedMonth)} className="text-xs text-[color:var(--color-primary)] hover:underline">Обновить</button>
          </div>
          {auditLog.length === 0 ? (
            <p className="text-sm text-[color:var(--color-muted-foreground)]">Изменений за этот месяц нет.</p>
          ) : (
            <div className="max-h-64 overflow-y-auto">
              <ResponsiveTable
                data={auditLog}
                keyFn={(e) => e.id}
                columns={[
                  {
                    label: 'Время',
                    primary: true,
                    render: (e) =>
                      new Date(e.timestamp).toLocaleString('ru-RU', {
                        day: '2-digit',
                        month: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                      }),
                  },
                  { label: 'Кто', render: (e) => <span className="font-mono">{e.actor}</span> },
                  { label: 'Действие', render: (e) => <span className="font-medium">{e.action}</span> },
                  { label: 'Сотрудник', key: 'employee_name' },
                ]}
              />
            </div>
          )}
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

      {/* Comment Modal */}
      {editingComment && (
        <CommentModal
          employee={editingComment}
          currentComment={comments[editingComment.employee_code] || ''}
          onSave={(text) => saveComment(editingComment.employee_code, text)}
          onClose={() => setEditingComment(null)}
        />
      )}
    </div>
  );
}
