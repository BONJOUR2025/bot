import { useState, useMemo, useEffect } from 'react';
import {
  Search, RefreshCw, Download, ChevronUp, ChevronDown, ChevronsUpDown, AlertTriangle,
  Hammer, ListChecks, CheckCircle2, Clock, Users, Receipt, ClipboardList,
  BarChart3, Trophy, Layers, X, GraduationCap,
} from 'lucide-react';
import {
  BarChart, Bar, PieChart, Pie, Cell, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import { useViewport } from '../providers/ViewportProvider.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { fmtMoney, Term, StatCard, Tabs, TONE_TEXT } from '../components/ui/SalaryUI.jsx';
import { CHART_PALETTE as CHART_COLORS } from '../utils/chartPalette.js';

const DAY_NAMES    = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб'];

const fmt    = (v) => (v == null ? '—' : v);
const fmtRub = (v) => (v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽');
const fmtMin = (v) => {
  if (v == null) return '—';
  if (v < 1) return '< 1м';
  const total = Math.round(v);
  const d = Math.floor(total / 1440);
  const h = Math.floor((total % 1440) / 60);
  const m = total % 60;
  if (d > 0) return `${d}д ${h}ч ${m}м`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
};
const fmtDt = (v) => {
  if (!v) return '—';
  try { return new Date(v).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return v; }
};

const STATUS_COLORS = {
  'Выполнено': 'bg-green-100 text-green-800',
  'В работе':  'bg-yellow-100 text-yellow-800',
  'Прочее':    'bg-[color:var(--color-bg-subtle)] text-[color:var(--color-text-muted)]',
};
const STATUS_OPTIONS = Object.keys(STATUS_COLORS);

const DURATION_OPTIONS = [
  { label: 'Любая', value: 'all' },
  { label: '< 5м',  value: 'lt5',    test: (v) => v != null && v < 5 },
  { label: '5–30м', value: '5to30',  test: (v) => v != null && v >= 5 && v < 30 },
  { label: '30–60м',value: '30to60', test: (v) => v != null && v >= 30 && v < 60 },
  { label: '> 1ч',  value: 'gt60',   test: (v) => v != null && v >= 60 },
  { label: 'Нет данных', value: 'null', test: (v) => v == null },
];

const WARNING_TYPES = [
  { key: 'warning_mismatch', label: 'Разные мастера' },
  { key: 'warning_too_fast', label: 'Слишком быстро' },
  { key: 'warning_no_in',    label: 'Нет входа' },
  { key: 'warning_multi',    label: 'Несколько сканов' },
];

function SortIcon({ col, sortCol, sortDir }) {
  if (sortCol !== col) return <ChevronsUpDown size={13} className="inline ml-1 opacity-30" />;
  return sortDir === 'asc'
    ? <ChevronUp size={13} className="inline ml-1 text-[color:var(--color-primary)]" />
    : <ChevronDown size={13} className="inline ml-1 text-[color:var(--color-primary)]" />;
}

function MastersSummaryTable({ rows, onMasterClick, advancesByMaster }) {
  const { isMobile } = useViewport();
  const [tab, setTab] = useState('works');

  const byMaster = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      const name = r.description || '—';
      if (!map[name]) map[name] = { name, total: 0, done: 0, inWork: 0, warnings: 0, durations: [] };
      map[name].total++;
      if (r.status === 'Выполнено') {
        map[name].done++;
        // Услуги короче 15 минут не учитываются в медиане — почти всегда
        // это артефакт сканирования (пакетное сканирование, повторный скан
        // и т.п.), а не реальное время работы, и тянет медиану вниз.
        if (r.duration_min != null && r.duration_min >= 15) map[name].durations.push(r.duration_min);
      }
      if (r.status === 'В работе') map[name].inWork++;
      if (r.warnings?.length > 0) map[name].warnings++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  // Строго по ВЫХОДАМ: только услуги с OUT-сканом, мастер = out_description.
  const bySalaryMaster = useMemo(() => {
    const map = {};
    rows.forEach((r) => {
      if (r.master_salary == null) return;
      const name = r.out_description || '—';
      if (!map[name]) map[name] = { master: name, services_done: 0, total_kredit: 0, total_salary: 0, warnings_count: 0 };
      map[name].services_done++;
      map[name].total_kredit += Number(r.kredit) || 0;
      map[name].total_salary += Number(r.master_salary) || 0;
      if (r.warnings?.length > 0) map[name].warnings_count++;
    });
    // Avances since the last salary payout aren't derivable from the service
    // rows above at all -- they come from PayoutRepository, keyed by the
    // employee's bot account, not from anything in a Firebird service scan.
    // Backend-supplied per master, looked up here rather than recomputed.
    return Object.values(map)
      .map((m) => {
        const advance = advancesByMaster?.[m.master] ?? 0;
        return { ...m, advances_since_last_salary: advance, to_pay: m.total_salary - advance };
      })
      .sort((a, b) => b.total_salary - a.total_salary);
  }, [rows, advancesByMaster]);

  const median = (arr) => {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  };

  return (
    <div className="app-card overflow-hidden">
      <div className="p-4 border-b border-[color:var(--color-border)] flex flex-wrap items-center gap-3">
        <h3 className="font-semibold">Сводка по мастерам</h3>
        <div className="sm:ml-auto">
          <Tabs
            tabs={[{ key: 'works', label: 'Работы' }, { key: 'salary', label: 'Зарплата' }]}
            active={tab} onChange={setTab}
          />
        </div>
      </div>

      {tab === 'works' && (
        isMobile ? (
          <div className="space-y-3 p-3">
            {byMaster.map((m) => (
              <div key={m.name} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium">
                  <button onClick={() => onMasterClick(m.name)}
                    className="text-left hover:text-[color:var(--color-primary)] hover:underline transition-colors">
                    {m.name}
                  </button>
                </div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  {/* Тот же принцип, что в реестре: цвет только там, где
                      он означает, что с мастером надо разобраться. */}
                  <div className="fui-micro"><span className="fui-micro__k">Всего</span><span className="fui-micro__v">{m.total}</span></div>
                  <div className="fui-micro"><span className="fui-micro__k">Выполнено</span><span className="fui-micro__v">{m.done}</span></div>
                  <div className="fui-micro"><span className="fui-micro__k">В работе</span><span className="fui-micro__v">{m.inWork || '—'}</span></div>
                  <div className="fui-micro"><span className="fui-micro__k" title="Услуги короче 15 минут не учитываются">Медиана</span><span className="fui-micro__v">{fmtMin(median(m.durations))}</span></div>
                  <div className="fui-micro"><span className="fui-micro__k">Нарушений</span><span className={`fui-micro__v ${m.warnings > 0 ? 'mas-warn--hot' : ''}`}>{m.warnings > 0 ? m.warnings : '—'}</span></div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <table className="mas-reg min-w-[560px]">
            <thead>
              <tr>
                <th>Мастер</th>
                <th className="r">Всего</th>
                <th className="r">Выполнено</th>
                <th className="r">В работе</th>
                <th className="r" title="Услуги короче 15 минут не учитываются">Медиана</th>
                <th className="r">Нарушений</th>
              </tr>
            </thead>
            <tbody>
              {byMaster.map((m, i) => {
                const maxTotal = Math.max(1, ...byMaster.map((x) => x.total));
                const maxWarn = Math.max(1, ...byMaster.map((x) => x.warnings || 0));
                return (
                  <tr key={m.name}>
                    <td>
                      <button onClick={() => onMasterClick(m.name)} className="mas-reg__name">{m.name}</button>
                    </td>
                    {/* Шкала переехала под число, которое измеряет. Под
                        именем она читалась как подчёркивание текста, а не
                        как загрузка относительно самого занятого мастера. */}
                    <td className="r n">
                      {m.total}
                      <span className={`mas-load ${i === 0 ? 'mas-load--lead' : ''}`}>
                        <i style={{ width: `${Math.max(3, (m.total / maxTotal) * 100)}%` }} />
                      </span>
                    </td>
                    <td className="r n">{m.done}</td>
                    <td className="r n">{m.inWork || <span className="dim">—</span>}</td>
                    <td className="r n dim">{fmtMin(median(m.durations))}</td>
                    <td className="r">
                      {m.warnings > 0
                        ? <span className={`mas-warn ${m.warnings >= maxWarn * 0.5 ? 'mas-warn--hot' : ''}`}>{m.warnings}</span>
                        : <span className="dim">—</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )
      )}

      {tab === 'salary' && (
        isMobile ? (
          <div className="space-y-3 p-3">
            {bySalaryMaster.map((m) => (
              <div key={m.master} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium">
                  <button onClick={() => onMasterClick(m.master)}
                    className="text-left hover:text-[color:var(--color-primary)] hover:underline transition-colors">
                    {m.master}
                  </button>
                </div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Учтено в ЗП</span><span>{m.services_done}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Сумма услуг</span><span className="text-[color:var(--color-muted-foreground)]">{fmtRub(m.total_kredit)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Зарплата</span><span className="font-semibold text-[color:var(--color-primary)]">{fmtRub(m.total_salary)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]" title="Авансы («Выплачено»/«Одобрено»), выданные после последней выплаты типа «Зарплата»">Аванс с посл. ЗП</span><span className="text-amber-600">{fmtRub(m.advances_since_last_salary)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">К выплате</span><span className="font-semibold text-emerald-600">{fmtRub(m.to_pay)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Нарушений</span><span>{m.warnings_count > 0 ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><AlertTriangle size={12} />{m.warnings_count}</span> : <span className="text-[color:var(--color-muted-foreground)]">—</span>}</span></div>
                </div>
              </div>
            ))}
            {bySalaryMaster.length > 0 && (
              <div className="border rounded-xl bg-[color:var(--color-muted)]/20 shadow-sm overflow-hidden">
                <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-semibold">Итого</div>
                <div className="px-4 py-2 space-y-1.5 text-sm">
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Учтено в ЗП</span><span className="font-semibold">{bySalaryMaster.reduce((s, r) => s + r.services_done, 0)}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Сумма услуг</span><span className="font-semibold">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_kredit || 0), 0))}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Зарплата</span><span className="font-semibold text-[color:var(--color-primary)]">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_salary || 0), 0))}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Аванс с посл. ЗП</span><span className="font-semibold text-amber-600">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.advances_since_last_salary || 0), 0))}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">К выплате</span><span className="font-semibold text-emerald-600">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.to_pay || 0), 0))}</span></div>
                  <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Нарушений</span><span className="font-semibold">{bySalaryMaster.reduce((s, r) => s + (r.warnings_count || 0), 0)}</span></div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <table className="w-full text-sm min-w-[680px]">
            <thead>
              <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
                <th className="px-4 py-2 text-left">Мастер</th>
                <th className="px-4 py-2 text-right">Учтено в ЗП</th>
                <th className="px-4 py-2 text-right">Сумма услуг</th>
                <th className="px-4 py-2 text-right text-[color:var(--color-primary)]">Зарплата</th>
                <th className="px-4 py-2 text-right text-amber-600" title="Авансы («Выплачено»/«Одобрено»), выданные после последней выплаты типа «Зарплата»">Аванс с посл. ЗП</th>
                <th className="px-4 py-2 text-right text-emerald-600">К выплате</th>
                <th className="px-4 py-2 text-right text-amber-600">Нарушений</th>
              </tr>
            </thead>
            <tbody>
              {bySalaryMaster.map((m, i) => (
                <tr key={m.master} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/30' : ''}>
                  <td className="px-4 py-2 font-medium">
                    <button onClick={() => onMasterClick(m.master)}
                      className="text-left hover:text-[color:var(--color-primary)] hover:underline transition-colors">
                      {m.master}
                    </button>
                  </td>
                  <td className="px-4 py-2 text-right">{m.services_done}</td>
                  <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtRub(m.total_kredit)}</td>
                  <td className="px-4 py-2 text-right font-semibold text-[color:var(--color-primary)]">{fmtRub(m.total_salary)}</td>
                  <td className="px-4 py-2 text-right text-amber-600">{fmtRub(m.advances_since_last_salary)}</td>
                  <td className="px-4 py-2 text-right font-semibold text-emerald-600">{fmtRub(m.to_pay)}</td>
                  <td className="px-4 py-2 text-right">
                    {m.warnings_count > 0
                      ? <span className="inline-flex items-center gap-1 text-amber-600 font-medium"><AlertTriangle size={12} />{m.warnings_count}</span>
                      : <span className="text-[color:var(--color-muted-foreground)]">—</span>}
                  </td>
                </tr>
              ))}
              {bySalaryMaster.length > 0 && (
                <tr className="border-t border-[color:var(--color-border)] font-semibold bg-[color:var(--color-muted)]/20">
                  <td className="px-4 py-2">Итого</td>
                  <td className="px-4 py-2 text-right">{bySalaryMaster.reduce((s, r) => s + r.services_done, 0)}</td>
                  <td className="px-4 py-2 text-right">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_kredit || 0), 0))}</td>
                  <td className="px-4 py-2 text-right text-[color:var(--color-primary)]">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.total_salary || 0), 0))}</td>
                  <td className="px-4 py-2 text-right text-amber-600">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.advances_since_last_salary || 0), 0))}</td>
                  <td className="px-4 py-2 text-right text-emerald-600">{fmtRub(bySalaryMaster.reduce((s, r) => s + (r.to_pay || 0), 0))}</td>
                  <td className="px-4 py-2 text-right">{bySalaryMaster.reduce((s, r) => s + (r.warnings_count || 0), 0)}</td>
                </tr>
              )}
            </tbody>
          </table>
        )
      )}
    </div>
  );
}

