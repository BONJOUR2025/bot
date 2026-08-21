import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Wallet, RefreshCw, Trash2, ChevronDown, ChevronUp, AlertTriangle, Banknote,
  CheckCircle2, Gauge, ShieldAlert, ListChecks, Receipt, Clock, Users, Coins,
} from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';
import { fmtMoney, fmtPct, Term, StatCard, MetricBar, Tabs, TONE_TEXT } from '../components/ui/SalaryUI.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';

function KpiRing({ pct, size = 84 }) {
  const clamped = Math.max(0, Math.min(pct ?? 0, 999));
  const r = (size - 10) / 2;
  const c = 2 * Math.PI * r;
  const dash = Math.min(clamped, 100) / 100 * c;
  const color = clamped >= 100 ? 'var(--color-success)' : clamped >= 79 ? 'var(--color-primary)' : 'var(--color-warning)';
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--color-bg-secondary)" strokeWidth="7" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth="7" strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`} style={{ transition: 'stroke-dasharray 0.6s ease' }} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-sm font-bold tabular-nums" style={{ color }}>{Math.round(clamped)}%</span>
        <span className="text-[9px] text-[color:var(--color-muted-foreground)] uppercase tracking-wide">KPI</span>
      </div>
    </div>
  );
}

const MANAGER_POSITION = 'менеджер по работе с клиентами';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

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

// Response-time tone: ≤30 мин хорошо, ≤1 ч приемлемо, дольше — плохо.
const respTone = (s) => (s == null ? 'muted' : s <= 1800 ? 'success' : s <= 3600 ? 'primary' : 'danger');

// ── Small presentational pieces ──────────────────────────────────────────────

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

