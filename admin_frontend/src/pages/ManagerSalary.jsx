import { useEffect, useMemo, useState, useCallback } from 'react';
import { Calculator, Wallet, RefreshCw, Trash2, ChevronDown, ChevronUp, AlertTriangle, Banknote, CheckCircle2 } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MANAGER_POSITION = 'менеджер по работе с клиентами';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(1)}%`);
// Human-readable duration from seconds: «45 сек» / «12 мин» / «2 ч 5 мин».
const fmtDuration = (s) => {
  if (s === null || s === undefined) return '—';
  s = Math.round(Number(s));
  if (s < 60) return `${s} сек`;
  if (s < 3600) return `${Math.round(s / 60)} мин`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return m ? `${h} ч ${m} мин` : `${h} ч`;
};
const lastDay = (ym) => { const [y, m] = ym.split('-').map(Number); return new Date(y, m, 0).getDate(); };

// last 12 months as {value:'YYYY-MM', label:'Июнь 2026'}
function recentMonths(n = 12) {
  const out = [];
  const d = new Date();
  for (let i = 0; i < n; i++) {
    const y = d.getFullYear(), m = d.getMonth();
    out.push({ value: `${y}-${String(m + 1).padStart(2, '0')}`, label: `${MONTHS_RU[m]} ${y}` });
    d.setMonth(m - 1);
  }
  return out;
}

function prevMonth(period) {
  const [y, m] = period.split('-').map(Number);
  const d = new Date(y, m - 2, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

// Relative change vs the previous period (up = green, down = red).
function TrendBadge({ cur, prev }) {
  if (cur == null || prev == null || !prev) return null;
  const pct = ((cur - prev) / prev) * 100;
  if (Math.abs(pct) < 0.05) {
    return <span className="text-[11px] text-[color:var(--color-muted-foreground)]">≈ пред. мес.</span>;
  }
  const up = pct > 0;
  return (
    <span
      className={`text-[11px] font-medium ${up ? 'text-[color:var(--color-success)]' : 'text-[color:var(--color-danger)]'}`}
      title={`Пред. период: ${Math.round(prev).toLocaleString('ru-RU')}`}
    >
      {up ? '▲' : '▼'} {Math.abs(pct).toFixed(1)}%
    </span>
  );
}

// Большая денежная плитка — крупно сумма + подпись/тренд.
function MoneyTile({ label, value, cur, prev, accent, hint, highlight }) {
  return (
    <div className={`app-card px-4 py-3 flex flex-col gap-1 ${highlight ? 'ring-1 ring-[color:var(--color-primary)]' : ''}`}>
      <div className="text-[11px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{label}</div>
      <div className={`text-2xl font-bold tabular-nums leading-tight whitespace-nowrap ${accent || 'text-[color:var(--color-text-primary)]'}`}>{value}</div>
      {hint ? <div className="text-[11px] text-[color:var(--color-muted-foreground)]">{hint}</div> : <TrendBadge cur={cur} prev={prev} />}
    </div>
  );
}

// Строка сравнения План / Факт / % с порогом 79%.
function PlanFactRow({ title, note, plan, fact, ratio, fmt = fmtMoney }) {
  const pct = ratio == null ? null : ratio * 100;
  const tone = pct == null ? 'text-[color:var(--color-muted-foreground)]'
    : pct >= 100 ? 'text-[color:var(--color-success)]'
    : pct >= 79 ? 'text-[color:var(--color-text-primary)]'
    : 'text-[color:var(--color-danger)]';
  return (
    <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_2.5rem] items-baseline gap-x-2 sm:gap-x-3 py-2 border-t border-[color:var(--color-border)] first:border-t-0">
      <div className="text-sm font-medium min-w-0">
        {title}{note ? <span className="block text-[11px] text-[color:var(--color-muted-foreground)]">{note}</span> : null}
      </div>
      <div className="text-right tabular-nums text-xs sm:text-sm whitespace-nowrap">{fmt(plan)}</div>
      <div className="text-right tabular-nums text-xs sm:text-sm font-semibold whitespace-nowrap">{fmt(fact)}</div>
      <div className={`text-right tabular-nums text-xs sm:text-sm font-semibold ${tone}`}>{pct == null ? '—' : `${pct.toFixed(0)}%`}</div>
    </div>
  );
}

// One deal row (shared by the flat and grouped lists).
function DealRow({ d, domain }) {
  return (
    <li className="px-3 py-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium truncate">
          {domain
            ? <a href={`https://${domain}/leads/detail/${d.id}`} target="_blank" rel="noreferrer" className="text-[color:var(--color-primary)] hover:underline">{d.name || `#${d.id}`}</a>
            : (d.name || `#${d.id}`)}
          <span className="text-[color:var(--color-muted-foreground)]"> · #{d.id}</span>
        </span>
        <span className="tabular-nums shrink-0">{Number(d.price || 0).toLocaleString('ru-RU')} ₽</span>
      </div>
      <div className="text-[color:var(--color-muted-foreground)] mt-0.5">{d.reason}</div>
    </li>
  );
}

