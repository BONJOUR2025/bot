import { useState, useMemo, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  RefreshCw, Download, EyeOff, Eye, ChevronDown, Check,
  TrendingUp, TrendingDown, BarChart3, Trophy, Users, Target, Calendar,
  Percent, Clock, RotateCcw, Gauge, Building2, PackageX, Phone, Package, Maximize2,
} from 'lucide-react';
import {
  ComposedChart, Area, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, Line,
  BarChart, PieChart, Pie, Cell,
} from 'recharts';
import api from '../api';
import { SkeletonTable } from '../components/ui/Skeleton.jsx';
import { TopProgressBar } from '../components/ui/ProgressBar.jsx';
import ResponsiveTable from '../components/ui/ResponsiveTable.jsx';
import { Tabs } from '../components/ui/SalaryUI.jsx';

/* ── constants ───────────────────────────────────────────── */
function toLocalDateStr(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
const TODAY = toLocalDateStr(new Date());
const MONTHS_RU      = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
const MONTHS_KEY_RU  = ['ЯНВАРЬ','ФЕВРАЛЬ','МАРТ','АПРЕЛЬ','МАЙ','ИЮНЬ','ИЮЛЬ','АВГУСТ','СЕНТЯБРЬ','ОКТЯБРЬ','НОЯБРЬ','ДЕКАБРЬ'];
const DAY_NAMES      = ['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
const CHART_COLORS   = ['#e61919','#4af626','#ffb347','#c9502a','#6fb8ff','#9a9a9a','#ff6b5e','#37c418','#ff8c42','#d4d44a'];

// Populated from EmployeeRepository (see loadEmployeeNames in the main
// component) — employee.name in the system is "Имя КОД" (e.g. "Вера 0102"),
// the same 4-digit code Firebird's sales data is keyed by. Module-level so
// empName() stays a plain lookup usable from every subcomponent below,
// without threading the map through props everywhere it's called.
let EMP_CODE_NAMES = {};

function buildCodeNameMap(employees) {
  const map = {};
  for (const emp of employees) {
    const match = String(emp.name || '').match(/^(.*?)\s*(\d{4})$/);
    if (match) map[match[2]] = match[1].trim() || emp.name;
  }
  return map;
}

const CATEGORIES = [
  { key:'repair',    label:'Ремонт / Химчистка', color:'#e61919' },
  { key:'cosmetics', label:'Косметика',           color:'#4af626' },
  { key:'shoes',     label:'Обувь',               color:'#ffb347' },
];
const LABEL_TO_KEY = Object.fromEntries(CATEGORIES.map((c) => [c.label, c.key]));

function toggleSet(setter, key) {
  setter((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });
}

/* ── helpers ─────────────────────────────────────────────── */
const fmtRub = (v) => v == null ? '—' : Math.round(v).toLocaleString('ru-RU') + ' ₽';
const fmtPct = (v) => v == null ? '—' : v.toFixed(1) + '%';

const empName = (code) => EMP_CODE_NAMES[code] || code;

function initials(name) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2).toUpperCase();
}

function getPeriodKey(dateStr, gran) {
  if (gran === 'day')   return dateStr;
  if (gran === 'month') return dateStr.slice(0, 7);
  const d   = new Date(dateStr);
  const day = d.getDay() || 7;
  d.setDate(d.getDate() + 4 - day);
  const jan1 = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil((((d - jan1) / 86400000) + 1) / 7);
  return `${d.getFullYear()}-W${String(week).padStart(2,'0')}`;
}

function getPeriodLabel(key, gran) {
  if (gran === 'day') { const [,m,d] = key.split('-'); return `${d}.${m}`; }
  if (gran === 'month') { const [y,m] = key.split('-'); return `${MONTHS_RU[+m-1]} ${y.slice(2)}`; }
  const [yearStr, wStr] = key.split('-W');
  const jan4 = new Date(+yearStr, 0, 4);
  const mon  = new Date(jan4);
  mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1 + (+wStr - 1) * 7);
  const sun = new Date(mon); sun.setDate(mon.getDate() + 6);
  const f = (dt) => `${String(dt.getDate()).padStart(2,'0')}.${String(dt.getMonth()+1).padStart(2,'0')}`;
  return `${f(mon)}–${f(sun)}`;
}

const toMonthKey = (yyyymm) => { const [y,m] = yyyymm.split('-'); return `${MONTHS_KEY_RU[+m-1]}_${y}`; };

function getMonthsInRange(from, to) {
  const months = [];
  const cur = new Date((from || TODAY).slice(0,7) + '-01');
  const end = new Date((to   || TODAY).slice(0,7) + '-01');
  while (cur <= end) { months.push(cur.toISOString().slice(0,7)); cur.setMonth(cur.getMonth()+1); }
  return months;
}

function quickRange(key) {
  const n = new Date(); const y = n.getFullYear(), m = n.getMonth();
  if (key === 'month') return [toLocalDateStr(new Date(y, m, 1)), TODAY];
  if (key === 'prev')  return [toLocalDateStr(new Date(y, m-1, 1)), toLocalDateStr(new Date(y, m, 0))];
  if (key === 'q')     return [toLocalDateStr(new Date(y, Math.floor(m/3)*3, 1)), TODAY];
  if (key === 'year')  return [toLocalDateStr(new Date(y, 0, 1)), TODAY];
  return [TODAY, TODAY];
}

