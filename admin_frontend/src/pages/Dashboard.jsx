import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wallet, CheckCircle, Umbrella, Warning, ArrowUpRight,
  CalendarBlank, Clock, ListChecks, PlayCircle, ArrowsClockwise,
  Scissors, UserPlus, ChatCircle, PaperPlaneTilt, Trophy, Sparkle,
} from '@phosphor-icons/react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';

const SALES_COLORS = { repair: '#818cf8', cosmetics: '#34d399', shoes: '#fbbf24' };
const SALES_LABELS = { repair: 'Ремонт', cosmetics: 'Косметика', shoes: 'Обувь' };
const FONT_LINK_ID = 'dashboard-v2-fonts';
const DISPLAY_FONT = "'Space Grotesk', 'Plus Jakarta Sans', sans-serif";
const BODY_FONT = "'Plus Jakarta Sans', sans-serif";

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

const VACATION_TONE = { Отпуск: '#38bdf8', Больничный: '#fbbf24', Командировка: 'rgba(255,255,255,0.4)' };

// ── one-time font injection (scoped to this page only) ──────────────────────

function useDashboardFonts() {
  useEffect(() => {
    if (document.getElementById(FONT_LINK_ID)) return;
    const pre1 = document.createElement('link');
    pre1.rel = 'preconnect';
    pre1.href = 'https://fonts.googleapis.com';
    const pre2 = document.createElement('link');
    pre2.rel = 'preconnect';
    pre2.href = 'https://fonts.gstatic.com';
    pre2.crossOrigin = 'anonymous';
    const sheet = document.createElement('link');
    sheet.id = FONT_LINK_ID;
    sheet.rel = 'stylesheet';
    sheet.href = 'https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap';
    document.head.append(pre1, pre2, sheet);
  }, []);
}

// ── scroll-reveal primitive (IntersectionObserver, transform+opacity only) ──

function useReveal() {
  const ref = useRef(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          io.disconnect();
        }
      },
      { threshold: 0.12 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return [ref, visible];
}

function Reveal({ className = '', delay = 0, children }) {
  const [ref, visible] = useReveal();
  return (
    <div
      ref={ref}
      className={`transition-all duration-[900ms] ease-[cubic-bezier(0.32,0.72,0,1)] ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'} ${className}`}
      style={{ transitionDelay: visible ? `${delay}ms` : '0ms' }}
    >
      {children}
    </div>
  );
}

// ── Double-Bezel glass shell ─────────────────────────────────────────────────

function GlassShell({ className = '', innerClassName = '', children }) {
  return (
    <div className={`rounded-[2rem] bg-white/[0.03] ring-1 ring-white/10 p-1.5 ${className}`}>
      <div
        className={`h-full rounded-[calc(2rem-0.375rem)] bg-white/[0.035] shadow-[inset_0_1px_1px_rgba(255,255,255,0.08)] ${innerClassName}`}
      >
        {children}
      </div>
    </div>
  );
}

function BentoCard({ span = '', eyebrow, eyebrowIcon: EyebrowIcon, title, action, delay = 0, children }) {
  return (
    <Reveal delay={delay} className={span}>
      <GlassShell className="h-full">
        <div className="flex h-full flex-col p-6 sm:p-7">
          {(title || action || eyebrow) && (
            <div className="mb-5 flex items-start justify-between gap-3">
              <div>
                {eyebrow && (
                  <div className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-3 py-1 text-[10px] font-medium uppercase tracking-[0.2em] text-white/45">
                    {EyebrowIcon && <EyebrowIcon size={11} weight="light" />}
                    {eyebrow}
                  </div>
                )}
                {title && (
                  <h3 className="text-lg font-semibold text-white/90" style={{ fontFamily: DISPLAY_FONT }}>
                    {title}
                  </h3>
                )}
              </div>
              {action}
            </div>
          )}
          <div className="flex-1">{children}</div>
        </div>
      </GlassShell>
    </Reveal>
  );
}

