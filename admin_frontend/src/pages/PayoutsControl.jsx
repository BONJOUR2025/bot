import { useEffect, useMemo, useState } from 'react';
import { ShieldAlert, AlertTriangle, BarChart3, ListChecks, Layers } from 'lucide-react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';

const warningDescriptions = {
  limit_exceeded: 'Сумма выплат за месяц превышает лимит',
  pending_too_long: 'Заявка в ожидании более 48 часов',
  frequent_request: 'Между выплатами прошло менее 3 дней',
  changed_bank_data: 'Реквизиты отличаются от последних подтверждённых',
  manual_created: 'Заявка создана вручную администратором',
  inactive_employee: 'Сотрудник помечен как неактивный',
};

const WARNING_SEVERITY = {
  limit_exceeded: 'high', inactive_employee: 'high',
  pending_too_long: 'medium', changed_bank_data: 'medium',
  manual_created: 'low', frequent_request: 'medium',
};

const STATUS_OPTIONS = ['Ожидает', 'Одобрено', 'Отклонено', 'Выплачено'];
const CHART_COLORS = { high: 'var(--color-danger)', medium: 'var(--color-warning)', low: 'var(--color-primary)' };

const fmtMoney = (v) => `${Math.round(Number(v) || 0).toLocaleString('ru-RU')} ₽`;

function KpiCard({ label, value, sub, accent, icon: Icon }) {
  return (
    <div className="app-card p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-[color:var(--color-muted-foreground)] mb-1">{label}</div>
          <div className="text-xl font-bold truncate" style={{ color: accent || 'var(--color-primary)' }}>{value}</div>
          {sub && <div className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{sub}</div>}
        </div>
        {Icon && (
          <div className="rounded-xl p-2 shrink-0" style={{ background: `color-mix(in oklab, ${accent || 'var(--color-primary)'} 9%, transparent)` }}>
            <Icon size={20} style={{ color: accent || 'var(--color-primary)' }} />
          </div>
        )}
      </div>
    </div>
  );
}