/* ── MultiSelect ─────────────────────────────────────────── */
// The dropdown is rendered via a portal into document.body rather than as a
// normal absolutely-positioned child. Reason: every .app-card has
// `backdrop-filter`, which per spec forces the card to establish its own
// stacking context — that traps this dropdown's z-index to a scope local to
// the card, so a *later* sibling card (e.g. the KPI row right below the
// filters card) paints over it in DOM order regardless of z-index. A portal
// sidesteps the whole stacking-context tree instead of trying to out-rank it.
function MultiSelect({ options, selected, onChange, placeholder = 'Все' }) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return;
    const updatePosition = () => {
      const r = btnRef.current?.getBoundingClientRect();
      if (!r) return;
      setMenuStyle({ position: 'fixed', top: r.bottom + 4, left: r.left, width: r.width, zIndex: 9999 });
    };
    updatePosition();
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const h = (e) => {
      if (btnRef.current?.contains(e.target)) return;
      if (menuRef.current?.contains(e.target)) return;
      setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, [open]);

  const allSelected = selected.size === 0;
  const label = allSelected ? placeholder : options.filter((o) => selected.has(o.value)).map((o) => o.label).join(', ');
  return (
    <div className="relative">
      <button ref={btnRef} type="button" onClick={() => setOpen((v) => !v)}
        className="input w-full text-left flex items-center justify-between gap-2 text-sm">
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className={`flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && menuStyle && createPortal(
        <div ref={menuRef} style={menuStyle}
          className="min-w-[180px] rounded-lg border border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] shadow-xl overflow-hidden max-h-64 overflow-y-auto">
          <button type="button" onClick={() => onChange(new Set())}
            className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors">
            <Check size={13} className={allSelected ? 'text-[color:var(--color-primary)]' : 'opacity-0'} />
            <span>{placeholder}</span>
          </button>
          <div className="border-t border-[color:var(--color-border)]" />
          {options.map((o) => {
            const sel = selected.has(o.value);
            return (
              <button key={o.value} type="button"
                onClick={() => { const next = new Set(selected); if (sel) next.delete(o.value); else next.add(o.value); onChange(next.size === options.length ? new Set() : next); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-[color:var(--color-muted)] transition-colors">
                <Check size={13} className={sel ? 'text-[color:var(--color-primary)]' : 'opacity-0'} />
                <span className="truncate">{o.label}</span>
              </button>
            );
          })}
        </div>,
        document.body
      )}
    </div>
  );
}

/* ── Chart tooltip ───────────────────────────────────────── */
const ChartTooltip = ({ active, payload, label, nameMap }) => {
  if (!active || !payload?.length) return null;
  const items = payload.filter((p) => p.dataKey !== '_ma');
  const ma    = payload.find((p)  => p.dataKey === '_ma');
  return (
    <div className="rounded-xl border border-[color:var(--color-border)] bg-[color:var(--color-modal-bg)] p-3 text-sm shadow-xl max-w-[260px]">
      <div className="font-semibold mb-2">{label}</div>
      {items.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 leading-6">
          <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.fill || p.color }} />
          <span className="text-[color:var(--color-muted-foreground)] truncate flex-1">{nameMap?.[p.dataKey] || p.name}:</span>
          <span className="font-medium tabular-nums">{Math.round(p.value || 0).toLocaleString('ru-RU')} ₽</span>
        </div>
      ))}
      {ma && (
        <div className="border-t border-[color:var(--color-border)] mt-1.5 pt-1.5 text-xs text-[color:var(--color-muted-foreground)]">
          MA7: {Math.round(ma.value || 0).toLocaleString('ru-RU')} ₽
        </div>
      )}
    </div>
  );
};

/* ── KPI card with left-border accent ───────────────────── */
function KpiStat({ label, value, delta, sub, accent = '#e61919', icon }) {
  const up = delta != null && delta > 0;
  const dn = delta != null && delta < 0;
  return (
    <div className="app-card p-4" style={{ borderLeft: `3px solid ${accent}` }}>
      <div className="flex gap-3">
        {icon && <div className="mt-0.5 shrink-0" style={{ color: accent }}>{icon}</div>}
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] font-medium">{label}</div>
          <div className="text-xl sm:text-2xl font-bold tabular-nums mt-0.5 leading-tight" style={{ color: accent }}>{value}</div>
          <div className="flex items-center gap-2 mt-0.5 flex-wrap">
            {delta != null && Math.abs(delta) >= 0.1 && (
              <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full ${up ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400' : 'bg-red-50 dark:bg-red-900/30 text-red-500 dark:text-red-400'}`}>
                {up ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                {up ? '+' : ''}{delta.toFixed(1)}%
              </span>
            )}
            {sub && <span className="text-[11px] text-[color:var(--color-muted-foreground)]">{sub}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Donut label ─────────────────────────────────────────── */
const RADIAN = Math.PI / 180;
function DonutLabel({ cx, cy, midAngle, innerRadius, outerRadius, percent }) {
  if (percent < 0.06) return null;
  const r = innerRadius + (outerRadius - innerRadius) * 0.5;
  const x = cx + r * Math.cos(-midAngle * RADIAN);
  const y = cy + r * Math.sin(-midAngle * RADIAN);
  return (
    <text x={x} y={y} fill="white" textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={700}>
      {`${(percent * 100).toFixed(0)}%`}
    </text>
  );
}

/* ── Employee avatar chip ────────────────────────────────── */
function EmpAvatar({ name, color, size = 32 }) {
  return (
    <div className="rounded-full flex items-center justify-center text-white font-bold shrink-0"
      style={{ width: size, height: size, background: color, fontSize: size * 0.34 }}>
      {initials(name)}
    </div>
  );
}

/* ── 3-color category breakdown bar ─────────────────────── */
function CatBar({ repair, cosmetics, shoes }) {
  const total = (repair||0) + (cosmetics||0) + (shoes||0);
  if (total === 0) return <div className="h-1.5 rounded-full bg-[color:var(--color-border)] w-full" />;
  return (
    <div className="flex h-1.5 rounded-full overflow-hidden w-full gap-px">
      {repair    > 0 && <div style={{ flex: repair,    background: '#e61919' }} />}
      {cosmetics > 0 && <div style={{ flex: cosmetics, background: '#4af626' }} />}
      {shoes     > 0 && <div style={{ flex: shoes,     background: '#ffb347' }} />}
    </div>
  );
}

/* ── Employee leaderboard ────────────────────────────────── */
function Leaderboard({ empSummary, planTotals, activeCodes, onSelect }) {
  const maxTotal = empSummary.length > 0 ? empSummary[0].total : 1;
  const medals   = ['🥇', '🥈', '🥉'];
  return (
    <div className="app-card overflow-hidden">
      <div className="px-5 py-3.5 border-b border-[color:var(--color-border)] flex items-center gap-2">
        <Trophy size={16} className="text-amber-500" />
        <h3 className="font-semibold">Рейтинг сотрудников</h3>
        <span className="ml-auto text-xs text-[color:var(--color-muted-foreground)]">{empSummary.length} чел.</span>
      </div>
      <div className="divide-y divide-[color:var(--color-border)]">
        {empSummary.map((e, i) => {
          const plan  = planTotals[e.code] || 0;
          const pct   = plan > 0 ? e.total / plan * 100 : null;
          const share = maxTotal > 0 ? e.total / maxTotal : 0;
          const color = CHART_COLORS[i % CHART_COLORS.length];
          const isActive = activeCodes?.has(e.code);
          return (
            <button
              key={e.code}
              type="button"
              onClick={() => onSelect?.(e.code)}
              className={`w-full text-left px-5 py-3 flex items-center gap-3 transition-colors ${onSelect ? 'hover:bg-[color:var(--color-muted)]/30 cursor-pointer' : ''} ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
            >
              <span className="w-7 text-center text-lg leading-none shrink-0">
                {medals[i] ?? <span className="text-sm font-semibold text-[color:var(--color-muted-foreground)]">{i+1}</span>}
              </span>
              <EmpAvatar name={empName(e.code)} color={color} size={36} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-sm truncate">{empName(e.code)}</span>
                  <span className="font-bold tabular-nums text-sm shrink-0" style={{ color }}>{fmtRub(e.total)}</span>
                </div>
                <div className="mt-1.5 h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: color }} />
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <CatBar repair={e.repair} cosmetics={e.cosmetics} shoes={e.shoes} />
                  {pct != null && (
                    <span className={`text-[10px] font-semibold shrink-0 ${pct >= 100 ? 'text-emerald-600' : pct >= 75 ? 'text-amber-500' : 'text-red-500'}`}>
                      {pct.toFixed(0)}% пл.
                    </span>
                  )}
                </div>
              </div>
              <div className="text-xs text-[color:var(--color-muted-foreground)] shrink-0 text-right hidden sm:block leading-5">
                <div>{e.activeDays} дн.</div>
                <div className="text-[10px]">{fmtRub(e.activeDays > 0 ? e.total / e.activeDays : 0)}/дн</div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── Day-of-week heatmap bars ────────────────────────────── */
function DayHeatmap({ data }) {
  const maxAvg = Math.max(...data.map((d) => d.avg), 1);
  return (
    <div className="app-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Calendar size={15} className="text-[color:var(--color-muted-foreground)]" />
        <h3 className="font-semibold text-sm">По дням недели</h3>
        <span className="text-xs text-[color:var(--color-muted-foreground)]">ср. выручка за день</span>
      </div>
      <div className="flex items-end gap-2" style={{ height: 96 }}>
        {data.map((d, i) => {
          const h   = maxAvg > 0 ? Math.max((d.avg / maxAvg) * 100, d.count > 0 ? 5 : 0) : 0;
          const wkd = i >= 5;
          return (
            <div key={d.name} className="flex-1 flex flex-col items-center gap-1 group" title={`${d.name}: ${fmtRub(d.avg)} / ${d.count} дн.`}>
              <div className="w-full flex items-end rounded-t-sm overflow-hidden" style={{ height: 72 }}>
                <div className="w-full rounded-t-md transition-all group-hover:opacity-70"
                  style={{
                    height: `${h}%`,
                    background: wkd ? '#ffb347' : '#e61919',
                  }}
                />
              </div>
              <span className="text-[10px] font-semibold text-[color:var(--color-muted-foreground)]">{d.name}</span>
              <span className="text-[9px] tabular-nums text-[color:var(--color-text-primary)]">
                {d.count > 0 ? Math.round(d.avg).toLocaleString('ru-RU') : '—'}
              </span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 mt-3 text-[10px] text-[color:var(--color-muted-foreground)]">
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:'#e61919'}} /> Будни</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{background:'#ffb347'}} /> Выходные</span>
      </div>
    </div>
  );
}

/* ── Plan fulfillment horizontal gauge bars ──────────────── */
function PlanGauges({ empSummary, planTotals }) {
  const withPlan = empSummary.filter((e) => (planTotals[e.code] || 0) > 0);
  if (withPlan.length === 0) return null;
  return (
    <div className="app-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Target size={15} className="text-[color:var(--color-muted-foreground)]" />
        <h3 className="font-semibold text-sm">Выполнение плана</h3>
      </div>
      <div className="space-y-3">
        {withPlan.map((e, i) => {
          const plan = planTotals[e.code];
          const pct  = Math.min(e.total / plan * 100, 130);
          const done = e.total / plan * 100;
          const color = done >= 100 ? '#4af626' : done >= 75 ? '#ffb347' : '#c9502a';
          return (
            <div key={e.code}>
              <div className="flex items-center justify-between mb-1 text-sm">
                <span className="font-medium truncate">{empName(e.code)}</span>
                <span className="font-bold tabular-nums text-xs" style={{ color }}>
                  {done.toFixed(0)}%
                  <span className="text-[color:var(--color-muted-foreground)] font-normal"> · {fmtRub(e.total)} / {fmtRub(plan)}</span>
                </span>
              </div>
              <div className="relative h-2 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                <div className="h-full rounded-full transition-all"
                  style={{ width: `${pct}%`, background: color }} />
                {/* 100% marker */}
                <div className="absolute top-0 bottom-0 w-px bg-[color:var(--color-text-primary)]/30" style={{ left: `${100/130*100}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── Card that can expand into a fullscreen modal on click — used for
   tables whose primary column truncates long names in the compact
   layout, so a click gives the user room to read them in full ── */
function ExpandableCard({ title, subtitle, children }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <>
      <div className="app-card overflow-hidden">
        <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="font-semibold text-sm">{title}</h3>
            {subtitle}
          </div>
          <button type="button" onClick={() => setExpanded(true)} title="Развернуть на весь экран"
            className="shrink-0 p-1.5 rounded-lg hover:bg-[color:var(--color-muted)]/50 text-[color:var(--color-muted-foreground)]">
            <Maximize2 size={15} />
          </button>
        </div>
        <div className="p-3">{children(false)}</div>
      </div>
      {expanded && createPortal(
        <div className="modal-backdrop" style={{ zIndex: 9999 }} onClick={(e) => e.target === e.currentTarget && setExpanded(false)}>
          <div className="modal-card max-w-6xl w-full flex flex-col overflow-hidden" style={{ maxHeight: '92vh' }}>
            <div className="flex items-center justify-between mb-3 shrink-0">
              <h3 className="text-base font-semibold">{title}</h3>
              <button onClick={() => setExpanded(false)} className="text-xl text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-foreground)] leading-none">&times;</button>
            </div>
            <div className="overflow-auto flex-1">{children(true)}</div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

/* ── Product rank table (top/bottom/rising/falling SKUs) ── */
function ProductRankTable({ title, items, showChange }) {
  return (
    <ExpandableCard title={title}>
      {(expanded) => (
        <ResponsiveTable
          data={items}
          keyFn={(p) => p.tovar_id}
          emptyText="Нет данных"
          columns={[
            { label: 'Товар/услуга', primary: true, render: (p) => (
              expanded ? (
                <span title={p.name}>{p.name || p.code}</span>
              ) : (
                <div className="max-w-[180px] sm:max-w-[220px] truncate" title={p.name}>{p.name || p.code}</div>
              )
            )},
            { label: 'Кол-во', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (p) => p.qty.toLocaleString('ru-RU') },
            { label: 'Выручка', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (p) => fmtRub(p.revenue) },
            ...(showChange ? [{ label: 'Δ период', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (p) => (
              p.is_new ? (
                <span className="text-emerald-600">новинка</span>
              ) : p.pct_change == null ? '—' : (
                <span className={p.pct_change >= 0 ? 'text-emerald-600' : 'text-red-500'}>{p.pct_change >= 0 ? '+' : ''}{p.pct_change}%{p.pct_change === -100 ? ' (продажи остановились)' : ''}</span>
              )
            )}] : []),
          ]}
        />
      )}
    </ExpandableCard>
  );
}

/* ── Unclaimed orders tab (self-contained: its own "days" window, not the page date range) ── */
function UnclaimedTab() {
  const [days, setDays] = useState(90);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const res = await api.get('/sales/unclaimed', { params: { days } });
      setData(res.data);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally { setLoading(false); }
  }

  function exportCsv() {
    if (!data?.orders?.length) return;
    const hdr = '№ заказа;Дата приёма;Обещанная выдача;Дней просрочки;Клиент;Телефон;Сумма';
    const body = data.orders.map((o) => [o.doc_num, o.order_date, o.due_date, o.days_overdue, o.client_name || '', o.client_phone || '', o.amount].join(';')).join('\n');
    const blob = new Blob(['﻿' + hdr + '\n' + body], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); a.href = url; a.download = 'unclaimed_orders.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="app-card p-4 space-y-3">
        <p className="text-sm text-[color:var(--color-muted-foreground)]">
          Заказы, у которых обещанная дата выдачи прошла, а фактической выдачи так и не было — вещи всё ещё лежат в приёмке/химчистке.
          Полная история таких заказов уходит до 2013 года (~9 200 шт.) — почти всё это давно неактуально, поэтому окно ограничено.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Обещанная выдача — окно (дн.)</label>
            <input type="number" className="input w-28" value={days} onChange={(e) => setDays(+e.target.value)} />
          </div>
          <button onClick={load} disabled={loading} className="btn btn--primary btn--sm flex items-center gap-1.5">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> {data ? 'Обновить' : 'Загрузить'}
          </button>
          {data?.orders?.length > 0 && (
            <button onClick={exportCsv} className="btn btn--secondary btn--sm">CSV</button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {!loading && data && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <KpiStat label="Незабранных заказов" value={data.total_count.toLocaleString('ru-RU')} accent="#c9502a" icon={<PackageX size={18} />} />
            <KpiStat label="Сумма" value={fmtRub(data.total_amount)} accent="#ffb347" icon={<TrendingDown size={18} />} />
          </div>

          <div className="app-card overflow-hidden">
            <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
              <h3 className="font-semibold">Список</h3>
              <span className="text-sm text-[color:var(--color-muted-foreground)]">{data.orders.length}</span>
            </div>
            <div className="p-3">
              <ResponsiveTable
                data={data.orders}
                keyFn={(o) => o.doc_num}
                emptyText="Ничего не просрочено — хороший знак"
                columns={[
                  { label: '№ заказа', primary: true, render: (o) => (
                    <div>
                      <div className="font-medium">{o.doc_num}</div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)]">обещали {o.due_date}</div>
                    </div>
                  )},
                  { label: 'Клиент', render: (o) => (
                    <div>
                      <div>{o.client_name || '—'}</div>
                      {o.client_phone && <div className="text-xs text-[color:var(--color-muted-foreground)] flex items-center gap-1"><Phone size={10} /> {o.client_phone}</div>}
                    </div>
                  )},
                  { label: 'Сумма', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (o) => fmtRub(o.amount) },
                  { label: 'Просрочка', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold text-red-500', render: (o) => `${o.days_overdue} дн.` },
                ]}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

/* ── main component ──────────────────────────────────────── */
export default function SalesAnalytics() {
  const now = new Date();
  const monthStart = toLocalDateStr(new Date(now.getFullYear(), now.getMonth(), 1));

  const [dateFrom, setDateFrom] = useState(monthStart);
  const [dateTo,   setDateTo]   = useState(TODAY);
  const [gran,     setGran]     = useState('day');
  const [hideZero, setHideZero] = useState(false);
  const [showMA,   setShowMA]   = useState(false);
  const [showPlan, setShowPlan] = useState(false);
  const [chartMode, setChartMode] = useState('area');
  const [selectedEmployees,  setSelectedEmployees]  = useState(new Set());
  const [selectedCategories, setSelectedCategories] = useState(new Set());
  const [selectedSalons,     setSelectedSalons]     = useState(new Set());
  // Only /sales/turnaround reads this (isolates "срок выполнения" to orders
  // containing a matching service/goods line, e.g. "набойки") — same
  // always-include-and-let-others-ignore-it approach as `categories` below.
  const [serviceSearch, setServiceSearch] = useState('');
  const [salonOptions,       setSalonOptions]       = useState([]);
  const [activeTab, setActiveTab] = useState('overview');

  // Salon list is independent of the date range (used to build the filter's
  // options), so it's fetched once on mount rather than inside load().
  useEffect(() => {
    api.get('/sales/salon-options').then((res) => {
      setSalonOptions((res.data || []).map((s) => ({ value: s.id, label: s.name })));
    }).catch((e) => console.error('Не удалось загрузить список салонов', e));
  }, []);

  const [rows,      setRows]      = useState([]);
  const [prevRows,  setPrevRows]  = useState([]);
  const [plans,     setPlans]     = useState({});
  const [retention, setRetention] = useState(null);
  const [margin,    setMargin]    = useState(null);
  const [turnaround, setTurnaround] = useState(null);
  const [returns,   setReturns]    = useState(null);
  const [workplaces, setWorkplaces] = useState(null);
  const [departments, setDepartments] = useState(null);
  const [topProducts, setTopProducts] = useState(null);
  const [tabLoading, setTabLoading] = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [loaded,    setLoaded]    = useState(false);
  const [error,     setError]     = useState(null);
  // Bumped on every "Загрузить"/"Обновить" click — the lazy-tab effect below
  // refetches the *active* tab whenever this changes, and every other lazy
  // tab's cached state was already cleared by load(), so it refetches too
  // next time the user actually visits it instead of eagerly on every click.
  const [filterVersion, setFilterVersion] = useState(0);

  const months = useMemo(() => getMonthsInRange(dateFrom, dateTo), [dateFrom, dateTo]);

  const activeCats = useMemo(() => {
    const all = CATEGORIES.map((c) => c.key);
    return selectedCategories.size === 0 ? all : all.filter((k) => selectedCategories.has(k));
  }, [selectedCategories]);

  function buildParams() {
    const params = {};
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo)   params.date_to   = dateTo;
    const salonIds = selectedSalons.size ? [...selectedSalons].join(',') : undefined;
    if (salonIds) params.salon_ids = salonIds;
    // Only /sales/top-products reads this — the other lazy endpoints just
    // ignore an unused query param, so it's simplest to always include it
    // here rather than special-case buildParams per tab.
    const categories = selectedCategories.size ? [...selectedCategories].join(',') : undefined;
    if (categories) params.categories = categories;
    if (serviceSearch.trim()) params.service_search = serviceSearch.trim();
    return params;
  }

  // Firebird-backed reports fired 8-10 at once on every load — each one is
  // its own connection/query against a single remote Firebird server, and
  // under concurrent load that contention made even individually-fast
  // queries take several seconds longer than in isolation (e.g. one report
  // measured 0.9s alone vs 4.3s in this stampede), which is what made the
  // whole page feel hung. Only the data the KPI row + default tab need
  // (daily×2, plans, retention) loads eagerly now; the rest is one request
  // each, fired only when its tab is actually opened (see the effect below).
  const LAZY_TABS = {
    margin:      { path: '/sales/margin',      set: setMargin },
    turnaround:  { path: '/sales/turnaround',   set: setTurnaround },
    returns:     { path: '/sales/returns',      set: setReturns },
    workplaces:  { path: '/sales/workplaces',   set: setWorkplaces },
    departments: { path: '/sales/departments',  set: setDepartments },
    products:    { path: '/sales/top-products', set: setTopProducts },
  };

  useEffect(() => {
    const tab = LAZY_TABS[activeTab];
    if (!loaded || !tab) return;
    let cancelled = false;
    setTabLoading(true);
    api.get(tab.path, { params: buildParams() })
      .then((res) => { if (!cancelled) tab.set(res.data); })
      .catch((e) => { if (!cancelled) setError(e.response?.data?.detail || e.message || 'Ошибка загрузки'); })
      .finally(() => { if (!cancelled) setTabLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTab, loaded, filterVersion]);

  async function load() {
    setLoading(true); setError(null);
    try {
      const params = buildParams();
      const d0 = new Date(dateFrom || TODAY), d1 = new Date(dateTo || TODAY);
      const prevTo = new Date(d0); prevTo.setDate(prevTo.getDate() - 1);
      const prevFrom = new Date(+prevTo - (d1 - d0));
      const prevParams = { ...params, date_from: prevFrom.toISOString().slice(0,10), date_to: prevTo.toISOString().slice(0,10) };
      const monthKeys = months.map(toMonthKey).join(',');
      const [mainRes, prevRes, plansRes, retentionRes] = await Promise.all([
        api.get('/sales/daily', { params }),
        api.get('/sales/daily', { params: prevParams }),
        api.get('/sales/plans', { params: { month_keys: monthKeys } }),
        api.get('/sales/client-retention', { params }),
      ]);
      // Lazy tabs get refetched (if revisited) against the new filters/date
      // range rather than showing stale data from before this reload.
      setMargin(null); setTurnaround(null); setReturns(null);
      setWorkplaces(null); setDepartments(null); setTopProducts(null);
      setFilterVersion((v) => v + 1);
      // Best-effort — a failure here shouldn't block sales data from
      // showing, it just leaves empName() falling back to the raw code.
      try {
        const empRes = await api.get('employees/', { params: { archived: false } });
        EMP_CODE_NAMES = buildCodeNameMap(empRes.data || []);
      } catch (e) {
        console.error('Не удалось загрузить имена сотрудников', e);
      }
      setRows(mainRes.data); setPrevRows(prevRes.data); setPlans(plansRes.data); setRetention(retentionRes.data); setLoaded(true);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Ошибка загрузки');
    } finally { setLoading(false); }
  }

  const allEmployees = useMemo(() => {
    const map = {};
    rows.forEach((r) => { if (!map[r.code]) map[r.code] = { code: r.code, description: r.description, total: 0 }; map[r.code].total += r.total; });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [rows]);

  const employeeOptions = useMemo(() => allEmployees.map((e) => ({ value: e.code, label: empName(e.code) })), [allEmployees]);
  const categoryOptions = CATEGORIES.map((c) => ({ value: c.key, label: c.label }));

  const filteredRows  = useMemo(() => selectedEmployees.size ? rows.filter((r) => selectedEmployees.has(r.code)) : rows, [rows, selectedEmployees]);
  const prevFiltered  = useMemo(() => selectedEmployees.size ? prevRows.filter((r) => selectedEmployees.has(r.code)) : prevRows, [prevRows, selectedEmployees]);

  const employees = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => { if (!map[r.code]) map[r.code] = { code: r.code, total: 0 }; map[r.code].total += r.total; });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows]);

  const nameMap = useMemo(() => Object.fromEntries(employees.map((e) => [e.code, empName(e.code)])), [employees]);

  const { periods, cells, allPeriodsCount } = useMemo(() => {
    const c = {};
    filteredRows.forEach((r) => {
      const key = getPeriodKey(r.date, gran);
      if (!c[key]) c[key] = {};
      const val = activeCats.reduce((s, k) => s + (r[k] || 0), 0);
      c[key][r.code] = (c[key][r.code] || 0) + val;
    });
    const all    = Object.keys(c).sort();
    const nonZero = all.filter((p) => employees.reduce((s, e) => s + (c[p]?.[e.code] || 0), 0) > 0);
    return { periods: hideZero ? nonZero : all, cells: c, allPeriodsCount: all.length };
  }, [filteredRows, gran, hideZero, employees, activeCats]);

  const chartData = useMemo(() => {
    const data = periods.map((key) => {
      const entry = { period: key, label: getPeriodLabel(key, gran) };
      employees.forEach((e) => { entry[e.code] = cells[key]?.[e.code] || 0; });
      entry._total = employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0);
      return entry;
    });
    data.forEach((d, i) => {
      const win = data.slice(Math.max(0, i - 6), i + 1);
      d._ma = win.reduce((s, x) => s + x._total, 0) / win.length;
    });
    return data;
  }, [periods, employees, cells, gran]);

  const empSummary = useMemo(() => {
    const map = {};
    filteredRows.forEach((r) => {
      if (!map[r.code]) map[r.code] = { code: r.code, repair: 0, cosmetics: 0, shoes: 0, total: 0, activeDays: 0 };
      map[r.code].repair    += r.repair    || 0;
      map[r.code].cosmetics += r.cosmetics || 0;
      map[r.code].shoes     += r.shoes     || 0;
      const catVal = activeCats.reduce((s, k) => s + (r[k] || 0), 0);
      map[r.code].total += catVal;
      if (catVal > 0) map[r.code].activeDays++;
    });
    return Object.values(map).sort((a, b) => b.total - a.total);
  }, [filteredRows, activeCats]);

  const planTotals = useMemo(() => {
    const result = {};
    allEmployees.forEach((e) => {
      result[e.code] = months.reduce((sum, ym) => {
        const p = plans?.[toMonthKey(ym)]?.[e.code];
        return p ? sum + (p.repair_plan||0) + (p.cosmetics_plan||0) + (p.shoes_plan||0) : sum;
      }, 0);
    });
    return result;
  }, [months, plans, allEmployees]);

  const colTotals = useMemo(() => {
    const t = {};
    employees.forEach((e) => { t[e.code] = periods.reduce((s, p) => s + (cells[p]?.[e.code] || 0), 0); });
    t._grand = employees.reduce((s, e) => s + (t[e.code] || 0), 0);
    return t;
  }, [periods, employees, cells]);

  const kpi = useMemo(() => {
    const catKeys = CATEGORIES.map((c) => c.key);
    const cur = Object.fromEntries([...catKeys, 'total'].map((k) => [k, 0]));
    const prev = { ...cur };
    filteredRows.forEach((r) => { catKeys.forEach((k) => { cur[k] += r[k]||0; }); cur.total += activeCats.reduce((s,k) => s+(r[k]||0), 0); });
    prevFiltered.forEach((r) => { catKeys.forEach((k) => { prev[k] += r[k]||0; }); prev.total += activeCats.reduce((s,k) => s+(r[k]||0), 0); });
    const delta = (c, p) => p > 0 ? (c - p) / p * 100 : null;
    return {
      ...cur,
      dRepair:    delta(cur.repair,    prev.repair),
      dCosmetics: delta(cur.cosmetics, prev.cosmetics),
      dShoes:     delta(cur.shoes,     prev.shoes),
      dTotal:     delta(cur.total,     prev.total),
      activePeriods: allPeriodsCount,
      avgPerActive:  allPeriodsCount > 0 ? cur.total / allPeriodsCount : 0,
    };
  }, [filteredRows, prevFiltered, allPeriodsCount, activeCats]);

  const categoryLeaders = useMemo(() => {
    const leaders = {};
    CATEGORIES.forEach(({ key }) => {
      const totals = {};
      filteredRows.forEach((r) => { if ((r[key]||0) > 0) totals[r.code] = (totals[r.code]||0) + r[key]; });
      const sorted = Object.entries(totals).sort((a, b) => b[1] - a[1]);
      leaders[key] = sorted.length ? { code: sorted[0][0], amount: sorted[0][1] } : null;
    });
    return leaders;
  }, [filteredRows]);

  const dayData = useMemo(() => {
    const counts = Array(7).fill(0), totals = Array(7).fill(0);
    filteredRows.forEach((r) => {
      const dow = (new Date(r.date).getDay() + 6) % 7;
      totals[dow] += activeCats.reduce((s, k) => s + (r[k]||0), 0);
      counts[dow]++;
    });
    return DAY_NAMES.map((name, i) => ({ name, total: totals[i], avg: counts[i] > 0 ? totals[i]/counts[i] : 0, count: counts[i] }));
  }, [filteredRows, activeCats]);

  const donutData = useMemo(() => [
    { name: 'Ремонт / Химчистка', value: kpi.repair    || 0, color: '#e61919' },
    { name: 'Косметика',           value: kpi.cosmetics || 0, color: '#4af626' },
    { name: 'Обувь',               value: kpi.shoes     || 0, color: '#ffb347' },
  ].filter((d) => d.value > 0), [kpi]);

  // Маржа/Сроки/Возвраты come back from the API already salon-filtered
  // (server-side, see load()) but not employee-filtered — that's cheap to
  // do here since each already carries a `code` per row, and re-deriving
  // "total" from the filtered subset keeps the KPI row honest instead of
  // showing an unfiltered total next to a filtered employee list.
  const filteredMargin = useMemo(() => {
    if (!margin) return null;
    if (!selectedEmployees.size) return margin;
    const byEmp = margin.by_employee.filter((e) => selectedEmployees.has(e.code));
    const sum = (field) => byEmp.reduce((s, e) => s + (e[field] || 0), 0);
    const categories = {};
    for (const cat of ['repair', 'cosmetics']) {
      const rev = sum(`${cat}_revenue`), cost = sum(`${cat}_cost`);
      categories[cat] = { revenue: rev, cost, margin: rev - cost, margin_pct: rev ? Math.round((rev - cost) / rev * 1000) / 10 : 0 };
    }
    const totalRev = categories.repair.revenue + categories.cosmetics.revenue;
    const totalCost = categories.repair.cost + categories.cosmetics.cost;
    return {
      categories,
      total: { revenue: totalRev, cost: totalCost, margin: totalRev - totalCost,
        margin_pct: totalRev ? Math.round((totalRev - totalCost) / totalRev * 1000) / 10 : 0 },
      by_employee: byEmp,
      unpriced_items: margin.unpriced_items,
    };
  }, [margin, selectedEmployees]);

  // Grouped by salon server-side already (salon_ids round-trips via
  // buildParams like every other lazy tab), so no client-side re-filter
  // is needed here the way the old per-employee version required.
  const filteredTurnaround = turnaround;

  const filteredReturns = useMemo(() => {
    if (!returns) return null;
    if (!selectedEmployees.size) return returns;
    const byEmp = returns.by_employee.filter((e) => selectedEmployees.has(e.code));
    const returnCount  = byEmp.reduce((s, e) => s + e.return_count, 0);
    const returnAmount = byEmp.reduce((s, e) => s + e.return_amount, 0);
    const orderCount   = byEmp.reduce((s, e) => s + e.order_count, 0);
    return {
      total: {
        return_count: returnCount,
        return_amount: returnAmount,
        order_count: orderCount,
        return_rate: orderCount ? Math.round(returnCount / orderCount * 1000) / 10 : 0,
      },
      by_employee: byEmp,
    };
  }, [returns, selectedEmployees]);

  const periodLabel = gran === 'day' ? 'дн.' : gran === 'week' ? 'нед.' : 'мес.';

  function downloadCsv() {
    if (!filteredRows.length) return;
    const hdr  = 'Дата;Код;Имя;Ремонт/Химчистка;Косметика;Обувь;Итого';
    const body = filteredRows.map((r) => [r.date, r.code, r.description, r.repair, r.cosmetics, r.shoes||0, r.total].join(';')).join('\n');
    const blob = new Blob(['﻿' + hdr + '\n' + body], { type:'text/csv;charset=utf-8' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a'); a.href = url; a.download = 'sales.csv'; a.click();
    URL.revokeObjectURL(url);
  }

  const mainTabs = [
    { key: 'overview',   label: 'Обзор',        icon: <BarChart3 size={15} /> },
    { key: 'employees',  label: 'Сотрудники',   icon: <Users size={15} />, badge: employees.length || undefined },
    { key: 'details',    label: 'Сводная',       icon: <Target size={15} /> },
    { key: 'margin',     label: 'Маржа',        icon: <Percent size={15} /> },
    { key: 'turnaround', label: 'Сроки',         icon: <Clock size={15} /> },
    { key: 'returns',    label: 'Возвраты',      icon: <RotateCcw size={15} /> },
    { key: 'workplaces', label: 'Пропускная способность', icon: <Gauge size={15} /> },
    { key: 'departments', label: 'Салоны',      icon: <Building2 size={15} /> },
    { key: 'unclaimed',  label: 'Незабранные',  icon: <PackageX size={15} /> },
    { key: 'products',   label: 'Товары',        icon: <Package size={15} /> },
  ];

  return (
    <div className="space-y-5">
      <TopProgressBar active={loading} />

      {/* ── Header ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold flex items-center gap-2">
            <BarChart3 size={22} className="text-[color:var(--color-primary)]" /> Аналитика продаж
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">
            Выручка по сотрудникам и категориям — динамика, структура, рейтинги
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={downloadCsv} disabled={!filteredRows.length}
            className="btn btn--secondary btn--sm flex items-center gap-1.5 disabled:opacity-40">
            <Download size={14} /> CSV
          </button>
          <button onClick={load} disabled={loading}
            className="btn btn--primary btn--sm flex items-center gap-1.5">
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loaded ? 'Обновить' : 'Загрузить'}
          </button>
        </div>
      </div>

      {/* ── Filters ───────────────────────────────────────── */}
      <div className="app-card p-4 space-y-3">
        <div className="flex flex-wrap gap-1.5">
          {[['month','Этот месяц'],['prev','Прошлый мес.'],['q','Квартал'],['year','Год']].map(([k, l]) => (
            <button key={k} onClick={() => { const [f,t] = quickRange(k); setDateFrom(f); setDateTo(t); }}
              className="px-3 py-1 rounded-full text-xs border border-[color:var(--color-border)] hover:border-[color:var(--color-primary)] hover:text-[color:var(--color-primary)] transition-colors">
              {l}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата от</label>
            <input type="date" className="input w-full" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
          </div>
          <div className="col-span-2 sm:col-span-1">
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Дата до</label>
            <input type="date" className="input w-full" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Группировка</label>
            <div className="flex rounded-lg border border-[color:var(--color-border)] overflow-hidden text-sm">
              {[['day','День'],['week','Нед.'],['month','Мес.']].map(([v, l]) => (
                <button key={v} onClick={() => setGran(v)}
                  className={`flex-1 py-1.5 transition-colors ${gran === v ? 'bg-[color:var(--color-primary)] text-white' : 'hover:bg-[color:var(--color-muted)]'}`}>
                  {l}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Сотрудники</label>
            <MultiSelect options={employeeOptions} selected={selectedEmployees} onChange={setSelectedEmployees} placeholder="Все сотрудники" />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Категории</label>
            <MultiSelect options={categoryOptions} selected={selectedCategories} onChange={setSelectedCategories} placeholder="Все категории" />
          </div>
          <div>
            <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Салон</label>
            <MultiSelect options={salonOptions} selected={selectedSalons} onChange={setSelectedSalons} placeholder="Все салоны" />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {[
            [hideZero, () => setHideZero((v) => !v), hideZero ? <EyeOff size={12}/> : <Eye size={12}/>, 'Скрыть нули'],
            [showMA,   () => setShowMA((v)   => !v), null, 'MA7'],
            [showPlan, () => setShowPlan((v) => !v), null, 'Планы'],
            [chartMode !== 'area', () => setChartMode((m) => m === 'area' ? 'bar' : m === 'bar' ? 'line' : 'area'), null,
              chartMode === 'area' ? '▲ Область' : chartMode === 'bar' ? '▬ Столбцы' : '— Линии'],
          ].map(([active, fn, icon, lbl], i) => (
            <button key={i} onClick={fn}
              className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${active
                ? 'border-[color:var(--color-primary)] bg-[color:var(--color-primary)]/10 text-[color:var(--color-primary)]'
                : 'border-[color:var(--color-border)] hover:bg-[color:var(--color-muted)]'}`}>
              {icon}{lbl}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 p-4 text-red-700 dark:text-red-300 text-sm">{error}</div>
      )}

      {!loaded && !loading && (
        <div className="app-card p-14 text-center">
          <BarChart3 size={44} className="mx-auto text-[color:var(--color-muted-foreground)] opacity-25 mb-3" />
          <p className="text-[color:var(--color-muted-foreground)]">Выберите период и нажмите <strong>Загрузить</strong></p>
        </div>
      )}

      {loading && <SkeletonTable rows={6} />}

      {loaded && !loading && (
        <>
          {/* ── KPI row ─────────────────────────────────────── */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
            <KpiStat label="Итого выручка" value={fmtRub(kpi.total)} delta={kpi.dTotal} accent="#e61919"
              icon={<BarChart3 size={18} />} sub={`∅ ${fmtRub(kpi.avgPerActive)} / ${periodLabel}`} />
            {CATEGORIES.map(({ key, label, color }) => {
              const leader    = categoryLeaders[key];
              const deltaKey  = `d${key.charAt(0).toUpperCase()}${key.slice(1)}`;
              return (
                <KpiStat key={key} label={label} value={fmtRub(kpi[key])} delta={kpi[deltaKey]} accent={color}
                  sub={leader ? `👤 ${empName(leader.code)}` : undefined} />
              );
            })}
            {retention && retention.total_clients > 0 && (
              <KpiStat label="Повторные клиенты" value={fmtPct(retention.repeat_rate)} accent="#9a9a9a"
                icon={<Users size={18} />}
                sub={`${retention.new_clients} нов. · ${retention.returning_clients} пост.`} />
            )}
          </div>

          <Tabs tabs={mainTabs} active={activeTab} onChange={setActiveTab} />

          {/* ══ OVERVIEW tab ════════════════════════════════ */}
          {activeTab === 'overview' && (
            <div className="space-y-4">

              {/* Chart + Donut side by side */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

                {chartData.length > 0 && (
                  <div className="app-card p-4 lg:col-span-2">
                    <div className="flex items-center justify-between mb-3">
                      <h3 className="font-semibold">Динамика продаж</h3>
                      <span className="text-xs text-[color:var(--color-muted-foreground)]">{chartData.length} {periodLabel}</span>
                    </div>
                    <ResponsiveContainer width="100%" height={250}>
                      <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 50 }}>
                        <defs>
                          {employees.map((e, i) => (
                            <linearGradient key={e.code} id={`ag${i}`} x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%"  stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.35} />
                              <stop offset="95%" stopColor={CHART_COLORS[i % CHART_COLORS.length]} stopOpacity={0.02} />
                            </linearGradient>
                          ))}
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#e5e7eb)" vertical={false} />
                        <XAxis dataKey="label" tick={{ fontSize: 11 }} angle={-40} textAnchor="end" height={60} interval="preserveStartEnd" />
                        <YAxis tickFormatter={(v) => v.toLocaleString('ru-RU')} tick={{ fontSize: 11 }} width={64} axisLine={false} tickLine={false} />
                        <Tooltip content={<ChartTooltip nameMap={nameMap} />} />
                        {employees.length > 1 && (
                          <Legend formatter={(code) => nameMap[code] || code} wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
                        )}
                        {employees.map((e, i) => {
                          const color = CHART_COLORS[i % CHART_COLORS.length];
                          if (chartMode === 'area')
                            return <Area key={e.code} dataKey={e.code} name={e.code} type="monotone" stroke={color} fill={`url(#ag${i})`} strokeWidth={2} dot={false} isAnimationActive={false} stackId="s" />;
                          if (chartMode === 'bar')
                            return <Bar  key={e.code} dataKey={e.code} name={e.code} fill={color} isAnimationActive={false} stackId="s" radius={i === employees.length - 1 ? [3,3,0,0] : 0} />;
                          return <Line key={e.code} dataKey={e.code} name={e.code} type="monotone" stroke={color} dot={false} strokeWidth={2} isAnimationActive={false} />;
                        })}
                        {showMA && <Line dataKey="_ma" name="_ma" type="monotone" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="5 3" dot={false} isAnimationActive={false} legendType="none" />}
                      </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {donutData.length > 0 && (
                  <div className="app-card p-4">
                    <h3 className="font-semibold mb-1">Структура выручки</h3>
                    <p className="text-xs text-[color:var(--color-muted-foreground)] mb-3">{fmtRub(kpi.total)} · {kpi.activePeriods} {periodLabel}</p>
                    <ResponsiveContainer width="100%" height={170}>
                      <PieChart>
                        <Pie data={donutData} cx="50%" cy="50%" innerRadius="45%" outerRadius="80%"
                          dataKey="value" labelLine={false} label={DonutLabel} isAnimationActive={false}
                          onClick={(entry) => toggleSet(setSelectedCategories, LABEL_TO_KEY[entry.name])}
                          cursor="pointer">
                          {donutData.map((entry, i) => (
                            <Cell key={i} fill={entry.color} opacity={selectedCategories.size && !selectedCategories.has(LABEL_TO_KEY[entry.name]) ? 0.35 : 1} />
                          ))}
                        </Pie>
                        <Tooltip formatter={(v, n) => [fmtRub(v), n]} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="space-y-2 mt-1">
                      {donutData.map((d) => {
                        const pct = kpi.total > 0 ? d.value / kpi.total * 100 : 0;
                        const isActive = selectedCategories.has(LABEL_TO_KEY[d.name]);
                        return (
                          <button
                            key={d.name}
                            type="button"
                            onClick={() => toggleSet(setSelectedCategories, LABEL_TO_KEY[d.name])}
                            className={`flex items-center gap-2 text-xs w-full text-left rounded-md -mx-1 px-1 py-0.5 transition-colors hover:bg-[color:var(--color-bg-secondary)] cursor-pointer ${isActive ? 'bg-[color:var(--color-primary-muted)]' : ''}`}
                          >
                            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.color }} />
                            <span className="flex-1 text-[color:var(--color-muted-foreground)] truncate">{d.name}</span>
                            <span className="font-semibold tabular-nums">{pct.toFixed(0)}%</span>
                            <span className="text-[color:var(--color-muted-foreground)] tabular-nums">{fmtRub(d.value)}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Day of week + top 3 leaders */}
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                {dayData.some((d) => d.count > 0) && (
                  <div className="lg:col-span-2">
                    <DayHeatmap data={dayData} />
                  </div>
                )}

                {empSummary.length > 0 && (
                  <div className="app-card p-5">
                    <div className="flex items-center gap-2 mb-4">
                      <Trophy size={15} className="text-amber-500" />
                      <h3 className="font-semibold text-sm">Топ-3</h3>
                    </div>
                    <div className="space-y-3">
                      {empSummary.slice(0, 3).map((e, i) => {
                        const medals = ['🥇','🥈','🥉'];
                        const color  = CHART_COLORS[i % CHART_COLORS.length];
                        const share  = empSummary[0].total > 0 ? e.total / empSummary[0].total : 0;
                        return (
                          <div key={e.code} className="flex items-center gap-2.5">
                            <span className="text-lg leading-none">{medals[i]}</span>
                            <EmpAvatar name={empName(e.code)} color={color} size={32} />
                            <div className="flex-1 min-w-0">
                              <div className="flex justify-between text-sm font-semibold">
                                <span className="truncate">{empName(e.code)}</span>
                                <span style={{ color }}>{fmtRub(e.total)}</span>
                              </div>
                              <div className="mt-1 h-1 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                                <div className="h-full rounded-full" style={{ width: `${share*100}%`, background: color }} />
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ══ EMPLOYEES tab ═══════════════════════════════ */}
          {activeTab === 'employees' && (
            <div className="space-y-4">
              {empSummary.length === 0 ? (
                <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
              ) : (
                <>
                  <Leaderboard empSummary={empSummary} planTotals={planTotals} activeCodes={selectedEmployees} onSelect={(code) => toggleSet(setSelectedEmployees, code)} />

                  {showPlan && <PlanGauges empSummary={empSummary} planTotals={planTotals} />}

                  {/* Stacked horizontal bar chart */}
                  <div className="app-card p-4">
                    <h3 className="font-semibold mb-3">Сравнение по категориям</h3>
                    <ResponsiveContainer width="100%" height={Math.max(180, empSummary.length * 52)}>
                      <BarChart data={empSummary.map((e) => ({ ...e, displayName: empName(e.code) }))}
                        layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border,#e5e7eb)" horizontal={false} />
                        <XAxis type="number" tickFormatter={(v) => v.toLocaleString('ru-RU')} tick={{ fontSize: 11 }} axisLine={false} />
                        <YAxis type="category" dataKey="displayName" tick={{ fontSize: 11 }} width={80} />
                        <Tooltip formatter={(v, n) => [fmtRub(v), n]} />
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        {CATEGORIES.map(({ key, label, color }) =>
                          activeCats.includes(key) && (
                            <Bar
                              key={key} dataKey={key} name={label} stackId="a" fill={color} isAnimationActive={false}
                              onClick={(entry) => toggleSet(setSelectedEmployees, entry.code)}
                              cursor="pointer"
                            />
                          )
                        )}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>

                  {/* Employee detail table */}
                  <div className="app-card overflow-hidden">
                    <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                      <h3 className="font-semibold">Детализация</h3>
                    </div>
                    <div className="p-3">
                      <ResponsiveTable
                        data={empSummary}
                        keyFn={(e) => e.code}
                        emptyText="Нет данных"
                        columns={[
                          { label: 'Сотрудник', primary: true, render: (e) => (
                            <div className="flex items-center gap-2">
                              <EmpAvatar name={empName(e.code)} color={CHART_COLORS[empSummary.indexOf(e) % CHART_COLORS.length]} size={26} />
                              <span>{empName(e.code)}</span>
                            </div>
                          )},
                          ...CATEGORIES.map(({ key, label, color }) => ({
                            label, headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => <span style={{ color }}>{Math.round(e[key]||0).toLocaleString('ru-RU')}</span>,
                          })),
                          { label: 'Итого', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => <span className="font-bold text-[color:var(--color-primary)]">{Math.round(e.total).toLocaleString('ru-RU')}</span> },
                          ...(showPlan ? [
                            { label: 'План', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                              render: (e) => { const p = planTotals[e.code]||0; return p > 0 ? Math.round(p).toLocaleString('ru-RU') : '—'; } },
                            { label: '%', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                              render: (e) => { const p = planTotals[e.code]||0, pct = p > 0 ? e.total/p*100 : null;
                                return <span className={`font-semibold ${pct == null ? '' : pct >= 100 ? 'text-emerald-600' : pct >= 75 ? 'text-amber-500' : 'text-red-500'}`}>{fmtPct(pct)}</span>; } },
                          ] : []),
                          { label: 'Дней', key: 'activeDays', headerClass: 'text-right', cellClass: 'text-right tabular-nums' },
                          { label: 'Ср/день', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                            render: (e) => Math.round(e.activeDays > 0 ? e.total/e.activeDays : 0).toLocaleString('ru-RU') },
                        ]}
                      />
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* ══ DETAILS tab ═════════════════════════════════ */}
          {activeTab === 'details' && (
            periods.length > 0 ? (
              <div className="app-card overflow-hidden">
                <div className="px-4 py-3 border-b border-[color:var(--color-border)] flex items-center justify-between">
                  <h3 className="font-semibold">Сводная таблица</h3>
                  <span className="text-sm text-[color:var(--color-muted-foreground)]">{periods.length} {periodLabel}</span>
                </div>
                <div className="p-3">
                  <ResponsiveTable
                    data={[
                      ...periods.map((key) => ({ key, isTotal: false, label: getPeriodLabel(key, gran), rowTotal: employees.reduce((s, e) => s + (cells[key]?.[e.code] || 0), 0) })),
                      { key: '_total', isTotal: true, label: 'Итого', rowTotal: colTotals._grand || 0 },
                    ]}
                    keyFn={(row) => row.key}
                    rowClass={(row) => row.isTotal ? 'border-t-2 border-[color:var(--color-border)] bg-[color:var(--color-muted)]/30 font-semibold' : ''}
                    emptyText="Нет данных"
                    columns={[
                      { label: 'Период', primary: true,
                        headerClass: 'sticky left-0 bg-[color:var(--color-modal-bg)]',
                        cellClass: 'sticky left-0 bg-inherit font-medium',
                        render: (row) => row.label },
                      ...employees.map((e, i) => ({
                        label: empName(e.code), headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                        render: (row) => {
                          if (row.isTotal) return <span className="font-bold" style={{ color: CHART_COLORS[i % CHART_COLORS.length] }}>{Math.round(colTotals[e.code]||0).toLocaleString('ru-RU')}</span>;
                          const v = cells[row.key]?.[e.code] || 0;
                          return <span className={v === 0 ? 'text-[color:var(--color-muted-foreground)]' : ''}>{v === 0 ? '—' : Math.round(v).toLocaleString('ru-RU')}</span>;
                        },
                      })),
                      { label: 'Итого', headerClass: 'text-right', cellClass: 'text-right whitespace-nowrap tabular-nums',
                        render: (row) => <span className={`font-semibold ${row.isTotal ? 'text-[color:var(--color-primary)]' : ''}`}>{Math.round(row.rowTotal||0).toLocaleString('ru-RU')}</span> },
                    ]}
                  />
                </div>
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}

          {/* ══ MARGIN tab ══════════════════════════════════ */}
          {activeTab === 'margin' && (
            tabLoading ? (
              <SkeletonTable rows={6} />
            ) : filteredMargin && filteredMargin.total.revenue > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                  <KpiStat label="Выручка" value={fmtRub(filteredMargin.total.revenue)} accent="#e61919" icon={<BarChart3 size={18} />} />
                  <KpiStat label="Себестоимость" value={fmtRub(filteredMargin.total.cost)} accent="#c9502a" icon={<Percent size={18} />} />
                  <KpiStat label="Валовая прибыль" value={fmtRub(filteredMargin.total.margin)} accent="#4af626" icon={<TrendingUp size={18} />} />
                  <KpiStat label="Маржа" value={fmtPct(filteredMargin.total.margin_pct)} accent="#9a9a9a" icon={<Target size={18} />} />
                </div>

                <div className="app-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                    <h3 className="font-semibold">По категориям</h3>
                  </div>
                  <div className="p-3">
                    <ResponsiveTable
                      data={CATEGORIES.filter((c) => c.key !== 'shoes').map((c) => ({ ...c, ...filteredMargin.categories[c.key] }))}
                      keyFn={(c) => c.key}
                      emptyText="Нет данных"
                      columns={[
                        { label: 'Категория', primary: true, render: (c) => (
                          <span className="flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c.color }} />
                            {c.label}
                          </span>
                        )},
                        { label: 'Выручка', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (c) => fmtRub(c.revenue) },
                        { label: 'Себестоимость', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (c) => fmtRub(c.cost) },
                        { label: 'Прибыль', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (c) => fmtRub(c.margin) },
                        { label: 'Маржа', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (c) => fmtPct(c.margin_pct) },
                      ]}
                    />
                  </div>
                  <div className="px-4 py-2.5 border-t border-[color:var(--color-border)] text-xs text-[color:var(--color-muted-foreground)]">
                    «Ремонт/химчистка» — это в основном услуги (труд), а не перепродаваемый товар: закупочная себестоимость по складским приходам
                    для них почти нулевая, поэтому маржа там близка к 100% — это ожидаемо, не ошибка расчёта. Себестоимость считается по последней
                    цене прихода на складе на конец периода{filteredMargin.unpriced_items > 0 ? `; для ${filteredMargin.unpriced_items} позиций приход в базе не найден — их себестоимость взята как 0` : ''}.
                  </div>
                </div>

                <div className="app-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                    <h3 className="font-semibold">По сотрудникам</h3>
                  </div>
                  <div className="p-3">
                    <ResponsiveTable
                      data={filteredMargin.by_employee}
                      keyFn={(e) => e.code}
                      emptyText="Нет данных"
                      columns={[
                        { label: 'Сотрудник', primary: true, render: (e) => (
                          <div className="flex items-center gap-2">
                            <EmpAvatar name={empName(e.code)} color={CHART_COLORS[filteredMargin.by_employee.indexOf(e) % CHART_COLORS.length]} size={26} />
                            <span>{empName(e.code)}</span>
                          </div>
                        )},
                        { label: 'Выручка', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (e) => fmtRub(e.revenue) },
                        { label: 'Себестоимость', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (e) => fmtRub(e.cost) },
                        { label: 'Прибыль', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (e) => fmtRub(e.margin) },
                        { label: 'Маржа', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (e) => fmtPct(e.margin_pct) },
                      ]}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}

          {/* ══ TURNAROUND tab ══════════════════════════════ */}
          {activeTab === 'turnaround' && (
            <div className="space-y-4">
              <div className="app-card p-3 flex flex-wrap items-end gap-2">
                <div className="flex-1 min-w-[220px]">
                  <label className="block text-xs text-[color:var(--color-muted-foreground)] mb-1">Услуга/товар (по названию)</label>
                  <input
                    type="text"
                    className="input w-full"
                    placeholder="напр. набойки"
                    value={serviceSearch}
                    onChange={(e) => setServiceSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') setFilterVersion((v) => v + 1); }}
                  />
                </div>
                <button onClick={() => setFilterVersion((v) => v + 1)} className="btn btn--primary btn--sm flex items-center gap-1.5">
                  <RefreshCw size={14} className={tabLoading ? 'animate-spin' : ''} /> Применить
                </button>
                {serviceSearch.trim() && (
                  <button onClick={() => { setServiceSearch(''); setFilterVersion((v) => v + 1); }} className="btn btn--secondary btn--sm">
                    Сбросить
                  </button>
                )}
              </div>
              <p className="text-xs text-[color:var(--color-muted-foreground)] -mt-2">
                Срок — от приёма заказа до перевода в статус «Исполненный» (когда работа фактически закончена, не когда клиент забрал).
                {serviceSearch.trim()
                  ? <> Считается только по заказам с позицией, содержащей «{serviceSearch.trim()}» в названии.</>
                  : <> Укажите название услуги/товара выше, чтобы измерить срок только по ней (например «набойки»).</>}
                {' '}Сузить по салонам можно фильтром «Салон» вверху страницы.
              </p>
              {tabLoading ? (
                <SkeletonTable rows={6} />
              ) : filteredTurnaround && filteredTurnaround.total.order_count > 0 ? (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                    <KpiStat label="Средний срок" value={`${filteredTurnaround.total.avg_days} дн.`} accent="#e61919" icon={<Clock size={18} />} />
                    <KpiStat label="Просрочено" value={fmtPct(filteredTurnaround.total.late_rate)} accent="#c9502a" icon={<TrendingDown size={18} />}
                      sub="работа завершена позже обещанной даты" />
                    <KpiStat label="Заказов исполнено" value={filteredTurnaround.total.order_count.toLocaleString('ru-RU')} accent="#4af626" icon={<Target size={18} />} />
                  </div>

                  <div className="app-card overflow-hidden">
                    <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                      <h3 className="font-semibold">По салонам</h3>
                      <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">Срок — от приёма до статуса «Исполненный». Просрочка — работа завершена (статус «Исполненный») позже обещанной клиенту даты выдачи; когда клиент фактически забрал заказ, не учитывается — это его график, а не вина бизнеса.</p>
                    </div>
                    <div className="p-3">
                      <ResponsiveTable
                        data={filteredTurnaround.by_salon}
                        keyFn={(s) => s.salon_id}
                        emptyText="Нет данных"
                        columns={[
                          { label: 'Салон', primary: true, render: (s) => (
                            <div className="flex items-center gap-2">
                              <span className="inline-block w-2.5 h-2.5 rounded-full shrink-0" style={{ background: CHART_COLORS[filteredTurnaround.by_salon.indexOf(s) % CHART_COLORS.length] }} />
                              <span>{s.salon_name}</span>
                            </div>
                          )},
                          { label: 'Заказов', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (s) => s.order_count.toLocaleString('ru-RU') },
                          { label: 'Ср. срок', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (s) => `${s.avg_days} дн.` },
                          { label: 'Просрочено', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (s) => `${s.late_count}` },
                          { label: '% просрочки', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (s) => (
                            <span className={s.late_rate >= 50 ? 'text-red-500' : s.late_rate >= 25 ? 'text-amber-500' : 'text-emerald-600'}>{fmtPct(s.late_rate)}</span>
                          )},
                        ]}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">
                  {serviceSearch.trim() ? `Нет заказов с «${serviceSearch.trim()}» за выбранный период` : 'Нет данных за выбранный период'}
                </div>
              )}
            </div>
          )}

          {/* ══ RETURNS tab ═════════════════════════════════ */}
          {activeTab === 'returns' && (
            tabLoading ? (
              <SkeletonTable rows={6} />
            ) : filteredReturns ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  <KpiStat label="Возвратов" value={filteredReturns.total.return_count.toLocaleString('ru-RU')} accent="#c9502a" icon={<RotateCcw size={18} />} />
                  <KpiStat label="% от заказов" value={fmtPct(filteredReturns.total.return_rate)} accent="#ffb347" icon={<Target size={18} />} />
                  <KpiStat label="Заказов всего" value={filteredReturns.total.order_count.toLocaleString('ru-RU')} accent="#e61919" icon={<BarChart3 size={18} />} />
                </div>

                {filteredReturns.by_employee.length > 0 ? (
                  <div className="app-card overflow-hidden">
                    <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                      <h3 className="font-semibold">По сотрудникам</h3>
                      <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                        Только отчёт — решение о штрафах/премиях по возвратам принимается вручную.
                      </p>
                    </div>
                    <div className="p-3">
                      <ResponsiveTable
                        data={filteredReturns.by_employee}
                        keyFn={(e) => e.code}
                        emptyText="Нет возвратов за период"
                        columns={[
                          { label: 'Сотрудник', primary: true, render: (e) => (
                            <div className="flex items-center gap-2">
                              <EmpAvatar name={empName(e.code)} color={CHART_COLORS[filteredReturns.by_employee.indexOf(e) % CHART_COLORS.length]} size={26} />
                              <span>{empName(e.code)}</span>
                            </div>
                          )},
                          { label: 'Заказов', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (e) => e.order_count.toLocaleString('ru-RU') },
                          { label: 'Возвратов', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (e) => e.return_count },
                          { label: '% возвратов', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (e) => (
                            <span className={e.return_rate >= 5 ? 'text-red-500' : e.return_rate >= 1 ? 'text-amber-500' : 'text-emerald-600'}>{fmtPct(e.return_rate)}</span>
                          )},
                        ]}
                      />
                    </div>
                  </div>
                ) : (
                  <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Возвратов за выбранный период нет</div>
                )}
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}

          {/* ══ WORKPLACES tab ══════════════════════════════ */}
          {activeTab === 'workplaces' && (
            tabLoading ? (
              <SkeletonTable rows={6} />
            ) : workplaces && workplaces.work_places.length > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <KpiStat label="Выручка через точки" value={fmtRub(workplaces.total_revenue)} accent="#e61919" icon={<Gauge size={18} />} />
                  <KpiStat label="Операций" value={workplaces.total_operations.toLocaleString('ru-RU')} accent="#4af626" icon={<BarChart3 size={18} />} />
                </div>

                <div className="app-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                    <h3 className="font-semibold">По точкам приёма/выдачи ремонта</h3>
                    <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                      Это не «выручка в час» — в базе нет надёжного учёта фактического времени выполнения по мастерам (начало/конец операции
                      совпадают почти во всех записях). Показана пропускная способность точек сканирования приёма/выдачи ремонта по филиалам —
                      количество операций и выручка через каждую из них.
                    </p>
                  </div>
                  <div className="p-3">
                    <ResponsiveTable
                      data={workplaces.work_places}
                      keyFn={(w) => w.name}
                      emptyText="Нет данных"
                      columns={[
                        { label: 'Точка', primary: true, render: (w) => w.name },
                        { label: 'Операций', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (w) => w.operation_count.toLocaleString('ru-RU') },
                        { label: 'Выручка', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (w) => fmtRub(w.revenue) },
                        { label: 'Средний чек', headerClass: 'text-right', cellClass: 'text-right tabular-nums', render: (w) => fmtRub(w.avg_ticket) },
                      ]}
                    />
                  </div>
                </div>
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}

          {/* ══ DEPARTMENTS tab ═════════════════════════════ */}
          {activeTab === 'departments' && (
            tabLoading ? (
              <SkeletonTable rows={6} />
            ) : departments && departments.departments.length > 0 ? (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <KpiStat label="Выручка по всем салонам" value={fmtRub(departments.total_revenue)} accent="#e61919" icon={<Building2 size={18} />} />
                  <KpiStat label="Салонов" value={departments.departments.length.toLocaleString('ru-RU')} accent="#4af626" icon={<Target size={18} />} />
                </div>

                <div className="app-card overflow-hidden">
                  <div className="px-4 py-3 border-b border-[color:var(--color-border)]">
                    <h3 className="font-semibold">Рейтинг салонов</h3>
                    <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                      Привязка заказа к салону — по коду в номере заказа (как в «ФОТ по салонам»), не по внутреннему DEP_ID Агбис.
                    </p>
                  </div>
                  <div className="divide-y divide-[color:var(--color-border)]">
                    {departments.departments.map((d, i) => {
                      const maxRev = departments.departments[0].revenue || 1;
                      const share = d.revenue / maxRev;
                      const color = CHART_COLORS[i % CHART_COLORS.length];
                      return (
                        <div key={d.salon_id} className="px-5 py-3">
                          <div className="flex items-center justify-between gap-2 mb-1.5">
                            <span className="font-semibold text-sm truncate">{d.salon_name}</span>
                            <span className="font-bold tabular-nums text-sm shrink-0" style={{ color }}>{fmtRub(d.revenue)}</span>
                          </div>
                          <div className="h-1.5 rounded-full bg-[color:var(--color-border)] overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${share * 100}%`, background: color }} />
                          </div>
                          <div className="flex items-center justify-between mt-1 text-xs text-[color:var(--color-muted-foreground)]">
                            <span>{d.order_count.toLocaleString('ru-RU')} заказ.</span>
                            <span>ср. чек {fmtRub(d.avg_check)}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}

          {/* ══ UNCLAIMED tab ═══════════════════════════════ */}
          {activeTab === 'unclaimed' && <UnclaimedTab />}

          {/* ══ PRODUCTS tab ════════════════════════════════ */}
          {activeTab === 'products' && (
            tabLoading ? (
              <SkeletonTable rows={6} />
            ) : topProducts && topProducts.top.length > 0 ? (
              <div className="space-y-4">
                <p className="text-xs text-[color:var(--color-muted-foreground)]">
                  Разбивка по конкретным товарам/услугам (не по категориям целиком). «vs пред. период» сравнивает с таким же по длине
                  периодом непосредственно перед выбранным; изменения по позициям дешевле {' '}{fmtRub(1000)}{' '} не показываются в
                  «растущих/падающих» — на таких суммах % ничего не значит.
                </p>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ProductRankTable title="Топ по выручке" items={topProducts.top} />
                  <ProductRankTable title="Меньше всего продаж" items={topProducts.bottom} />
                  <ProductRankTable title="Растущие позиции" items={topProducts.rising} showChange />
                  <ProductRankTable title="Падающие позиции" items={topProducts.falling} showChange />
                </div>

                {topProducts.dead_stock && topProducts.dead_stock.length > 0 && (
                  <ExpandableCard
                    title="Нулевые продажи (товар в наличии, но не продаётся)"
                    subtitle={(
                      <p className="text-xs text-[color:var(--color-muted-foreground)] mt-0.5">
                        Товары со складским остатком {'>'} 0, у которых за выбранный период не было ни одной продажи.
                        Только косметика/товары — у ремонта нет физического остатка на складе.
                      </p>
                    )}
                  >
                    {(expanded) => (
                      <ResponsiveTable
                        data={topProducts.dead_stock}
                        keyFn={(p) => p.tovar_id}
                        emptyText="Нет данных"
                        columns={[
                          { label: 'Товар', primary: true, render: (p) => (
                            expanded ? (
                              <span title={p.name}>{p.name || p.code}</span>
                            ) : (
                              <div className="max-w-[220px] sm:max-w-[280px] truncate" title={p.name}>{p.name || p.code}</div>
                            )
                          )},
                          { label: 'Код', render: (p) => <span className="text-[color:var(--color-muted-foreground)]">{p.code}</span> },
                          { label: 'Остаток', headerClass: 'text-right', cellClass: 'text-right tabular-nums font-semibold', render: (p) => p.stock_qty.toLocaleString('ru-RU') },
                        ]}
                      />
                    )}
                  </ExpandableCard>
                )}
              </div>
            ) : (
              <div className="app-card p-8 text-center text-[color:var(--color-muted-foreground)]">Нет данных за выбранный период</div>
            )
          )}
        </>
      )}
    </div>
  );
}
