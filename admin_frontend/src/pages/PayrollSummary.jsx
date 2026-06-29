import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import { BarChart2, RefreshCw, Image as ImageIcon, Calculator, Hammer, Users } from 'lucide-react';
import { toPng } from 'html-to-image';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const MANAGER_POSITION = 'менеджер по работе с клиентами';
const MONTHS_RU = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Math.round(Number(v)).toLocaleString('ru-RU')} ₽`);
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

// Unified column set for the breakdown table.
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
  const monthName = MONTHS_RU[m - 1].toUpperCase();   // payroll months = Excel sheet names
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
  // Мастера — сдельная оплата: вся сумма как «комиссия», начислено = к выплате.
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
  { key: 'admins', title: 'Администраторы', icon: Calculator, load: loadAdmins },
  { key: 'masters', title: 'Мастера', icon: Hammer, load: loadMasters },
  { key: 'managers', title: 'Менеджеры', icon: Users, load: loadManagers },
];

// ── Pieces ───────────────────────────────────────────────────────────────────

function cell(value, key) {
  if (key === 'gross' || key === 'to_pay') return fmtMoney(value);
  return value ? fmtMoney(value) : '—';
}

function Tile({ label, value, accent, highlight }) {
  return (
    <div className={`app-card px-4 py-3 ${highlight ? 'ring-1 ring-[color:var(--color-primary)]' : ''}`}>
      <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">{label}</div>
      <div className={`mt-1 text-xl font-bold tabular-nums whitespace-nowrap ${accent || 'text-[color:var(--color-text-primary)]'}`}>{value}</div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function PayrollSummary() {
  const { toast } = useToast();
  const months = useMemo(() => recentMonths(12), []);
  const [period, setPeriod] = useState(months[0].value);
  const [data, setData] = useState(null);     // { admins, masters, managers }
  const [loading, setLoading] = useState(false);
  const [pnging, setPnging] = useState(false);
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
    } finally { setLoading(false); }
  }, [period]);

  useEffect(() => { load(); }, [load]);

  const allRows = data ? [...(data.admins?.rows || []), ...(data.masters?.rows || []), ...(data.managers?.rows || [])] : [];
  const grand = sumRows(allRows);

  async function downloadPng() {
    if (!reportRef.current) return;
    setPnging(true);
    try {
      const bg = (getComputedStyle(document.documentElement).getPropertyValue('--color-bg') || '#0b0f17').trim() || '#0b0f17';
      const url = await toPng(reportRef.current, { backgroundColor: bg, pixelRatio: 2, cacheBust: true, skipFonts: true });
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
    <div className="space-y-5 max-w-6xl mx-auto pb-12">
      {/* Header + controls */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
            <BarChart2 size={24} /> Сводный отчёт по ФОТ
          </h2>
          <p className="text-sm text-[color:var(--color-muted-foreground)] mt-0.5">Администраторы, мастера и менеджеры за период — с разбивкой</p>
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
        <div className="overflow-x-auto">
          {/* Captured report */}
          <div ref={reportRef} className="min-w-[940px] space-y-5 p-5 rounded-2xl" style={{ background: 'var(--color-bg)' }}>
            <div className="flex items-end justify-between gap-3">
              <div>
                <div className="text-lg font-semibold">Фонд оплаты труда · {periodLabel}</div>
                <div className="text-xs text-[color:var(--color-muted-foreground)]">Сводный отчёт по администраторам, мастерам и менеджерам</div>
              </div>
              <div className="text-right">
                <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">Итого начислено (ФОТ)</div>
                <div className="text-2xl font-bold tabular-nums text-[color:var(--color-primary)]">{fmtMoney(grand.gross)}</div>
              </div>
            </div>

            {/* Tiles */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <Tile label="Администраторы" value={fmtMoney(sumRows(data?.admins?.rows).gross)} />
              <Tile label="Мастера" value={fmtMoney(sumRows(data?.masters?.rows).gross)} />
              <Tile label="Менеджеры" value={fmtMoney(sumRows(data?.managers?.rows).gross)} />
              <Tile label="Итого к выплате" value={fmtMoney(grand.to_pay)} accent="text-[color:var(--color-primary)]" highlight />
            </div>

            {/* One aligned breakdown table: a tbody per category + grand total */}
            <div className="app-card overflow-hidden">
              <table className="w-full text-sm table-fixed">
                <colgroup>
                  <col style={{ width: '20%' }} />
                  {COLS.map((c) => <col key={c.key} style={{ width: `${80 / COLS.length}%` }} />)}
                </colgroup>
                <thead>
                  <tr className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] border-b border-[color:var(--color-border)]">
                    <th className="text-left font-medium px-4 py-2">Сотрудник</th>
                    {COLS.map((c) => <th key={c.key} className="text-right font-medium px-4 py-2">{c.label}</th>)}
                  </tr>
                </thead>
                {CATS.map((c) => {
                  const cat = data?.[c.key];
                  const rows = cat?.rows || [];
                  const tot = sumRows(rows);
                  const Icon = c.icon;
                  return (
                    <tbody key={c.key} className="border-t-4 border-[color:var(--color-border)]">
                      <tr className="bg-[color:var(--color-bg-secondary)]">
                        <td colSpan={COLS.length + 1} className="px-4 py-2">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-semibold flex items-center gap-2"><Icon size={15} /> {c.title}
                              <span className="text-xs font-normal text-[color:var(--color-muted-foreground)]">· {rows.length}</span>
                            </span>
                            <span className="text-sm">ФОТ <span className="font-semibold tabular-nums">{fmtMoney(tot.gross)}</span></span>
                          </div>
                        </td>
                      </tr>
                      {cat?.error ? (
                        <tr><td colSpan={COLS.length + 1} className="px-4 py-3 text-sm text-[color:var(--color-danger)]">Не удалось загрузить: {cat.error}</td></tr>
                      ) : rows.length === 0 ? (
                        <tr><td colSpan={COLS.length + 1} className="px-4 py-3 text-sm text-[color:var(--color-muted-foreground)]">Нет данных за период.</td></tr>
                      ) : (<>
                        {rows.map((r, i) => (
                          <tr key={i} className="border-t border-[color:var(--color-border)]">
                            <td className="px-4 py-2 font-medium break-words">{r.name}</td>
                            {COLS.map((col) => (
                              <td key={col.key} className={`px-4 py-2 text-right tabular-nums ${col.key === 'to_pay' ? 'text-[color:var(--color-primary)] font-semibold' : (col.key === 'penalties' || col.key === 'advances') && r[col.key] ? 'text-[color:var(--color-danger)]' : ''}`}>
                                {cell(r[col.key], col.key)}
                              </td>
                            ))}
                          </tr>
                        ))}
                        <tr className="border-t border-[color:var(--color-border)] font-semibold">
                          <td className="px-4 py-2">Итого · {c.title.toLowerCase()}</td>
                          {COLS.map((col) => (
                            <td key={col.key} className={`px-4 py-2 text-right tabular-nums ${col.key === 'to_pay' ? 'text-[color:var(--color-primary)]' : ''}`}>{fmtMoney(tot[col.key])}</td>
                          ))}
                        </tr>
                      </>)}
                    </tbody>
                  );
                })}
                <tfoot>
                  <tr className="border-t-4 border-[color:var(--color-border)] font-bold bg-[color:var(--color-bg-secondary)]">
                    <td className="px-4 py-3">ВСЕГО · {allRows.length} чел.</td>
                    {COLS.map((c) => (
                      <td key={c.key} className={`px-4 py-3 text-right tabular-nums ${c.key === 'gross' || c.key === 'to_pay' ? 'text-[color:var(--color-primary)]' : ''}`}>{fmtMoney(grand[c.key])}</td>
                    ))}
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
