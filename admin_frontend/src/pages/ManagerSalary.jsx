import { useEffect, useMemo, useState } from 'react';
import { Calculator, Wallet, RefreshCw, Trash2, ChevronDown, ChevronUp } from 'lucide-react';
import api from '../api';
import { useToast } from '../providers/ToastProvider.jsx';

const fmtMoney = (v) => (v === null || v === undefined ? '—' : `${Number(v).toLocaleString('ru-RU')} ₽`);
const fmtPct = (v) => (v === null || v === undefined ? '—' : `${(Number(v) * 100).toFixed(1)}%`);

function lastDayOfMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m, 0).getDate();
}

const num = (v) => (v === '' || v === null || v === undefined ? 0 : Number(v));

// One labelled input cell.
function NumField({ label, value, onChange, suffix, hint }) {
  return (
    <label className="block">
      <span className="block text-sm font-medium mb-1">{label}</span>
      <div className="flex items-center gap-2">
        <input type="number" className="input w-full" value={value}
          onChange={(e) => onChange(e.target.value)} />
        {suffix && <span className="text-sm text-[color:var(--color-muted-foreground)]">{suffix}</span>}
      </div>
      {hint && <p className="text-xs text-[color:var(--color-muted-foreground)] mt-1">{hint}</p>}
    </label>
  );
}

// One row of the KPI breakdown.
function KpiRow({ title, weight, max, factor, amount, zeroed, extra }) {
  return (
    <div className="flex items-center justify-between gap-3 py-2 border-t border-[color:var(--color-border)] first:border-t-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{title} <span className="text-xs text-[color:var(--color-muted-foreground)]">· вес {(weight * 100).toFixed(0)}%</span></div>
        <div className="text-xs text-[color:var(--color-muted-foreground)]">
          макс {fmtMoney(max)} · коэф {factor == null ? '—' : `${(Math.min(factor, 1) * 100).toFixed(1)}%`}{extra ? ` · ${extra}` : ''}
        </div>
      </div>
      <div className={`text-right whitespace-nowrap font-semibold tabular-nums ${zeroed ? 'text-[color:var(--color-muted-foreground)]' : 'text-[color:var(--color-text-primary)]'}`}>
        {fmtMoney(amount)}
      </div>
    </div>
  );
}