// ── nested-icon ghost link ("see all") ───────────────────────────────────────

function GhostLink({ to, label = 'Все' }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(to)}
      className="group inline-flex shrink-0 items-center gap-2 text-xs font-medium text-white/45 transition-colors duration-300 hover:text-white/90"
    >
      {label}
      <span className="grid h-5 w-5 place-items-center rounded-full bg-white/[0.06] transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:translate-x-0.5 group-hover:bg-white/[0.14]">
        <ArrowUpRight size={11} weight="light" />
      </span>
    </button>
  );
}

// ── island refresh button (button-in-button) ─────────────────────────────────

function IslandButton({ onClick, disabled, spinning, children }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="group inline-flex items-center gap-3 rounded-full bg-white/[0.06] py-1.5 pl-5 pr-1.5 text-sm font-medium text-white/75 ring-1 ring-white/10 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] hover:bg-white/[0.1] hover:ring-white/20 active:scale-[0.98] disabled:opacity-40"
    >
      {children}
      <span className="grid h-8 w-8 place-items-center rounded-full bg-white/[0.08] transition-transform duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:-translate-y-px group-hover:translate-x-0.5 group-hover:scale-105">
        <ArrowsClockwise size={15} weight="light" className={spinning ? 'animate-spin' : ''} />
      </span>
    </button>
  );
}

// ── KPI orb (bento cell) ─────────────────────────────────────────────────────

function StatOrb({ icon: Icon, label, value, sub, tone = 'primary', to, big = false, delay = 0 }) {
  const navigate = useNavigate();
  const toneColor = {
    primary: '#a5b4fc',
    warning: '#fbbf24',
    danger: '#f87171',
    success: '#34d399',
    info: '#38bdf8',
    neutral: 'rgba(255,255,255,0.55)',
  }[tone];

  return (
    <Reveal delay={delay} className="h-full">
      <button
        type="button"
        onClick={to ? () => navigate(to) : undefined}
        className={`group h-full w-full rounded-[1.75rem] bg-white/[0.03] p-1.5 text-left ring-1 ring-white/10 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] ${
          to ? 'cursor-pointer hover:bg-white/[0.05] hover:ring-white/20 active:scale-[0.99]' : 'cursor-default'
        }`}
      >
        <div
          className={`flex h-full flex-col justify-between gap-5 rounded-[calc(1.75rem-0.375rem)] bg-white/[0.03] shadow-[inset_0_1px_1px_rgba(255,255,255,0.06)] ${
            big ? 'p-7' : 'p-5'
          }`}
        >
          <div className="flex items-center justify-between">
            <div
              className="grid h-10 w-10 place-items-center rounded-2xl bg-white/[0.06] ring-1 ring-white/10"
              style={{ color: toneColor }}
            >
              <Icon size={18} weight="light" />
            </div>
            {to && (
              <ArrowUpRight
                size={14}
                weight="light"
                className="text-white/15 transition-all duration-500 ease-[cubic-bezier(0.32,0.72,0,1)] group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-white/50"
              />
            )}
          </div>
          <div>
            <div
              className={`${big ? 'text-4xl' : 'text-3xl'} font-semibold leading-none text-white`}
              style={{ fontFamily: DISPLAY_FONT }}
            >
              {value}
            </div>
            <div className="mt-2 text-sm text-white/50">{label}</div>
            {sub && <div className="mt-0.5 text-xs text-white/25">{sub}</div>}
          </div>
        </div>
      </button>
    </Reveal>
  );
}

// ── task queue row ────────────────────────────────────────────────────────────