// ── Visualization components ──────────────────────────────────────

function TopMastersChart({ data, activeNames, onSelect }) {
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Trophy size={15} className="text-[color:var(--color-primary)]" />
        Топ мастеров по зарплате
      </div>
      <ResponsiveContainer width="100%" height={Math.max(150, data.length * 38)}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid horizontal={false} stroke="var(--fui-edge)" />
          <XAxis type="number" tickFormatter={fmtRub} tick={{ fontSize: 9.5, fill: 'var(--color-text-faint)' }} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="master" tick={{ fontSize: 11, fill: 'var(--color-text-faint)' }} tickLine={false} axisLine={false} width={120} />
          <Tooltip formatter={(v) => [fmtRub(v), 'Зарплата']} />
          <Bar dataKey="total_salary" radius={[0, 4, 4, 0]} onClick={(entry) => onSelect?.(entry.master)} cursor={onSelect ? 'pointer' : 'default'}>
            {/* Акцент — только лидеру, остальные графитом по убыванию:
                это ранжирование, а не набор независимых категорий. */}
            {data.map((d, i) => (
              <Cell
                key={d.master}
                fill={i === 0 ? 'var(--color-primary)' : `color-mix(in srgb, var(--color-text) ${Math.max(12, 32 - i * 3)}%, transparent)`}
                opacity={activeNames?.size && !activeNames.has(d.master) ? 0.35 : 1}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function StatusDonut({ data, total, activeNames, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <BarChart3 size={15} className="text-[color:var(--color-primary)]" />
        Статусы услуг
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 150, height: 150, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data} dataKey="value" nameKey="name"
                innerRadius="50%" outerRadius="80%" paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}
                onClick={(entry) => onSelect?.(entry.name)}
                cursor={onSelect ? 'pointer' : 'default'}
              >
                {data.map((entry, i) => (
                  <Cell key={entry.name} fill={entry.color} opacity={activeNames?.size && !activeNames.has(entry.name) ? 0.35 : (hover === null || hover === i ? 1 : 0.4)} stroke="none" />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [v, 'Услуг']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0 w-full">
          {data.map((d) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            const isActive = activeNames?.has(d.name);
            return (
              <button
                key={d.name}
                type="button"
                onClick={() => onSelect?.(d.name)}
                className={`flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
              >
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs">{d.name}</span>
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

function CategoryDonut({ data, total, activeNames, onSelect }) {
  const [hover, setHover] = useState(null);
  if (!data.length) return null;
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Layers size={15} className="text-[color:var(--color-primary)]" />
        Категории услуг
      </div>
      <div className="flex flex-col sm:flex-row gap-4 items-center">
        <div style={{ width: 150, height: 150, flexShrink: 0 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data} dataKey="value" nameKey="name"
                innerRadius="50%" outerRadius="80%" paddingAngle={2}
                onMouseEnter={(_, i) => setHover(i)} onMouseLeave={() => setHover(null)}
                onClick={(entry) => entry.name !== 'Прочие' && onSelect?.(entry.name)}
                cursor={onSelect ? 'pointer' : 'default'}
              >
                {data.map((entry, i) => (
                  <Cell key={entry.name} fill={CHART_COLORS[i % CHART_COLORS.length]} opacity={activeNames?.size && !activeNames.has(entry.name) ? 0.35 : (hover === null || hover === i ? 1 : 0.4)} stroke="none" />
                ))}
              </Pie>
              <Tooltip formatter={(v) => [fmtRub(v), 'Сумма']} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-2 min-w-0 w-full">
          {data.map((d, i) => {
            const pct = total > 0 ? (d.value / total) * 100 : 0;
            const clickable = d.name !== 'Прочие';
            const isActive = activeNames?.has(d.name);
            return (
              <button
                key={d.name}
                type="button"
                disabled={!clickable}
                onClick={() => onSelect?.(d.name)}
                className={`flex items-center gap-2 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect && clickable ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
              >
                <div className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: CHART_COLORS[i % CHART_COLORS.length] }} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-1">
                    <span className="text-xs truncate">{d.name}</span>
                    <span className="text-xs font-semibold shrink-0">{pct.toFixed(0)}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-[color:var(--color-bg-secondary)] mt-0.5 overflow-hidden">
                    <div className="h-full rounded-full" style={{ width: `${pct}%`, background: CHART_COLORS[i % CHART_COLORS.length] }} />
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

function ServiceDayHeatmap({ data, activeDay, onSelect }) {
  const max = Math.max(...data.map((d) => d.count), 1);
  return (
    <div className="app-card p-5">
      <div className="text-sm font-semibold mb-4 flex items-center gap-2">
        <Clock size={15} className="text-[color:var(--color-primary)]" />
        Активность по дням недели
      </div>
      <div className="space-y-2.5">
        {data.map((d, i) => {
          const pct = max > 0 ? (d.count / max) * 100 : 0;
          const isWeekend = d.day === 'Вс' || d.day === 'Сб';
          const isActive = activeDay === i;
          return (
            <button
              key={d.day}
              type="button"
              onClick={() => onSelect?.(i)}
              className={`flex items-center gap-3 w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-bg-secondary)] cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <div className="w-6 text-xs text-right text-[color:var(--color-muted-foreground)] shrink-0 font-medium">{d.day}</div>
              <div className="flex-1 h-6 rounded-lg bg-[color:var(--color-bg-secondary)] overflow-hidden">
                <div
                  className="h-full rounded-lg transition-all duration-500"
                  /* Выходные графитом: янтарный здесь означал бы
                     предупреждение, а суббота — просто другой день. */
                  style={{ width: `${pct}%`, background: isWeekend ? 'color-mix(in srgb, var(--color-text) 26%, transparent)' : 'var(--color-primary)', opacity: activeDay != null && !isActive ? 0.35 : 0.85 }}
                />
              </div>
              <div className="text-xs font-medium w-16 text-right shrink-0">{d.count} усл.</div>
            </button>
          );
        })}
      </div>
      <div className="flex gap-4 mt-4 text-xs text-[color:var(--color-muted-foreground)]">
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'var(--color-primary)' }} />Будни</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-3 h-3 rounded-sm opacity-75" style={{ background: 'color-mix(in srgb, var(--color-text) 26%, transparent)' }} />Выходные</span>
      </div>
    </div>
  );
}

function toLocalDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

// A single /masters/works request for a multi-month range can take a
// minute+ server-side (unbounded SQL + pandas over the whole span) and,
// worse, ride through xtunnel for that whole time — which has documented
// relay-side instability with long-lived connections (see
// xtunnel_healthcheck.py). One request per calendar month keeps each
// call in the range this endpoint is actually fast at (~8-16s/month,
// measured), and is safe to concatenate: the backend's date filter
// matches each service to exactly one month by its OUT event (or IN
// event if still "в работе"), so chunk boundaries can't split, drop, or
// duplicate a service.
function splitIntoMonthlyRanges(fromStr, toStr) {
  if (!fromStr || !toStr) return [[fromStr, toStr]];
  const from = new Date(`${fromStr}T00:00:00`);
  const to = new Date(`${toStr}T00:00:00`);
  if (isNaN(from) || isNaN(to) || from > to) return [[fromStr, toStr]];
  const ranges = [];
  let cursor = from;
  while (cursor <= to) {
    const monthEnd = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
    const chunkEnd = monthEnd < to ? monthEnd : to;
    ranges.push([toLocalDateStr(cursor), toLocalDateStr(chunkEnd)]);
    cursor = new Date(chunkEnd.getFullYear(), chunkEnd.getMonth(), chunkEnd.getDate() + 1);
  }
  return ranges;
}

export default function Masters() {
  const { isMobile } = useViewport();
  const now = new Date();
  const today = toLocalDateStr(now);
  const monthStart = toLocalDateStr(new Date(now.getFullYear(), now.getMonth(), 1));

  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo, setDateTo]     = useState(today);
  const [statusFilter, setStatusFilter]     = useState(new Set());
  const [masterFilter, setMasterFilter]     = useState(new Set());
  const [masterSearchText, setMasterSearchText] = useState('');
  const [nameSearch, setNameSearch]         = useState('');
  const [codeSearch, setCodeSearch]         = useState('');
  const [docSearch, setDocSearch]           = useState('');
  const [durationFilter, setDurationFilter] = useState('all');
  const [categoryFilter, setCategoryFilter]       = useState(new Set());
  const [warningTypeFilter, setWarningTypeFilter] = useState(new Set());
  const [dayFilter, setDayFilter] = useState(null);

  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState('asc');

  const [rows, setRows]                   = useState([]);
  const [salarySummary, setSalarySummary] = useState([]);
  const advancesByMaster = useMemo(
    () => Object.fromEntries(
      salarySummary
        .filter((s) => s.advances_since_last_salary != null)
        .map((s) => [s.master, s.advances_since_last_salary]),
    ),
    [salarySummary],
  );
  const [loading, setLoading]             = useState(false);
  const [loadProgress, setLoadProgress]   = useState(null);
  const [error, setError]                 = useState(null);
  const [stale, setStale]                 = useState(null);

  // Стипендия учеников — отдельный ростер и отдельный источник данных
  // (турникетные регистрации, а не сканы услуг), поэтому не переиспользует
  // ни `rows`, ни `load()` выше: своя загрузка, свой период тот же.
  const [apprentices, setApprentices]         = useState([]);
  const [apprenticesLoading, setApprenticesLoading] = useState(false);
  const [apprenticesError, setApprenticesError]     = useState(null);
  const [apprenticesLoadedRange, setApprenticesLoadedRange] = useState(null);
  const [loaded, setLoaded]               = useState(false);
  const [warningsOnly, setWarningsOnly]   = useState(false);
  const [tab, setTab] = useState('overview');

  const masterNames = useMemo(
    () => [...new Set(rows.map((r) => r.description).filter(Boolean))].sort(),
    [rows],
  );

  const categoryOptions = useMemo(
    () => [...new Set(rows.map((r) => r.top_parent_name).filter(Boolean))].sort(),
    [rows],
  );

  const visibleMasterNames = useMemo(
    () => (masterSearchText ? masterNames.filter((n) => n.toLowerCase().includes(masterSearchText.toLowerCase())) : masterNames),
    [masterNames, masterSearchText],
  );

  function toggleStatus(status) {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }

  function toggleCategory(cat) {
    setCategoryFilter((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  function toggleMaster(name) {
    setMasterFilter((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  function toggleWarningType(key) {
    setWarningTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function fetchOneRange(f, t) {
    const params = {};
    if (f) params.date_from = f;
    if (t) params.date_to   = t;
    const res = await api.get('/masters/works', { params });
    const data = res.data;
    // Support both old (array) and new (object) response shape
    return Array.isArray(data) ? { services: data, salary_summary: [], stale: false } : {
      services: data.services || [], salary_summary: data.salary_summary || [],
      // Set by the backend when Firebird was too busy to answer inside the
      // request budget and it served the last good report instead.
      stale: Boolean(data.stale), staleAgeSec: data.stale_age_sec || 0,
    };
  }

  async function load() {
    setLoading(true);
    setError(null);
    setStale(null);
    setLoadProgress(null);
    try {
      const ranges = splitIntoMonthlyRanges(dateFrom, dateTo);
      if (ranges.length <= 1) {
        const { services, salary_summary, stale: isStale, staleAgeSec } =
          await fetchOneRange(dateFrom, dateTo);
        setRows(services);
        setSalarySummary(salary_summary);
        if (isStale) setStale(staleAgeSec);
      } else {
        let allServices = [];
        // Advances-since-last-salary is a snapshot of the master's payout
        // history, not scoped to whatever period is being viewed here, so
        // every per-month response carries the same figure for a given
        // master -- collecting across ranges (last one wins) recovers it
        // for a multi-month view instead of discarding it.
        const advancesByMaster = {};
        for (let i = 0; i < ranges.length; i++) {
          const [f, t] = ranges[i];
          setLoadProgress({ done: i, total: ranges.length, label: f.slice(0, 7) });
          try {
            const { services, salary_summary, stale: isStale, staleAgeSec } = await fetchOneRange(f, t);
            allServices = allServices.concat(services);
            for (const s of salary_summary || []) {
              if (s.advances_since_last_salary != null) {
                advancesByMaster[s.master] = s.advances_since_last_salary;
              }
            }
            if (isStale) setStale((prev) => Math.max(prev || 0, staleAgeSec));
          } catch (e) {
            const detail = e.response?.data?.detail || e.message || 'Ошибка загрузки';
            throw new Error(`${f.slice(0, 7)}: ${detail}`);
          }
        }
        setRows(allServices);
        // total_salary/services_done/etc. in salary_summary are still period-
        // scoped to the last range fetched, and MastersSummaryTable already
        // recomputes those correctly from allServices -- only the advances
        // figure is range-independent, so that's the only part carried over.
        setSalarySummary(
          Object.entries(advancesByMaster).map(([master, advances_since_last_salary]) => (
            { master, advances_since_last_salary }
          )),
        );
      }
      setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
      setLoadProgress(null);
    }
  }

  function toggleSort(col) {
    if (sortCol === col) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  }

  const filtered = useMemo(() => {
    let r = rows;
    if (statusFilter.size > 0) r = r.filter((x) => statusFilter.has(x.status));
    if (warningsOnly) r = r.filter((x) => x.warnings?.length > 0);
    if (warningTypeFilter.size > 0) r = r.filter((x) => [...warningTypeFilter].some((k) => x[k]));
    if (categoryFilter.size > 0) r = r.filter((x) => x.top_parent_name && categoryFilter.has(x.top_parent_name));
    if (masterFilter.size > 0) r = r.filter((x) => masterFilter.has(x.description));
    if (nameSearch)   r = r.filter((x) => (x.name || '').toLowerCase().includes(nameSearch.toLowerCase()));
    if (docSearch)    r = r.filter((x) => (x.doc_num || '').toLowerCase().includes(docSearch.toLowerCase()));
    if (codeSearch) {
      const tokens = codeSearch.split(/[,;\s]+/).filter(Boolean);
      r = r.filter((x) => {
        const c = (x.code || '').toLowerCase();
        return tokens.some((t) => t.endsWith('.') ? c.startsWith(t.toLowerCase()) : c.includes(t.toLowerCase()));
      });
    }
    if (durationFilter !== 'all') {
      const opt = DURATION_OPTIONS.find((o) => o.value === durationFilter);
      if (opt) r = r.filter((x) => opt.test(x.duration_min));
    }
    if (dayFilter != null) {
      r = r.filter((x) => {
        const t = x.out_time || x.in_time;
        const d = t && new Date(t);
        return d && !isNaN(d) && d.getDay() === dayFilter;
      });
    }
    return r;
  }, [rows, statusFilter, warningsOnly, warningTypeFilter, categoryFilter, masterFilter, nameSearch, docSearch, codeSearch, durationFilter, dayFilter]);

  const sorted = useMemo(() => {
    if (!sortCol) return filtered;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...filtered].sort((a, b) => {
      const av = a[sortCol] ?? '';
      const bv = b[sortCol] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv), 'ru') * dir;
    });
  }, [filtered, sortCol, sortDir]);

  const kpi = useMemo(() => {
    const orderMap = {};
    filtered.forEach((r) => {
      if (!r.doc_num) return;
      if (!orderMap[r.doc_num]) orderMap[r.doc_num] = [];
      orderMap[r.doc_num].push(r.status);
    });
    const orders = Object.values(orderMap);
    let totalKredit = 0, totalSalary = 0;
    filtered.forEach((r) => {
      if (r.master_salary == null) return;
      totalKredit += Number(r.kredit) || 0;
      totalSalary += Number(r.master_salary) || 0;
    });
    return {
      total:        filtered.length,
      done:         filtered.filter((x) => x.status === 'Выполнено').length,
      inWork:       filtered.filter((x) => x.status === 'В работе').length,
      warnings:     filtered.filter((x) => x.warnings?.length > 0).length,
      masters:      new Set(filtered.map((x) => x.description).filter(Boolean)).size,
      ordersTotal:  orders.length,
      ordersDone:   orders.filter((s) => s.every((v) => v === 'Выполнено')).length,
      ordersInWork: orders.filter((s) => s.some((v) => v === 'В работе')).length,
      totalKredit,
      totalSalary,
    };
  }, [filtered]);

  const topMastersChart = useMemo(() => {
    const map = {};
    filtered.forEach((r) => {
      if (r.master_salary == null) return;
      const name = r.out_description || r.description || '—';
      if (!map[name]) map[name] = { master: name, total_salary: 0 };
      map[name].total_salary += Number(r.master_salary) || 0;
    });
    return Object.values(map).sort((a, b) => b.total_salary - a.total_salary).slice(0, 8);
  }, [filtered]);

  const statusDonutData = useMemo(() => {
    // Выполнено — норма и 92% объёма: ярко-зелёное кольцо почти целиком
    // окрашивало экран в «успех», а «в работе» янтарным читалось как
    // проблема, хотя это просто текущая стадия.
    const colors = { 'Выполнено': 'color-mix(in srgb, var(--color-text) 26%, transparent)', 'В работе': 'var(--color-primary)', 'Прочее': 'var(--fui-processing)' };
    const counts = {};
    filtered.forEach((r) => {
      const s = r.status || 'Прочее';
      counts[s] = (counts[s] || 0) + 1;
    });
    return Object.entries(counts).map(([name, value]) => ({ name, value, color: colors[name] || 'var(--color-text-muted)' }));
  }, [filtered]);

  const categoryDonutData = useMemo(() => {
    const map = {};
    filtered.forEach((r) => {
      if (r.master_salary == null) return;
      const cat = r.top_parent_name || 'Прочее';
      map[cat] = (map[cat] || 0) + (Number(r.kredit) || 0);
    });
    const entries = Object.entries(map).sort((a, b) => b[1] - a[1]);
    const top = entries.slice(0, 7);
    const rest = entries.slice(7).reduce((s, [, v]) => s + v, 0);
    const data = top.map(([name, value]) => ({ name, value }));
    if (rest > 0) data.push({ name: 'Прочие', value: rest });
    return data;
  }, [filtered]);

  const dayHeatmapData = useMemo(() => {
    const map = Array.from({ length: 7 }, (_, i) => ({ day: DAY_NAMES[i], count: 0 }));
    filtered.forEach((r) => {
      const t = r.out_time || r.in_time;
      if (!t) return;
      const d = new Date(t);
      if (!isNaN(d)) map[d.getDay()].count++;
    });
    return map;
  }, [filtered]);

  async function loadApprentices() {
    setApprenticesLoading(true);
    setApprenticesError(null);
    try {
      const res = await api.get('/masters/apprentices', { params: { date_from: dateFrom, date_to: dateTo } });
      setApprentices(res.data.apprentices || []);
      setApprenticesLoadedRange(`${dateFrom}_${dateTo}`);
    } catch (e) {
      setApprenticesError(e?.response?.data?.detail || 'Не удалось загрузить стипендии учеников');
    } finally {
      setApprenticesLoading(false);
    }
  }

  // Лёгкий запрос (одна таблица турникета, без джойнов на доки/услуги
  // мастеров), в отличие от «works» выше — грузим сам при открытии
  // вкладки или смене периода, не дожидаясь отдельного клика.
  useEffect(() => {
    if (tab !== 'apprentices') return;
    if (apprenticesLoadedRange === `${dateFrom}_${dateTo}`) return;
    loadApprentices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, dateFrom, dateTo]);

  function downloadCsv() {
    if (!filtered.length) return;
    const cols = ['status', 'description', 'doc_num', 'code', 'name', 'service_group', 'in_time', 'out_time', 'duration_min', 'master_salary', 'warnings'];
    const header = cols.join(';');
    const body = filtered.map((r) => cols.map((c) => (r[c] ?? '')).join(';')).join('\n');
    const blob = new Blob(['﻿' + header + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'masters_works.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  const sortLabel = (col, text) => (
    <button
      type="button"
      onClick={() => toggleSort(col)}
      className="cursor-pointer select-none hover:text-[color:var(--color-text-primary)] transition-colors inline-flex items-center bg-transparent border-0 p-0"
    >
      {text}
      <SortIcon col={col} sortCol={sortCol} sortDir={sortDir} />
    </button>
  );

  const tabs = [
    { key: 'overview', label: 'Обзор', icon: <ListChecks size={15} /> },
    { key: 'services', label: 'Список услуг', icon: <Receipt size={15} />, badge: filtered.length },
    { key: 'apprentices', label: 'Ученики', icon: <GraduationCap size={15} />, badge: apprentices.length || undefined },
  ];

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-12">
      <TopProgressBar active={loading} />
      {/* Header */}
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          {/* Иконка из заголовка убрана: она дублировала подсвеченный
              пункт меню и конкурировала с крупным начертанием. Период
              вынесен наверх — от него зависят все цифры ниже. */}
          <span className="ui-eyebrow mb-3">Период · {dateFrom} — {dateTo}</span>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)]">
            Зарплата мастеров
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-2 max-w-[60ch]">
            Работы по чек-ин/чек-аут, длительность, нарушения и расчёт зарплаты
          </p>
        </div>
      </div>

      {/* Панель периода одной строкой-прибором. Раньше здесь стояли
          .app-card и flex одновременно, но .app-card задаёт display:grid
          и грузится после утилит — flex не применялся, и два поля с
          двумя кнопками выстраивались столбиком во всю ширину, а
          «Загрузить» весила как главное действие страницы. */}
      <div className="mas-bar">
        <label className="mas-bar__f">
          <span className="mas-bar__k">Период с</span>
          <input type="date" className="input" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </label>
        <label className="mas-bar__f">
          <span className="mas-bar__k">по</span>
          <input type="date" className="input" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </label>
        <span className="mas-bar__gap" />
        <button className="btn btn--secondary btn--sm" onClick={downloadCsv} disabled={!filtered.length}>
          <Download size={14} /> CSV
        </button>
        <button className="btn btn--primary btn--sm" onClick={load} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {loaded ? 'Обновить' : 'Загрузить'}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
          {error}
        </div>
      )}

      {stale != null && (
        <div className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-amber-800 text-sm">
          База Agbis сейчас перегружена, свежий запрос не успел отработать.
          Показаны последние удачно полученные данные
          {stale >= 60 ? ` — ${Math.round(stale / 60)} мин назад` : ' — меньше минуты назад'}.
          Повторная загрузка через пару минут обычно проходит.
        </div>
      )}

      {/* Tabs — вкладка «Ученики» не зависит от тяжёлой загрузки works
          выше, поэтому переключатель виден сразу, а не только после
          первого «Загрузить». */}
      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {!loaded && !loading && tab !== 'apprentices' && (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
          <Hammer size={28} className="mx-auto mb-2 opacity-60" />
          Выберите период и нажмите <strong>Загрузить</strong>
        </div>
      )}

      {loading && loadProgress && tab !== 'apprentices' && (
        <div className="app-card p-3 flex items-center gap-3 text-sm">
          <RefreshCw size={14} className="animate-spin shrink-0" />
          <div className="flex-1">
            <div className="flex items-center justify-between mb-1">
              <span>Большой период — загружаю по месяцам: {loadProgress.label}</span>
              <span className="text-[color:var(--color-muted-foreground)]">{loadProgress.done}/{loadProgress.total}</span>
            </div>
            <div className="h-1.5 rounded-full bg-[color:var(--color-bg-secondary)] overflow-hidden">
              <div className="h-full rounded-full bg-[color:var(--color-primary)] transition-all duration-300"
                style={{ width: `${(loadProgress.done / loadProgress.total) * 100}%` }} />
            </div>
          </div>
        </div>
      )}
      {loading && tab !== 'apprentices' && <SkeletonTable rows={8} />}

      {tab === 'apprentices' && (
        <div className="space-y-4">
          {apprenticesError && (
            <div className="rounded-lg bg-red-50 border border-red-200 p-4 text-red-700 text-sm">
              {apprenticesError}
            </div>
          )}
          {apprenticesLoading ? (
            <SkeletonTable rows={4} />
          ) : apprentices.length === 0 ? (
            <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">
              <GraduationCap size={28} className="mx-auto mb-2 opacity-60" />
              {apprenticesError ? 'Не удалось загрузить данные' : 'Нет сотрудников с должностью «Ученик мастера»'}
            </div>
          ) : (
            <>
              <section className="app-card overflow-hidden">
                <div className="p-5 sm:p-6">
                  <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                    Стипендия учеников · {apprentices.length} {apprentices.length === 1 ? 'ученик' : 'учеников'}
                  </div>
                  <div className="mas-total">
                    {Math.round(apprentices.reduce((s, a) => s + (a.to_pay || 0), 0)).toLocaleString('ru-RU')}<small>₽</small>
                  </div>
                  <div className="mt-1 text-sm text-[color:var(--color-muted-foreground)]">
                    к выплате за период, за вычетом авансов
                  </div>
                </div>
                <div className="px-5 sm:px-6 py-4 border-t border-[color:var(--color-border)] flex flex-wrap items-center gap-x-4 gap-y-3">
                  <Term label="Дней обучения всего" value={apprentices.reduce((s, a) => s + (a.days_count || 0), 0)} fmt={(v) => String(v)} />
                  <Term op="·" label="Стипендия начислена" value={apprentices.reduce((s, a) => s + (a.stipend || 0), 0)} />
                  <Term op="−" label="Авансы с посл. ЗП" value={apprentices.reduce((s, a) => s + (a.advances_since_last_salary || 0), 0)} />
                </div>
              </section>

              {isMobile ? (
                <div className="space-y-3">
                  {apprentices.map((a) => (
                    <div key={a.employee_id} className="border rounded-xl bg-[color:var(--color-surface)] shadow-sm overflow-hidden">
                      <div className="px-4 py-3 border-b bg-[color:var(--color-bg-subtle)] text-sm font-medium">{a.name}</div>
                      <div className="px-4 py-2 space-y-1.5 text-sm">
                        <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Дней обучения</span><span>{a.days_count}</span></div>
                        <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Ставка</span><span className="text-[color:var(--color-muted-foreground)]">{fmtRub(a.rate)}/день</span></div>
                        <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">Стипендия</span><span className="font-semibold text-[color:var(--color-primary)]">{fmtRub(a.stipend)}</span></div>
                        <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]" title="Авансы («Выплачено»/«Одобрено»), выданные после последней выплаты типа «Зарплата»">Аванс с посл. ЗП</span><span className="text-amber-600">{fmtRub(a.advances_since_last_salary)}</span></div>
                        <div className="flex justify-between"><span className="text-[color:var(--color-text-muted)]">К выплате</span><span className="font-semibold text-emerald-600">{fmtRub(a.to_pay)}</span></div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="app-card overflow-x-auto">
                  <table className="w-full text-sm min-w-[620px]">
                    <thead>
                      <tr className="border-b border-[color:var(--color-border)] text-[color:var(--color-muted-foreground)]">
                        <th className="px-4 py-2 text-left">Ученик</th>
                        <th className="px-4 py-2 text-right">Дней обучения</th>
                        <th className="px-4 py-2 text-right">Ставка</th>
                        <th className="px-4 py-2 text-right text-[color:var(--color-primary)]">Стипендия</th>
                        <th className="px-4 py-2 text-right text-amber-600" title="Авансы («Выплачено»/«Одобрено»), выданные после последней выплаты типа «Зарплата»">Аванс с посл. ЗП</th>
                        <th className="px-4 py-2 text-right text-emerald-600">К выплате</th>
                      </tr>
                    </thead>
                    <tbody>
                      {apprentices.map((a, i) => (
                        <tr key={a.employee_id} className={i % 2 === 1 ? 'bg-[color:var(--color-muted)]/30' : ''}>
                          <td className="px-4 py-2 font-medium">{a.name}</td>
                          <td className="px-4 py-2 text-right">{a.days_count}</td>
                          <td className="px-4 py-2 text-right text-[color:var(--color-muted-foreground)]">{fmtRub(a.rate)}/день</td>
                          <td className="px-4 py-2 text-right font-semibold text-[color:var(--color-primary)]">{fmtRub(a.stipend)}</td>
                          <td className="px-4 py-2 text-right text-amber-600">{fmtRub(a.advances_since_last_salary)}</td>
                          <td className="px-4 py-2 text-right font-semibold text-emerald-600">{fmtRub(a.to_pay)}</td>
                        </tr>
                      ))}
                      <tr className="border-t border-[color:var(--color-border)] font-semibold bg-[color:var(--color-muted)]/20">
                        <td className="px-4 py-2">Итого</td>
                        <td className="px-4 py-2 text-right">{apprentices.reduce((s, a) => s + (a.days_count || 0), 0)}</td>
                        <td className="px-4 py-2 text-right" />
                        <td className="px-4 py-2 text-right text-[color:var(--color-primary)]">{fmtRub(apprentices.reduce((s, a) => s + (a.stipend || 0), 0))}</td>
                        <td className="px-4 py-2 text-right text-amber-600">{fmtRub(apprentices.reduce((s, a) => s + (a.advances_since_last_salary || 0), 0))}</td>
                        <td className="px-4 py-2 text-right text-emerald-600">{fmtRub(apprentices.reduce((s, a) => s + (a.to_pay || 0), 0))}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {loaded && !loading && tab !== 'apprentices' && (
        <>
          {/* Hero: payout summary */}
          <section className="app-card overflow-hidden">
            <div className="p-5 sm:p-6">
              <div className="text-xs uppercase tracking-wide text-[color:var(--color-muted-foreground)]">
                Зарплата мастеров · {kpi.masters} {kpi.masters === 1 ? 'мастер' : 'мастеров'}
              </div>
              {/* Деньги набраны основным цветом, а не акцентом: фиолетовый
                  в этой системе означает активное состояние, а сумма —
                  величина. Масса даётся размером, знак рубля — лёгким
                  начертанием, как на дашборде и в выплатах. */}
              <div className="mas-total">
                {Math.round(kpi.totalSalary ?? 0).toLocaleString('ru-RU')}<small>₽</small>
              </div>
              <div className="mt-1 text-sm text-[color:var(--color-muted-foreground)]">
                {kpi.done} услуг учтено в ЗП за период
              </div>
            </div>
            <div className="px-5 sm:px-6 py-4 border-t border-[color:var(--color-border)] flex flex-wrap items-center gap-x-4 gap-y-3">
              <Term label="Услуг всего" value={kpi.total} fmt={(v) => String(v)} />
              <Term op="·" label="Учтено в ЗП" value={kpi.done} fmt={(v) => String(v)} />
              <Term op="·" label="Сумма услуг" value={kpi.totalKredit} />
              {/* Итог формулы не повторяет заголовок цветом и жиром: та же
                  сумма уже стоит крупно строкой выше, и второй фиолетовый
                  экземпляр делал из вывода второй заголовок. */}
              <Term op="=" label="Зарплата" value={kpi.totalSalary} strong />
            </div>
          </section>

          {tab === 'overview' && (
            <div className="space-y-7">
              {/* Восемь одинаковых карточек в двух сетках сведены в одну
                  решётку: услуги и заказы — один класс информации, и
                  разделять их подзаголовками значило дважды объяснять то,
                  что видно по подписям. Цвет остался единственному
                  показателю, который требует действия. */}
              <div className="fui-lattice">
                <button
                  type="button"
                  style={{ '--sig': 'var(--color-danger)' }}
                  className={`fui-cellstat fui-cellstat--lead fui-press ${kpi.warnings ? 'fui-cellstat--sig' : ''}`}
                  onClick={() => setWarningsOnly((v) => !v)}
                >
                  <span className="fui-cellstat__k">
                    <AlertTriangle size={12} className="mr-1.5 inline-block align-[-1px]" style={{ color: 'var(--color-danger)' }} />
                    Нарушений
                  </span>
                  <span className="fui-cellstat__v">{kpi.warnings}</span>
                  <span className="fui-cellstat__m">{warningsOnly ? 'фильтр вкл.' : 'нажмите, чтобы отфильтровать'}</span>
                </button>
                <div className="fui-cellstat">
                  <span className="fui-cellstat__k">Услуг всего</span>
                  <span className="fui-cellstat__v">{kpi.total}</span>
                  <span className="fui-cellstat__m">выполнено {kpi.done} · в работе {kpi.inWork}</span>
                </div>
                <div className="fui-cellstat">
                  <span className="fui-cellstat__k">Заказов</span>
                  <span className="fui-cellstat__v">{kpi.ordersTotal}</span>
                  <span className="fui-cellstat__m">выполнено {kpi.ordersDone} · в работе {kpi.ordersInWork}</span>
                </div>
                <div className="fui-cellstat">
                  <span className="fui-cellstat__k">Мастеров</span>
                  <span className="fui-cellstat__v">{kpi.masters}</span>
                  <span className="fui-cellstat__m">в смене за период</span>
                </div>
              </div>

              {(topMastersChart.length > 0 || statusDonutData.length > 0) && (
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <div className="lg:col-span-2">
                    <TopMastersChart data={topMastersChart} activeNames={masterFilter} onSelect={(name) => { toggleMaster(name); setTab('services'); }} />
                  </div>
                  <StatusDonut data={statusDonutData} total={kpi.total} activeNames={statusFilter} onSelect={(name) => { toggleStatus(name); setTab('services'); }} />
                </div>
              )}

              {(categoryDonutData.length > 0 || dayHeatmapData.some((d) => d.count > 0)) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <CategoryDonut data={categoryDonutData} total={kpi.totalKredit} activeNames={categoryFilter} onSelect={(name) => { toggleCategory(name); setTab('services'); }} />
                  <ServiceDayHeatmap data={dayHeatmapData} activeDay={dayFilter} onSelect={(i) => { setDayFilter((prev) => (prev === i ? null : i)); setTab('services'); }} />
                </div>
              )}

              {(nameSearch || masterFilter.size > 0 || masterSearchText || categoryFilter.size > 0) && (
                <div className="app-card p-3 flex flex-wrap items-center gap-2 text-xs">
                  <span className="text-[color:var(--color-muted-foreground)]">Медиана ниже посчитана с учётом активных фильтров:</span>
                  {nameSearch && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                      Услуга: «{nameSearch}»
                      <button onClick={() => setNameSearch('')} className="hover:opacity-70"><X size={11} /></button>
                    </span>
                  )}
                  {masterFilter.size > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                      Мастеров выбрано: {masterFilter.size}
                      <button onClick={() => setMasterFilter(new Set())} className="hover:opacity-70"><X size={11} /></button>
                    </span>
                  )}
                  {masterSearchText && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                      Мастер: «{masterSearchText}»
                      <button onClick={() => setMasterSearchText('')} className="hover:opacity-70"><X size={11} /></button>
                    </span>
                  )}
                  {categoryFilter.size > 0 && (
                    <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                      Категорий: {categoryFilter.size}
                      <button onClick={() => setCategoryFilter(new Set())} className="hover:opacity-70"><X size={11} /></button>
                    </span>
                  )}
                </div>
              )}
              <MastersSummaryTable rows={filtered} onMasterClick={(name) => toggleMaster(name)} advancesByMaster={advancesByMaster} />
            </div>
          )}

          {tab === 'services' && (
            <div className="space-y-4">
              {dayFilter != null && (
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-[color:var(--color-muted-foreground)]">Фильтр из графика:</span>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[color:var(--color-primary-muted)] text-[color:var(--color-primary)] font-medium">
                    {DAY_NAMES[dayFilter]}
                    <button onClick={() => setDayFilter(null)} className="hover:opacity-70"><X size={12} /></button>
                  </span>
                </div>
              )}
              {/* Filters */}
              <div className="app-card p-4 space-y-3">
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">
                      Статус
                      {statusFilter.size > 0 && (
                        <button onClick={() => setStatusFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                          сбросить
                        </button>
                      )}
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {STATUS_OPTIONS.map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => toggleStatus(s)}
                          className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                            statusFilter.has(s)
                              ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                              : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                          }`}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Услуга (влияет на медиану в «Обзоре»)</label>
                    <input className="input w-full" placeholder="напр. набойки" value={nameSearch} onChange={(e) => setNameSearch(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Заказ</label>
                    <input className="input w-full" placeholder="Номер заказа..." value={docSearch} onChange={(e) => setDocSearch(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Код (через запятую, или с точкой)</label>
                    <input className="input w-full" placeholder="2.17, 3." value={codeSearch} onChange={(e) => setCodeSearch(e.target.value)} />
                  </div>
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Длительность</label>
                    <select className="input w-full" value={durationFilter} onChange={(e) => setDurationFilter(e.target.value)}>
                      {DURATION_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
                {masterNames.length > 0 && (
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
                      Мастера (мультивыбор)
                      {masterFilter.size > 0 && (
                        <button onClick={() => setMasterFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                          сбросить ({masterFilter.size})
                        </button>
                      )}
                    </label>
                    {masterNames.length > 8 && (
                      <div className="relative mb-1.5">
                        <Search size={14} style={{ position:'absolute', left:'10px', top:'50%', transform:'translateY(-50%)', pointerEvents:'none' }} className="text-[color:var(--color-muted-foreground)]" />
                        <input className="input w-full" style={{ paddingLeft:'2rem' }} placeholder="Найти мастера в списке..." value={masterSearchText} onChange={(e) => setMasterSearchText(e.target.value)} />
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      {visibleMasterNames.map((n) => (
                        <button
                          key={n}
                          type="button"
                          onClick={() => toggleMaster(n)}
                          className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                            masterFilter.has(n)
                              ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                              : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                      {visibleMasterNames.length === 0 && (
                        <span className="text-xs text-[color:var(--color-muted-foreground)]">Ничего не найдено</span>
                      )}
                    </div>
                  </div>
                )}
                {categoryOptions.length > 0 && (
                  <div>
                    <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
                      Категория услуги
                      {categoryFilter.size > 0 && (
                        <button onClick={() => setCategoryFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                          сбросить
                        </button>
                      )}
                    </label>
                    <div className="flex flex-wrap gap-1.5">
                      {categoryOptions.map((cat) => (
                        <button
                          key={cat}
                          onClick={() => toggleCategory(cat)}
                          className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                            categoryFilter.has(cat)
                              ? 'bg-[color:var(--color-primary)] text-white border-[color:var(--color-primary)]'
                              : 'border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)]'
                          }`}
                        >
                          {cat}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div>
                  <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1.5">
                    Тип нарушения
                    {warningTypeFilter.size > 0 && (
                      <button onClick={() => setWarningTypeFilter(new Set())} className="ml-2 text-[color:var(--color-primary)] hover:underline">
                        сбросить
                      </button>
                    )}
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {WARNING_TYPES.map(({ key, label }) => (
                      <button
                        key={key}
                        onClick={() => toggleWarningType(key)}
                        className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                          warningTypeFilter.has(key)
                            ? 'bg-amber-500 text-white border-amber-500'
                            : 'border-[color:var(--color-border)] hover:border-amber-400 hover:text-amber-600'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Full table */}
              <div className="app-card">
                <div className="p-4 border-b border-[color:var(--color-border)] flex items-center justify-between">
                  <h3 className="font-semibold">Список услуг</h3>
                  <span className="text-sm text-[color:var(--color-muted-foreground)]">{filtered.length} строк</span>
                </div>

                <ResponsiveTable
                  data={sorted.slice(0, 500)}
                  keyFn={(r) => r.service_id ?? `${r.doc_num}-${r.code}-${r.in_time}`}
                  rowState={(r) => (r.warnings?.length > 0 ? 'warning' : null)}
                  emptyText="Работ за период нет" emptyHint="Расчёт строится по чек-инам мастеров — проверьте даты."
                  columns={[
                    {
                      key: 'status',
                      label: sortLabel('status', 'Статус'),
                      render: (r) => (
                        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[r.status] || STATUS_COLORS['Прочее']}`}>
                          {r.status}
                        </span>
                      ),
                    },
                    {
                      key: 'warning',
                      label: '',
                      render: (r) => (
                        r.warnings?.length > 0 && (
                          <span title={r.warnings.join('\n')} className="cursor-help">
                            <AlertTriangle size={14} className="text-amber-500" />
                          </span>
                        )
                      ),
                    },
                    {
                      key: 'description',
                      label: sortLabel('description', 'Мастер'),
                      primary: true,
                      render: (r) => fmt(r.description),
                    },
                    {
                      key: 'doc_num',
                      label: sortLabel('doc_num', 'Заказ'),
                      cellClass: 'text-[color:var(--color-muted-foreground)]',
                      render: (r) => fmt(r.doc_num),
                    },
                    {
                      key: 'code',
                      label: sortLabel('code', 'Код'),
                      mobileHide: true,
                      cellClass: 'font-mono text-xs',
                      render: (r) => fmt(r.code),
                    },
                    {
                      key: 'name',
                      label: sortLabel('name', 'Услуга'),
                      render: (r) => fmt(r.name),
                    },
                    {
                      key: 'service_group',
                      label: sortLabel('service_group', 'Группа'),
                      mobileHide: true,
                      cellClass: 'text-[color:var(--color-muted-foreground)]',
                      render: (r) => fmt(r.service_group),
                    },
                    {
                      key: 'in_time',
                      label: sortLabel('in_time', 'Приём'),
                      numeric: true,
                      cellClass: 'text-[color:var(--color-muted-foreground)]',
                      render: (r) => fmtDt(r.in_time),
                    },
                    {
                      key: 'out_time',
                      label: sortLabel('out_time', 'Выдача'),
                      numeric: true,
                      cellClass: 'text-[color:var(--color-muted-foreground)]',
                      render: (r) => fmtDt(r.out_time),
                    },
                    {
                      key: 'duration_min',
                      label: sortLabel('duration_min', 'Длит.'),
                      numeric: true,
                      render: (r) => fmtMin(r.duration_min),
                    },
                    {
                      key: 'master_salary',
                      label: sortLabel('master_salary', 'ЗП'),
                      numeric: true,
                      cellClass: 'font-medium text-[color:var(--color-primary)]',
                      render: (r) => fmtRub(r.master_salary),
                    },
                  ]}
                />
                {filtered.length > 500 && (
                  <div className="px-4 py-3 text-center text-sm text-[color:var(--color-muted-foreground)] border-t border-[color:var(--color-border)]">
                    Показано первые 500 из {filtered.length}. Используйте фильтры или скачайте CSV.
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