export default function ManagerSalary() {
  const { toast } = useToast();
  const [employees, setEmployees] = useState([]);
  const [managerId, setManagerId] = useState('');
  const now = new Date();
  const [period, setPeriod] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`);

  const [form, setForm] = useState({
    oklad: '', kpi_max: '',
    revenue_plan: '', revenue_actual: '',
    repair_plan_conv: '50', repair_target_deals: '', repair_total_deals: '',
    sew_plan_conv: '25', sew_target_deals: '', sew_total_deals: '', sew_new_leads: '',
    advances: '',
  });
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const [result, setResult] = useState(null);
  const [accruals, setAccruals] = useState([]);
  const [accruing, setAccruing] = useState(false);
  const [showHistory, setShowHistory] = useState(true);

  const manager = useMemo(() => employees.find((e) => String(e.id) === String(managerId)), [employees, managerId]);
  const dateFrom = `${period}-01`;
  const dateTo = `${period}-${String(lastDayOfMonth(period)).padStart(2, '0')}`;

  useEffect(() => { loadEmployees(); }, []);
  useEffect(() => { if (managerId) loadAccruals(); }, [managerId]);

  async function loadEmployees() {
    try {
      const res = await api.get('employees/', { params: { archived: false } });
      setEmployees(res.data.filter((e) => e.status !== 'inactive'));
    } catch (err) { console.error(err); }
  }

  async function loadAccruals() {
    try {
      const res = await api.get('manager-salary/accruals', { params: { employee_code: managerId, limit: 50 } });
      setAccruals(res.data || []);
    } catch (err) { console.error(err); }
  }

  // Server is the source of truth for the formula — recompute on change (debounced).
  const payload = useMemo(() => ({
    oklad: num(form.oklad), kpi_max: num(form.kpi_max),
    revenue_plan: num(form.revenue_plan), revenue_actual: num(form.revenue_actual),
    repair_plan_conv: num(form.repair_plan_conv) / 100,
    repair_target_deals: num(form.repair_target_deals), repair_total_deals: num(form.repair_total_deals),
    sew_plan_conv: num(form.sew_plan_conv) / 100,
    sew_target_deals: num(form.sew_target_deals), sew_total_deals: num(form.sew_total_deals),
    sew_new_leads: num(form.sew_new_leads), advances: num(form.advances),
  }), [form]);

  useEffect(() => {
    const t = setTimeout(async () => {
      try {
        const res = await api.post('manager-salary/calc', payload);
        setResult(res.data);
      } catch (err) { console.error(err); }
    }, 250);
    return () => clearTimeout(t);
  }, [payload]);

  async function loadMetrics() {
    if (!manager?.amo_user_id) {
      toast('У менеджера не привязан пользователь amoCRM (карточка сотрудника)', 'warning');
      return;
    }
    try {
      const res = await api.get('manager-salary/metrics', {
        params: { date_from: dateFrom, date_to: dateTo, amo_user_id: manager.amo_user_id },
      });
      const m = res.data;
      setForm((f) => ({
        ...f,
        revenue_actual: String(m.revenue_actual ?? ''),
        repair_target_deals: String(m.repair_target_deals ?? ''),
        repair_total_deals: String(m.repair_total_deals ?? ''),
        sew_target_deals: String(m.sew_target_deals ?? ''),
        sew_total_deals: String(m.sew_total_deals ?? ''),
        sew_new_leads: String(m.sew_new_leads ?? ''),
      }));
      toast('Метрики подтянуты из amoCRM', 'success');
    } catch (err) {
      const msg = err?.response?.data?.detail || 'amoCRM недоступен';
      toast(`Не удалось получить метрики: ${msg}`, 'error');
    }
  }

  async function loadAdvances() {
    if (!managerId) { toast('Выберите менеджера', 'warning'); return; }
    try {
      const res = await api.get('manager-salary/advances', { params: { employee_id: managerId, date_from: dateFrom, date_to: dateTo } });
      set('advances')(String(res.data.total || 0));
      toast(`Авансы за период: ${fmtMoney(res.data.total)} (${res.data.count})`, 'success');
    } catch (err) { console.error(err); toast('Не удалось загрузить авансы', 'error'); }
  }

  async function accrue() {
    if (!managerId) { toast('Выберите менеджера', 'warning'); return; }
    setAccruing(true);
    try {
      await api.post('manager-salary/accrue', {
        ...payload,
        employee_code: String(managerId),
        employee_name: manager?.full_name || manager?.name || '',
        user_id: String(managerId),
        period, date_from: dateFrom, date_to: dateTo,
      });
      toast('Начисление сохранено', 'success');
      loadAccruals();
    } catch (err) { console.error(err); toast('Ошибка начисления', 'error'); }
    finally { setAccruing(false); }
  }

  async function deleteAccrual(id) {
    if (!window.confirm('Удалить начисление?')) return;
    try { await api.delete(`manager-salary/accruals/${id}`); loadAccruals(); }
    catch (err) { console.error(err); toast('Ошибка удаления', 'error'); }
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <h2 className="text-2xl font-semibold tracking-tight text-[color:var(--color-text)] flex items-center gap-2">
        <Calculator size={24} /> Расчёт ЗП менеджеров
      </h2>

      {/* Manager + period */}
      <div className="app-card p-4 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-sm font-medium mb-1">Менеджер</span>
          <select className="input min-w-[220px]" value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">— выберите —</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>{(e.full_name || e.name)}{e.position ? ` · ${e.position}` : ''}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="block text-sm font-medium mb-1">Период</span>
          <input type="month" className="input" value={period} onChange={(e) => setPeriod(e.target.value)} />
        </label>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Inputs */}
        <div className="space-y-4">
          <div className="app-card p-4 space-y-3">
            <div className="font-semibold">Оклад и KPI</div>
            <div className="grid grid-cols-2 gap-3">
              <NumField label="Оклад" suffix="₽" value={form.oklad} onChange={set('oklad')} />
              <NumField label="KPI (макс.)" suffix="₽" value={form.kpi_max} onChange={set('kpi_max')} hint="Макс. сверх оклада" />
            </div>
          </div>

          <div className="app-card p-4 space-y-3">
            <div className="font-semibold">Планы</div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <NumField label="План выручки" suffix="₽" value={form.revenue_plan} onChange={set('revenue_plan')} />
              <NumField label="План конв. ремонта" suffix="%" value={form.repair_plan_conv} onChange={set('repair_plan_conv')} />
              <NumField label="План конв. пошива" suffix="%" value={form.sew_plan_conv} onChange={set('sew_plan_conv')} />
            </div>
          </div>

          <div className="app-card p-4 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="font-semibold">Факт (метрики)</div>
              <button className="btn btn--secondary text-xs flex items-center gap-1.5 whitespace-nowrap" onClick={loadMetrics}>
                <RefreshCw size={13} /> Из amoCRM
              </button>
            </div>
            <NumField label="Фактическая выручка (ремонт+пошив)" suffix="₽" value={form.revenue_actual} onChange={set('revenue_actual')} />
            <div className="grid grid-cols-2 gap-3">
              <NumField label="Ремонт: целевых сделок" value={form.repair_target_deals} onChange={set('repair_target_deals')} />
              <NumField label="Ремонт: всего сделок" value={form.repair_total_deals} onChange={set('repair_total_deals')} />
              <NumField label="Пошив: целевых сделок" value={form.sew_target_deals} onChange={set('sew_target_deals')} />
              <NumField label="Пошив: всего сделок" value={form.sew_total_deals} onChange={set('sew_total_deals')} />
              <NumField label="Пошив: новых лидов" value={form.sew_new_leads} onChange={set('sew_new_leads')} hint="< 50 → пошив = 0" />
            </div>
          </div>

          <div className="app-card p-4 space-y-3">
            <div className="font-semibold">Авансы (вычет)</div>
            <div className="flex items-end gap-2">
              <div className="flex-1"><NumField label="Выданные авансы за период" suffix="₽" value={form.advances} onChange={set('advances')} /></div>
              <button className="btn btn--secondary flex items-center gap-1.5 whitespace-nowrap" onClick={loadAdvances}>
                <RefreshCw size={14} /> Из выплат
              </button>
            </div>
          </div>
        </div>

        {/* Result */}
        <div className="space-y-4">
          <div className="app-card p-4">
            <div className="font-semibold mb-2">Расчёт</div>
            {result ? (
              <>
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div className="rounded-lg border border-[color:var(--color-border)] p-3">
                    <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">Начислено</div>
                    <div className="text-xl font-semibold">{fmtMoney(result.gross)}</div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)]">оклад {fmtMoney(result.oklad)} + KPI {fmtMoney(result.kpi)}</div>
                  </div>
                  <div className="rounded-lg border border-[color:var(--color-border)] p-3">
                    <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)]">К выплате</div>
                    <div className="text-xl font-semibold text-[color:var(--color-primary)]">{fmtMoney(result.to_pay)}</div>
                    <div className="text-xs text-[color:var(--color-muted-foreground)]">− авансы {fmtMoney(result.advances)}</div>
                  </div>
                </div>
                <div className="rounded-lg border border-[color:var(--color-border)] p-3">
                  <div className="text-[11px] uppercase tracking-wide text-[color:var(--color-muted-foreground)] mb-1">KPI · максимум {fmtMoney(result.kpi_max)}</div>
                  <KpiRow title="Выручка" weight={result.weights.revenue} max={result.revenue.max}
                    factor={result.revenue.ratio} amount={result.revenue.amount} zeroed={result.revenue.zeroed}
                    extra={`факт/план ${fmtPct(result.revenue.ratio)}`} />
                  <KpiRow title="Конверсия ремонта" weight={result.weights.repair} max={result.repair.max}
                    factor={result.repair.ratio} amount={result.repair.amount} zeroed={result.repair.zeroed}
                    extra={`конв ${fmtPct(result.repair.conv)}`} />
                  <KpiRow title="Конверсия пошива" weight={result.weights.sew} max={result.sew.max}
                    factor={result.sew.ratio} amount={result.sew.amount} zeroed={result.sew.zeroed}
                    extra={result.sew.leads_gate_failed ? `лидов ${result.sew.new_leads} < ${result.sew.min_leads}` : `конв ${fmtPct(result.sew.conv)}`} />
                </div>
                <button className="btn btn--primary w-full mt-3 flex items-center justify-center gap-2" onClick={accrue} disabled={accruing || !managerId}>
                  <Wallet size={16} /> {accruing ? 'Начисляю…' : 'Начислить'}
                </button>
              </>
            ) : (
              <div className="text-sm text-[color:var(--color-muted-foreground)]">Заполните поля — расчёт появится здесь.</div>
            )}
          </div>
        </div>
      </div>

      {/* History */}
      <div className="app-card overflow-hidden">
        <button type="button" onClick={() => setShowHistory((v) => !v)}
          className="w-full flex items-center justify-between gap-3 px-4 py-3">
          <span className="font-medium">Журнал начислений {manager ? `· ${manager.full_name || manager.name}` : ''} <span className="text-xs text-[color:var(--color-muted-foreground)]">({accruals.length})</span></span>
          {showHistory ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
        {showHistory && (
          <div className="border-t border-[color:var(--color-border)]">
            {!managerId ? (
              <div className="px-4 py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">Выберите менеджера, чтобы увидеть историю начислений.</div>
            ) : accruals.length === 0 ? (
              <div className="px-4 py-6 text-center text-sm text-[color:var(--color-muted-foreground)]">Начислений пока нет.</div>
            ) : (
              <ul className="divide-y divide-[color:var(--color-border)]">
                {accruals.map((a) => (
                  <li key={a.id} className="px-4 py-2.5 text-sm flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="font-medium">{a.period} <span className="text-xs text-[color:var(--color-muted-foreground)]">· {a.created_at?.slice(0, 16).replace('T', ' ')}</span></div>
                      <div className="text-xs text-[color:var(--color-muted-foreground)]">
                        оклад {fmtMoney(a.result?.oklad)} · KPI {fmtMoney(a.result?.kpi)} · авансы {fmtMoney(a.result?.advances)}
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      <span className="font-semibold tabular-nums text-[color:var(--color-primary)]">{fmtMoney(a.result?.to_pay)}</span>
                      <button onClick={() => deleteAccrual(a.id)} className="text-[color:var(--color-muted-foreground)] hover:text-[color:var(--color-danger)]" title="Удалить">
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