function DealList({ title, deals, domain, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const list = deals || [];
  const sum = list.reduce((s, d) => s + (Number(d.price) || 0), 0);
  return (
    <div className="border border-[color:var(--color-border)] rounded-lg overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-bg-secondary)]">
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

function GroupedDealList({ title, deals, groupLabel, domain }) {
  const [open, setOpen] = useState(false);
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
        className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-bg-secondary)]">
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

// Per-deal response time list (slowest first; «без касания» at the end).
function ResponseList({ deals, domain }) {
  const [open, setOpen] = useState(false);
  const list = deals || [];
  const counted = list.filter((d) => d.seconds != null).length;
  const excluded = list.length - counted;
  return (
    <div className="app-card overflow-hidden">
      <button type="button" onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-2 px-5 py-3 hover:bg-[color:var(--color-bg-secondary)]">
        <span className="font-semibold flex items-center gap-2">
          <Clock size={16} /> Время ответа по сделкам
          <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· {counted} с касанием{excluded ? `, ${excluded} без` : ''}</span>
        </span>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && (
        list.length === 0 ? (
          <div className="px-5 py-6 text-center text-sm text-[color:var(--color-muted-foreground)] border-t border-[color:var(--color-border)]">Нет сделок за период.</div>
        ) : (
          <>
          <div className="px-5 py-2 border-t border-[color:var(--color-border)] text-[11px] text-[color:var(--color-muted-foreground)]">
            Только заявки, которые робот создал или перенёс на «Получена заявка». Время — до первого звонка или сообщения в чате, в рабочие часы 10:00–19:00 МСК.
          </div>
          <ul className="border-t border-[color:var(--color-border)] divide-y divide-[color:var(--color-border)] max-h-[28rem] overflow-y-auto">
            {list.map((d) => {
              const tone = respTone(d.seconds);
              return (
                <li key={d.id} className="px-5 py-2.5 flex items-center justify-between gap-3 text-sm">
                  <div className="min-w-0">
                    <div className="font-medium truncate">
                      {domain
                        ? <a href={`https://${domain}/leads/detail/${d.id}`} target="_blank" rel="noreferrer" className="text-[color:var(--color-primary)] hover:underline">{d.name || `#${d.id}`}</a>
                        : (d.name || `#${d.id}`)}
                      <span className="text-[color:var(--color-muted-foreground)]"> · #{d.id}</span>
                    </div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)]">заявка {d.received}{d.channel ? ` · ${d.channel}` : ''}</div>
                  </div>
                  <div className={`shrink-0 font-semibold tabular-nums whitespace-nowrap ${TONE_TEXT[tone]}`}>
                    {d.seconds == null
                      ? <span className="text-[color:var(--color-muted-foreground)] font-normal">без касания</span>
                      : fmtDuration(d.seconds)}
                  </div>
                </li>
              );
            })}
          </ul>
          </>
        )
      )}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ManagerSalary() {
  const { toast } = useToast();
  const months = useMemo(() => recentMonths(12), []);
  const [employees, setEmployees] = useState([]);
  const [managerId, setManagerId] = useState('');
  const [period, setPeriod] = useState(months[0].value);

  const [plan, setPlan] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [advances, setAdvances] = useState(null);
  const [incentives, setIncentives] = useState({ bonuses: 0, penalties: 0 });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [metricsError, setMetricsError] = useState(null);
  const [amoStatus, setAmoStatus] = useState(null);
  const [accruals, setAccruals] = useState([]);
  const [accruing, setAccruing] = useState(false);
  const [payingId, setPayingId] = useState(null);
  const [accrualsTick, setAccrualsTick] = useState(0);
  const [tab, setTab] = useState('overview');

  const managers = useMemo(
    () => employees
      .filter((e) => (e.position || '').trim().toLowerCase() === MANAGER_POSITION)
      .sort((a, b) => (a.full_name || a.name || '').localeCompare(b.full_name || b.name || '', 'ru')),
    [employees]);
  const manager = useMemo(() => managers.find((e) => String(e.id) === String(managerId)), [managers, managerId]);
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const periodLabel = months.find((m) => m.value === period)?.label || period;

  useEffect(() => {
    api.get('employees/', { params: { archived: false } })
      .then((r) => setEmployees((r.data || []).filter((e) => e.status !== 'inactive')))
      .catch(() => {});
    api.get('amo/status').then((r) => setAmoStatus(r.data)).catch(() => setAmoStatus(null));
  }, []);

  const loadAll = useCallback(async () => {
    if (!managerId) { setResult(null); setPlan(null); setMetrics(null); setAdvances(null); return; }
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

      const res = await api.post('manager-salary/calc', {
        oklad: pl.oklad, kpi_max: pl.kpi_max,
        revenue_plan: pl.revenue_plan, revenue_actual: met?.revenue_actual || 0,
        repair_plan_conv: pl.repair_plan_conv, repair_target_deals: met?.repair_target_deals || 0, repair_total_deals: met?.repair_total_deals || 0,
        sew_plan_conv: pl.sew_plan_conv, sew_target_deals: met?.sew_target_deals || 0, sew_total_deals: met?.sew_total_deals || 0, sew_new_leads: met?.sew_new_leads || 0,
        advances: adv?.total || 0, bonuses, penalties,
      });
      setResult(res.data);
    } catch (e) {
      console.error(e);
    } finally { setLoading(false); }
  }, [managerId, period, manager, dateFrom, dateTo]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useEffect(() => { if (managerId) api.get('manager-salary/accruals', { params: { employee_code: managerId, limit: 50 } }).then((r) => setAccruals(r.data || [])).catch(() => {}); else setAccruals([]); }, [managerId, accrualsTick]);

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
      setTab('history');
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
  const susp = metrics?.items?.suspicious || [];
  const kept = result?.advances || result?.penalties ? (result.advances + result.penalties) : 0;

  const tabs = [
    { key: 'overview', label: 'Обзор', icon: <Gauge size={15} /> },
    { key: 'control', label: 'Контроль', icon: <ShieldAlert size={15} />, badge: susp.length },
    { key: 'deals', label: 'Сделки', icon: <ListChecks size={15} /> },
    { key: 'history', label: 'История', icon: <Receipt size={15} />, badge: accruals.length },
  ];

  return (
    <div className="space-y-5 max-w-5xl mx-auto pb-12">
      <TopProgressBar active={loading} />
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">Зарплата менеджеров</h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Оклад и KPI, контроль качества, начисление и выплаты</p>
        </div>
        {amoStatus && (amoStatus.authorized
          ? <span className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-[color:var(--color-success-muted)] text-[color:var(--color-success)]"><span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-success)]" /> amoCRM подключён</span>
          : <a href="/admin/settings/integrations" className="inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full bg-[color:var(--color-danger-muted)] text-[color:var(--color-danger)] hover:underline"><span className="h-1.5 w-1.5 rounded-full bg-[color:var(--color-danger)]" /> amoCRM не подключён</a>)}
      </div>

      {/* Toolbar */}
      <div className="app-card p-3 flex flex-col sm:flex-row sm:items-end gap-3">
        <label className="block sm:flex-1">
          <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Менеджер</span>
          <select className="input w-full" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">— выберите —</option>
            {managers.map((e) => <option key={e.id} value={e.id}>{e.full_name || e.name}</option>)}
          </select>
        </label>
        <label className="block sm:w-48">
          <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Период</span>
          <select className="input w-full" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </label>
        <button className="btn btn--secondary flex items-center justify-center gap-1.5" onClick={loadAll} disabled={!managerId || loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
        </button>
      </div>

      {managers.length === 0 && (
        <div className="app-card p-4 text-sm text-[color:var(--color-muted-foreground)]">
          Нет сотрудников с должностью «менеджер по работе с клиентами». Назначьте должность в карточке сотрудника.
        </div>
      )}

      {!managerId ? (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
          <Users size={28} className="mx-auto mb-2 opacity-60" />
          Выберите менеджера и период, чтобы увидеть расчёт.
        </div>
      ) : loading && !result ? (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Загрузка…</div>
      ) : result ? (
        <>
          {/* Warnings */}
          {(planEmpty || metricsError) && (
            <div className="space-y-2">
              {planEmpty && (
                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  План на этот месяц не задан — заполните оклад/KPI/план на странице «Планы продаж».
                </div>
              )}
              {metricsError && (
                <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-amber-50 border border-amber-200 text-sm text-amber-800 dark:bg-amber-900/20 dark:border-amber-800 dark:text-amber-300">
                  <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                  Факт из amoCRM недоступен ({metricsError}). KPI посчитан по нулям — показан только оклад.
                </div>
              )}
            </div>
          )}

          {/* Hero: payout summary + action */}
          <section className="app-card overflow-hidden">
            <div className="p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-5">
              <div className="flex items-center gap-4 min-w-0">
                <KpiRing pct={result.kpi_max > 0 ? (result.kpi / result.kpi_max) * 100 : 0} />
                <div className="min-w-0">
                  <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                    К выплате · {manager?.full_name || manager?.name} · {periodLabel}
                  </div>
                  <div className="mt-1 text-4xl font-bold tabular-nums text-[color:var(--color-primary)] whitespace-nowrap">
                    {fmtMoney(result.to_pay)}
                  </div>
                  <div className="mt-1 text-sm text-[color:var(--color-muted-foreground)]">
                    Начислено {fmtMoney(result.gross)}{kept ? <> · удержано <span className="text-[color:var(--color-danger)]">{fmtMoney(kept)}</span></> : null}
                  </div>
                </div>
              </div>
              <div className="shrink-0 sm:text-right">
                <button className="btn btn--primary flex items-center gap-2 w-full sm:w-auto justify-center" onClick={accrue} disabled={accruing}>
                  <Wallet size={16} /> {accruing ? 'Начисляю…' : 'Начислить ЗП'}
                </button>
                <div className="mt-1.5 text-[11px] text-[color:var(--color-muted-foreground)] max-w-[220px] sm:ml-auto">
                  Зафиксирует расчёт в журнале. Выплату создадите там же.
                </div>
              </div>
            </div>
            {/* Payout formula */}
            <div className="px-5 sm:px-6 py-4 border-t border-[color:var(--color-border)] flex flex-wrap items-center gap-x-4 gap-y-3">
              <Term label="Оклад" value={result.oklad} />
              <Term op="+" label="Комиссия KPI" value={result.kpi} tone={TONE_TEXT.success} />
              <Term op="+" label="Премии" value={result.bonuses} tone={result.bonuses ? TONE_TEXT.success : ''} />
              <Term op="−" label="Авансы" value={result.advances} tone={result.advances ? TONE_TEXT.danger : ''} />
              <Term op="−" label="Штрафы" value={result.penalties} tone={result.penalties ? TONE_TEXT.danger : ''} />
              <Term op="=" label="К выплате" value={result.to_pay} tone={TONE_TEXT.primary} strong />
            </div>
          </section>

          {/* Tabs */}
          <Tabs tabs={tabs} active={tab} onChange={setTab} />

          {tab === 'overview' && (
            <div className="space-y-4">
            <div className="grid lg:grid-cols-3 gap-4">
              {/* KPI breakdown with progress bars */}
              <div className="lg:col-span-2 app-card p-5">
                <div className="flex items-baseline justify-between gap-2 mb-3">
                  <h3 className="font-semibold flex items-center gap-2"><Coins size={16} /> Комиссия (KPI)</h3>
                  <div className="text-sm text-[color:var(--color-muted-foreground)]">
                    <span className="font-semibold text-[color:var(--color-text)]">{fmtMoney(result.kpi)}</span> из цели {fmtMoney(result.kpi_max)}
                  </div>
                </div>
                <MetricBar
                  label={`Выручка · вес ${(result.weights.revenue * 100).toFixed(0)}%`}
                  plan={plan?.revenue_plan} fact={metrics?.revenue_actual}
                  ratio={result.revenue.ratio} contribution={result.revenue.amount} />
                <MetricBar
                  label={`Конверсия ремонта · вес ${(result.weights.repair * 100).toFixed(0)}%`}
                  plan={plan?.repair_plan_conv} fact={result.repair.conv} fmt={fmtPct}
                  ratio={result.repair.ratio} contribution={result.repair.amount}
                  note={`целевых ${result.repair.target} / всего ${result.repair.total}`} />
                <MetricBar
                  label={`Конверсия пошива · вес ${(result.weights.sew * 100).toFixed(0)}%`}
                  plan={plan?.sew_plan_conv} fact={result.sew.conv} fmt={fmtPct}
                  ratio={result.sew.ratio} contribution={result.sew.amount}
                  note={result.sew.leads_gate_failed
                    ? `не зачтена: лидов ${result.sew.new_leads} < ${result.sew.min_leads}`
                    : `целевых ${result.sew.target} / всего ${result.sew.total}`} />
                <div className="mt-3 text-[11px] text-[color:var(--color-muted-foreground)]">
                  Полоской отмечен порог 79%: компонент ниже порога не оплачивается. Цель 100% = план; перевыполнение оплачивается сверх цели.
                </div>
              </div>

              {/* Quality stats */}
              <div className="space-y-4">
                <StatCard
                  icon={<Clock size={18} />}
                  label="Время первого ответа"
                  value={fmtDuration(metrics?.median_response_seconds)}
                  tone={TONE_TEXT[respTone(metrics?.median_response_seconds)]}
                  sub={metrics?.response_sample
                    ? `медиана · ср. ${fmtDuration(metrics.avg_response_seconds)} · по ${metrics.response_sample}${metrics.response_excluded ? `, ${metrics.response_excluded} без касания` : ''}`
                    : 'нет данных (нет звонка/сообщения после заявки)'} />
                <StatCard
                  icon={<Users size={18} />}
                  label="Новых лидов (пошив)"
                  value={metrics?.sew_new_leads ?? '—'}
                  sub="созданы в периоде в воронке пошива" />
                <StatCard
                  icon={<ShieldAlert size={18} />}
                  label="Подозрительные сделки"
                  value={susp.length}
                  tone={susp.length ? TONE_TEXT.danger : TONE_TEXT.success}
                  sub={susp.length ? 'перемещения между воронками — см. «Контроль»' : 'перемещений между воронками нет'} />
              </div>
            </div>
            {metrics?.items?.response && (
              <ResponseList deals={metrics.items.response} domain={amoStatus?.domain} />
            )}
            </div>
          )}

          {tab === 'control' && (
            <div className="app-card p-5 space-y-3">
              <h3 className="font-semibold flex items-center gap-2"><ShieldAlert size={16} className="text-amber-500" /> Подозрительные сделки <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· перемещения между воронками ({susp.length})</span></h3>
              {susp.length === 0 ? (
                <div className="text-sm text-[color:var(--color-muted-foreground)]">За период перемещений между воронками не обнаружено.</div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <GroupedDealList title="Пришли из другой воронки" deals={susp.filter((d) => d.direction === 'in' || d.direction === 'between')} domain={amoStatus?.domain} groupLabel={(d) => `из «${d.from_name || '—'}»`} />
                  <GroupedDealList title="Перенесены в другую воронку" deals={susp.filter((d) => d.direction === 'out' || d.direction === 'between')} domain={amoStatus?.domain} groupLabel={(d) => `в «${d.to_name || '—'}»`} />
                </div>
              )}
              <div className="text-[11px] text-[color:var(--color-muted-foreground)]">
                Сделки, у которых в периоде менялась воронка (пришли из другой воронки или были перенесены). Могут искусственно влиять на выручку и конверсию — стоит проверить обоснованность.
              </div>
            </div>
          )}

          {tab === 'deals' && (
            metrics?.items ? (
              <div className="app-card p-5 space-y-2">
                <h3 className="font-semibold flex items-center gap-2"><ListChecks size={16} /> Сделки в расчёте <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">(проверка цифр)</span></h3>
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
            ) : (
              <div className="app-card p-8 text-center text-sm text-[color:var(--color-muted-foreground)]">Детализация недоступна — нет данных из amoCRM.</div>
            )
          )}

          {tab === 'history' && (
            <div className="app-card overflow-hidden">
              <div className="px-5 py-3 border-b border-[color:var(--color-border)] font-semibold flex items-center gap-2">
                <Receipt size={16} /> Журнал начислений
                <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">{manager ? manager.full_name || manager.name : ''} · {accruals.length}</span>
              </div>
              {accruals.length === 0 ? (
                <div className="px-5 py-10 text-center text-sm text-[color:var(--color-muted-foreground)]">Начислений пока нет. Нажмите «Начислить ЗП», чтобы зафиксировать расчёт.</div>
              ) : (
                <ul className="divide-y divide-[color:var(--color-border)]">
                  {accruals.map((a) => (
                    <li key={a.id} className="px-5 py-3 text-sm flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
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
        </>
      ) : null}
    </div>
  );
}