function SeverityDonut({ data, total, activeName, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <ShieldAlert size={15} className="text-[color:var(--color-primary)]" />
        Риск по уровню серьёзности
        {activeName && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {activeName}</span>}
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 160, height: 160, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data} dataKey="value" nameKey="name" innerRadius="50%" outerRadius="80%" paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}
                onClick={(entry) => onSelect?.(entry.name)} cursor="pointer"
              >
                {data.map((entry, i) => (
                  <Cell key={entry.name} fill={entry.color}
                    opacity={activeName && activeName !== entry.name ? 0.35 : (hover === null || hover === i ? 1 : 0.4)}
                    stroke="none" />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [v, 'Заявок']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0">
          {data.map((d) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            const isActive = activeName === d.name;
            return (
              <button key={d.name} type="button" onClick={() => onSelect?.(d.name)}
                className={`flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}>
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs truncate">{d.name}</span>
                    <span className="text-xs font-semibold shrink-0">{d.value} ({pct.toFixed(0)}%)</span>
                  </div>
                  <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: d.color }} />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function WarningBreakdown({ data, activeWarning, onSelect }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Layers size={15} className="text-[color:var(--color-primary)]" />
        По типам предупреждений
      </div>
      <div className="space-y-2.5">
        {data.map((d) => {
          const pct = max > 0 ? (d.count / max) * 100 : 0;
          const isActive = activeWarning === d.key;
          const color = CHART_COLORS[WARNING_SEVERITY[d.key]] || 'var(--color-primary)';
          return (
            <button key={d.key} type="button" onClick={() => onSelect?.(d.key)}
              className={`w-full text-left rounded-lg -mx-1 px-1 py-1 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs truncate flex-1" title={warningDescriptions[d.key]}>{warningDescriptions[d.key]}</span>
                <span className="text-xs font-semibold shrink-0 ml-2">{d.count}</span>
              </div>
              <div className="h-1.5 rounded-lg bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div className="h-full rounded-lg" style={{ width: `${pct}%`, background: color, opacity: 0.8 }} />
              </div>
            </button>
          );
        })}
        {data.length === 0 && <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Предупреждений нет</div>}
      </div>
    </div>
  );
}

export default function PayoutsControl() {
  const [list, setList] = useState([]);
  const [filters, setFilters] = useState({
    type: '',
    status: '',
    method: '',
    from: '',
    to: '',
    warnings: [],
  });
  const [activeTab, setActiveTab] = useState('overview');
  const [severityFilter, setSeverityFilter] = useState(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const params = {
        type: filters.type || undefined,
        status: filters.status || undefined,
        method: filters.method || undefined,
        date_from: filters.from || undefined,
        date_to: filters.to || undefined,
      };
      const res = await api.get('payouts/control', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  const severityOf = (ws) => {
    if (ws.some((w) => WARNING_SEVERITY[w] === 'high')) return 'Высокий риск';
    if (ws.some((w) => WARNING_SEVERITY[w] === 'medium')) return 'Средний риск';
    if (ws.length) return 'Низкий риск';
    return null;
  };

  const filtered = list.filter((i) => {
    if (filters.warnings.length && !filters.warnings.every((w) => i.warnings.includes(w))) return false;
    if (severityFilter && severityOf(i.warnings) !== severityFilter) return false;
    return true;
  });

  function toggleWarning(w) {
    setFilters((prev) => {
      const warnings = prev.warnings.includes(w)
        ? prev.warnings.filter((x) => x !== w)
        : [...prev.warnings, w];
      return { ...prev, warnings };
    });
    setActiveTab('list');
  }

  function selectSeverity(name) {
    setSeverityFilter((prev) => (prev === name ? null : name));
    setActiveTab('list');
  }

  function rowColor(ws) {
    if (ws.includes('limit_exceeded') || ws.includes('inactive_employee'))
      return 'bg-red-50';
    if (ws.includes('pending_too_long') || ws.includes('changed_bank_data'))
      return 'bg-orange-50';
    if (ws.includes('manual_created')) return 'bg-blue-50';
    return '';
  }

  // ── Derived analytics ──────────────────────────────────────────
  const stats = useMemo(() => {
    let flagged = 0, clean = 0, totalAmount = 0, flaggedAmount = 0;
    const sevCount = { 'Высокий риск': 0, 'Средний риск': 0, 'Низкий риск': 0 };
    const warnCount = {};
    for (const p of list) {
      const amt = Number(p.amount) || 0;
      totalAmount += amt;
      if (p.warnings.length) {
        flagged++;
        flaggedAmount += amt;
        const sev = severityOf(p.warnings);
        if (sev) sevCount[sev]++;
        for (const w of p.warnings) warnCount[w] = (warnCount[w] || 0) + 1;
      } else clean++;
    }
    return { flagged, clean, totalAmount, flaggedAmount, sevCount, warnCount, total: list.length };
  }, [list]);

  const severityDonutData = useMemo(() => ([
    { name: 'Высокий риск', value: stats.sevCount['Высокий риск'], color: CHART_COLORS.high },
    { name: 'Средний риск', value: stats.sevCount['Средний риск'], color: CHART_COLORS.medium },
    { name: 'Низкий риск', value: stats.sevCount['Низкий риск'], color: CHART_COLORS.low },
  ].filter((d) => d.value > 0)), [stats]);

  const warningBreakdownData = useMemo(() =>
    Object.keys(warningDescriptions)
      .map((key) => ({ key, count: stats.warnCount[key] || 0 }))
      .filter((d) => d.count > 0)
      .sort((a, b) => b.count - a.count)
  , [stats]);

  const mainTabs = [
    { key: 'overview', label: 'Обзор', icon: <BarChart3 size={14} /> },
    { key: 'list', label: 'Список', icon: <ListChecks size={14} />, badge: filtered.length },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
        <ShieldAlert size={24} /> Контроль выплат
      </h2>

      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="Всего заявок" value={String(stats.total)} sub={fmtMoney(stats.totalAmount)} accent="var(--color-primary)" icon={ListChecks} />
            <KpiCard label="С предупреждениями" value={String(stats.flagged)} sub={fmtMoney(stats.flaggedAmount)} accent="var(--color-danger)" icon={AlertTriangle} />
            <KpiCard label="Без замечаний" value={String(stats.clean)} sub={stats.total ? `${Math.round((stats.clean / stats.total) * 100)}% от всех` : ''} accent="var(--color-success)" icon={ShieldAlert} />
            <KpiCard label="Высокий риск" value={String(stats.sevCount['Высокий риск'])} sub="требуют проверки в первую очередь" accent="var(--color-danger)" icon={AlertTriangle} />
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <SeverityDonut data={severityDonutData} total={stats.flagged} activeName={severityFilter} onSelect={selectSeverity} />
            <WarningBreakdown data={warningBreakdownData} activeWarning={filters.warnings[0]} onSelect={toggleWarning} />
          </div>
        </div>
      )}

      {activeTab === 'list' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2 items-end">
            <select
              className="input text-sm"
              value={filters.type}
              onChange={(e) => setFilters({ ...filters, type: e.target.value })}
            >
              <option value="">Все типы</option>
              <option value="advance">Аванс</option>
              <option value="final">Финальная</option>
              <option value="compensation">Компенсация</option>
            </select>
            <select
              className="input text-sm"
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            >
              <option value="">Все статусы</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <select
              className="input text-sm"
              value={filters.method}
              onChange={(e) => setFilters({ ...filters, method: e.target.value })}
            >
              <option value="">Все способы</option>
              <option value="card">На карту</option>
              <option value="cash">Наличными</option>
              <option value="account">На счёт</option>
            </select>
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 w-full sm:w-auto">
              <input
                type="date"
                className="input text-sm w-full sm:w-auto"
                value={filters.from}
                onChange={(e) => setFilters({ ...filters, from: e.target.value })}
              />
              <input
                type="date"
                className="input text-sm w-full sm:w-auto"
                value={filters.to}
                onChange={(e) => setFilters({ ...filters, to: e.target.value })}
              />
            </div>
            <button className="btn" onClick={load}>
              Применить
            </button>
            <div className="flex flex-wrap gap-2 border border-[color:var(--color-border)] rounded p-2 bg-[color:var(--color-bg-subtle)] text-xs w-full sm:w-auto">
              {Object.keys(warningDescriptions).map((w) => (
                <label key={w} className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={filters.warnings.includes(w)}
                    onChange={() => toggleWarning(w)}
                  />
                  {warningDescriptions[w]}
                </label>
              ))}
            </div>
          </div>

          {severityFilter && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-[color:var(--color-muted-foreground)]">Фильтр по графику:</span>
              <button className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium" onClick={() => setSeverityFilter(null)}>
                {severityFilter} ✕
              </button>
            </div>
          )}

          <ResponsiveTable
            data={filtered}
            keyFn={(p) => p.id}
            rowClass={(p) => rowColor(p.warnings)}
            emptyText="Нет данных"
            columns={[
              { label: 'ФИО', key: 'name', primary: true },
              { label: 'Тип', key: 'type' },
              { label: 'Способ', key: 'method' },
              {
                label: 'Сумма',
                headerClass: 'text-right',
                cellClass: 'text-right whitespace-nowrap',
                render: (p) => (
                  <span className="text-[color:var(--color-primary)] font-medium tabular-nums">
                    {Number(p.amount || 0).toLocaleString('ru-RU')} ₽
                  </span>
                ),
              },
              { label: 'Статус', key: 'status' },
              {
                label: 'Дата',
                render: (p) => <span className="text-xs">{p.date}</span>,
              },
              {
                label: '⚠️ Предупреждения',
                render: (p) => (
                  <div className="flex flex-wrap gap-1">
                    {p.warnings.map((w) => (
                      <span
                        key={w}
                        title={warningDescriptions[w]}
                        className="inline-block bg-[color:var(--color-control-bg)] px-1 rounded text-xs"
                      >
                        {w}
                      </span>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}
    </div>
  );
}