// Collapsible list of the concrete deals counted in one calculation group.
function DealList({ title, deals, domain, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const list = deals || [];
  const sum = list.reduce((s, d) => s + (Number(d.price) || 0), 0);
  return (
    <div className="border border-[color:var(--color-border)] rounded-lg overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm">
        <span className="font-medium text-left">{title} <span className="text-xs text-[color:var(--color-muted-foreground)]">· {list.length} шт · Σ {sum.toLocaleString('ru-RU')} ₽</span></span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {open && (
        list.length === 0 ? (
          <div className="px-3 py-3 text-xs text-[color:var(--color-muted-foreground)] border-t border-[color:var(--color-border)]">Пусто.</div>
        ) : (
          <ul className="border-t border-[color:var(--color-border)] divide-y divide-[color:var(--color-border)] max-h-72 overflow-y-auto">
            {list.map((d) => <DealRow key={d.id} d={d} domain={domain} />)}
          </ul>
        )
      )}
    </div>
  );
}

// Like DealList, but deals are split into subgroups (subheader + rows).
function GroupedDealList({ title, deals, groupLabel, domain, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const list = deals || [];
  const sum = list.reduce((s, d) => s + (Number(d.price) || 0), 0);
  const groups = [];
  const idx = new Map();
  for (const d of list) {
    const g = groupLabel(d);
    if (!idx.has(g)) { idx.set(g, groups.length); groups.push({ label: g, items: [] }); }
    groups[idx.get(g)].items.push(d);
  }
  return (
    <div className="border border-[color:var(--color-border)] rounded-lg overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm">
        <span className="font-medium text-left">{title} <span className="text-xs text-[color:var(--color-muted-foreground)]">· {list.length} шт · Σ {sum.toLocaleString('ru-RU')} ₽</span></span>
        {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
      </button>
      {open && (
        list.length === 0 ? (
          <div className="px-3 py-3 text-xs text-[color:var(--color-muted-foreground)] border-t border-[color:var(--color-border)]">Пусто.</div>
        ) : (
          <div className="border-t border-[color:var(--color-border)] max-h-80 overflow-y-auto divide-y divide-[color:var(--color-border)]">
            {groups.map((g) => {
              const gsum = g.items.reduce((s, d) => s + (Number(d.price) || 0), 0);
              return (
                <div key={g.label}>
                  <div className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] bg-[color:var(--color-bg-secondary)] flex items-center justify-between gap-2">
                    <span className="truncate">{g.label}</span>
                    <span className="shrink-0 tabular-nums">{g.items.length} · Σ {gsum.toLocaleString('ru-RU')} ₽</span>
                  </div>
                  <ul className="divide-y divide-[color:var(--color-border)]">
                    {g.items.map((d) => <DealRow key={d.id} d={d} domain={domain} />)}
                  </ul>
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}

function KpiRow({ title, weight, max, ratio, amount, zeroed, extra }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-t border-[color:var(--color-border)] first:border-t-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{title} <span className="text-xs text-[color:var(--color-muted-foreground)]">· вес {(weight * 100).toFixed(0)}%</span></div>
        <div className="text-xs text-[color:var(--color-muted-foreground)]">
          цель {fmtMoney(max)} · коэф {ratio == null ? '—' : `${(ratio * 100).toFixed(1)}%`}{extra ? ` · ${extra}` : ''}
        </div>
      </div>
      <div className={`text-right whitespace-nowrap font-semibold tabular-nums ${zeroed ? 'text-[color:var(--color-muted-foreground)]' : 'text-[color:var(--color-text-primary)]'}`}>
        {fmtMoney(amount)}
      </div>
    </div>
  );
}

export default function ManagerSalary() {
  const { toast } = useToast();
  const months = useMemo(() => recentMonths(12), []);
  const [employees, setEmployees] = useState([]);
  const [managerId, setManagerId] = useState('');
  const [period, setPeriod] = useState(months[0].value);

  const [plan, setPlan] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [advances, setAdvances] = useState(null);   // {total, since}
  const [incentives, setIncentives] = useState({ bonuses: 0, penalties: 0 });
  const [result, setResult] = useState(null);
  const [prev, setPrev] = useState(null);            // {result, metrics} of previous month
  const [loading, setLoading] = useState(false);
  const [metricsError, setMetricsError] = useState(null);
  const [amoStatus, setAmoStatus] = useState(null);
  const [accruals, setAccruals] = useState([]);
  const [accruing, setAccruing] = useState(false);
  const [payingId, setPayingId] = useState(null);
  const [accrualsTick, setAccrualsTick] = useState(0);
  const [showHistory, setShowHistory] = useState(true);

  const managers = useMemo(
    () => employees.filter((e) => (e.position || '').trim().toLowerCase() === MANAGER_POSITION),
    [employees]);
  const manager = useMemo(() => managers.find((e) => String(e.id) === String(managerId)), [managers, managerId]);
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;

  useEffect(() => {
    api.get('employees/', { params: { archived: false } })
      .then((r) => setEmployees((r.data || []).filter((e) => e.status !== 'inactive')))
      .catch(() => {});
    api.get('amo/status').then((r) => setAmoStatus(r.data)).catch(() => setAmoStatus(null));
  }, []);

  const loadAll = useCallback(async () => {
    if (!managerId) { setResult(null); setPlan(null); setMetrics(null); setAdvances(null); setPrev(null); return; }
    setLoading(true);
    setMetricsError(null);
    try {
      const planP = api.get('manager-salary/plan', { params: { employee_code: managerId, period } }).then((r) => r.data);
      const advP = api.get('manager-salary/advances', { params: { employee_id: managerId } }).then((r) => r.data).catch(() => ({ total: 0 }));
      const incP = api.get('incentives/', { params: { employee_id: managerId, date_from: dateFrom, date_to: dateTo } }).then((r) => r.data).catch(() => []);
      const metP = manager?.amo_user_id
        ? api.get('manager-salary/metrics', { params: { date_from: dateFrom, date_to: dateTo, amo_user_id: manager.amo_user_id, detail: 1 } }).then((r) => r.data)
        : Promise.reject(new Error(manager ? 'у менеджера не привязан amoCRM' : 'нет менеджера'));

      const [pl, adv, inc] = await Promise.all([planP, advP, incP]);
      const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
      const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
      setPlan(pl); setAdvances(adv); setIncentives({ bonuses, penalties });
      let met = null;
      try { met = await metP; setMetrics(met); }
      catch (e) { setMetrics(null); setMetricsError(e?.response?.data?.detail || e.message || 'amoCRM недоступен'); }

      const payload = {
        oklad: pl.oklad, kpi_max: pl.kpi_max,
        revenue_plan: pl.revenue_plan, revenue_actual: met?.revenue_actual || 0,
        repair_plan_conv: pl.repair_plan_conv, repair_target_deals: met?.repair_target_deals || 0, repair_total_deals: met?.repair_total_deals || 0,
        sew_plan_conv: pl.sew_plan_conv, sew_target_deals: met?.sew_target_deals || 0, sew_total_deals: met?.sew_total_deals || 0, sew_new_leads: met?.sew_new_leads || 0,
        advances: adv?.total || 0, bonuses, penalties,
      };
      const res = await api.post('manager-salary/calc', payload);
      setResult(res.data);

      // Previous month — for the widget comparison (advances excluded: they
      // are a running «since last salary» total, not period-comparable).
      const pp = prevMonth(period);
      (async () => {
        try {
          const ppPlan = await api.get('manager-salary/plan', { params: { employee_code: managerId, period: pp } }).then((r) => r.data);
          let ppMet = null;
          if (manager?.amo_user_id) {
            const pF = `${pp}-01`, pT = `${pp}-${String(lastDay(pp)).padStart(2, '0')}`;
            ppMet = await api.get('manager-salary/metrics', { params: { date_from: pF, date_to: pT, amo_user_id: manager.amo_user_id } }).then((r) => r.data);
          }
          const ppRes = await api.post('manager-salary/calc', {
            oklad: ppPlan.oklad, kpi_max: ppPlan.kpi_max,
            revenue_plan: ppPlan.revenue_plan, revenue_actual: ppMet?.revenue_actual || 0,
            repair_plan_conv: ppPlan.repair_plan_conv, repair_target_deals: ppMet?.repair_target_deals || 0, repair_total_deals: ppMet?.repair_total_deals || 0,
            sew_plan_conv: ppPlan.sew_plan_conv, sew_target_deals: ppMet?.sew_target_deals || 0, sew_total_deals: ppMet?.sew_total_deals || 0, sew_new_leads: ppMet?.sew_new_leads || 0,
            advances: 0,
          }).then((r) => r.data);
          setPrev({ result: ppRes, metrics: ppMet });
        } catch { setPrev(null); }
      })();
    } catch (e) {
      console.error(e);
    } finally { setLoading(false); }
  }, [managerId, period, manager, dateFrom, dateTo]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { if (managerId) api.get('manager-salary/accruals', { params: { employee_code: managerId, limit: 50 } }).then((r) => setAccruals(r.data || [])).catch(() => {}); }, [managerId, accrualsTick]);

  async function accrue() {
    if (!managerId || !plan) return;
    setAccruing(true);
    try {
      await api.post('manager-salary/accrue', {
        oklad: plan.oklad, kpi_max: plan.kpi_max,
        revenue_plan: plan.revenue_plan, revenue_actual: metrics?.revenue_actual || 0,
        repair_plan_conv: plan.repair_plan_conv, repair_target_deals: metrics?.repair_target_deals || 0, repair_total_deals: metrics?.repair_total_deals || 0,
        sew_plan_conv: plan.sew_plan_conv, sew_target_deals: metrics?.sew_target_deals || 0, sew_total_deals: metrics?.sew_total_deals || 0, sew_new_leads: metrics?.sew_new_leads || 0,
        advances: advances?.total || 0, bonuses: incentives.bonuses, penalties: incentives.penalties,
        employee_code: String(managerId), employee_name: manager?.full_name || manager?.name || '',
        user_id: String(managerId), period, date_from: dateFrom, date_to: dateTo,
      });
      toast('Начисление сохранено', 'success');
      setAccrualsTick((t) => t + 1);
    } catch (e) { console.error(e); toast('Ошибка начисления', 'error'); }
    finally { setAccruing(false); }
  }

  async function deleteAccrual(id) {
    if (!window.confirm('Удалить начисление?')) return;
    try { await api.delete(`manager-salary/accruals/${id}`); setAccrualsTick((t) => t + 1); }
    catch { toast('Ошибка удаления', 'error'); }
  }

  async function createPayout(a) {
    const sum = a.result?.to_pay || 0;
    if (!window.confirm(`Создать выплату «Зарплата» на ${fmtMoney(sum)} (наличными)?`)) return;
    setPayingId(a.id);
    try {
      await api.post(`manager-salary/accruals/${a.id}/payout`);
      toast('Выплата создана', 'success');
      setAccrualsTick((t) => t + 1);
    } catch (e) {
      toast(e?.response?.data?.detail || 'Ошибка создания выплаты', 'error');
    } finally { setPayingId(null); }
  }

  const planEmpty = plan && !plan.oklad && !plan.kpi_max && !plan.revenue_plan;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
          <Calculator size={24} /> Расчёт ЗП менеджеров
        </h2>
        {amoStatus && (amoStatus.authorized
          ? <span className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-[color:var(--color-success-muted)] text-[color:var(--color-success)]"><span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-success)]" /> amoCRM подключён</span>
          : <a href="/admin/settings/integrations" className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-full bg-[color:var(--color-danger-muted)] text-[color:var(--color-danger)] hover:underline"><span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-danger)]" /> amoCRM не подключён — настроить</a>)}
      </div>

      {/* Selectors */}
      <div className="app-card p-4 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-sm font-medium mb-1">Менеджер</span>
          <select className="input min-w-[240px]" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">— выберите —</option>
            {managers.map((e) => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="block text-sm font-medium mb-1">Период</span>
          <select className="input min-w-[160px]" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        <button className="btn btn--secondary flex items-center gap-1.5" onClick={loadAll} disabled={!managerId || loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
        {managers.length === 0 && (
          <span className="text-sm text-[color:var(--color-muted-foreground)]">Нет сотрудников с должностью «менеджер по работе с клиентами»</span>
        )}
      </div>

      {!managerId ? (
        <div className="app-card p-10 text-center text-[color:var(--color-muted-foreground)]">Выберите менеджера и период.</div>
      ) : (
        <>
          {/* Warnings */}
          {planEmpty && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              План на этот месяц не задан. Заполните оклад/KPI/план на странице «Планы продаж».
            </div>
          )}
          {metricsError && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              Метрики из amoCRM недоступны ({metricsError}). KPI рассчитан по нулевым фактам — показан только оклад.
            </div>
          )}

          {result && (<>
            {/* Крупные денежные плитки (3 в ряд — чтобы суммы с копейками не обрезались) */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <MoneyTile label="Оклад" value={fmtMoney(result.oklad)} hint="фикс. часть" />
              <MoneyTile label="Комиссия (KPI)" value={fmtMoney(result.kpi)} cur={result.kpi} prev={prev?.result?.kpi} accent="text-[color:var(--color-success)]" />
              <MoneyTile label="Премии" value={fmtMoney(result.bonuses)} hint="+ к начислению" accent={result.bonuses ? 'text-[color:var(--color-success)]' : undefined} />
              <MoneyTile label="Авансы" value={fmtMoney(result.advances)} hint="с посл. зарплаты" accent={result.advances ? 'text-[color:var(--color-danger)]' : undefined} />
              <MoneyTile label="Штрафы" value={fmtMoney(result.penalties)} hint="− из выплаты" accent={result.penalties ? 'text-[color:var(--color-danger)]' : undefined} />
              <MoneyTile label="К выплате" value={fmtMoney(result.to_pay)} accent="text-[color:var(--color-primary)]" highlight hint={`начислено ${fmtMoney(result.gross)}`} />
            </div>

            {/* План / Факт / % — выручка и конверсии + лиды */}
            <div className="app-card p-4 space-y-2">
              <div className="grid grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_minmax(0,1fr)_2.5rem] gap-x-2 sm:gap-x-3 text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                <div>Показатель</div>
                <div className="text-right">План</div>
                <div className="text-right">Факт</div>
                <div className="text-right">%</div>
              </div>
              <PlanFactRow title="Выручка" plan={plan?.revenue_plan} fact={metrics?.revenue_actual} ratio={result.revenue.ratio} />
              <PlanFactRow title="Конверсия ремонта" note={`целевых ${result.repair.target} / всего ${result.repair.total}`} plan={plan?.repair_plan_conv} fact={result.repair.conv} ratio={result.repair.ratio} fmt={fmtPct} />
              <PlanFactRow title="Конверсия пошива" note={result.sew.leads_gate_failed ? `лидов ${result.sew.new_leads} < ${result.sew.min_leads} — не зачтена` : `целевых ${result.sew.target} / всего ${result.sew.total}`} plan={plan?.sew_plan_conv} fact={result.sew.conv} ratio={result.sew.ratio} fmt={fmtPct} />
              <div className="flex items-center justify-between pt-2 border-t border-[color:var(--color-border)] text-sm">
                <span className="text-[color:var(--color-muted-foreground)]">Новых лидов за период (пошив)</span>
                <span className="font-semibold tabular-nums">{metrics?.sew_new_leads ?? '—'}</span>
              </div>
              <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Порог KPI — 79%: компонент с факт/план ниже порога не оплачивается.</div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              {/* Breakdown */}
              <div className="app-card p-4 space-y-3">
                <div className="rounded-lg border border-[color:var(--color-border)] p-3">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">KPI · цель {fmtMoney(result.kpi_max)}</div>
                  <KpiRow title="Выручка" weight={result.weights.revenue} max={result.revenue.max} ratio={result.revenue.ratio} amount={result.revenue.amount} zeroed={result.revenue.zeroed} extra={`факт/план ${fmtPct(result.revenue.ratio)}`} />
                  <KpiRow title="Конверсия ремонта" weight={result.weights.repair} max={result.repair.max} ratio={result.repair.ratio} amount={result.repair.amount} zeroed={result.repair.zeroed} extra={`конв ${fmtPct(result.repair.conv)}`} />
                  <KpiRow title="Конверсия пошива" weight={result.weights.sew} max={result.sew.max} ratio={result.sew.ratio} amount={result.sew.amount} zeroed={result.sew.zeroed} extra={result.sew.leads_gate_failed ? `лидов ${result.sew.new_leads} < ${result.sew.min_leads}` : `конв ${fmtPct(result.sew.conv)}`} />
                </div>

                {/* Начисление */}
                <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">Начислить ЗП за {months.find((m) => m.value === period)?.label}</div>
                      <div className="text-[11px] text-[color:var(--color-muted-foreground)]">Фиксирует расчёт в журнале начислений (оклад + KPI + премии − авансы − штрафы). Сумму выплаты заводите в «Выплатах».</div>
                    </div>
                    <button className="btn btn--primary flex items-center gap-1.5 shrink-0" onClick={accrue} disabled={accruing}>
                      <Wallet size={15} /> {accruing ? 'Начисляю…' : 'Начислить'}
                    </button>
                  </div>
                </div>
              </div>

              {/* Source data (read-only) */}
              <div className="app-card p-4 space-y-3 text-sm">
                <div className="font-semibold">Исходные данные · {months.find((m) => m.value === period)?.label}</div>
                <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">План (из «Планы продаж»)</div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">Оклад / KPI</span><span>{fmtMoney(plan?.oklad)} / {fmtMoney(plan?.kpi_max)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">План выручки</span><span>{fmtMoney(plan?.revenue_plan)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">План конв. ремонт / пошив</span><span>{fmtPct(plan?.repair_plan_conv)} / {fmtPct(plan?.sew_plan_conv)}</span></div>
                </div>
                <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">Факт из amoCRM</div>
                  {metrics ? (<>
                    <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">Выручка</span><span>{fmtMoney(metrics.revenue_actual)}</span></div>
                    <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">Ремонт: целевых / всего</span><span>{metrics.repair_target_deals} / {metrics.repair_total_deals}</span></div>
                    <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">Пошив: целевых / всего</span><span>{metrics.sew_target_deals} / {metrics.sew_total_deals}</span></div>
                    <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">Новых лидов (пошив)</span><span>{metrics.sew_new_leads}</span></div>
                    <div className="flex justify-between" title="От создания сделки до первого действия менеджера (смена этапа / исходящий звонок / сообщение в чате). Медиана; в скобках среднее.">
                      <span className="text-[color:var(--color-muted-foreground)]">Время первого ответа</span>
                      <span>{fmtDuration(metrics.median_response_seconds)}{metrics.response_sample ? <span className="text-[color:var(--color-muted-foreground)]"> · ср. {fmtDuration(metrics.avg_response_seconds)} · по {metrics.response_sample}</span> : null}</span>
                    </div>
                  </>) : (<div className="text-[color:var(--color-muted-foreground)]">недоступно</div>)}
                </div>
                <div className="rounded-lg border border-[color:var(--color-border)] p-3 space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">Авансы</div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-muted-foreground)]">С последней зарплаты</span><span className="text-[color:var(--color-danger)]">{fmtMoney(advances?.total)}</span></div>
                </div>
              </div>
            </div>

            {/* Контроль: подозрительные сделки — перемещения между воронками */}
            {metrics?.items && (() => {
              const susp = metrics.items.suspicious || [];
              const incoming = susp.filter((d) => d.direction === 'in' || d.direction === 'between');
              const outgoing = susp.filter((d) => d.direction === 'out' || d.direction === 'between');
              return (
                <div className="app-card p-4 space-y-2">
                  <div className="flex items-center gap-2 font-semibold">
                    <AlertTriangle size={16} className="text-amber-500 shrink-0" />
                    Подозрительные сделки <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· перемещения между воронками ({susp.length})</span>
                  </div>
                  {susp.length === 0 ? (
                    <div className="text-sm text-[color:var(--color-muted-foreground)]">За период перемещений между воронками не обнаружено.</div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      <GroupedDealList title="Пришли из другой воронки" deals={incoming} domain={amoStatus?.domain}
                        groupLabel={(d) => `из «${d.from_name || '—'}»`} />
                      <GroupedDealList title="Перенесены в другую воронку" deals={outgoing} domain={amoStatus?.domain}
                        groupLabel={(d) => `в «${d.to_name || '—'}»`} />
                    </div>
                  )}
                  <div className="text-[11px] text-[color:var(--color-muted-foreground)]">
                    Сделки, у которых в течение периода менялась воронка (например, пришли из «Текущая работа» в «Мастерскую» или были перенесены из «Мастерской» в другую воронку). Могут искусственно влиять на выручку и конверсию — стоит проверить обоснованность.
                  </div>
                </div>
              );
            })()}

            {/* Drill-down: which deals landed in each calculation group, and why */}
            {metrics?.items && (
              <div className="app-card p-4 space-y-2">
                <div className="font-semibold">Сделки в расчёте <span className="text-xs text-[color:var(--color-muted-foreground)]">(проверка)</span></div>
                <DealList title="Выручка — сделки на целевых этапах в периоде" deals={metrics.items.revenue} domain={amoStatus?.domain} />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <DealList title="Конверсия ремонта · числитель" deals={metrics.items.repair_num} domain={amoStatus?.domain} />
                  <DealList title="Конверсия ремонта · знаменатель" deals={metrics.items.repair_denom} domain={amoStatus?.domain} />
                  <DealList title="Конверсия пошива · числитель" deals={metrics.items.sew_num} domain={amoStatus?.domain} />
                  <DealList title="Конверсия пошива · знаменатель" deals={metrics.items.sew_denom} domain={amoStatus?.domain} />
                </div>
                {metrics.items.excluded?.length > 0 && (
                  <DealList title="Исключены (достигли этапа, но не зачтены)" deals={metrics.items.excluded} domain={amoStatus?.domain} />
                )}
              </div>
            )}
          </>)}
        </>
      )}

      {/* History */}
      <div className="app-card overflow-hidden">
        <button type="button" onClick={() => setShowHistory((v) => !v)} className="w-full flex items-center justify-between gap-3 px-4 py-3">
          <span className="font-medium">Журнал начислений {manager ? `· ${manager.full_name || manager.name}` : ''} <span className="text-xs text-[color:var(--color-muted-foreground)]">({accruals.length})</span></span>
          {showHistory ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {showHistory && (
          <div className="border-t border-[color:var(--color-border)]">
            {!managerId ? (
              <div className="px-4 py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">Выберите менеджера.</div>
            ) : accruals.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">Начислений пока нет.</div>
            ) : (
              <ul className="divide-y divide-[color:var(--color-border)]">
                {accruals.map((a) => (
                  <li key={a.id} className="px-4 py-3 text-sm flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
                    <div className="min-w-0">
                      <div className="font-medium">{a.period} <span className="text-xs text-[color:var(--color-muted-foreground)]">· {a.created_at?.slice(0, 16).replace('T', ' ')}</span></div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                        <span className="text-[color:var(--color-success)]">+ начислено</span> оклад {fmtMoney(a.result?.oklad)} · KPI {fmtMoney(a.result?.kpi)}{a.result?.bonuses ? ` · премии ${fmtMoney(a.result?.bonuses)}` : ''}
                      </div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)]">
                        <span className="text-[color:var(--color-danger)]">− списано</span> авансы {fmtMoney(a.result?.advances)}{a.result?.penalties ? ` · штрафы ${fmtMoney(a.result?.penalties)}` : ''}
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-3 shrink-0 border-t border-[color:var(--color-border)] pt-2 sm:border-0 sm:pt-0 sm:justify-end">
                      <div className="sm:text-right">
                        <div className="font-semibold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">{fmtMoney(a.result?.to_pay)}</div>
                        <div className="text-[10px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">к выплате</div>
                      </div>
                      {a.payout_id ? (
                        <span className="inline-flex items-center gap-1 text-xs text-[color:var(--color-success)] shrink-0" title={`Выплата #${a.payout_id}`}><CheckCircle2 size={14} /> выплата</span>
                      ) : (
                        <button onClick={() => createPayout(a)} disabled={payingId === a.id || !(a.result?.to_pay > 0)}
                          className="btn btn--secondary btn--sm flex items-center gap-1.5 shrink-0" title="Создать выплату «Зарплата» на сумму к выплате">
                          <Banknote size={14} /> {payingId === a.id ? '…' : 'Выплата'}
                        </button>
                      )}
                      <button onClick={() => deleteAccrual(a.id)} className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-danger)] shrink-0" title="Удалить"><Trash2 size={15} /></button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
