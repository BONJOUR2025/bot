import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wallet, CheckCircle, Umbrella, Warning, ArrowUpRight,
  CalendarBlank, Clock, ListChecks, PlayCircle, ArrowsClockwise,
  Scissors, UserPlus, ChatCircle, PaperPlaneTilt, Trophy,
  Timer, Airplane, Users, Receipt,
} from '@phosphor-icons/react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';
import { useAuth } from '../providers/AuthProvider.jsx';
import EmptyState from '../components/ui/EmptyState.jsx';

const SALES_COLORS = { repair: 'var(--color-primary)', cosmetics: 'var(--color-success)', shoes: 'var(--color-warning)' };
const SALES_LABELS = { repair: 'Ремонт', cosmetics: 'Косметика', shoes: 'Обувь' };

// ── helpers ──────────────────────────────────────────────────────────────────

function fmt(n) {
  return Number(n ?? 0).toLocaleString('ru-RU');
}

function fmtDate(val) {
  if (!val) return '';
  const d = new Date(val);
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function fmtTs(val) {
  if (!val) return '';
  const d = new Date(val);
  const now = new Date();
  const diff = Math.floor((now - d) / 60000);
  if (diff < 60) return `${diff} мин назад`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ч назад`;
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function nextBirthdayDate(birthdate) {
  if (!birthdate) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const bd = new Date(birthdate);
  const candidate = new Date(today.getFullYear(), bd.getMonth(), bd.getDate());
  if (candidate < today) candidate.setFullYear(today.getFullYear() + 1);
  return candidate;
}

function daysUntilBirthday(birthdate) {
  const next = nextBirthdayDate(birthdate);
  if (!next) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((next - today) / 86400000);
}

function daysLeft(endDateStr) {
  if (!endDateStr) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const d = new Date(endDateStr);
  d.setHours(0, 0, 0, 0);
  return Math.round((d - today) / 86400000);
}

function greeting() {
  const h = new Date().getHours();
  if (h < 5) return 'Доброй ночи';
  if (h < 12) return 'Доброе утро';
  if (h < 18) return 'Добрый день';
  return 'Добрый вечер';
}

const VACATION_TONE = { Отпуск: 'var(--color-info)', Больничный: 'var(--color-warning)', Командировка: 'var(--color-text-faint)' };

// ── scroll-reveal primitive (IntersectionObserver, transform+opacity only) ──

/**
 * Появление одного блока. Класс .ui-reveal и его переход описаны в
 * globals.css, здесь — только момент, когда навесить .is-in, поэтому
 * анимация одинакова с остальными страницами и меняется в одном месте.
 *
 * Порог 0.12 оставлен от прежней реализации: карточки бенто высокие, и
 * при меньшем значении верхняя кромка засчитывалась бы за появление,
 * когда сама карточка ещё за экраном.
 */
function Reveal({ className = '', delay = 0, children }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;

    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    if (reduced || typeof IntersectionObserver === 'undefined') {
      el.classList.add('is-in');
      return undefined;
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        el.style.setProperty('--reveal-delay', `${delay}ms`);
        el.classList.add('is-in');
        io.disconnect();
      },
      { threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [delay]);

  return (
    <div ref={ref} className={`ui-reveal ${className}`.trim()}>
      {children}
    </div>
  );
}

// ── поверхность бенто: оболочка + ядро (вне стекла обёртки инертны) ──────────

function Panel({ className = '', children }) {
  return (
    <div className="ui-shell h-full">
      <div
        className={`ui-core border border-[color:var(--color-border)] bg-[color:var(--color-surface)] ${className}`}
      >
        {children}
      </div>
    </div>
  );
}

function BentoCard({ span = '', eyebrow, title, action, delay = 0, children }) {
  return (
    <Reveal delay={delay} className={span}>
      <Panel className="flex h-full flex-col p-5 sm:p-6">
        {(title || action || eyebrow) && (
          <div className="mb-4 flex items-start justify-between gap-3 border-b border-[color:var(--color-border)] pb-3">
            <div>
              {eyebrow && <div className="ui-label mb-1.5">{eyebrow}</div>}
              {title && (
                <h3 className="text-base font-medium tracking-[-0.02em] text-[color:var(--color-text)]">
                  {title}
                </h3>
              )}
            </div>
            {action}
          </div>
        )}
        <div className="flex-1">{children}</div>
      </Panel>
    </Reveal>
  );
}

// ── "see all" link ────────────────────────────────────────────────────────────

function GhostLink({ to, label = 'Все' }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(to)}
      className="group inline-flex shrink-0 items-center gap-1 text-xs font-medium text-[color:var(--color-text-faint)] transition-colors hover:text-[color:var(--color-primary)]"
    >
      {label}
      <ArrowUpRight size={12} weight="light" className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
    </button>
  );
}

// ── refresh button ────────────────────────────────────────────────────────────

function RefreshButton({ onClick, disabled, spinning, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-2 border border-[color:var(--color-border)] px-4 py-2 text-sm font-medium text-[color:var(--color-text)] transition-colors hover:bg-[color:var(--color-control-bg-hover)] disabled:opacity-40"
    >
      <ArrowsClockwise size={15} weight="light" className={spinning ? 'animate-spin' : ''} />
      {children}
    </button>
  );
}

// ── KPI cell ──────────────────────────────────────────────────────────────────

function StatOrb({ icon: Icon, label, value, sub, tone = 'primary', to, big = false, delay = 0 }) {
  const navigate = useNavigate();
  const toneColor = {
    primary: 'var(--color-primary)',
    warning: 'var(--color-warning)',
    danger: 'var(--color-danger)',
    success: 'var(--color-success)',
    info: 'var(--color-info)',
    neutral: 'var(--color-text-faint)',
  }[tone];

  return (
    <Reveal delay={delay} className="h-full">
      {/* Полоска-акцент слева убрана намеренно: она была единственным
          носителем tone, а цветная рамка у карточки читается как
          статус-индикатор даже там, где tone означает всего лишь раздел.
          Теперь тон несёт иконка, а показатель остаётся нейтральным. */}
      <div className="ui-shell h-full">
        <button
          type="button"
          onClick={to ? () => navigate(to) : undefined}
          className={`ui-core h-full w-full border border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-5 text-left ${big ? 'sm:p-6' : ''} ${
            to ? 'cursor-pointer hover:bg-[color:var(--color-control-bg-hover)]' : 'cursor-default'
          }`}
        >
          <div className="flex items-center justify-between">
            <span
              className="grid h-8 w-8 place-items-center rounded-full"
              style={{ background: `color-mix(in oklab, ${toneColor} 14%, transparent)` }}
            >
              <Icon size={16} weight="light" style={{ color: toneColor }} />
            </span>
            {to && (
              <ArrowUpRight
                size={13}
                weight="light"
                className="text-[color:var(--color-text-faint)]"
              />
            )}
          </div>
          <div className="mt-4">
            <div
              className={`ui-metric text-[color:var(--color-text)] ${big ? 'sm:text-[2.6rem]' : ''}`}
            >
              {value}
            </div>
            <div className="mt-2 text-sm text-[color:var(--color-text-muted)]">{label}</div>
            {sub && <div className="mt-0.5 text-xs text-[color:var(--color-text-faint)]">{sub}</div>}
          </div>
        </button>
      </div>
    </Reveal>
  );
}

// ── task queue row ────────────────────────────────────────────────────────────

function TaskRow({ icon: Icon, label, count, tone }) {
  const color = {
    danger: 'var(--color-danger)',
    warning: 'var(--color-warning)',
    info: 'var(--color-info)',
    neutral: 'var(--color-text-faint)',
  }[tone];
  return (
    <div className="flex items-center justify-between border-b border-[color:var(--color-border)] py-2.5 last:border-0">
      <div className="flex items-center gap-2.5 text-sm text-[color:var(--color-text-muted)]">
        <Icon size={15} weight="light" style={{ color }} />
        <span>{label}</span>
      </div>
      <span className="text-sm font-semibold" style={{ color }}>
        {count}
      </span>
    </div>
  );
}

// ── empty state ───────────────────────────────────────────────────────────────

// Обёртка над общим EmptyState: сохраняет прежнюю сигнатуру (text/icon),
// чтобы не править полтора десятка точек вызова, но рисует то же, что и
// остальное приложение. Карточки бенто невысокие, поэтому compact.
function Empty({ text = 'Нет данных', icon: Icon, hint }) {
  return <EmptyState compact title={text} hint={hint} icon={Icon} />;
}

// ── loading skeleton ──────────────────────────────────────────────────────────

function SkeletonBento({ span = '', h = 'h-40' }) {
  return (
    <div className={span}>
      <div className={`skeleton ${h} border border-[color:var(--color-border)]`} />
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [pending, setPending] = useState([]);
  const [approved, setApproved] = useState([]);
  const [vacations, setVacations] = useState([]);
  const [taskStats, setTaskStats] = useState(null);
  const [birthdays, setBirthdays] = useState([]);
  const [masters, setMasters] = useState(null);
  const [sales, setSales] = useState(null); // null = unavailable
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [recruitNotifs, setRecruitNotifs] = useState(null);
  const [shiftCheckins, setShiftCheckins] = useState(null); // null = unavailable
  const [leaveRequests, setLeaveRequests] = useState(null);
  const [cashBalances, setCashBalances] = useState(null);
  const [visitorSummary, setVisitorSummary] = useState(null);
  const [receivables, setReceivables] = useState(null);

  async function load(silent = false) {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [
        pendRes, vacRes, taskRes, bdRes, mastersRes, salesRes, notifRes,
        shiftRes, leaveRes, cashRes, visitorRes, receivablesRes,
      ] = await Promise.allSettled([
        api.get('payouts/active'),
        api.get('vacations/active'),
        api.get('tasks/stats'),
        api.get('birthdays/', { params: { days: 30 } }),
        api.get('masters/works', { params: { date_from: today, date_to: today } }),
        api.get('sales/daily', { params: { date_from: today, date_to: today } }),
        api.get('recruitment/notifications'),
        api.get('shift-checkins/', { params: { date_from: today, date_to: today } }),
        api.get('leave-requests/'),
        api.get('cash-moves/balances'),
        api.get('visitor-events/summary', { params: { date_from: today, date_to: today } }),
        api.get('sales/receivables'),
      ]);
      if (pendRes.status === 'fulfilled') {
        const all = pendRes.value.data ?? [];
        setPending(all.filter((p) => p.status === 'Ожидает'));
        setApproved(all.filter((p) => p.status === 'Одобрено'));
      }
      if (vacRes.status === 'fulfilled') setVacations(vacRes.value.data ?? []);
      if (taskRes.status === 'fulfilled') setTaskStats(taskRes.value.data ?? null);
      if (bdRes.status === 'fulfilled') setBirthdays(bdRes.value.data ?? []);
      if (mastersRes.status === 'fulfilled') setMasters(mastersRes.value.data ?? null);
      else retryMasters(today);
      if (salesRes.status === 'fulfilled') setSales(salesRes.value.data ?? null);
      else retrySales(today);
      if (notifRes.status === 'fulfilled') setRecruitNotifs(notifRes.value.data ?? null);
      if (shiftRes.status === 'fulfilled') setShiftCheckins(shiftRes.value.data ?? []);
      if (leaveRes.status === 'fulfilled') setLeaveRequests(leaveRes.value.data ?? []);
      if (cashRes.status === 'fulfilled') setCashBalances(cashRes.value.data ?? []);
      if (visitorRes.status === 'fulfilled') setVisitorSummary(visitorRes.value.data ?? []);
      if (receivablesRes.status === 'fulfilled') setReceivables(receivablesRes.value.data ?? null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  // masters/works and sales/daily are the two Firebird-heavy dashboard
  // queries — they're the ones most likely to miss load()'s window on the
  // very first hit of the day/after a restart, when Firebird's page cache
  // for them is still cold (a manual "Обновить" click moments later reads
  // the same, now-warm, pages and succeeds). Retried independently of
  // load()'s own Promise.allSettled so a slow retry doesn't hold up
  // rendering the rest of the dashboard.
  function retryMasters(today) {
    api.get('masters/works', { params: { date_from: today, date_to: today } })
      .then((res) => setMasters(res.data ?? null))
      .catch(() => {});
  }
  function retrySales(today) {
    api.get('sales/daily', { params: { date_from: today, date_to: today } })
      .then((res) => setSales(res.data ?? null))
      .catch(() => {});
  }

  useEffect(() => {
    load();
  }, []);

  const pendingTotal = pending.reduce((s, p) => s + (p.amount ?? 0), 0);
  const approvedTotal = approved.reduce((s, p) => s + (p.amount ?? 0), 0);
  const today = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' });
  const { user } = useAuth();
  // Показываем только имя: полное ФИО в приветствии звучит как обращение
  // из документа, а не из панели, которой человек пользуется каждый день.
  const displayName = (user?.display_name || user?.login || '').trim().split(/\s+/)[0] || '';

  // ── sales aggregation (unchanged from prior logic) ──
  let salesRows = [];
  let salesDonut = [];
  let totTotal = 0;
  let hiddenSalesCount = 0;
  if (sales && sales.length) {
    const byEmp = {};
    for (const r of sales) {
      const key = r.description || r.code || '—';
      if (!byEmp[key]) byEmp[key] = { description: key, repair: 0, cosmetics: 0, shoes: 0 };
      byEmp[key].repair += r.repair ?? 0;
      byEmp[key].cosmetics += r.cosmetics ?? 0;
      byEmp[key].shoes += r.shoes ?? 0;
    }
    const rows = Object.values(byEmp).sort((a, b) => b.repair + b.cosmetics + b.shoes - (a.repair + a.cosmetics + a.shoes));
    const totRepair = rows.reduce((s, r) => s + r.repair, 0);
    const totCosmetics = rows.reduce((s, r) => s + r.cosmetics, 0);
    const totShoes = rows.reduce((s, r) => s + r.shoes, 0);
    totTotal = totRepair + totCosmetics + totShoes;
    hiddenSalesCount = Math.max(0, rows.length - 5);
    salesRows = rows.slice(0, 5);
    salesDonut = [
      { key: 'repair', value: totRepair },
      { key: 'cosmetics', value: totCosmetics },
      { key: 'shoes', value: totShoes },
    ].filter((d) => d.value > 0);
  }

  // ── masters aggregation (unchanged from prior logic) ──
  let topMasters = [];
  let hiddenMastersCount = 0;
  let maxKredit = 1;
  let mastersTotals = { done: 0, kredit: 0, salary: 0 };
  if (masters?.salary_summary?.length) {
    const rows = masters.salary_summary;
    mastersTotals = {
      done: rows.reduce((s, r) => s + (r.services_done ?? 0), 0),
      kredit: rows.reduce((s, r) => s + (r.total_kredit ?? 0), 0),
      salary: rows.reduce((s, r) => s + (r.total_salary ?? 0), 0),
    };
    topMasters = [...rows].sort((a, b) => (b.total_kredit ?? 0) - (a.total_kredit ?? 0)).slice(0, 5);
    hiddenMastersCount = Math.max(0, rows.length - 5);
    maxKredit = Math.max(1, ...topMasters.map((m) => m.total_kredit ?? 0));
  }

  const tooltipStyle = {
    contentStyle: {
      background: 'var(--color-modal-bg)',
      border: '1px solid var(--color-border)',
      borderRadius: 0,
      fontSize: 12,
      color: 'var(--color-text)',
    },
    itemStyle: { color: 'var(--color-text)' },
    labelStyle: { color: 'var(--color-text-muted)' },
  };

  // ── extra operational metrics (attendance, leave requests, cash, footfall, receivables) ──
  const lateCheckins = shiftCheckins ? shiftCheckins.filter((c) => (c.delay_minutes ?? 0) > 0) : null;
  const pendingLeave = leaveRequests ? leaveRequests.filter((r) => r.status === 'Ожидает') : null;
  const cashTotal = cashBalances ? Math.round(cashBalances.reduce((s, c) => s + (c.balance || 0), 0)) : null;
  const topCashRegister = cashBalances && cashBalances.length ? cashBalances[0] : null;
  const visitorsToday = visitorSummary ? visitorSummary.reduce((s, v) => s + (v.in_count || 0), 0) : null;

  // ── KPI priority ranking — the metric that most needs attention right now
  // leads as the hero cell, instead of a fixed "pending payouts" slot that
  // stays prominent even when it's zero. Base priorities (no urgency) keep a
  // sensible fallback order: overdue tasks > payout approvals > money owed > staff absence.
  const statDefs = [
    {
      key: 'overdue',
      icon: Warning,
      label: 'Просрочено задач',
      value: taskStats?.overdue ?? '—',
      sub: taskStats?.due_today ? `Сегодня: ${taskStats.due_today}` : undefined,
      tone: taskStats?.overdue > 0 ? 'danger' : 'neutral',
      to: '/admin/tasks',
      priority: taskStats?.overdue > 0 ? 100 : 40,
    },
    {
      key: 'pending',
      icon: Wallet,
      label: 'Ожидают одобрения выплаты',
      value: pending.length,
      sub: pending.length ? `${fmt(pendingTotal)} ₽ к согласованию` : 'Пусто — можно выдохнуть',
      tone: 'warning',
      to: '/admin/payouts',
      priority: pending.length > 0 ? 90 : 35,
    },
    {
      key: 'approved',
      icon: CheckCircle,
      label: 'Одобрено, к выплате',
      value: approved.length,
      sub: approved.length ? `${fmt(approvedTotal)} ₽` : undefined,
      tone: 'success',
      to: '/admin/payouts',
      priority: approved.length > 0 ? 85 : 30,
    },
    {
      key: 'lateCheckins',
      icon: Timer,
      label: 'Опоздания сегодня',
      value: lateCheckins ? lateCheckins.length : '—',
      sub: lateCheckins ? `Явок всего: ${shiftCheckins.length}` : undefined,
      tone: lateCheckins && lateCheckins.length > 0 ? 'danger' : 'neutral',
      to: '/admin/shift-checkins',
      priority: lateCheckins && lateCheckins.length > 0 ? 95 : 38,
    },
    {
      key: 'pendingLeave',
      icon: Airplane,
      label: 'Заявки на отпуск',
      value: pendingLeave ? pendingLeave.length : '—',
      sub: pendingLeave && pendingLeave.length ? 'Ожидают решения' : undefined,
      tone: pendingLeave && pendingLeave.length > 0 ? 'warning' : 'neutral',
      to: '/admin/leave-requests',
      priority: pendingLeave && pendingLeave.length > 0 ? 70 : 25,
    },
    {
      key: 'vacations',
      icon: Umbrella,
      label: 'Сейчас отсутствуют',
      value: vacations.length,
      tone: 'info',
      to: '/admin/vacations',
      priority: 20,
    },
  ];
  const [heroStat, ...secondaryStats] = [...statDefs].sort((a, b) => b.priority - a.priority);

  // same idea for the payouts-list vs tasks-list panels below: whichever
  // needs action more right now takes the wider, leading position.
  const financeUrgency = Math.max(pending.length > 0 ? 90 : 35, approved.length > 0 ? 85 : 30);
  const tasksUrgency = taskStats?.overdue > 0 ? 100 : 40;
  const financeFirst = financeUrgency >= tasksUrgency;

  const renderFinancePanel = (delay) => (
    <BentoCard eyebrow="Финансы" title="Ожидают выплаты" action={<GhostLink to="/admin/payouts" />} delay={delay}>
      {pending.length === 0 ? (
        <Empty text="Нет запросов на выплату" icon={Wallet} />
      ) : (
        <div>
          {pending.slice(0, 7).map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-3 border-b border-[color:var(--color-border)] py-2.5 last:border-0">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-[color:var(--color-text)]">{p.name}</div>
                <div className="flex flex-wrap items-center gap-x-2 text-xs text-[color:var(--color-text-faint)]">
                  <span>{p.payout_type}</span>
                  <span>·</span>
                  <span>{p.method}</span>
                  <span>·</span>
                  <span>{fmtTs(p.timestamp)}</span>
                </div>
              </div>
              <span className="shrink-0 text-sm font-semibold text-[color:var(--color-text)]">{fmt(p.amount)} ₽</span>
            </div>
          ))}
          {pending.length > 7 && (
            <p className="pt-2.5 text-xs text-[color:var(--color-text-faint)]">+ ещё {pending.length - 7}</p>
          )}
        </div>
      )}
    </BentoCard>
  );

  const renderTasksPanel = (delay) => (
    <BentoCard eyebrow="Коммуникации" title="Задачи" action={<GhostLink to="/admin/tasks" />} delay={delay}>
      {!taskStats ? (
        <Empty text="Нет данных по задачам" icon={ListChecks} />
      ) : (
        <div>
          <TaskRow icon={Warning} label="Просрочено" count={taskStats.overdue} tone="danger" />
          <TaskRow icon={Clock} label="Сегодня" count={taskStats.due_today} tone="warning" />
          <TaskRow icon={PlayCircle} label="В работе" count={taskStats.in_progress} tone="info" />
          <TaskRow icon={ListChecks} label="В очереди" count={taskStats.todo} tone="neutral" />
          <div className="flex items-center justify-between pt-2.5 text-xs text-[color:var(--color-text-faint)]">
            <span>Всего активных</span>
            <span className="font-medium text-[color:var(--color-text-muted)]">{(taskStats.todo ?? 0) + (taskStats.in_progress ?? 0)}</span>
          </div>
        </div>
      )}
    </BentoCard>
  );

  return (
    <div className="space-y-5">
      {/* Шапка. Имя берём из учётной записи: раньше здесь было
          захардкожено «Nick», и приветствие обращалось не к тому, кто вошёл. */}
      <div className="ui-reveal mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <span className="ui-eyebrow">Обзор · {today}</span>
          <h1 className="mt-4 text-2xl font-semibold tracking-[-0.03em] text-[color:var(--color-text)] sm:text-[2.6rem]">
            {greeting()}
            {displayName ? (
              <>
                ,<br />
                <b>{displayName}</b>.
              </>
            ) : (
              '.'
            )}
          </h1>
        </div>
        <RefreshButton onClick={() => load(true)} disabled={refreshing} spinning={refreshing}>
          Обновить
        </RefreshButton>
      </div>

      {loading ? (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <SkeletonBento h="h-32" />
            <SkeletonBento h="h-32" />
            <SkeletonBento h="h-32" />
            <SkeletonBento h="h-32" />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            <SkeletonBento span="lg:col-span-7" h="h-56" />
            <SkeletonBento span="lg:col-span-5" h="h-56" />
          </div>
        </div>
      ) : (
        <>
          {/* sales today */}
          {sales !== null && (
            <BentoCard eyebrow="Продажи" title="Продажи сегодня" action={<GhostLink to="/admin/sales" label="Подробнее" />}>
              {!sales.length ? (
                <Empty text="Нет данных по продажам за сегодня" icon={Scissors} />
              ) : (
                <>
                  {salesDonut.length > 0 && (
                    <div className="mb-4 flex items-center gap-5 border-b border-[color:var(--color-border)] pb-4">
                      <div style={{ width: 76, height: 76, flexShrink: 0 }}>
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie data={salesDonut} dataKey="value" nameKey="key" innerRadius="55%" outerRadius="90%" paddingAngle={2} isAnimationActive={false}>
                              {salesDonut.map((d) => (
                                <Cell key={d.key} fill={SALES_COLORS[d.key]} stroke="none" />
                              ))}
                            </Pie>
                            <Tooltip formatter={(v, n, p) => [`${fmt(v)} ₽`, SALES_LABELS[p.payload.key]]} {...tooltipStyle} />
                          </PieChart>
                        </ResponsiveContainer>
                      </div>
                      <div className="flex flex-1 flex-wrap gap-x-5 gap-y-1.5">
                        {salesDonut.map((d) => (
                          <div key={d.key} className="flex items-center gap-1.5 text-xs">
                            <span className="h-2.5 w-2.5 shrink-0" style={{ background: SALES_COLORS[d.key] }} />
                            <span className="text-[color:var(--color-text-faint)]">{SALES_LABELS[d.key]}</span>
                            <span className="font-semibold text-[color:var(--color-text)]">{fmt(d.value)} ₽</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  <div className="space-y-2">
                    {salesRows.map((r) => {
                      const total = r.repair + r.cosmetics + r.shoes;
                      return (
                        <div key={r.description} className="flex items-center justify-between gap-3 border border-[color:var(--color-border)] px-3 py-2.5">
                          <span className="min-w-0 truncate text-sm font-medium text-[color:var(--color-text)]">{r.description}</span>
                          <div className="flex shrink-0 items-center gap-4 text-xs text-[color:var(--color-text-faint)]">
                            <span>Р {r.repair ? fmt(r.repair) : '—'}</span>
                            <span>К {r.cosmetics ? fmt(r.cosmetics) : '—'}</span>
                            <span>О {r.shoes ? fmt(r.shoes) : '—'}</span>
                            <span className="font-semibold text-[color:var(--color-text)]">{fmt(total)} ₽</span>
                          </div>
                        </div>
                      );
                    })}
                    <div className="flex items-center justify-between border border-[color:var(--color-border)] bg-[color:var(--color-bg-subtle)] px-3 py-2.5">
                      <span className="text-sm font-semibold text-[color:var(--color-text)]">Итого</span>
                      <span className="text-sm font-semibold text-[color:var(--color-text)]">{fmt(totTotal)} ₽</span>
                    </div>
                  </div>
                  {hiddenSalesCount > 0 && (
                    <p className="pt-2.5 text-xs text-[color:var(--color-text-faint)]">+ ещё {hiddenSalesCount} — все продажи в разделе «Подробнее» выше</p>
                  )}
                </>
              )}
            </BentoCard>
          )}

          {/* masters today */}
          {masters !== null && (
            <BentoCard eyebrow="Мастера" title="Мастера сегодня" action={<GhostLink to="/admin/masters" label="Подробнее" />} delay={80}>
              {!masters.salary_summary?.length ? (
                <Empty text="Нет данных по мастерам за сегодня" icon={Trophy} />
              ) : (
                <>
                  {topMasters.length > 0 && (
                    <div className="mb-4 space-y-2 border-b border-[color:var(--color-border)] pb-4">
                      <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-[color:var(--color-text-faint)]">
                        <Trophy size={13} weight="light" /> Топ по выручке
                      </div>
                      {topMasters.map((m) => {
                        const pct = maxKredit > 0 ? ((m.total_kredit ?? 0) / maxKredit) * 100 : 0;
                        return (
                          <div key={m.master} className="flex items-center gap-3">
                            <span className="w-24 shrink-0 truncate text-xs text-[color:var(--color-text-muted)]">{m.master}</span>
                            <div className="h-1.5 flex-1 overflow-hidden bg-[color:var(--color-bg-subtle)]">
                              <div
                                className="h-full transition-[width] duration-700 ease-out"
                                style={{ width: `${pct}%`, background: 'var(--color-primary)' }}
                              />
                            </div>
                            <span className="w-20 shrink-0 text-right text-xs font-semibold text-[color:var(--color-text)]">{fmt(m.total_kredit)} ₽</span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div className="space-y-2">
                    {topMasters.map((m) => (
                      <div key={m.master} className="flex items-center justify-between gap-3 border border-[color:var(--color-border)] px-3 py-2.5">
                        <span className="min-w-0 truncate text-sm font-medium text-[color:var(--color-text)]">{m.master}</span>
                        <div className="flex shrink-0 items-center gap-4 text-xs text-[color:var(--color-text-faint)]">
                          <span>{m.services_done} усл.</span>
                          <span className="font-semibold text-[color:var(--color-text-muted)]">{fmt(m.total_kredit)} ₽</span>
                          <span className="font-semibold" style={{ color: 'var(--color-success)' }}>{fmt(m.total_salary)} ₽</span>
                          {m.warnings_count > 0 && (
                            <span className="border px-1.5 py-0.5 font-semibold" style={{ borderColor: 'var(--color-danger)', color: 'var(--color-danger)' }}>{m.warnings_count}</span>
                          )}
                        </div>
                      </div>
                    ))}
                    <div className="flex items-center justify-between border border-[color:var(--color-border)] bg-[color:var(--color-bg-subtle)] px-3 py-2.5">
                      <span className="text-sm font-semibold text-[color:var(--color-text)]">Итого · {mastersTotals.done} усл.</span>
                      <span className="text-sm font-semibold" style={{ color: 'var(--color-success)' }}>{fmt(mastersTotals.salary)} ₽</span>
                    </div>
                  </div>
                  {hiddenMastersCount > 0 && (
                    <p className="pt-2.5 text-xs text-[color:var(--color-text-faint)]">+ ещё {hiddenMastersCount} — все мастера в разделе «Подробнее» выше</p>
                  )}
                </>
              )}
            </BentoCard>
          )}

          {/* business snapshot: cash on hand, outstanding receivables */}
          {(cashBalances || receivables) && (
            <div className="space-y-3">
              <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-[color:var(--color-text-faint)]">
                // Обзор бизнеса
              </div>
              <div className="grid grid-cols-2 gap-4">
                {cashBalances && (
                  <StatOrb
                    icon={Wallet}
                    label="Касса, ₽"
                    value={fmt(cashTotal)}
                    sub={topCashRegister ? `${topCashRegister.name}: ${fmt(Math.round(topCashRegister.balance))} ₽` : undefined}
                    tone="neutral"
                    to="/admin/cash-summary"
                  />
                )}
                {receivables && (
                  <StatOrb
                    icon={Receipt}
                    label="Дебиторская задолженность, ₽"
                    value={fmt(receivables.total_amount)}
                    sub={`${receivables.total_count} заказов · 30 дн.`}
                    tone={receivables.total_count > 0 ? 'warning' : 'neutral'}
                    to="/admin/receivables"
                    delay={60}
                  />
                )}
              </div>
            </div>
          )}

          {/* KPI bento: hero + secondary cells, ranked by what needs attention now */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-12">
            <div className="col-span-2 lg:col-span-5">
              <StatOrb {...heroStat} big />
            </div>
            <div className="col-span-2 grid grid-cols-1 gap-4 sm:grid-cols-3 lg:col-span-7">
              {secondaryStats.map((s, i) => (
                <StatOrb key={s.key} {...s} delay={60 * (i + 1)} />
              ))}
            </div>
          </div>

          {/* recruitment notifications */}
          {recruitNotifs && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
              <StatOrb
                icon={UserPlus}
                label="Новые отклики (24ч)"
                value={recruitNotifs.new_candidates}
                tone={recruitNotifs.new_candidates > 0 ? 'info' : 'neutral'}
                to="/admin/recruitment"
              />
              <StatOrb
                icon={ChatCircle}
                label="Сообщения hh.ru"
                value={recruitNotifs.unread_hh}
                tone={recruitNotifs.unread_hh > 0 ? 'warning' : 'neutral'}
                to="/admin/recruitment"
                delay={60}
              />
              <StatOrb
                icon={PaperPlaneTilt}
                label="Сообщения Telegram"
                value={recruitNotifs.unread_tg}
                tone={recruitNotifs.unread_tg > 0 ? 'warning' : 'neutral'}
                to="/admin/recruitment"
                delay={120}
              />
              {recruitNotifs.pending_tg_24h > 0 && (
                <StatOrb
                  icon={Clock}
                  label="Ждут TG-привязки >24ч"
                  value={recruitNotifs.pending_tg_24h}
                  tone="danger"
                  to="/admin/recruitment"
                  delay={180}
                />
              )}
            </div>
          )}

          {/* footfall */}
          {visitorSummary && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <StatOrb
                icon={Users}
                label="Посетители сегодня"
                value={fmt(visitorsToday)}
                tone="info"
                to="/admin/visitor-counters"
              />
            </div>
          )}

          {/* payouts + tasks: whichever needs action more right now leads */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
            {financeFirst ? (
              <>
                <div className="lg:col-span-7">{renderFinancePanel(0)}</div>
                <div className="lg:col-span-5">{renderTasksPanel(80)}</div>
              </>
            ) : (
              <>
                <div className="lg:col-span-7">{renderTasksPanel(0)}</div>
                <div className="lg:col-span-5">{renderFinancePanel(80)}</div>
              </>
            )}
          </div>

          {/* vacations + birthdays */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <BentoCard eyebrow="Персонал" title="Кто сейчас отсутствует" action={<GhostLink to="/admin/vacations" />}>
              {vacations.length === 0 ? (
                <Empty text="Никто не в отпуске" icon={Umbrella} />
              ) : (
                <div>
                  {vacations.map((v) => {
                    const left = daysLeft(v.end_date);
                    return (
                      <div key={v.id} className="flex items-center justify-between gap-3 border-b border-[color:var(--color-border)] py-2.5 last:border-0">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-[color:var(--color-text)]">{v.name}</div>
                          <div className="text-xs text-[color:var(--color-text-faint)]">
                            до {fmtDate(v.end_date)}
                            {left != null && left >= 0 && ` · ещё ${left} дн.`}
                          </div>
                        </div>
                        <span
                          className="shrink-0 border px-2 py-0.5 text-[11px] font-medium"
                          style={{ borderColor: VACATION_TONE[v.type] ?? 'var(--color-border)', color: VACATION_TONE[v.type] ?? 'var(--color-text-muted)' }}
                        >
                          {v.type}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </BentoCard>

            <BentoCard eyebrow="Персонал" title="Дни рождения (30 дней)" action={<GhostLink to="/admin/birthdays" />} delay={80}>
              {birthdays.length === 0 ? (
                <Empty text="Нет дней рождения в ближайшие 30 дней" icon={CalendarBlank} />
              ) : (
                <div>
                  {birthdays.slice(0, 7).map((b) => {
                    const days = daysUntilBirthday(b.birthdate);
                    return (
                      <div key={b.user_id ?? b.full_name} className="flex items-center justify-between gap-3 border-b border-[color:var(--color-border)] py-2.5 last:border-0">
                        <div className="flex items-center gap-2.5 min-w-0">
                          <CalendarBlank size={15} weight="light" className="shrink-0 text-[color:var(--color-text-faint)]" />
                          <span className="truncate text-sm text-[color:var(--color-text)]">{b.full_name}</span>
                        </div>
                        <div className="shrink-0 text-right">
                          <div className="text-xs font-medium text-[color:var(--color-text-muted)]">{fmtDate(nextBirthdayDate(b.birthdate))}</div>
                          {days != null && (
                            <div className="text-xs text-[color:var(--color-text-faint)]">{days === 0 ? 'сегодня!' : `через ${days} дн.`}</div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {birthdays.length > 7 && <p className="pt-2.5 text-xs text-[color:var(--color-text-faint)]">+ ещё {birthdays.length - 7}</p>}
                </div>
              )}
            </BentoCard>
          </div>
        </>
      )}
    </div>
  );
}
