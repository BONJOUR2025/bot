import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Wallet, CheckCircle2, Palmtree, AlertTriangle,
  ArrowRight, CalendarDays, ClipboardList, Clock,
  ListTodo, CirclePlay, RefreshCw, Scissors,
  UserPlus, MessageSquare, Send, Trophy,
} from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import Skeleton, { SkeletonCard } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';

const SALES_COLORS = { repair: '#6366f1', cosmetics: '#22c55e', shoes: '#f59e0b' };
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

const VACATION_TONE = { Отпуск: 'info', Больничный: 'warning', Командировка: 'neutral' };

// ── StatCard ──────────────────────────────────────────────────────────────────

function StatCard({ icon: Icon, label, value, sub, tone = 'primary', to }) {
  const navigate = useNavigate();
  const accent = {
    primary: '#6366f1',
    warning: '#f59e0b',
    danger:  '#ef4444',
    success: '#10b981',
    info:    '#3b82f6',
  }[tone] ?? '#6366f1';
  const iconCls = {
    primary: 'text-[color:var(--color-primary)] bg-[color:var(--color-primary-muted)]',
    warning: 'text-[color:var(--color-warning)] bg-[color:var(--color-warning-muted)]',
    danger:  'text-[color:var(--color-danger)]  bg-[color:var(--color-danger-muted)]',
    success: 'text-[color:var(--color-success)] bg-[color:var(--color-success-muted)]',
    info:    'text-[color:var(--color-info)]    bg-[color:var(--color-info-muted)]',
  }[tone] ?? '';

  return (
    <div
      onClick={to ? () => navigate(to) : undefined}
      style={{ borderLeft: `3px solid ${accent}` }}
      className={`flex items-center gap-4 rounded-2xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] p-5 shadow-sm transition-shadow duration-200 ${to ? 'cursor-pointer hover:shadow-md' : ''}`}
    >
      <div className={`rounded-xl p-3 shrink-0 ${iconCls}`}>
        <Icon size={22} />
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-bold leading-none text-[color:var(--color-text)]">{value}</div>
        <div className="mt-1 text-sm text-[color:var(--color-text-muted)]">{label}</div>
        {sub && <div className="text-xs text-[color:var(--color-text-muted)] opacity-75">{sub}</div>}
      </div>
    </div>
  );
}

// ── SectionLink ───────────────────────────────────────────────────────────────

function SectionLink({ to, label = 'Все' }) {
  const navigate = useNavigate();
  return (
    <button
      onClick={() => navigate(to)}
      className="flex items-center gap-1 text-sm font-medium text-[color:var(--color-primary)] hover:opacity-75 transition-opacity"
    >
      {label} <ArrowRight size={14} />
    </button>
  );
}

// ── TaskMini ──────────────────────────────────────────────────────────────────

function TaskRow({ icon: Icon, label, count, tone }) {
  const color = {
    danger:  'text-[color:var(--color-danger)]',
    warning: 'text-[color:var(--color-warning)]',
    info:    'text-[color:var(--color-info)]',
    neutral: 'text-[color:var(--color-text-muted)]',
  }[tone] ?? 'text-[color:var(--color-text-muted)]';

  return (
    <div className="flex items-center justify-between py-2">
      <div className={`flex items-center gap-2 text-sm ${color}`}>
        <Icon size={15} />
        <span>{label}</span>
      </div>
      <span className={`text-sm font-semibold ${color}`}>{count}</span>
    </div>
  );
}

// ── EmptyState ────────────────────────────────────────────────────────────────

