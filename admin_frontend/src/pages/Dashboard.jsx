import {
  ArrowDownRight,
  ArrowUpRight,
  BadgeCheck,
  CalendarDays,
  Clock3,
  Crown,
  Gift,
  Sparkles,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import api from '../api';
import Card from '../components/ui/Card';

const palette = ['#4f46e5', '#22c55e', '#f97316', '#0ea5e9', '#a855f7', '#f43f5e'];

export default function Dashboard() {
  const [employees, setEmployees] = useState([]);
  const [archivedEmployees, setArchivedEmployees] = useState([]);
  const [birthdays, setBirthdays] = useState([]);
  const [vacations, setVacations] = useState([]);
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const [empRes, archivedRes, bRes, vRes, pRes] = await Promise.all([
        api.get('employees/'),
        api.get('employees/', { params: { archived: true } }),
        api.get('birthdays/', { params: { days: 365 } }),
        api.get('vacations/active'),
        api.get('payouts/active'),
      ]);

      setEmployees(empRes.data || []);
      setArchivedEmployees(archivedRes.data || []);
      setBirthdays(bRes.data || []);
      setVacations(vRes.data || []);
      setPayouts(pRes.data || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  const allEmployees = useMemo(() => {
    const map = new Map();
    [...employees, ...archivedEmployees].forEach((emp) => {
      map.set(emp.id, emp);
    });
    return Array.from(map.values());
  }, [employees, archivedEmployees]);

  const metrics = useMemo(() => {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0);

    const total = employees.length;
    const newThisMonth = employees.filter((emp) => isSameMonth(emp.created_at, startOfMonth, endOfMonth)).length;
    const leftThisMonth = archivedEmployees.filter((emp) => isSameMonth(emp.archived_at, startOfMonth, endOfMonth)).length;

    const tenures = employees
      .map((emp) => ({
        created: toDate(emp.created_at),
        archived: emp.archived_at ? toDate(emp.archived_at) : null,
      }))
      .filter((emp) => emp.created)
      .map((emp) => {
        const endDate = emp.archived || now;
        return (endDate - emp.created) / (1000 * 60 * 60 * 24 * 365);
      });
    const avgTenureYears = tenures.length ? tenures.reduce((a, b) => a + b, 0) / tenures.length : 0;

    return {
      total,
      newThisMonth,
      leftThisMonth,
      avgTenureYears,
    };
  }, [employees, archivedEmployees]);

  const departments = useMemo(() => {
    const grouped = employees.reduce((acc, emp) => {
      const dept = emp.work_place || 'Без отдела';
      acc[dept] = (acc[dept] || 0) + 1;
      return acc;
    }, {});

    const entries = Object.entries(grouped)
      .map(([name, count], index) => ({
        name,
        count,
        color: palette[index % palette.length],
      }))
      .sort((a, b) => b.count - a.count);

    const total = entries.reduce((sum, item) => sum + item.count, 0) || 1;

    return { entries, total };
  }, [employees]);

  const monthlyHeadcount = useMemo(() => {
    const now = new Date();
    const months = Array.from({ length: 6 }).map((_, idx) => {
      const date = new Date(now.getFullYear(), now.getMonth() - (5 - idx), 1);
      return date;
    });

    return months.map((monthDate) => {
      const endOfMonth = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0);
      const headcount = allEmployees.filter((emp) => isActiveAt(emp, endOfMonth)).length;
      return {
        label: monthDate.toLocaleString('ru-RU', { month: 'short' }),
        value: headcount,
      };
    });
  }, [allEmployees]);

  const eventFeed = useMemo(() => {
    const birthdayEvents = birthdays.slice(0, 5).map((item) => ({
      type: 'birthday',
      title: `${item.full_name || item.name || 'День рождения'}`,
      subtitle: 'Празднует в этом месяце',
      date: toDate(item.birthdate, true),
      icon: Gift,
      color: '#ef4444',
    }));

    const vacationEvents = vacations.slice(0, 5).map((v) => ({
      type: 'vacation',
      title: v.name,
      subtitle: v.type,
      date: toDate(v.start_date),
      icon: CalendarDays,
      color: '#0ea5e9',
    }));

    const payoutEvents = payouts.slice(0, 5).map((p) => ({
      type: 'payout',
      title: p.name,
      subtitle: `${p.amount?.toLocaleString('ru-RU')} ₽ — ${p.payout_type || 'выплата'}`,
      date: toDate(p.timestamp, true),
      icon: Sparkles,
      color: '#f59e0b',
    }));

    return [...birthdayEvents, ...vacationEvents, ...payoutEvents]
      .filter((item) => item.date)
      .sort((a, b) => a.date - b.date)
      .slice(0, 10);
  }, [birthdays, vacations, payouts]);

  const topEmployees = useMemo(() => {
    return employees
      .map((emp) => ({
        ...emp,
        score: 70 + (hashString(emp.id || emp.name) % 31),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 6);
  }, [employees]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-sm text-[color:var(--muted-foreground)]">Обзор ключевых показателей компании</p>
          <h2 className="text-3xl font-semibold tracking-tight">Панель управления</h2>
        </div>
        <div className="flex items-center gap-3">
          <div className="text-right">
            <div className="text-sm text-[color:var(--muted-foreground)]">Алексей Иванов</div>
            <div className="text-base font-semibold">Директор</div>
          </div>
          <div className="grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-[color:var(--primary)] to-[color:var(--accent)] text-sm font-semibold text-white shadow-md">
            AI
          </div>
        </div>
      </header>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Штат сотрудников"
          value={metrics.total}
          hint="активные профили"
          accent="from-[color:var(--primary)] to-[color:var(--accent)]"
        />
        <StatCard
          title="Новых за месяц"
          value={metrics.newThisMonth}
          hint="присоединились в этом месяце"
          trend="up"
        />
        <StatCard
          title="Ушли за месяц"
          value={metrics.leftThisMonth}
          hint="архивированы в этом месяце"
          trend="down"
        />
        <StatCard
          title="Средний стаж"
          value={`${metrics.avgTenureYears.toFixed(1)} года`}
          hint="по активным сотрудникам"
          icon={Clock3}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Динамика показателей"
          description="Изменение численности за последние 6 месяцев"
          className="lg:col-span-2"
        >
          <LineChartBlock data={monthlyHeadcount} loading={loading} />
        </Card>

        <Card title="Распределение по отделам" description="Текущее количество сотрудников">
          <DepartmentChart departments={departments} loading={loading} />
        </Card>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        <Card title="Лента событий" description="Ближайшие события по людям">
          <Timeline events={eventFeed} loading={loading} />
        </Card>

        <Card title="Лучшие сотрудники" description="Номинанты недели" className="xl:col-span-2">
          <BestEmployees employees={topEmployees} loading={loading} />
        </Card>
      </div>
    </div>
  );
}

function StatCard({ title, value, hint, trend, icon, accent }) {
  const Icon = icon || (trend === 'up' ? ArrowUpRight : trend === 'down' ? ArrowDownRight : BadgeCheck);
  const gradient = accent || 'from-[color:var(--color-bg-alt)] to-[color:var(--muted)]';

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-white/80 shadow-sm ring-1 ring-black/5">
      <div className={`absolute inset-x-0 top-0 h-1.5 bg-gradient-to-r ${gradient}`} />
      <div className="flex items-start gap-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[color:var(--accent)]/10 text-[color:var(--accent-foreground)]">
          <Icon className="h-5 w-5 text-[color:var(--primary)]" />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-[color:var(--muted-foreground)]">{title}</p>
          <div className="text-2xl font-semibold leading-tight text-[color:var(--foreground)]">{value}</div>
          <p className="text-xs text-[color:var(--muted-foreground)]">{hint}</p>
        </div>
      </div>
    </div>
  );
}

function DepartmentChart({ departments, loading }) {
  const segments = useMemo(() => {
    let cursor = 0;
    return departments.entries.map((dept) => {
      const start = (cursor / departments.total) * 100;
      cursor += dept.count;
      const end = (cursor / departments.total) * 100;
      return `${dept.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
    });
  }, [departments]);

  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-[color:var(--muted)]/20" />;
  }

  if (!departments.entries.length) {
    return <p className="text-sm text-[color:var(--muted-foreground)]">Нет данных по отделам</p>;
  }

  return (
    <div className="flex flex-col items-center gap-6 lg:flex-row">
      <div
        className="grid h-40 w-40 place-items-center rounded-full border border-border bg-white/80 shadow-inner"
        style={{ background: `conic-gradient(${segments.join(',')})` }}
      >
        <div className="grid h-24 w-24 place-items-center rounded-full bg-white text-center shadow-sm">
          <span className="text-sm font-semibold text-[color:var(--foreground)]">{departments.total} сотрудников</span>
        </div>
      </div>

      <div className="space-y-3 w-full">
        {departments.entries.map((dept) => (
          <div key={dept.name} className="flex items-center justify-between gap-3 rounded-lg bg-[color:var(--muted)]/8 px-3 py-2">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: dept.color }} />
              <span className="text-sm font-medium text-[color:var(--foreground)]">{dept.name}</span>
            </div>
            <div className="text-sm font-semibold text-[color:var(--foreground)]">{dept.count}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function LineChartBlock({ data, loading }) {
  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-[color:var(--muted)]/20" />;
  }

  const maxValue = Math.max(...data.map((d) => d.value), 1);
  const points = data
    .map((item, idx) => {
      const x = (idx / Math.max(data.length - 1, 1)) * 100;
      const y = 100 - (item.value / maxValue) * 100;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <div className="space-y-6">
      <div className="relative h-52 w-full">
        <svg viewBox="0 0 100 100" className="h-full w-full" preserveAspectRatio="none">
          <defs>
            <linearGradient id="lineGradient" x1="0%" x2="0%" y1="0%" y2="100%">
              <stop offset="0%" stopColor="var(--color-primary)" stopOpacity="0.18" />
              <stop offset="100%" stopColor="var(--color-primary)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <polyline
            fill="url(#lineGradient)"
            stroke="var(--color-primary)"
            strokeWidth="1.5"
            points={`0,100 ${points} 100,100`}
            vectorEffect="non-scaling-stroke"
          />
          {data.map((item, idx) => {
            const x = (idx / Math.max(data.length - 1, 1)) * 100;
            const y = 100 - (item.value / maxValue) * 100;
            return <circle key={item.label} cx={x} cy={y} r="1.8" fill="white" stroke="var(--color-primary)" strokeWidth="1" />;
          })}
        </svg>
      </div>
      <div className="grid grid-cols-6 gap-2 text-center text-xs text-[color:var(--muted-foreground)]">
        {data.map((item) => (
          <span key={item.label} className="rounded-lg bg-[color:var(--muted)]/10 py-2 font-medium text-[color:var(--foreground)]">
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function Timeline({ events, loading }) {
  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-[color:var(--muted)]/20" />;
  }

  if (!events.length) {
    return <p className="text-sm text-[color:var(--muted-foreground)]">Нет ближайших событий</p>;
  }

  return (
    <div className="space-y-4">
      {events.map((event, idx) => {
        const Icon = event.icon;
        return (
          <div key={`${event.title}-${idx}`} className="flex items-start gap-3 rounded-xl border border-border bg-white/70 px-3 py-3 shadow-sm">
            <div className="mt-0.5 rounded-lg bg-[color:var(--muted)]/20 p-2" style={{ color: event.color }}>
              <Icon className="h-4 w-4" />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold text-[color:var(--foreground)]">{event.title}</p>
                <BadgeCheck className="h-4 w-4 text-[color:var(--accent)]" />
              </div>
              <p className="text-xs text-[color:var(--muted-foreground)]">{event.subtitle}</p>
            </div>
            <span className="rounded-full bg-[color:var(--muted)]/12 px-3 py-1 text-xs font-semibold text-[color:var(--foreground)]">
              {formatDateShort(event.date)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function BestEmployees({ employees, loading }) {
  if (loading) {
    return <div className="h-64 animate-pulse rounded-xl bg-[color:var(--muted)]/20" />;
  }

  if (!employees.length) {
    return <p className="text-sm text-[color:var(--muted-foreground)]">Нет данных по сотрудникам</p>;
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
      {employees.map((emp, index) => {
        const key = emp.id || emp.name || index;
        return (
          <div key={key} className="flex items-center gap-3 rounded-xl border border-border bg-white/70 px-3 py-3 shadow-sm">
          <div className="grid h-12 w-12 place-items-center rounded-full bg-gradient-to-br from-[color:var(--primary)]/90 to-[color:var(--accent)]/90 text-sm font-semibold text-white shadow">
            {emp.name?.slice(0, 2).toUpperCase() || 'HR'}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-[color:var(--foreground)]">{emp.name}</p>
            <p className="truncate text-xs text-[color:var(--muted-foreground)]">{emp.position || 'Сотрудник'}</p>
            <div className="mt-2 h-2 rounded-full bg-[color:var(--muted)]/20">
              <div
                className="h-full rounded-full bg-gradient-to-r from-[color:var(--primary)] to-[color:var(--accent)]"
                style={{ width: `${emp.score}%` }}
              />
            </div>
          </div>
          <div className="text-right">
            <span className="flex items-center gap-1 text-xs font-semibold text-[color:var(--foreground)]">
              {emp.score}% <Crown className="h-4 w-4 text-[color:var(--warning)]" />
            </span>
            <p className="text-[10px] uppercase tracking-wide text-[color:var(--muted-foreground)]">рейтинг</p>
          </div>
          {index === 0 && <BadgeCheck className="h-5 w-5 text-[color:var(--accent)]" />}
          </div>
        );
      })}
    </div>
  );
}

function isSameMonth(dateValue, startOfMonth, endOfMonth) {
  const date = toDate(dateValue);
  return date && date >= startOfMonth && date <= endOfMonth;
}

function toDate(value, allowNull = false) {
  if (!value && !allowNull) return null;
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return allowNull ? null : new Date();
  return date;
}

function isActiveAt(employee, date) {
  const created = toDate(employee.created_at);
  const archived = employee.archived_at ? toDate(employee.archived_at) : null;
  if (!created) return false;
  return created <= date && (!archived || archived > date);
}

function formatDateShort(date) {
  if (!date) return '';
  return date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function hashString(value = '') {
  return value.split('').reduce((acc, char) => acc + char.charCodeAt(0), 0);
}




