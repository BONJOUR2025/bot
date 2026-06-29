import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { BarChart2, RefreshCw, Image as ImageIcon, Calculator, Hammer, Users, Wallet, TrendingDown, UserRound } from 'lucide-react';
import { PieChart, Pie, Cell } from 'recharts';
import { toPng } from 'html-to-image';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MANAGER_POSITION = 'менеджер по работе с клиентами';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Math.round(Number(v)).toLocaleString('ru-RU')} ₽`);
const fmtShort = (v) => {
  v = Math.round(Number(v) || 0);
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} млн ₽`;
  if (Math.abs(v) >= 1e3) return `${Math.round(v / 1e3).toLocaleString('ru-RU')} тыс ₽`;
  return `${v} ₽`;
};
const pct = (part, whole) => (whole ? Math.round((part / whole) * 100) : 0);
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

const COLS = [
  { key: 'oklad', label: 'Оклад' },
  { key: 'commission', label: 'Комиссия / KPI' },
  { key: 'bonuses', label: 'Премии' },
  { key: 'penalties', label: 'Штрафы' },
  { key: 'advances', label: 'Авансы' },
  { key: 'gross', label: 'Начислено' },
  { key: 'to_pay', label: 'К выплате' },
];

const sumRows = (rows) => {
  const t = {};
  for (const c of COLS) t[c.key] = (rows || []).reduce((s, r) => s + (Number(r[c.key]) || 0), 0);
  return t;
};

// ── Per-category loaders ─────────────────────────────────────────────────────

async function loadAdmins(period) {
  const [y, m] = period.split('-').map(Number);
  const monthName = MONTHS_RU[m - 1].toUpperCase();
  const res = await api.get('payroll/calculate', { params: { month: monthName, year: y } });
  return (res.data?.rows || []).map((r) => ({
    name: r.employee_name || r.employee_code || '—',
    oklad: r.base_salary || 0,
    commission: r.total_commission || 0,
    bonuses: (r.bonuses || 0) + (r.excel_bonus || 0),
    penalties: r.penalties || 0,
    advances: r.advances || 0,
    gross: r.total_gross ?? ((r.base_salary || 0) + (r.total_commission || 0) + (r.bonuses || 0) + (r.excel_bonus || 0)),
    to_pay: r.total_net ?? 0,
  })).filter((r) => r.gross || r.oklad || r.commission || r.advances);
}

async function loadMasters(period) {
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const res = await api.get('masters/works', { params: { date_from: dateFrom, date_to: dateTo } });
  const data = res.data;
  const services = Array.isArray(data) ? data : (data.services || []);
  const map = {};
  for (const r of services) {
    if (r.master_salary == null) continue;
    const name = r.out_description || '—';
    map[name] = (map[name] || 0) + (Number(r.master_salary) || 0);
  }
  return Object.entries(map)
    .map(([name, sal]) => ({ name, oklad: 0, commission: sal, bonuses: 0, penalties: 0, advances: 0, gross: sal, to_pay: sal }))
    .sort((a, b) => b.gross - a.gross);
}