function Empty({ text = 'Нет данных', icon: Icon }) {
  return (
    <div className="flex flex-col items-center gap-2 py-6 text-center text-[color:var(--color-text-muted)]">
      {Icon && <Icon size={22} className="opacity-40" />}
      <p className="text-sm">{text}</p>
    </div>
  );
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [pending, setPending]     = useState([]);
  const [approved, setApproved]   = useState([]);
  const [vacations, setVacations] = useState([]);
  const [taskStats, setTaskStats] = useState(null);
  const [birthdays, setBirthdays] = useState([]);
  const [masters, setMasters]     = useState(null);
  const [sales, setSales]         = useState(null);   // null = unavailable
  const [loading, setLoading]             = useState(true);
  const [refreshing, setRefreshing]       = useState(false);
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
        api.get('sales/daily',   { params: { date_from: today, date_to: today } }),
        api.get('recruitment/notifications'),
      ]);
      if (pendRes.status === 'fulfilled') {
        const all = pendRes.value.data ?? [];
        setPending(all.filter(p => p.status === 'Ожидает'));
        setApproved(all.filter(p => p.status === 'Одобрено'));
      }
      if (vacRes.status     === 'fulfilled') setVacations(vacRes.value.data ?? []);
      if (taskRes.status    === 'fulfilled') setTaskStats(taskRes.value.data ?? null);
      if (bdRes.status      === 'fulfilled') setBirthdays(bdRes.value.data ?? []);
      if (mastersRes.status === 'fulfilled') setMasters(mastersRes.value.data ?? null);
      if (salesRes.status   === 'fulfilled') setSales(salesRes.value.data ?? null);
      if (notifRes.status   === 'fulfilled') setRecruitNotifs(notifRes.value.data ?? null);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => { load(); }, []);

  const pendingTotal  = pending.reduce((s, p) => s + (p.amount ?? 0), 0);
  const approvedTotal = approved.reduce((s, p) => s + (p.amount ?? 0), 0);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2"><SkeletonCard /></div>
          <SkeletonCard />
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <SkeletonCard /><SkeletonCard />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <TopProgressBar active={loading} />

      {/* header */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-[color:var(--color-text)]">Дашборд</h2>
        <button
          onClick={() => load(true)}
          disabled={refreshing}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-[color:var(--color-text-muted)] hover:bg-[color:var(--color-control-bg)] transition-colors disabled:opacity-50"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard
          icon={Wallet}
          label="К одобрению"
          value={pending.length}
          sub={pending.length ? `${fmt(pendingTotal)} ₽` : undefined}
          tone="warning"
          to="/admin/payouts"
        />
        <StatCard
          icon={CheckCircle2}
          label="Одобрено, к выплате"
          value={approved.length}
          sub={approved.length ? `${fmt(approvedTotal)} ₽` : undefined}
          tone="success"
          to="/admin/payouts"
        />
        <StatCard
          icon={Palmtree}
          label="Сейчас отсутствуют"
          value={vacations.length}
          tone="info"
          to="/admin/vacations"
        />
        <StatCard
          icon={AlertTriangle}
          label="Просрочено задач"
          value={taskStats?.overdue ?? '—'}
          sub={taskStats?.due_today ? `Сегодня: ${taskStats.due_today}` : undefined}
          tone={taskStats?.overdue > 0 ? 'danger' : 'neutral'}
          to="/admin/tasks"
        />
      </div>

      {/* recruitment notifications */}
      {recruitNotifs && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <StatCard
            icon={UserPlus}
            label="Новые отклики (24ч)"
            value={recruitNotifs.new_candidates}
            tone={recruitNotifs.new_candidates > 0 ? 'info' : 'neutral'}
            to="/admin/recruitment"
          />
          <StatCard
            icon={MessageSquare}
            label="Новые сообщения hh.ru"
            value={recruitNotifs.unread_hh}
            tone={recruitNotifs.unread_hh > 0 ? 'warning' : 'neutral'}
            to="/admin/recruitment"
          />
          <StatCard
            icon={Send}
            label="Новые сообщения Telegram"
            value={recruitNotifs.unread_tg}
            tone={recruitNotifs.unread_tg > 0 ? 'warning' : 'neutral'}
            to="/admin/recruitment"
          />
          {recruitNotifs.pending_tg_24h > 0 && (
            <StatCard
              icon={Clock}
              label="Ждут TG-привязки >24ч"
              value={recruitNotifs.pending_tg_24h}
              tone="danger"
              to="/admin/recruitment"
            />
          )}
        </div>
      )}

      {/* middle row: payouts + tasks */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">

        {/* pending payouts */}
        <Card
          className="lg:col-span-2"
          title="Ожидают выплаты"
          actions={<SectionLink to="/admin/payouts" />}
        >
          {pending.length === 0 ? (
            <Empty text="Нет запросов на выплату" icon={Wallet} />
          ) : (
            <div className="divide-y divide-[color:var(--color-border)]">
              {pending.slice(0, 7).map((p) => (
                <div key={p.id} className="flex items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-[color:var(--color-text)]">
                      {p.name}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 text-xs text-[color:var(--color-text-muted)]">
                      <span>{p.payout_type}</span>
                      <span>·</span>
                      <span>{p.method}</span>
                      <span>·</span>
                      <span>{fmtTs(p.timestamp)}</span>
                    </div>
                  </div>
                  <span className="shrink-0 text-sm font-semibold text-[color:var(--color-primary)]">
                    {fmt(p.amount)} ₽
                  </span>
                </div>
              ))}
              {pending.length > 7 && (
                <p className="pt-2.5 text-xs text-[color:var(--color-text-muted)]">
                  + ещё {pending.length - 7}
                </p>
              )}
            </div>
          )}
        </Card>

        {/* task stats */}
        <Card
          title="Задачи"
          actions={<SectionLink to="/admin/tasks" />}
        >
          {!taskStats ? (
            <Empty text="Нет данных по задачам" icon={ListTodo} />
          ) : (
            <div className="divide-y divide-[color:var(--color-border)]">
              <TaskRow icon={AlertTriangle} label="Просрочено"  count={taskStats.overdue}       tone="danger" />
              <TaskRow icon={Clock}         label="Сегодня"      count={taskStats.due_today}     tone="warning" />
              <TaskRow icon={CirclePlay}    label="В работе"     count={taskStats.in_progress}   tone="info" />
              <TaskRow icon={ListTodo}      label="В очереди"    count={taskStats.todo}          tone="neutral" />
              <div className="flex items-center justify-between pt-2 text-xs text-[color:var(--color-text-muted)]">
                <span>Всего активных</span>
                <span className="font-medium">{(taskStats.todo ?? 0) + (taskStats.in_progress ?? 0)}</span>
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* bottom row: vacations + birthdays */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">

        {/* vacations */}
        <Card
          title="Кто сейчас отсутствует"
          actions={<SectionLink to="/admin/vacations" />}
        >
          {vacations.length === 0 ? (
            <Empty text="Никто не в отпуске" icon={Palmtree} />
          ) : (
            <div className="divide-y divide-[color:var(--color-border)]">
              {vacations.map((v) => {
                const left = daysLeft(v.end_date);
                return (
                  <div key={v.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-[color:var(--color-text)]">
                        {v.name}
                      </div>
                      <div className="text-xs text-[color:var(--color-text-muted)]">
                        до {fmtDate(v.end_date)}
                        {left != null && left >= 0 && ` · ещё ${left} дн.`}
                      </div>
                    </div>
                    <Badge tone={VACATION_TONE[v.type] ?? 'neutral'}>{v.type}</Badge>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* birthdays */}
        <Card
          title="Дни рождения (30 дней)"
          actions={<SectionLink to="/admin/birthdays" />}
        >
          {birthdays.length === 0 ? (
            <Empty text="Нет дней рождения в ближайшие 30 дней" icon={CalendarDays} />
          ) : (
            <div className="divide-y divide-[color:var(--color-border)]">
              {birthdays.slice(0, 7).map((b) => {
                const days = daysUntilBirthday(b.birthdate);
                return (
                  <div key={b.user_id ?? b.full_name} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="flex items-center gap-2.5">
                      <CalendarDays size={15} className="shrink-0 text-[color:var(--color-text-muted)]" />
                      <span className="text-sm text-[color:var(--color-text)]">{b.full_name}</span>
                    </div>
                    <div className="shrink-0 text-right">
                      <div className="text-xs font-medium text-[color:var(--color-text-muted)]">
                        {fmtDate(nextBirthdayDate(b.birthdate))}
                      </div>
                      {days != null && (
                        <div className="text-xs text-[color:var(--color-text-muted)] opacity-75">
                          {days === 0 ? '🎂 сегодня!' : `через ${days} дн.`}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
              {birthdays.length > 7 && (
                <p className="pt-2.5 text-xs text-[color:var(--color-text-muted)]">+ ещё {birthdays.length - 7}</p>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* sales today */}
      {sales !== null && (
        <Card
          title="Продажи сегодня"
          actions={<SectionLink to="/admin/sales" label="Подробнее" />}
        >
          {!sales.length ? (
            <Empty text="Нет данных по продажам за сегодня" icon={Scissors} />
          ) : (() => {
            // aggregate by employee (description)
            const byEmp = {};
            for (const r of sales) {
              const key = r.description || r.code || '—';
              if (!byEmp[key]) byEmp[key] = { description: key, repair: 0, cosmetics: 0, shoes: 0 };
              byEmp[key].repair    += r.repair    ?? 0;
              byEmp[key].cosmetics += r.cosmetics ?? 0;
              byEmp[key].shoes     += r.shoes     ?? 0;
            }
            const rows = Object.values(byEmp).sort((a, b) => {
              const ta = a.repair + a.cosmetics + a.shoes;
              const tb = b.repair + b.cosmetics + b.shoes;
              return tb - ta;
            });
            const totRepair    = rows.reduce((s, r) => s + r.repair, 0);
            const totCosmetics = rows.reduce((s, r) => s + r.cosmetics, 0);
            const totShoes     = rows.reduce((s, r) => s + r.shoes, 0);
            const totTotal     = totRepair + totCosmetics + totShoes;
            const hiddenSalesCount = Math.max(0, rows.length - 5);
            const salesRows = [
              ...rows.slice(0, 5),
              { description: 'Итого', repair: totRepair, cosmetics: totCosmetics, shoes: totShoes, isTotal: true },
            ];
            const salesDonut = [
              { key: 'repair', value: totRepair },
              { key: 'cosmetics', value: totCosmetics },
              { key: 'shoes', value: totShoes },
            ].filter((d) => d.value > 0);
            return (
              <>
              {salesDonut.length > 0 && (
                <div className="flex items-center gap-4 pb-4 mb-4 border-b border-[color:var(--color-border)]">
                  <div style={{ width: 76, height: 76, flexShrink: 0 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={salesDonut} dataKey="value" nameKey="key" innerRadius="55%" outerRadius="90%" paddingAngle={2} isAnimationActive={false}>
                          {salesDonut.map((d) => <Cell key={d.key} fill={SALES_COLORS[d.key]} stroke="none" />)}
                        </Pie>
                        <Tooltip formatter={(v, n, p) => [`${fmt(v)} ₽`, SALES_LABELS[p.payload.key]]} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="flex-1 flex flex-wrap gap-x-5 gap-y-1.5">
                    {salesDonut.map((d) => (
                      <div key={d.key} className="flex items-center gap-1.5 text-xs">
                        <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: SALES_COLORS[d.key] }} />
                        <span className="text-[color:var(--color-text-muted)]">{SALES_LABELS[d.key]}</span>
                        <span className="font-semibold">{fmt(d.value)} ₽</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <ResponsiveTable
                data={salesRows}
                keyFn={(r) => r.description}
                rowClass={(r) => (r.isTotal ? 'font-semibold' : '')}
                emptyText="Нет данных по продажам за сегодня"
                columns={[
                  {
                    label: 'Сотрудник',
                    primary: true,
                    headerClass: 'pl-6',
                    cellClass: 'pl-6 font-medium',
                    render: (r) => (
                      <span style={{ color: r.isTotal ? 'var(--color-text-muted)' : 'var(--color-text)' }}>
                        {r.description}
                      </span>
                    ),
                  },
                  {
                    label: 'Ремонт',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (r) => (
                      <span style={{ color: 'var(--color-text-muted)' }}>
                        {r.isTotal ? `${fmt(r.repair)} ₽` : (r.repair ? fmt(r.repair) + ' ₽' : '—')}
                      </span>
                    ),
                  },
                  {
                    label: 'Косметика',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (r) => (
                      <span style={{ color: 'var(--color-text-muted)' }}>
                        {r.isTotal ? `${fmt(r.cosmetics)} ₽` : (r.cosmetics ? fmt(r.cosmetics) + ' ₽' : '—')}
                      </span>
                    ),
                  },
                  {
                    label: 'Обувь',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (r) => (
                      <span style={{ color: 'var(--color-text-muted)' }}>
                        {r.isTotal ? `${fmt(r.shoes)} ₽` : (r.shoes ? fmt(r.shoes) + ' ₽' : '—')}
                      </span>
                    ),
                  },
                  {
                    label: 'Итого',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (r) => {
                      const total = r.isTotal ? totTotal : r.repair + r.cosmetics + r.shoes;
                      return (
                        <span className="font-semibold" style={{ color: 'var(--color-primary)' }}>
                          {fmt(total)} ₽
                        </span>
                      );
                    },
                  },
                ]}
              />
              {hiddenSalesCount > 0 && (
                <p className="pt-2.5 text-xs text-[color:var(--color-text-muted)]">
                  + ещё {hiddenSalesCount} — все продажи в разделе «Подробнее» выше
                </p>
              )}
              </>
            );
          })()}
        </Card>
      )}

      {/* masters today */}
      {masters !== null && (
        <Card
          title="Мастера сегодня"
          actions={<SectionLink to="/admin/masters" label="Подробнее" />}
        >
          {!masters.salary_summary?.length ? (
            <Empty text="Нет данных по мастерам за сегодня" icon={Trophy} />
          ) : (() => {
            const rows = masters.salary_summary;
            const totKredit = rows.reduce((s, r) => s + (r.total_kredit ?? 0), 0);
            const totSalary = rows.reduce((s, r) => s + (r.total_salary ?? 0), 0);
            const totDone   = rows.reduce((s, r) => s + (r.services_done ?? 0), 0);
            const totWarn   = rows.reduce((s, r) => s + (r.warnings_count ?? 0), 0);
            const topMasters = [...rows].sort((a, b) => (b.total_kredit ?? 0) - (a.total_kredit ?? 0)).slice(0, 5);
            const hiddenMastersCount = Math.max(0, rows.length - 5);
            const masterRows = [
              ...topMasters,
              {
                master: 'Итого',
                services_done: totDone,
                total_kredit: totKredit,
                total_salary: totSalary,
                warnings_count: totWarn,
                isTotal: true,
              },
            ];
            const maxKredit = Math.max(1, ...topMasters.map((m) => m.total_kredit ?? 0));
            return (
              <>
              {topMasters.length > 0 && (
                <div className="pb-4 mb-4 border-b border-[color:var(--color-border)] space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-medium text-[color:var(--color-text-muted)] mb-1">
                    <Trophy size={13} /> Топ по выручке
                  </div>
                  {topMasters.map((m, i) => {
                    const pct = maxKredit > 0 ? ((m.total_kredit ?? 0) / maxKredit) * 100 : 0;
                    return (
                      <div key={m.master} className="flex items-center gap-2">
                        <span className="text-xs w-24 truncate shrink-0 text-[color:var(--color-text)]">{m.master}</span>
                        <div className="flex-1 h-2 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: '#6366f1' }} />
                        </div>
                        <span className="text-xs font-semibold w-20 text-right shrink-0">{fmt(m.total_kredit)} ₽</span>
                      </div>
                    );
                  })}
                </div>
              )}
              <ResponsiveTable
                data={masterRows}
                keyFn={(m) => m.master}
                rowClass={(m) => (m.isTotal ? 'font-semibold' : '')}
                emptyText="Нет данных по мастерам за сегодня"
                columns={[
                  {
                    label: 'Мастер',
                    primary: true,
                    headerClass: 'pl-6',
                    cellClass: 'pl-6 font-medium',
                    render: (m) => (
                      <span style={{ color: m.isTotal ? 'var(--color-text-muted)' : 'var(--color-text)' }}>
                        {m.master}
                      </span>
                    ),
                  },
                  {
                    label: 'Услуг',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (m) => (
                      <span style={{ color: m.isTotal ? undefined : 'var(--color-text-muted)' }}>
                        {m.services_done}
                      </span>
                    ),
                  },
                  {
                    label: 'Выручка',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (m) => <span>{fmt(m.total_kredit)} ₽</span>,
                  },
                  {
                    label: 'ЗП мастера',
                    headerClass: 'text-right',
                    cellClass: 'text-right',
                    render: (m) => (
                      <span className="font-semibold" style={{ color: 'var(--color-success)' }}>
                        {fmt(m.total_salary)} ₽
                      </span>
                    ),
                  },
                  {
                    label: '⚠️',
                    headerClass: 'text-center',
                    cellClass: 'text-center',
                    render: (m) =>
                      m.warnings_count > 0 ? (
                        <Badge tone="danger">{m.warnings_count}</Badge>
                      ) : m.isTotal ? (
                        '—'
                      ) : (
                        <span className="text-[color:var(--color-text-muted)] opacity-40">—</span>
                      ),
                  },
                ]}
              />
              {hiddenMastersCount > 0 && (
                <p className="pt-2.5 text-xs text-[color:var(--color-text-muted)]">
                  + ещё {hiddenMastersCount} — все мастера в разделе «Подробнее» выше
                </p>
              )}
              </>
            );
          })()}
        </Card>
      )}

    </div>
  );
}
