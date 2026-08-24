import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Coins, TrendingUp, TrendingDown, Users, BarChart3, Layers, Trophy,
} from 'lucide-react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import api from '../api';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';
import { groupEmployeesByPosition } from '../utils/employeeGrouping.js';
import KpiCard from '../components/ui/Kpi.jsx';

const CHART_COLORS = ['var(--color-success)', 'var(--color-danger)', 'var(--color-primary)', 'var(--color-warning)'];
const MONTHS_RU = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

const fmtMoney = (v) => `${Math.round(Number(v) || 0).toLocaleString('ru-RU')} ₽`;


function TypeDonut({ data, total, activeName, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Layers size={15} className="text-[color:var(--color-primary)]" />
        Премии и штрафы
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
              <Tooltip formatter={(v) => [fmtMoney(v), 'Сумма']} />
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
                    <span className="text-xs">{d.name}</span>
                    <span className="text-xs font-semibold shrink-0">{fmtMoney(d.value)} ({pct.toFixed(0)}%)</span>
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

function EmployeeLeaderboard({ data, activeName, onSelect }) {
  const medals = ['🥇', '🥈', '🥉'];
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Trophy size={15} className="text-[color:var(--color-primary)]" />
        По сотрудникам (чистый итог)
        {activeName && <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· фильтр: {activeName}</span>}
      </div>
      <div className="space-y-3">
        {data.slice(0, 8).map((r, i) => {
          const isActive = activeName === r.name;
          // Спарклайн — реальные подписанные суммы последних записей этого
          // сотрудника (премия — положительная, штраф — отрицательная),
          // хронологический порядок, не выдуманные бары.
          const trendMax = r.trend?.length ? Math.max(...r.trend.map((v) => Math.abs(v)), 1) : 1;
          return (
            <button key={r.name} type="button" onClick={() => onSelect?.(r.name)}
              className={`w-full text-left rounded-md -mx-1 px-1 py-1 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}>
              <div className="flex items-center justify-between mb-1">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  {i < 3 ? <span className="text-base shrink-0">{medals[i]}</span> : <span className="w-5 text-center text-xs font-bold text-[color:var(--color-muted-foreground)] shrink-0">{i + 1}</span>}
                  <span className="text-sm font-medium truncate">{r.name}</span>
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  {r.trend?.length > 0 && (
                    <div className="incentive-fui-spark" title={`Последние ${r.trend.length} записей`}>
                      {r.trend.map((v, ti) => (
                        <i
                          key={ti}
                          style={{
                            height: `${Math.max(3, (Math.abs(v) / trendMax) * 18)}px`,
                            background: v >= 0 ? 'var(--color-success)' : 'var(--color-danger)',
                            opacity: 0.5 + (Math.abs(v) / trendMax) * 0.5,
                          }}
                        />
                      ))}
                    </div>
                  )}
                  <div className={`text-sm font-bold whitespace-nowrap ${r.net >= 0 ? 'text-[color:var(--color-success)]' : 'text-[color:var(--color-danger)]'}`}>
                    {r.net >= 0 ? '+' : ''}{fmtMoney(r.net)}
                  </div>
                </div>
              </div>
              <div className="flex gap-1 h-1.5 rounded-full overflow-hidden bg-[color:var(--color-bg-secondary)]">
                {r.bonuses > 0 && <div style={{ width: `${(r.bonuses / (r.bonuses + r.penalties || 1)) * 100}%`, background: 'var(--color-success)' }} />}
                {r.penalties > 0 && <div style={{ width: `${(r.penalties / (r.bonuses + r.penalties || 1)) * 100}%`, background: 'var(--color-danger)' }} />}
              </div>
            </button>
          );
        })}
        {data.length === 0 && <div className="text-sm text-[color:var(--color-muted-foreground)] text-center py-4">Нет данных</div>}
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-surface)] shadow-xl p-3 text-sm">
      <div className="font-semibold mb-1 text-[color:var(--color-muted-foreground)]">{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full" style={{ background: p.fill || p.color }} />
          <span>{p.name}: <b>{fmtMoney(p.value)}</b></span>
        </div>
      ))}
    </div>
  );
}

export default function Incentives() {
  const location = useLocation();
  const query = new URLSearchParams(location.search);

  const emptyForm = {
    id: null,
    employee_id: '',
    name: '',
    type: 'bonus',
    amount: '',
    reason: '',
    date: new Date().toISOString().slice(0, 10),
    added_by: 'admin',
  };

  const [list, setList] = useState([]);
  const [employees, setEmployees] = useState([]);
  const employeesByPosition = useMemo(() => groupEmployeesByPosition(employees), [employees]);
  const [filters, setFilters] = useState({
    employee: query.get('employee_id') || '',
    type: query.get('type') || '',
    from: query.get('date_from') || '',
    to: query.get('date_to') || '',
  });
  const [form, setForm] = useState(emptyForm);
  const [showForm, setShowForm] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [typeFilter, setTypeFilter] = useState(null);
  const [employeeFilter, setEmployeeFilter] = useState(null);

  useEffect(() => {
    loadEmployees();
  }, []);

  useEffect(() => {
    load();
  }, [filters]);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function load() {
    const params = {
      employee_id: filters.employee || undefined,
      type: filters.type || undefined,
      date_from: filters.from || undefined,
      date_to: filters.to || undefined,
    };
    try {
      const res = await api.get('incentives/', { params });
      setList(res.data);
    } catch (err) {
      console.error(err);
    }
  }

  async function saveForm() {
    if (!form.employee_id || !form.amount || !form.date) return;
    const payload = { ...form, amount: Number(form.amount) };
    try {
      if (form.id) {
        await api.patch(`incentives/${form.id}`, payload);
      } else {
        await api.post('incentives/', payload);
      }
      setShowForm(false);
      setForm(emptyForm);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  async function remove(id) {
    if (!window.confirm('Удалить запись?')) return;
    try {
      await api.delete(`incentives/${id}`);
      load();
    } catch (err) {
      console.error(err);
    }
  }

  function startCreate() {
    setForm(emptyForm);
    setShowForm(true);
  }

  function startEdit(item) {
    setForm({ ...item, amount: item.amount });
    setShowForm(true);
  }

  // Токенизированные фоны строк вместо bg-green-50/bg-red-50 — те были
  // не завязаны на CSS-переменные темы и оставались светлыми (по сути
  // невидимыми) поверх тёмного фона таблицы. Тот же класс уже
  // используется в CourierSalary.jsx/ManagerSalary.jsx/Recruitment.jsx.
  const rowColor = (type) => (type === 'bonus' ? 'bg-[color:var(--color-success-muted)]' : 'bg-[color:var(--color-danger-muted)]');
  const typeLabel = (t) => (t === 'bonus' ? '💰 Премия' : '⚠️ Штраф');

  // ── Derived analytics ──────────────────────────────────────────
  const totals = useMemo(() => {
    let bonuses = 0, bonusCount = 0, penalties = 0, penaltyCount = 0;
    for (const r of list) {
      const amt = Number(r.amount) || 0;
      if (r.type === 'bonus') { bonuses += amt; bonusCount++; }
      else { penalties += amt; penaltyCount++; }
    }
    return { bonuses, bonusCount, penalties, penaltyCount, net: bonuses - penalties, employees: new Set(list.map((r) => r.employee_id)).size };
  }, [list]);

  const typeDonutData = useMemo(() => ([
    { name: 'Премии', value: totals.bonuses, color: CHART_COLORS[0] },
    { name: 'Штрафы', value: totals.penalties, color: CHART_COLORS[1] },
  ].filter((d) => d.value > 0)), [totals]);

  const employeeLeaderboard = useMemo(() => {
    const map = {};
    for (const r of list) {
      const name = r.name || '—';
      if (!map[name]) map[name] = { name, bonuses: 0, penalties: 0, records: [] };
      const amt = Number(r.amount) || 0;
      if (r.type === 'bonus') map[name].bonuses += amt;
      else map[name].penalties += amt;
      // Подписанная сумма (премия +, штраф −) с датой — сырьё для
      // спарклайна: реальная хронология записей этого сотрудника, а не
      // синтетические одинаковые бары.
      map[name].records.push({ date: r.date || '', signed: r.type === 'bonus' ? amt : -amt });
    }
    return Object.values(map).map((r) => {
      const trend = [...r.records]
        .sort((a, b) => a.date.localeCompare(b.date))
        .slice(-6)
        .map((x) => x.signed);
      return { name: r.name, bonuses: r.bonuses, penalties: r.penalties, net: r.bonuses - r.penalties, trend };
    }).sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
  }, [list]);

  const monthlyData = useMemo(() => {
    const map = {};
    for (const r of list) {
      if (!r.date) continue;
      const d = new Date(r.date);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      // Include a 2-digit year: the 12-month window (below) can span a year boundary,
      // and without it two bars both labeled "Июл" (a year apart) look identical.
      if (!map[key]) map[key] = { key, label: `${MONTHS_RU[d.getMonth()]} ${String(d.getFullYear()).slice(2)}`, bonuses: 0, penalties: 0 };
      const amt = Number(r.amount) || 0;
      if (r.type === 'bonus') map[key].bonuses += amt;
      else map[key].penalties += amt;
    }
    return Object.values(map).sort((a, b) => a.key.localeCompare(b.key)).slice(-12);
  }, [list]);

  const displayList = useMemo(() => {
    let rows = list;
    if (typeFilter) rows = rows.filter((r) => (typeFilter === 'Премии' ? r.type === 'bonus' : r.type === 'penalty'));
    if (employeeFilter) rows = rows.filter((r) => (r.name || '—') === employeeFilter);
    return rows;
  }, [list, typeFilter, employeeFilter]);

  // Нетто-телеметрия ленты «Список» — реальный агрегат по тому, что
  // сейчас видно в таблице (учитывает и серверные фильтры, и клик по
  // донату/лидерборду), пересчитывается на каждое изменение displayList.
  const visibleTotals = useMemo(() => {
    let bonuses = 0, bonusCount = 0, penalties = 0, penaltyCount = 0;
    for (const r of displayList) {
      const amt = Number(r.amount) || 0;
      if (r.type === 'bonus') { bonuses += amt; bonusCount++; }
      else { penalties += amt; penaltyCount++; }
    }
    return { bonuses, bonusCount, penalties, penaltyCount, net: bonuses - penalties };
  }, [displayList]);

  function selectType(name) {
    setTypeFilter((prev) => (prev === name ? null : name));
    setActiveTab('list');
  }
  function selectEmployee(name) {
    setEmployeeFilter((prev) => (prev === name ? null : name));
    setActiveTab('list');
  }

  const mainTabs = [
    { key: 'overview', label: 'Обзор', icon: <BarChart3 size={14} /> },
    { key: 'list', label: 'Список', icon: <Coins size={14} />, badge: list.length },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div>
        <span className="ui-eyebrow mb-3">
          {list.length ? `Записей: ${list.length}` : 'Записей нет'}
        </span>
        <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
          Штрафы и премии
        </h2>
      </div>

      <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KpiCard label="Премии" value={fmtMoney(totals.bonuses)} sub={`${totals.bonusCount} записей`} accent="var(--color-success)" icon={TrendingUp} />
            <KpiCard label="Штрафы" value={fmtMoney(totals.penalties)} sub={`${totals.penaltyCount} записей`} accent="var(--color-danger)" icon={TrendingDown} />
            <KpiCard label="Чистый итог" value={`${totals.net >= 0 ? '+' : ''}${fmtMoney(totals.net)}`} sub="премии − штрафы" accent={totals.net >= 0 ? 'var(--color-success)' : 'var(--color-danger)'} icon={Coins} />
            <KpiCard label="Сотрудников" value={String(totals.employees)} sub="затронуто записями" accent="var(--color-primary)" icon={Users} />
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <TypeDonut data={typeDonutData} total={totals.bonuses + totals.penalties} activeName={typeFilter} onSelect={selectType} />
            <EmployeeLeaderboard data={employeeLeaderboard} activeName={employeeFilter} onSelect={selectEmployee} />
          </div>

          {monthlyData.length > 0 && (
            <div className="app-card p-5">
              <div className="text-sm font-semibold mb-4 flex items-center gap-2">
                <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
                Динамика по месяцам
              </div>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 12, fill: 'var(--color-muted-foreground)' }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--color-bg-secondary)' }} />
                  <Bar dataKey="bonuses" name="Премии" fill="var(--color-success)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="penalties" name="Штрафы" fill="var(--color-danger)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      )}

      {activeTab === 'list' && (
        <div className="space-y-4">
          <div className="incentive-fui-readout">
            <span>SYS://incentives.stream</span><span className="sep">·</span>
            <span>
              НЕТТО ЗА ПЕРИОД:{' '}
              <b style={{ color: visibleTotals.net >= 0 ? 'var(--color-success)' : 'var(--color-danger)' }}>
                {visibleTotals.net >= 0 ? '+' : ''}{fmtMoney(visibleTotals.net)}
              </b>
            </span><span className="sep">·</span>
            <span>ПРЕМИЙ: <b>{visibleTotals.bonusCount}</b></span><span className="sep">·</span>
            <span>ШТРАФОВ: <b>{visibleTotals.penaltyCount}</b></span>
          </div>
          <div className="flex flex-wrap gap-2 items-end">
            <select
              className="input"
              value={filters.employee}
              onChange={(e) => setFilters({ ...filters, employee: e.target.value })}
            >
              <option value="">Все сотрудники</option>
              {employeesByPosition.map(([position, list]) => (
                <optgroup key={position} label={position}>
                  {list.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name || e.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <select
              className="input"
              value={filters.type}
              onChange={(e) => setFilters({ ...filters, type: e.target.value })}
            >
              <option value="">Все типы</option>
              <option value="bonus">Премия</option>
              <option value="penalty">Штраф</option>
            </select>
            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2 w-full sm:w-auto">
              <input
                type="date"
                className="input w-full sm:w-auto"
                value={filters.from}
                onChange={(e) => setFilters({ ...filters, from: e.target.value })}
              />
              <input
                type="date"
                className="input w-full sm:w-auto"
                value={filters.to}
                onChange={(e) => setFilters({ ...filters, to: e.target.value })}
              />
            </div>
            <button className="btn" onClick={load}>
              Применить
            </button>
            <button className="btn ml-auto" onClick={startCreate}>
              ➕ Добавить
            </button>
          </div>

          {(typeFilter || employeeFilter) && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              <span className="text-[color:var(--color-muted-foreground)]">Фильтр по графику:</span>
              {typeFilter && (
                <button className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium" onClick={() => setTypeFilter(null)}>
                  {typeFilter} ✕
                </button>
              )}
              {employeeFilter && (
                <button className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium" onClick={() => setEmployeeFilter(null)}>
                  {employeeFilter} ✕
                </button>
              )}
            </div>
          )}

          <ResponsiveTable
            data={displayList}
            keyFn={(item) => item.id}
            rowClass={(item) => rowColor(item.type)}
            emptyText="Начислений нет" emptyHint="За выбранный период штрафы и премии не заводились."
            columns={[
              { label: 'Сотрудник', key: 'name', primary: true },
              { label: 'Дата', key: 'date' },
              { label: 'Тип', render: (item) => <span className="font-medium">{typeLabel(item.type)}</span> },
              {
                label: 'Сумма',
                headerClass: 'text-right',
                cellClass: 'text-right whitespace-nowrap',
                render: (item) => (
                  <span className={`font-medium tabular-nums ${item.type === 'bonus' ? 'text-[color:var(--color-success)]' : 'text-[color:var(--color-danger)]'}`}>
                    {item.type === 'bonus' ? '+' : '−'}{Number(item.amount || 0).toLocaleString('ru-RU')} ₽
                  </span>
                ),
              },
              { label: 'Причина', key: 'reason' },
              { label: 'Добавил', key: 'added_by' },
              {
                label: '',
                isAction: true,
                cellClass: 'text-right',
                render: (item) => (
                  <>
                    {item.locked && (
                      <span className="incentive-fui-locked mr-1" title="Запись защищена от удаления">
                        🔒 LOCKED
                      </span>
                    )}
                    <button className="text-blue-600 mr-1" onClick={() => startEdit(item)}>✏️</button>
                    {!item.locked && (
                      <button className="text-red-600" onClick={() => remove(item.id)}>🗑️</button>
                    )}
                  </>
                ),
              },
            ]}
          />
        </div>
      )}

      {showForm && (
        <div className="modal-backdrop" onClick={e => e.target === e.currentTarget && setShowForm(false)}>
          <div className="modal-card max-w-md">
            <h2 className="text-xl font-semibold">{form.id ? 'Редактирование' : 'Новая запись'}</h2>
            <select
              className="modal-control"
              value={form.employee_id}
              onChange={(e) => {
                const id = e.target.value;
                setForm((f) => ({
                  ...f,
                  employee_id: id,
                  name: employees.find((u) => String(u.id) === String(id))?.full_name || '',
                }));
              }}
            >
              <option value="">Сотрудник</option>
              {employeesByPosition.map(([position, list]) => (
                <optgroup key={position} label={position}>
                  {list.map((e) => (
                    <option key={e.id} value={e.id}>
                      {e.full_name || e.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <input
              type="date"
              className="modal-control"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
            />
            <select
              className="modal-control"
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
            >
              <option value="bonus">Премия</option>
              <option value="penalty">Штраф</option>
            </select>
            <input
              className="modal-control"
              placeholder="Сумма"
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
            />
            <textarea
              className="modal-control"
              placeholder="Причина"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <div className="flex justify-end gap-2 pt-2">
              <button className="btn btn--secondary" onClick={() => setShowForm(false)}>
                Отмена
              </button>
              <button className="btn" onClick={saveForm}>
                Сохранить
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