async function loadManagers(period) {
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDay(period)).padStart(2, '0')}`;
  const emp = await api.get('employees/', { params: { archived: false } }).then((r) => r.data || []);
  const managers = emp.filter((e) => e.status !== 'inactive' && (e.position || '').trim().toLowerCase() === MANAGER_POSITION);
  const rows = await Promise.all(managers.map(async (mgr) => {
    const plan = await api.get('manager-salary/plan', { params: { employee_code: mgr.id, period } }).then((r) => r.data).catch(() => ({}));
    const adv = await api.get('manager-salary/advances', { params: { employee_id: mgr.id } }).then((r) => r.data).catch(() => ({ total: 0 }));
    const inc = await api.get('incentives/', { params: { employee_id: mgr.id, date_from: dateFrom, date_to: dateTo } }).then((r) => r.data).catch(() => []);
    const bonuses = (inc || []).filter((i) => i.type === 'bonus').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    const penalties = (inc || []).filter((i) => i.type === 'penalty').reduce((s, i) => s + (Number(i.amount) || 0), 0);
    let met = null;
    if (mgr.amo_user_id) {
      met = await api.get('manager-salary/metrics', { params: { date_from: dateFrom, date_to: dateTo, amo_user_id: mgr.amo_user_id } }).then((r) => r.data).catch(() => null);
    }
    const calc = await api.post('manager-salary/calc', {
      oklad: plan.oklad, kpi_max: plan.kpi_max,
      revenue_plan: plan.revenue_plan, revenue_actual: met?.revenue_actual || 0,
      repair_plan_conv: plan.repair_plan_conv, repair_target_deals: met?.repair_target_deals || 0, repair_total_deals: met?.repair_total_deals || 0,
      sew_plan_conv: plan.sew_plan_conv, sew_target_deals: met?.sew_target_deals || 0, sew_total_deals: met?.sew_total_deals || 0, sew_new_leads: met?.sew_new_leads || 0,
      advances: adv?.total || 0, bonuses, penalties,
    }).then((r) => r.data).catch(() => null);
    if (!calc) return null;
    return {
      name: mgr.full_name || mgr.name, oklad: calc.oklad, commission: calc.kpi,
      bonuses: calc.bonuses, penalties: calc.penalties, advances: calc.advances,
      gross: calc.gross, to_pay: calc.to_pay,
    };
  }));
  return rows.filter(Boolean).sort((a, b) => b.gross - a.gross);
}

const CATS = [
  { key: 'admins', title: 'Администраторы', icon: Calculator, color: '#6366f1', load: loadAdmins },
  { key: 'masters', title: 'Мастера', icon: Hammer, color: '#f59e0b', load: loadMasters },
  { key: 'managers', title: 'Менеджеры', icon: Users, color: '#10b981', load: loadManagers },
];

// Fixed «agency» palette so the PNG looks identical regardless of app theme.
const INK = '#0f172a', MUTED = '#64748b', LINE = '#e2e8f0', BRAND = '#6366f1', DANGER = '#ef4444';

// ── Report pieces (fixed light palette) ──────────────────────────────────────

function KpiCard({ icon, label, value, sub, color = INK }) {
  return (
    <div className="rounded-xl border p-4" style={{ borderColor: LINE, background: '#fff' }}>
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: MUTED }}>
        {icon}{label}
      </div>
      <div className="mt-1.5 text-[26px] font-bold leading-none tabular-nums" style={{ color }}>{value}</div>
      {sub && <div className="mt-1.5 text-xs" style={{ color: MUTED }}>{sub}</div>}
    </div>
  );
}

function Bar({ label, value, max, color, right }) {
  const w = max > 0 ? Math.max((value / max) * 100, value > 0 ? 4 : 0) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="w-40 shrink-0 text-sm truncate" style={{ color: INK }}>{label}</div>
      <div className="flex-1 h-6 rounded-md" style={{ background: '#f1f5f9' }}>
        <div className="h-6 rounded-md flex items-center justify-end pr-2" style={{ width: `${w}%`, background: color, minWidth: value > 0 ? 40 : 0 }}>
        </div>
      </div>
      <div className="w-28 shrink-0 text-right text-sm font-semibold tabular-nums" style={{ color: INK }}>{right}</div>
    </div>
  );
}

function Section({ title, hint, children }) {
  return (
    <div>
      <div className="flex items-baseline gap-2 mb-3">
        <div className="h-4 w-1 rounded" style={{ background: BRAND }} />
        <h3 className="text-sm font-bold uppercase tracking-wide" style={{ color: INK }}>{title}</h3>
        {hint && <span className="text-xs" style={{ color: MUTED }}>{hint}</span>}
      </div>
      {children}
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function PayrollSummary() {
  const { toast } = useToast();
  const months = useMemo(() => recentMonths(12), []);
  const [period, setPeriod] = useState(months[0].value);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pnging, setPnging] = useState(false);
  const [generatedAt, setGeneratedAt] = useState('');
  const reportRef = useRef(null);
  const periodLabel = months.find((m) => m.value === period)?.label || period;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const results = await Promise.all(CATS.map((c) =>
        c.load(period).then((rows) => ({ rows })).catch((e) => ({ rows: [], error: e?.response?.data?.detail || e.message || 'ошибка' }))));
      const next = {};
      CATS.forEach((c, i) => { next[c.key] = results[i]; });
      setData(next);
      setGeneratedAt(new Date().toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' }));
    } finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  // Derived
  const cat = (k) => ({ rows: data?.[k]?.rows || [], error: data?.[k]?.error, totals: sumRows(data?.[k]?.rows) });
  const cats = CATS.map((c) => ({ ...c, ...cat(c.key) }));
  const tagged = cats.flatMap((c) => c.rows.map((r) => ({ ...r, catColor: c.color, catTitle: c.title })));
  const grand = sumRows(tagged);
  const headcount = tagged.length;
  const withholdings = grand.advances + grand.penalties;
  const donut = cats.filter((c) => c.totals.gross > 0).map((c) => ({ name: c.title, value: c.totals.gross, color: c.color }));
  const topEarners = [...tagged].sort((a, b) => b.to_pay - a.to_pay).slice(0, 6);
  const maxCat = Math.max(1, ...cats.map((c) => c.totals.gross));
  const maxTop = Math.max(1, ...topEarners.map((r) => r.to_pay));
  const comp = [
    { label: 'Оклад', value: grand.oklad, color: '#6366f1' },
    { label: 'Комиссия / KPI', value: grand.commission, color: '#10b981' },
    { label: 'Премии', value: grand.bonuses, color: '#f59e0b' },
  ].filter((s) => s.value > 0);

  async function downloadPng() {
    if (!reportRef.current) return;
    setPnging(true);
    try {
      const url = await toPng(reportRef.current, { backgroundColor: '#ffffff', pixelRatio: 2, cacheBust: true, skipFonts: true });
      const a = document.createElement('a');
      a.href = url;
      a.download = `ФОТ_${period}.png`;
      a.click();
      toast('PNG сохранён', 'success');
    } catch (e) {
      console.error(e);
      toast('Ошибка генерации PNG', 'error');
    } finally { setPnging(false); }
  }

  return (
    <div className="space-y-5 max-w-[1140px] mx-auto pb-12">
      {/* Controls (app chrome) */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
            <BarChart2 size={24} /> Сводный отчёт по ФОТ
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Администраторы, мастера и менеджеры за период · стильный PNG-отчёт</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="block">
            <span className="block text-xs font-medium uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">Период</span>
            <select className="input min-w-[160px]" value={period} onChange={(e) => setPeriod(e.target.value)}>
              {months.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
            </select>
          </label>
          <button className="btn btn--secondary flex items-center gap-1.5" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Обновить
          </button>
          <button className="btn btn--primary flex items-center gap-1.5" onClick={downloadPng} disabled={pnging || loading || !data}>
            <ImageIcon size={15} /> {pnging ? 'Генерирую…' : 'Скачать PNG'}
          </button>
        </div>
      </div>

      {loading && !data ? (
        <div className="app-card p-12 text-center text-[color:var(--color-muted-foreground)]">Считаю ФОТ по всем категориям…</div>
      ) : (
        <div className="overflow-x-auto rounded-2xl">
          {/* ════ Captured report (fixed 1080px, agency style) ════ */}
          <div ref={reportRef} style={{ width: 1080, background: '#fff', color: INK }} className="fot-report overflow-hidden">
            {/* Neutralise the app's global dark table styling inside the light report */}
            <style>{`.fot-report table,.fot-report thead,.fot-report tbody,.fot-report tfoot,.fot-report tr,.fot-report td,.fot-report th{background:transparent;border:0;color:inherit;box-shadow:none;}`}</style>
            {/* Header */}
            <div className="px-10 pt-9 pb-8 text-white flex items-end justify-between"
              style={{ background: 'linear-gradient(110deg,#4f46e5 0%,#7c3aed 55%,#9333ea 100%)' }}>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] opacity-80">Сводный отчёт</div>
                <div className="mt-1 text-[30px] font-extrabold leading-tight">Фонд оплаты труда</div>
                <div className="mt-1 text-sm opacity-90">{periodLabel} · администраторы · мастера · менеджеры</div>
              </div>
              <div className="text-right">
                <div className="text-[11px] font-semibold uppercase tracking-wide opacity-80">Итого начислено</div>
                <div className="text-[40px] font-extrabold leading-none tabular-nums">{fmtMoney(grand.gross)}</div>
                <div className="mt-1 text-sm opacity-90">к выплате {fmtMoney(grand.to_pay)}</div>
              </div>
            </div>

            <div className="px-10 py-8 space-y-8">
              {/* KPI cards */}
              <div className="grid grid-cols-4 gap-4">
                <KpiCard icon={<Wallet size={13} />} label="ФОТ за период" value={fmtMoney(grand.gross)} sub={`средняя ${fmtShort(headcount ? grand.gross / headcount : 0)} / чел.`} color={BRAND} />
                <KpiCard icon={<Wallet size={13} />} label="К выплате" value={fmtMoney(grand.to_pay)} sub={`${pct(grand.to_pay, grand.gross)}% от начисленного`} color="#10b981" />
                <KpiCard icon={<UserRound size={13} />} label="Сотрудников" value={String(headcount)} sub={cats.map((c) => `${c.title.slice(0, 4).toLowerCase()}. ${c.rows.length}`).join(' · ')} />
                <KpiCard icon={<TrendingDown size={13} />} label="Удержания" value={fmtMoney(withholdings)} sub={`авансы ${fmtShort(grand.advances)} · штрафы ${fmtShort(grand.penalties)}`} color={DANGER} />
              </div>

              {/* Charts row */}
              <div className="grid grid-cols-2 gap-6">
                <Section title="Доля категорий в ФОТ">
                  <div className="flex items-center gap-5">
                    <div className="relative" style={{ width: 200, height: 200 }}>
                      {donut.length > 0 ? (
                        <PieChart width={200} height={200}>
                          <Pie data={donut} dataKey="value" innerRadius={66} outerRadius={96} paddingAngle={donut.length > 1 ? 2 : 0} stroke="none" startAngle={90} endAngle={-270} isAnimationActive={false}>
                            {donut.map((d) => <Cell key={d.name} fill={d.color} />)}
                          </Pie>
                        </PieChart>
                      ) : <div className="w-full h-full rounded-full" style={{ background: '#f1f5f9' }} />}
                      <div className="absolute inset-0 flex flex-col items-center justify-center">
                        <div className="text-[10px] uppercase tracking-wide" style={{ color: MUTED }}>ФОТ</div>
                        <div className="text-base font-bold tabular-nums" style={{ color: INK }}>{fmtShort(grand.gross)}</div>
                      </div>
                    </div>
                    <div className="flex-1 space-y-2.5">
                      {cats.map((c) => (
                        <div key={c.key} className="flex items-center gap-2.5">
                          <span className="h-3 w-3 rounded-sm shrink-0" style={{ background: c.color }} />
                          <span className="text-sm flex-1" style={{ color: INK }}>{c.title}</span>
                          <span className="text-sm font-semibold tabular-nums" style={{ color: INK }}>{fmtMoney(c.totals.gross)}</span>
                          <span className="w-10 text-right text-xs tabular-nums" style={{ color: MUTED }}>{pct(c.totals.gross, grand.gross)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </Section>

                <Section title="ФОТ по категориям">
                  <div className="space-y-3 pt-1">
                    {cats.map((c) => (
                      <Bar key={c.key} label={c.title} value={c.totals.gross} max={maxCat} color={c.color} right={fmtMoney(c.totals.gross)} />
                    ))}
                  </div>
                </Section>
              </div>

              {/* Composition */}
              <Section title="Структура начислений" hint={`всего ${fmtMoney(grand.gross)}`}>
                <div className="h-7 w-full rounded-lg overflow-hidden flex" style={{ background: '#f1f5f9' }}>
                  {comp.map((s) => (
                    <div key={s.label} className="h-7 flex items-center justify-center text-[11px] font-semibold text-white"
                      style={{ width: `${pct(s.value, grand.gross)}%`, background: s.color }}>
                      {pct(s.value, grand.gross) >= 8 ? `${pct(s.value, grand.gross)}%` : ''}
                    </div>
                  ))}
                </div>
                <div className="mt-2.5 flex flex-wrap gap-x-6 gap-y-1">
                  {comp.map((s) => (
                    <div key={s.label} className="flex items-center gap-2 text-sm">
                      <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />
                      <span style={{ color: MUTED }}>{s.label}</span>
                      <span className="font-semibold tabular-nums" style={{ color: INK }}>{fmtMoney(s.value)}</span>
                    </div>
                  ))}
                  <div className="flex items-center gap-2 text-sm ml-auto">
                    <span style={{ color: MUTED }}>− удержания</span>
                    <span className="font-semibold tabular-nums" style={{ color: DANGER }}>{fmtMoney(withholdings)}</span>
                    <span style={{ color: MUTED }}>= к выплате</span>
                    <span className="font-bold tabular-nums" style={{ color: '#10b981' }}>{fmtMoney(grand.to_pay)}</span>
                  </div>
                </div>
              </Section>

              {/* Top earners */}
              {topEarners.length > 0 && (
                <Section title="Топ по выплате" hint="самые крупные выплаты за период">
                  <div className="space-y-2.5 pt-1">
                    {topEarners.map((r, i) => (
                      <Bar key={i} label={r.name} value={r.to_pay} max={maxTop} color={r.catColor} right={fmtMoney(r.to_pay)} />
                    ))}
                  </div>
                </Section>
              )}

              {/* Breakdown table */}
              <Section title="Детализация по сотрудникам">
                <div className="rounded-xl border overflow-hidden" style={{ borderColor: LINE }}>
                  <table className="w-full text-[13px] table-fixed">
                    <colgroup>
                      <col style={{ width: '20%' }} />
                      {COLS.map((c) => <col key={c.key} style={{ width: `${80 / COLS.length}%` }} />)}
                    </colgroup>
                    <thead>
                      <tr style={{ background: '#f8fafc', color: MUTED }} className="text-[10px] uppercase tracking-wide">
                        <th className="text-left font-semibold px-3 py-2">Сотрудник</th>
                        {COLS.map((c) => <th key={c.key} className="text-right font-semibold px-3 py-2">{c.label}</th>)}
                      </tr>
                    </thead>
                    {cats.map((c) => {
                      const Icon = c.icon;
                      return (
                        <tbody key={c.key}>
                          <tr style={{ background: '#fff', borderTop: `2px solid ${LINE}` }}>
                            <td colSpan={COLS.length + 1} className="px-3 py-1.5">
                              <div className="flex items-center justify-between">
                                <span className="font-bold flex items-center gap-1.5" style={{ color: c.color }}><Icon size={13} /> {c.title}
                                  <span className="text-[11px] font-normal" style={{ color: MUTED }}>· {c.rows.length}</span></span>
                                <span className="text-[12px]" style={{ color: MUTED }}>ФОТ <span className="font-bold" style={{ color: INK }}>{fmtMoney(c.totals.gross)}</span></span>
                              </div>
                            </td>
                          </tr>
                          {c.error ? (
                            <tr><td colSpan={COLS.length + 1} className="px-3 py-2 text-[12px]" style={{ color: DANGER }}>Не удалось загрузить: {c.error}</td></tr>
                          ) : c.rows.length === 0 ? (
                            <tr><td colSpan={COLS.length + 1} className="px-3 py-2 text-[12px]" style={{ color: MUTED }}>Нет данных за период.</td></tr>
                          ) : (<>
                            {c.rows.map((r, i) => (
                              <tr key={i} style={{ borderTop: `1px solid ${LINE}` }}>
                                <td className="px-3 py-1.5 font-medium break-words" style={{ color: INK }}>{r.name}</td>
                                {COLS.map((col) => (
                                  <td key={col.key} className="px-3 py-1.5 text-right tabular-nums"
                                    style={{ color: col.key === 'to_pay' ? BRAND : (col.key === 'penalties' || col.key === 'advances') && r[col.key] ? DANGER : INK, fontWeight: col.key === 'to_pay' ? 600 : 400 }}>
                                    {col.key === 'gross' || col.key === 'to_pay' ? fmtMoney(r[col.key]) : (r[col.key] ? fmtMoney(r[col.key]) : '—')}
                                  </td>
                                ))}
                              </tr>
                            ))}
                            <tr style={{ borderTop: `1px solid ${LINE}`, background: '#f8fafc' }}>
                              <td className="px-3 py-1.5 font-semibold" style={{ color: INK }}>Итого · {c.title.toLowerCase()}</td>
                              {COLS.map((col) => (
                                <td key={col.key} className="px-3 py-1.5 text-right tabular-nums font-semibold" style={{ color: col.key === 'to_pay' ? BRAND : INK }}>{fmtMoney(c.totals[col.key])}</td>
                              ))}
                            </tr>
                          </>)}
                        </tbody>
                      );
                    })}
                    <tfoot>
                      <tr style={{ borderTop: `2px solid ${INK}` }}>
                        <td className="px-3 py-2 font-extrabold" style={{ color: INK }}>ВСЕГО · {headcount} чел.</td>
                        {COLS.map((c) => (
                          <td key={c.key} className="px-3 py-2 text-right tabular-nums font-extrabold" style={{ color: c.key === 'gross' || c.key === 'to_pay' ? BRAND : INK }}>{fmtMoney(grand[c.key])}</td>
                        ))}
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </Section>
            </div>

            {/* Footer */}
            <div className="px-10 py-4 flex items-center justify-between text-[11px]" style={{ borderTop: `1px solid ${LINE}`, color: MUTED }}>
              <span>Сводный отчёт по фонду оплаты труда · {periodLabel}</span>
              <span>Сформировано {generatedAt}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