function TaskRow({ icon: Icon, label, count, tone }) {
  const color = {
    danger: '#f87171',
    warning: '#fbbf24',
    info: '#38bdf8',
    neutral: 'rgba(255,255,255,0.45)',
  }[tone];
  return (
    <div className="flex items-center justify-between border-b border-white/[0.06] py-3 last:border-0">
      <div className="flex items-center gap-2.5 text-sm text-white/60">
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

function Empty({ text = 'Нет данных', icon: Icon }) {
  return (
    <div className="flex flex-col items-center gap-3 py-8 text-center">
      {Icon && (
        <div className="grid h-11 w-11 place-items-center rounded-2xl bg-white/[0.05] text-white/25">
          <Icon size={20} weight="light" />
        </div>
      )}
      <p className="text-sm text-white/35">{text}</p>
    </div>
  );
}

// ── loading skeleton (bespoke, matches the glass canvas) ─────────────────────

function SkeletonBento({ span = '', h = 'h-40' }) {
  return (
    <div className={span}>
      <div className="rounded-[2rem] bg-white/[0.03] p-1.5 ring-1 ring-white/10">
        <div className={`${h} animate-pulse rounded-[calc(2rem-0.375rem)] bg-white/[0.04]`} />
      </div>
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  useDashboardFonts();

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

  async function load(silent = false) {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const today = new Date().toISOString().slice(0, 10);
      const [pendRes, vacRes, taskRes, bdRes, mastersRes, salesRes, notifRes] = await Promise.allSettled([
        api.get('payouts/active'),
        api.get('vacations/active'),
        api.get('tasks/stats'),
        api.get('birthdays/', { params: { days: 30 } }),
        api.get('masters/works', { params: { date_from: today, date_to: today } }),
        api.get('sales/daily', { params: { date_from: today, date_to: today } }),
        api.get('recruitment/notifications'),
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
      if (salesRes.status === 'fulfilled') setSales(salesRes.value.data ?? null);
      if (notifRes.status === 'fulfilled') setRecruitNotifs(notifRes.value.data ?? null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const pendingTotal = pending.reduce((s, p) => s + (p.amount ?? 0), 0);
  const approvedTotal = approved.reduce((s, p) => s + (p.amount ?? 0), 0);
  const today = new Date().toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', weekday: 'long' });

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
      background: 'rgba(18,18,22,0.95)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 12,
      fontSize: 12,
      color: '#fff',
    },
    itemStyle: { color: '#fff' },
    labelStyle: { color: 'rgba(255,255,255,0.6)' },
  };

  return (
    <div
      className="relative isolate -mx-2.5 overflow-hidden rounded-[2rem] px-5 py-8 sm:-mx-3.5 sm:px-8 sm:py-10 lg:mx-0 lg:rounded-[2.5rem] lg:px-10 lg:py-12"
      style={{
        background: '#08080b',
        fontFamily: BODY_FONT,
        backgroundImage:
          'radial-gradient(circle at 15% 8%, rgba(99,102,241,0.16), transparent 42%), radial-gradient(circle at 88% 18%, rgba(52,211,153,0.10), transparent 38%), radial-gradient(circle at 50% 100%, rgba(139,92,246,0.10), transparent 45%)',
      }}
    >
      {/* noise texture — static, non-scrolling decorative layer only */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.035]"
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
        }}
      />

      <div className="relative space-y-6 sm:space-y-8">
        {/* header */}
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-3 py-1 text-[10px] font-medium uppercase tracking-[0.2em] text-white/45">
              <Sparkle size={11} weight="light" />
              Дашборд · {today}
            </div>
            <h1 className="text-3xl font-semibold text-white sm:text-4xl" style={{ fontFamily: DISPLAY_FONT }}>
              {greeting()}, Nick
            </h1>
          </div>
          <IslandButton onClick={() => load(true)} disabled={refreshing} spinning={refreshing}>
            Обновить
          </IslandButton>
        </div>

        {loading ? (
          <div className="space-y-6">
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
            {/* KPI bento: one hero orb + three secondary */}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-12">
              <div className="col-span-2 lg:col-span-5">
                <StatOrb
                  icon={Wallet}
                  label="Ожидают одобрения выплаты"
                  value={pending.length}
                  sub={pending.length ? `${fmt(pendingTotal)} ₽ к согласованию` : 'Пусто — можно выдохнуть'}
                  tone="warning"
                  to="/admin/payouts"
                  big
                />
              </div>
              <div className="col-span-2 grid grid-cols-1 gap-4 sm:grid-cols-3 lg:col-span-7">
                <StatOrb
                  icon={CheckCircle}
                  label="Одобрено, к выплате"
                  value={approved.length}
                  sub={approved.length ? `${fmt(approvedTotal)} ₽` : undefined}
                  tone="success"
                  to="/admin/payouts"
                  delay={60}
                />
                <StatOrb
                  icon={Umbrella}
                  label="Сейчас отсутствуют"
                  value={vacations.length}
                  tone="info"
                  to="/admin/vacations"
                  delay={120}
                />
                <StatOrb
                  icon={Warning}
                  label="Просрочено задач"
                  value={taskStats?.overdue ?? '—'}
                  sub={taskStats?.due_today ? `Сегодня: ${taskStats.due_today}` : undefined}
                  tone={taskStats?.overdue > 0 ? 'danger' : 'neutral'}
                  to="/admin/tasks"
                  delay={180}
                />
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

            {/* payouts + tasks */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
              <div className="lg:col-span-7">
                <BentoCard
                  eyebrow="Финансы"
                  eyebrowIcon={Wallet}
                  title="Ожидают выплаты"
                  action={<GhostLink to="/admin/payouts" />}
                >
                  {pending.length === 0 ? (
                    <Empty text="Нет запросов на выплату" icon={Wallet} />
                  ) : (
                    <div>
                      {pending.slice(0, 7).map((p) => (
                        <div key={p.id} className="flex items-center justify-between gap-3 border-b border-white/[0.06] py-3 last:border-0">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-white/85">{p.name}</div>
                            <div className="flex flex-wrap items-center gap-x-2 text-xs text-white/35">
                              <span>{p.payout_type}</span>
                              <span>·</span>
                              <span>{p.method}</span>
                              <span>·</span>
                              <span>{fmtTs(p.timestamp)}</span>
                            </div>
                          </div>
                          <span className="shrink-0 text-sm font-semibold text-white/90">{fmt(p.amount)} ₽</span>
                        </div>
                      ))}
                      {pending.length > 7 && (
                        <p className="pt-3 text-xs text-white/30">+ ещё {pending.length - 7}</p>
                      )}
                    </div>
                  )}
                </BentoCard>
              </div>

              <div className="lg:col-span-5">
                <BentoCard eyebrow="Коммуникации" eyebrowIcon={ListChecks} title="Задачи" action={<GhostLink to="/admin/tasks" />} delay={80}>
                  {!taskStats ? (
                    <Empty text="Нет данных по задачам" icon={ListChecks} />
                  ) : (
                    <div>
                      <TaskRow icon={Warning} label="Просрочено" count={taskStats.overdue} tone="danger" />
                      <TaskRow icon={Clock} label="Сегодня" count={taskStats.due_today} tone="warning" />
                      <TaskRow icon={PlayCircle} label="В работе" count={taskStats.in_progress} tone="info" />
                      <TaskRow icon={ListChecks} label="В очереди" count={taskStats.todo} tone="neutral" />
                      <div className="flex items-center justify-between pt-3 text-xs text-white/35">
                        <span>Всего активных</span>
                        <span className="font-medium text-white/60">{(taskStats.todo ?? 0) + (taskStats.in_progress ?? 0)}</span>
                      </div>
                    </div>
                  )}
                </BentoCard>
              </div>
            </div>

            {/* vacations + birthdays */}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <BentoCard eyebrow="Персонал" eyebrowIcon={Umbrella} title="Кто сейчас отсутствует" action={<GhostLink to="/admin/vacations" />}>
                {vacations.length === 0 ? (
                  <Empty text="Никто не в отпуске" icon={Umbrella} />
                ) : (
                  <div>
                    {vacations.map((v) => {
                      const left = daysLeft(v.end_date);
                      return (
                        <div key={v.id} className="flex items-center justify-between gap-3 border-b border-white/[0.06] py-3 last:border-0">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-white/85">{v.name}</div>
                            <div className="text-xs text-white/35">
                              до {fmtDate(v.end_date)}
                              {left != null && left >= 0 && ` · ещё ${left} дн.`}
                            </div>
                          </div>
                          <span
                            className="shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium"
                            style={{ background: 'rgba(255,255,255,0.06)', color: VACATION_TONE[v.type] ?? 'rgba(255,255,255,0.5)' }}
                          >
                            {v.type}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </BentoCard>

              <BentoCard eyebrow="Персонал" eyebrowIcon={CalendarBlank} title="Дни рождения (30 дней)" action={<GhostLink to="/admin/birthdays" />} delay={80}>
                {birthdays.length === 0 ? (
                  <Empty text="Нет дней рождения в ближайшие 30 дней" icon={CalendarBlank} />
                ) : (
                  <div>
                    {birthdays.slice(0, 7).map((b) => {
                      const days = daysUntilBirthday(b.birthdate);
                      return (
                        <div key={b.user_id ?? b.full_name} className="flex items-center justify-between gap-3 border-b border-white/[0.06] py-3 last:border-0">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <CalendarBlank size={15} weight="light" className="shrink-0 text-white/30" />
                            <span className="truncate text-sm text-white/85">{b.full_name}</span>
                          </div>
                          <div className="shrink-0 text-right">
                            <div className="text-xs font-medium text-white/45">{fmtDate(nextBirthdayDate(b.birthdate))}</div>
                            {days != null && (
                              <div className="text-xs text-white/25">{days === 0 ? '🎂 сегодня!' : `через ${days} дн.`}</div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                    {birthdays.length > 7 && <p className="pt-3 text-xs text-white/30">+ ещё {birthdays.length - 7}</p>}
                  </div>
                )}
              </BentoCard>
            </div>

            {/* sales today */}
            {sales !== null && (
              <BentoCard eyebrow="Продажи" eyebrowIcon={Scissors} title="Продажи сегодня" action={<GhostLink to="/admin/sales" label="Подробнее" />}>
                {!sales.length ? (
                  <Empty text="Нет данных по продажам за сегодня" icon={Scissors} />
                ) : (
                  <>
                    {salesDonut.length > 0 && (
                      <div className="mb-5 flex items-center gap-5 border-b border-white/[0.06] pb-5">
                        <div style={{ width: 84, height: 84, flexShrink: 0 }}>
                          <ResponsiveContainer width="100%" height="100%">
                            <PieChart>
                              <Pie data={salesDonut} dataKey="value" nameKey="key" innerRadius="58%" outerRadius="92%" paddingAngle={3} isAnimationActive={false}>
                                {salesDonut.map((d) => (
                                  <Cell key={d.key} fill={SALES_COLORS[d.key]} stroke="none" />
                                ))}
                              </Pie>
                              <Tooltip formatter={(v, n, p) => [`${fmt(v)} ₽`, SALES_LABELS[p.payload.key]]} {...tooltipStyle} />
                            </PieChart>
                          </ResponsiveContainer>
                        </div>
                        <div className="flex flex-1 flex-wrap gap-x-5 gap-y-2">
                          {salesDonut.map((d) => (
                            <div key={d.key} className="flex items-center gap-2 text-xs">
                              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: SALES_COLORS[d.key] }} />
                              <span className="text-white/40">{SALES_LABELS[d.key]}</span>
                              <span className="font-semibold text-white/85">{fmt(d.value)} ₽</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="space-y-2">
                      {salesRows.map((r) => {
                        const total = r.repair + r.cosmetics + r.shoes;
                        return (
                          <div key={r.description} className="flex items-center justify-between gap-3 rounded-2xl bg-white/[0.025] px-4 py-3">
                            <span className="min-w-0 truncate text-sm font-medium text-white/80">{r.description}</span>
                            <div className="flex shrink-0 items-center gap-4 text-xs text-white/35">
                              <span>Р {r.repair ? fmt(r.repair) : '—'}</span>
                              <span>К {r.cosmetics ? fmt(r.cosmetics) : '—'}</span>
                              <span>О {r.shoes ? fmt(r.shoes) : '—'}</span>
                              <span className="font-semibold text-white/85">{fmt(total)} ₽</span>
                            </div>
                          </div>
                        );
                      })}
                      <div className="flex items-center justify-between rounded-2xl bg-white/[0.05] px-4 py-3 ring-1 ring-white/10">
                        <span className="text-sm font-semibold text-white/85">Итого</span>
                        <span className="text-sm font-semibold text-white">{fmt(totTotal)} ₽</span>
                      </div>
                    </div>
                    {hiddenSalesCount > 0 && (
                      <p className="pt-3 text-xs text-white/30">+ ещё {hiddenSalesCount} — все продажи в разделе «Подробнее» выше</p>
                    )}
                  </>
                )}
              </BentoCard>
            )}

            {/* masters today */}
            {masters !== null && (
              <BentoCard eyebrow="Мастера" eyebrowIcon={Trophy} title="Мастера сегодня" action={<GhostLink to="/admin/masters" label="Подробнее" />} delay={80}>
                {!masters.salary_summary?.length ? (
                  <Empty text="Нет данных по мастерам за сегодня" icon={Trophy} />
                ) : (
                  <>
                    {topMasters.length > 0 && (
                      <div className="mb-5 space-y-2.5 border-b border-white/[0.06] pb-5">
                        <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-white/40">
                          <Trophy size={13} weight="light" /> Топ по выручке
                        </div>
                        {topMasters.map((m) => {
                          const pct = maxKredit > 0 ? ((m.total_kredit ?? 0) / maxKredit) * 100 : 0;
                          return (
                            <div key={m.master} className="flex items-center gap-3">
                              <span className="w-24 shrink-0 truncate text-xs text-white/70">{m.master}</span>
                              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
                                <div
                                  className="h-full rounded-full transition-[width] duration-700 ease-[cubic-bezier(0.32,0.72,0,1)]"
                                  style={{ width: `${pct}%`, background: 'linear-gradient(90deg,#818cf8,#a78bfa)' }}
                                />
                              </div>
                              <span className="w-20 shrink-0 text-right text-xs font-semibold text-white/85">{fmt(m.total_kredit)} ₽</span>
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <div className="space-y-2">
                      {topMasters.map((m) => (
                        <div key={m.master} className="flex items-center justify-between gap-3 rounded-2xl bg-white/[0.025] px-4 py-3">
                          <span className="min-w-0 truncate text-sm font-medium text-white/80">{m.master}</span>
                          <div className="flex shrink-0 items-center gap-4 text-xs text-white/35">
                            <span>{m.services_done} усл.</span>
                            <span className="font-semibold text-white/70">{fmt(m.total_kredit)} ₽</span>
                            <span className="font-semibold" style={{ color: '#34d399' }}>{fmt(m.total_salary)} ₽</span>
                            {m.warnings_count > 0 && (
                              <span className="rounded-full bg-red-400/10 px-2 py-0.5 font-semibold text-red-400">{m.warnings_count}</span>
                            )}
                          </div>
                        </div>
                      ))}
                      <div className="flex items-center justify-between rounded-2xl bg-white/[0.05] px-4 py-3 ring-1 ring-white/10">
                        <span className="text-sm font-semibold text-white/85">Итого · {mastersTotals.done} усл.</span>
                        <span className="text-sm font-semibold" style={{ color: '#34d399' }}>{fmt(mastersTotals.salary)} ₽</span>
                      </div>
                    </div>
                    {hiddenMastersCount > 0 && (
                      <p className="pt-3 text-xs text-white/30">+ ещё {hiddenMastersCount} — все мастера в разделе «Подробнее» выше</p>
                    )}
                  </>
                )}
              </BentoCard>
            )}
          </>
        )}
      </div>
    </div>
  );
}
